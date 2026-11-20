import { fireEvent, render, screen } from '@testing-library/react-native';

import HelpScreen from '@/app/(tabs)/help';
import AboutScreen from '@/app/about';
import HomeScreen from '@/app/index';
import { Faq, PricingFaq } from '@/constants/content';
import { useAuth } from '@/context/auth';
import { NotificationsProvider } from '@/context/notifications';
import type { Plan } from '@/lib/types';
import { mockApi } from '@/testing/api';
import { shopDetail } from '@/testing/fixtures';
import { router } from '@/testing/router';

jest.mock('expo-router', () => require('@/testing/router'));
jest.mock('@/context/auth', () => ({ useAuth: jest.fn() }));
jest.mock('@/lib/api', () => ({ ...jest.requireActual('@/lib/api'), api: jest.fn() }));

const signedIn = (user: object | null) => (useAuth as jest.Mock).mockReturnValue({ user });
const renderScreen = (screenElement: React.ReactElement) => render(screenElement, { wrapper: NotificationsProvider });

const plan = (code: string, name: string, price: string, maxShops: number): Plan => ({
  code,
  name,
  description: '',
  price,
  currency: 'PLN',
  vat_rate: '23.00',
  interval_months: 1,
  max_shops: maxShops,
  max_magento_shops: 0,
  max_staff: 5,
  shop_memory_mb: 512,
  is_featured: code === 'standard',
  features: [],
});
const PLANS = [plan('start', 'Start', '29.00', 1), plan('standard', 'Standard', '49.00', 3)];

beforeEach(() => {
  jest.clearAllMocks();
  // An array of responses is a sequence, so one list is wrapped once more.
  mockApi({ 'GET /billing/plans/': [PLANS], 'GET /shops/': [[]] });
});

test('the home page invites visitors to sign up', async () => {
  signedIn(null);
  await renderScreen(<HomeScreen />);

  expect(screen.getByText('Co dostajesz w każdym sklepie')).toBeTruthy();
  expect(screen.getByText('Cztery kroki do otwarcia')).toBeTruthy();
  expect(screen.getByText('Wybierz plan')).toBeTruthy();
  expect(await screen.findByText('Plany i ceny')).toBeTruthy();
  expect(await screen.findByText(/^Plany od 29\s+zł miesięcznie, z VAT\./)).toBeTruthy();
  expect(screen.getByText('Który system wybrać?')).toBeTruthy();
  expect(screen.getByText(PricingFaq[3].question)).toBeTruthy();
  await fireEvent.press(screen.getAllByRole('button', { name: 'Załóż konto' })[0]);
  await fireEvent.press(screen.getByRole('button', { name: 'Zobacz, jak to działa' }));

  expect(router.push).toHaveBeenCalledWith('/sign-up');
  expect(router.push).toHaveBeenCalledWith('/about');
});

test('the home page takes signed-in users to their shops', async () => {
  signedIn({ email: 'anna@example.com', shop_limit: 3, is_email_verified: true });
  await renderScreen(<HomeScreen />);

  await fireEvent.press(screen.getAllByRole('button', { name: 'Moje sklepy' })[0]);

  expect(router.push).toHaveBeenCalledWith('/shops');
});

test('a verified user without a plan picks one straight from the home page', async () => {
  signedIn({ email: 'anna@example.com', shop_limit: 0, is_email_verified: true, plan: null });
  await renderScreen(<HomeScreen />);

  const [, standard] = await screen.findAllByRole('button', { name: 'Wybierz plan' });
  await fireEvent.press(standard);

  expect(router.push).toHaveBeenCalledWith({ pathname: '/billing/checkout', params: { plan: 'standard' } });
});

test('the questions open one at a time', async () => {
  signedIn(null);
  await renderScreen(<AboutScreen />);
  const [first, second] = Faq;

  await fireEvent.press(screen.getByRole('button', { name: first.question }));
  expect(screen.getByRole('button', { name: first.question })).toHaveProp('accessibilityState', { expanded: true });

  await fireEvent.press(screen.getByRole('button', { name: second.question }));
  expect(screen.getByRole('button', { name: first.question })).toHaveProp('accessibilityState', { expanded: false });
  expect(screen.getByRole('button', { name: second.question })).toHaveProp('accessibilityState', { expanded: true });
});

test('the about page leads to the contact form', async () => {
  signedIn(null);
  await renderScreen(<AboutScreen />);

  await fireEvent.press(screen.getAllByRole('button', { name: 'Napisz do nas' })[0]);

  expect(router.push).toHaveBeenCalledWith('/contact');
});

test('help leads to the contact form too', async () => {
  signedIn({ email: 'anna@example.com' });
  await renderScreen(<HelpScreen />);

  await fireEvent.press(screen.getByRole('button', { name: 'Napisz do nas' }));

  expect(router.push).toHaveBeenCalledWith('/contact');
});

test('help walks through the panel of the first shop’s system, and the others on request', async () => {
  signedIn({ email: 'anna@example.com' });
  mockApi({
    'GET /billing/plans/': [PLANS],
    'GET /shops/': [[shopDetail({ platform: 'magento', platform_display: 'Magento' })]],
  });
  await renderScreen(<HelpScreen />);

  expect(await screen.findByText('Sklepy → Konfiguracja → Ogólne → Informacje o sklepie')).toBeTruthy();
  await fireEvent.press(screen.getByRole('radio', { name: 'PrestaShop' }));

  expect(screen.getByText('Preferencje → Kontakt → Sklepy')).toBeTruthy();
  // Without a shop there is no panel to open.
  expect(screen.queryByRole('button', { name: /otwórz w panelu sklepu/ })).toBeNull();
});
