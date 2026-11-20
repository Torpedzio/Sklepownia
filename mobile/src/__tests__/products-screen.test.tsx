import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { router, useLocalSearchParams } from 'expo-router';

import ShopProductScreen from '@/app/shops/[id]/products/[productId]';
import EditProductScreen from '@/app/shops/[id]/products/[productId]/edit';
import NewProductScreen from '@/app/shops/[id]/products/new';
import ShopProductsScreen from '@/app/shops/[id]/products';
import { NotificationsProvider } from '@/context/notifications';
import { ApiError } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import { clearQueryCache, readQuery, writeQuery } from '@/lib/query-cache';
import type { Product, ProductDetail, ShopProducts } from '@/lib/types';
import { mockApi } from '@/testing/api';
import { shopDetail } from '@/testing/fixtures';

jest.mock('expo-router', () => require('@/testing/router'));
jest.mock('@/lib/api', () => ({ ...jest.requireActual('@/lib/api'), api: jest.fn() }));
jest.mock('@/lib/confirm', () => ({ confirm: jest.fn(async () => true) }));

function product(id: string, fields: Partial<Product> = {}): Product {
  return {
    external_id: id,
    name: `Kawa ${id}`,
    sku: `KAWA-${id}`,
    price: '39.90',
    regular_price: null,
    stock: 12,
    in_stock: true,
    visible: true,
    image: '',
    has_variants: false,
    ...fields,
  };
}

function page(products: Product[], fields: Partial<ShopProducts> = {}): ShopProducts {
  return { currency: 'PLN', products, has_more: false, ...fields };
}

async function openList(routes: Record<string, unknown>, params: Record<string, string> = {}) {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: '7', ...params });
  const api = mockApi({ 'GET /shops/7/': shopDetail(), ...routes });
  await render(<ShopProductsScreen />, { wrapper: NotificationsProvider });
  return { api };
}

beforeEach(() => {
  jest.clearAllMocks();
  clearQueryCache();
});

describe('the list', () => {
  test('shows the products with price and stock and opens one', async () => {
    await openList({
      'GET /shops/7/products/': page([
        product('41', { regular_price: '49.90' }),
        product('40', { stock: 0, in_stock: false, visible: false }),
        product('39', { stock: null }),
      ]),
    });

    expect(await screen.findByText('Kawa 41')).toBeTruthy();
    expect(screen.getByText('12 szt.')).toBeTruthy();
    expect(screen.getByText('Brak')).toBeTruthy();
    expect(screen.getByText('Dostępny')).toBeTruthy();
    expect(screen.getByText('KAWA-40, ukryty w sklepie')).toBeTruthy();

    await fireEvent.press(screen.getByRole('button', { name: 'Dodaj produkt' }));
    expect(router.push).toHaveBeenCalledWith({ pathname: '/shops/[id]/products/new', params: { id: '7' } });
    await fireEvent.press(screen.getByRole('button', { name: /^Kawa 41, 39,90 zł/ }));

    expect(router.push).toHaveBeenCalledWith({
      pathname: '/shops/[id]/products/[productId]',
      params: { id: '7', productId: '41' },
    });
  });

  test('searches after a pause in typing and filters what is sold out', async () => {
    jest.useFakeTimers();
    try {
      const { api } = await openList({
        'GET /shops/7/products/': page([product('41'), product('40')]),
        'GET /shops/7/products/?q=kawa%20e': page([]),
        'GET /shops/7/products/?q=kawa%20e&stock=out_of_stock': page([product('40', { in_stock: false })]),
      });
      expect(await screen.findByText('Kawa 41')).toBeTruthy();

      await fireEvent.changeText(screen.getByLabelText('Szukaj'), 'kawa e');
      await act(async () => {
        jest.advanceTimersByTime(500);
      });
      expect(await screen.findByText('Nic nie znaleźliśmy')).toBeTruthy();

      await fireEvent.press(screen.getByRole('radio', { name: 'Brak w magazynie' }));
      expect(await screen.findByText('Kawa 40')).toBeTruthy();
      expect(api.calls.filter((call) => call.key.includes('?q=')).length).toBe(2);
    } finally {
      jest.useRealTimers();
    }
  });

  test('more products load on request, with the same filters', async () => {
    const { api } = await openList(
      {
        'GET /shops/7/products/?stock=out_of_stock': page([product('41')], { has_more: true }),
        'GET /shops/7/products/?stock=out_of_stock&page=2': page([product('12')]),
      },
      { stock: 'out_of_stock' },
    );

    await fireEvent.press(await screen.findByRole('button', { name: 'Pokaż więcej' }));

    expect(await screen.findByText('Kawa 12')).toBeTruthy();
    expect(screen.getByText('Kawa 41')).toBeTruthy();
    expect(api.calls.map((call) => call.key)).toContain('GET /shops/7/products/?stock=out_of_stock&page=2');
    expect(screen.queryByRole('button', { name: 'Pokaż więcej' })).toBeNull();
  });

  test('nothing sold out, and a shop without products', async () => {
    await openList(
      { 'GET /shops/7/products/?stock=out_of_stock': page([]), 'GET /shops/7/products/': page([]) },
      { stock: 'out_of_stock' },
    );
    expect(await screen.findByText('Niczego nie brakuje')).toBeTruthy();

    await fireEvent.press(screen.getByRole('button', { name: 'Pokaż wszystkie' }));

    expect(await screen.findByText('Sklep nie ma jeszcze produktów')).toBeTruthy();
  });

  test('a shop that does not answer says why and lets you try again', async () => {
    const { api } = await openList({
      'GET /shops/7/products/': [new ApiError(503, { detail: 'Sklep nie odpowiedział na czas.' }), page([product('41')])],
    });

    expect(await screen.findByText('Sklep nie odpowiedział na czas.')).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Spróbuj ponownie' }));
    expect(await screen.findByText('Kawa 41')).toBeTruthy();
    expect(api.calls.filter((call) => call.key === 'GET /shops/7/products/').length).toBe(2);
  });
});

