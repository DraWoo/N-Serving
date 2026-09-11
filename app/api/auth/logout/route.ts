// app/api/auth/logout/route.ts (redirect 대상 부분 발췌)
//
// ============================================================
// [수정 요약 — 이슈 4: 로그아웃 후 자동 로그인 (SSO 안 끊김)]
// ------------------------------------------------------------
// 원래 문제:
//   - 로그아웃 후 즐겨찾기 재접속 시 로그인 화면 없이 자동 진입
//   - Network: logout → keycloak(로그인) 호출,
//     Location이 /openid-connect/auth?prompt=login (= 로그인 시작)
//
// 원인:
//   - logout route가 로그아웃 후 돌아갈 곳을 AUTH_ROUTES.LOGIN(/api/auth/keycloak)으로 지정
//   - 즉 "로그아웃 → 곧바로 로그인 시작" 구조
//   - Keycloak SSO 세션이 끊기기 전에 재로그인 → SSO 살아있으면 자동 진입
//
// 수정:
//   - post_logout_redirect_uri 및 forceLogin redirect를
//     AUTH_ROUTES.LOGIN → AUTH_ROUTES.CALLBACK 으로 변경
//   - CALLBACK(/api/auth/logout/callback)은 쿠키 전부 삭제 후 홈으로 보내는 안전한 종착지
//   - LOGIN으로 보내면 로그아웃이 "종착"이 아니라 "새 로그인의 출발"이 됨
// ============================================================

import { NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/authOptions";
import { AUTH_ROUTES } from "@/lib/constants";
import { nlog } from "@/lib/nlog/serverLog";

// clearAuthCookies(...) 정의는 기존 그대로

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const forceLogin = searchParams.get("force") === "true";

  try {
    const session = await getServerSession(authOptions);
    const userId = session?.userId ?? "unknown";
    const idToken = session?.idToken ?? null;

    nlog.log("[SSO 로그아웃 START]", {
      userId,
      idToken: idToken ? "있음" : "없음",
      force: forceLogin,
    });

    // ── idToken 있음 → Keycloak SSO 세션 종료 ──
    if (idToken) {
      const keycloakLogoutUrl = new URL(
        `${process.env.KEYCLOAK_ISSUER}/protocol/openid-connect/logout`,
      );

      // id_token_hint → Keycloak 확인 화면 없이 로그아웃
      keycloakLogoutUrl.searchParams.set("id_token_hint", idToken);

      // ───────────────────────────────────────────────────────
      // [수정] post_logout_redirect_uri: LOGIN → CALLBACK
      //
      //   ❌ 기존:
      //     `${process.env.NEXTAUTH_URL}${AUTH_ROUTES.LOGIN}`
      //     → 로그아웃 직후 /api/auth/keycloak(로그인 시작) → SSO 끊기기 전 재로그인
      //
      //   ✅ 수정:
      //     `${process.env.NEXTAUTH_URL}${AUTH_ROUTES.CALLBACK}`
      //     → 쿠키 삭제 후 홈으로 가는 종착지. 로그인 시작 안 함.
      // ───────────────────────────────────────────────────────
      keycloakLogoutUrl.searchParams.set(
        "post_logout_redirect_uri",
        `${process.env.NEXTAUTH_URL}${AUTH_ROUTES.CALLBACK}`, // ✅ LOGIN → CALLBACK
      );

      nlog.auth.logout(userId);
      return NextResponse.redirect(keycloakLogoutUrl.toString());
    }

    // ── idToken 없음 + force → 세션 만료 상황 ──
    if (forceLogin) {
      nlog.warn("AUTH", `idToken 없음 - NextAuth 세션만 삭제: ${userId}`);

      // ───────────────────────────────────────────────────────
      // [수정] forceLogin redirect: LOGIN → CALLBACK
      //
      //   ❌ 기존:
      //     `${process.env.NEXTAUTH_URL}${AUTH_ROUTES.LOGIN}`
      //     → 쿠키 지우자마자 로그인 시작 → 자동 진입 위험
      //
      //   ✅ 수정:
      //     `${process.env.NEXTAUTH_URL}${AUTH_ROUTES.CALLBACK}`
      //     → 쿠키 삭제 후 홈. 사용자가 직접 다시 로그인하게 함.
      // ───────────────────────────────────────────────────────
      const response = NextResponse.redirect(
        `${process.env.NEXTAUTH_URL}${AUTH_ROUTES.CALLBACK}`, // ✅ LOGIN → CALLBACK
      );
      clearAuthCookies(response);
      return response;
    }

    // ── idToken 없음 → 쿠키 삭제 + home 이동 (기존 그대로) ──
    nlog.warn("AUTH", `idToken 없음 - NextAuth 세션만 삭제: ${userId}`);
    const response = NextResponse.redirect(
      `${process.env.NEXTAUTH_URL}${AUTH_ROUTES.CALLBACK}`,
    );
    clearAuthCookies(response);
    return response;
  } catch (error) {
    nlog.error("AUTH", "SSO 로그아웃 실패", { error: String(error) });
    // 실패 시 Home으로 이동
    return NextResponse.redirect(`${process.env.NEXTAUTH_URL}/`);
  }
}

// 참고: clearAuthCookies는 state/pkce를 삭제하지 않음 (OAuth 검증 보존)
//       session-token / csrf-token / callback-url 만 삭제
