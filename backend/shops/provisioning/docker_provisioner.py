import base64
import json
import logging
import re
import secrets
from decimal import Decimal, InvalidOperation

from django.conf import settings

from ..categories import category_names
from ..choices import COUNTRY_TIMEZONES
from ..models import ShopTemplate
from ..platforms import Platform
from .container import FILES_PATH, CommandError, ContainerProvisioner, container_env, container_name, db_name

logger = logging.getLogger(__name__)

WP_PATH = FILES_PATH
ADMIN_USERNAME = "admin"
SAMPLE_PRODUCT_CATEGORIES = 3
SAMPLE_PRODUCTS_PER_CATEGORY = 2

# Marks the sample products, so they can be removed later without touching the owner's own products.
SAMPLE_PRODUCT_META = "_sklepownia_sample"
# Older shops have unmarked sample products; they are recognised by name.
SAMPLE_PRODUCT_NAME = re.compile(r"^Przykładowy produkt \d+$")

# Where the settings keep track of the shipping zone and VAT rate they manage.
SHIPPING_ZONE_OPTION = "sklepownia_shipping_zone_id"
TAX_RATE_OPTION = "sklepownia_tax_rate_id"

# WordPress options read back into the settings (see read_settings).
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

# PHP run by `wp eval`. `$d` holds the data passed in (see _php). Output after OUTPUT_MARKER is the result,
# so notices WordPress might print before it don't break parsing.
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
echo "\n%(marker)s" . wp_json_encode(array(
    'options' => $options,
    'bacs_enabled' => is_array($bacs) && ($bacs['enabled'] ?? 'no') === 'yes',
    'bacs_account' => is_array($accounts) && $accounts ? $accounts[0] : null,
    'cod_enabled' => is_array($cod) && ($cod['enabled'] ?? 'no') === 'yes',
    'methods' => (object) $methods,
    'tax_rate' => $rate,
));
""" % {"zone": SHIPPING_ZONE_OPTION, "rate": TAX_RATE_OPTION, "marker": OUTPUT_MARKER}

SET_OPTIONS_PHP = "foreach ($d as $name => $value) { update_option($name, $value); }"

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

# Currencies written like "1 234,56 zł" rather than "$1,234.56".
COMMA_DECIMAL_CURRENCIES = {"PLN", "EUR"}

# How each theme shows the shop sidebar. `options` are PHP statements turning the sidebar on
# for the product archive, on the left; `search` is False where the header already has one.
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

# Environment of the WordPress image; a change means the container gets replaced.
WORDPRESS_ENV_KEYS = (
    "WORDPRESS_DB_HOST", "WORDPRESS_DB_NAME", "WORDPRESS_DB_USER", "WORDPRESS_DB_PASSWORD", "WORDPRESS_CONFIG_EXTRA",
)


class DockerProvisioner(ContainerProvisioner):
    """
    WooCommerce: every shop is its own WordPress container (see ContainerProvisioner).
    Mirrors infra/shops/provision-shop.sh step by step.
    """

    ENV_KEYS = WORDPRESS_ENV_KEYS
    START_FAILED = "WordPress nie wystartował."

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

    # --- steps ---

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
        credentials.wp_application_password = self._wp(
            shop, "user", "application-password", "create", username, "platform", "--porcelain",
        )
        credentials.save(update_fields=["wp_application_password", "updated_at"])

    def step_health_check(self, shop):
        credentials = self._credentials(shop)
        self._check_pages(shop, [
            ("strona sklepu", [self.proxy_url("/")]),
            ("API sklepu", ["-u", f"{credentials.admin_login}:{credentials.wp_application_password}",
                            self.proxy_url("/wp-json/wc/v3/system_status")]),
        ])

    # --- running shops ---

    def read_settings(self, shop):
        data = json.loads(self._php(shop, READ_SETTINGS_PHP, {"options": SETTINGS_OPTIONS}))
        options, methods = data["options"], data["methods"]

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
        username = credentials.admin_login
        self._wp(shop, "user", "update", username, f"--user_pass={password}", "--skip-email")
        credentials.admin_password = password
        credentials.save(update_fields=["admin_password", "updated_at"])
        # Whoever was logged in with the old password is logged out.
        self._wp_succeeds(shop, "user", "session", "destroy", username, "--all")

    def remove_sample_products(self, shop):
        pattern = "/" + SAMPLE_PRODUCT_NAME.pattern + "/u"
        return int(self._php(shop, REMOVE_SAMPLE_PRODUCTS_PHP, {"name_pattern": pattern}))

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

    # --- lifecycle ---

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

    # --- helpers ---

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


def _env(container):
    return container_env(container, WORDPRESS_ENV_KEYS)


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
    """A whole number from a WordPress option; a missing option comes back as False, which isn't 0."""
    if isinstance(value, bool):
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _money(value):
    """A price from WooCommerce settings as "15.00"; costs typed in wp-admin may use a comma. Not a number: "0.00"."""
    try:
        return str(Decimal(str(value).replace(",", ".").replace(" ", "")).quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError):
        return "0.00"
