import Constants from 'expo-constants';
import * as Notifications from 'expo-notifications';

import { api } from '@/lib/api';
import { enablePush, forgetDevice, openTappedNotifications, pushBlocker, registerDevice } from '@/lib/push';

jest.mock('@/lib/api', () => ({ api: jest.fn(async () => ({})) }));
jest.mock('expo', () => ({ isRunningInExpoGo: () => false }));
jest.mock('expo-device', () => ({ isDevice: true, modelName: 'Pixel 8' }));
jest.mock('expo-constants', () => ({
  __esModule: true,
  default: { expoConfig: { extra: { eas: { projectId: 'p-1' } } } },
}));
jest.mock('expo-notifications', () => {
  const listeners: ((response: unknown) => void)[] = [];
  return {
    IosAuthorizationStatus: { PROVISIONAL: 3 },
    AndroidImportance: { HIGH: 4, DEFAULT: 3 },
    getPermissionsAsync: jest.fn(),
    requestPermissionsAsync: jest.fn(),
    getExpoPushTokenAsync: jest.fn(async () => ({ type: 'expo', data: 'ExponentPushToken[abc]' })),
    setNotificationChannelAsync: jest.fn(async () => null),
    getLastNotificationResponse: jest.fn(() => null),
    clearLastNotificationResponse: jest.fn(),
    addNotificationResponseReceivedListener: jest.fn((listener) => {
      listeners.push(listener);
      return { remove: jest.fn() };
    }),
    __tap: (url: unknown) => listeners.forEach((listener) => listener(mockTapOn(url))),
  };
});

function mockTapOn(url: unknown) {
  return { notification: { request: { content: { data: { url } } } } };
}

const permissions = (status: 'granted' | 'denied' | 'undetermined', canAskAgain = true) => ({
  status,
  granted: status === 'granted',
  canAskAgain,
  expires: 'never',
});

const mocked = Notifications as jest.Mocked<typeof Notifications> & { __tap: (url: unknown) => void };

beforeEach(() => {
  jest.clearAllMocks();
  mocked.getPermissionsAsync.mockResolvedValue(permissions('granted') as never);
});

test('an allowed phone sends its token with the platform and model', async () => {
  expect(await registerDevice({ force: true })).toBe(true);

  expect(mocked.getExpoPushTokenAsync).toHaveBeenCalledWith({ projectId: 'p-1' });
  expect(api).toHaveBeenCalledWith('/push/devices/', {
    method: 'POST',
    body: { token: 'ExponentPushToken[abc]', platform: 'ios', name: 'Pixel 8' },
  });
  // Coming back to the app a moment later doesn't send it again.
  (api as jest.Mock).mockClear();
  expect(await registerDevice()).toBe(true);
  expect(api).not.toHaveBeenCalled();
});

test('a phone without permission sends nothing', async () => {
  mocked.getPermissionsAsync.mockResolvedValue(permissions('denied') as never);

  expect(await registerDevice({ force: true })).toBe(false);
  expect(api).not.toHaveBeenCalled();
});

test('turning notifications on asks the phone once, then registers it', async () => {
  mocked.getPermissionsAsync.mockResolvedValueOnce(permissions('undetermined') as never);
  mocked.requestPermissionsAsync.mockResolvedValue(permissions('granted') as never);

  expect(await enablePush()).toBe('granted');

  expect(mocked.requestPermissionsAsync).toHaveBeenCalledTimes(1);
  expect(api).toHaveBeenCalledWith('/push/devices/', expect.objectContaining({ method: 'POST' }));
});

test('a refusal that the phone remembers is not asked again', async () => {
  mocked.getPermissionsAsync.mockResolvedValue(permissions('denied', false) as never);

  expect(await enablePush()).toBe('denied');
  expect(mocked.requestPermissionsAsync).not.toHaveBeenCalled();
});

test('signing out forgets the registered phone', async () => {
  await registerDevice({ force: true });

  await forgetDevice();
  await forgetDevice();

  expect(api).toHaveBeenCalledWith('/push/devices/forget/', {
    method: 'POST',
    body: { token: 'ExponentPushToken[abc]' },
  });
  expect((api as jest.Mock).mock.calls.filter(([path]) => path === '/push/devices/forget/')).toHaveLength(1);
});

test('a tapped notification opens its screen of the app, nothing else', () => {
  const open = jest.fn();
  mocked.getLastNotificationResponse.mockReturnValueOnce(mockTapOn('/shops/7/sales') as never);

  const stop = openTappedNotifications(open);
  mocked.__tap('https://example.com');
  mocked.__tap('/billing');
  stop();

  expect(open.mock.calls).toEqual([['/shops/7/sales'], ['/billing']]);
});

test('a build without an Expo project cannot get notifications', () => {
  expect(pushBlocker()).toBeNull();
  Constants.expoConfig!.extra!.eas.projectId = undefined;

  expect(pushBlocker()).toBe('no-project');
});
