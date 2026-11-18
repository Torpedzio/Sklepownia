import type { ThemeColor } from '@/constants/theme';
import { plural } from '@/lib/plural';
import type { OrderStatus, SalesPeriod } from '@/lib/types';

// While the platform reads the shop, the app asks again this often.
export const SALES_POLL_MS = 2500;

/** "1 zamówienie", "3 zamówienia", "5 zamówień". */
export function ordersLabel(count: number) {
  return `${count} ${plural(count, ['zamówienie', 'zamówienia', 'zamówień'])}`;
}

export type RevenueChange = { direction: 'up' | 'down' | 'same'; text: string };

/** How the last 30 days compare with the 30 before, or null when neither had sales. */
export function revenueChange(current: SalesPeriod, previous: SalesPeriod): RevenueChange | null {
  const now = Number(current.revenue);
  const before = Number(previous.revenue);
  if (!before) return now ? { direction: 'up', text: 'W poprzednich 30 dniach bez sprzedaży' } : null;
  const percent = Math.round(((now - before) / before) * 100);
  if (!percent) return { direction: 'same', text: 'Tyle samo co w poprzednich 30 dniach' };
  // A real minus sign, as wide as the plus.
  const signed = percent > 0 ? `+${percent}%` : `\u2212${-percent}%`;
  return { direction: percent > 0 ? 'up' : 'down', text: `${signed} względem poprzednich 30 dni` };
}

/**
 * The top of the chart's scale: the biggest day rounded up to 1, 2, 2.5 or 5 times a power of ten,
 * so its label is a round number.
 */
export function scaleTop(max: number) {
  if (max <= 0) return 0;
  const magnitude = 10 ** Math.floor(Math.log10(max));
  const step = [1, 2, 2.5, 5, 10].find((factor) => factor * magnitude >= max)!;
  return step * magnitude;
}

/** Orders waiting for the owner come first in the eye: the rest recede. */
export const ORDER_STATUS_COLORS = {
  new: ['warning', 'accentMuted'],
  processing: ['primary', 'primaryMuted'],
  completed: ['textSecondary', 'surfaceMuted'],
  cancelled: ['danger', 'dangerMuted'],
  unfinished: ['textSecondary', 'surfaceMuted'],
} as const satisfies Record<OrderStatus, readonly [ThemeColor, ThemeColor]>;
