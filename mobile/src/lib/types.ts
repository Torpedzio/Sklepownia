export type User = {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  is_email_verified: boolean;
  date_joined: string;
  /** 0 without a plan; test shops don't count. */
  shop_limit: number;
  magento_shop_limit: number;
  plan: string | null;
  can_create_shops: boolean;
  avatar_url: string | null;
  /** Chosen at sign-up, changeable: own shops (the app suggests a plan) or joining others' teams. */
  purpose: AccountPurpose;
};

export type AccountPurpose = 'own_shop' | 'team';

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
  platform: Platform;
  platform_display: string;
  /** Pre-plan shop: works without a plan, outside its limit. */
  is_test: boolean;
  created_at: string;
  /** Since when the running shop doesn't answer; null while it works. */
  down_since: string | null;
  /** The signed-in person's role: owner (pays for the plan) or staff, who can only view the shop and its sales. */
  role: ShopRole;
};

export type ShopRole = 'owner' | 'staff';

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
  /** For the staff: who runs the shop and invited them. */
  owner: Person;
  /** E.g. "panel WordPressa". */
  panel_name: string;
  /** E.g. "około dwóch minut". */
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

/** The login and password only ever go by e-mail, to `sent_to`. */
export type ShopAdminAccess = {
  admin_url: string;
  sent_to: string;
};

export type Choice = { value: string; label: string };

