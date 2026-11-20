import { fireEvent, render, screen } from '@testing-library/react-native';
import { router, useLocalSearchParams } from 'expo-router';

import ShopSalesScreen from '@/app/shops/[id]/sales';
import { NotificationsProvider } from '@/context/notifications';
import type { ShopSales } from '@/lib/types';
import { mockApi, type Routes } from '@/testing/api';
import { shopDetail, shopSales } from '@/testing/fixtures';

jest.mock('expo-router', () => require('@/testing/router'));
jest.mock('@/lib/api', () => ({ ...jest.requireActual('@/lib/api'), api: jest.fn() }));

const SALES = 'GET /shops/7/sales/';

async function open(sales: ShopSales | ShopSales[], routes: Routes = {}) {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: '7' });
  const api = mockApi({ 'GET /shops/7/': shopDetail(), [SALES]: Array.isArray(sales) ? sales : [sales], ...routes });
  await render(<ShopSalesScreen />, { wrapper: NotificationsProvider });
  return { api };
}

beforeEach(() => jest.clearAllMocks());

test('the overview shows the sales, what to handle and the latest orders', async () => {
  await open(shopSales());

  expect(await screen.findByText('Ostatnie 30 dni')).toBeTruthy();
  expect(screen.getByText('320,00 zł')).toBeTruthy();
  expect(screen.getByText('3 zamówienia, średnio 106,67 zł')).toBeTruthy();
  // 320 against 250 before.
  expect(screen.getByText('+28% względem poprzednich 30 dni')).toBeTruthy();
  expect(screen.getByText('Do obsłużenia')).toBeTruthy();
  expect(screen.getByText('opłacone, do wysłania')).toBeTruthy();
  expect(screen.getByText('Nr 1042')).toBeTruthy();
  expect(screen.getByText(/^Anna N\., 2 szt\., /)).toBeTruthy();
  // Once among the orders to handle, once on the order.
  expect(screen.getAllByText('W realizacji')).toHaveLength(2);

  await fireEvent.press(screen.getByRole('button', { name: 'Panel WordPressa' }));
  expect(router.push).toHaveBeenCalledWith({
    pathname: '/shops/[id]/settings',
    params: { id: '7', section: 'reczne' },
  });
});

test('the orders open from the overview', async () => {
  await open(shopSales());

  await fireEvent.press(await screen.findByRole('button', { name: /Zamówienie nr 1041/ }));
  expect(router.push).toHaveBeenLastCalledWith({
    pathname: '/shops/[id]/orders/[orderId]',
    params: { id: '7', orderId: '41' },
  });

  await fireEvent.press(screen.getByRole('button', { name: 'Pokaż do obsłużenia' }));
  expect(router.push).toHaveBeenLastCalledWith({ pathname: '/shops/[id]/orders', params: { id: '7', status: 'new' } });

  await fireEvent.press(screen.getByRole('button', { name: 'Wszystkie zamówienia' }));
  expect(router.push).toHaveBeenLastCalledWith({ pathname: '/shops/[id]/orders', params: { id: '7' } });
});

test('a bar tells its day, and the table has the same numbers', async () => {
  await open(shopSales());

  const day = await screen.findByRole('button', { name: 'wt., 3 listopada: 200,00 zł, 1 zamówienie' });
  await fireEvent(day, 'pressIn');
  expect(screen.getByText('wt., 3 listopada: 200,00 zł, 1 zamówienie')).toBeTruthy();
  // The scale ends on the biggest day, rounded.
  expect(screen.getByText('200 zł')).toBeTruthy();

  await fireEvent.press(screen.getByRole('radio', { name: 'Tabela' }));
  expect(screen.queryByRole('button', { name: /3 listopada/ })).toBeNull();
  expect(screen.getByText('wt., 3 listopada')).toBeTruthy();
  // The day's row, and the order of that day in the list below.
  expect(screen.getAllByText('200,00 zł')).toHaveLength(2);
});

test('the first read is waited for', async () => {
  jest.useFakeTimers();
  try {
    await open([shopSales({ synced_at: null, refreshing: true }), shopSales()]);
    expect(await screen.findByText('Za chwilę zobaczysz sprzedaż')).toBeTruthy();

    await jest.advanceTimersByTimeAsync(2600);

    expect(await screen.findByText('Ostatnie 30 dni')).toBeTruthy();
  } finally {
    jest.useRealTimers();
  }
});

test('the refresh button reads the shop again', async () => {
  const { api } = await open([shopSales(), shopSales({ refreshing: true })], {
    'POST /shops/7/sales/refresh/': shopSales({ refreshing: true }),
  });

  await fireEvent.press(await screen.findByRole('button', { name: 'Odśwież' }));

  expect(api.sent('POST /shops/7/sales/refresh/')).toHaveLength(1);
  expect(await screen.findByText('Odczytujemy zamówienia ze sklepu…')).toBeTruthy();
});

test('the refresh button says so when the numbers are current', async () => {
  await open(shopSales(), { 'POST /shops/7/sales/refresh/': shopSales() });

  await fireEvent.press(await screen.findByRole('button', { name: 'Odśwież' }));

  expect(await screen.findByText('Zamówienia są aktualne, odczytaliśmy je przed chwilą.')).toBeTruthy();
});

test('a failed read keeps the last numbers and says so', async () => {
  await open(shopSales({ error: 'Nie udało się odczytać zamówień ze sklepu.' }));

  expect(await screen.findByText('Nie udało się odczytać zamówień ze sklepu.')).toBeTruthy();
  expect(screen.getByText('Poniżej jest stan z ostatniego udanego odczytu.')).toBeTruthy();
  expect(screen.getByText('320,00 zł')).toBeTruthy();
});

test('a shop without orders and a shop that is not running', async () => {
  const none = { orders: 0, revenue: '0.00', average: '0.00' };
  await open(shopSales({ today: none, last_7_days: none, last_30_days: none, recent: [] }));
  expect(await screen.findByText('Nie ma jeszcze zamówień')).toBeTruthy();

  screen.unmount();
  await open(shopSales({ available: false }));
  expect(await screen.findByText('Sklep teraz nie działa')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Odśwież' })).toBeNull();
});