function detail(fields: Partial<ProductDetail> = {}): ProductDetail {
  return {
    ...product('41'),
    currency: 'PLN',
    categories: [
      { id: '3', name: 'Kawa' },
      { id: '5', name: 'Prezenty' },
    ],
    url: 'https://palarnia.example.com/kawa-41',
    description: 'Palona jasno.\n\nZ Etiopii.',
    formatted_description: false,
    ...fields,
  };
}

async function openProduct(response: unknown, routes: Record<string, unknown> = {}, role: 'owner' | 'staff' = 'owner') {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: '7', productId: '41' });
  const api = mockApi({
    'GET /shops/7/': shopDetail({ role }),
    'GET /shops/7/products/41/': response,
    ...routes,
  });
  await render(<ShopProductScreen />, { wrapper: NotificationsProvider });
  return { api };
}

describe('the product', () => {
  test('shows the price, sale and categories', async () => {
    await openProduct(detail({ price: '29.90', regular_price: '39.90' }));

    expect(await screen.findByText('Kawa 41')).toBeTruthy();
    expect(screen.getByText('29,90 zł')).toBeTruthy();
    expect(screen.getByText('39,90 zł')).toBeTruthy();
    expect(screen.getByText('Kawa, Prezenty')).toBeTruthy();
    expect(screen.getByText('Widoczny dla klientów')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Zobacz w sklepie' })).toBeTruthy();
  });

  test('the stock is changed with the buttons and saved in the shop', async () => {
    const { api } = await openProduct(detail(), {
      'POST /shops/7/products/41/stock/': detail({ stock: 14 }),
    });

    await fireEvent.press(await screen.findByRole('button', { name: 'Dodaj sztukę' }));
    await fireEvent.press(screen.getByRole('button', { name: 'Dodaj sztukę' }));
    expect(screen.getByLabelText('Sztuk w magazynie').props.value).toBe('14');
    await fireEvent.press(screen.getByRole('button', { name: 'Zapisz stan' }));

    expect(await screen.findByText('Zapisane: 14 szt.')).toBeTruthy();
    expect(api.sent('POST /shops/7/products/41/stock/')).toEqual([{ quantity: 14 }]);
    expect(screen.getAllByText('14 szt.').length).toBeGreaterThan(0);
    // The answer is the product read again; no second read of the shop.
    expect(api.calls.filter((call) => call.key === 'GET /shops/7/products/41/').length).toBe(1);
  });

  test('a typed stock of 0 sells it out; nothing to save while unchanged', async () => {
    const { api } = await openProduct(detail(), {
      'POST /shops/7/products/41/stock/': detail({ stock: 0, in_stock: false }),
    });

    const save = await screen.findByRole('button', { name: 'Zapisz stan' });
    expect(save.props.accessibilityState.disabled).toBe(true);
    await fireEvent.changeText(screen.getByLabelText('Sztuk w magazynie'), '0');
    await fireEvent.press(screen.getByRole('button', { name: 'Zapisz stan' }));

    expect(await screen.findByText('Zapisane: produktu brak w magazynie.')).toBeTruthy();
    expect(api.sent('POST /shops/7/products/41/stock/')).toEqual([{ quantity: 0 }]);
  });

  test('variants keep their stock in the panel', async () => {
    await openProduct(detail({ has_variants: true, stock: null }));

    expect(await screen.findByText(/każdy z nich ma własny stan/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Zapisz stan' })).toBeNull();
    expect(screen.getByText('Cena od')).toBeTruthy();
  });

  test('a stock the shop refuses is reported', async () => {
    await openProduct(detail(), {
      'POST /shops/7/products/41/stock/': new ApiError(503, { detail: 'Sklep zwrócił błąd 500.' }),
    });

    await fireEvent.press(await screen.findByRole('button', { name: 'Odejmij sztukę' }));
    await fireEvent.press(screen.getByRole('button', { name: 'Zapisz stan' }));

    expect(await screen.findByText('Sklep zwrócił błąd 500.')).toBeTruthy();
    expect(screen.getByLabelText('Sztuk w magazynie').props.value).toBe('11');
  });

  test('the staff edits and shows it, but only the owner deletes it', async () => {
    const { api } = await openProduct(detail({ visible: false, url: '' }), {
      'PATCH /shops/7/products/41/': detail({ visible: true }),
    }, 'staff');

    expect(await screen.findByText(/zmienia na razie właściciel sklepu/)).toBeTruthy();
    expect(screen.getByText('Ukryty')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Zobacz w sklepie' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Usuń produkt' })).toBeNull();

    await fireEvent.press(screen.getByRole('button', { name: 'Edytuj' }));
    expect(router.push).toHaveBeenCalledWith({
      pathname: '/shops/[id]/products/[productId]/edit',
      params: { id: '7', productId: '41' },
    });
    await fireEvent.press(screen.getByRole('button', { name: 'Pokaż w sklepie' }));

    expect(await screen.findByText('Produkt jest widoczny w sklepie.')).toBeTruthy();
    expect(api.sent('PATCH /shops/7/products/41/')).toEqual([{ visible: true }]);
    expect(screen.getByRole('button', { name: 'Ukryj przed klientami' })).toBeTruthy();
  });

  test('shows the description', async () => {
    await openProduct(detail());

    expect(await screen.findByText('Palona jasno.\n\nZ Etiopii.')).toBeTruthy();
  });

  test('the owner deletes it after confirming, and the list forgets it', async () => {
    writeQuery('/shops/7/products/', page([product('41'), product('40')]));
    const { api } = await openProduct(detail(), { 'DELETE /shops/7/products/41/': null });

    await fireEvent.press(await screen.findByRole('button', { name: 'Usuń produkt' }));

    expect(confirm).toHaveBeenCalledWith(
      'Usunąć produkt?',
      expect.stringContaining('trafi do kosza'),
      'Usuń produkt',
    );
    expect(await screen.findByText('Usunięte: „Kawa 41”.')).toBeTruthy();
    expect(api.calls.map((call) => call.key)).toContain('DELETE /shops/7/products/41/');
    expect(router.back).toHaveBeenCalled();
    const list = readQuery('/shops/7/products/').data as ShopProducts;
    expect(list.products.map((item) => item.external_id)).toEqual(['40']);
  });

  test('nothing is deleted without confirming', async () => {
    (confirm as jest.Mock).mockResolvedValueOnce(false);
    const { api } = await openProduct(detail(), {}, 'owner');

    await fireEvent.press(await screen.findByRole('button', { name: 'Usuń produkt' }));

    expect(api.calls.map((call) => call.key)).not.toContain('DELETE /shops/7/products/41/');
  });
});

const CATEGORIES = {
  categories: [
    { id: '3', name: 'Kawa' },
    { id: '4', name: 'Herbata' },
    { id: '5', name: 'Prezenty' },
  ],
};

async function openForm(screenToOpen: 'new' | 'edit', routes: Record<string, unknown>) {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: '7', productId: '41' });
  const api = mockApi({
    'GET /shops/7/': shopDetail(),
    'GET /shops/7/products/': page([]),
    'GET /shops/7/products/categories/': CATEGORIES,
    ...routes,
  });
  await render(screenToOpen === 'new' ? <NewProductScreen /> : <EditProductScreen />, {
    wrapper: NotificationsProvider,
  });
  return { api };
}

