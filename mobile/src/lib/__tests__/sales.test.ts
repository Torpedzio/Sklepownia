import { ordersLabel, revenueChange, scaleTop } from '@/lib/sales';

const period = (revenue: string) => ({ orders: 1, revenue, average: revenue });

test('orders are counted in Polish', () => {
  expect([1, 2, 5, 12, 22].map(ordersLabel)).toEqual([
    '1 zamówienie',
    '2 zamówienia',
    '5 zamówień',
    '12 zamówień',
    '22 zamówienia',
  ]);
});

describe('revenueChange', () => {
  test('says how much more or less was sold than in the 30 days before', () => {
    expect(revenueChange(period('150.00'), period('100.00'))).toEqual({
      direction: 'up',
      text: '+50% względem poprzednich 30 dni',
    });
    expect(revenueChange(period('80.00'), period('100.00'))).toEqual({
      direction: 'down',
      text: '−20% względem poprzednich 30 dni',
    });
    expect(revenueChange(period('100.20'), period('100.00'))?.direction).toBe('same');
  });

  test('has no percentage when nothing was sold before', () => {
    expect(revenueChange(period('50.00'), period('0.00'))?.text).toBe('W poprzednich 30 dniach bez sprzedaży');
    expect(revenueChange(period('0.00'), period('0.00'))).toBeNull();
  });
});

test('the chart scale ends on a round number', () => {
  expect([0, 7, 120, 199, 201, 350, 999, 1000].map(scaleTop)).toEqual([0, 10, 200, 200, 250, 500, 1000, 1000]);
});
