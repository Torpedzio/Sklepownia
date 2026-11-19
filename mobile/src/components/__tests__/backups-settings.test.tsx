import { backupName, backupTime } from '@/components/backups-settings';
import { formatSize } from '@/lib/format';

const now = new Date(2026, 10, 19, 14, 30);

test('a backup is named by its day, today and yesterday in words', () => {
  expect(backupTime(new Date(2026, 10, 19, 3, 0).toISOString(), now)).toBe('Dziś, 03:00');
  expect(backupTime(new Date(2026, 10, 18, 15, 20).toISOString(), now)).toBe('Wczoraj, 15:20');
  expect(backupTime(new Date(2026, 10, 16, 3, 0).toISOString(), now)).toBe('16 listopada, 03:00');

  expect(backupName(new Date(2026, 10, 19, 3, 0).toISOString(), now)).toBe('dzisiejszą kopię z 03:00');
  expect(backupName(new Date(2026, 10, 18, 3, 0).toISOString(), now)).toBe('wczorajszą kopię z 03:00');
  expect(backupName(new Date(2026, 9, 31, 3, 0).toISOString(), now)).toBe('kopię z 31 października, 03:00');
});

test('sizes are short and in Polish', () => {
  expect(formatSize(980)).toBe('980 B');
  expect(formatSize(48_000)).toBe('48 kB');
  expect(formatSize(215_300_000)).toBe('215 MB');
  expect(formatSize(1_240_000_000)).toBe('1,2 GB');
  expect(formatSize(3_000_000)).toBe('3 MB');
});
