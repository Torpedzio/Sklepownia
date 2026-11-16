"""
PrestaShop: every shop is its own container of the official PrestaShop image (see ContainerProvisioner),
installed with the image's command-line installer and configured by PHP run inside the shop.
"""

import base64
import json
import secrets

from django.conf import settings

from ..categories import category_names
from ..choices import COUNTRY_TIMEZONES
from ..models import ShopTemplate
from ..platforms import Platform
from .base import ProvisioningError
from .container import FILES_PATH, CommandError, ContainerProvisioner, container_name, db_name

SAMPLE_PRODUCT_CATEGORIES = 3
SAMPLE_PRODUCTS_PER_CATEGORY = 2
TABLE_PREFIX = "ps_"

# Output after this marker is the result, so notices PrestaShop might print before it don't break parsing.
OUTPUT_MARKER = "@@sklepownia@@"
# Configuration key with the ids of the sample products, so they can be removed later without touching
# the owner's own products (and without a marker customers could see).
SAMPLE_PRODUCTS_KEY = "SKLEPOWNIA_SAMPLE_PRODUCTS"

# The image's environment; a change means the container gets replaced. Nothing is installed automatically:
# install_prestashop runs the installer itself, with the shop's settings.
CONTAINER_ENV = {"PS_INSTALL_AUTO": "0", "PS_DEV_MODE": "0", "PS_DEMO_MODE": "0", "PS_ERASE_DB": "0"}

# Installer language codes for our WordPress-style locales.
LANGUAGES = {"pl_PL": "pl", "en_US": "en", "de_DE": "de"}

# Which file in localization/ brings each currency with its name, symbol and format.
CURRENCY_LOCALIZATION = {"PLN": "pl", "EUR": "de", "USD": "us", "GBP": "gb"}

# Payment modules the app turns on and off; cheques are switched off for good.
WIRE_MODULE = "ps_wirepayment"
COD_MODULE = "ps_cashondelivery"
CHEQUE_MODULE = "ps_checkpayment"
# Modules that fill a new shop's home page with demo slides and lorem ipsum.
DEMO_MODULES = ["ps_imageslider", "ps_customtext", "ps_banner"]

# Runs before every script: PrestaShop with its default shop, language and first employee as the context.
# `$d` holds the data passed in (see _php).
BOOTSTRAP_PHP = """
require '%(root)s/config/config.inc.php';
$context = Context::getContext();
$context->shop = new Shop((int) Configuration::get('PS_SHOP_DEFAULT'));
Shop::setContext(Shop::CONTEXT_SHOP, (int) $context->shop->id);
$context->language = new Language((int) Configuration::get('PS_LANG_DEFAULT'));
$context->employee = new Employee((int) Db::getInstance()->getValue(
    'SELECT id_employee FROM ' . _DB_PREFIX_ . 'employee WHERE id_profile = ' . (int) _PS_ADMIN_PROFILE_ . ' ORDER BY id_employee'
));
$names = function ($text) { $r = array(); foreach (Language::getIDs(false) as $id) { $r[$id] = $text; } return $r; };
function sklepownia_module($name, $enabled) {
    $module = Module::getInstanceByName($name);
    if (!$module) { return; }
    if ($enabled && !Module::isInstalled($name)) { $module->install(); }
    if (!Module::isInstalled($name)) { return; }
    if ($enabled) { $module->enable(); } else { $module->disable(); }
}
""" % {"root": FILES_PATH}

# Some services (currencies) need the Symfony kernel of the back office.
KERNEL_PHP = "global $kernel; $kernel = new AdminKernel('prod', false); $kernel->boot();"

ADMIN_PHP = """
$employee = $context->employee;
$employee->email = $d['email'];
$employee->passwd = PrestaShop\\PrestaShop\\Adapter\\ServiceLocator::get('\\\\PrestaShop\\\\PrestaShop\\\\Core\\\\Crypto\\\\Hashing')
    ->hash($d['password']);
$employee->update();
Db::getInstance()->delete('employee_session', 'id_employee = ' . (int) $employee->id);
"""

