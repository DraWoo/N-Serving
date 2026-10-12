/**
 * ==========================================================
 * [Proxy] 백엔드 API Proxy Route (Catch-All)
 * 
 * - 클라이언트 -> 백엔드 사이의 proxy
 * - NextAuth JWT accessToken 추출
 * - Authorization 헤더에 추가 (Content-Type은 설정 안함)
 * - 백엔드 응답을 그대로 클라이언트에 반환
 * - Content-Type 전달 규칙
 *   - headers에 Content-Type을 설정하지 않음
 *   - fetch API가 body 타입에 따라 자동 설정
 *     text body -> text/plain;charset=UTF-8 설정
 *     FormData body -> multipart/form-data;boundary=....
 *   - AS-IS 개별 route 파일들과 동일한 설정
 * ==========================================================
 * 변경 내역:
 * - [20260522] - timeout 설정: 5분으로 변경
 *                const TIMEOUT_SHORT_MS: number = 300_000;
 * - [20260526] - Mock 데이터 분기용 import 추가
 *                TODO API 연동 시 제거
 * - [20260602] - content-disposition: attachment 분기 추가 (zip 다운로드 분기)
 * ==========================================================
 */

import { NextRequest, NextResponse } from "next/server";
import * as process from "node:process";
import { getToken, JWT } from "next-auth/jwt";
import { nlog } from "@/lib/nlog/serverLog";
import { USE_MOCK } from "@/types/api/mock/mockConfig";
import { handleAccountMock } from "@/types/api/mock/mockHandler";

/** proxy 파라미터 key */
const SERVER_TYPE_PARAM = "_server";

/** TIMEOUT 설정 (밀리초) */
const TIMEOUT_SHORT_MS: number = 300_000;
const TIMEOUT_LONG_MS: number = 600_000;

/** 허용할 HTTP 메서드 목록 */
const ALLOWED_METHOD: ReadonlySet<string> = new Set([
  "GET",
  "POST",
  "PUT",
  "DELETE",
  "PATCH",
  "OPTIONS",
]);

// === Base Url 설정 ==========================================================
/**
 * [Base Url 함수]
 * @_server 파라미터 값에 따라 short/long 서버 url 결정
 * @param serverType - "_server" 쿼리 파라미터 값("long" 또는 null)
 * @returns 백엔드 서버 url
 */
function resolveBaseUrl(serverType: string | null): string | null {
  if (serverType === "long") {
    return process.env.PY_LONG_API_SERVER_URL ?? null;
  }
  return process.env.PY_API_SERVER_URL ?? null;
}

// === CORS header 생성 =======================================================
/** CORS header 생성 함수 */
function buildCorsHeaders(): Record<string, string> {
  const allowedOrigin: string = process.env.NEXTAUTH_URL ?? "http://localhost:3000";
  return {
    "Access-Control-Allow-Origin": allowedOrigin,
    "Access-Control-Allow-Method": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
  };
}

