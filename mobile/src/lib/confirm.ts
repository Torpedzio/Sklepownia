import { Alert, Platform } from 'react-native';

/** `cancelLabel` for when "Anuluj" would read as the action itself, e.g. next to cancelling an order. */
export function confirm(
  title: string,
  message: string,
  confirmLabel: string,
  cancelLabel = 'Anuluj',
): Promise<boolean> {
  if (Platform.OS === 'web') {
    return Promise.resolve(globalThis.confirm(`${title}\n\n${message}`));
  }
  return new Promise((resolve) =>
    Alert.alert(title, message, [
      { text: cancelLabel, style: 'cancel', onPress: () => resolve(false) },
      { text: confirmLabel, style: 'destructive', onPress: () => resolve(true) },
    ]),
  );
}
