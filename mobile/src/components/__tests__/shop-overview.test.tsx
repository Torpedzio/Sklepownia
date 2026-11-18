import { fireEvent, render, screen } from '@testing-library/react-native';
import { router } from 'expo-router';

import { describeSettings, missingForSales, ShopOverview } from '@/components/shop-overview';
import { shopSettings } from '@/testing/fixtures';

jest.mock('expo-router', () => ({ router: { push: jest.fn() } }));

const valueOf = (settings: ReturnType<typeof shopSettings>, title: string) =>
  describeSettings(settings).find((tile) => tile.title === title)!;

describe('describeSettings', () => {
  test('a fresh shop is missing payments and shipping', () => {
    const settings = shopSettings();

    expect(valueOf(settings, 'Płatności')).toMatchObject({
      value: 'Brak. Klienci nie mają jak zapłacić.',
      missing: true,
    });
    expect(valueOf(settings, 'Wysyłka')).toMatchObject({ value: 'Brak. Klienci nie wybiorą dostawy.', missing: true });
    expect(missingForSales(settings)).toEqual(['płatności', 'wysyłkę']);
  });

  test('lists what the shop offers, with prices in its currency', () => {
    const settings = shopSettings({
      payments: { bank_transfer_enabled: true, cash_on_delivery_enabled: true },
      shipping: {
        courier_enabled: true,
        courier_cost: '14.99',
        free_shipping_enabled: true,
        local_pickup_enabled: true,
      },
      taxes: { enabled: true, prices_include_tax: false, standard_rate: '8.00' },
      region: { currency: 'EUR', country: 'DE', language: 'en_US' },
    });

    expect(valueOf(settings, 'Płatności').value).toBe('Przelew tradycyjny, płatność przy odbiorze');
    expect(valueOf(settings, 'Wysyłka').value).toBe('Kurier 14,99 EUR, darmowa od 200,00 EUR, odbiór osobisty');
    expect(valueOf(settings, 'Podatki').value).toBe('VAT 8%, ceny netto');
    expect(valueOf(settings, 'Region').value).toBe('English, EUR, Niemcy');
    expect(missingForSales(settings)).toEqual([]);
  });

  test('online payments count as a way to pay', () => {
    const settings = shopSettings({ payments: { przelewy24_enabled: true, payu_enabled: true } });

    expect(valueOf(settings, 'Płatności')).toMatchObject({ value: 'Przelewy24, PayU', missing: false });
    expect(missingForSales(settings)).toEqual(['wysyłkę']);
  });

  test('describes a closed shop, free shipping without a threshold and other choices', () => {
    const settings = shopSettings({
      availability: { is_open: false },
      shipping: { free_shipping_enabled: true, free_shipping_min_amount: '0.00' },
      shopping: { guest_checkout: false, signup_at_checkout: true, reviews: false },
      appearance: { theme: 'astra' },
    });

    expect(valueOf(settings, 'Sklep').value).toBe('Zamknięty. Klienci widzą stronę „Wkrótce otwarcie”.');
    expect(valueOf(settings, 'Wysyłka').value).toBe('Zawsze darmowa');
    expect(valueOf(settings, 'Zakupy').value).toBe('Tylko z kontem klienta, bez opinii');
    expect(valueOf(settings, 'Podatki').value).toBe('Bez naliczania VAT');
    expect(valueOf(settings, 'Wygląd').value).toBe('Motyw Astra');
    expect(valueOf(settings, 'Kontakt').value).toBe('kontakt@example.com');
  });

  test('shows the raw value for an option the list does not know', () => {
    const settings = shopSettings({ region: { language: 'fr_FR' } });

    expect(valueOf(settings, 'Region').value).toBe('fr_FR, PLN, Polska');
  });
});

test('a tile opens its section of the settings', async () => {
  await render(<ShopOverview shopId={7} settings={shopSettings()} />);

  await fireEvent.press(screen.getByLabelText('Wysyłka: Brak. Klienci nie wybiorą dostawy. Zmień w ustawieniach.'));

  expect(router.push).toHaveBeenCalledWith({
    pathname: '/shops/[id]/settings',
    params: { id: '7', section: 'wysylka' },
  });
});
