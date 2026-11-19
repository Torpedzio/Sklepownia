import { requestHeaders } from 'expo-server';
import type { ScaledSize } from 'react-native';

/**
 * The server renders before it knows the window size, so it assumes narrow (phones) or wide. Hydration must
 * assume the same or React can't reuse the page; the real size takes over right after.
 */
export type Viewport = 'compact' | 'wide';

const WINDOWS: Record<Viewport, ScaledSize> = {
  compact: { width: 390, height: 844, scale: 1, fontScale: 1 },
  wide: { width: 1280, height: 800, scale: 1, fontScale: 1 },
};

/** From the request's browser hints; narrow outside a request. */
export function viewportOfRequest(): Viewport {
  try {
    const headers = requestHeaders();
    // Chromium's client hint; other browsers name the device in the user agent ("Mobile" on phones, not tablets).
    const hint = headers.get('sec-ch-ua-mobile');
    if (hint) return hint === '?1' ? 'compact' : 'wide';
    return /Mobi|iPhone|iPod/.test(headers.get('user-agent') ?? '') ? 'compact' : 'wide';
  } catch {
    return 'compact';
  }
}

/** Server: the request's window; browser: the one +html noted on <html>. */
export function assumedWindow(): ScaledSize {
  if (typeof document === 'undefined') return WINDOWS[viewportOfRequest()];
  return WINDOWS[document.documentElement.dataset.viewport === 'wide' ? 'wide' : 'compact'];
}
