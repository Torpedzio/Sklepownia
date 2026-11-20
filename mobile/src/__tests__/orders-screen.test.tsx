import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { router, useLocalSearchParams } from 'expo-router';

import ShopOrderScreen from '@/app/shops/[id]/orders/[orderId]';
import ShopOrdersScreen from '@/app/shops/[id]/orders';
import { NotificationsProvider } from '@/context/notifications';
import { ApiError } from '@/lib/api';
import type { ShopOrder, ShopOrderDetail, ShopOrders } from '@/lib/types';
import { mockApi } from '@/testing/api';
import { shopDetail } from '@/testing/fixtures';

jest.mock('expo-router', () => require('@/testing/router'));
jest.mock('@/lib/api', () => ({ ...jest.requireActual('@/lib/api'), api: jest.fn() }));

function order(id: string, fields: Partial<ShopOrder> = {}): ShopOrder {
  return {
    external_id: id,
    number: `10${id}`,
    status: 'new',
    status_display: 'Nowe',
    total: '120.00',
    currency: 'PLN',
    items: 2,
    customer: 'Anna N.',
    placed_at: '2026-11-18T09:15:00Z',
    ...fields,
  };
}

function page(orders: ShopOrder[], fields: Partial<ShopOrders> = {}): ShopOrders {
  return {
    available: true,
    synced_at: '2026-11-20T10:00:00Z',
    refreshing: false,
    error: '',
    counts: { new: 1, processing: 1, completed: 3, cancelled: 0, unfinished: 0 },
    orders,
    has_more: false,
    ...fields,
  };
}

async function openList(routes: Record<string, unknown>, params: Record<string, string> = {}) {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: '7', ...params });
  const api = mockApi({ 'GET /shops/7/': shopDetail(), ...routes });
  await render(<ShopOrdersScreen />, { wrapper: NotificationsProvider });
  return { api };
}

beforeEach(() => jest.clearAllMocks());

describe('the list', () => {
  test('shows the orders with counts per status and opens one', async () => {
    await openList({ 'GET /shops/7/orders/': page([order('41'), order('40', { status: 'completed' })]) });

    expect(await screen.findByText('Nr 1041')).toBeTruthy();
    expect(screen.getByRole('radio', { name: 'Wszystkie (5)' })).toBeTruthy();
    expect(screen.getByRole('radio', { name: 'Zrealizowane (3)' })).toBeTruthy();

    await fireEvent.press(screen.getByRole('button', { name: /Zamówienie nr 1041/ }));

    expect(router.push).toHaveBeenCalledWith({
      pathname: '/shops/[id]/orders/[orderId]',
      params: { id: '7', orderId: '41' },
    });
  });

  test('filters by status, starting from the one in the link', async () => {
    const { api } = await openList(
      {
        'GET /shops/7/orders/?status=new': page([order('41')]),
        'GET /shops/7/orders/?status=completed': page([], { counts: { ...page([]).counts, completed: 0 } }),
        'GET /shops/7/orders/': page([order('41'), order('38', { status: 'processing' })]),
      },
      { status: 'new' },
    );

    expect(await screen.findByText('Nr 1041')).toBeTruthy();
    await fireEvent.press(screen.getByRole('radio', { name: /^Zrealizowane/ }));

    expect(await screen.findByText('Brak zamówień w tym statusie')).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Pokaż wszystkie' }));
    expect(await screen.findByText('Nr 1038')).toBeTruthy();
    expect(api.calls.map((call) => call.key)).toContain('GET /shops/7/orders/?status=completed');
  });

  test('searches after a pause in typing', async () => {
    jest.useFakeTimers();
    try {
      const { api } = await openList({
        'GET /shops/7/orders/': page([order('41'), order('40')]),
        'GET /shops/7/orders/?q=jan%20k': page([]),
      });
      expect(await screen.findByText('Nr 1041')).toBeTruthy();

      await fireEvent.changeText(screen.getByLabelText('Szukaj'), 'jan k');
      await act(async () => {
        jest.advanceTimersByTime(500);
      });

      expect(await screen.findByText('Nic nie znaleźliśmy')).toBeTruthy();
      expect(api.calls.filter((call) => call.key.includes('?q=')).length).toBe(1);
    } finally {
      jest.useRealTimers();
    }
  });

  test('older orders load on request, with the same filters', async () => {
    const { api } = await openList(
      {
        'GET /shops/7/orders/?status=new': page([order('41')], { has_more: true }),
        'GET /shops/7/orders/?status=new&before=41': page([order('39')]),
      },
      { status: 'new' },
    );

    await fireEvent.press(await screen.findByRole('button', { name: 'Pokaż starsze' }));

    expect(await screen.findByText('Nr 1039')).toBeTruthy();
    expect(screen.getByText('Nr 1041')).toBeTruthy();
    expect(api.calls.map((call) => call.key)).toContain('GET /shops/7/orders/?status=new&before=41');
    expect(screen.queryByRole('button', { name: 'Pokaż starsze' })).toBeNull();
  });

  test('a shop without orders yet', async () => {
    await openList({
      'GET /shops/7/orders/': page([], { counts: { new: 0, processing: 0, completed: 0, cancelled: 0, unfinished: 0 } }),
    });
    expect(await screen.findByText('Nie ma jeszcze zamówień')).toBeTruthy();
  });
});

