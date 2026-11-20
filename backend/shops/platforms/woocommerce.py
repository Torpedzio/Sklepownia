import base64
import json
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings

from ..categories import category_names
from ..choices import COUNTRY_TIMEZONES
from ..models import ShopTemplate
from ..orders import (
    Address, Order, OrderDetail, OrderLine, Status as OrderStatus, amount, country_name, customer_label, from_timestamp,
    full_name, quantity,
)
from ..shop_settings import OPERATORS
from . import Platform
from ..provisioning import packages
from ..provisioning.base import ProductCount
from ..provisioning.container import (
    FILES_PATH, CommandError, ContainerProvisioner, container_name, db_name, mail_relay,
)
from ..provisioning.packages import Package
from ..remote import NotInShop
from ..remote.woocommerce import WooCommerceApi


WP_PATH = FILES_PATH
ADMIN_USERNAME = "admin"
SAMPLE_PRODUCT_CATEGORIES = 3
SAMPLE_PRODUCTS_PER_CATEGORY = 2

# Marks the sample products, so they can be removed later without touching the owner's own products.
SAMPLE_PRODUCT_META = "_sklepownia_sample"
# Older shops have unmarked sample products; they are recognised by name.
SAMPLE_PRODUCT_NAME = re.compile(r"^Przykładowy produkt \d+$")

# Sends the shop's e-mail through the platform's relay; its settings are in MAIL_OPTION.
MAIL_PLUGIN = Path(__file__).parent / "files" / "woocommerce" / "sklepownia-mail.php"
MAIL_PLUGIN_PATH = f"{WP_PATH}/wp-content/mu-plugins/sklepownia-mail.php"
MAIL_OPTION = "sklepownia_mail"

# Links the published terms and privacy policy under every theme's footer; the pages are in DOCUMENTS_OPTION.
DOCUMENTS_PLUGIN = Path(__file__).parent / "files" / "woocommerce" / "sklepownia-documents.php"
DOCUMENTS_PLUGIN_PATH = f"{WP_PATH}/wp-content/mu-plugins/sklepownia-documents.php"
DOCUMENTS_OPTION = "sklepownia_documents"
# WordPress options naming the shop's terms (WooCommerce links them at checkout) and privacy policy pages.
DOCUMENT_PAGE_OPTIONS = {"terms": "woocommerce_terms_page_id", "privacy": "wp_page_for_privacy_policy"}

# The shipping zone and VAT rate the app manages.
SHIPPING_ZONE_OPTION = "sklepownia_shipping_zone_id"
TAX_RATE_OPTION = "sklepownia_tax_rate_id"

SETTINGS_OPTIONS = [
    "blogname", "blogdescription", "admin_email", "WPLANG", "timezone_string", "stylesheet",
    "woocommerce_email_from_address", "woocommerce_coming_soon",
    "woocommerce_enable_guest_checkout", "woocommerce_enable_signup_and_login_from_checkout",
    "woocommerce_enable_reviews", "woocommerce_manage_stock", "woocommerce_notify_low_stock_amount",
    "woocommerce_currency", "woocommerce_default_country",
    "woocommerce_calc_taxes", "woocommerce_prices_include_tax",
]

# Titles customers see, in the shop's language.
SHIPPING_TITLES = {
    "pl_PL": {"flat_rate": "Kurier", "free_shipping": "Darmowa dostawa", "local_pickup": "Odbiór osobisty"},
    "en_US": {"flat_rate": "Courier", "free_shipping": "Free shipping", "local_pickup": "Local pickup"},
    "de_DE": {"flat_rate": "Kurier", "free_shipping": "Kostenloser Versand", "local_pickup": "Abholung"},
}
SHOP_PAGE_TITLES = {
    "pl_PL": {"shop": "Sklep", "cart": "Koszyk", "checkout": "Zamówienie", "myaccount": "Moje konto"},
    "en_US": {"shop": "Shop", "cart": "Cart", "checkout": "Checkout", "myaccount": "My account"},
    "de_DE": {"shop": "Shop", "cart": "Warenkorb", "checkout": "Kasse", "myaccount": "Mein Konto"},
}


@dataclass(frozen=True)
class GatewayPlugin:
    """An operator's plugin, installed the first time the owner turns the operator on."""

    package: Package
    # The plugin's main file, as WordPress names active plugins.
    file: str
    # Id prefix of all the plugin's gateways.
    prefix: str
    # The gateway the app turns on: a redirect to the operator's page with all its methods (BLIK, transfers, cards).
    main: str


ONLINE_PAYMENTS = {
    "przelewy24": GatewayPlugin(
        package=Package(
            title="wtyczki Przelewy24",
            folder="woo-przelewy24",
            version="1.2.1",
            url="https://www.przelewy24.pl/storage/app/media/do-pobrania/gotowe-wtyczki/woocommerce/"
            "woocommerce-11-przelewy24-1.2.1.zip",
            sha256="05686972c679ccd55d987f6022432553d4e0ee6f9f1a962a072d8dc140eb39cb",
        ),
        file="woo-przelewy24/woocommerce-p24-gateway.php",
        prefix="p24-",
        main="p24-online-payments",
    ),
    "payu": GatewayPlugin(
        package=Package(
            title="wtyczki PayU",
            folder="woo-payu-payment-gateway",
            version="2.12.1",
            url="https://downloads.wordpress.org/plugin/woo-payu-payment-gateway.2.12.1.zip",
            sha256="d3d01f3a0854f7c16b8143be588137642ea0ced130bd22ae891c0219ed8372ea",
        ),
        file="woo-payu-payment-gateway/woocommerce-gateway-payu.php",
        prefix="payu",
        main="payustandard",
    ),
}

# Output of `wp eval` after this marker is the result (see _php), so notices WordPress prints first don't break parsing.
OUTPUT_MARKER = "@@sklepownia@@"

