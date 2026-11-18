import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';

import { api, ApiError } from '@/lib/api';
import { fetchQuery, readQuery, subscribeQuery } from '@/lib/query-cache';

type Options<T> = {
  /** Milliseconds until the next refetch for the given data, or false to stop polling. */
  refetchInterval?: (data: T | undefined) => number | false;
  /** Skip the request, e.g. until the user signs in. */
  enabled?: boolean;
};

/**
 * Data from `GET path`, loaded on every visit to the screen. A screen opened again shows the data it had at once
 * (shared by every screen with the same path) and swaps in the fresh copy when it arrives.
 */
export function useApiQuery<T>(path: string, { refetchInterval, enabled = true }: Options<T> = {}) {
  const subscribe = useCallback((onChange: () => void) => subscribeQuery(path, onChange), [path]);
  const getEntry = useCallback(() => readQuery(path), [path]);
  const entry = useSyncExternalStore(subscribe, getEntry, getEntry);
  const [isRefreshing, setIsRefreshing] = useState(false);
  // What the cache held when this screen started showing `path`: until it changes, it's a copy from earlier.
  const [opened, setOpened] = useState({ path, entry });
  if (opened.path !== path) setOpened({ path, entry });

  const fetchData = useCallback(
    async (force = false) => {
      if (!enabled) return;
      const load = () =>
        api<T>(path).catch((e: unknown) => {
          throw e instanceof ApiError ? e : new ApiError(0, null);
        });
      await fetchQuery(path, load, { force });
    },
    [path, enabled],
  );

  useFocusEffect(
    useCallback(() => {
      fetchData();
    }, [fetchData]),
  );

  const data = enabled ? (entry.data as T | undefined) : undefined;
  const error = enabled ? entry.error : null;
  const interval = refetchInterval?.(data) ?? false;
  // Every answer, an error too, sets the next poll.
  useEffect(() => {
    if (!interval) return;
    const timer = setTimeout(fetchData, interval);
    return () => clearTimeout(timer);
  }, [entry, interval, fetchData]);

  // After a change: a request sent before it may still be on its way, so this one doesn't join it.
  const refresh = useCallback(async () => {
    setIsRefreshing(true);
    await fetchData(true);
    setIsRefreshing(false);
  }, [fetchData]);

  return {
    data,
    error,
    isLoading: data === undefined && error === null,
    /** The data is a copy from an earlier visit; the fresh one is on its way. */
    isStale: data !== undefined && entry === opened.entry,
    isRefreshing,
    refresh,
  };
}
