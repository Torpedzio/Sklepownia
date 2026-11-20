/**
 * `useApiQuery` data kept between screens by path: a reopened screen shows its last data and refreshes it.
 * A session change empties it (one account never sees another's data) and drops answers to earlier requests.
 */
import type { ApiError } from './api';

export type QueryEntry = {
  data?: unknown;
  /** The last request's error; data stays from the last success. */
  error: ApiError | null;
};

const EMPTY: QueryEntry = { error: null };

const entries = new Map<string, QueryEntry>();
const listeners = new Map<string, Set<() => void>>();
// The newest request for each key; answers to older ones are dropped.
const requests = new Map<string, { id: number; promise: Promise<void>; done: boolean }>();
let lastId = 0;

/** Same object until it changes, as `useSyncExternalStore` needs. */
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

/** `load` throws `ApiError`s. Joins a pending request unless `force` (after a change the answer must be newer). */
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

/** E.g. the answer to a change, which already holds the fresh data; requests still on their way are dropped. */
export function writeQuery(key: string, data: unknown) {
  requests.delete(key);
  write(key, { data, error: null });
}

/** E.g. on a session change; screens still open load again. */
export function clearQueryCache() {
  const keys = [...entries.keys()];
  entries.clear();
  requests.clear();
  keys.forEach((key) => listeners.get(key)?.forEach((listener) => listener()));
}
