/**
 * Answers `api()` calls in screen tests by "METHOD /path/": a value, a function of the body, or a list used in turn
 * (the last repeats). Use with `jest.mock('@/lib/api', () => ({ ...jest.requireActual('@/lib/api'), api: jest.fn() }))`.
 */
import { api } from '@/lib/api';

type Handler = unknown | ((body: unknown) => unknown);
export type Routes = Record<string, Handler | Handler[]>;

export function mockApi(routes: Routes) {
  const used: Record<string, number> = {};
  const calls: { key: string; body: unknown }[] = [];
  (api as jest.Mock).mockImplementation(async (path: string, options: { method?: string; body?: unknown } = {}) => {
    const key = `${options.method ?? 'GET'} ${path}`;
    calls.push({ key, body: options.body });
    if (!(key in routes)) throw new Error(`Unexpected request: ${key}`);
    const route = routes[key];
    let handler = route;
    if (Array.isArray(route)) {
      handler = route[Math.min(used[key] ?? 0, route.length - 1)];
      used[key] = (used[key] ?? 0) + 1;
    }
    const result = typeof handler === 'function' ? (handler as (body: unknown) => unknown)(options.body) : handler;
    if (result instanceof Error) throw result;
    return result;
  });
  return {
    calls,
    /** Bodies sent to "METHOD /path/". */
    sent: (key: string) => calls.filter((call) => call.key === key).map((call) => call.body),
  };
}
