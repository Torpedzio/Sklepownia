/** "49,00 zł" for ("49.00", "PLN"). */
export function formatMoney(amount: string | number, currency: string) {
  return new Intl.NumberFormat('pl-PL', { style: 'currency', currency }).format(Number(amount));
}

/** "5 grudnia 2026". */
export function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('pl-PL', { day: 'numeric', month: 'long', year: 'numeric' });
}
