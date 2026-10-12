import { NextResponse } from 'next/server';
import { nlog } from "@/lib/nlog/serverLog";

/**
 * ==========================================================
 * Keycloak 직접 redirect
 * ==========================================================
 * NextAuth "Sign in with Keycloak" 선택 화면 완전 스킵
 *
 * ==========================================================
 * 변경 내역:
 * - [20260618] - 두번 로그인 시 장시간 방치 시 state cookie was missing 수정
 * - [20260710] - csrf 쿠키 릴레이 getSetCookie() 배열방식으로 수정
 *               에러 후 재진입 시 만료된 OAuth 쿠키(state/pkce/nonce) 삭제 추가
 * ==========================================================
 */

// ==========================================
// Keycloak 직접 redirect
// ==========================================
export async function GET(request: Request): Promise<NextResponse<unknown>> {
  const { searchParams } = new URL(request.url);
  let callbackUrl: string = searchParams.get("callbackUrl") || "/";

  /** 에러 후 재진입 감지 */
  const error: string | null = searchParams.get("error");

  if (error) {
    nlog.log(`[AUDIT][keycloak/route] Error 후 재진입: ${error}`);
  }

  const baseUrl: string = process.env.NEXTAUTH_URL!;

  /** callback URL 검증 */
  try {
    const cb = new URL(callbackUrl, baseUrl);
    if (cb.origin !== new URL(baseUrl).origin) callbackUrl = "/";
  } catch {
    callbackUrl = "/";
  }

  // CSRF 토큰 가져오기
  const csrfRes: Response = await fetch(`${baseUrl}/api/auth/csrf`, {
    signal: AbortSignal.timeout(10_000), // Keycloak/ 서버 무응답 시 무한 대기 방지
    headers: {
      cookie: request.headers.get("cookie") || ""
    },
  });

  const csrfData: any = await csrfRes.json();
  const csrfToken: any = csrfData.csrfToken;

  // CSRF 쿠키 전달 용(signin POST 요청 헤더에만 사용 - 응답엔 중복 전달 X)
  // const csrfCookie = csrfRes.headers.get("set-cookie") || "";
  const csrfCookies: string[] = csrfRes.headers.getSetCookie?.() ?? [];

  // NextAuth signin POST - Keycloak provider 직접 호출
  const signinRes: Response = await fetch(`${baseUrl}/api/auth/signin/keycloak`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      cookie: [request.headers.get("cookie") || "",
        ...csrfCookies.map((c: string) => c.split(";")[0])
      ]
      .filter(Boolean)
      .join("; "),
    },
    body: new URLSearchParams({
      csrfToken,
      callbackUrl,
    }).toString(),
    redirect: "manual", // 리다이렉트를 따라가지 않음
  });

  // NextAuth가 변환한 Keycloak 인증 URL로 리다이렉트
  const keycloakAuthUrl: string | null = signinRes.headers.get("location");
  if (keycloakAuthUrl) {
    const response: NextResponse<unknown> = NextResponse.redirect(keycloakAuthUrl);

    /**
     * 에러 후 재진입 시: 만료된 옛 state/pkce 잔재를 정리
     * 새로 발급된 것은 아래 append
     * 삭제 후 재설정이 한 응답에서 순서대로 적용됨
     */
    if (error) {
      response.cookies.delete("next-auth-state");
      response.cookies.delete("next-auth.pkce.code_verifier");
      response.cookies.delete("next-auth.nonce");
    } else {
      // [TEST] 판정 로그 - 정상 로그인에서 찍혀야 정상
      nlog.log("[KC-CLEAN] 정상 흐름 - 청소 미실행");
    }

    // 로그인 시 새 쿠키(state/pkce)를 설정
    const cookies: string[] = signinRes.headers.getSetCookie?.() || [];

    // 체크 재진입 시 signin이 새 state/pkce를 줬는지
    console.log("[keycloak/route] ERROR:", !!error);
    console.log("[keycloak/route] 발급 쿠키:", cookies.map((c: string) => c.split("=")[0]));
    cookies.forEach((cookie: string) => {
      response.headers.append("set-cookie", cookie);
    });
    csrfCookies.forEach((cookie: string) => {
      response.headers.append("set-cookie", cookie);
    });

    return response;
  }

  return NextResponse.redirect(`${baseUrl}/`);
}
