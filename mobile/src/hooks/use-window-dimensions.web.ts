import { useSyncExternalStore } from 'react';
import { Dimensions, type ScaledSize } from 'react-native';

import { assumedWindow } from '@/lib/viewport';

function subscribe(onChange: () => void) {
  const subscription = Dimensions.addEventListener('change', onChange);
  return () => subscription.remove();
}

const currentWindow = () => Dimensions.get('window');

/**
 * The window's size, like React Native's hook, except while the page from the server comes to life: then it is
 * the size the server drew the page for (`assumedWindow`), so React can reuse that page, and the real size
 * follows in the next render.
 */
export function useWindowDimensions(): ScaledSize {
  return useSyncExternalStore(subscribe, currentWindow, assumedWindow);
}