export type FormOptions = {
  platforms: (Choice & {
    value: Platform;
    description: string;
    /** Allowed by the plan now. */
    available: boolean;
    /** The plan's limit (e.g. which plans have Magento); empty without one. */
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
    przelewy24_enabled: boolean;
    przelewy24_sandbox: boolean;
    przelewy24_merchant_id: string;
    /** CRC and API keys of the chosen mode are saved. Keys are only ever sent, never returned. */
    przelewy24_keys_saved: boolean;
    payu_enabled: boolean;
    payu_sandbox: boolean;
    payu_pos_id: string;
    payu_client_id: string;
    /** Same for the second MD5 key and client_secret. */
    payu_keys_saved: boolean;
  };
  shipping: {
    courier_enabled: boolean;
    /** Money goes both ways as text with two decimals, e.g. "15.00". */
    courier_cost: string;
    free_shipping_enabled: boolean;
    free_shipping_min_amount: string;
    local_pickup_enabled: boolean;
  };
  taxes: { enabled: boolean; prices_include_tax: boolean; standard_rate: string };
  region: { language: string; currency: string; country: string; timezone: string };
  appearance: { theme: string };
  documents: {
    /** The app republishes the documents after every change they describe. */
    managed: boolean;
    seller_name: string;
    register: SellerRegister;
    street: string;
    postal_code: string;
    city: string;
    tax_id: string;
    regon: string;
    krs: string;
    phone: string;
    return_days: number;
    free_returns: boolean;
    /** Working days from payment to dispatch. */
    dispatch_days: number;
    /** Empty until the first publication. */
    terms_url: string;
    privacy_url: string;
    /** E.g. "2026-11-18". */
    version: string;
  };
};

export type SellerRegister = 'ceidg' | 'krs' | 'unregistered';

export type SettingsSection = keyof ShopSettingsValues;

export type ShopOperationKind =
  | 'update_settings'
  | 'sync_settings'
  | 'reset_admin_password'
  | 'remove_sample_products'
  | 'publish_documents'
  | 'create_backup'
  | 'restore_backup';

/** One level of items can sit inside. */
export type DocumentListItem = { text: string; items?: DocumentListItem[] };

export type DocumentBlock =
  | { type: 'heading'; level: number; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'list'; ordered: boolean; items: DocumentListItem[] };

export type ShopDocument = { key: 'terms' | 'privacy'; title: string; blocks: DocumentBlock[] };

export type ShopOperation = {
  id: number;
  kind: ShopOperationKind;
  kind_display: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  status_display: string;
  changes: Partial<{ [S in SettingsSection]: Partial<ShopSettingsValues[S]> }>;
  /** Field labels, e.g. ["Waluta"]. */
  changed_fields: string[];
  /** removed: sample products deleted; before: the backup made before restoring. */
  result: { removed?: number; before?: number };
  /** Of the backup made (create_backup) or restored (restore_backup). */
  backup_created_at: string | null;
  error: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type PaymentOperator = 'przelewy24' | 'payu';

export type ShopBackup = {
  id: number;
  kind: 'nightly' | 'manual' | 'before_restore' | 'before_delete';
  kind_display: string;
  created_at: string;
  /** Bytes. */
  size: number | null;
};

export type ShopBackups = {
  /** The platform supports backups. */
  enabled: boolean;
  /** Newest first. */
  backups: ShopBackup[];
  manual_left: number;
  manual_per_day: number;
  /** The newest backup of each of this many last days and weeks stays. */
  keep_daily: number;
  keep_weekly: number;
  nightly_at: string;
};

export type ShopSettings = {
  values: ShopSettingsValues;
  /** Changeable here on this platform; the rest only in the admin panel. */
  sections: SettingsSection[];
  payment_operators: PaymentOperator[];
  /** Przelewy24 wants this address in its panel; null until known. */
  server_ip: string | null;
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
    registers: Choice[];
  };
};

export type Plan = {
  code: string;
  name: string;
  description: string;
  /** Gross, per period, e.g. "49.00". */
  price: string;
  currency: string;
  vat_rate: string;
  interval_months: number;
  max_shops: number;
  max_magento_shops: number;
  /** Staff per shop, not counting the owner; null: no limit. */
  max_staff: number | null;
  shop_memory_mb: number;
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
  /** Overpaid money (e.g. after downgrading mid-period); renewals use it first. */
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
  /** From the balance, not the card. */
  credit_used: string;
  currency: string;
  gateway_title: string;
  period_start: string | null;
  period_end: string | null;
  error: string;
  created_at: string;
  paid_at: string | null;
  /** Null when there is none (e.g. a renewal paid from the balance). */
  invoice: Invoice | null;
};

export type Invoice = {
  /** Empty until issued. */
  number: string;
  issue_date: string | null;
  gross: string;
  currency: string;
  ksef_number: string;
  /** Issued (and accepted in KSeF when it goes there), so downloadable. */
  ready: boolean;
  /** Signed PDF link valid for a day; null until ready. */
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

export type PlanChangePreview = {
  plan: Plan;
  direction: 'upgrade' | 'downgrade' | '';
  /** For the rest of the paid period. */
  surcharge: string;
  credit_used: string;
  amount_due: string;
  /** Below 5 zł, not charged. */
  waived: boolean;
  credit_added: string;
  credit_after: string;
  keep: ShopBrief[];
  suspend: ShopBrief[];
  resume: ShopBrief[];
  /** Empty when the change is possible. */
  blocked: string;
};

export type PlanChangeResult = {
  change: PlanChangePreview;
  payment: Payment | null;
  redirect_url: string | null;
};

/** Placed, non-cancelled orders, in the shop's currency. */
export type SalesPeriod = { orders: number; revenue: string; average: string };

export type SalesDay = { date: string; orders: number; revenue: string };

export type OrderStatus = 'new' | 'processing' | 'completed' | 'cancelled' | 'unfinished';

/** As last read from the shop; the customer is a first name and an initial. */
export type ShopOrder = {
  number: string;
  status: OrderStatus;
  status_display: string;
  total: string;
  currency: string;
  items: number;
  customer: string;
  placed_at: string;
};

/** From a copy of the orders the platform reads every few minutes. */
export type ShopSales = {
  /** The shop runs, so its orders are read. */
  available: boolean;
  synced_at: string | null;
  /** A read is under way: ask again in a few seconds. */
  refreshing: boolean;
  error: string;
  currency: string;
  today: SalesPeriod;
  last_7_days: SalesPeriod;
  last_30_days: SalesPeriod;
  previous_30_days: SalesPeriod;
  /** Oldest first. */
  daily: SalesDay[];
  to_handle: { new: number; processing: number };
  /** Newest first. */
  recent: ShopOrder[];
};

export type ChecklistStepKey =
  | 'payments'
  | 'shipping'
  | 'documents'
  | 'products'
  | 'sample_products'
  | 'notifications'
  | 'test_order';

/** Every step ticks itself off from what the platform sees in the shop. */
export type ShopChecklist = {
  /** The shop runs and the owner hasn't hidden the list. */
  available: boolean;
  hidden: boolean;
  /** Applicable steps, in order. */
  steps: { key: ChecklistStepKey; done: boolean }[];
  /** Own products and samples left; null until counted. */
  products: number | null;
  sample_products: number | null;
  counted_at: string | null;
  /** Counting, reading orders or saving: ask again in a few seconds. */
  refreshing: boolean;
};

export type PushPreferences = {
  new_orders: boolean;
  shops: boolean;
  billing: boolean;
  devices: { name: string; platform: 'ios' | 'android'; platform_display: string; last_seen_at: string }[];
};

export type Person = {
  id: number;
  name: string;
  email: string;
};

/** An invitation to a shop's staff, waiting for the signed-in person. */
export type Invitation = {
  id: number;
  shop: { id: number; name: string; url: string; platform: Platform; platform_display: string };
  invited_by: Person | null;
  created_at: string;
  expires_at: string;
};

export type TeamMember = Person & { joined_at: string };

export type TeamInvitation = {
  id: number;
  email: string;
  created_at: string;
  expires_at: string;
  /** Past its term: inviting the address again sends a new one. */
  expired: boolean;
};

/** `GET /shops/{id}/team/`, for the owner. */
export type Team = {
  owner: Person;
  members: TeamMember[];
  invitations: TeamInvitation[];
  /** Staff the owner's plan allows, not counting the owner; null: no limit. */
  limit: number | null;
  /** Members and valid invitations. */
  used: number;
};
