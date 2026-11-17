import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { router, useLocalSearchParams } from 'expo-router';

import BillingScreen from '@/app/billing';
import ChangePlanScreen from '@/app/billing/change';
import CheckoutScreen from '@/app/billing/checkout';
import PaymentReturnScreen from '@/app/billing/return';
import PricingScreen from '@/app/pricing';
import { useAuth } from '@/context/auth';
import { NotificationsProvider } from '@/context/notifications';
import { ApiError } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import { goToPayment } from '@/lib/payment';
import type { BillingOverview, BillingProfile, Payment, Plan, PlanChangePreview, Subscription } from '@/lib/types';
import { mockApi } from '@/testing/api';

jest.mock('expo-router', () => require('@/testing/router'));
jest.mock('@/lib/api', () => ({ ...jest.requireActual('@/lib/api'), api: jest.fn() }));
jest.mock('@/context/auth', () => ({ useAuth: jest.fn() }));
jest.mock('@/lib/confirm', () => ({ confirm: jest.fn(async () => true) }));
jest.mock('@/lib/payment', () => ({
  paymentReturnUrl: () => 'http://localhost:8081/billing/return',
  goToPayment: jest.fn(async () => {}),
}));

const standard: Plan = {
  code: 'standard',
  name: 'Standard',
  description: 'Dla małego sklepu',
  price: '49.00',
  currency: 'PLN',
  vat_rate: '23.00',
  interval_months: 1,
  max_shops: 3,
  max_magento_shops: 1,
  shop_memory_mb: 512,
  is_featured: true,
  features: ['Do 3 sklepów'],
};
const start: Plan = {
  ...standard,
  code: 'start',
  name: 'Start',
  price: '29.00',
  max_shops: 1,
  max_magento_shops: 0,
  is_featured: false,
};
const business: Plan = {
  ...standard,
  code: 'business',
  name: 'Biznes',
  price: '99.00',
  max_shops: 10,
  max_magento_shops: 5,
  shop_memory_mb: 1024,
  is_featured: false,
};

const woo = (id: number, name: string) => ({
  id,
  name,
  status: 'active' as const,
  platform: 'woocommerce' as const,
  platform_display: 'WooCommerce',
});

const person: BillingProfile = {
  kind: 'individual',
  full_name: 'Anna Nowak',
  company_name: '',
  tax_id: '',
  street: 'Kwiatowa 1',
  postal_code: '00-001',
  city: 'Warszawa',
  country: 'PL',
};

function subscription(overrides: Partial<Subscription> = {}): Subscription {
  return {
    plan: standard,
    status: 'active',
    status_display: 'Aktywny',
    current_period_start: '2026-11-05T10:00:00Z',
    current_period_end: '2026-12-05T10:00:00Z',
    cancel_at_period_end: false,
    next_attempt_at: null,
    card: { brand: 'Visa', tail: '4242', expiry: '1230' },
    credit: '0.00',
    allows_new_shops: true,
    ...overrides,
  };
}

function payment(overrides: Partial<Payment> = {}): Payment {
  return {
    id: 5,
    kind: 'initial',
    kind_display: 'Pierwsza płatność',
    status: 'paid',
    status_display: 'Opłacona',
    plan_name: 'Standard',
    amount: '49.00',
    credit_used: '0.00',
    currency: 'PLN',
    gateway_title: 'TR-1',
    period_start: '2026-11-05T10:00:00Z',
    period_end: '2026-12-05T10:00:00Z',
    error: '',
    created_at: '2026-11-05T10:00:00Z',
    paid_at: '2026-11-05T10:01:00Z',
    ...overrides,
  };
}

const overview = (overrides: Partial<BillingOverview> = {}): BillingOverview => ({
  subscription: null,
  profile: null,
  payments: [],
  ...overrides,
});

const refreshUser = jest.fn(async () => {});
function signedIn(user: object | null) {
  (useAuth as jest.Mock).mockReturnValue({ user, refreshUser });
}
const verified = { email: 'anna@example.com', is_email_verified: true, plan: null };
const renderScreen = (element: React.ReactElement) => render(element, { wrapper: NotificationsProvider });

