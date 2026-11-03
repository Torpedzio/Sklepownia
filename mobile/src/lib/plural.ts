/** Polish plural: plural(2, ['sklep', 'sklepy', 'sklepów']) → 'sklepy'. */
export function plural(count: number, [one, few, many]: [string, string, string]) {
  if (count === 1) return one;
  const lastDigit = count % 10;
  const lastTwo = count % 100;
  return lastDigit >= 2 && lastDigit <= 4 && (lastTwo < 12 || lastTwo > 14) ? few : many;
}
