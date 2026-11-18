import type { SalesDay, ShopDetail, ShopSales, ShopSettings, ShopSettingsValues } from '@/lib/types';

type Overrides = { [S in keyof ShopSettingsValues]?: Partial<ShopSettingsValues[S]> };

/** Settings of a shop as the API returns them, with sections changed by `overrides`. */
export function shopSettings(overrides: Overrides = {}, extra: Partial<ShopSettings> = {}): ShopSettings {
  const values: ShopSettingsValues = {
    general: { name: 'Palarnia', description: 'Kawa', contact_email: 'kontakt@example.com' },
    availability: { is_open: true },
    shopping: {
      guest_checkout: true,
      signup_at_checkout: false,
      reviews: true,
      manage_stock: true,
      low_stock_threshold: 2,
    },
    payments: {
      bank_transfer_enabled: false,
      bank_account_name: '',
      bank_account_number: '',
      bank_name: '',
      cash_on_delivery_enabled: false,
    },
    shipping: {
      courier_enabled: false,
      courier_cost: '15.00',
      free_shipping_enabled: false,
      free_shipping_min_amount: '200.00',
      local_pickup_enabled: false,
    },
    taxes: { enabled: false, prices_include_tax: true, standard_rate: '23.00' },
    region: { language: 'pl_PL', currency: 'PLN', country: 'PL', timezone: 'Europe/Warsaw' },
    appearance: { theme: 'storefront' },
  };
  for (const [section, fields] of Object.entries(overrides)) {
    Object.assign(values[section as keyof ShopSettingsValues], fields);
  }
  return {
    values,
    sections: ['general', 'availability', 'shopping', 'payments', 'shipping', 'taxes', 'region', 'appearance'],
    panel_name: 'panel WordPressa',
    synced_at: '2026-11-05T10:42:00Z',
    operation: null,
    busy: false,
    options: {
      languages: [
        { value: 'pl_PL', label: 'Polski' },
        { value: 'en_US', label: 'English' },
      ],
      currencies: [
        { value: 'PLN', label: 'Złoty (PLN)' },
        { value: 'EUR', label: 'Euro (EUR)' },
      ],
      countries: [
        { value: 'PL', label: 'Polska' },
        { value: 'DE', label: 'Niemcy' },
      ],
      timezones: [{ value: 'Europe/Warsaw', label: 'Warszawa' }],
      themes: [
        { value: 'storefront', label: 'Storefront' },
        { value: 'astra', label: 'Astra' },
      ],
      vat_rates: { PL: ['23.00', '8.00', '5.00', '0.00'], DE: ['19.00', '7.00', '0.00'] },
    },
    ...extra,
  };
}

/** A shop as GET /shops/{id}/ returns it, set up and running unless `overrides` say otherwise. */
export function shopDetail(overrides: Partial<ShopDetail> = {}): ShopDetail {
  const steps = [
    { key: 'allocate_server', label: 'Miejsce na serwerze' },
    { key: 'install_wordpress', label: 'Strona i konto administratora' },
  ];
  const status = overrides.status ?? 'active';
  return {
    id: 7,
    name: 'Palarnia',
    slug: 'palarnia',
    url: 'http://palarnia.localhost:8080',
    status,
    status_display:
      { active: 'Aktywny', provisioning: 'Zakładanie', failed: 'Błąd', pending: 'Oczekuje' }[status as string] ??
      status,
    platform: 'woocommerce',
    platform_display: 'WooCommerce',
    panel_name: 'panel WordPressa',
    setup_time: 'około dwóch minut',
    is_test: false,
    created_at: '2026-11-05T10:00:00Z',
    config: {
      industry: 'food',
      template: {
        slug: 'storefront',
        platform: 'woocommerce',
        name: 'Storefront',
        description: '',
        preview_image_url: '',
      },
      category_count: 3,
      language: 'pl_PL',
      currency: 'PLN',
      country: 'PL',
      contact_email: 'kontakt@example.com',
      description: '',
      include_sample_products: true,
    },
    provisioning: {
      id: 1,
      status: status === 'active' ? 'succeeded' : status === 'failed' ? 'failed' : 'running',
      error: '',
      completed_steps: status === 'active' ? 2 : 1,
      total_steps: 2,
      steps: steps.map((step, index) => ({
        ...step,
        status: status === 'active' || index === 0 ? 'done' : status === 'failed' ? 'failed' : 'running',
        error: status === 'failed' && index === 1 ? 'WordPress nie wystartował.' : '',
      })),
    },
    ...overrides,
  };
}

/**
 * The sales overview of a shop with three orders: two today (one new, one paid) and one on 3 November.
 * The 30 days run from 20 October to 18 November 2026.
 */
export function shopSales(overrides: Partial<ShopSales> = {}): ShopSales {
  const daily: SalesDay[] = Array.from({ length: 30 }, (_, offset) => {
    const date = new Date(Date.UTC(2026, 9, 20 + offset)).toISOString().slice(0, 10);
    const sales = { '2026-11-03': ['1', '200.00'], '2026-11-18': ['2', '120.00'] }[date] ?? ['0', '0.00'];
    return { date, orders: Number(sales[0]), revenue: sales[1] };
  });
  return {
    available: true,
    synced_at: '2026-11-18T13:05:00Z',
    refreshing: false,
    error: '',
    currency: 'PLN',
    today: { orders: 2, revenue: '120.00', average: '60.00' },
    last_7_days: { orders: 2, revenue: '120.00', average: '60.00' },
    last_30_days: { orders: 3, revenue: '320.00', average: '106.67' },
    previous_30_days: { orders: 2, revenue: '250.00', average: '125.00' },
    daily,
    to_handle: { new: 1, processing: 1 },
    recent: [
      { number: '1042', status: 'processing', status_display: 'W realizacji', total: '70.00', currency: 'PLN',
        items: 2, customer: 'Anna N.', placed_at: '2026-11-18T12:40:00Z' },
      { number: '1041', status: 'new', status_display: 'Nowe', total: '50.00', currency: 'PLN', items: 1,
        customer: 'Jan K.', placed_at: '2026-11-18T09:15:00Z' },
      { number: '1040', status: 'completed', status_display: 'Zrealizowane', total: '200.00', currency: 'PLN',
        items: 4, customer: 'Ola W.', placed_at: '2026-11-03T17:00:00Z' },
    ],
    ...overrides,
  };
}
