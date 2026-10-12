/**
 * [Hook] POST/PUT/DELETE 요청 + 캐시 무효화 훅
 * - client component에서 데이터 변경 요청(POST 등) 전송
 * - 성공 시 관련 GET 캐시를 자동으로 무효화
 * - 무효화된 캐시를 사용하는 useCachedFetch가 다음 렌더링에서 자동으로 새 데이터를 fetch
 */
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { buildCacheKey, useApiCacheStore } from "@/stores/useApiCacheStore";
import { clientFetch } from "@/fetcher/client";

type MutationMethod = "POST" | "PUT" | "PATCH" | "DELETE";
interface InvalidateTarget {
  /** 무효화할 GET 엔드포인트 */
  endpoint: string;
  /** 해당 엔드포인트의 파라미터 (있으면 정확한 key 매칭, 없으면 전체) */
  params?: [string, string][];
}

// -- 훅 옵션 타입 --
interface UseApiMutationOptions {
  /** Http 메서드 (기본값 : POST) */
  method?: MutationMethod;

  invalidateEndpoints?: InvalidateTarget[]; // key 매칭
  invalidatePrefixes?: string[];           // 패턴 매칭
  onSuccess?: (data: unknown) => void;     // 성공시 호출되는 콜백
  onError?: (error: string) => void;       // 실패시 호출되는 콜백
}

// -- 훅 반환 타입 --
interface UseApiMutationResult<T> {
  data: T | null;
  isLoading: boolean;
  error: string | null;
  mutate: (body: unknown) => Promise<T | null>;
  resetError: () => void;
}

// -- 훅 구현 --
export function useApiMutation<T = unknown>(
  endpoint: string,
  options: UseApiMutationOptions = {}
): UseApiMutationResult<T> {
  const {
    method = "POST",
    invalidateEndpoints = [],
    invalidatePrefixes = [],
    onSuccess,
    onError,
  } = options;
  const normalizedInvalidateEndpoints = useMemo(() => invalidateEndpoints, [invalidateEndpoints]);
  const normalizedInvalidatePrefixes = useMemo(() => invalidatePrefixes, [invalidatePrefixes]);

  const [data, setData] = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Zustand store에서 캐시 무효화 액션만 가져옴
  const invalidateKey = useApiCacheStore((store) => store.invalidate);
  const invalidateByPrefix = useApiCacheStore((store) => store.invalidateByPrefix);

  // -- 중복 요청 방지 --
  const isSubmittingRef = useRef<boolean>(false);

  // -- 컴포넌트 unmounted 추적 --
  const mountedRef = useRef<boolean>(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // -- mutation 실행 함수 --
  const mutate = useCallback(
    async (body: unknown): Promise<T | null> => {
      /**
       * 버튼 더블클릭, 네트워크 지연 시 재클릭 막음
       */
      if (isSubmittingRef.current) {
        console.log(`[useApiMutation] 중복 요청 차단 - ${endpoint}`);
        return null;
      }

      isSubmittingRef.current = true;
      if (mountedRef.current) {
        setIsLoading(true);
        setError(null);
      }

      try {
        const result: T | null = await clientFetch<T>(endpoint, {
          method,
          body,
        });

        if (result !== null) {
          if (mountedRef.current) {
            setData(result);
          }
          // 캐시 무효화
          normalizedInvalidateEndpoints.forEach((target: InvalidateTarget) => {
            const targetParams: [string, string][] = target.params ?? [];
            const targetKey: string = buildCacheKey(target.endpoint, targetParams);
            invalidateKey(targetKey);
          });
          normalizedInvalidatePrefixes.forEach((prefix: string) => {
            invalidateByPrefix(prefix);
          });

          if (onSuccess) {
            onSuccess(result);
          }
          return result;
        }
        const errorMessage = "요청이 실패했습니다.";
        if (mountedRef.current) {
          setError(errorMessage);
        }

        if (onError) {
          onError(errorMessage);
        }
        return null;
      } catch (error: unknown) {
        const message: string =
          error instanceof Error ? error.message : String(error);
        setError(message);

        if (onError) {
          onError(message);
        }

        return null;
      } finally {
        if (mountedRef.current) {
          setIsLoading(false);
        }
      }
    },
    [endpoint, invalidateByPrefix, invalidateKey, method, normalizedInvalidateEndpoints, normalizedInvalidatePrefixes, onError, onSuccess]
  );

  // -- 에러 초기화 함수 --
  const resetError = useCallback(() => {
    if (mountedRef.current) {
      setError(null);
    }
  }, []);

  return {
    data,
    isLoading,
    error,
    mutate,
    resetError,
  };
}