beforeEach(() => jest.clearAllMocks());

describe('pricing', () => {
  test.each([
    [null, 'Załóż konto', '/sign-up'],
    [{ ...verified, is_email_verified: false }, 'Potwierdź e-mail, żeby wybrać plan', '/verify-email'],
    [{ ...verified, plan: 'Standard' }, 'Plan i płatności', '/billing'],
  ])('leads each visitor onward (%#)', async (user, button, target) => {
    signedIn(user);
    mockApi({ 'GET /billing/plans/': [[start, standard, business]] });
    await renderScreen(<PricingScreen />);

    const buttons = await screen.findAllByRole('button', { name: button });
    expect(buttons).toHaveLength(3);
    await fireEvent.press(buttons[0]);

    expect(router.push).toHaveBeenCalledWith(target);
  });

  test('a verified user without a plan picks one of three, the usual choice marked', async () => {
    signedIn(verified);
    mockApi({ 'GET /billing/plans/': [[start, standard, business]] });
    await renderScreen(<PricingScreen />);

    expect(await screen.findByText('29,00 zł')).toBeTruthy();
    expect(screen.getByText('99,00 zł')).toBeTruthy();
    expect(screen.getAllByText('Polecany')).toHaveLength(1);
    await fireEvent.press(screen.getAllByRole('button', { name: 'Wybierz plan' })[2]);

    expect(router.push).toHaveBeenCalledWith({ pathname: '/billing/checkout', params: { plan: 'business' } });
  });
});

describe('checkout', () => {
  async function open(data: BillingOverview = overview(), routes = {}) {
    signedIn(verified);
    (useLocalSearchParams as jest.Mock).mockReturnValue({ plan: 'standard' });
    const api = mockApi({ 'GET /billing/plans/': [[start, standard, business]], 'GET /billing/': data, ...routes });
    await renderScreen(<CheckoutScreen />);
    return { api };
  }

  test('switching the plan changes the amount to pay', async () => {
    await open(overview({ profile: person }));

    await fireEvent.press(await screen.findByRole('radio', { name: /^Biznes/ }));

    expect(screen.getByRole('button', { name: 'Zapłać kartą 99,00 zł' })).toBeTruthy();
  });

  test('without a plan in the link the usual choice is picked', async () => {
    signedIn(verified);
    (useLocalSearchParams as jest.Mock).mockReturnValue({});
    mockApi({ 'GET /billing/plans/': [[start, standard, business]], 'GET /billing/': overview() });
    await renderScreen(<CheckoutScreen />);

    expect(await screen.findByRole('radio', { name: /^Standard, polecany/ })).toHaveProp('accessibilityState', {
      selected: true,
    });
  });

  test('pays once the terms are accepted and a person agrees to start now', async () => {
    const checkout = { payment: payment({ status: 'pending' }), redirect_url: 'https://secure.sandbox.tpay.com/x' };
    const { api } = await open(overview({ profile: person }), {
      'PUT /billing/profile/': person,
      'POST /billing/checkout/': checkout,
    });

    const pay = await screen.findByRole('button', { name: 'Zapłać kartą 49,00 zł' });
    expect(pay).toBeDisabled();
    await fireEvent.press(screen.getByRole('switch', { name: 'Akceptuję regulamin usługi' }));
    expect(pay).toBeDisabled();
    await fireEvent.press(screen.getByRole('switch', { name: 'Chcę, żeby usługa zaczęła działać od razu' }));
    await fireEvent.press(pay);

    expect(api.sent('PUT /billing/profile/')).toEqual([person]);
    expect(api.sent('POST /billing/checkout/')).toEqual([
      {
        plan: 'standard',
        return_url: 'http://localhost:8081/billing/return',
        accept_terms: true,
        immediate_start_consent: true,
      },
    ]);
    await waitFor(() => expect(goToPayment).toHaveBeenCalledWith(checkout));
  });

  test('a company gives its name and NIP and needs no consent to start', async () => {
    const { api } = await open(overview(), {
      'PUT /billing/profile/': new ApiError(400, { tax_id: ['Ten NIP ma błąd. Sprawdź, czy nie brakuje cyfry.'] }),
    });

    await fireEvent.press(await screen.findByRole('radio', { name: 'Firma' }));
    expect(screen.queryByRole('switch', { name: 'Chcę, żeby usługa zaczęła działać od razu' })).toBeNull();
    await fireEvent.changeText(screen.getByLabelText('Nazwa firmy'), 'Palarnia sp. z o.o.');
    await fireEvent.changeText(screen.getByLabelText('NIP'), '1234567890');
    await fireEvent.changeText(screen.getByLabelText('Osoba do kontaktu'), 'Anna Nowak');
    await fireEvent.press(screen.getByRole('switch', { name: 'Akceptuję regulamin usługi' }));
    await fireEvent.press(screen.getByRole('button', { name: 'Zapłać kartą 49,00 zł' }));

    expect(api.sent('PUT /billing/profile/')[0]).toMatchObject({
      kind: 'company',
      company_name: 'Palarnia sp. z o.o.',
      tax_id: '1234567890',
    });
    expect(await screen.findByText('Ten NIP ma błąd. Sprawdź, czy nie brakuje cyfry.')).toBeTruthy();
    expect(screen.getByText('Popraw zaznaczone dane do faktury.')).toBeTruthy();
    expect(api.sent('POST /billing/checkout/')).toEqual([]);
  });

  test('a gateway problem is reported and the button works again', async () => {
    await open(overview({ profile: { ...person, kind: 'company', company_name: 'Firma', tax_id: '5260001246' } }), {
      'PUT /billing/profile/': person,
      'POST /billing/checkout/': new ApiError(502, { detail: 'Nie udało się połączyć z operatorem płatności.' }),
    });

    await fireEvent.press(await screen.findByRole('switch', { name: 'Akceptuję regulamin usługi' }));
    await fireEvent.press(screen.getByRole('button', { name: 'Zapłać kartą 49,00 zł' }));

    expect(await screen.findByText('Nie udało się połączyć z operatorem płatności.')).toBeTruthy();
    expect(goToPayment).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Zapłać kartą 49,00 zł' })).toBeEnabled();
  });

  test('with a plan already there is nothing to buy', async () => {
    await open(overview({ subscription: subscription() }));

    expect(await screen.findByText('Masz już plan Standard')).toBeTruthy();
  });
});