READ_SETTINGS_PHP = """
$options = array();
foreach ($d['options'] as $name) { $options[$name] = get_option($name); }
$methods = array();
$zone_id = (int) get_option('%(zone)s', 0);
$zone = $zone_id ? WC_Shipping_Zones::get_zone($zone_id) : false;
if ($zone && $zone->get_id()) {
    foreach ($zone->get_shipping_methods(false) as $method) {
        $methods[$method->id] = array(
            'enabled' => $method->is_enabled(),
            'cost' => $method->get_option('cost'),
            'min_amount' => $method->get_option('min_amount'),
        );
    }
}
$rate = null;
$rate_id = (int) get_option('%(rate)s', 0);
if ($rate_id) { $found = WC_Tax::_get_tax_rate($rate_id); if (!empty($found)) { $rate = $found['tax_rate']; } }
$accounts = get_option('woocommerce_bacs_accounts', array());
$bacs = get_option('woocommerce_bacs_settings', array());
$cod = get_option('woocommerce_cod_settings', array());
// Online payments: an operator is on when any gateway of its active plugin is. Keys are only checked, not read.
if (!function_exists('is_plugin_active')) { require_once ABSPATH . 'wp-admin/includes/plugin.php'; }
$gateways = WC()->payment_gateways()->payment_gateways();
$online = array();
foreach ($d['online'] as $key => $plugin) {
    $active = is_plugin_active($plugin['file']);
    $enabled = false;
    foreach ($gateways as $id => $gateway) {
        if ($active && strpos($id, $plugin['prefix']) === 0 && $gateway->enabled === 'yes') { $enabled = true; }
    }
    $online[$key] = array('active' => $active, 'enabled' => $enabled);
}
$filled = function ($value) { return is_string($value) && $value !== ''; };
$payu = get_option('payu_settings_option_name', array());
if (!is_array($payu)) { $payu = array(); }
$payu_standard = get_option('woocommerce_payustandard_settings', array());
$payu_sandbox = is_array($payu_standard) && ($payu_standard['sandbox'] ?? 'no') === 'yes';
$payu_prefix = $payu_sandbox ? 'global_sandbox_' : 'global_';
$online['przelewy24'] += array(
    'sandbox' => get_option('p24_mode', 'sandbox') !== 'production',
    'merchant_id' => (string) get_option('p24_merchant_id', ''),
    'keys' => $filled(get_option('p24_crc_key', '')) && $filled(get_option('p24_reports_key', '')),
);
$online['payu'] += array(
    'sandbox' => $payu_sandbox,
    'pos_id' => (string) ($payu[$payu_prefix . 'pos_id'] ?? ''),
    'client_id' => (string) ($payu[$payu_prefix . 'client_id'] ?? ''),
    'keys' => $filled($payu[$payu_prefix . 'md5'] ?? '') && $filled($payu[$payu_prefix . 'client_secret'] ?? ''),
);
echo "\n%(marker)s" . wp_json_encode(array(
    'options' => $options,
    'bacs_enabled' => is_array($bacs) && ($bacs['enabled'] ?? 'no') === 'yes',
    'bacs_account' => is_array($accounts) && $accounts ? $accounts[0] : null,
    'cod_enabled' => is_array($cod) && ($cod['enabled'] ?? 'no') === 'yes',
    'methods' => (object) $methods,
    'tax_rate' => $rate,
    'online' => $online,
));
""" % {"zone": SHIPPING_ZONE_OPTION, "rate": TAX_RATE_OPTION, "marker": OUTPUT_MARKER}

PLUGIN_STATE_PHP = """
if (!function_exists('get_plugins')) { require_once ABSPATH . 'wp-admin/includes/plugin.php'; }
$plugins = get_plugins();
echo "\n%(marker)s" . wp_json_encode(array(
    'installed' => isset($plugins[$d['file']]),
    'active' => is_plugin_active($d['file']),
));
""" % {"marker": OUTPUT_MARKER}

# Written before the plugin is activated: activating asks Przelewy24 for the payment methods of the account.
PRZELEWY24_ACCOUNT_PHP = """
update_option('p24_mode', $d['sandbox'] ? 'sandbox' : 'production');
update_option('p24_merchant_id', $d['merchant_id']);
foreach (array('crc_key' => 'p24_crc_key', 'api_key' => 'p24_reports_key') as $field => $option) {
    if (isset($d[$field])) { update_option($option, $d[$field]); }
}
$methods = 'WC_P24\\Utilities\\Payment_Methods';
if (class_exists($methods)) { $methods::clear_payment_methods_cache(); }
"""

# Written after activating, which adds PayU's defaults first. A new install turns off the installments widget: it
# asks PayU for every product list shown.
PAYU_ACCOUNT_PHP = """
$settings = get_option('payu_settings_option_name', array());
if (!is_array($settings)) { $settings = array(); }
if (function_exists('payu_get_default_settings')) { $settings = array_merge(payu_get_default_settings(), $settings); }
$prefix = $d['sandbox'] ? 'global_sandbox_' : 'global_';
$settings[$prefix . 'pos_id'] = $d['pos_id'];
$settings[$prefix . 'client_id'] = $d['client_id'];
foreach (array('md5_key' => 'md5', 'client_secret' => 'client_secret') as $field => $name) {
    if (isset($d[$field])) { $settings[$prefix . $name] = $d[$field]; }
}
if ($d['fresh']) {
    foreach (array('listings', 'product_page', 'cart_page', 'checkout_page') as $page) {
        $settings['credit_widget_on_' . $page] = 'no';
    }
}
update_option('payu_settings_option_name', $settings);
"""

# Toggles the main gateway. The others go off with it, else stay as the owner set them, except right after
# installing, when the ones the plugin turned on by itself go off.
ONLINE_GATEWAYS_PHP = """
foreach (WC()->payment_gateways()->payment_gateways() as $id => $gateway) {
    if (strpos($id, $d['prefix']) !== 0) { continue; }
    $on = $id === $d['main'] ? $d['enabled'] : ($d['enabled'] && !$d['fresh'] && $gateway->enabled === 'yes');
    $gateway->update_option('enabled', $on ? 'yes' : 'no');
    foreach ($d['options'][$id] ?? array() as $name => $value) { $gateway->update_option($name, $value); }
}
"""

SET_OPTIONS_PHP = "foreach ($d as $name => $value) { update_option($name, $value); }"