CONFIGURE_SHOP_PHP = """
$id = (int) Currency::getIdByIsoCode($d['currency'], 0, true);
if (!$id) {
    $pack = new LocalizationPack();
    $pack->loadLocalisationPack(file_get_contents(_PS_ROOT_DIR_ . '/localization/' . $d['currency_pack'] . '.xml'), array('currencies'), true);
    $id = (int) Currency::getIdByIsoCode($d['currency'], 0, true);
}
if ($id) {
    $currency = new Currency($id);
    if (!$currency->active) { $currency->active = 1; $currency->update(); }
    Configuration::updateValue('PS_CURRENCY_DEFAULT', $id);
}
foreach ($d['config'] as $key => $value) { Configuration::updateValue($key, $value); }
sklepownia_module('%(cheque)s', false);
sklepownia_module('%(wire)s', false);
sklepownia_module('%(cod)s', false);
// Demo content of the home page (slides, lorem ipsum, banner); the owner adds their own in the panel.
foreach ($d['demo_modules'] as $name) { sklepownia_module($name, false); }
echo "\\n%(marker)s" . Currency::getDefaultCurrency()->iso_code;
""" % {"cheque": CHEQUE_MODULE, "wire": WIRE_MODULE, "cod": COD_MODULE, "marker": OUTPUT_MARKER}

CATEGORIES_PHP = """
$lang = (int) $context->language->id;
$home = (int) Configuration::get('PS_HOME_CATEGORY');
$ids = array();
foreach ($d['names'] as $name) {
    $found = Category::searchByNameAndParentCategoryId($lang, $name, $home);
    if ($found) { $ids[] = (int) $found['id_category']; continue; }
    $category = new Category();
    $category->name = $names($name);
    $category->link_rewrite = $names(Tools::str2url($name));
    $category->id_parent = $home;
    $category->active = 1;
    $category->add();
    $ids[] = (int) $category->id;
}
$samples = array();
$has_products = (int) Db::getInstance()->getValue('SELECT COUNT(*) FROM ' . _DB_PREFIX_ . 'product') > 0;
if ($d['samples'] && !$has_products) {
    $number = 1;
    foreach (array_slice($ids, 0, $d['sample_categories']) as $category_id) {
        for ($i = 0; $i < $d['per_category']; $i++) {
            $name = 'Przykładowy produkt ' . $number;
            $product = new Product();
            $product->name = $names($name);
            $product->link_rewrite = $names(Tools::str2url($name));
            $product->description = $names($d['description']);
            $product->price = $number * 25 + 24.99;
            $product->id_category_default = $category_id;
            $product->active = 1;
            $product->visibility = 'both';
            $product->add();
            // On the home category too, so the home page shows them.
            $product->addToCategories(array($home, $category_id));
            StockAvailable::setQuantity($product->id, 0, 100);
            $samples[] = (int) $product->id;
            $number++;
        }
    }
    Configuration::updateValue('%(samples)s', json_encode($samples));
}
echo "\\n%(marker)s" . json_encode($ids);
""" % {"samples": SAMPLE_PRODUCTS_KEY, "marker": OUTPUT_MARKER}

NAVIGATION_PHP = """
$db = Db::getInstance();
$home = (int) Configuration::get('PS_HOME_CATEGORY');
$items = array();
foreach (Category::getChildren($home, (int) $context->language->id, true) as $category) {
    $items[] = 'CAT' . (int) $category['id_category'];
}
Configuration::updateValue('MOD_BLOCKTOPMENU_ITEMS', implode(',', $items));
$facets = Module::getInstanceByName('ps_facetedsearch');
if ($facets && Module::isInstalled('ps_facetedsearch')) {
    // The module's own default template only covers products with combinations, so ours is made here:
    // categories, price and availability on the home page, every category and the product listings.
    if (!(int) $db->getValue('SELECT COUNT(*) FROM ' . _DB_PREFIX_ . 'layered_filter')) {
        $checkbox = array('filter_type' => 0, 'filter_show_limit' => 0);
        $controllers = array_values(array_diff(array_keys($facets->getSupportedControllers()), array('search')));
        $categories = array_map('intval', array_column($db->executeS(
            'SELECT id_category FROM ' . _DB_PREFIX_ . 'category WHERE id_category != ' . (int) Configuration::get('PS_ROOT_CATEGORY')
        ), 'id_category'));
        $filters = array(
            'categories' => $categories,
            'controllers' => $controllers,
            'shop_list' => Shop::getShops(false, null, true),
            'layered_selection_subcategories' => $checkbox,
            'layered_selection_price_slider' => $checkbox,
            'layered_selection_stock' => $checkbox,
        );
        $db->insert('layered_filter', array(
            'name' => pSQL($d['template_name']),
            'filters' => pSQL(serialize($filters)),
            'n_categories' => count($categories),
            'date_add' => date('Y-m-d H:i:s'),
        ));
        $id = (int) $db->Insert_ID();
        foreach (Shop::getShops(false, null, true) as $shop_id) {
            $db->insert('layered_filter_shop', array('id_layered_filter' => $id, 'id_shop' => (int) $shop_id));
        }
    }
    $facets->buildLayeredCategories();
    $facets->fullPricesIndexProcess();
}
Tools::clearAllCache();
"""

