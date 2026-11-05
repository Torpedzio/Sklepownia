import * as SecureStore from 'expo-secure-store';
import { Alert, type AlertButton } from 'react-native';

import { confirm } from '@/lib/confirm';
import { readTokens, writeTokens } from '@/lib/token-storage';

jest.mock('expo-secure-store', () => {
  const store = new Map<string, string>();
  return {
    getItemAsync: jest.fn(async (key: string) => store.get(key) ?? null),
    setItemAsync: jest.fn(async (key: string, value: string) => void store.set(key, value)),
    deleteItemAsync: jest.fn(async (key: string) => void store.delete(key)),
  };
});

test('tokens live in the secure store on the phone', async () => {
  await expect(readTokens()).resolves.toBeNull();

  await writeTokens({ access: 'a', refresh: 'r' });
  await expect(readTokens()).resolves.toEqual({ access: 'a', refresh: 'r' });

  await writeTokens(null);
  await expect(readTokens()).resolves.toBeNull();
  expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith('auth-tokens');
});

test.each([
  ['Usuń sklep', true],
  ['Anuluj', false],
])('confirm resolves when "%s" is chosen', async (choice, expected) => {
  jest.spyOn(Alert, 'alert').mockImplementation((_title, _message, buttons?: AlertButton[]) => {
    buttons?.find((button) => button.text === choice)?.onPress?.();
  });

  await expect(confirm('Usunąć sklep?', 'Tego nie da się cofnąć.', 'Usuń sklep')).resolves.toBe(expected);
});
