import { plural } from '@/lib/plural';

const forms: [string, string, string] = ['sklep', 'sklepy', 'sklepów'];

test.each([
  [1, 'sklep'],
  [2, 'sklepy'],
  [4, 'sklepy'],
  [5, 'sklepów'],
  [12, 'sklepów'],
  [14, 'sklepów'],
  [22, 'sklepy'],
  [0, 'sklepów'],
])('%i → %s', (count, expected) => {
  expect(plural(count, forms)).toBe(expected);
});
