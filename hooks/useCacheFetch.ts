/**
 * [Hook] GET 요청 + Zustand 캐시 연동 훅
 * - Client Component에서 GET 요청을 보내고 결과를 캐시
 * - 캐시가 유효하다면 네트워크 요청 없이 즉시 반환
 * - 캐시가 만료(stale)되면 자동으로 새로 fetch
 * - inFlight 체크로 같은 요청 중복 호출 방지
 */
"use client";

// -- 훅 옵션 타입 --
import { buildCacheKey, useApiCacheStore } from "@/stores/useApiCacheStore";
import { useCallback, useEffect, useMemo, useRef } from "react";
import { clientFetch } from "@/fetcher/client";
import { nlog } from "@/lib/nlog/clientLog";

interface UseCacheFetchOptions {
  /** 쿼리 파라미터 배열 */
  params?: [string, string][];
  /** 캐시 유효 시간 */
  ttl?: number;
  enabled?: boolean;
  /** SSR 또는 상위 컴포넌트에서 받은 초기 데이터 */
  initialData?: unknown;
}

// -- 훅 반환 타입 --
interface UseCacheFetchResult<T> {
  /** 캐시 또는 fetch로 받아온 데이터 (없으면 null) */
  data: T | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  invalidate: () => void;
}

// -- 훅 구현 --
/**
 * GET 요청 + Zustand 캐시를 연동하는 커스텀 훅
 * @typeParam T - 응답 데이터의 타입
 * @param endpoint - API 엔드포인트
 * @param options - 파라미터, TTL, enabled 설정
 * @returns { data, isLoading, error, refetch, invalidate }
 */
export function useCacheFetch<T = unknown>(
  endpoint: string,
  options: UseCacheFetchOptions = {}
): UseCacheFetchResult<T> {
  const { ttl = 600_000, enabled = true, initialData } = options;

  const normalizedParams: [string, string][] = useMemo(() => options.params ?? [], [
    options.params,
  ]);

  // 캐시 key 생성
  const cacheKey: string = useMemo(() =>
    buildCacheKey(endpoint, normalizedParams),
    [endpoint, normalizedParams]
  );

  /** Zustand store에서 필요한 상태와 액션 구독 */
  const entry = useApiCacheStore((state) => state.cache[cacheKey]);
  const inFlight: boolean = useApiCacheStore((state) => state.inFlight[cacheKey] ?? false);

  const setLoading = useApiCacheStore((state) => state.setLoading);
  const setData = useApiCacheStore((state) => state.setData);
  const setError = useApiCacheStore((state) => state.setError);
  const isStale = useApiCacheStore((state) => state.isStale);
  const invalidateKey = useApiCacheStore((state) => state.invalidate);

  /** 컴포넌트 unMounted 추적 */
  const mountedRef = useRef<boolean>(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  /**
   * 서버에서 가져온 initialData가 있는데
   * Zustand 캐시에는 아직 데이터가 없으면
   * 초기값으로 시드 세팅
   */
  const seededRef = useRef<boolean>(false);
  if (initialData !== undefined && !seededRef.current && !entry) {
    setData(cacheKey, initialData);
    seededRef.current = true;
    nlog.cache.seed(cacheKey);
  }

  // -- fetch 로직 --
  const fetchData = useCallback(async (): Promise<void> => {
    /**
     * 중복 요청 방지
     * inFlight가 true면 이미 같은 키에 대한 요청 진행중
     */
    if (inFlight) return;
    setLoading(cacheKey);

    const timer = nlog.startTimer();
    nlog.fetch.start(endpoint);

    try {
      const result: T | null = await clientFetch<T>(endpoint, { params: normalizedParams });
      // 컴포넌트가 unMounted 상태인지 확인
      if (!mountedRef.current) return;
      if (result !== null) {
        setData<T>(cacheKey, result);
        nlog.fetch.success(endpoint, timer);
      } else {
        setError(cacheKey, "데이터를 불러오지 못했습니다.");
        nlog.fetch.fail(endpoint, timer, "null 반환");
      }
    } catch (error: unknown) {
      if (!mountedRef.current) return;

      const message: string = error instanceof Error ? error.message : String(error);
      setError(cacheKey, message);
      nlog.fetch.fail(endpoint, timer, message);
    }
  }, [cacheKey, endpoint, inFlight, normalizedParams, setData, setError, setLoading]);

  // -- mount시 자동 fetch --
  useEffect(() => {
    /**
     * enabled가 false면 자동 fetch 안함
     */
    if (!enabled) return;
    /**
     * isStale 체크:
     * - 캐시 없음 -> stale -> fetch 실행
     * - 캐시가 있지만 TTL 만료 -> stale -> fetch 실행
     * - 캐시가 유효 -> stale 아님 -> fetch 안 함 (즉시 캐시 데이터 사용)
     * - inFlight가 true -> stale 아님 -> 중복 요청 방지
     */
    if (isStale(cacheKey, ttl)) {
      nlog.cache.stale(cacheKey, ttl);
      fetchData();
    }
  }, [cacheKey, enabled, fetchData, isStale, ttl]);

  return {
    /**
     * 데이터 우선순위 :
     * 1) Zustand 캐시 데이터 (fetch 성공 시)
     * 2) initialData (캐시가 아직 없을 때 - SSR 데이터로 즉시 표시)
     * 3) null (둘 다 없을때)
     */
    data: (entry?.data as T) ?? (initialData as T | undefined) ?? null,
    isLoading: entry?.isLoading ?? false,
    error: entry?.error ?? null,

    /**
     * 수동 재호출 함수
     * 사용예: <button onClick={refetch}>새로고침</button>
     * 캐시를 무시하고 강제로 새데이터를 가져옴
     * 기존 데이터는 유지한 채 로딩 표시
     */
    refetch: fetchData,

    /** 이 key의 캐시만 삭제 -> 다른 컴포넌트에서 이 데이터를 다시 읽으면 자동으로 fetch */
    invalidate: (): void => {
      invalidateKey(cacheKey);
    },
  };
}
