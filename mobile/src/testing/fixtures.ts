import type { ShopDetail, ShopSettings, ShopSettingsValues } from '@/lib/types';

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
    created_at: '2026-11-05T10:00:00Z',
    config: {
      industry: 'food',
      template: { slug: 'storefront', name: 'Storefront', description: '', preview_image_url: '' },
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
