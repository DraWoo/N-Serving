import {nlog} from "@/Lib/nlog/clientLog";

/**
 * ===============================================
 * = [Client] 클라이언트 컴포넌트 전용 fetch 래퍼
 * = "use Client" 컴포넌트에서 백엔드 호출
 * =   api/proxy/[...path]를 경유 인증 처리
 * = - 브라우저 -> Next.js -> Proxy -> 백엔드 호출
 * ===============================================
 * 변경내역:
 * - [20260624] - 기존 브라우저 자동 설정 request headers => application/json 명시적 설정 추가
 * ===============================================
 */
// -- HTTP 메서드 타입 --
type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

// -- clientFetch 옵션 타입 --
interface ClientFetchOptions {
  method?: HttpMethod; /** HTTP 메서드 (기본값: GET) */
  params?: [string, string | number | null][]; /** 쿼리 파라미터 배열 */
  body?: unknown; /** POST/PUT 요청 시 전송할 body 데이터 */
  useLongServer?: boolean; /** PY_LONG_API_SERVER_URL 분기 */
}

// -- 클라이언트 사이드 fetch --
/**
 * =======================
 * * JSON 요청 Fetch
 * =======================
 */
export async function clientFetch<T = unknown>(
  endpoint: string,
  options: ClientFetchOptions = {}
): Promise<T | null> {
  const { method = "GET", body, useLongServer = false } = options;
  const params: [string, string | number | null][] = options.params ?? [];

  // -- URL 조립 --
  const searchParams = new URLSearchParams();
  params.forEach(([key, value]: [string, string | number | null]) : void => {
    if (value !== null && value !== undefined) {
      searchParams.append(key, String(value));
    }
  });

  /** long서버 사용시 _server=long 파라미터 추가 */
  if (useLongServer) {
    searchParams.append("_server", "long");
  }

  const queryString: string = searchParams.toString();
  const url: string =
    queryString.length > 0
      ? `/api/proxy/${endpoint}?${queryString}`
      : `/api/proxy/${endpoint}`;

  // =[fetch옵션]=
  const fetchOptions: RequestInit = { method };

  if (method !== "GET" && body !== undefined) {
    fetchOptions.body = typeof body === "string" ? body : JSON.stringify(body);
  }

  //요청 헤더
  fetchOptions.headers = { "Content-Type": "application/json" };

  try {
    const res: Response = await fetch(url, fetchOptions);
    // HTTP 에러 처리
    if (!res.ok) {
      /**
       * 401 Unauthorized -> 세션 만료
       * 403 Forbidden    -> 권한 없음
       * 500 Internal     -> 백엔드 에러
       */
      const errorBody: string = await res.text().catch(() : string => "*응답 본문 읽기 실패*");
      nlog.log({ msg: `[clientFetch] HTTP ${res.status} - ${endpoint}`,
        errorBody,
        method,
        url,
        bodyLength: typeof fetchOptions.body === "string" ? fetchOptions.body.length : "N/A",
      });
      return null;
    }

    // =[응답 파싱]=
    const text: string = await res.text();
    // body가 비어있으면 성공을 간주하고 빈 객체 전환
    if (text.length === 0) return {} as T;

    // json 파싱 시도
    try {
      return JSON.parse(text) as T;
    } catch {
      // json이 아닌 일반 텍스트
      return text as unknown as T;
    }
  } catch (error: unknown) {
    // 네트워크 에러, DNS 실패, 타임아웃 등
    const message: string =
      error instanceof Error ? error.message : String(error);
    console.log({ message: `[clientFetch] Network ERROR - ${endpoint}:`, message });
    return null;
  }
}

/**
 * =======================
 * * 파일 업로드 전용 fetch
 * =======================
 * Content-Type을 설정하지 않음 -> 브라우저가 boundary 자동 설정
 */
