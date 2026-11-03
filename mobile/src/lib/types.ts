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
