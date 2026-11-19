/** Push only works in app builds (development or store), not in Expo Go or the browser. */
import { isRunningInExpoGo } from 'expo';
import Constants from 'expo-constants';
import * as Device from 'expo-device';
import { Platform } from 'react-native';

import { api } from '@/lib/api';

type NotificationsModule = typeof import('expo-notifications');
type Permissions = Awaited<ReturnType<NotificationsModule['getPermissionsAsync']>>;

// Loaded only where push works: expo-notifications warns on import in Expo Go.
const Notifications: NotificationsModule | null =
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  Platform.OS === 'web' || isRunningInExpoGo() ? null : require('expo-notifications');

export type PushBlocker = 'web' | 'expo-go' | 'simulator' | 'no-project';

export type PushPermission = 'granted' | 'denied' | 'undetermined';

// One Android channel per topic, so the phone's settings can silence each. Ids match the backend.
const CHANNELS = [
  { id: 'new_orders', name: 'Nowe zamówienia', high: true },
  { id: 'shops', name: 'Sklepy', high: false },
  { id: 'billing', name: 'Plan i płatności', high: false },
];

// After this long the token is sent again, so the platform knows it's still in use.
const REGISTER_AGAIN_AFTER_MS = 60 * 60 * 1000;

let registered: { token: string; at: number } | null = null;

function projectId(): string | undefined {
  return Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
}

export function pushBlocker(): PushBlocker | null {
  if (Platform.OS === 'web') return 'web';
  if (!Notifications) return 'expo-go';
  if (!Device.isDevice) return 'simulator';
  if (!projectId()) return 'no-project';
  return null;
}

/** Quiet banners while the app is open too. Call once, at start. */
export function configurePush() {
  Notifications?.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: false,
      shouldSetBadge: false,
    }),
  });
}

export async function getPushPermission(): Promise<{ permission: PushPermission; canAskAgain: boolean }> {
  if (!Notifications) return { permission: 'undetermined', canAskAgain: false };
  return describe(await Notifications.getPermissionsAsync());
}

/** Returns whether the phone is registered; `force` resends even if the token just went. */
export async function registerDevice({ force = false } = {}) {
  if (!Notifications || pushBlocker()) return false;
  if (describe(await Notifications.getPermissionsAsync()).permission !== 'granted') return false;
  if (!force && registered && Date.now() - registered.at < REGISTER_AGAIN_AFTER_MS) return true;
  await createChannels();
  const { data: token } = await Notifications.getExpoPushTokenAsync({ projectId: projectId() });
  await api('/push/devices/', {
    method: 'POST',
    body: { token, platform: Platform.OS, name: (Device.modelName ?? '').slice(0, 100) },
  });
  registered = { token, at: Date.now() };
  return true;
}

export async function enablePush(): Promise<PushPermission> {
  if (!Notifications || pushBlocker()) return 'undetermined';
  // Android 13 asks for permission once a channel exists, so the channels come first.
  await createChannels();
  let permissions = await Notifications.getPermissionsAsync();
  if (describe(permissions).permission !== 'granted' && permissions.canAskAgain) {
    permissions = await Notifications.requestPermissionsAsync();
  }
  const { permission } = describe(permissions);
  if (permission === 'granted') await registerDevice({ force: true });
  return permission;
}

/** Never fails the sign-out. */
export async function forgetDevice() {
  const token = registered?.token;
  registered = null;
  if (token) await api('/push/devices/forget/', { method: 'POST', body: { token } }).catch(() => {});
}

export function onPushTokenChange(listener: () => void) {
  const subscription = Notifications?.addPushTokenListener(listener);
  return () => subscription?.remove();
}

/** Also handles the tap that started the app. Returns the cleanup. */
export function openTappedNotifications(open: (url: string) => void) {
  if (!Notifications) return () => {};
  const module = Notifications;
  function handle(response: ReturnType<NotificationsModule['getLastNotificationResponse']>) {
    const url = response?.notification.request.content.data?.url;
    // Only screens of the app, never an outside address.
    if (typeof url === 'string' && url.startsWith('/')) open(url);
    module.clearLastNotificationResponse();
  }
  const last = module.getLastNotificationResponse();
  if (last) handle(last);
  const subscription = module.addNotificationResponseReceivedListener(handle);
  return () => subscription.remove();
}

function describe(permissions: Permissions): { permission: PushPermission; canAskAgain: boolean } {
  // iOS can allow notifications quietly ("provisional"): they still arrive, in the notification centre.
  const provisional = permissions.ios?.status === Notifications?.IosAuthorizationStatus.PROVISIONAL;
  const permission =
    permissions.granted || provisional ? 'granted' : permissions.status === 'denied' ? 'denied' : 'undetermined';
  return { permission, canAskAgain: permissions.canAskAgain };
}

async function createChannels() {
  if (Platform.OS !== 'android' || !Notifications) return;
  const { AndroidImportance } = Notifications;
  await Promise.all(
    CHANNELS.map((channel) =>
      Notifications.setNotificationChannelAsync(channel.id, {
        name: channel.name,
        importance: channel.high ? AndroidImportance.HIGH : AndroidImportance.DEFAULT,
        lightColor: '#0F7B5F',
      }),
    ),
  );
}