# Updates the shop's terms and privacy policy pages (WordPress's own privacy draft too), creating missing ones.
# Without a user, WordPress filters the HTML as for an author, which keeps ours.
DOCUMENTS_PHP = """
$admins = get_users(array('role' => 'administrator', 'number' => 1, 'fields' => 'ID'));
$ids = array();
$urls = array();
foreach ($d['documents'] as $document) {
    $id = (int) get_option($document['option']);
    $post = $id ? get_post($id) : null;
    $page = array(
        'post_type' => 'page',
        'post_status' => 'publish',
        'post_title' => $document['title'],
        'post_name' => $document['slug'],
        'post_content' => $document['html'],
        'comment_status' => 'closed',
        'ping_status' => 'closed',
    );
    if ($post && $post->post_type === 'page' && $post->post_status !== 'trash') {
        $page['ID'] = $id;
    } elseif ($admins) {
        $page['post_author'] = (int) $admins[0];
    }
    $id = wp_insert_post(wp_slash($page), true);
    if (is_wp_error($id)) { throw new Exception($id->get_error_message()); }
    update_option($document['option'], $id);
    $ids[$document['key']] = $id;
    $urls[$document['key']] = get_permalink($id);
}
update_option('%(option)s', $ids);
echo "\n%(marker)s" . wp_json_encode($urls);
""" % {"option": DOCUMENTS_OPTION, "marker": OUTPUT_MARKER}

RENAME_PAGES_PHP = """
foreach ($d as $page => $title) {
    $id = wc_get_page_id($page);
    if ($id > 0) { wp_update_post(array('ID' => $id, 'post_title' => $title)); }
}
"""

PAYMENTS_PHP = """
$bacs = get_option('woocommerce_bacs_settings', array());
if (!is_array($bacs)) { $bacs = array(); }
$bacs['enabled'] = $d['bank_transfer'] ? 'yes' : 'no';
update_option('woocommerce_bacs_settings', $bacs);
update_option('woocommerce_bacs_accounts', $d['account'] ? array(array_merge(
    array('sort_code' => '', 'iban' => '', 'bic' => ''), $d['account']
)) : array());
$cod = get_option('woocommerce_cod_settings', array());
if (!is_array($cod)) { $cod = array(); }
$cod['enabled'] = $d['cash_on_delivery'] ? 'yes' : 'no';
update_option('woocommerce_cod_settings', $cod);
"""

TAXES_PHP = """
update_option('woocommerce_calc_taxes', $d['enabled'] ? 'yes' : 'no');
update_option('woocommerce_prices_include_tax', $d['include'] ? 'yes' : 'no');
update_option('woocommerce_tax_display_shop', $d['include'] ? 'incl' : 'excl');
update_option('woocommerce_tax_display_cart', $d['include'] ? 'incl' : 'excl');
$rate = array(
    'tax_rate_country' => $d['country'], 'tax_rate_state' => '', 'tax_rate' => $d['rate'],
    'tax_rate_name' => 'VAT', 'tax_rate_priority' => 1, 'tax_rate_compound' => 0,
    'tax_rate_shipping' => 1, 'tax_rate_order' => 0, 'tax_rate_class' => '',
);
$id = (int) get_option('%(rate)s', 0);
if ($id && !empty(WC_Tax::_get_tax_rate($id))) { WC_Tax::_update_tax_rate($id, $rate); }
else { update_option('%(rate)s', WC_Tax::_insert_tax_rate($rate)); }
""" % {"rate": TAX_RATE_OPTION}

SHIPPING_PHP = """
$id = (int) get_option('%(zone)s', 0);
$zone = $id ? WC_Shipping_Zones::get_zone($id) : false;
if (!$zone || !$zone->get_id()) { $zone = new WC_Shipping_Zone(); }
$zone->set_zone_name($d['zone_name']);
$zone->set_locations(array(array('code' => $d['country'], 'type' => 'country')));
$zone->save();
update_option('%(zone)s', $zone->get_id());
foreach ($d['methods'] as $method_id => $wanted) {
    $instance = null;
    foreach ($zone->get_shipping_methods(false) as $existing) {
        if ($existing->id === $method_id) { $instance = $existing; break; }
    }
    if (!$wanted['enabled']) {
        if ($instance) { $zone->delete_shipping_method($instance->instance_id); }
        continue;
    }
    $instance_id = $instance ? $instance->instance_id : $zone->add_shipping_method($method_id);
    $key = 'woocommerce_' . $method_id . '_' . $instance_id . '_settings';
    $current = get_option($key, array());
    update_option($key, array_merge(is_array($current) ? $current : array(), $wanted['settings']));
}
WC_Cache_Helper::get_transient_version('shipping', true);
""" % {"zone": SHIPPING_ZONE_OPTION}

# WooCommerce's API works with both order storages (HPOS and posts). Refunds (shop_order_refund) are not listed.
READ_ORDERS_PHP = """
$orders = wc_get_orders(array(
    'type' => 'shop_order',
    'limit' => (int) $d['limit'],
    'orderby' => 'modified',
    'order' => 'ASC',
    'date_modified' => '>=' . (int) $d['since'],
    'status' => array_keys(wc_get_order_statuses()),
));
$rows = array();
foreach ($orders as $order) {
    $created = $order->get_date_created();
    $modified = $order->get_date_modified() ?: $created;
    $rows[] = array(
        'id' => (string) $order->get_id(),
        'number' => (string) $order->get_order_number(),
        'status' => $order->get_status(),
        'total' => (string) $order->get_total(),
        'currency' => $order->get_currency(),
        'items' => (int) $order->get_item_count(),
        'first_name' => $order->get_billing_first_name(),
        'last_name' => $order->get_billing_last_name(),
        'created' => $created ? $created->getTimestamp() : 0,
        'modified' => $modified ? $modified->getTimestamp() : 0,
    );
}
echo "\n%(marker)s" . wp_json_encode($rows);
""" % {"marker": OUTPUT_MARKER}

# Without "wc-". "pending" waits for an online payment; "on-hold" is placed but unpaid (e.g. bank transfer).
# Block checkout drafts are not orders yet.
ORDER_STATUSES = {
    "pending": OrderStatus.UNFINISHED,
    "on-hold": OrderStatus.NEW,
    "processing": OrderStatus.PROCESSING,
    "completed": OrderStatus.COMPLETED,
    "cancelled": OrderStatus.CANCELLED,
    "refunded": OrderStatus.CANCELLED,
    "failed": OrderStatus.CANCELLED,
    "trash": OrderStatus.CANCELLED,
}
SKIPPED_ORDER_STATUSES = {"checkout-draft"}

