// app/api/auth/keycloak/route.ts
//
// ============================================================
// [수정 요약 — 이슈 1: 두 번 로그인 / State cookie missing]
// ------------------------------------------------------------
// 원래 문제:
//   - 첫 로그인이 실패하고 두 번째에 성공
//   - 2시간 방치 후 재로그인 시 "State cookie was missing"
//
// 원인 (2가지 쿠키 충돌):
//   (1) error 재진입 시 response.cookies.delete()로 state/pkce를 지우는데,
//       같은 응답에서 signin이 주는 "새 state/pkce"와 충돌
//       → 새 쿠키가 빈 값(Expires=1970)으로 덮어써짐 → state 검증 실패
//   (2) csrf 쿠키 이중 전달
//       → signin 응답에 csrf가 이미 있는데 마지막에 또 append → 충돌
//
// 수정:
//   [A] error 시 cookiesToDelete 삭제 블록 "전체 제거"
//       (signin 새 쿠키가 같은 이름이라 자동으로 옛 쿠키를 덮어쓰므로 delete 불필요)
//   [B] 마지막 csrf 쿠키 중복 append "제거"
//       (signin 응답 cookies에 이미 포함됨)
// ============================================================

import { NextResponse } from "next/server";
import { nlog } from "@/lib/nlog/serverLog";

/**
 * ============================================================
 * Keycloak 직접 redirect
 * ============================================================
 * NextAuth "Sign in with Keycloak" 선택 화면 완전 스킵
 */
export async function GET(
  request: Request,
): Promise<NextResponse<unknown>> {
  const { searchParams } = new URL(request.url);
  const callbackUrl = searchParams.get("callbackUrl") || "/";

  // 에러 후 재진입 감지 (로그만 남김 — 쿠키는 건드리지 않음)
  const error = searchParams.get("error");

  if (error) {
    nlog.log("[keycloak/route] 에러 후 재진입", error);
  }

  const baseUrl = process.env.NEXTAUTH_URL!;

  // CSRF 토큰 가져오기
  const csrfRes = await fetch(`${baseUrl}/api/auth/csrf`, {
    headers: {
      cookie: request.headers.get("cookie") || "",
    },
  });

  const csrfData = await csrfRes.json();
  const csrfToken = csrfData.csrfToken;

  // CSRF 쿠키 전달 용 (signin POST 요청 헤더에만 사용 — 응답엔 중복 전달하지 않음)
  const csrfCookie = csrfRes.headers.get("set-cookie") || "";

  // NextAuth signin POST - Keycloak provider 직접 호출
  const signinRes = await fetch(`${baseUrl}/api/auth/signin/keycloak`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      cookie: [request.headers.get("cookie") || "", csrfCookie]
        .filter(Boolean)
        .join("; "),
    },
    body: new URLSearchParams({
      csrfToken,
      callbackUrl,
    }).toString(),
    redirect: "manual", // 리다이렉트를 따라가지 않음
  });

  // NextAuth가 반환한 Keycloak 인증 URL로 리다이렉트
  const keycloakAuthUrl = signinRes.headers.get("location");

  if (keycloakAuthUrl) {
    const response = NextResponse.redirect(keycloakAuthUrl);

    // ───────────────────────────────────────────────────────
    // [수정 A] ❌ 제거됨 — error 재진입 시 state/pkce 삭제 블록
    //
    //   기존 코드:
    //     if (error) {
    //       const cookiesToDelete = [
    //         "next-auth.state",
    //         "next-auth.pkce.code_verifier",
    //         "next-auth.callback-url",
    //         "__Host-next-auth.state",
    //         "__Host-next-auth.pkce.code_verifier",
    //         "__Host-next-auth.callback-url",
    //         "__Secure-next-auth.state",
    //         "__Secure-next-auth.pkce.code_verifier",
    //         "__Secure-next-auth.callback-url",
    //       ];
    //       cookiesToDelete.forEach((name) => response.cookies.delete(name));
    //       nlog.log("[keycloak/route 쿠키 정리 완료]");
    //     }
    //
    //   제거 이유:
    //     - delete는 "빈 값 + Expires=1970" Set-Cookie를 응답에 추가함
    //     - 아래에서 signin이 주는 "새 state/pkce"도 같은 이름으로 추가됨
    //     - 같은 이름 Set-Cookie 충돌 → 새 쿠키가 빈 값으로 덮어써짐
    //     - 결과: state 검증 실패 → 첫 로그인 실패(두 번 로그인)
    //     - 새 state는 같은 이름이라 옛 쿠키를 자동으로 덮어쓰므로 delete 자체가 불필요
    // ───────────────────────────────────────────────────────

    // NextAuth가 설정한 (state, pkce, csrf 등)을 브라우저에 전달
    // ※ 이 cookies 배열에 새 state/pkce/csrf가 모두 포함되어 있음
    const cookies = signinRes.headers.getSetCookie?.() || [];

    cookies.forEach((cookie): void => {
      response.headers.append("set-cookie", cookie);
    });

    // ───────────────────────────────────────────────────────
    // [수정 B] ❌ 제거됨 — csrf 쿠키 중복 전달
    //
    //   기존 코드:
    //     if (csrfCookie) {
    //       response.headers.append("set-cookie", csrfCookie);
    //     }
    //
    //   제거 이유:
    //     - 위 cookies(signin 응답)에 csrf 쿠키가 이미 포함됨
    //     - 또 append하면 csrf 쿠키가 2개 심겨 충돌 → 검증 흐름 꼬임
    //     - csrfCookie는 위쪽 signin POST 요청 "헤더"에만 쓰면 충분
    // ───────────────────────────────────────────────────────

    return response;
  }

  return NextResponse.redirect(`${baseUrl}/`);
}