describe('return from the payment page', () => {
  function returnTo(paymentId: string | undefined) {
    (useLocalSearchParams as jest.Mock).mockReturnValue({ payment: paymentId });
    signedIn({ ...verified, plan: null });
  }

  test('a paid payment activates the plan and leads to a new shop', async () => {
    returnTo('5');
    mockApi({ 'GET /billing/payments/5/': payment() });
    await renderScreen(<PaymentReturnScreen />);

    expect(await screen.findByText('Plan Standard jest aktywny')).toBeTruthy();
    await waitFor(() => expect(refreshUser).toHaveBeenCalled());
    await fireEvent.press(screen.getByRole('button', { name: 'Załóż sklep' }));
    expect(router.push).toHaveBeenCalledWith('/shops/new');
  });

  test('after paying the shop list is one tap away, not a step back to the gateway', async () => {
    returnTo('5');
    mockApi({ 'GET /billing/payments/5/': payment() });
    await renderScreen(<PaymentReturnScreen />);

    await fireEvent.press(await screen.findByRole('button', { name: 'Przejdź do sklepów' }));
    expect(router.dismissTo).toHaveBeenCalledWith('/shops');
    expect(router.back).not.toHaveBeenCalled();
  });

  test('waits while the payment is pending', async () => {
    returnTo('5');
    mockApi({ 'GET /billing/payments/5/': payment({ status: 'pending' }) });
    await renderScreen(<PaymentReturnScreen />);

    expect(await screen.findByText('Sprawdzamy płatność…')).toBeTruthy();
    expect(refreshUser).not.toHaveBeenCalled();
  });

  test('a declined payment can be tried again', async () => {
    returnTo('5');
    mockApi({ 'GET /billing/payments/5/': payment({ status: 'failed', error: 'Karta odrzucona.' }) });
    await renderScreen(<PaymentReturnScreen />);

    expect(await screen.findByText(/Karta odrzucona\. Nie pobraliśmy pieniędzy\./)).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Spróbuj ponownie' }));
    expect(router.push).toHaveBeenCalledWith('/billing/checkout');
    await fireEvent.press(screen.getByRole('button', { name: 'Przejdź do sklepów' }));
    expect(router.dismissTo).toHaveBeenCalledWith('/shops');
  });

  test('without a payment it goes to the billing page', async () => {
    returnTo(undefined);
    await renderScreen(<PaymentReturnScreen />);

    expect(router.replace).toHaveBeenCalledWith('/billing');
  });
});