REMOVE_SAMPLE_PRODUCTS_PHP = """
$removed = 0;
$products = wc_get_products(array('limit' => -1, 'status' => array('publish', 'draft', 'pending', 'private')));
foreach ($products as $product) {
    if ($product->get_meta('%(meta)s') || preg_match($d['name_pattern'], $product->get_name())) {
        $product->delete(true);
        $removed++;
    }
}
echo "\n%(marker)s" . $removed;
""" % {"meta": SAMPLE_PRODUCT_META, "marker": OUTPUT_MARKER}

# Counted in SQL, as loading every product is slow in a big catalogue. Samples as in REMOVE_SAMPLE_PRODUCTS_PHP.
COUNT_PRODUCTS_PHP = """
global $wpdb;
$statuses = "'publish', 'draft', 'pending', 'private', 'future'";
$total = (int) $wpdb->get_var(
    "SELECT COUNT(*) FROM {$wpdb->posts} WHERE post_type = 'product' AND post_status IN ($statuses)"
);
$candidates = $wpdb->get_results($wpdb->prepare(
    "SELECT p.post_title, MAX(m.meta_value) AS marked FROM {$wpdb->posts} p"
    . " LEFT JOIN {$wpdb->postmeta} m ON m.post_id = p.ID AND m.meta_key = %%s"
    . " WHERE p.post_type = 'product' AND p.post_status IN ($statuses)"
    . " AND (m.meta_id IS NOT NULL OR p.post_title LIKE %%s) GROUP BY p.ID",
    '%(meta)s', $wpdb->esc_like('Przykładowy produkt ') . '%%'
));
$samples = 0;
foreach ($candidates as $row) {
    if ($row->marked || preg_match($d['name_pattern'], $row->post_title)) { $samples++; }
}
echo "\\n%(marker)s" . json_encode(array('products' => $total - $samples, 'samples' => $samples));
""" % {"meta": SAMPLE_PRODUCT_META, "marker": OUTPUT_MARKER}

# Currencies written like "1 234,56 zł" rather than "$1,234.56".
COMMA_DECIMAL_CURRENCIES = {"PLN", "EUR"}

# `options`: PHP putting the shop sidebar left of the product archive; `search` is False where the header has one.
THEME_NAVIGATION = {
    "storefront": {
        "sidebar": "sidebar-1",
        "search": False,
        "options": "set_theme_mod('storefront_layout', 'left');",
    },
    "astra": {
        "sidebar": "astra-woo-shop-sidebar",
        "search": True,
        "options": (
            "$s = get_option('astra-settings', array());"
            "$s['archive-product-sidebar-layout'] = 'left-sidebar';"
            "update_option('astra-settings', $s);"
        ),
    },
    "kadence": {
        "sidebar": "sidebar-primary",
        "search": True,
        # The front page (our shop page) takes its layout from the page itself, not the archive setting.
        "options": (
            "set_theme_mod('product_archive_layout', 'left');"
            "update_post_meta(wc_get_page_id('shop'), '_kad_post_layout', 'left');"
        ),
    },
}

NAVIGATION_TITLES = {
    "pl_PL": {"search": "Szukaj produktów", "categories": "Kategorie", "active": "Aktywne filtry",
              "price": "Cena", "rating": "Ocena"},
    "en_US": {"search": "Search products", "categories": "Categories", "active": "Active filters",
              "price": "Price", "rating": "Rating"},
    "de_DE": {"search": "Produkte suchen", "categories": "Kategorien", "active": "Aktive Filter",
              "price": "Preis", "rating": "Bewertung"},
}

WORDPRESS_ENV_KEYS = (
    "WORDPRESS_DB_HOST", "WORDPRESS_DB_NAME", "WORDPRESS_DB_USER", "WORDPRESS_DB_PASSWORD", "WORDPRESS_CONFIG_EXTRA",
)


