import Constants from 'expo-constants';

import { clearQueryCache } from './query-cache';
import { readTokens, writeTokens } from './token-storage';
import type { Tokens } from './types';

function resolveBaseUrl() {
  if (process.env.EXPO_PUBLIC_API_URL) return process.env.EXPO_PUBLIC_API_URL;
  // In dev the backend runs on the same machine as Metro, so reuse its host.
  const host = Constants.expoConfig?.hostUri?.split(':')[0] ?? 'localhost';
  return `http://${host}:8000`;
}

export const API_URL = `${resolveBaseUrl()}/api`;

export class ApiError extends Error {
  constructor(
    public status: number,
    public data: Record<string, unknown> | null,
  ) {
    super(ApiError.describe(status, data));
  }

  /** Field-level validation messages, e.g. `{ slug: 'Ten adres jest już zajęty.' }`. */
  get fieldErrors(): Record<string, string> {
    const result: Record<string, string> = {};
    for (const [key, value] of Object.entries(this.data ?? {})) {
      if (key !== 'detail' && key !== 'non_field_errors' && Array.isArray(value)) {
        result[key] = String(value[0]);
      }
    }
    return result;
  }

  private static describe(status: number, data: Record<string, unknown> | null) {
    if (typeof data?.detail === 'string') return data.detail;
    if (Array.isArray(data?.non_field_errors)) return String(data.non_field_errors[0]);
    if (status === 0) return 'Brak połączenia z serwerem.';
    if (status >= 500) return 'Błąd serwera. Spróbuj ponownie.';
    return 'Sprawdź poprawność formularza.';
  }
}

let tokens: Tokens | null = null;
let refreshing: Promise<boolean> | null = null;
let onSessionExpired: () => void = () => {};

export async function loadTokens() {
  tokens = await readTokens();
  return tokens;
}

export async function setTokens(next: Tokens | null) {
  // Signing in or out: what the screens loaded belongs to the previous session. New tokens for the same session
  // (after a password change) keep it.
  if (!next || !tokens) clearQueryCache();
  tokens = next;
  await writeTokens(next);
}

export function setOnSessionExpired(callback: () => void) {
  onSessionExpired = callback;
}

type RequestOptions = { method?: string; body?: unknown; auth?: boolean };

export async function api<T>(path: string, { method = 'GET', body, auth = true }: RequestOptions = {}): Promise<T> {
  let response = await send(path, method, body, auth);
  if (response.status === 401 && auth && tokens) {
    if (await refreshTokens()) {
      response = await send(path, method, body, auth);
    } else {
      await setTokens(null);
      onSessionExpired();
    }
  }
  const data = response.status === 204 || response.status === 205 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, data);
  return data as T;
}

async function send(path: string, method: string, body: unknown, auth: boolean) {
  const headers: Record<string, string> = { Accept: 'application/json' };
  // A FormData upload sets its own multipart Content-Type with the boundary.
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData;
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json';
  if (auth && tokens) headers.Authorization = `Bearer ${tokens.access}`;
  try {
    return await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, null);
  }
}

// Concurrent 401s share one refresh, since the backend rotates refresh tokens.
function refreshTokens() {
  refreshing ??= (async () => {
    try {
      const response = await fetch(`${API_URL}/auth/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh: tokens?.refresh }),
      });
      if (!response.ok) return false;
      const data = await response.json();
      await setTokens({ access: data.access, refresh: data.refresh ?? tokens!.refresh });
      return true;
    } catch {
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}