describe('plan and payments', () => {
  async function open(data: BillingOverview, routes = {}) {
    signedIn({ ...verified, plan: 'Standard' });
    const api = mockApi({ 'GET /billing/': data, ...routes });
    await renderScreen(<BillingScreen />);
    return { api };
  }

  test('without a plan it offers one', async () => {
    await open(overview());

    expect(await screen.findByText('Nie masz jeszcze planu')).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Wybierz plan' }));
    expect(router.push).toHaveBeenCalledWith('/billing/checkout');
  });

  test('shows the next payment, the card and the history', async () => {
    await open(overview({ subscription: subscription(), profile: person, payments: [payment()] }));

    expect(await screen.findByText(/Następna płatność 5 grudnia 2026: 49,00 zł\./)).toBeTruthy();
    expect(screen.getByText('Visa •••• 4242')).toBeTruthy();
    expect(screen.getByText('Pierwsza płatność, plan Standard')).toBeTruthy();
    expect(screen.getByText('Anna Nowak')).toBeTruthy();
  });

  test('cancelling asks first and keeps the plan until the period ends', async () => {
    const { api } = await open(overview({ subscription: subscription() }), {
      'POST /billing/subscription/cancel/': subscription({ cancel_at_period_end: true }),
    });

    await fireEvent.press(await screen.findByRole('button', { name: 'Anuluj plan' }));

    expect(confirm).toHaveBeenCalledWith('Anulować plan?', expect.stringContaining('5 grudnia 2026'), 'Anuluj plan');
    expect(api.sent('POST /billing/subscription/cancel/')).toHaveLength(1);
    expect(await screen.findByText('Plan nie będzie odnawiany.')).toBeTruthy();
    expect(refreshUser).toHaveBeenCalled();
  });

  test('a cancelled plan can be resumed', async () => {
    const { api } = await open(overview({ subscription: subscription({ cancel_at_period_end: true }) }), {
      'POST /billing/subscription/resume/': subscription(),
    });

    expect(await screen.findByText('Plan działa do 5 grudnia 2026. Nie odnowimy go.')).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Wznów plan' }));

    expect(api.sent('POST /billing/subscription/resume/')).toHaveLength(1);
  });

  test('a failed renewal says when it is tried again', async () => {
    await open(
      overview({
        subscription: subscription({
          status: 'past_due',
          status_display: 'Zaległa płatność',
          next_attempt_at: '2026-12-06T10:00:00Z',
        }),
      }),
    );

    expect(await screen.findByText(/Spróbujemy ponownie 6 grudnia 2026\./)).toBeTruthy();
  });

  test('invoice details can be changed', async () => {
    const { api } = await open(overview({ subscription: subscription(), profile: person }), {
      'PUT /billing/profile/': { ...person, city: 'Kraków' },
    });

    await fireEvent.press(await screen.findByRole('button', { name: 'Zmień dane' }));
    await fireEvent.changeText(screen.getByLabelText('Miejscowość'), 'Kraków');
    await fireEvent.press(screen.getByRole('button', { name: 'Zapisz' }));

    expect(api.sent('PUT /billing/profile/')).toEqual([{ ...person, city: 'Kraków' }]);
    expect(await screen.findByText('Zapisano dane do faktury.')).toBeTruthy();
  });
});

