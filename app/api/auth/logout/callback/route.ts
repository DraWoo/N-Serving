import { NextResponse } from "next/server";
import * as process from "node:process";
import { AUTH_ROUTES } from "@/lib/constants";

/**
 * ==========================================================
 * Keycloak 로그아웃 후 콜백
 *
 * - keycloak SSO 종료 후 이 경로로 리다이렉트 됨
 * - NextAuth 세션 쿠키를 직접 삭제하고 홈으로 이동
 * -> NextAuth 기본 signout 확인 화면 skip
 * ==========================================================
 * [변경 내역]
 * - [20260710] - 세션 쿠키 청크 삭제 0~2 => 0~5 확대(for문으로 대체)
 */
export async function GET(): Promise<NextResponse<unknown>> {
  const response : NextResponse<unknown> = NextResponse.redirect(
    `${process.env.NEXTAUTH_URL}${AUTH_ROUTES.LOGIN}`
  );

  const cookieNames : string[] = [
    "next-auth.session-token",
    "next-auth.csrf-token",
    "next-auth.callback-url",
    "__Secure-next-auth.session-token",
    "__Secure-next-auth.csrf-token",
    "__Secure-next-auth.callback-url",
  ];

  for (let i : number = 0; i <= 5; i++) {
    cookieNames.push(`next-auth.session-token.${i}`);
    cookieNames.push(`__Secure-next-auth.session-token.${i}`);
  }

  /** 삭제 실행 */
  cookieNames.forEach((name : string) : void => {
    response.cookies.delete(name)
  });

  return response;
}
