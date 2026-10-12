/**
 * ===============================================
 * * {Server} - 서버 컴포넌트 전용 fetch 래퍼
 * ===============================================
 * - 기존 get.ts_[OLD] + post.ts를 하나로 통합
 * - getServerSession()으로 토큰을 가져와 Authorization 추가
 * - Next.js fetch 캐시(revalidate, tags)
 * - PY_API_SERVER_URL / PY_LONG_API_SERVER_URL 분기
 * ===============================================
 * 변경 내역 -
 * - 20260720: 캐시 처리 분기 수정: revalidate: 0일때 cache: no-store로 처리
 * =
 */

import {getServerSession, Session} from "next-auth";
import {authOptions} from "@/lib/authOptions";

// == HTTP 메서드 타입 ==
type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

// == Next.js fetch 캐시 옵션 ==
interface NextCacheOpt {
  /**
   * 캐시 재검증 주기(초 단위)
   * ex) 60 -> 60초마다 백엔드에 새로 요청
   * 미지정시 -> 매번 새로 요청 (캐시 안함)
   */
  revalidate?: number;
  /**
   * 캐시 tag
   * revalidateTag()로 특정 태그의 캐시를 수동 무효화할 때 사용
   * ex) ["product-123-feature"] -> POST 후 해당 tag 무효화
   * 미지정시 -> 매번 새로 요청 (캐시 안함)
   */
  tags?: string[];
}

// == serverFetch 옵션 타입 ==
interface ServerFetchOptions {
  /** HTTP 메서드 (기본값: GET) */
  method?: HttpMethod;
  /** 쿼리 파라미터 배열 */
  params?: [string, string | number | null][];
  /** POST/PUT 요청 시 전송할 body 데이터 */
  body?: unknown;
  /** Next.js fetch 캐시 옵션 */
  cacheOpt?: NextCacheOpt;
  /**
   * true -> PY_LONG_API_SERVER_URL 사용 (기존 getLong 대체)
   * false/미지정 -> PY_API_SERVER_URL 사용 (기본)
   */
  useLongServer?: boolean;
  /** 요청 타임아웃 설정 (밀리초) */
  timeoutMs?: number;
}

// == base URL 함수 ==
/**
 * ===============================================
 * @param useLong - true인 경우 PY_LONG_API_SERVER_URL
 * @returns API 서버 기본 URL
 * @throws env가 없으면 에러
 * ===============================================
 */
function getBaseUrl(useLong: boolean): string {
  const url: string | undefined = useLong
    ? process.env.PY_LONG_API_SERVER_URL
    : process.env.PY_API_SERVER_URL;
  if (!url) {
    throw new Error(`[serverFetch] env환경변수 ${useLong ? "PY_LONG_API_SERVER_URL" : "PY_API_SERVER_URL"}이 설정되지 않았습니다.`);
  }
  return url;
}

// == 서버 사이드 fetch ==
/**
 * ===============================================
 * * Server Component에서 백엔드를 호출하는 통합 함수
 * ===============================================
 * * as-is => get(), getLong(), post() 3개 함수 대체
 * * @typeParam T - 응답 데이터의 타입 (제네릭)
 * * @param endpoint - API 엔드포인트 (ex: "serving/product/feature")
 * * @param options - 요청 옵션 (method, params, body, cacheOpt 등)
 * * @return 파싱된 응답 데이터 또는 실패 시 null
 */
export async function serverFetch<T = unknown>(
  endpoint: string,
  options: ServerFetchOptions = {}
): Promise<T | null> {
  const {
    method = "GET",
    body,
    cacheOpt,
    useLongServer = false,
    timeoutMs = useLongServer ? 60_000 : 15_000,
  } = options;

  // == URL 조립 ==
  const params: [string, string | number | null][] = options.params ?? [];
  const targetUrl = new URL(`${getBaseUrl(useLongServer)}/${endpoint}`);
  params.forEach(([key, value]: [string, string | number | null]): void => {
    if (value !== null && value !== undefined) {
      targetUrl.searchParams.append(key, String(value));
    }
  });

  // == NextAuth session accessToken 획득 ==
  const session: Session | null = await getServerSession(authOptions);
  if (!session) {
    return null;
  }

  const accessToken: string | undefined = (session as Session & { accessToken?: string }).accessToken;
  if (!accessToken) {
    console.log({ message: "[serverFetch] accessToken이 session에 없습니다." });
    return null;
  }

  /** API 요청 시 응답이 무한정 대기하지 않도록 요청 시간 제한 */
  const controller = new AbortController();
  const timeoutId: Timeout = setTimeout(() => controller.abort(), timeoutMs);

  // == fetch 옵션 ==
  const fetchOptions: RequestInit & { next?: NextCacheOpt; cache?: RequestCache; } = {
    method,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    signal: controller.signal,
  };

  /** body가 이미 문자열이면 그대로, 객체면 JSON.stringify 처리 */
  if (method !== "GET" && body !== undefined) {
    fetchOptions.body = typeof body === "string" ? body : JSON.stringify(body);
  }

  /**
   * ===============================================
   * * Next.js fetch 캐시 설정
   * ===============================================
   * - cacheOpt가 있으면: Next.js가 응답을 서버 캐시에 저장
   * {revalidate: 60} -> 60초 동안 캐시 사용, 이후 백그라운드에서 갱신
   * {tags: ["product-123]} -> revalidateTag("product-123") 수동 무효화
   * 
   * cacheOpt가 없으면 매 요청마다 백엔드에서 새로 요청
   * 기본값 no-store
   */
  if (cacheOpt) {
    if (cacheOpt.revalidate === 0) {
      // + revalidate: 0 -> 완전 비활성화
      fetchOptions.cache = "no-cache";
    } else {
      fetchOptions.next = cacheOpt;
    }
  } else {
    fetchOptions.cache = "no-store";
  }

  // == fetch 호출 ==
  try {
    const res: Response = await fetch(targetUrl.toString(), fetchOptions);
    clearTimeout(timeoutId);

    // HTTP 상태코드가 200이 아닌 경우
    if (!res.ok) {
      const errorBody: string = await res.text().catch((): string => "응답 본문 읽기 실패");
      if (res.status === 401 || res.status === 403) {
        throw new Error(`[serverFetch] 인증 오류 ${res.status} ${res.statusText} - ${errorBody}`);
      }
      console.log({ message: `[serverFetch] HTTP ${res.status} ${res.statusText} - ${endpoint}`, errorBody });
      return null;
    }

    /** 빈 응답 처리 */
    const text: string = await res.text();
    // body가 비어있으면 성공을 간주하고 빈 객체 전환
    if (text.length === 0) {
      return {} as T;
    }

    // json 파싱 시도
    try {
      return JSON.parse(text) as T;
    } catch {
      // json이 아닌 일반 텍스트
      return text as unknown as T;
    }
  } catch (error: unknown) {
    // 네트워크 에러, DNS 실패, 타임아웃 등
    clearTimeout(timeoutId);
    const message: string =
      error instanceof Error ? error.message : String(error);

    // 네트워크 다운과 타임아웃 구분
    if (error instanceof Error && error.name === "AbortError") {
      console.log({ message: `[serverFetch] 타임아웃 - ${endpoint}: ${timeoutMs}ms 초과` });
      return null;
    }

    console.log({ message: `[serverFetch] 네트워크 에러 - ${endpoint}:`, message });
    return null;
  }
}