describe('changing the plan', () => {
  function previewOf(overrides: Partial<PlanChangePreview>): PlanChangePreview {
    return {
      plan: business,
      direction: 'upgrade',
      surcharge: '25.00',
      credit_used: '0.00',
      amount_due: '25.00',
      waived: false,
      credit_added: '0.00',
      credit_after: '0.00',
      keep: [],
      suspend: [],
      resume: [],
      blocked: '',
      ...overrides,
    };
  }

  async function open(routes = {}, current = standard) {
    signedIn({ ...verified, plan: current.name });
    const api = mockApi({
      'GET /billing/plans/': [[start, standard, business]],
      'GET /billing/': overview({ subscription: subscription({ plan: current }) }),
      ...routes,
    });
    await renderScreen(<ChangePlanScreen />);
    return { api };
  }

  test('the current plan is marked and cannot be picked', async () => {
    await open();

    expect(await screen.findByText('Twój plan')).toBeTruthy();
    expect(screen.queryByRole('radio', { name: /^Standard/ })).toBeNull();
  });

  test('a dearer plan shows the surcharge and sends you to pay it', async () => {
    const checkout = {
      payment: payment({ kind: 'upgrade', amount: '25.00', status: 'pending' }),
      redirect_url: 'https://x',
    };
    const { api } = await open({
      'POST /billing/subscription/change-preview/': previewOf({}),
      'POST /billing/subscription/change/': { change: previewOf({}), ...checkout },
    });

    await fireEvent.press(await screen.findByRole('radio', { name: /^Biznes/ }));

    expect(await screen.findByText(/Dopłacisz teraz 25,00 zł za dni do 5 grudnia 2026\./)).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Dopłać 25,00 zł i zmień plan' }));

    expect(api.sent('POST /billing/subscription/change/')).toEqual([
      { plan: 'business', return_url: 'http://localhost:8081/billing/return' },
    ]);
    await waitFor(() => expect(goToPayment).toHaveBeenCalledWith(checkout));
  });

  test('a surcharge below 5 zł is waived and the plan changes at once', async () => {
    const waived = previewOf({ surcharge: '1.67', amount_due: '0.00', waived: true });
    await open({
      'POST /billing/subscription/change-preview/': waived,
      'POST /billing/subscription/change/': { change: waived, payment: null, redirect_url: null },
    });

    await fireEvent.press(await screen.findByRole('radio', { name: /^Biznes/ }));
    expect(await screen.findByText(/mniej niż 5 zł, więc zmieniamy plan bez dopłaty/)).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Zmień plan' }));

    expect(await screen.findByText('Masz teraz plan Biznes.')).toBeTruthy();
    expect(refreshUser).toHaveBeenCalled();
    expect(router.replace).toHaveBeenCalledWith('/billing');
  });

  test('a cheaper plan credits the difference and lets you choose which shops stay', async () => {
    const shops = [
      woo(1, 'Palarnia'),
      woo(2, 'Herbaciarnia'),
    ];
    const downgrade = (keepIds: number[]) =>
      previewOf({
        plan: start,
        direction: 'downgrade',
        surcharge: '-10.00',
        amount_due: '0.00',
        credit_added: '10.00',
        credit_after: '10.00',
        keep: shops.filter((shop) => keepIds.includes(shop.id)),
        suspend: shops.filter((shop) => !keepIds.includes(shop.id)),
      });
    const { api } = await open({
      'POST /billing/subscription/change-preview/': (body: { keep_shops?: number[] }) =>
        downgrade(body.keep_shops ?? [1]),
      'POST /billing/subscription/change/': (body: { keep_shops?: number[] }) => ({
        change: downgrade(body.keep_shops ?? [1]),
        payment: null,
        redirect_url: null,
      }),
    });

    await fireEvent.press(await screen.findByRole('radio', { name: /^Start/ }));
    expect(await screen.findByText(/Niewykorzystane 10,00 zł trafi na saldo/)).toBeTruthy();
    expect(screen.getByText(/Następna płatność 5 grudnia 2026: 19,00 zł/)).toBeTruthy();

    // Swap which shop stays: drop the default one, keep the other.
    await fireEvent.press(screen.getByRole('checkbox', { name: /Palarnia/ }));
    await fireEvent.press(await screen.findByRole('checkbox', { name: /Herbaciarnia/ }));
    await waitFor(() =>
      expect(screen.getByRole('checkbox', { name: /Herbaciarnia/ })).toHaveProp('accessibilityState', {
        checked: true,
      }),
    );
    await fireEvent.press(screen.getByRole('button', { name: 'Zmień plan' }));

    expect(confirm).toHaveBeenCalledWith('Zawiesić sklepy?', expect.stringContaining('Palarnia'), 'Zmień plan');
    expect(api.sent('POST /billing/subscription/change/')).toEqual([
      { plan: 'start', return_url: 'http://localhost:8081/billing/return', keep_shops: [2] },
    ]);
  });

  test('keeping too many shops is refused before asking the server', async () => {
    const shops = [
      woo(1, 'Palarnia'),
      woo(2, 'Herbaciarnia'),
    ];
    await open({
      'POST /billing/subscription/change-preview/': previewOf({
        plan: start,
        direction: 'downgrade',
        amount_due: '0.00',
        credit_added: '10.00',
        keep: [shops[0]],
        suspend: [shops[1]],
      }),
    });

    await fireEvent.press(await screen.findByRole('radio', { name: /^Start/ }));
    await fireEvent.press(await screen.findByRole('checkbox', { name: /Herbaciarnia/ }));

    expect(await screen.findByText('W planie Start zostawisz najwyżej 1 sklep.')).toBeTruthy();
  });

  test('Magento shops beyond the plan are refused before asking the server', async () => {
    const shops = [
      { ...woo(1, 'Palarnia'), platform: 'magento' as const, platform_display: 'Magento' },
      { ...woo(2, 'Herbaciarnia'), platform: 'magento' as const, platform_display: 'Magento' },
      woo(3, 'Kawiarnia'),
    ];
    await open({
      'POST /billing/subscription/change-preview/': previewOf({
        plan: standard,
        direction: 'downgrade',
        amount_due: '0.00',
        credit_added: '50.00',
        keep: [shops[0], shops[2]],
        suspend: [shops[1]],
      }),
    }, business);

    await fireEvent.press(await screen.findByRole('radio', { name: /^Standard/ }));

    expect(
      await screen.findByText('Plan Standard to do 3 sklepów, w tym 1 na Magento. Wybierz, które sklepy zostają aktywne:'),
    ).toBeTruthy();
    await fireEvent.press(screen.getByRole('checkbox', { name: /Herbaciarnia/ }));

    expect(await screen.findByText('W planie Standard zostawisz najwyżej 1 sklep Magento.')).toBeTruthy();
  });

  test('a blocked change says why', async () => {
    await open({
      'POST /billing/subscription/change-preview/': previewOf({
        blocked: 'Poprzednia zmiana planu czeka jeszcze na płatność.',
      }),
    });

    await fireEvent.press(await screen.findByRole('radio', { name: /^Biznes/ }));

    expect(await screen.findByText('Poprzednia zmiana planu czeka jeszcze na płatność.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /zmień plan/i })).toBeNull();
  });
});

test('the billing page offers a plan change and shows the balance', async () => {
  signedIn({ ...verified, plan: 'Standard' });
  mockApi({ 'GET /billing/': overview({ subscription: subscription({ credit: '10.00' }) }) });
  await renderScreen(<BillingScreen />);

  expect(await screen.findByText(/Saldo nadpłaty: 10,00 zł/)).toBeTruthy();
  expect(screen.getByText(/Następna płatność 5 grudnia 2026: 39,00 zł\./)).toBeTruthy();
  await fireEvent.press(screen.getByRole('button', { name: 'Zmień plan' }));
  expect(router.push).toHaveBeenCalledWith('/billing/change');
});
