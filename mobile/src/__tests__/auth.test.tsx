import { act, render, screen, waitFor } from '@testing-library/react-native';
import { useEffect } from 'react';
import { Text } from 'react-native';

import { AuthProvider, useAuth } from '@/context/auth';
import { NotificationsProvider } from '@/context/notifications';
import { ApiError, loadTokens, setOnSessionExpired, setTokens } from '@/lib/api';
import { mockApi, type Routes } from '@/testing/api';

jest.mock('@/lib/api', () => ({
  ...jest.requireActual('@/lib/api'),
  api: jest.fn(),
  loadTokens: jest.fn(),
  setTokens: jest.fn(async () => {}),
  setOnSessionExpired: jest.fn(),
}));

const anna = { id: 1, email: 'anna@example.com', first_name: 'Anna', is_email_verified: true };
// The latest context value, for calling its actions from tests.
const latest: { auth?: ReturnType<typeof useAuth> } = {};
const auth = () => latest.auth!;

function Probe() {
  const value = useAuth();
  useEffect(() => {
    latest.auth = value;
  });
  return <Text>{value.isLoading ? 'ładowanie' : (value.user?.email ?? 'wylogowany')}</Text>;
}

async function start(tokens: unknown, routes: Routes = {}) {
  (loadTokens as jest.Mock).mockResolvedValue(tokens);
  const api = mockApi(routes);
  await render(
    <NotificationsProvider>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </NotificationsProvider>,
  );
  return { api };
}

beforeEach(() => jest.clearAllMocks());

test('a saved session is restored on start', async () => {
  await start({ access: 'a', refresh: 'r' }, { 'GET /auth/me/': anna });

  expect(await screen.findByText('anna@example.com')).toBeTruthy();
});

test('a session the server no longer accepts is dropped', async () => {
  await start({ access: 'a', refresh: 'r' }, { 'GET /auth/me/': new ApiError(401, null) });

  expect(await screen.findByText('wylogowany')).toBeTruthy();
  expect(setTokens).toHaveBeenCalledWith(null);
});

test('signing in stores the tokens and loads the user', async () => {
  const { api } = await start(null, {
    'POST /auth/login/': { access: 'a', refresh: 'r' },
    'GET /auth/me/': anna,
  });
  await screen.findByText('wylogowany');

  await act(() => auth().signIn('anna@example.com', 'haslo'));

  expect(setTokens).toHaveBeenCalledWith({ access: 'a', refresh: 'r' });
  expect(api.sent('POST /auth/login/')).toEqual([{ email: 'anna@example.com', password: 'haslo' }]);
  expect(screen.getByText('anna@example.com')).toBeTruthy();
});

test('signing up, verifying, resending and editing the profile keep the user current', async () => {
  const { api } = await start(null, {
    'POST /auth/register/': { user: { ...anna, is_email_verified: false }, tokens: { access: 'a', refresh: 'r' } },
    'POST /auth/verify-email/': anna,
    'POST /auth/resend-verification/': null,
    'PATCH /auth/me/': { ...anna, email: 'anna.nowak@example.com' },
  });
  await screen.findByText('wylogowany');

  await act(() => auth().signUp('anna@example.com', 'haslo'));
  expect(auth().user?.is_email_verified).toBe(false);
  await act(() => auth().verifyEmail('123456'));
  expect(auth().user?.is_email_verified).toBe(true);
  await act(() => auth().resendCode());
  await act(() => auth().updateProfile({ first_name: 'Anna', last_name: 'Nowak' }));

  expect(api.sent('POST /auth/verify-email/')).toEqual([{ code: '123456' }]);
  expect(screen.getByText('anna.nowak@example.com')).toBeTruthy();
});

test('signing out forgets the session on the server and here', async () => {
  const { api } = await start({ access: 'a', refresh: 'r' }, { 'GET /auth/me/': anna, 'POST /auth/logout/': null });
  await screen.findByText('anna@example.com');

  await act(() => auth().signOut());

  expect(api.sent('POST /auth/logout/')).toEqual([{ refresh: 'r' }]);
  expect(screen.getByText('wylogowany')).toBeTruthy();
});

