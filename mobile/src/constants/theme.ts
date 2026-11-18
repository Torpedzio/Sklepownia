/**
 * Design tokens. The look borrows from a street-level shop: a striped awning (accent),
 * a green "open" sign (primary) and receipt paper for anything that records progress.
 */

import { Platform } from 'react-native';

export const Colors = {
  light: {
    background: '#F4F6FA',
    surface: '#FFFFFF',
    surfaceMuted: '#EBEEF4',
    text: '#14213D',
    textSecondary: '#5B6478',
    border: '#D9DEE8',
    primary: '#0F7B5F',
    primaryMuted: '#E2F1EB',
    onPrimary: '#FFFFFF',
    accent: '#F2C14E',
    accentMuted: '#FBF0CF',
    onAccent: '#14213D',
    danger: '#B93A2B',
    onDanger: '#FFFFFF',
    dangerMuted: '#F8E4E1',
    success: '#0F7B5F',
    warning: '#A86B00',
    // Bars of the sales chart.
    chart: '#0F7B5F',
    // Receipts stay paper-white in dark mode too.
    receipt: '#FFFFFF',
    receiptInk: '#1D2433',
    receiptMuted: '#7A8294',
  },
  dark: {
    background: '#0E1526',
    surface: '#16203A',
    surfaceMuted: '#1F2B49',
    text: '#EEF1F8',
    textSecondary: '#A3ADC2',
    border: '#2B3759',
    primary: '#3CC59A',
    primaryMuted: '#173D35',
    onPrimary: '#0B1A15',
    accent: '#F2C14E',
    accentMuted: '#3B3220',
    onAccent: '#14213D',
    danger: '#F2887A',
    onDanger: '#2A0E0A',
    dangerMuted: '#402424',
    success: '#3CC59A',
    warning: '#F2C14E',
    // Darker than primary, so the bars don't glare on the dark surface.
    chart: '#2DA882',
    receipt: '#F7F7F2',
    receiptInk: '#1D2433',
    receiptMuted: '#6D7487',
  },
} as const;

export type ThemeColor = keyof typeof Colors.light & keyof typeof Colors.dark;

// On the web the page shows before the fonts arrive (font-display: swap), in the system font meanwhile.
const withFallback = (font: string) =>
  Platform.OS === 'web' ? `${font}, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` : font;

export const Fonts = {
  display: withFallback('BricolageGrotesque_700Bold'),
  displayMedium: withFallback('BricolageGrotesque_600SemiBold'),
  body: withFallback('Figtree_400Regular'),
  bodyMedium: withFallback('Figtree_500Medium'),
  bodySemiBold: withFallback('Figtree_600SemiBold'),
  bodyBold: withFallback('Figtree_700Bold'),
  mono: Platform.select({ ios: 'Menlo', android: 'monospace', default: 'ui-monospace, Menlo, Consolas, monospace' }),
};

export const Spacing = {
  half: 2,
  one: 4,
  two: 8,
  three: 16,
  four: 24,
  five: 32,
  six: 64,
} as const;

/** Small things are rounder than big ones: chips are pills, sections are nearly square. */
export const Radius = {
  small: 8,
  medium: 14,
  large: 20,
  pill: 999,
} as const;

export const MaxContentWidth = 1080;
export const ReadableWidth = 640;
/** Screen width from which layouts switch to two columns. */
export const WideBreakpoint = 900;
