from datetime import timedelta
from pathlib import Path
import os

from celery.schedules import crontab


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost")

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',
    'accounts',
    'shops',
    'support',
    'handbook',
    'billing',
    'push',
    'monitoring',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ["POSTGRES_DB"],
        'USER': os.environ["POSTGRES_USER"],
        'PASSWORD': os.environ["POSTGRES_PASSWORD"],
        'HOST': os.environ.get("POSTGRES_HOST", "db"),
        'PORT': os.environ.get("POSTGRES_PORT", "5432"),
    }
}


# Auth

AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

EMAIL_VERIFICATION_CODE_TTL = timedelta(minutes=15)
EMAIL_VERIFICATION_MAX_ATTEMPTS = 5
EMAIL_VERIFICATION_RESEND_COOLDOWN = timedelta(seconds=60)


LANGUAGE_CODE = 'pl'

TIME_ZONE = 'Europe/Warsaw'

USE_I18N = True

USE_TZ = True

STATIC_URL = 'static/'

# Avatars, served by the app itself (accounts.views.avatar_file).
MEDIA_URL = '/media/'
MEDIA_ROOT = Path(os.environ.get('MEDIA_ROOT', BASE_DIR / 'media'))

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Email

EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "0") == "1"
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Sklepownia <no-reply@localhost>")
PLATFORM_NAME = os.environ.get("PLATFORM_NAME", "Sklepownia")
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "kontakt@localhost")
# Where links in e-mails lead (the web app).
APP_URL = os.environ.get("APP_URL", "http://localhost:8081").rstrip("/")


# REST API

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_RATES': {
        'auth': '10/min',
        'email_verification': '10/hour',
        'password_reset': '5/hour',
        'contact': '5/hour',
        'admin_access_email': '5/hour',
        'shop_invitations': '30/hour',
        'avatar': '30/hour',
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'MobileApp API',
    'VERSION': '0.1.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'ENUM_NAME_OVERRIDES': {
        'ShopStatusEnum': 'shops.models.Shop.Status',
        'ProvisioningJobStatusEnum': 'shops.models.ProvisioningJob.Status',
        'ProvisioningStepStatusEnum': 'shops.models.ProvisioningStep.Status',
        'PushDevicePlatformEnum': 'push.models.PushDevice.Platform',
        'PlatformEnum': 'shops.platforms.Platform',
        'ChecklistStepEnum': 'shops.models.ShopChecklist.Step',
        'ShopOrderStatusEnum': 'shops.models.ShopOrder.Status',
        'OrderActionEnum': 'shops.serializers.ORDER_ACTIONS',
    },
}

# Expo Web dev server; native apps don't send Origin, so they don't need CORS.
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:8081")


# Celery

CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
# crontab hours in CELERY_BEAT_SCHEDULE are local time.
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1


# Repository root as mounted into the container; its docs are shown under /docs/.
HANDBOOK_ROOT = os.environ.get("HANDBOOK_ROOT", "/project")

# Shops

# Fernet key used to encrypt shop credentials at rest.
FIELD_ENCRYPTION_KEY = os.environ["FIELD_ENCRYPTION_KEY"]

SHOPS_BASE_DOMAIN = os.environ.get("SHOPS_BASE_DOMAIN", "localhost")
SHOPS_URL_SCHEME = os.environ.get("SHOPS_URL_SCHEME", "https")
SHOPS_HTTP_PORT = int(os.environ.get("SHOPS_HTTP_PORT", "443"))
# "docker" (real shops, per-platform provisioners: shops/provisioning/__init__.py) or one class for every platform.
SHOP_PROVISIONER = os.environ.get("SHOP_PROVISIONER", "shops.provisioning.fake.FakeProvisioner")
# Seconds per fake provisioning step, so the app shows progress.
FAKE_PROVISIONER_STEP_DELAY = float(os.environ.get("FAKE_PROVISIONER_STEP_DELAY", "2"))
# Step key at which the fake provisioner fails, to test error handling.
FAKE_PROVISIONER_FAIL_AT_STEP = os.environ.get("FAKE_PROVISIONER_FAIL_AT_STEP", "")