class WooCommerceProvisioner(ContainerProvisioner):
    """WordPress with WooCommerce; mirrors infra/shops/woocommerce/provision-shop.sh step by step."""

    ENV_KEYS = WORDPRESS_ENV_KEYS
    API = WooCommerceApi
    START_FAILED = "WordPress nie wystartował."
    # Caching plugins' page caches and WordPress's update leftovers.
    BACKUP_EXCLUDES = ("wp-content/cache", "wp-content/upgrade")

    def image(self):
        return settings.SHOPS_WORDPRESS_IMAGE

    def container_environment(self, shop):
        return {
            "WORDPRESS_DB_HOST": settings.SHOPS_DB_CONTAINER,
            "WORDPRESS_DB_NAME": db_name(shop),
            "WORDPRESS_DB_USER": db_name(shop),
            "WORDPRESS_DB_PASSWORD": self._credentials(shop).db_password,
            "WORDPRESS_CONFIG_EXTRA": (
                f"define('WP_ENVIRONMENT_TYPE', '{settings.SHOPS_WP_ENVIRONMENT}');"
                "define('DISALLOW_FILE_EDIT', true);"
            ),
        }

    def ready_command(self):
        # The entrypoint copies WordPress into the volume and writes wp-config.php.
        return ["test", "-f", f"{WP_PATH}/wp-config.php"]

    def default_admin_login(self, shop):
        return ADMIN_USERNAME

    def step_install_wordpress(self, shop):
        credentials = self._credentials(shop)
        installed = self._wp_succeeds(shop, "core", "is-installed")
        if not credentials.admin_password:
            credentials.admin_login = ADMIN_USERNAME
            credentials.admin_password = secrets.token_urlsafe(18)
            credentials.save(update_fields=["admin_login", "admin_password", "updated_at"])
            if installed:
                # Installed by an earlier attempt whose password never got stored.
                self._wp(shop, "user", "update", ADMIN_USERNAME,
                         f"--user_pass={credentials.admin_password}", "--skip-email")
        if not installed:
            self._wp(
                shop, "core", "install",
                f"--url={shop.url}",
                f"--title={shop.name}",
                f"--admin_user={credentials.admin_login}",
                f"--admin_password={credentials.admin_password}",
                f"--admin_email={shop.config.contact_email}",
                "--skip-email",
            )
            # Drop "Hello world" and "Sample Page". Only on a fresh install.
            default_content = self._wp(
                shop, "post", "list", "--post_type=post,page", "--post_status=any", "--format=ids",
            ).split()
            if default_content:
                self._wp(shop, "post", "delete", *default_content, "--force")
        self._wp(shop, "option", "update", "blogname", shop.name)
        self._wp(shop, "option", "update", "blogdescription", shop.config.description)

    def step_configure_locale(self, shop):
        language = shop.config.language
        if language != "en_US":
            self._wp(shop, "language", "core", "install", language)
            self._wp(shop, "site", "switch-language", language)
        self._wp(shop, "option", "update", "timezone_string", COUNTRY_TIMEZONES.get(shop.config.country, "UTC"))
        self._wp(shop, "rewrite", "structure", "/%postname%/")
        self._wp(shop, "rewrite", "flush", "--hard")

    def step_configure_woocommerce(self, shop):
        config = shop.config
        # Translation first: activation creates the shop pages in the active language.
        if config.language != "en_US":
            self._wp(shop, "language", "plugin", "install", "woocommerce", config.language)
        if not self._wp_succeeds(shop, "plugin", "is-active", "woocommerce"):
            self._wp(shop, "plugin", "activate", "woocommerce")

        options = {
            "woocommerce_default_country": config.country,
            **_currency_options(config.currency),
            "woocommerce_weight_unit": "kg",
            "woocommerce_dimension_unit": "cm",
            "woocommerce_email_from_address": config.contact_email,
            "woocommerce_email_from_name": shop.name,
            # New stores start in "coming soon" mode; open them right away.
            "woocommerce_coming_soon": "no",
            "woocommerce_allow_tracking": "no",
            "woocommerce_show_marketplace_suggestions": "no",
        }
        for key, value in options.items():
            self._wp(shop, "option", "update", key, value)
        # Skip the onboarding wizard and the setup task list (WooCommerce 11 option names).
        self._wp(shop, "option", "update", "woocommerce_onboarding_profile",
                 json.dumps({"skipped": True}), "--format=json")
        self._wp(shop, "option", "update", "woocommerce_task_list_hidden_lists",
                 json.dumps(["setup", "extended"]), "--format=json")
        self._wp(shop, "wc", "tool", "run", "install_pages", f"--user={ADMIN_USERNAME}")
        self._wp(shop, "option", "update", "show_on_front", "page")
        shop_page = self._wp(shop, "option", "get", "woocommerce_shop_page_id")
        self._wp(shop, "option", "update", "page_on_front", shop_page)
        # For order confirmations and the owner's new-order alerts.
        relay = mail_relay(shop)
        if relay is not None:
            self._configure_mail(shop, relay)

    def step_install_theme(self, shop):
        theme = shop.config.template.theme
        if self._wp(shop, "option", "get", "stylesheet") != theme:
            self._wp(shop, "theme", "activate", theme)
            # Drop the default blog widgets the theme picked up. Block themes have no sidebars.
            self._wp_succeeds(shop, "widget", "reset", "--all")
        if shop.config.language != "en_US":
            # Not every theme ships every translation.
            self._wp_succeeds(shop, "language", "theme", "install", theme, shop.config.language)

    def step_create_categories(self, shop):
        config = shop.config
        category_ids = []
        for name in category_names(config.industry, config.category_count):
            existing = self._wp(shop, "term", "list", "product_cat", f"--name={name}", "--field=term_id")
            category_ids.append(existing or self._wp(
                shop, "wc", "product_cat", "create", f"--name={name}", f"--user={ADMIN_USERNAME}", "--porcelain",
            ))

        # Make our first category the default one, so "Uncategorized" doesn't show up in the menu.
        default_category = self._wp(shop, "option", "get", "default_product_cat")
        if default_category not in category_ids:
            self._wp(shop, "option", "update", "default_product_cat", category_ids[0])
            self._wp_succeeds(shop, "term", "delete", "product_cat", default_category)

        has_products = self._wp(shop, "wc", "product", "list", f"--user={ADMIN_USERNAME}", "--format=count") != "0"
        if not config.include_sample_products or has_products:
            return
        number = 1
        for category_id in category_ids[:SAMPLE_PRODUCT_CATEGORIES]:
            for _ in range(SAMPLE_PRODUCTS_PER_CATEGORY):
                self._wp(
                    shop, "wc", "product", "create", f"--user={ADMIN_USERNAME}", "--porcelain",
                    f"--name=Przykładowy produkt {number}",
                    "--type=simple", "--status=publish",
                    f"--regular_price={number * 25 + 24}.99",
                    "--description=To jest przykładowy produkt. Zmień jego opis, zdjęcia i cenę w panelu sklepu.",
                    f"--categories={json.dumps([{'id': int(category_id)}])}",
                    f"--meta_data={json.dumps([{'key': SAMPLE_PRODUCT_META, 'value': '1'}])}",
                )
                number += 1

    def step_configure_navigation(self, shop):
        navigation = THEME_NAVIGATION.get(shop.config.template.theme)
        if navigation is None:
            return
        titles = NAVIGATION_TITLES.get(shop.config.language, NAVIGATION_TITLES["en_US"])
        sidebar = navigation["sidebar"]
        self._wp(shop, "eval", navigation["options"])
        # Rebuilt from scratch, so running it again gives the same sidebar.
        self._wp_succeeds(shop, "widget", "reset", sidebar)
        widgets = [
            ("woocommerce_product_search", [f"--title={titles['search']}"]),
            ("woocommerce_product_categories",
             [f"--title={titles['categories']}", "--count=1", "--hierarchical=1", "--orderby=name"]),
            # Shown only once a filter is applied / once products have reviews.
            ("woocommerce_layered_nav_filters", [f"--title={titles['active']}"]),
            ("woocommerce_price_filter", [f"--title={titles['price']}"]),
        ]
        # WooCommerce has no rating filter while reviews are turned off.
        if self._option(shop, "woocommerce_enable_reviews", "yes") == "yes":
            widgets.append(("woocommerce_rating_filter", [f"--title={titles['rating']}"]))
        if not navigation["search"]:
            widgets = widgets[1:]
        for position, (widget, args) in enumerate(widgets, start=1):
            self._wp(shop, "widget", "add", widget, sidebar, str(position), *args)

    def step_generate_api_keys(self, shop):
        credentials = self._credentials(shop)
        username = credentials.admin_login
        existing = self._wp(shop, "user", "application-password", "list", username,
                            "--name=platform", "--field=uuid").split()
        for uuid in existing:
            self._wp(shop, "user", "application-password", "delete", username, uuid)
        credentials.api_key = self._wp(
            shop, "user", "application-password", "create", username, "platform", "--porcelain",
        )
        credentials.save(update_fields=["api_key", "updated_at"])

    def step_health_check(self, shop):
        self._check_pages(shop, [("strona sklepu", [self.proxy_url("/")])])
        self._check_api(shop)

    # --- running shops ---

    def read_settings(self, shop):
        data = json.loads(self._php(shop, READ_SETTINGS_PHP, {
            "options": SETTINGS_OPTIONS,
            "online": {key: {"file": plugin.file, "prefix": plugin.prefix} for key, plugin in ONLINE_PAYMENTS.items()},
        }))
        options, methods = data["options"], data["methods"]
        przelewy24, payu = data["online"]["przelewy24"], data["online"]["payu"]

        def text(name):
            return options.get(name) or ""

        def yes(name):
            return options.get(name) == "yes"

        account = data["bacs_account"] or {}
        courier = methods.get("flat_rate", {})
        free = methods.get("free_shipping", {})
        theme = ShopTemplate.objects.filter(platform=Platform.WOOCOMMERCE, theme=text("stylesheet")).first()
        return {
            "general": {
                "name": text("blogname"),
                "description": text("blogdescription"),
                "contact_email": text("woocommerce_email_from_address") or text("admin_email"),
            },
            "availability": {"is_open": not yes("woocommerce_coming_soon")},
            "shopping": {
                "guest_checkout": yes("woocommerce_enable_guest_checkout"),
                "signup_at_checkout": yes("woocommerce_enable_signup_and_login_from_checkout"),
                "reviews": yes("woocommerce_enable_reviews"),
                "manage_stock": yes("woocommerce_manage_stock"),
                "low_stock_threshold": _int(options.get("woocommerce_notify_low_stock_amount"), 2),
            },
            "payments": {
                "bank_transfer_enabled": data["bacs_enabled"],
                "bank_account_name": account.get("account_name") or "",
                "bank_account_number": account.get("account_number") or account.get("iban") or "",
                "bank_name": account.get("bank_name") or "",
                "cash_on_delivery_enabled": data["cod_enabled"],
                "przelewy24_enabled": przelewy24["enabled"],
                # Without the plugin there's no mode: the plugin's default (sandbox) isn't the owner's choice.
                "przelewy24_sandbox": przelewy24["active"] and przelewy24["sandbox"],
                "przelewy24_merchant_id": przelewy24["merchant_id"],
                "przelewy24_keys_saved": przelewy24["keys"],
                "payu_enabled": payu["enabled"],
                "payu_sandbox": payu["active"] and payu["sandbox"],
                "payu_pos_id": payu["pos_id"],
                "payu_client_id": payu["client_id"],
                "payu_keys_saved": payu["keys"],
            },
            "shipping": {
                "courier_enabled": bool(courier.get("enabled")),
                **({"courier_cost": _money(courier.get("cost"))} if courier else {}),
                "free_shipping_enabled": bool(free.get("enabled")),
                **({"free_shipping_min_amount": _money(free.get("min_amount"))} if free else {}),
                "local_pickup_enabled": bool(methods.get("local_pickup", {}).get("enabled")),
            },
            "taxes": {
                "enabled": yes("woocommerce_calc_taxes"),
                "prices_include_tax": yes("woocommerce_prices_include_tax"),
                **({"standard_rate": _money(data["tax_rate"])} if data["tax_rate"] is not None else {}),
            },
            "region": {
                "language": text("WPLANG") or "en_US",
                "currency": text("woocommerce_currency"),
                # Stored as "PL" or "PL:<state>".
                "country": text("woocommerce_default_country").split(":")[0],
                "timezone": text("timezone_string") or "UTC",
            },
            **({"appearance": {"theme": theme.slug}} if theme else {}),
        }

    def apply_settings(self, shop, changes, values):
        region = changes.get("region", {})
        theme_changed = "theme" in changes.get("appearance", {})
        if "language" in region:
            self._switch_language(shop)
        if theme_changed:
            self.step_install_theme(shop)
        if "currency" in region:
            self._set_options(shop, _currency_options(region["currency"]))
        if "country" in region:
            self._set_options(shop, {"woocommerce_default_country": region["country"]})
        if "timezone" in region:
            self._set_options(shop, {"timezone_string": region["timezone"]})

        if "general" in changes:
            general = values["general"]
            self._set_options(shop, {
                "blogname": general["name"],
                "blogdescription": general["description"],
                "admin_email": general["contact_email"],
                "woocommerce_email_from_address": general["contact_email"],
                "woocommerce_email_from_name": general["name"],
            })
        if "availability" in changes:
            self._set_options(shop, {
                "woocommerce_coming_soon": "no" if values["availability"]["is_open"] else "yes",
                "woocommerce_store_pages_only": "no",
            })
        if "shopping" in changes:
            shopping = values["shopping"]
            self._set_options(shop, {
                "woocommerce_enable_guest_checkout": _yes_no(shopping["guest_checkout"]),
                "woocommerce_enable_signup_and_login_from_checkout": _yes_no(shopping["signup_at_checkout"]),
                "woocommerce_enable_reviews": _yes_no(shopping["reviews"]),
                "woocommerce_manage_stock": _yes_no(shopping["manage_stock"]),
                "woocommerce_notify_low_stock_amount": str(shopping["low_stock_threshold"]),
            })
        if "payments" in changes:
            payments = values["payments"]
            has_account = bool(payments["bank_account_number"])
            self._php(shop, PAYMENTS_PHP, {
                "bank_transfer": payments["bank_transfer_enabled"],
                "cash_on_delivery": payments["cash_on_delivery_enabled"],
                "account": {
                    "account_name": payments["bank_account_name"],
                    "account_number": payments["bank_account_number"],
                    "bank_name": payments["bank_name"],
                } if has_account else None,
            })
            self._apply_online_payments(shop, changes["payments"], payments)
        # The VAT rate and the shipping zone belong to the country; shipping titles to the language.
        if "taxes" in changes or "country" in region:
            taxes = values["taxes"]
            self._php(shop, TAXES_PHP, {
                "enabled": taxes["enabled"],
                "include": taxes["prices_include_tax"],
                "rate": taxes["standard_rate"],
                "country": values["region"]["country"],
            })
        if "shipping" in changes or "country" in region or "language" in region:
            self._apply_shipping(shop, values)
        # The sidebar depends on the theme, its titles on the language, the rating filter on reviews.
        if theme_changed or "language" in region or "reviews" in changes.get("shopping", {}):
            self.step_configure_navigation(shop)

    def reset_admin_password(self, shop):
        credentials = self._credentials(shop)
        password = secrets.token_urlsafe(18)
        self.set_admin_password(shop, password)
        credentials.admin_password = password
        credentials.save(update_fields=["admin_password", "updated_at"])

    def set_admin_password(self, shop, password):
        username = self._credentials(shop).admin_login
        self._wp(shop, "user", "update", username, f"--user_pass={password}", "--skip-email")
        # Whoever was logged in with the old password is logged out.
        self._wp_succeeds(shop, "user", "session", "destroy", username, "--all")

    def remove_sample_products(self, shop):
        pattern = "/" + SAMPLE_PRODUCT_NAME.pattern + "/u"
        return int(self._php(shop, REMOVE_SAMPLE_PRODUCTS_PHP, {"name_pattern": pattern}))

    def count_products(self, shop):
        pattern = "/" + SAMPLE_PRODUCT_NAME.pattern + "/u"
        counted = json.loads(self._php(shop, COUNT_PRODUCTS_PHP, {"name_pattern": pattern}))
        return ProductCount(products=int(counted["products"]), samples=int(counted["samples"]))

    def read_orders(self, shop, since, limit):
        rows = json.loads(self._php(shop, READ_ORDERS_PHP, {"since": int(since.timestamp()), "limit": limit}))
        return [
            Order(
                external_id=row["id"],
                number=row["number"] or row["id"],
                # Statuses added by plugins count as placed orders.
                status=ORDER_STATUSES.get(row["status"], OrderStatus.NEW),
                total=_order_total(row["total"]),
                currency=row["currency"] or shop.config.currency,
                items=row["items"],
                customer=customer_label(row["first_name"], row["last_name"]),
                placed_at=from_timestamp(row["created"] or row["modified"]),
                changed_at=from_timestamp(row["modified"] or row["created"]),
            )
            for row in rows
            if row["status"] not in SKIPPED_ORDER_STATUSES
        ]

    def read_order(self, shop, external_id):
        data = self.api(shop).get(f"orders/{int(external_id)}")
        if data["status"] in SKIPPED_ORDER_STATUSES:
            raise NotInShop("Nie ma tego zamówienia w sklepie.")
        billing, shipping = data.get("billing") or {}, data.get("shipping") or {}
        lines = []
        for item in data.get("line_items") or []:
            # Before the coupon: the discount is shown on its own.
            gross = amount(item.get("subtotal")) + amount(item.get("subtotal_tax"))
            lines.append(OrderLine(
                name=item.get("name") or "",
                sku=item.get("sku") or "",
                quantity=quantity(item.get("quantity")),
                price=_unit_price(gross, item.get("quantity")),
                total=gross,
            ))
        return OrderDetail(
            external_id=str(data["id"]),
            number=str(data.get("number") or data["id"]),
            status=ORDER_STATUSES.get(data["status"], OrderStatus.NEW),
            currency=data.get("currency") or shop.config.currency,
            products_total=sum((line.total for line in lines), amount(0)),
            shipping_total=amount(data.get("shipping_total")) + amount(data.get("shipping_tax")),
            discount_total=amount(data.get("discount_total")) + amount(data.get("discount_tax")),
            total=amount(data.get("total")),
            payment_method=data.get("payment_method_title") or "",
            shipping_method=", ".join(
                line["method_title"] for line in data.get("shipping_lines") or [] if line.get("method_title")
            ),
            customer_name=full_name(billing.get("first_name"), billing.get("last_name"))
            or full_name(shipping.get("first_name"), shipping.get("last_name")),
            email=billing.get("email") or "",
            phone=billing.get("phone") or shipping.get("phone") or "",
            billing=_order_address(billing),
            shipping=_order_address(shipping),
            lines=tuple(lines),
            customer_note=data.get("customer_note") or "",
            placed_at=datetime.fromisoformat(data["date_created_gmt"]).replace(tzinfo=UTC),
        )

    def _configure_mail(self, shop, relay):
        # A must-use plugin: WordPress loads it on its own and the panel can't switch it off.
        self._write_file(shop, MAIL_PLUGIN_PATH, MAIL_PLUGIN.read_text())
        self._set_options(shop, {MAIL_OPTION: relay})

    def _apply_online_payments(self, shop, changed, payments):
        """Install, configure and toggle the operators whose fields are in `changed`."""
        for key, plugin in ONLINE_PAYMENTS.items():
            if not any(field.startswith(f"{key}_") for field in changed):
                continue
            enabled = payments[f"{key}_enabled"]
            state = json.loads(self._php(shop, PLUGIN_STATE_PHP, {"file": plugin.file}))
            if not state["installed"] and not enabled:
                continue
            fresh = not state["installed"]
            if fresh:
                self._install_plugin(shop, plugin.package)
            # Keys only when given: blank means the shop keeps its own.
            keys = {
                field.removeprefix(f"{key}_"): payments[field] for field in OPERATORS[key].keys if payments.get(field)
            }
            account = {"sandbox": payments[f"{key}_sandbox"], **keys}
            options = {}
            if key == "przelewy24":
                self._php(shop, PRZELEWY24_ACCOUNT_PHP, {**account, "merchant_id": payments["przelewy24_merchant_id"]})
            if enabled and not state["active"]:
                self._wp(shop, "plugin", "activate", plugin.package.folder)
            if key == "payu" and (enabled or state["active"]):
                self._php(shop, PAYU_ACCOUNT_PHP, {
                    **account, "pos_id": payments["payu_pos_id"], "client_id": payments["payu_client_id"],
                    "fresh": fresh,
                })
                # Also for virtual products (e.g. e-books): PayU leaves them out unless told otherwise.
                options = {plugin.main: {
                    "sandbox": _yes_no(payments["payu_sandbox"]), "use_global": "yes",
                    **({"enable_for_virtual": "yes"} if fresh else {}),
                }}
            self._php(shop, ONLINE_GATEWAYS_PHP, {
                "prefix": plugin.prefix, "main": plugin.main, "enabled": enabled, "fresh": fresh, "options": options,
            })

    def publish_documents(self, shop, documents):
        self._write_file(shop, DOCUMENTS_PLUGIN_PATH, DOCUMENTS_PLUGIN.read_text())
        return json.loads(self._php(shop, DOCUMENTS_PHP, {"documents": [
            {"key": document.key, "option": DOCUMENT_PAGE_OPTIONS[document.key], "title": document.title,
             "slug": document.slug, "html": document.html}
            for document in documents
        ]}))

    def _install_plugin(self, shop, package):
        """From the checked archive, without activating it."""
        path = f"/tmp/{package.filename}"
        self._upload(shop, path, packages.fetch(package))
        try:
            self._wp(shop, "plugin", "install", path)
        finally:
            self._exec(container_name(shop), ["rm", "-f", path])

    def _switch_language(self, shop):
        language = shop.config.language
        if language != "en_US":
            self._wp(shop, "language", "core", "install", language)
            self._wp(shop, "language", "plugin", "install", "woocommerce", language)
            self._wp_succeeds(shop, "language", "theme", "install", shop.config.template.theme, language)
        self._wp(shop, "site", "switch-language", language)
        self._php(shop, RENAME_PAGES_PHP, SHOP_PAGE_TITLES.get(language, SHOP_PAGE_TITLES["en_US"]))

    def _apply_shipping(self, shop, values):
        shipping = values["shipping"]
        titles = SHIPPING_TITLES.get(shop.config.language, SHIPPING_TITLES["en_US"])
        min_amount = shipping["free_shipping_min_amount"]
        self._php(shop, SHIPPING_PHP, {
            "zone_name": shop.config.get_country_display(),
            "country": values["region"]["country"],
            "methods": {
                "flat_rate": {
                    "enabled": shipping["courier_enabled"],
                    "settings": {"title": titles["flat_rate"], "cost": shipping["courier_cost"], "tax_status": "taxable"},
                },
                "free_shipping": {
                    "enabled": shipping["free_shipping_enabled"],
                    "settings": {
                        "title": titles["free_shipping"],
                        "requires": "min_amount" if Decimal(min_amount) > 0 else "",
                        "min_amount": min_amount,
                        "ignore_discounts": "no",
                    },
                },
                "local_pickup": {
                    "enabled": shipping["local_pickup_enabled"],
                    "settings": {"title": titles["local_pickup"], "cost": "", "tax_status": "none"},
                },
            },
        })

    def update_address(self, shop):
        if self._find_container(shop) is None:
            return None
        self.step_start_container(shop)
        previous = self._wp(shop, "option", "get", "home")
        if previous != shop.url:
            # WordPress stores absolute URLs in options and content. GUIDs must stay as they were.
            self._wp(shop, "search-replace", previous, shop.url, "--all-tables-with-prefix", "--skip-columns=guid")
            self._wp(shop, "cache", "flush")
        return previous

    def _wp(self, shop, *args):
        return self._exec(container_name(shop), ["wp", f"--path={WP_PATH}", *args], user="www-data")

    def _wp_succeeds(self, shop, *args):
        try:
            self._wp(shop, *args)
        except CommandError:
            return False
        return True

    def _php(self, shop, code, data=None):
        """Runs PHP inside WordPress with `data` available as `$d`; returns what it printed after OUTPUT_MARKER."""
        # Passed as base64, so no value can break out of the PHP string.
        encoded = base64.b64encode(json.dumps(data if data is not None else {}).encode()).decode()
        output = self._wp(shop, "eval", f"$d = json_decode(base64_decode('{encoded}'), true); {code}")
        return output.rsplit(OUTPUT_MARKER, 1)[1] if OUTPUT_MARKER in output else output

    def _option(self, shop, name, default=""):
        """Like `wp option get`, but a missing option gives `default` instead of an error."""
        return self._php(shop, f'echo "\\n{OUTPUT_MARKER}" . get_option($d["name"], $d["default"]);',
                         {"name": name, "default": default})

    def _set_options(self, shop, options):
        self._php(shop, SET_OPTIONS_PHP, options)


