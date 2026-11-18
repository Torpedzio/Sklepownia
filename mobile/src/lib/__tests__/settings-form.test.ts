import { changedFields, fieldList, formatTime, sectionErrors, toApi } from '@/lib/settings-form';

describe('changedFields', () => {
  test('keeps only edits that differ from the saved values', () => {
    const saved = { name: 'Palarnia', low_stock_threshold: 2, reviews: true };

    expect(changedFields(saved, { name: 'Palarnia', low_stock_threshold: '2', reviews: false })).toEqual({
      reviews: false,
    });
  });

  test('no draft means no changes', () => {
    expect(changedFields({ name: 'Palarnia' }, undefined)).toEqual({});
  });

  test('a payment key, never returned by the API, is a change once typed', () => {
    expect(changedFields({}, { przelewy24_crc_key: '' })).toEqual({});
    expect(changedFields({}, { przelewy24_crc_key: 'abc' })).toEqual({ przelewy24_crc_key: 'abc' });
  });
});

describe('fieldList', () => {
  test('starts labels in lower case, but not names and acronyms', () => {
    expect(fieldList(['Nazwa sklepu', 'Stawka VAT', 'ID sprzedawcy Przelewy24', 'OAuth client_id PayU'])).toBe(
      'nazwa sklepu, stawka VAT, ID sprzedawcy Przelewy24, OAuth client_id PayU',
    );
  });
});

describe('toApi', () => {
  test.each([
    ['courier_cost', '12,50', '12.50'],
    ['free_shipping_min_amount', '1 200', '1200'],
    ['standard_rate', '8', '8'],
    ['low_stock_threshold', ' 5 ', 5],
    // Left as typed, so the API explains what is wrong.
    ['low_stock_threshold', 'pięć', 'pięć'],
    ['name', 'Kawa, herbata', 'Kawa, herbata'],
  ])('%s: %p → %p', (key, value, expected) => {
    expect(toApi(key, value)).toEqual(expected);
  });

  test('switches stay booleans', () => {
    expect(toApi('reviews', false)).toBe(false);
  });
});

describe('sectionErrors', () => {
  test('takes the first message of every field, section by section', () => {
    expect(
      sectionErrors({
        payments: { bank_account_number: ['Ten numer konta ma błąd.', 'Drugi komunikat'] },
        general: { name: 'Za krótka nazwa' },
        detail: 'Popraw formularz',
        non_field_errors: ['Coś'],
      }),
    ).toEqual({
      payments: { bank_account_number: 'Ten numer konta ma błąd.' },
      general: { name: 'Za krótka nazwa' },
    });
  });

  test('handles an empty response', () => {
    expect(sectionErrors(null)).toEqual({});
  });
});

describe('formatTime', () => {
  const now = new Date(2026, 10, 5, 15, 0);

  test('says "today" for today', () => {
    expect(formatTime(new Date(2026, 10, 5, 9, 7).toISOString(), now)).toMatch(/^dziś, 09:07$/);
  });

  test('names the day otherwise', () => {
    expect(formatTime(new Date(2026, 10, 3, 18, 30).toISOString(), now)).toMatch(/^3 listopada, 18:30$/);
  });
});
