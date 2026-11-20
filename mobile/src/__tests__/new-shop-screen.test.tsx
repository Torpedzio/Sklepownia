import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { router } from 'expo-router';

import NewShopScreen from '@/app/shops/new';
import { useAuth } from '@/context/auth';
import { NotificationsProvider } from '@/context/notifications';
import { ApiError } from '@/lib/api';
import type { FormOptions } from '@/lib/types';
import { mockApi, type Routes } from '@/testing/api';
import { shopDetail } from '@/testing/fixtures';

jest.mock('expo-router', () => require('@/testing/router'));
jest.mock('@/lib/api', () => ({ ...jest.requireActual('@/lib/api'), api: jest.fn() }));
jest.mock('@/context/auth', () => ({ useAuth: jest.fn() }));

const options: FormOptions = {
  platforms: [
    { value: 'woocommerce', label: 'WooCommerce', description: 'WordPress z wtyczką WooCommerce.', available: true, note: '' },
    { value: 'prestashop', label: 'PrestaShop', description: 'Samodzielny system sklepowy.', available: true, note: '' },
    {
      value: 'magento',
      label: 'Magento',
      description: 'Dla dużych katalogów.',
      available: false,
      note: 'Sklepy Magento są w planach Standard i Biznes. Plan Start ich nie obejmuje.',
    },
  ],
  industries: [
    { value: 'food', label: 'Żywność i napoje' },
    { value: 'books', label: 'Książki i multimedia' },
  ],
  languages: [{ value: 'pl_PL', label: 'Polski' }],
  currencies: [{ value: 'PLN', label: 'Złoty (PLN)' }],
  countries: [{ value: 'PL', label: 'Polska' }],
  templates: [
    { slug: 'storefront', platform: 'woocommerce', name: 'Storefront', description: 'Prosty', preview_image_url: '' },
    { slug: 'hummingbird', platform: 'prestashop', name: 'Hummingbird', description: 'Nowy', preview_image_url: '' },
    { slug: 'classic', platform: 'prestashop', name: 'Classic', description: 'Klasyczny', preview_image_url: '' },
  ],
  category_count: { min: 1, max: 20, default: 5 },
  base_domain: 'localhost',
};

async function open(routes: Routes = {}, shopCount = 0, plan: string | null = 'Standard') {
  (useAuth as jest.Mock).mockReturnValue({ user: { shop_limit: 3, plan } });
  const api = mockApi({
    'GET /shops/form-options/': options,
    'GET /shops/': [Array.from({ length: shopCount }, (_, id) => ({ id, is_test: false, role: 'owner' }))],
    ...routes,
  });
  await render(<NewShopScreen />, { wrapper: NotificationsProvider });
  return { api };
}

beforeEach(() => jest.clearAllMocks());

test('the address follows the name until edited, and is checked', async () => {
  await open({
    'GET /shops/check-slug/?slug=pracownia-ceramiki': { slug: 'pracownia-ceramiki', available: true, reason: null },
  });

  await fireEvent.changeText(await screen.findByPlaceholderText('np. Pracownia Ceramiki'), 'Pracownia Ceramiki');

  expect(screen.getByText('pracownia-ceramiki.localhost')).toBeTruthy();
  expect(await screen.findByText('✓ Adres jest wolny')).toBeTruthy();
});

test('a taken address says why', async () => {
  await open({
    'GET /shops/check-slug/?slug=kawa': { slug: 'kawa', available: false, reason: 'Ten adres jest już zajęty.' },
  });

  await fireEvent.changeText(await screen.findByPlaceholderText('np. Pracownia Ceramiki'), 'Kawa');

  expect(await screen.findByText('Ten adres jest już zajęty.')).toBeTruthy();
});

test('the shop is created with the chosen options and opened', async () => {
  const { api } = await open({
    'GET /shops/check-slug/?slug=ksiegarnia': { slug: 'ksiegarnia', available: true, reason: null },
    'POST /shops/': shopDetail({ id: 9, name: 'Księgarnia', status: 'pending' }),
  });

  await fireEvent.changeText(await screen.findByPlaceholderText('np. Pracownia Ceramiki'), 'Księgarnia');
  await fireEvent.press(screen.getByRole('radio', { name: 'Książki i multimedia' }));
  await fireEvent.press(screen.getByRole('button', { name: 'Załóż sklep' }));

  expect(api.sent('POST /shops/')).toEqual([
    expect.objectContaining({
      name: 'Księgarnia',
      slug: 'ksiegarnia',
      industry: 'books',
      platform: 'woocommerce',
      template: 'storefront',
      category_count: 5,
    }),
  ]);
  await waitFor(() => expect(router.push).toHaveBeenCalledWith({ pathname: '/shops/[id]', params: { id: 9 } }));
});

