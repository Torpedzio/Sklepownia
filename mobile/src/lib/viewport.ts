import { requestHeaders } from 'expo-server';
import type { ScaledSize } from 'react-native';

/**
 * The server draws the page before the browser can tell it the window's size, so it assumes one: narrow for
 * phones, wide for everything else. The browser's first render (hydration) has to assume the same, or React
 * can't reuse the page, and the real size takes over right after (`useWindowDimensions` on the web).
 */
export type Viewport = 'compact' | 'wide';

const WINDOWS: Record<Viewport, ScaledSize> = {
  compact: { width: 390, height: 844, scale: 1, fontScale: 1 },
  wide: { width: 1280, height: 800, scale: 1, fontScale: 1 },
};

/** On the server, from what the request's browser says about itself; narrow outside a request. */
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

/** The window the page was drawn for: on the server the request's, in the browser the one +html noted on <html>. */
export function assumedWindow(): ScaledSize {
  if (typeof document === 'undefined') return WINDOWS[viewportOfRequest()];
  return WINDOWS[document.documentElement.dataset.viewport === 'wide' ? 'wide' : 'compact'];
}
