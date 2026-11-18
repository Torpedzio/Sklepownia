import { fireEvent, render, screen } from '@testing-library/react-native';
import { Linking } from 'react-native';

import NotificationsScreen from '@/app/notifications';
import { PushPrompt } from '@/components/push-prompt';
import { NotificationsProvider } from '@/context/notifications';
import { enablePush, getPushPermission, pushBlocker } from '@/lib/push';
import type { PushPreferences } from '@/lib/types';
import { mockApi } from '@/testing/api';

jest.mock('expo-router', () => require('@/testing/router'));
jest.mock('@/lib/api', () => ({ ...jest.requireActual('@/lib/api'), api: jest.fn() }));
jest.mock('@/lib/push', () => ({
  pushBlocker: jest.fn(() => null),
  getPushPermission: jest.fn(async () => ({ permission: 'undetermined', canAskAgain: true })),
  enablePush: jest.fn(async () => 'granted'),
}));

function preferences(overrides: Partial<PushPreferences> = {}): PushPreferences {
  return {
    new_orders: true,
    shops: true,
    billing: true,
    devices: [
      { name: 'Pixel 8', platform: 'android', platform_display: 'Android', last_seen_at: '2026-11-03T09:00:00Z' },
    ],
    ...overrides,
  };
}

function permission(value: 'granted' | 'denied' | 'undetermined', canAskAgain = true) {
  (getPushPermission as jest.Mock).mockResolvedValue({ permission: value, canAskAgain });
}

beforeEach(() => {
  jest.clearAllMocks();
  (pushBlocker as jest.Mock).mockReturnValue(null);
  permission('undetermined');
});

test('the owner chooses what the notifications are about', async () => {
  const api = mockApi({
    'GET /push/preferences/': [preferences(), preferences({ new_orders: false })],
    'PATCH /push/preferences/': (body: object) => preferences(body),
  });
  await render(<NotificationsScreen />, { wrapper: NotificationsProvider });

  expect(await screen.findByText(/^Powiadomienia dostają: Pixel 8 \(ostatnio 3 listopada, /)).toBeTruthy();
  await fireEvent.press(screen.getByRole('switch', { name: 'Nowe zamówienia' }));

  expect(api.sent('PATCH /push/preferences/')).toEqual([{ new_orders: false }]);
  expect(screen.getByRole('switch', { name: 'Nowe zamówienia' }).props.accessibilityState.checked).toBe(false);
});

test('notifications are turned on for this phone', async () => {
  mockApi({ 'GET /push/preferences/': preferences() });
  await render(<NotificationsScreen />, { wrapper: NotificationsProvider });

  await fireEvent.press(await screen.findByRole('button', { name: 'Włącz powiadomienia' }));

  expect(enablePush).toHaveBeenCalled();
  expect(await screen.findByText('Powiadomienia na tym telefonie są włączone.')).toBeTruthy();
});

test('a phone that refused leads to its settings', async () => {
  permission('denied', false);
  const openSettings = jest.spyOn(Linking, 'openSettings').mockResolvedValue(undefined);
  mockApi({ 'GET /push/preferences/': preferences({ devices: [] }) });
  await render(<NotificationsScreen />, { wrapper: NotificationsProvider });

  await fireEvent.press(await screen.findByRole('button', { name: 'Otwórz ustawienia telefonu' }));

  expect(openSettings).toHaveBeenCalled();
  expect(screen.getByText('Żaden telefon nie dostaje jeszcze powiadomień.')).toBeTruthy();
});

test('in the browser the choices stay, the phone part explains', async () => {
  (pushBlocker as jest.Mock).mockReturnValue('web');
  mockApi({ 'GET /push/preferences/': preferences() });
  await render(<NotificationsScreen />, { wrapper: NotificationsProvider });

  expect(await screen.findByText(/^Powiadomienia przychodzą na telefon z aplikacją/)).toBeTruthy();
  expect(screen.getByRole('switch', { name: 'Plan i płatności' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Włącz powiadomienia' })).toBeNull();
});

test('the offer on the sales screen shows until the phone is asked', async () => {
  await render(<PushPrompt />, { wrapper: NotificationsProvider });
  await fireEvent.press(await screen.findByRole('button', { name: 'Włącz powiadomienia' }));
  expect(await screen.findByText('Powiadomimy Cię o nowych zamówieniach.')).toBeTruthy();

  screen.unmount();
  permission('granted');
  await render(<PushPrompt />, { wrapper: NotificationsProvider });
  expect(screen.queryByText('Wiedz o zamówieniach od razu')).toBeNull();
});
