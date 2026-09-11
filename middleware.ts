// middleware.ts (토큰 처리 부분 발췌)
//
// ============================================================
// [수정 요약 — 이슈 3: 토큰 만료 시 다른 메뉴에서 404]
// ------------------------------------------------------------
// 원래 문제:
//   - 인증 만료 후 메뉴 진입 → /ko/serving/product?session=expired → 404
//   - 홈(/ko?session=expired)에서는 정상
//
// 원인:
//   - 만료 시 "보던 페이지 유지"하려고 req.nextUrl.clone()으로
//     현재 보호 페이지 주소에 ?session=expired를 붙임
//   - 보호 페이지(/serving/...)는 토큰 없이는 렌더링 불가 → 404
//   - 홈은 public이라 토큰 없어도 렌더링되어 문제가 안 드러났음
//
// 수정:
//   - 만료 시 보호 페이지 유지 대신 안전한 홈(/{lang})으로 이동하며 신호 전달
//   - ?session=expired가 이미 붙은 요청은 통과 → 무한 루프 방지
//
// 참고(연동): SessionExpireGuard가 ?session=expired를 useSearchParams로 읽어
//   기존 인증 만료 모달을 띄움. layout에서 Guard를 <Suspense>로 격리.
// ============================================================

import { NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";
import type { NextRequest } from "next/server";

// (locale 처리 등 상단 로직은 기존 그대로)

export async function middleware(req: NextRequest) {
  // ... locale 리다이렉트 처리 (기존 그대로) ...

  // ── 토큰 확인 ──
  const token = await getToken({
    req,
    secret: process.env.NEXTAUTH_SECRET,
  });

  // (선택) 토큰 수명 진단 로그 — Edge Runtime이라 console 사용
  // 운영 배포 전 제거 권장
  if (token) {
    const now = Math.floor(Date.now() / 1000);
    const iat = typeof token.iat === "number" ? token.iat : 0;
    const exp = typeof token.exp === "number" ? token.exp : 0;
    console.log("[middleware] 토큰 수명", {
      수명초: exp - iat, // 1800이면 정상(30분), 2592000이면 jwt.maxAge 누락(30일)
      남은초: exp - now,
      만료됨: now > exp,
    });
  }

  if (!token) {
    // ───────────────────────────────────────────────────────
    // [수정] 만료 처리 — 보호 페이지 유지 → 홈 이동으로 변경
    // ───────────────────────────────────────────────────────

    // (1) 이미 만료 신호가 붙어 있으면 통과 (무한 루프 방지)
    if (req.nextUrl.searchParams.get("session") === "expired") {
      return NextResponse.next();
    }

    // (2) ❌ 기존: 보던 보호 페이지 주소 그대로 → 404 유발
    //     const url = req.nextUrl.clone();
    //     url.searchParams.set("session", "expired");
    //     return NextResponse.redirect(url);
    //
    //     또는 옛 코드: return redirectToKeycloak(req); // → /api/auth/keycloak 직행(안내 없음)

    // (2) ✅ 수정: 안전한 홈(public)으로 이동 + 만료 신호
    //     보호 페이지는 만료 사용자가 어차피 못 보므로 홈으로 빼낸 뒤 모달로 안내
    const lang = req.nextUrl.pathname.split("/")[1] || "ko"; // 현재 언어 유지
    const url = new URL(`/${lang}`, req.url);                 // /ko (홈)
    url.searchParams.set("session", "expired");               // ?session=expired
    return NextResponse.redirect(url);
  }

  // ── refreshToken 만료 (CASE 2) ──
  const refreshExp =
    typeof token.refreshTokenExpires === "number"
      ? token.refreshTokenExpires
      : null;
  const refreshExpired = refreshExp !== null && Date.now() > refreshExp;

  if (refreshExpired) {
    const url = new URL(
      `/${req.nextUrl.pathname.split("/")[1] || "ko"}`,
      req.url,
    );
    url.searchParams.set("session", "expired");
    return NextResponse.redirect(url);
  }

  // ── error 있음 (CASE 3) — 가로채지 않고 통과 → Guard가 session.error로 모달 표시 ──
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next|favicon.ico|.*\\..*).*)"], // api, _next, favicon 제외
};
