import { slugify } from '@/lib/slugify';

test.each([
  ['Pracownia Ceramiki', 'pracownia-ceramiki'],
  ['Zażółć gęślą jaźń', 'zazolc-gesla-jazn'],
  ['  --Kawa & Herbata!--  ', 'kawa-herbata'],
  ['Café Crème', 'cafe-creme'],
  ['Bardzo długa nazwa sklepu internetowego', 'bardzo-dluga-nazwa-sklepu-inte'],
])('%s → %s', (name, slug) => {
  expect(slugify(name)).toBe(slug);
});

test('never ends with a dash after cutting to 30 characters', () => {
  expect(slugify('abcdefghijklmnopqrstuvwxyz abc def')).toBe('abcdefghijklmnopqrstuvwxyz-abc');
  expect(slugify('abcdefghijklmnopqrstuvwxyzabc def')).toBe('abcdefghijklmnopqrstuvwxyzabc');
});