# Docker provisioner: the shop node from infra/shops, via the Docker socket.
SHOPS_WORDPRESS_IMAGE = os.environ.get("SHOPS_WORDPRESS_IMAGE", "shops/wordpress:7.1")
SHOPS_PRESTASHOP_IMAGE = os.environ.get("SHOPS_PRESTASHOP_IMAGE", "prestashop/prestashop:9.2.1-apache")
SHOPS_MAGENTO_IMAGE = os.environ.get("SHOPS_MAGENTO_IMAGE", "shops/magento:4.0.0")
# Minimum memory for Magento, even when the owner's plan gives less.
SHOPS_MAGENTO_MEMORY = os.environ.get("SHOPS_MAGENTO_MEMORY", "1536m")
SHOPS_NETWORK = os.environ.get("SHOPS_NETWORK", "shops")
SHOPS_DB_CONTAINER = os.environ.get("SHOPS_DB_CONTAINER", "shops-db")
SHOPS_PROXY_CONTAINER = os.environ.get("SHOPS_PROXY_CONTAINER", "shops-proxy")
# Magento's search engine.
SHOPS_SEARCH_CONTAINER = os.environ.get("SHOPS_SEARCH_CONTAINER", "shops-search")
SHOPS_DB_ROOT_PASSWORD = os.environ.get("SHOPS_DB_ROOT_PASSWORD", "")
SHOPS_CONTAINER_MEMORY = os.environ.get("SHOPS_CONTAINER_MEMORY", "512m")
# "local" lets WordPress accept application passwords over plain HTTP; use "production" with HTTPS.
SHOPS_WP_ENVIRONMENT = os.environ.get("SHOPS_WP_ENVIRONMENT", "production")
# Shops mail through a relay on the shop node, without credentials: owners can read their shop's whole config.
# Locally Mailpit (shops-mail), in production a relay holding the provider's credentials. Empty: no mail server.
SHOPS_SMTP_HOST = os.environ.get("SHOPS_SMTP_HOST", "shops-mail")
SHOPS_SMTP_PORT = int(os.environ.get("SHOPS_SMTP_PORT", "1025"))
# Shops send from <slug>@SHOPS_MAIL_DOMAIN so the provider can sign it; shop software rejects dotless domains.
SHOPS_MAIL_DOMAIN = os.environ.get("SHOPS_MAIL_DOMAIN") or (
    SHOPS_BASE_DOMAIN if "." in SHOPS_BASE_DOMAIN else f"sklepy.{SHOPS_BASE_DOMAIN}"
)
# Download cache for plugins installed in shops (shops/provisioning/packages.py); safe to lose.
SHOPS_PACKAGE_CACHE = os.environ.get("SHOPS_PACKAGE_CACHE", "/tmp/sklepownia-packages")

# Restic backups (shops/backups.py) in a volume on the shop node. No password: no backups.
# The password encrypts the repository: keep a copy away from the server, without it the backups can't be read.
SHOPS_BACKUP_PASSWORD = os.environ.get("SHOPS_BACKUP_PASSWORD", "")
SHOPS_BACKUP_IMAGE = os.environ.get("SHOPS_BACKUP_IMAGE", "shops/backup:0.19.1")
SHOPS_BACKUP_VOLUME = os.environ.get("SHOPS_BACKUP_VOLUME", "shops-backups")
SHOPS_BACKUP_CACHE_VOLUME = os.environ.get("SHOPS_BACKUP_CACHE_VOLUME", "shops-backup-cache")
# Hour (TIME_ZONE) of the nightly backup and pruning.
SHOPS_BACKUP_HOUR = int(os.environ.get("SHOPS_BACKUP_HOUR", "3"))
# Kept: everything from the last day, plus the newest backup of each of the latest days and weeks.
SHOPS_BACKUP_KEEP_DAILY = int(os.environ.get("SHOPS_BACKUP_KEEP_DAILY", "7"))
SHOPS_BACKUP_KEEP_WEEKLY = int(os.environ.get("SHOPS_BACKUP_KEEP_WEEKLY", "4"))
# Days a deleted shop's last backup is kept, so a shop deleted by mistake can be restored.
SHOPS_BACKUP_DELETED_DAYS = int(os.environ.get("SHOPS_BACKUP_DELETED_DAYS", "14"))
# Manual backups per day, on top of the nightly ones.
SHOPS_BACKUP_MANUAL_PER_DAY = int(os.environ.get("SHOPS_BACKUP_MANUAL_PER_DAY", "3"))


# Billing

# billing.gateways.fake.FakeGateway (simulated) or billing.gateways.tpay.TpayGateway (needs the TPAY_* keys).
PAYMENT_GATEWAY = os.environ.get("PAYMENT_GATEWAY", "billing.gateways.fake.FakeGateway")
TPAY_CLIENT_ID = os.environ.get("TPAY_CLIENT_ID", "")
TPAY_CLIENT_SECRET = os.environ.get("TPAY_CLIENT_SECRET", "")
# Merchant security code (Merchant panel → Notifications → Security), for the notification checksum.
TPAY_SECURITY_CODE = os.environ.get("TPAY_SECURITY_CODE", "")
TPAY_SANDBOX = os.environ.get("TPAY_SANDBOX", "1") == "1"
# Public address of billing.views.gateway_notification. Tpay must reach it (ports 80, 443 or 8080).
TPAY_NOTIFICATION_URL = os.environ.get("TPAY_NOTIFICATION_URL", "http://localhost:8000/api/billing/notifications/")
FAKE_GATEWAY_DECLINE_RENEWALS = os.environ.get("FAKE_GATEWAY_DECLINE_RENEWALS", "0") == "1"
# Allowed payer return URLs: the web app and the mobile app's links (exp:// in Expo Go).
BILLING_RETURN_URL_PREFIXES = env_list("BILLING_RETURN_URL_PREFIXES", "http://localhost:8081/,mobile://,exp://")

