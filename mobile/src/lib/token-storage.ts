import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

import type { Tokens } from './types';

const KEY = 'auth-tokens';

// SecureStore has no web implementation; web dev falls back to localStorage.
export async function readTokens(): Promise<Tokens | null> {
  const raw =
    Platform.OS === 'web' ? globalThis.localStorage?.getItem(KEY) : await SecureStore.getItemAsync(KEY);
  return raw ? JSON.parse(raw) : null;
}

export async function writeTokens(tokens: Tokens | null) {
  if (Platform.OS === 'web') {
    if (tokens) globalThis.localStorage?.setItem(KEY, JSON.stringify(tokens));
    else globalThis.localStorage?.removeItem(KEY);
    return;
  }
  if (tokens) await SecureStore.setItemAsync(KEY, JSON.stringify(tokens));
  else await SecureStore.deleteItemAsync(KEY);
}
