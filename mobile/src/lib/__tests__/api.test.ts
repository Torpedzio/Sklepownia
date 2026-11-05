import type * as ApiModule from '@/lib/api';

jest.mock('@/lib/token-storage', () => ({
  readTokens: jest.fn(async () => ({ access: 'old-access', refresh: 'old-refresh' })),
  writeTokens: jest.fn(async () => {}),
}));

type Reply = { status: number; body?: unknown } | 'offline';

/** fetch answering in order; records what was asked. */
function mockFetch(...replies: Reply[]) {
  const fetchMock = jest.fn(async (_url: string, _init?: RequestInit) => {
    const reply = replies.shift();
    if (!reply) throw new Error('unexpected request');
    if (reply === 'offline') throw new TypeError('Network request failed');
    return {
      status: reply.status,
      ok: reply.status >= 200 && reply.status < 300,
      json: async () => {
        if (reply.body === undefined) throw new SyntaxError('no body');
        return reply.body;
      },
    };
  });
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

type Storage = { writeTokens: jest.Mock };
let storage: Storage;

// The client keeps tokens in module state, so every test starts from a fresh copy (with its own storage mock).
async function freshClient(signedIn = true) {
  let client!: typeof ApiModule;
  jest.isolateModules(() => {
    client = require('@/lib/api');
    storage = require('@/lib/token-storage');
  });
  if (signedIn) await client.loadTokens();
  return client;
}

function headersOf(call: [string, RequestInit?]) {
  return call[1]!.headers as Record<string, string>;
}

test('sends JSON with the access token and returns the response', async () => {
  const { api, API_URL } = await freshClient();
  const fetchMock = mockFetch({ status: 200, body: { id: 1 } });

  await expect(api('/shops/', { method: 'POST', body: { name: 'Kawa' } })).resolves.toEqual({ id: 1 });

  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toBe(`${API_URL}/shops/`);
  expect(init!.body).toBe('{"name":"Kawa"}');
  expect(headersOf(fetchMock.mock.calls[0])).toMatchObject({
    Authorization: 'Bearer old-access',
    'Content-Type': 'application/json',
  });
});

test('requests without auth carry no token', async () => {
  const { api } = await freshClient();
  const fetchMock = mockFetch({ status: 200, body: {} });

  await api('/auth/login/', { method: 'POST', body: {}, auth: false });

  expect(headersOf(fetchMock.mock.calls[0]).Authorization).toBeUndefined();
});

test('no content gives null', async () => {
  const { api } = await freshClient();
  mockFetch({ status: 204 });

  await expect(api('/shops/1/', { method: 'DELETE' })).resolves.toBeNull();
});

test('an expired access token is refreshed once and the request repeated', async () => {
  const { api } = await freshClient();
  const fetchMock = mockFetch(
    { status: 401, body: {} },
    { status: 200, body: { access: 'new-access', refresh: 'new-refresh' } },
    { status: 200, body: { ok: true } },
  );

  await expect(api('/auth/me/')).resolves.toEqual({ ok: true });

  expect(headersOf(fetchMock.mock.calls[2]).Authorization).toBe('Bearer new-access');
  expect(storage.writeTokens).toHaveBeenCalledWith({ access: 'new-access', refresh: 'new-refresh' });
});

test('requests failing together share one refresh', async () => {
  const { api } = await freshClient();
  const fetchMock = mockFetch(
    { status: 401, body: {} },
    { status: 401, body: {} },
    { status: 200, body: { access: 'new-access' } },
    { status: 200, body: { n: 1 } },
    { status: 200, body: { n: 2 } },
  );

  await Promise.all([api('/a/'), api('/b/')]);

  const refreshes = fetchMock.mock.calls.filter((call) => String(call[0]).endsWith('/auth/refresh/'));
  expect(refreshes).toHaveLength(1);
});

test('a refresh that fails signs the user out', async () => {
  const client = await freshClient();
  const expired = jest.fn();
  client.setOnSessionExpired(expired);
  mockFetch({ status: 401, body: { detail: 'Token wygasł.' } }, { status: 401, body: {} });

  await expect(client.api('/auth/me/')).rejects.toMatchObject({ status: 401, message: 'Token wygasł.' });

  expect(expired).toHaveBeenCalled();
  expect(storage.writeTokens).toHaveBeenCalledWith(null);
});

test('a refresh without network counts as failed', async () => {
  const client = await freshClient();
  const expired = jest.fn();
  client.setOnSessionExpired(expired);
  mockFetch({ status: 401, body: {} }, 'offline');

  await expect(client.api('/auth/me/')).rejects.toMatchObject({ status: 401 });
  expect(expired).toHaveBeenCalled();
});

test('no network gives a clear message', async () => {
  const { api } = await freshClient(false);
  mockFetch('offline');

  await expect(api('/shops/')).rejects.toMatchObject({ status: 0, message: 'Brak połączenia z serwerem.' });
});

describe('ApiError', () => {
  test.each([
    [400, { detail: 'Nie można.' }, 'Nie można.'],
    [400, { non_field_errors: ['Zły kod.'] }, 'Zły kod.'],
    [500, null, 'Błąd serwera. Spróbuj ponownie.'],
    [400, { email: ['Zajęty.'] }, 'Sprawdź poprawność formularza.'],
  ])('%i %p → %s', async (status, data, message) => {
    const { ApiError } = await freshClient(false);

    expect(new ApiError(status, data).message).toBe(message);
  });

  test('field errors take the first message of each field', async () => {
    const { ApiError } = await freshClient(false);
    const error = new ApiError(400, { slug: ['Zajęty.', 'Inny'], detail: 'x', non_field_errors: ['y'], nested: {} });

    expect(error.fieldErrors).toEqual({ slug: 'Zajęty.' });
  });
});
