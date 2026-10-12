import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/authOptions";
import * as process from "node:process";
import { NextRequest, NextResponse } from "next/server";
import { nlog } from "@/lib/nlog/serverLog";
import { AUTH_ROUTES } from "@/lib/constants";
import { getToken, JWT } from "next-auth/jwt";
/**
 * ==========================================================
 * Keycloak SSO 로그아웃 API Route
 *
 * 별도 API Route:
 *   - NextAuth의 signout()은 NextAuth 세션만 삭제
 *   - Keycloak SSO 세션은 브라우저가 직접 방문해야 쿠키가 삭제됨
 *   - 서버 fetch()로는 브라우저 쿠키 제거 불가
 *
 * flow:
 *   1. 클라이언트 -> window.location.href = "/api/auth/logout"
 *   2. 로그아웃 route -> Keycloak logout URL 조회 (id_token_hint 포함)
 *   3. 브라우저를 Keycloak logout으로 리다이렉트
 *   4. Keycloak SSO 쿠키 삭제 후 -> post_logout_redirect_uri로 이동
 *   5. /api/auth/signout -> NextAuth 세션 삭제 -> HOME("/")으로 이동
 *
 * 호출: AUTH_ROUTES.LOGOUT ("/api/auth/logout")
 * ==========================================================
 */

/** NextAuth 쿠키 삭제 */
function clearAuthCookies(response: NextResponse): void {
  const cookieNames: string[] = [
    "next-auth.session-token",
    // "next-auth.session-token.0",
    // "next-auth.session-token.1",
    // "next-auth.session-token.2",
    "next-auth.csrf-token",
    "next-auth.callback-url",
    "__Secure-next-auth.session-token",
    // "__Secure-next-auth.session-token.0",
    // "__Secure-next-auth.session-token.1",
    // "__Secure-next-auth.session-token.2",
    "__Secure-next-auth.csrf-token",
    "__Secure-next-auth.callback-url",
  ];

  for (let i: number = 0; i <= 5; i++) {
    cookieNames.push(`next-auth.session-token.${i}`);
    cookieNames.push(`__Secure-next-auth.session-token.${i}`);
  }

  /** 삭제 실행 */
  cookieNames.forEach((name: string): void => {
    response.cookies.delete(name);
  });
}

type ExtendedJwt = JWT & { idToken?: string };

export async function GET(request: NextRequest): Promise<NextResponse<unknown>> {
  const { searchParams } = request.nextUrl;
  const forceLogin: boolean = searchParams.get("force") === "true";

  try {
    const token: JWT | null = await getToken({
      req: request,
      secret: process.env.NEXTAUTH_SECRET,
    });

    console.log("[logout token 확인]", {
      token있음: !!token,
      idToken있음: !!(token as ExtendedJwt | null)?.idToken,
      key목록: token ? Object.keys(token) : [],
    });

    // 현재 세션에서 userId, idToken 조회
    const session: Session | null = await getServerSession(authOptions);
    const userId: string = session?.userId ?? "unknown";
    // session 체인에서 직접 idToken 조회
    const idToken: string | null = (token as ExtendedJwt | null)?.idToken ?? session?.idToken ?? null;

    nlog.log("[SSO 로그아웃 START]", {
      userId,
      idToken: idToken ? "있음" : "없음(SSO 안 끊김)",
      force: forceLogin,
    });

    // idToken 있음 -> Keycloak SSO 세션 종료
    if (idToken) {
      const keycloakLogoutUrl = new URL(
        `${process.env.KEYCLOAK_ISSUER}/protocol/openid-connect/logout`
      );

      nlog.log("[SSO 로그아웃 idToken]", {
        userId,
        idToken: idToken ? "있음" : "없음",
      });

      // id_token_hint -> Keycloak 확인 화면 없이 로그아웃
      keycloakLogoutUrl.searchParams.set("id_token_hint", idToken);

      // Keycloak 로그아웃 완료 후 -> callback에서 쿠키삭제 -> Home으로 이동
      keycloakLogoutUrl.searchParams.set(
        "post_logout_redirect_uri",
        `${process.env.NEXTAUTH_URL}${AUTH_ROUTES.CALLBACK}`
      );

      nlog.auth.logout(userId);
      return NextResponse.redirect(keycloakLogoutUrl.toString());
    }

    // idToken 없음 + force -> 세션 만료 상황 -> Keycloak 로그인 강제
    if (forceLogin) {
      nlog.warn({ category: "AUTH", msg: `idToken 없음 - NextAuth 세션만 삭제: ${userId}` });
      const response: NextResponse<unknown> = NextResponse.redirect(
        `${process.env.NEXTAUTH_URL}${AUTH_ROUTES.CALLBACK}`
      );
      clearAuthCookies(response);
      return response;
    }

    // idToken 없음 -> 쿠키 삭제 + home이동
    nlog.warn({ category: "AUTH", msg: `idToken 없음 - NextAuth 세션만 삭제: ${userId}` });
    const response: NextResponse<unknown> = NextResponse.redirect(
      `${process.env.NEXTAUTH_URL}${AUTH_ROUTES.CALLBACK}`
    );

    clearAuthCookies(response);
    return response;
  } catch (error) {
    nlog.error({ category: "AUTH", msg: "SSO 로그아웃 실패", error: String(error) });

    // 실패 시 Home으로 이동
    return NextResponse.redirect(`${process.env.NEXTAUTH_URL}/`);
  }
}