# billing.invoicing.platform.PlatformIssuer (numbered and rendered here, outside KSeF) or
# billing.invoicing.fakturownia.FakturowniaIssuer (Fakturownia numbers them and sends company invoices to KSeF).
INVOICE_ISSUER = os.environ.get("INVOICE_ISSUER", "billing.invoicing.platform.PlatformIssuer")
# Seller on PlatformIssuer invoices; Fakturownia uses the company set up in its account.
INVOICE_SELLER = {
    "name": os.environ.get("INVOICE_SELLER_NAME", ""),
    "tax_id": os.environ.get("INVOICE_SELLER_TAX_ID", ""),
    "street": os.environ.get("INVOICE_SELLER_STREET", ""),
    "postal_code": os.environ.get("INVOICE_SELLER_POSTAL_CODE", ""),
    "city": os.environ.get("INVOICE_SELLER_CITY", ""),
    "bank_account": os.environ.get("INVOICE_SELLER_BANK_ACCOUNT", ""),
}
if DEBUG and not INVOICE_SELLER["name"]:
    # Development without a company: invoices say they are test documents.
    INVOICE_SELLER.update(name=f"{PLATFORM_NAME} (dane testowe)", tax_id="5260001246", street="Testowa 1",
                          postal_code="00-001", city="Warszawa", test=True)
# PlatformIssuer numbering; the counter starts over every month.
INVOICE_NUMBER_FORMAT = os.environ.get("INVOICE_NUMBER_FORMAT", "FV/{year}/{month:02}/{number:04}")
# Fakturownia: the account's subdomain (firma for firma.fakturownia.pl) and API token
# (Ustawienia → Ustawienia konta → Integracja → Kod autoryzacyjny API).
FAKTUROWNIA_DOMAIN = os.environ.get("FAKTUROWNIA_DOMAIN", "")
FAKTUROWNIA_API_TOKEN = os.environ.get("FAKTUROWNIA_API_TOKEN", "")
# 1 = invoices for companies go to KSeF (the account needs KSeF connected: Ustawienia → KSeF).
FAKTUROWNIA_KSEF = os.environ.get("FAKTUROWNIA_KSEF", "1") == "1"

SHOP_ORDERS_SYNC_MINUTES = int(os.environ.get("SHOP_ORDERS_SYNC_MINUTES", "15"))

# Expo's service, or push.senders.log.LogSender to only log notifications.
PUSH_SENDER = os.environ.get("PUSH_SENDER", "push.senders.expo.ExpoSender")
# Needed only with "enhanced security for push notifications" on in the Expo project.
EXPO_ACCESS_TOKEN = os.environ.get("EXPO_ACCESS_TOKEN", "")

# Monitoring: a shop is down after MONITOR_FAILURES failed checks in a row; ALERT_EMAILS are the staff.
MONITOR_INTERVAL_MINUTES = int(os.environ.get("MONITOR_INTERVAL_MINUTES", "5"))
MONITOR_FAILURES = int(os.environ.get("MONITOR_FAILURES", "2"))
ALERT_EMAILS = [email.strip() for email in os.environ.get("ALERT_EMAILS", CONTACT_EMAIL).split(",") if email.strip()]
# Staff are alerted below this free disk share and above this share of a server's shop limit.
MONITOR_DISK_MIN_FREE_PERCENT = int(os.environ.get("MONITOR_DISK_MIN_FREE_PERCENT", "10"))
MONITOR_SERVER_FULL_PERCENT = int(os.environ.get("MONITOR_SERVER_FULL_PERCENT", "90"))
# Pinged after every round (e.g. healthchecks.io), which alarms when rounds stop. Empty: no ping.
MONITOR_PING_URL = os.environ.get("MONITOR_PING_URL", "")
# Shops checked in parallel.
MONITOR_WORKERS = int(os.environ.get("MONITOR_WORKERS", "8"))

CELERY_BEAT_SCHEDULE = {
    "renew-subscriptions": {"task": "billing.tasks.renew_subscriptions", "schedule": 15 * 60},
    "reconcile-payments": {"task": "billing.tasks.reconcile_payments", "schedule": 5 * 60},
    "process-invoices": {"task": "billing.tasks.process_invoices", "schedule": 5 * 60},
    "sync-shop-orders": {"task": "shops.tasks.sync_all_shop_orders", "schedule": SHOP_ORDERS_SYNC_MINUTES * 60},
    "check-push-receipts": {"task": "push.tasks.check_push_receipts", "schedule": 15 * 60},
    "back-up-shops": {"task": "shops.tasks.back_up_all_shops", "schedule": crontab(hour=SHOPS_BACKUP_HOUR, minute=0)},
    # Expires: rounds queued behind a busy worker would run back to back and count a shop's failures seconds apart.
    "check-shops": {
        "task": "monitoring.tasks.check_shops",
        "schedule": MONITOR_INTERVAL_MINUTES * 60,
        "options": {"expires": MONITOR_INTERVAL_MINUTES * 60},
    },
}
