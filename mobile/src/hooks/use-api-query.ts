import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';

import { api, ApiError } from '@/lib/api';

type Options<T> = {
  /** Milliseconds until the next refetch for the given data, or false to stop polling. */
  refetchInterval?: (data: T | undefined) => number | false;
  /** Skip the request, e.g. until the user signs in. */
  enabled?: boolean;
};

export function useApiQuery<T>(path: string, { refetchInterval, enabled = true }: Options<T> = {}) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<ApiError | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchData = useCallback(async () => {
    if (!enabled) return;
    try {
      setData(await api<T>(path));
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, null));
    }
  }, [path, enabled]);

  useFocusEffect(
    useCallback(() => {
      fetchData();
    }, [fetchData]),
  );

  const interval = refetchInterval?.(data) ?? false;
  useEffect(() => {
    if (!interval) return;
    const timer = setTimeout(fetchData, interval);
    return () => clearTimeout(timer);
  }, [data, interval, fetchData]);

  const refresh = useCallback(async () => {
    setIsRefreshing(true);
    await fetchData();
    setIsRefreshing(false);
  }, [fetchData]);

  return { data, error, isLoading: data === undefined && error === null, isRefreshing, refresh };
}
