import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { Linking } from 'react-native';

import ShopScreen from '@/app/shops/[id]';
import { NotificationsProvider } from '@/context/notifications';
import { ApiError } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import type { ShopDetail } from '@/lib/types';
import { mockApi, type Routes } from '@/testing/api';
import { shopDetail, shopSettings } from '@/testing/fixtures';

jest.mock('expo-router', () => require('@/testing/router'));
jest.mock('@/lib/api', () => ({ ...jest.requireActual('@/lib/api'), api: jest.fn() }));
jest.mock('@/lib/confirm', () => ({ confirm: jest.fn(async () => true) }));

const SHOP = 'GET /shops/7/';

async function open(shop: ShopDetail | ShopDetail[], routes: Routes = {}) {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: '7' });
  const api = mockApi({ [SHOP]: Array.isArray(shop) ? shop : [shop], ...routes });
  await render(<ShopScreen />, { wrapper: NotificationsProvider });
  return { api };
}

beforeEach(() => jest.clearAllMocks());

test('a running shop shows its settings at a glance and what is missing', async () => {
  await open(shopDetail(), { 'GET /shops/7/settings/': shopSettings() });

  expect(await screen.findByText('Ustawienia w skrócie')).toBeTruthy();
  expect(
    screen.getByText('Zanim ogłosisz sklep, ustaw płatności i wysyłkę. Bez tego klienci nie złożą zamówienia.'),
  ).toBeTruthy();
  expect(screen.getByText('Brak. Klienci nie mają jak zapłacić.')).toBeTruthy();
  // The receipt keeps the record of the setup.
  expect(screen.getByText('Zakładanie sklepu')).toBeTruthy();
});

test('a shop ready to sell says so', async () => {
  const ready = shopSettings({
    payments: { cash_on_delivery_enabled: true },
    shipping: { local_pickup_enabled: true },
  });
  await open(shopDetail(), { 'GET /shops/7/settings/': ready });

  expect(await screen.findByText(/Klienci mogą już kupować/)).toBeTruthy();
});

test('a closed shop says customers cannot see it', async () => {
  await open(shopDetail(), { 'GET /shops/7/settings/': shopSettings({ availability: { is_open: false } }) });

  expect(await screen.findByText('Sklep jest zamknięty dla klientów')).toBeTruthy();
});

test('the buttons open the shop, its settings and the WordPress panel', async () => {
  const openURL = jest.spyOn(Linking, 'openURL').mockResolvedValue();
  await open(shopDetail(), { 'GET /shops/7/settings/': shopSettings() });

  await fireEvent.press(await screen.findByRole('button', { name: 'Otwórz sklep' }));
  await fireEvent.press(screen.getByRole('button', { name: 'Ustawienia sklepu' }));
  await fireEvent.press(screen.getByRole('button', { name: 'Panel WordPressa' }));

  expect(openURL).toHaveBeenCalledWith('http://palarnia.localhost:8080');
  expect(router.push).toHaveBeenCalledWith({ pathname: '/shops/[id]/settings', params: { id: '7' } });
  expect(router.push).toHaveBeenCalledWith({
    pathname: '/shops/[id]/settings',
    params: { id: '7', section: 'reczne' },
  });
});