test('each platform offers its own themes', async () => {
  const { api } = await open({
    'GET /shops/check-slug/?slug=kawa': { slug: 'kawa', available: true, reason: null },
    'POST /shops/': shopDetail({ id: 9, status: 'pending' }),
  });

  expect(await screen.findByRole('radio', { name: /Storefront/ })).toBeTruthy();
  expect(screen.queryByRole('radio', { name: /Hummingbird/ })).toBeNull();

  await fireEvent.press(screen.getByRole('radio', { name: /PrestaShop/ }));

  expect(screen.queryByRole('radio', { name: /Storefront/ })).toBeNull();
  expect(screen.getByRole('radio', { name: /Hummingbird/ })).toBeSelected();
  await fireEvent.press(screen.getByRole('radio', { name: /Classic/ }));
  await fireEvent.changeText(screen.getByPlaceholderText('np. Pracownia Ceramiki'), 'Kawa');
  await fireEvent.press(screen.getByRole('radio', { name: 'Żywność i napoje' }));
  await fireEvent.press(screen.getByRole('button', { name: 'Załóż sklep' }));

  expect(api.sent('POST /shops/')).toEqual([expect.objectContaining({ platform: 'prestashop', template: 'classic' })]);
});

test('a platform the plan does not allow says why and cannot be chosen', async () => {
  await open();

  const magento = await screen.findByRole('radio', { name: /^Magento/ });
  expect(magento).toHaveProp('accessibilityState', { selected: false, disabled: true });
  expect(screen.getByText('Sklepy Magento są w planach Standard i Biznes. Plan Start ich nie obejmuje.')).toBeTruthy();

  await fireEvent.press(magento);
  expect(screen.getByRole('radio', { name: /^WooCommerce/ })).toHaveProp('accessibilityState', {
    selected: true,
    disabled: false,
  });
});

test('errors from the server show under the fields', async () => {
  await open({
    'GET /shops/check-slug/?slug=kawa': { slug: 'kawa', available: true, reason: null },
    'POST /shops/': new ApiError(400, { slug: ['Ten adres jest już zajęty.'] }),
  });

  await fireEvent.changeText(await screen.findByPlaceholderText('np. Pracownia Ceramiki'), 'Kawa');
  await fireEvent.press(screen.getByRole('radio', { name: 'Żywność i napoje' }));
  await fireEvent.press(screen.getByRole('button', { name: 'Załóż sklep' }));

  expect(await screen.findByText('Ten adres jest już zajęty.')).toBeTruthy();
  expect(router.push).not.toHaveBeenCalled();
});

test('the form waits for a name and an industry', async () => {
  await open();

  expect(await screen.findByRole('button', { name: 'Załóż sklep' })).toBeDisabled();
});

test('at the shop limit there is no form', async () => {
  await open({}, 3);

  expect(await screen.findByText('Masz już 3 sklepy')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Załóż sklep' })).toBeNull();
});

test('without a plan the form sends you to choose one', async () => {
  await open({}, 0, null);

  expect(await screen.findByText('Najpierw wybierz plan')).toBeTruthy();
  await fireEvent.press(screen.getByRole('button', { name: 'Wybierz plan' }));
  expect(router.push).toHaveBeenCalledWith('/billing/checkout');
});

test('test shops do not count towards the limit', async () => {
  (useAuth as jest.Mock).mockReturnValue({ user: { shop_limit: 1, plan: 'Standard' } });
  mockApi({ 'GET /shops/form-options/': options, 'GET /shops/': [[{ id: 1, is_test: true, role: 'owner' }]] });

  await render(<NewShopScreen />, { wrapper: NotificationsProvider });

  expect(await screen.findByText('Opisz swój sklep')).toBeTruthy();
});