// === 공통 핸들러 함수 =======================================================
async function handler(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  try {
    // 메서드 허용 여부 확인
    if (!ALLOWED_METHOD.has(req.method)) {
      return NextResponse.json(
        { message: `Method ${req.method} not allowed.` },
        { status: 405 }
      );
    }

    // options preflight 처리
    if (req.method === "OPTIONS") {
      return new NextResponse(null, {
        status: 204,
        headers: buildCorsHeaders(),
      });
    }

    // Mock 분기 - API 구현 시 제거
    if (USE_MOCK) {
      const { path } = await params;
      const endpoint: string = path.join("/");

      const ACCOUNT_MOCK_ENDPOINTS: string[] = [
        "permission",
        "role",
        "group",
        "user",
        "user/unlock",
        "member",
      ];

      const isAccountEndPoint: boolean =
        ACCOUNT_MOCK_ENDPOINTS.some(
          (e: string): boolean => endpoint === e || endpoint.startsWith(e + "/")
        );

      if (isAccountEndPoint) {
        return handleAccountMock(req, endpoint);
      }
    }

    // [인증] - (getToken = 쿠키만 읽음)
    const token: JWT | null = await getToken({
      req,
      secret: process.env.NEXTAUTH_SECRET,
    });

    if (!token) {
      return NextResponse.json(
        { message: "Unauthorized - access token is not valid." },
        { status: 401 }
      );
    }

    const accessToken: string | null | undefined =
      token.accessToken as string | null | undefined;

    if (!accessToken) {
      return NextResponse.json(
        { message: "Unauthorized - 엑세스 토큰이 없습니다." },
        { status: 401 }
      );
    }

    // 백엔드 url 조립
    const { path } = await params;
    const endpoint: string = path.join("/");

    /** _server 파라미터로 short/long 서버 분기 */
    const serverType: string | null = req.nextUrl.searchParams.get(SERVER_TYPE_PARAM);
    const baseUrl: string | null = resolveBaseUrl(serverType);

    if (!baseUrl) {
      const envName: string = serverType === "long" ? "PY_LONG_API_SERVER_URL" : "PY_API_SERVER_URL";
      return NextResponse.json(
        { message: `${envName} 환경변수가 설정되지 않았습니다.` },
        { status: 500 }
      );
    }

    const targetUrl = new URL(`${baseUrl}/${endpoint}`);

    // 쿼리 파라미터 전달 -> 백엔드로 전달 (_server 제외)
    req.nextUrl.searchParams.forEach((value: string, key: string): void => {
      if (key !== SERVER_TYPE_PARAM) {
        targetUrl.searchParams.append(key, value);
      }
    });

    // === 요청 헤더 구성 =====================================================
    const isGet: boolean = req.method === "GET" || req.method === "HEAD";
    const clientContentType: string | null = req.headers.get("content-type");
    const isMultipart: boolean =
      clientContentType?.includes("multipart/form-data") ?? false;

    // === body 읽기 ==========================================================
    let requestBody: BodyInit | undefined;

    if (!isGet) {
      if (isMultipart) {
        requestBody = new Uint8Array(await req.arrayBuffer());
      } else {
        requestBody = await req.text();
      }
    }

    // header 구성
    const headers: Record<string, string> = {
      Authorization: `Bearer ${token.accessToken}`,
    };

    // if (!isGet && !isMultipart) {
    if (!isGet) {
      headers["Content-Type"] = isMultipart
        ? (clientContentType ?? "multipart/form-data")
        : (clientContentType ?? "application/json");
    }

    // === TIMEOUT 설정 =======================================================
    /**
     * AbortController 타임아웃 구현
     * - fetch API에는 timeout 옵션이 없음
     * - AbortController.abort() 요청 강제 취소
     * - 지정 시간 후 자동으로 abort -> catch에서 타임아웃 에러 처리
     * 
     * short 서버: 30초
     * long 서버: 5분
     */
    const timeoutMs: number = serverType === "long" ? TIMEOUT_LONG_MS : TIMEOUT_SHORT_MS;
    const abortController = new AbortController();
    const timeoutId: ReturnType<typeof setTimeout> = setTimeout(() => {
      abortController.abort();
    }, timeoutMs);

    // === 백엔드 요청 전달 ===================================================
    let backendResponse: Response;
    try {
      if (endpoint.includes("feature/group")) {
        console.log("[Proxy] feature/group 요청:", {
          method: req.method,
          targetUrl: targetUrl.toString(),
          headers,
        });
      }

      backendResponse = await fetch(targetUrl.toString(), {
        method: req.method,
        headers,
        body: requestBody,
        signal: abortController.signal,
      });
    } catch (fetchError: unknown) {
      if (fetchError instanceof DOMException && fetchError.name === "AbortError") {
        return NextResponse.json(
          { message: `요청 시간 초과 (${timeoutMs / 1000}초). 백엔드 응답이 없습니다.`, status: 504 },
          { status: 504 }
        );
      }
      throw fetchError;
    } finally {
      clearTimeout(timeoutId);
    }

    // === cache 무효화 (변경 요청 성공 시) ====================================
    if (backendResponse.ok && !isGet) {
      const { revalidateTag, revalidatePath } = await import("next/cache");

      // URL 쿼리에서 product-id 추출
      const productId: string | null =
        req.nextUrl.searchParams.get("product-id") ??
        req.nextUrl.searchParams.get("id");

      // 상점 목록 캐시 무효화
      if (endpoint.includes("serving/product")) {
        revalidateTag("product-list");
      }
      if (productId) {
        // product 관련 캐시 등록
        const productTags: string[] = [
          "detail",
          "history",
          "mart",
          "feature",
          "feature-group",
          "refit",
          "predict",
          "segment-list",
          "available",
          "task-list",
          // mock
          "permission",
          "role",
          "group",
          "user",
          "user/unlock",
          "member",
        ];
        productTags.forEach((tags: string): void => {
          revalidateTag(`product-${productId}-${tags}`);
        });
      }

      // segment 관련 요청이면 페이지 전체 무효화
      if (endpoint.includes("product/mart") && productId) {
        revalidateTag(`product-${productId}-mart`);
      }
      nlog.info({ category: "REVALIDATE", msg: `${req.method} ${endpoint} -> 캐시 무효화 대상`, productId: req.nextUrl.searchParams.get("product-id") ?? "없음" });
    }

    // === 백엔드 응답을 클라이언트에 반환 ====================================
    const responseRawContentType: string =
      backendResponse.headers.get("content-type") ?? "text/plain";

    const contentDisposition: string =
      backendResponse.headers.get("content-disposition") ?? "";

    // 첨부파일(다운로드) 추가 여부 판단 - attachment면 바이너리 그대로 전달
    const isAttachment: boolean = contentDisposition
      .toLowerCase()
      .includes("attachment");

    if (isAttachment) {
      // text가 아니라 arrayBuffer() - 바이트 원본 보존
      const responseBuffer: ArrayBuffer = await backendResponse.arrayBuffer();

      // 첨부 파일인데 Content-type이 text 계열이면 octet-stream으로 교정
      const safeContentType: string =
        !responseRawContentType || responseRawContentType.includes("text/*")
          ? "application/octet-stream"
          : responseRawContentType;

      return new NextResponse(responseBuffer, {
        status: backendResponse.status,
        headers: {
          "Content-Type": safeContentType,
          "Content-Disposition": contentDisposition,
          ...buildCorsHeaders(),
        },
      });
    }

    const responseBody: string = await backendResponse.text();
    const responseContentType: string =
      backendResponse.headers.get("content-type") ?? "text/plain";

    return new NextResponse(responseBody, {
      status: backendResponse.status,
      headers: {
        "Content-Type": responseContentType,
        ...buildCorsHeaders(),
      },
    });
  } catch (error: unknown) {
    const err: Error = error instanceof Error ? error : new Error(String(error));
    const cause = err.cause as { code?: string; message?: string } | undefined;

    const errCode: string | undefined = (err as { code?: string }).code;
    console.log('[Proxy] 에러 상세', {
      message: err.message,
      code: errCode ?? cause?.code ?? "UNKNOWN",
      causeMessage: cause?.message ?? null,
    });

    return NextResponse.json(
      { error: err.message },
      { status: 500 }
    );
  }

  return NextResponse.json(
    { error: "Unexpected: no response generate." },
    { status: 500 }
  );
}

// HTTP 메서드 export
export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH= handler;
export const DELETE = handler;
export const OPTIONS = handler;
