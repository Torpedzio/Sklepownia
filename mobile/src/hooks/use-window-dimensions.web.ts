import { useSyncExternalStore } from 'react';
import { Dimensions, type ScaledSize } from 'react-native';

import { assumedWindow } from '@/lib/viewport';

function subscribe(onChange: () => void) {
  const subscription = Dimensions.addEventListener('change', onChange);
  return () => subscription.remove();
}

const currentWindow = () => Dimensions.get('window');

/** Like React Native's, but during hydration the size the server rendered for (`assumedWindow`). */
export function useWindowDimensions(): ScaledSize {
  return useSyncExternalStore(subscribe, currentWindow, assumedWindow);
}
