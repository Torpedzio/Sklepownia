export type User = {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  is_email_verified: boolean;
  date_joined: string;
  /** How many shops the active plan allows; 0 without a plan. Test shops don't count. */
  shop_limit: number;
  /** Name of the active plan, or null. */
  plan: string | null;
  can_create_shops: boolean;
  /** Profile picture (a 512×512 WebP), or null. */
  avatar_url: string | null;
};

export type Tokens = { access: string; refresh: string };

export type ShopStatus = 'pending' | 'provisioning' | 'active' | 'failed' | 'suspended' | 'deleted';

export type Platform = 'woocommerce' | 'prestashop' | 'magento';

export type Shop = {
  id: number;
  name: string;
  slug: string;
  url: string;
  status: ShopStatus;
  status_display: string;
  /** The e-commerce system the shop runs on. */
  platform: Platform;
  platform_display: string;
  /** From before paid plans: works without a plan and doesn't count towards its limit. */
  is_test: boolean;
  created_at: string;
};

export type ShopTemplate = {
  slug: string;
  platform: Platform;
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
  /** The admin panel as owners know it, e.g. "panel WordPressa". */
  panel_name: string;
  /** How long setting up takes, e.g. "około dwóch minut". */
  setup_time: string;
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

/** Where the admin panel is. The login and password only ever go by e-mail, to `sent_to`. */
export type ShopAdminAccess = {
  admin_url: string;
  sent_to: string;
};

export type Choice = { value: string; label: string };

export type FormOptions = {
  platforms: (Choice & {
    value: Platform;
    description: string;
    /** Whether the plan lets the user create a shop on it now. */
    available: boolean;
    /** The plan's limit, e.g. which plans have Magento; empty without one. */
    note: string;
  })[];
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
  platform: Platform;
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
  /** Sections the app can change on the shop's platform; the rest is set in the admin panel. */
  sections: SettingsSection[];
  /** The admin panel as owners know it, e.g. "panel WordPressa". */
  panel_name: string;
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

export type Plan = {
  code: string;
  name: string;
  description: string;
  /** Gross price per period, e.g. "49.00". */
  price: string;
  currency: string;
  vat_rate: string;
  interval_months: number;
  max_shops: number;
  /** How many of those shops may run on Magento; 0 when the plan has no Magento. */
  max_magento_shops: number;
  /** Memory of each shop's container. */
  shop_memory_mb: number;
  /** Highlighted as the usual choice. */
  is_featured: boolean;
  features: string[];
};

export type BillingProfile = {
  kind: 'individual' | 'company';
  full_name: string;
  company_name: string;
  tax_id: string;
  street: string;
  postal_code: string;
  city: string;
  country: string;
};

export type SubscriptionStatus = 'incomplete' | 'active' | 'past_due' | 'canceled' | 'expired';

export type Subscription = {
  plan: Plan;
  status: SubscriptionStatus;
  status_display: string;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  next_attempt_at: string | null;
  card: { brand: string; tail: string; expiry: string } | null;
  /** Overpaid money (e.g. after a cheaper plan mid-period); renewals use it first. */
  credit: string;
  allows_new_shops: boolean;
};

export type Payment = {
  id: number;
  kind: 'initial' | 'renewal' | 'upgrade';
  kind_display: string;
  status: 'pending' | 'paid' | 'failed';
  status_display: string;
  plan_name: string;
  amount: string;
  /** Taken from the balance instead of the card. */
  credit_used: string;
  currency: string;
  gateway_title: string;
  period_start: string | null;
  period_end: string | null;
  error: string;
  created_at: string;
  paid_at: string | null;
  /** The invoice of a paid payment; null when there is none (e.g. a renewal paid from the balance). */
  invoice: Invoice | null;
};

export type Invoice = {
  /** Empty until it is issued. */
  number: string;
  issue_date: string | null;
  gross: string;
  currency: string;
  ksef_number: string;
  /** Issued (and accepted in KSeF when it goes there): it can be downloaded. */
  ready: boolean;
  /** The PDF, a signed link valid for a day; null until ready. */
  url: string | null;
};

export type BillingOverview = {
  subscription: Subscription | null;
  profile: BillingProfile | null;
  payments: Payment[];
};

export type Checkout = { payment: Payment; redirect_url: string };

export type ShopBrief = {
  id: number;
  name: string;
  status: ShopStatus;
  platform: Platform;
  platform_display: string;
};

/** What moving to another plan would mean now. */
export type PlanChangePreview = {
  plan: Plan;
  direction: 'upgrade' | 'downgrade' | '';
  /** Price difference for the rest of the paid period. */
  surcharge: string;
  credit_used: string;
  /** To pay now. */
  amount_due: string;
  /** A surcharge below 5 zł that isn't charged. */
  waived: boolean;
  /** Unused money moved to the balance. */
  credit_added: string;
  credit_after: string;
  keep: ShopBrief[];
  suspend: ShopBrief[];
  resume: ShopBrief[];
  /** Why the change isn't possible; empty when it is. */
  blocked: string;
};

export type PlanChangeResult = {
  change: PlanChangePreview;
  payment: Payment | null;
  redirect_url: string | null;
};
