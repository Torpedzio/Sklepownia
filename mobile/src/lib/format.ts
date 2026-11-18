/** "49,00 zł" for ("49.00", "PLN"), "50 zł" with `whole`. A code Intl doesn't take is written out as is. */
export function formatMoney(amount: string | number, currency: string, { whole = false } = {}) {
  try {
    return new Intl.NumberFormat('pl-PL', {
      style: 'currency',
      currency,
      ...(whole ? { minimumFractionDigits: 0, maximumFractionDigits: 0 } : {}),
    }).format(Number(amount));
  } catch {
    return `${amount} ${currency}`.trim();
  }
}

/** "5 grudnia 2026". */
export function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('pl-PL', { day: 'numeric', month: 'long', year: 'numeric' });
}

/** A calendar day ("2026-11-18") as a local date, not midnight UTC. */
export function parseDay(day: string) {
  const [year, month, date] = day.split('-').map(Number);
  return new Date(year, month - 1, date);
}

/** "18 lis" for "2026-11-18". */
export function formatShortDay(day: string) {
  return parseDay(day).toLocaleDateString('pl-PL', { day: 'numeric', month: 'short' });
}

/** "śr., 18 listopada" for "2026-11-18". */
export function formatDay(day: string) {
  return parseDay(day).toLocaleDateString('pl-PL', { weekday: 'short', day: 'numeric', month: 'long' });
}

/** "panel WordPressa" → "panelu WordPressa", for "w …". */
export function panelLocative(panelName: string | undefined) {
  return (panelName ?? 'panel sklepu').replace(/^panel\b/, 'panelu');
}

/** "panel WordPressa" → "Panel WordPressa", for a button. */
export function panelTitle(panelName: string) {
  return panelName.charAt(0).toUpperCase() + panelName.slice(1);
}