THEME_PHP = """
$manager = (new PrestaShop\\PrestaShop\\Core\\Addon\\Theme\\ThemeManagerBuilder($context, Db::getInstance()))->build();
if ($context->shop->theme_name !== $d['theme'] && !$manager->enable($d['theme'])) {
    throw new Exception('Theme ' . $d['theme'] . ' could not be enabled');
}
Tools::clearSf2Cache();
Tools::clearAllCache();
"""

READ_SETTINGS_PHP = """
$lang = (int) $context->language->id;
$meta = Meta::getMetaByPage('index', $lang);
$installed = function ($name) { return Module::isInstalled($name) && Module::isEnabled($name); };
echo "\\n%(marker)s" . json_encode(array(
    'name' => Configuration::get('PS_SHOP_NAME'),
    'description' => $meta ? $meta['description'] : '',
    'email' => Configuration::get('PS_SHOP_EMAIL'),
    'enabled' => (bool) Configuration::get('PS_SHOP_ENABLE'),
    'wire' => $installed('%(wire)s'),
    'wire_owner' => Configuration::get('BANK_WIRE_OWNER'),
    'wire_details' => Configuration::get('BANK_WIRE_DETAILS'),
    'wire_address' => Configuration::get('BANK_WIRE_ADDRESS'),
    'cod' => $installed('%(cod)s'),
    'theme' => $context->shop->theme_name,
));
""" % {"wire": WIRE_MODULE, "cod": COD_MODULE, "marker": OUTPUT_MARKER}

GENERAL_PHP = """
Configuration::updateValue('PS_SHOP_NAME', $d['name']);
Configuration::updateValue('PS_SHOP_EMAIL', $d['email']);
$lang = (int) $context->language->id;
$found = Meta::getMetaByPage('index', $lang);
if ($found) {
    $meta = new Meta((int) $found['id_meta']);
    $meta->description[$lang] = $d['description'];
    $meta->update();
}
"""

PAYMENTS_PHP = """
Configuration::updateValue('BANK_WIRE_OWNER', $d['owner']);
Configuration::updateValue('BANK_WIRE_DETAILS', $d['details']);
Configuration::updateValue('BANK_WIRE_ADDRESS', $d['address']);
sklepownia_module('%(wire)s', $d['wire']);
sklepownia_module('%(cod)s', $d['cod']);
""" % {"wire": WIRE_MODULE, "cod": COD_MODULE}

REMOVE_SAMPLE_PRODUCTS_PHP = """
$removed = 0;
foreach ((array) json_decode((string) Configuration::get('%(samples)s'), true) as $id) {
    $product = new Product((int) $id);
    if (Validate::isLoadedObject($product) && $product->delete()) { $removed++; }
}
Configuration::updateValue('%(samples)s', '[]');
echo "\\n%(marker)s" . $removed;
""" % {"samples": SAMPLE_PRODUCTS_KEY, "marker": OUTPUT_MARKER}

ADDRESS_PHP = """
$row = Db::getInstance()->getRow('SELECT id_shop_url, domain FROM ' . _DB_PREFIX_ . 'shop_url WHERE main = 1');
if ($row['domain'] !== $d['domain']) {
    Db::getInstance()->update('shop_url', array('domain' => pSQL($d['domain']), 'domain_ssl' => pSQL($d['domain'])),
        'id_shop_url = ' . (int) $row['id_shop_url']);
    Configuration::updateGlobalValue('PS_SHOP_DOMAIN', $d['domain']);
    Configuration::updateGlobalValue('PS_SHOP_DOMAIN_SSL', $d['domain']);
    Tools::generateHtaccess();
    Tools::clearAllCache();
}
echo "\\n%(marker)s" . $row['domain'];
""" % {"marker": OUTPUT_MARKER}