export async function clientUpload<T = unknown>(
  endpoint: string,
  formData: FormData,
  options: { method?: "POST" | "PUT"; useLongServer?: boolean } = {}
): Promise<T | null> {
  const { method = "POST", useLongServer = false } = options;

  const searchParams = new URLSearchParams();
  if (useLongServer) {
    searchParams.append("_server", "long");
  }

  const queryString: string = searchParams.toString();
  const url: string =
    queryString.length > 0
      ? `/api/proxy/${endpoint}?${queryString}`
      : `/api/proxy/${endpoint}`;

  try {
    const res: Response = await fetch(url, {
      method,
      body: formData,
    });

    if (!res.ok) {
      const errorBody: string = await res.text().catch(() : string => "*응답 본문 읽기 실패*");
      console.log({ message: `[clientFetch] HTTP ${res.status} - ${endpoint}`, errorBody });
      return null;
    }

    const text: string = await res.text();
    if (text.length === 0) return {} as T;

    try {
      return JSON.parse(text) as T;
    } catch {
      return text as unknown as T;
    }
  } catch (error: unknown) {
    console.log({ message: `[clientUpload] Network ERROR - ${endpoint}:`, error });
    return null;
  }
}

/**
 * ===============================================
 * * Response 객체가 필요한 경우
 * ===============================================
 * - tryDownloadFromResponse 등
 * - clientFetch처럼 URL 조립만 하고 Response 그대로 반환
 */
export async function clientDownload(
  endpoint: string,
  options: {
    method?: "GET" | "POST";
    params?: [string, string | number | null][];
    body?: unknown;
    fileName?: string;
    useLongServer?: boolean;
  } = {}
): Promise<boolean> {
  const { method = "GET", body, fileName, useLongServer = false } = options;
  const searchParams = new URLSearchParams();
  const params: [string, string | number | null][] = options.params ?? [];

  params.forEach(([key, value] : [string, string | number | null] ) : void => {
    if (value !== null && value !== undefined) {
      searchParams.append(key, String(value));
    }
  });

  if (useLongServer) {
    searchParams.append("_server", "long");
  }

  const queryString: string = searchParams.toString();
  const url: string =
    queryString.length > 0
      ? `/api/proxy/${endpoint}?${queryString}`
      : `/api/proxy/${endpoint}`;

  const fetchOptions: RequestInit = { method };
  if (method !== "GET" && body !== undefined) {
    fetchOptions.body = typeof body === "string" ? body : JSON.stringify(body);
  }
  //요청 헤더
  fetchOptions.headers = { "Content-Type": "application/json" };

  try {
    const res: Response = await fetch(url, fetchOptions);
    if (!res.ok) {
      nlog.log({ msg: `[clientDownload] HTTP ${res.status} - ${endpoint}` });
      return false;
    }

    const blob: Blob = await res.blob();
    const blobUrl: string = window.URL.createObjectURL(blob);
    const a: HTMLAnchorElement = document.createElement("a");

    a.href = blobUrl;
    a.download = fileName ?? "download";

    document.body.appendChild(a);
    a.click();
    a.remove();

    window.URL.revokeObjectURL(blobUrl);
    return true;
  } catch (error: unknown) {
    const message: string = error instanceof Error ? error.message : String(error);
    nlog.error({ categoryOrMsg: "UI", msgorMeta: `[clientDownload] ERROR - ${endpoint}: ${message}` });
    return false;
  }
}

/**
 * ===============================================
 * * Response 객체가 필요한 경우
 * ===============================================
 * - tryDownloadFromResponse 등
 * - clientFetch처럼 URL 조립만 하고 Response 그대로 반환
 */
export async function clientRawFetch(
  endpoint: string,
  options: {
    method?: HttpMethod;
    body?: unknown;
    useLongServer?: boolean;
  } = {}
): Promise<Response> {
  const { method = "GET", body, useLongServer = false } = options;

  const searchParams = new URLSearchParams();
  if (useLongServer) {
    searchParams.append("_server", "long");
  }

  const queryString: string = searchParams.toString();
  const url: string =
    queryString.length > 0
      ? `/api/proxy/${endpoint}?${queryString}`
      : `/api/proxy/${endpoint}`;

  const fetchOptions: RequestInit = { method };
  if (method !== "GET" && body !== undefined) {
    fetchOptions.body = typeof body === "string" ? body : JSON.stringify(body);
  }
  //요청 헤더
  fetchOptions.headers = { "Content-Type": "application/json" };

  return fetch(url, fetchOptions);
}
