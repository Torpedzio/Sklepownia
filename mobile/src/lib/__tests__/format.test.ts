import { formatMoment } from '@/lib/format';

test('a moment today is just the time, on another day the date too', () => {
  const now = new Date(2026, 10, 19, 15, 0);

  expect(formatMoment(new Date(2026, 10, 19, 9, 5).toISOString(), now)).toBe('09:05');
  expect(formatMoment(new Date(2026, 10, 18, 22, 30).toISOString(), now)).toBe('18 listopada, 22:30');
});
