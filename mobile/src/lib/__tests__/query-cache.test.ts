import { ApiError, setTokens } from '@/lib/api';
import { fetchQuery, readQuery, subscribeQuery, writeQuery } from '@/lib/query-cache';

jest.mock('@/lib/token-storage', () => ({
  readTokens: jest.fn(async () => null),
  writeTokens: jest.fn(async () => {}),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => (resolve = done));
  return { promise, resolve };
}

test('screens asking for the same path at once share one request', async () => {
  const load = jest.fn(async () => ['Palarnia']);

  await Promise.all([fetchQuery('/shops/', load), fetchQuery('/shops/', load)]);

  expect(load).toHaveBeenCalledTimes(1);
  expect(readQuery('/shops/').data).toEqual(['Palarnia']);
});

test('after a change the answer comes from a request sent after it, not one already on its way', async () => {
  const before = deferred<string>();
  const earlier = fetchQuery('/billing/', () => before.promise);

  await fetchQuery('/billing/', async () => 'po zmianie', { force: true });
  before.resolve('przed zmianą');
  await earlier;

  expect(readQuery('/billing/').data).toBe('po zmianie');
});

test('data written after a change replace the answer to a request already on its way', async () => {
  const before = deferred<string>();
  const earlier = fetchQuery('/orders/41/', () => before.promise);
  const listener = jest.fn();
  subscribeQuery('/orders/41/', listener);

  writeQuery('/orders/41/', 'po zmianie');
  before.resolve('przed zmianą');
  await earlier;

  expect(readQuery('/orders/41/')).toEqual({ data: 'po zmianie', error: null });
  expect(listener).toHaveBeenCalledTimes(1);
});

test('a failed refresh keeps the data and reports the error', async () => {
  await fetchQuery('/shops/', async () => ['Palarnia']);
  const offline = new ApiError(0, null);

  await fetchQuery('/shops/', async () => {
    throw offline;
  });

  expect(readQuery('/shops/')).toEqual({ data: ['Palarnia'], error: offline });
});

test('a screen hears about new data for its own path only, until it leaves', async () => {
  const shops = jest.fn();
  const billing = jest.fn();
  const leave = subscribeQuery('/shops/', shops);
  subscribeQuery('/billing/', billing);

  await fetchQuery('/shops/', async () => []);
  leave();
  await fetchQuery('/shops/', async () => [], { force: true });

  expect(shops).toHaveBeenCalledTimes(1);
  expect(billing).not.toHaveBeenCalled();
});

test('signing out forgets what was loaded, answers still on their way included', async () => {
  await setTokens({ access: 'a', refresh: 'r' });
  await fetchQuery('/shops/', async () => ['Sklep konta A']);
  const late = deferred<string>();
  const pending = fetchQuery('/billing/', () => late.promise);

  await setTokens(null);
  late.resolve('Plan konta A');
  await pending;

  expect(readQuery('/shops/').data).toBeUndefined();
  expect(readQuery('/billing/').data).toBeUndefined();
});

test('new tokens for the same session, e.g. after a password change, keep the data', async () => {
  await setTokens({ access: 'a', refresh: 'r' });
  await fetchQuery('/shops/', async () => ['Palarnia']);

  await setTokens({ access: 'b', refresh: 's' });

  expect(readQuery('/shops/').data).toEqual(['Palarnia']);
});