describe('the product form', () => {
  test('adds a product with a price typed with a comma and opens it', async () => {
    const { api } = await openForm('new', { 'POST /shops/7/products/': detail({ external_id: '42', name: 'Kubek' }) });

    await fireEvent.changeText(await screen.findByLabelText('Nazwa'), ' Kubek ');
    await fireEvent.changeText(screen.getByLabelText('Cena brutto (zł)'), '49,9');
    await fireEvent.changeText(screen.getByLabelText('Sztuk w magazynie'), '5');
    await fireEvent.changeText(screen.getByLabelText('Opis produktu'), 'Duży.\n\nNa kawę.');
    await fireEvent.press(await screen.findByRole('checkbox', { name: 'Herbata' }));
    await fireEvent.press(screen.getByRole('checkbox', { name: 'Kawa' }));
    await fireEvent.press(screen.getByRole('button', { name: 'Dodaj produkt' }));

    expect(await screen.findByText('Dodane: „Kubek”.')).toBeTruthy();
    expect(api.sent('POST /shops/7/products/')).toEqual([
      {
        name: 'Kubek',
        price: '49.9',
        sale_price: null,
        sku: '',
        description: 'Duży.\n\nNa kawę.',
        categories: ['4', '3'],
        visible: true,
        stock: 5,
      },
    ]);
    expect(router.replace).toHaveBeenCalledWith({
      pathname: '/shops/[id]/products/[productId]',
      params: { id: '7', productId: '42' },
    });
    expect((readQuery('/shops/7/products/42/').data as ProductDetail).name).toBe('Kubek');
  });

  test('checks the name, the prices and the sale before sending', async () => {
    const { api } = await openForm('new', {});

    await fireEvent.press(await screen.findByRole('button', { name: 'Dodaj produkt' }));
    expect(screen.getByText('Podaj nazwę produktu.')).toBeTruthy();
    expect(screen.getByText('Wpisz cenę, np. 49,99.')).toBeTruthy();

    await fireEvent.changeText(screen.getByLabelText('Nazwa'), 'Kubek');
    await fireEvent.changeText(screen.getByLabelText('Cena brutto (zł)'), '20');
    await fireEvent.changeText(screen.getByLabelText('Cena promocyjna (zł)'), '25');
    await fireEvent.press(screen.getByRole('button', { name: 'Dodaj produkt' }));

    expect(screen.getByText('Cena promocyjna musi być niższa od ceny.')).toBeTruthy();
    expect(api.calls.map((call) => call.key)).not.toContain('POST /shops/7/products/');
  });

  test('an edit sends only what changed and goes back', async () => {
    const { api } = await openForm('edit', {
      'GET /shops/7/products/41/': detail({ price: '29.90', regular_price: '39.90' }),
      'PATCH /shops/7/products/41/': detail({ name: 'Kawa z Kenii' }),
    });

    expect((await screen.findByLabelText('Cena brutto (zł)')).props.value).toBe('39,90');
    expect(screen.getByLabelText('Cena promocyjna (zł)').props.value).toBe('29,90');
    expect(screen.getByText('Główna: Kawa (wybrana jako pierwsza).')).toBeTruthy();
    expect(screen.getByRole('checkbox', { name: 'Kawa' })).toHaveProp('accessibilityState', { checked: true });
    expect(screen.queryByLabelText('Sztuk w magazynie')).toBeNull();
    await fireEvent.changeText(screen.getByLabelText('Nazwa'), 'Kawa z Kenii');
    await fireEvent.changeText(screen.getByLabelText('Cena brutto (zł)'), '39,9');
    await fireEvent.changeText(screen.getByLabelText('Cena promocyjna (zł)'), '');
    await fireEvent.press(screen.getByRole('button', { name: 'Zapisz zmiany' }));

    expect(await screen.findByText('Zapisane w sklepie.')).toBeTruthy();
    expect(api.sent('PATCH /shops/7/products/41/')).toEqual([{ name: 'Kawa z Kenii', sale_price: null }]);
    expect(router.back).toHaveBeenCalled();
    expect((readQuery('/shops/7/products/41/').data as ProductDetail).name).toBe('Kawa z Kenii');
  });

  test('variants keep their prices, and a formatted description is explained', async () => {
    const { api } = await openForm('edit', {
      'GET /shops/7/products/41/': detail({ has_variants: true, formatted_description: true }),
      'PATCH /shops/7/products/41/': detail({ visible: false }),
    });

    expect(await screen.findByText(/warianty z własnymi cenami/)).toBeTruthy();
    expect(screen.queryByLabelText('Cena brutto (zł)')).toBeNull();
    expect(screen.getByText(/formatowanie zostanie/)).toBeTruthy();
    await fireEvent.press(screen.getByRole('switch', { name: 'Widoczny w sklepie' }));
    await fireEvent.press(screen.getByRole('button', { name: 'Zapisz zmiany' }));

    expect(await screen.findByText('Zapisane w sklepie.')).toBeTruthy();
    expect(api.sent('PATCH /shops/7/products/41/')).toEqual([{ visible: false }]);
  });

  test("the shop's refusal is shown under the field and the form stays", async () => {
    await openForm('edit', {
      'GET /shops/7/products/41/': detail({ price: '29.90', regular_price: '39.90' }),
      'PATCH /shops/7/products/41/': new ApiError(400, { sale_price: ['Cena promocyjna musi być niższa od ceny.'] }),
    });

    await fireEvent.changeText(await screen.findByLabelText('Cena promocyjna (zł)'), '35');
    await fireEvent.press(screen.getByRole('button', { name: 'Zapisz zmiany' }));

    expect((await screen.findAllByText('Cena promocyjna musi być niższa od ceny.')).length).toBeGreaterThan(0);
    expect(router.back).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Cena promocyjna (zł)').props.value).toBe('35');
  });
});
