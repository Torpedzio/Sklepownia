export type User = {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  is_email_verified: boolean;
  date_joined: string;
  shop_limit: number;
};

export type Tokens = { access: string; refresh: string };

export type ShopStatus = 'pending' | 'provisioning' | 'active' | 'failed' | 'suspended' | 'deleted';

export type Shop = {
  id: number;
  name: string;
  slug: string;
  url: string;
  status: ShopStatus;
  status_display: string;
  created_at: string;
};

export type ShopTemplate = {
  slug: string;
  name: string;
  description: string;
  preview_image_url: string;
};

export type ProvisioningStep = {
  key: string;
  label: string;
  status: 'pending' | 'running' | 'done' | 'failed';
  error: string;
};

export type ShopDetail = Shop & {
  config: {
    industry: string;
    template: ShopTemplate;
    category_count: number;
    language: string;
    currency: string;
    country: string;
    contact_email: string;
    description: string;
    include_sample_products: boolean;
  };
  provisioning: {
    id: number;
    status: 'queued' | 'running' | 'succeeded' | 'failed';
    error: string;
    completed_steps: number;
    total_steps: number;
    steps: ProvisioningStep[];
  } | null;
};

export type ShopAdminAccess = {
  admin_url: string;
  username: string;
  password: string;
};

export type Choice = { value: string; label: string };

export type FormOptions = {
  industries: Choice[];
  languages: Choice[];
  currencies: Choice[];
  countries: Choice[];
  templates: ShopTemplate[];
  category_count: { min: number; max: number; default: number };
  base_domain: string;
};

export type NewShop = {
  name: string;
  slug: string;
  industry: string;
  template: string;
  category_count: number;
  language: string;
  currency: string;
  country: string;
  include_sample_products: boolean;
};

export type ShopSettingsValues = {
  general: { name: string; description: string; contact_email: string };
  availability: { is_open: boolean };
  shopping: {
    guest_checkout: boolean;
    signup_at_checkout: boolean;
    reviews: boolean;
    manage_stock: boolean;
    low_stock_threshold: number;
  };
  payments: {
    bank_transfer_enabled: boolean;
    bank_account_name: string;
    bank_account_number: string;
    bank_name: string;
    cash_on_delivery_enabled: boolean;
  };
  shipping: {
    courier_enabled: boolean;
    /** Money is sent and received as text with two decimals, e.g. "15.00". */
    courier_cost: string;
    free_shipping_enabled: boolean;
    free_shipping_min_amount: string;
    local_pickup_enabled: boolean;
  };
  taxes: { enabled: boolean; prices_include_tax: boolean; standard_rate: string };
  region: { language: string; currency: string; country: string; timezone: string };
  appearance: { theme: string };
};

export type SettingsSection = keyof ShopSettingsValues;

export type ShopOperationKind = 'update_settings' | 'sync_settings' | 'reset_admin_password' | 'remove_sample_products';

export type ShopOperation = {
  id: number;
  kind: ShopOperationKind;
  kind_display: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  status_display: string;
  changes: Partial<{ [S in SettingsSection]: Partial<ShopSettingsValues[S]> }>;
  /** Labels of the changed fields, e.g. ["Waluta"]. */
  changed_fields: string[];
  result: { removed?: number };
  error: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type ShopSettings = {
  values: ShopSettingsValues;
  synced_at: string | null;
  operation: ShopOperation | null;
  busy: boolean;
  options: {
    languages: Choice[];
    currencies: Choice[];
    countries: Choice[];
    timezones: Choice[];
    themes: Choice[];
    vat_rates: Record<string, string[]>;
  };
};