function detail(fields: Partial<ShopOrderDetail> = {}): ShopOrderDetail {
  const address = {
    name: 'Jan Kowalski',
    company: '',
    lines: ['ul. Polna 3'],
    postcode: '00-950',
    city: 'Warszawa',
    country: 'Polska',
    phone: '+48 600 100 200',
  };
  return {
    external_id: '41',
    number: '1041',
    status: 'processing',
    status_display: 'W realizacji',
    currency: 'PLN',
    products_total: '100.00',
    shipping_total: '14.99',
    discount_total: '10.00',
    total: '104.99',
    payment_method: 'Przelew bankowy',
    shipping_method: 'Kurier DPD',
    customer_name: 'Jan Kowalski',
    email: 'jan@example.com',
    phone: '+48 600 100 200',
    billing: address,
    shipping: address,
    lines: [{ name: 'Kubek', sku: 'KUB-1', quantity: 2, price: '50.00', total: '100.00' }],
    customer_note: 'Proszę o kontakt przed wysyłką.',
    placed_at: '2026-11-18T09:15:00Z',
    ...fields,
  };
}

async function openOrder(response: unknown, role: 'owner' | 'staff' = 'owner') {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: '7', orderId: '41' });
  const api = mockApi({ 'GET /shops/7/': shopDetail({ role }), 'GET /shops/7/orders/41/': response });
  await render(<ShopOrderScreen />, { wrapper: NotificationsProvider });
  return { api };
}

describe('the details', () => {
  test('show the products, totals, customer and addresses', async () => {
    await openOrder(detail());

    expect(await screen.findByText('Nr 1041')).toBeTruthy();
    expect(screen.getByText('W realizacji')).toBeTruthy();
    expect(screen.getByText('KUB-1, 2 × 50,00 zł')).toBeTruthy();
    expect(screen.getByText('−10,00 zł')).toBeTruthy();
    expect(screen.getByText('104,99 zł')).toBeTruthy();
    expect(screen.getByText('jan@example.com')).toBeTruthy();
    expect(screen.getByText('Proszę o kontakt przed wysyłką.')).toBeTruthy();
    expect(screen.getByText('Kurier DPD')).toBeTruthy();
    expect(screen.getByText('00-950 Warszawa')).toBeTruthy();
    expect(screen.getByText('Dane do faktury takie jak adres dostawy.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Napisz e-mail' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Zadzwoń' })).toBeTruthy();
  });

  test('separate billing data are shown apart, and no discount line without a discount', async () => {
    const billing = { ...detail().billing!, company: 'Kowalski sp. z o.o.', lines: ['ul. Krótka 2'] };
    await openOrder(detail({ billing, discount_total: '0.00', customer_note: '' }));

    expect(await screen.findByText('Dane do faktury')).toBeTruthy();
    expect(screen.getByText('Kowalski sp. z o.o.')).toBeTruthy();
    expect(screen.queryByText('Rabat')).toBeNull();
    expect(screen.queryByText('Uwagi klienta')).toBeNull();
  });

  test('an unreachable shop says why and lets you try again', async () => {
    const { api } = await openOrder(new ApiError(503, { detail: 'Sklep nie odpowiedział na czas.' }));

    expect(await screen.findByText('Sklep nie odpowiedział na czas.')).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Spróbuj ponownie' }));
    expect(api.calls.filter((call) => call.key === 'GET /shops/7/orders/41/').length).toBe(2);
  });

  test('the staff is not sent to the panel', async () => {
    await openOrder(detail(), 'staff');
    expect(await screen.findByText(/nigdzie ich nie zapisujemy\.$/)).toBeTruthy();
    expect(screen.queryByText(/w panelu sklepu/)).toBeNull();
  });
});