class PrestaShopProvisioner(ContainerProvisioner):
    ENV_KEYS = tuple(CONTAINER_ENV)
    START_FAILED = "PrestaShop nie wystartował."

    def image(self):
        return settings.SHOPS_PRESTASHOP_IMAGE

    def container_environment(self, shop):
        return dict(CONTAINER_ENV)

    def ready_command(self):
        # The web server starts once the entrypoint has put the files in place; any answer will do.
        return ["curl", "-s", "-o", "/dev/null", "http://localhost/"]

    def default_admin_login(self, shop):
        # PrestaShop employees sign in with their e-mail address.
        return shop.config.contact_email

    # --- steps ---

    def step_install_prestashop(self, shop):
        config = shop.config
        credentials = self._credentials(shop)
        if not credentials.admin_password:
            credentials.admin_login = config.contact_email
            credentials.admin_password = secrets.token_urlsafe(18)
            credentials.save(update_fields=["admin_login", "admin_password", "updated_at"])
        if not self._installed(shop):
            # A retry after a failed installation starts over: the installer clears the tables it finds.
            self._exec(container_name(shop), [
                "php", "-d", "memory_limit=-1", f"{FILES_PATH}/install/index_cli.php",
                f"--domain={_host(shop)}",
                f"--db_server={settings.SHOPS_DB_CONTAINER}",
                f"--db_name={db_name(shop)}",
                f"--db_user={db_name(shop)}",
                f"--db_password={credentials.db_password}",
                f"--prefix={TABLE_PREFIX}",
                f"--name={shop.name}",
                f"--language={LANGUAGES.get(config.language, 'en')}",
                f"--country={config.country.lower()}",
                f"--timezone={COUNTRY_TIMEZONES.get(config.country, 'UTC')}",
                "--firstname=Właściciel",
                "--lastname=Sklepu",
                f"--email={credentials.admin_login}",
                f"--password={credentials.admin_password}",
                f"--ssl={int(settings.SHOPS_URL_SCHEME == 'https')}",
                "--newsletter=0",
                "--send_email=0",
                "--fixtures=0",
                f"--theme={config.template.theme}",
            ], user="www-data")
        # The installer gives the admin panel a random folder name, which keeps it hidden from bots.
        if not shop.admin_path:
            shop.admin_path = self._admin_folder(shop)
            shop.save(update_fields=["admin_path", "updated_at"])
        # Also covers an installation from an earlier attempt: the login is always what we stored.
        self._php(shop, ADMIN_PHP, {"email": credentials.admin_login, "password": credentials.admin_password})

    def step_configure_shop(self, shop):
        config = shop.config
        currency = self._php(shop, CONFIGURE_SHOP_PHP, {
            "currency": config.currency,
            "currency_pack": CURRENCY_LOCALIZATION.get(config.currency, "pl"),
            "demo_modules": DEMO_MODULES,
            "config": {
                "PS_SHOP_NAME": shop.name,
                "PS_SHOP_EMAIL": config.contact_email,
                "PS_SHOP_ENABLE": 1,
                "PS_GUEST_CHECKOUT_ENABLED": 1,
                "PS_STOCK_MANAGEMENT": 1,
                "PS_TIMEZONE": COUNTRY_TIMEZONES.get(config.country, "UTC"),
            },
        }, kernel=True)
        if currency != config.currency:
            raise ProvisioningError("Nie udało się ustawić waluty sklepu.")
        if config.description:
            self._php(shop, GENERAL_PHP, {
                "name": shop.name, "email": config.contact_email, "description": config.description,
            })

    def step_create_categories(self, shop):
        config = shop.config
        self._php(shop, CATEGORIES_PHP, {
            "names": category_names(config.industry, config.category_count),
            "samples": config.include_sample_products,
            "sample_categories": SAMPLE_PRODUCT_CATEGORIES,
            "per_category": SAMPLE_PRODUCTS_PER_CATEGORY,
            "description": "To jest przykładowy produkt. Zmień jego opis, zdjęcia i cenę w panelu sklepu.",
        })

    def step_configure_navigation(self, shop):
        self._php(shop, NAVIGATION_PHP, {"template_name": "Sklepownia"})

    def step_health_check(self, shop):
        self._check_pages(shop, [
            ("strona sklepu", [self.proxy_url("/")]),
            ("panel sklepu", [self.proxy_url(f"/{shop.admin_path}/login")]),
        ])

    # --- running shops ---

    def read_settings(self, shop):
        data = json.loads(self._php(shop, READ_SETTINGS_PHP))
        theme = ShopTemplate.objects.filter(platform=Platform.PRESTASHOP, theme=data["theme"]).first()
        return {
            "general": {
                "name": data["name"] or "",
                "description": data["description"] or "",
                "contact_email": data["email"] or "",
            },
            "availability": {"is_open": data["enabled"]},
            "payments": {
                "bank_transfer_enabled": data["wire"],
                "bank_account_name": data["wire_owner"] or "",
                "bank_account_number": data["wire_details"] or "",
                "bank_name": data["wire_address"] or "",
                "cash_on_delivery_enabled": data["cod"],
            },
            **({"appearance": {"theme": theme.slug}} if theme else {}),
        }

    def apply_settings(self, shop, changes, values):
        if "general" in changes:
            general = values["general"]
            self._php(shop, GENERAL_PHP, {
                "name": general["name"], "email": general["contact_email"], "description": general["description"],
            })
        if "availability" in changes:
            self._php(shop, "Configuration::updateValue('PS_SHOP_ENABLE', $d['open'] ? 1 : 0);",
                      {"open": values["availability"]["is_open"]})
        if "payments" in changes:
            payments = values["payments"]
            self._php(shop, PAYMENTS_PHP, {
                "wire": payments["bank_transfer_enabled"],
                "cod": payments["cash_on_delivery_enabled"],
                "owner": payments["bank_account_name"],
                "details": payments["bank_account_number"],
                "address": payments["bank_name"],
            })
        if "theme" in changes.get("appearance", {}):
            self._php(shop, THEME_PHP, {"theme": shop.config.template.theme})

    def reset_admin_password(self, shop):
        credentials = self._credentials(shop)
        password = secrets.token_urlsafe(18)
        # Also logs out whoever was signed in with the old one.
        self._php(shop, ADMIN_PHP, {"email": credentials.admin_login, "password": password})
        credentials.admin_password = password
        credentials.save(update_fields=["admin_password", "updated_at"])

    def remove_sample_products(self, shop):
        return int(self._php(shop, REMOVE_SAMPLE_PRODUCTS_PHP))

    def update_address(self, shop):
        if self._find_container(shop) is None:
            return None
        self.step_start_container(shop)
        previous = self._php(shop, ADDRESS_PHP, {"domain": _host(shop)})
        return f"{shop.url.split('://', 1)[0]}://{previous}"

    # --- helpers ---

    def _installed(self, shop):
        try:
            self._exec(container_name(shop), ["test", "-f", f"{FILES_PATH}/app/config/parameters.php"])
        except CommandError:
            return False
        return True

    def _admin_folder(self, shop):
        folders = self._exec(container_name(shop), ["sh", "-c", f"cd {FILES_PATH} && ls -d admin*/"]).split()
        names = [folder.rstrip("/") for folder in folders if folder.rstrip("/") not in ("admin", "admin-api")]
        if len(names) != 1:
            raise ProvisioningError("Nie znaleziono panelu sklepu.")
        return names[0]

    def _php(self, shop, code, data=None, kernel=False):
        """Runs PHP inside PrestaShop with `data` available as `$d`; returns what it printed after OUTPUT_MARKER."""
        # Passed as base64, so no value can break out of the PHP string.
        encoded = base64.b64encode(json.dumps(data if data is not None else {}).encode()).decode()
        script = "\n".join([
            f"$d = json_decode(base64_decode('{encoded}'), true);",
            BOOTSTRAP_PHP,
            KERNEL_PHP if kernel else "",
            code,
        ])
        # As the web server's user, so files it writes (cache) stay readable for the shop.
        output = self._exec(container_name(shop), ["php", "-d", "memory_limit=512M", "-r", script], user="www-data")
        return output.rsplit(OUTPUT_MARKER, 1)[1] if OUTPUT_MARKER in output else output


def _host(shop):
    """The shop's address without the scheme, with the port when it isn't the default: what PrestaShop stores."""
    return shop.url.split("://", 1)[1]
