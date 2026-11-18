import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { router } from 'expo-router';
import { Linking } from 'react-native';

import { ShopChecklist } from '@/components/shop-checklist';
import { NotificationsProvider } from '@/context/notifications';
import { ApiError } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import { mockApi, type Routes } from '@/testing/api';
import { shopChecklist, shopDetail } from '@/testing/fixtures';

jest.mock('expo-router', () => require('@/testing/router'));
jest.mock('@/lib/api', () => ({ ...jest.requireActual('@/lib/api'), api: jest.fn() }));
jest.mock('@/lib/confirm', () => ({ confirm: jest.fn(async () => true) }));

const CHECKLIST = 'GET /shops/7/checklist/';

async function open(routes: Routes, shop = shopDetail()) {
  const api = mockApi(routes);
  const openSettings = jest.fn();
  await render(<ShopChecklist shop={shop} onOpenSettings={openSettings} />, { wrapper: NotificationsProvider });
  return { api, openSettings };
}

beforeEach(() => jest.clearAllMocks());

test('the next step to do is open, the done ones are ticked off', async () => {
  const { openSettings } = await open({ [CHECKLIST]: shopChecklist(['payments', 'shipping', 'documents']) });

  expect(await screen.findByText('Lista startowa')).toBeTruthy();
  expect(screen.getByText('3 z 7')).toBeTruthy();
  expect(screen.getByRole('progressbar').props.accessibilityValue).toMatchObject({ now: 3, max: 7 });
  expect(screen.getByLabelText('Ustaw płatności: zrobione')).toBeTruthy();
  // The first step left is open, with its way to the panel.
  expect(screen.getByText(/Zdjęcia, opis i cenę dodasz w panelu WordPressa/)).toBeTruthy();
  await fireEvent.press(screen.getByRole('button', { name: 'Panel WordPressa' }));
  expect(openSettings).toHaveBeenCalledWith('reczne');
  // The others show only their title.
  expect(screen.queryByText(/Kup coś we własnym sklepie/)).toBeNull();
});

test('the terms step opens their section of the settings', async () => {
  const { openSettings } = await open({ [CHECKLIST]: shopChecklist(['payments', 'shipping']) });

  expect(await screen.findByText(/Każdy sklep w Polsce musi je mieć/)).toBeTruthy();
  await fireEvent.press(screen.getByRole('button', { name: 'Przygotuj regulamin' }));

  expect(openSettings).toHaveBeenCalledWith('regulamin');
});

test('tapping another step opens it instead', async () => {
  const openURL = jest.spyOn(Linking, 'openURL').mockResolvedValue();
  await open({ [CHECKLIST]: shopChecklist() });

  await fireEvent.press(await screen.findByRole('button', { name: 'Złóż próbne zamówienie' }));

  expect(screen.queryByText(/Przelew, płatność przy odbiorze albo płatności online/)).toBeNull();
  await fireEvent.press(screen.getByRole('button', { name: 'Otwórz sklep' }));
  expect(openURL).toHaveBeenCalledWith('http://palarnia.localhost:8080');

  await fireEvent.press(screen.getByRole('button', { name: 'Włącz powiadomienia' }));
  await fireEvent.press(screen.getAllByRole('button', { name: 'Włącz powiadomienia' }).at(-1)!);
  expect(router.push).toHaveBeenCalledWith('/notifications');
});

test('the samples left are counted and removed from the list', async () => {
  const done = ['payments', 'shipping', 'documents', 'products'] as const;
  const { api } = await open({
    [CHECKLIST]: [shopChecklist([...done]), shopChecklist([...done], { refreshing: true })],
    'POST /shops/7/remove-sample-products/': { id: 3, kind: 'remove_sample_products', status: 'queued' },
  });

  expect(await screen.findByText(/W sklepie jest jeszcze 6 przykładowych produktów z zakładania/)).toBeTruthy();
  await fireEvent.press(screen.getByRole('button', { name: 'Usuń przykładowe' }));

  expect(confirm).toHaveBeenCalledWith('Usunąć przykładowe produkty?', expect.any(String), 'Usuń');
  expect(api.calls.map((call) => call.key)).toContain('POST /shops/7/remove-sample-products/');
  expect(await screen.findByText('Usuwamy przykładowe produkty. Krok odhaczy się za chwilę.')).toBeTruthy();
  expect(screen.getByText('Sprawdzamy sklep…')).toBeTruthy();
});

test('a busy shop says why the samples cannot go now', async () => {
  await open({
    [CHECKLIST]: shopChecklist(['payments', 'shipping', 'documents', 'products']),
    'POST /shops/7/remove-sample-products/': new ApiError(409, { detail: 'Sklep zapisuje poprzednią zmianę.' }),
  });

  await fireEvent.press(await screen.findByRole('button', { name: 'Usuń przykładowe' }));

  expect(await screen.findByText('Sklep zapisuje poprzednią zmianę.')).toBeTruthy();
});

test('the list can be hidden after a question', async () => {
  const { api } = await open({
    [CHECKLIST]: [shopChecklist(), shopChecklist([], { available: false, hidden: true, steps: [] })],
    'PATCH /shops/7/checklist/': shopChecklist([], { available: false, hidden: true, steps: [] }),
  });

  await fireEvent.press(await screen.findByRole('button', { name: 'Ukryj listę' }));

  expect(confirm).toHaveBeenCalledWith('Ukryć listę startową?', expect.any(String), 'Ukryj');
  expect(api.sent('PATCH /shops/7/checklist/')).toEqual([{ hidden: true }]);
  await waitFor(() => expect(screen.queryByText('Lista startowa')).toBeNull());
});

test('a finished list says the shop is ready and hides without asking', async () => {
  const all = [
    'payments',
    'shipping',
    'documents',
    'products',
    'sample_products',
    'notifications',
    'test_order',
  ] as const;
  const { api } = await open({
    [CHECKLIST]: shopChecklist([...all]),
    'PATCH /shops/7/checklist/': shopChecklist([...all], { available: false, hidden: true }),
  });

  expect(await screen.findByText('Sklep jest gotowy do sprzedaży')).toBeTruthy();
  await fireEvent.press(screen.getByRole('button', { name: 'Ukryj listę' }));

  expect(confirm).not.toHaveBeenCalled();
  expect(api.sent('PATCH /shops/7/checklist/')).toEqual([{ hidden: true }]);
});

test('a hidden list shows nothing', async () => {
  const { api } = await open({ [CHECKLIST]: shopChecklist([], { available: false, hidden: true, steps: [] }) });

  await waitFor(() => expect(api.calls).toHaveLength(1));
  expect(screen.queryByText('Lista startowa')).toBeNull();
  expect(screen.queryByText('Sklep jest gotowy do sprzedaży')).toBeNull();
});
