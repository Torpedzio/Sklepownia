/**
 * What `useApiQuery` loaded, kept between screens by path: a screen opened again shows its last data at once and
 * refreshes it in the background. Changing the session (signing in or out) empties it, so one account never sees
 * what another loaded, and answers to requests sent before that are dropped.
 */
import type { ApiError } from './api';

export type QueryEntry = {
  data?: unknown;
  /** The last request's error; the data stays from the last success. */
  error: ApiError | null;
};

const EMPTY: QueryEntry = { error: null };

const entries = new Map<string, QueryEntry>();
const listeners = new Map<string, Set<() => void>>();
// The newest request for each key; answers to older ones are dropped.
const requests = new Map<string, { id: number; promise: Promise<void>; done: boolean }>();
let lastId = 0;

/** The entry for `key`; the same object until it changes, as `useSyncExternalStore` needs. */
export function readQuery(key: string): QueryEntry {
  return entries.get(key) ?? EMPTY;
}

export function subscribeQuery(key: string, listener: () => void) {
  let keyListeners = listeners.get(key);
  if (!keyListeners) listeners.set(key, (keyListeners = new Set()));
  keyListeners.add(listener);
  return () => {
    keyListeners.delete(listener);
    if (!keyListeners.size) listeners.delete(key);
  };
}

function write(key: string, entry: QueryEntry) {
  entries.set(key, entry);
  listeners.get(key)?.forEach((listener) => listener());
}

/**
 * Loads `key` with `load` (which throws `ApiError`s). Joins a request for the same key that is still on its way,
 * unless `force`: after a change the answer must come from a request sent after it.
 */
export function fetchQuery(key: string, load: () => Promise<unknown>, { force = false } = {}): Promise<void> {
  const running = requests.get(key);
  if (running && !running.done && !force) return running.promise;
  const id = ++lastId;
  const isNewest = () => requests.get(key)?.id === id;
  const promise = load()
    .then(
      (data) => {
        if (isNewest()) write(key, { data, error: null });
      },
      (error: ApiError) => {
        if (isNewest()) write(key, { ...readQuery(key), error });
      },
    )
    .finally(() => {
      const request = requests.get(key);
      if (request?.id === id) request.done = true;
    });
  requests.set(key, { id, promise, done: false });
  return promise;
}

/** Forgets everything, e.g. when the session changes; screens still open start loading again. */
export function clearQueryCache() {
  const keys = [...entries.keys()];
  entries.clear();
  requests.clear();
  keys.forEach((key) => listeners.get(key)?.forEach((listener) => listener()));
}