test('a shop being set up shows progress and cannot be deleted yet', async () => {
  await open(shopDetail({ status: 'provisioning' }));

  expect(await screen.findByText('Zakładamy Twój sklep…')).toBeTruthy();
  expect(screen.getByText('To potrwa około dwóch minut')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Usuń sklep' })).toBeNull();
});

test('the end of setup is announced when it happens on screen', async () => {
  jest.useFakeTimers();
  try {
    await open([shopDetail({ status: 'provisioning' }), shopDetail()], {
      'GET /shops/7/settings/': shopSettings(),
    });
    await screen.findByText('Zakładamy Twój sklep…');

    // The screen polls while the shop is being set up.
    await jest.advanceTimersByTimeAsync(1600);

    expect(await screen.findByText('Sklep „Palarnia” jest gotowy. Możesz dodawać produkty.')).toBeTruthy();
  } finally {
    jest.useRealTimers();
  }
});

test('a failed setup can be retried', async () => {
  const { api } = await open([shopDetail({ status: 'failed' }), shopDetail({ status: 'provisioning' })], {
    'POST /shops/7/retry/': shopDetail({ status: 'pending' }),
  });

  expect(await screen.findByText('WordPress nie wystartował.')).toBeTruthy();
  await fireEvent.press(screen.getByRole('button', { name: 'Spróbuj ponownie' }));

  expect(api.sent('POST /shops/7/retry/')).toHaveLength(1);
  expect(await screen.findByText('Wznawiamy zakładanie od kroku, który się nie udał.')).toBeTruthy();
});

test('deleting asks first, then goes back', async () => {
  const { api } = await open(shopDetail(), {
    'GET /shops/7/settings/': shopSettings(),
    'DELETE /shops/7/': null,
  });

  await fireEvent.press(await screen.findByRole('button', { name: 'Usuń sklep' }));

  expect(confirm).toHaveBeenCalledWith('Usunąć sklep?', expect.stringContaining('Palarnia'), 'Usuń sklep');
  await waitFor(() => expect(router.back).toHaveBeenCalled());
  expect(api.sent('DELETE /shops/7/')).toHaveLength(1);
});

test('deleting can be called off', async () => {
  (confirm as jest.Mock).mockResolvedValueOnce(false);
  const { api } = await open(shopDetail(), { 'GET /shops/7/settings/': shopSettings() });

  await fireEvent.press(await screen.findByRole('button', { name: 'Usuń sklep' }));

  expect(api.sent('DELETE /shops/7/')).toEqual([]);
});

test('a suspended shop can be brought back or the plan changed', async () => {
  const suspended = shopDetail({ status: 'suspended', status_display: 'Niedostępny w obecnym planie' });
  const { api } = await open([suspended, shopDetail()], {
    'POST /shops/7/resume/': shopDetail(),
    'GET /shops/7/settings/': shopSettings(),
  });

  expect(await screen.findByText('Sklep niedostępny w obecnym planie')).toBeTruthy();
  await fireEvent.press(screen.getByRole('button', { name: 'Zmień plan' }));
  expect(router.push).toHaveBeenCalledWith('/billing/change');

  await fireEvent.press(screen.getByRole('button', { name: 'Przywróć sklep' }));
  expect(api.sent('POST /shops/7/resume/')).toHaveLength(1);
  expect(await screen.findByText('Sklep „Palarnia” znów działa.')).toBeTruthy();
});

test('bringing a shop back explains when the plan is full', async () => {
  await open(shopDetail({ status: 'suspended', status_display: 'Niedostępny w obecnym planie' }), {
    'POST /shops/7/resume/': new ApiError(400, {
      detail: 'Twój plan pozwala na 1 sklep. Zmień plan albo usuń inny sklep, żeby przywrócić ten.',
    }),
  });

  await fireEvent.press(await screen.findByRole('button', { name: 'Przywróć sklep' }));

  expect(await screen.findByText(/Zmień plan albo usuń inny sklep/)).toBeTruthy();
});

test('a PrestaShop shop names its panel and asks only for what the app can set', async () => {
  const presta = shopDetail({ platform: 'prestashop', platform_display: 'PrestaShop', panel_name: 'panel PrestaShop' });
  const settings = shopSettings({}, { sections: ['general', 'availability', 'payments', 'appearance'] });
  await open(presta, { 'GET /shops/7/settings/': settings });

  expect(await screen.findByRole('button', { name: 'Panel PrestaShop' })).toBeTruthy();
  // Shipping is set in the PrestaShop panel, so the app neither shows nor asks for it.
  expect(
    screen.getByText('Zanim ogłosisz sklep, ustaw płatności. Bez tego klienci nie złożą zamówienia.'),
  ).toBeTruthy();
  expect(screen.queryByText('Wysyłka')).toBeNull();
});