test('a new password keeps this device signed in with fresh tokens', async () => {
  const { api } = await start(
    { access: 'a', refresh: 'r' },
    {
      'GET /auth/me/': anna,
      'POST /auth/change-password/': { access: 'a2', refresh: 'r2' },
      'POST /auth/logout-everywhere/': null,
    },
  );
  await screen.findByText('anna@example.com');

  await act(() => auth().changePassword('stare', 'nowe-haslo-123'));

  expect(api.sent('POST /auth/change-password/')).toEqual([
    { current_password: 'stare', new_password: 'nowe-haslo-123' },
  ]);
  expect(setTokens).toHaveBeenCalledWith({ access: 'a2', refresh: 'r2' });
  expect(screen.getByText('anna@example.com')).toBeTruthy();

  await act(() => auth().signOutEverywhere());

  expect(setTokens).toHaveBeenLastCalledWith(null);
  expect(screen.getByText('wylogowany')).toBeTruthy();
});

test('deleting the account sends the password and drops the session', async () => {
  const { api } = await start({ access: 'a', refresh: 'r' }, { 'GET /auth/me/': anna, 'POST /auth/delete-account/': null });
  await screen.findByText('anna@example.com');

  await act(() => auth().deleteAccount('Sekretne-haslo-123'));

  expect(api.sent('POST /auth/delete-account/')).toEqual([{ password: 'Sekretne-haslo-123' }]);
  expect(setTokens).toHaveBeenLastCalledWith(null);
  expect(screen.getByText('wylogowany')).toBeTruthy();
});

test('a forgotten password: a code by e-mail, then signed in with the new password', async () => {
  const { api } = await start(null, {
    'POST /auth/password-reset/': null,
    'POST /auth/password-reset/confirm/': { access: 'a', refresh: 'r' },
    'GET /auth/me/': anna,
  });
  await screen.findByText('wylogowany');

  await act(() => auth().requestPasswordReset('anna@example.com'));
  await act(() => auth().resetPassword('anna@example.com', '123456', 'Nowe-haslo-123'));

  expect(api.sent('POST /auth/password-reset/')).toEqual([{ email: 'anna@example.com' }]);
  expect(api.sent('POST /auth/password-reset/confirm/')).toEqual([
    { email: 'anna@example.com', code: '123456', new_password: 'Nowe-haslo-123' },
  ]);
  expect(setTokens).toHaveBeenCalledWith({ access: 'a', refresh: 'r' });
  expect(screen.getByText('anna@example.com')).toBeTruthy();
});

test('a new profile picture goes up as a file and the user keeps it', async () => {
  const withPhoto = { ...anna, avatar_url: 'http://localhost:8000/media/avatars/a.webp' };
  const { api } = await start(
    { access: 'a', refresh: 'r' },
    { 'GET /auth/me/': anna, 'PUT /auth/avatar/': withPhoto, 'DELETE /auth/avatar/': anna },
  );
  await screen.findByText('anna@example.com');
  // On the web the picker hands over a File; on phones React Native's FormData takes { uri, name, type }.
  const photo = new File(['jpeg'], 'photo.jpg', { type: 'image/jpeg' });

  await act(() => auth().changeAvatar(photo));

  const [form] = api.sent('PUT /auth/avatar/') as FormData[];
  expect(form).toBeInstanceOf(FormData);
  expect(form.get('avatar')).toMatchObject({ name: 'photo.jpg', type: 'image/jpeg' });
  expect(auth().user?.avatar_url).toBe(withPhoto.avatar_url);

  await act(() => auth().removeAvatar());

  expect(auth().user?.avatar_url).toBeUndefined();
});

test('an expired session signs out with a message', async () => {
  await start({ access: 'a', refresh: 'r' }, { 'GET /auth/me/': anna });
  await screen.findByText('anna@example.com');

  const onExpired = (setOnSessionExpired as jest.Mock).mock.calls[0][0];
  await act(async () => onExpired());

  expect(screen.getByText('wylogowany')).toBeTruthy();
  expect(screen.getByText('Sesja wygasła. Zaloguj się ponownie.')).toBeTruthy();
});

test('useAuth outside the provider is a mistake', () => {
  jest.spyOn(console, 'error').mockImplementation(() => {});
  function Lonely() {
    useAuth();
    return null;
  }

  expect(() => render(<Lonely />)).rejects.toThrow('useAuth must be used inside AuthProvider');
});

test('notifications can be dismissed and fade on their own', async () => {
  jest.useFakeTimers();
  try {
    await start({ access: 'a', refresh: 'r' }, { 'GET /auth/me/': anna });
    await screen.findByText('anna@example.com');
    const onExpired = (setOnSessionExpired as jest.Mock).mock.calls[0][0];

    await act(async () => onExpired());
    await act(() => jest.advanceTimersByTimeAsync(7100));
    await waitFor(() => expect(screen.queryByText('Sesja wygasła. Zaloguj się ponownie.')).toBeNull());
  } finally {
    jest.useRealTimers();
  }
});