def _currency_options(currency):
    comma_decimal = currency in COMMA_DECIMAL_CURRENCIES
    return {
        "woocommerce_currency": currency,
        "woocommerce_currency_pos": "right_space" if comma_decimal else "left",
        "woocommerce_price_thousand_sep": " " if comma_decimal else ",",
        "woocommerce_price_decimal_sep": "," if comma_decimal else ".",
    }


def _yes_no(value):
    return "yes" if value else "no"


def _int(value, fallback):
    """A missing WordPress option comes back as False, which isn't 0."""
    if isinstance(value, bool):
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _order_address(address):
    """An Address from WooCommerce's billing or shipping; None when it was left empty."""
    if not any(address.get(key) for key in ("first_name", "last_name", "company", "address_1", "city")):
        return None
    return Address(
        name=full_name(address.get("first_name"), address.get("last_name")),
        company=address.get("company") or "",
        lines=tuple(line for line in (address.get("address_1"), address.get("address_2")) if line),
        postcode=address.get("postcode") or "",
        city=address.get("city") or "",
        country=country_name(address.get("country")),
        phone=address.get("phone") or "",
    )


def _unit_price(total, count):
    count = quantity(count)
    return amount(total / count) if count else total


def _order_total(value):
    try:
        return Decimal(value or "0").quantize(Decimal("0.01"))
    except InvalidOperation:
        return Decimal("0.00")


def _money(value):
    """A price as "15.00"; costs typed in wp-admin may use a comma. Not a number: "0.00"."""
    try:
        return str(Decimal(str(value).replace(",", ".").replace(" ", "")).quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError):
        return "0.00"
