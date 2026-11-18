"""
PrestaShop: every shop is its own container of the official PrestaShop image (see ContainerProvisioner),
installed with the image's command-line installer and configured by PHP run inside the shop.
"""

import base64
import json
import secrets
from decimal import Decimal
from pathlib import Path

from django.conf import settings

from ..categories import category_names
from ..choices import COUNTRY_TIMEZONES
from ..models import ShopTemplate
from ..orders import Order, customer_label, from_timestamp
from ..shop_settings import OPERATORS
from . import Platform
from ..provisioning import packages
from ..provisioning.base import ProductCount, ProvisioningError
from ..provisioning.container import (
    FILES_PATH, CommandError, ContainerProvisioner, container_name, db_name, mail_relay,
)
from ..provisioning.packages import Package

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
# Our module that sends the shop's e-mail from the platform's address (see MAIL_PHP).
MAIL_MODULE = "sklepowniamail"
MAIL_MODULE_FILE = Path(__file__).parent / "files" / "prestashop" / MAIL_MODULE / f"{MAIL_MODULE}.php"
# Modules that fill a new shop's home page with demo slides and lorem ipsum.
DEMO_MODULES = ["ps_imageslider", "ps_customtext", "ps_banner"]

# Online payment operators' modules, installed the first time the owner turns the operator on.
ONLINE_PAYMENTS = {
    "przelewy24": Package(
        title="modułu Przelewy24",
        folder="przelewy24payment",
        version="1.2.1",
        url="https://www.przelewy24.pl/storage/app/media/do-pobrania/gotowe-wtyczki/prestashop/release/"
        "przelewy24_prestashop1.7.6-9_1.2.1_p24.zip",
        sha256="eaf261598e4a1eb85ddc88be8aabcafe3ab02c03841a236247266f02465d0df1",
    ),
    "payu": Package(
        title="modułu PayU",
        folder="payu",
        version="3.6.1",
        url="https://github.com/PayU-EMEA/plugin_prestashop/releases/download/v3.6.1/payu_prestashop_plugin_3.6.1.zip",
        sha256="1f66c1dcb26dedb37899eaf197a2262843233b49878fea4e7c702d328666b22e",
    ),
}

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

# The operators as the shop has them, for the shop's default currency (both keep an account per currency).
# Keys are only checked, not read.
ONLINE_PAYMENTS_PHP = """
function sklepownia_online_payments($installed) {
    $context = Context::getContext();
    $db = Db::getInstance();
    $currency = new Currency((int) Configuration::get('PS_CURRENCY_DEFAULT'));
    $przelewy24 = array(
        'active' => $installed('przelewy24payment'), 'sandbox' => false, 'merchant_id' => '', 'keys' => false,
    );
    if (Module::isInstalled('przelewy24payment')) {
        $account = $db->getRow('SELECT id_account, test_mode FROM ' . _DB_PREFIX_ . 'przelewy24_account'
            . ' WHERE id_shop = ' . (int) $context->shop->id . ' AND id_currency = ' . (int) $currency->id);
        if ($account) {
            $przelewy24['sandbox'] = (bool) $account['test_mode'];
            $credentials = $db->getRow('SELECT * FROM ' . _DB_PREFIX_ . 'przelewy24_credentials_config'
                . ' WHERE id_account = ' . (int) $account['id_account']
                . ' AND test_mode = ' . (int) $account['test_mode']);
            if ($credentials) {
                $przelewy24['merchant_id'] = (string) $credentials['id_merchant'];
                $przelewy24['keys'] = $credentials['salt'] !== '' && $credentials['api_key'] !== '';
            }
        }
    }
    $sandbox = (bool) Configuration::get('PAYU_SANDBOX');
    $payu_value = function ($name) use ($currency, $sandbox) {
        $values = Tools::unSerialize((string) Configuration::get(($sandbox ? 'SANDBOX_' : '') . $name));
        return is_array($values) && isset($values[$currency->iso_code]) ? (string) $values[$currency->iso_code] : '';
    };
    $payu = array(
        'active' => $installed('payu'),
        'sandbox' => $sandbox,
        'pos_id' => $payu_value('PAYU_MC_POS_ID'),
        'client_id' => $payu_value('PAYU_MC_OAUTH_CLIENT_ID'),
        'keys' => $payu_value('PAYU_MC_SIGNATURE_KEY') !== '' && $payu_value('PAYU_MC_OAUTH_CLIENT_SECRET') !== '',
    );
    return array('przelewy24' => $przelewy24, 'payu' => $payu);
}
"""

READ_SETTINGS_PHP = ONLINE_PAYMENTS_PHP + """
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
    'online' => sklepownia_online_payments($installed),
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


# Unpacks a module's checked archive (see _install_module) and installs it; PrestaShop turns it on.
INSTALL_MODULE_PHP = """
$zip = new ZipArchive();
if ($zip->open($d['zip']) !== true || !$zip->extractTo(_PS_MODULE_DIR_)) {
    throw new Exception('Could not unpack ' . $d['zip']);
}
$zip->close();
$module = Module::getInstanceByName($d['name']);
if (!$module) { throw new Exception('Module ' . $d['name'] . ' not found after unpacking'); }
if (!Module::isInstalled($d['name']) && !$module->install()) {
    throw new Exception('Module ' . $d['name'] . ' did not install: ' . implode(' ', $module->getErrors()));
}
"""

# The account of the default currency in test or production mode, with the merchant id as the shop id too
# (Przelewy24 gives a merchant's first shop the merchant's id). Keys only when given.
PRZELEWY24_ACCOUNT_PHP = """
$db = Db::getInstance();
$table = _DB_PREFIX_ . 'przelewy24_account';
$find = function () use ($db, $table, $context) {
    return (int) $db->getValue('SELECT id_account FROM ' . $table . ' WHERE id_shop = ' . (int) $context->shop->id
        . ' AND id_currency = ' . (int) Configuration::get('PS_CURRENCY_DEFAULT'));
};
$account = $find();
if (!$account) {
    // A currency added after the module was installed: the module makes the missing accounts itself.
    Module::getInstanceByName('przelewy24payment');
    Przelewy24\\Model\\Przlewy24AccountModel::fillAccount();
    $account = $find();
}
if (!$account) { throw new Exception('No Przelewy24 account for the default currency'); }
$test = $d['sandbox'] ? 1 : 0;
$fields = array('id_merchant' => pSQL($d['merchant_id']), 'shop_id' => pSQL($d['merchant_id']));
if (isset($d['crc_key'])) { $fields['salt'] = pSQL($d['crc_key']); }
if (isset($d['api_key'])) { $fields['api_key'] = pSQL($d['api_key']); }
$where = 'id_account = ' . $account . ' AND test_mode = ' . $test;
if ($db->getValue('SELECT COUNT(*) FROM ' . _DB_PREFIX_ . 'przelewy24_credentials_config WHERE ' . $where)) {
    $db->update('przelewy24_credentials_config', $fields, $where);
} else {
    $db->insert('przelewy24_credentials_config', array_merge(
        array('id_account' => $account, 'test_mode' => $test, 'salt' => '', 'api_key' => ''), $fields
    ));
}
$db->update('przelewy24_account', array('test_mode' => $test), 'id_account = ' . $account);
"""

# PayU keeps a value per currency in serialized arrays, with SANDBOX_ in front for test mode; only the default
# currency's changes. The installments promotion asks PayU on product pages, so a new installation has it off, and
# installments as a payment method of their own too, as in WooCommerce.
PAYU_ACCOUNT_PHP = """
$iso = (new Currency((int) Configuration::get('PS_CURRENCY_DEFAULT')))->iso_code;
$prefix = $d['sandbox'] ? 'SANDBOX_' : '';
$set = function ($name, $value) use ($iso, $prefix) {
    $values = Tools::unSerialize((string) Configuration::get($prefix . $name));
    if (!is_array($values)) { $values = array(); }
    $values[$iso] = $value;
    Configuration::updateValue($prefix . $name, serialize($values));
};
Configuration::updateValue('PAYU_SANDBOX', $d['sandbox'] ? 1 : 0);
$set('PAYU_MC_POS_ID', $d['pos_id']);
$set('PAYU_MC_OAUTH_CLIENT_ID', $d['client_id']);
if (isset($d['md5_key'])) { $set('PAYU_MC_SIGNATURE_KEY', $d['md5_key']); }
if (isset($d['client_secret'])) { $set('PAYU_MC_OAUTH_CLIENT_SECRET', $d['client_secret']); }
if ($d['fresh']) {
    foreach (array('CART', 'SUMMARY', 'PRODUCT') as $place) {
        Configuration::updateValue('PAYU_PROMOTE_CREDIT_' . $place, 0);
    }
    Configuration::updateValue('PAYU_SEPARATE_INSTALLMENTS', 0);
}
"""

PAYMENTS_PHP = """
Configuration::updateValue('BANK_WIRE_OWNER', $d['owner']);
Configuration::updateValue('BANK_WIRE_DETAILS', $d['details']);
Configuration::updateValue('BANK_WIRE_ADDRESS', $d['address']);
sklepownia_module('%(wire)s', $d['wire']);
sklepownia_module('%(cod)s', $d['cod']);
""" % {"wire": WIRE_MODULE, "cod": COD_MODULE}

# The terms take the CMS page the shop accepts at checkout (PrestaShop's own "Terms and conditions of use" at first),
# the privacy policy a page of ours, also linked in the footer next to the terms. Customers tick the terms at checkout.
# Hummingbird resets the numbers of ordered lists, which the terms' paragraphs are made of.
NUMBERED_LIST = '<ol style="list-style-type: decimal; padding-left: 2em;">'

DOCUMENTS_PHP = """
$ids = array(
    'terms' => (int) Configuration::get('PS_CONDITIONS_CMS_ID'),
    'privacy' => (int) Configuration::get('%(privacy)s'),
);
$link = new Link();
$urls = array();
foreach ($d['documents'] as $document) {
    $cms = new CMS($ids[$document['key']] ?: null);
    if (!Validate::isLoadedObject($cms)) {
        $cms = new CMS();
        $cms->id_cms_category = 1;
    }
    $cms->meta_title = $names($document['title']);
    $cms->head_seo_title = $names($document['title']);
    $cms->content = $names($document['html']);
    $cms->link_rewrite = $names($document['slug']);
    $cms->active = 1;
    $cms->indexation = 1;
    $cms->save();
    $ids[$document['key']] = (int) $cms->id;
    $urls[$document['key']] = $link->getCMSLink($cms, null, null, (int) $context->language->id);
}
Configuration::updateValue('PS_CONDITIONS', 1);
Configuration::updateValue('PS_CONDITIONS_CMS_ID', $ids['terms']);
Configuration::updateValue('%(privacy)s', $ids['privacy']);
// The footer's link block with the terms (ps_linklist) gets the privacy policy too.
$table = _DB_PREFIX_ . 'link_block';
if (Db::getInstance()->executeS("SHOW TABLES LIKE '" . pSQL($table) . "'")) {
    foreach (Db::getInstance()->executeS('SELECT id_link_block, content FROM ' . $table) as $block) {
        $content = json_decode($block['content'], true);
        $pages = array_map('intval', array_filter((array) ($content['cms'] ?? array())));
        if (!in_array($ids['terms'], $pages, true) || in_array($ids['privacy'], $pages, true)) { continue; }
        $content['cms'] = array_map('strval', array_merge($pages, array($ids['privacy'])));
        Db::getInstance()->update('link_block', array('content' => pSQL(json_encode($content))),
            'id_link_block = ' . (int) $block['id_link_block']);
    }
}
Tools::clearSmartyCache();
echo "\n%(marker)s" . json_encode($urls);
""" % {"privacy": "SKLEPOWNIA_PRIVACY_CMS_ID", "marker": OUTPUT_MARKER}

# PrestaShop sends through the relay, without logging in; the module sets the sender. 2 is Mail::METHOD_SMTP.
MAIL_PHP = """
Configuration::updateValue('PS_MAIL_METHOD', 2);
Configuration::updateValue('PS_MAIL_SERVER', $d['host']);
Configuration::updateValue('PS_MAIL_SMTP_PORT', (int) $d['port']);
Configuration::updateValue('PS_MAIL_SMTP_ENCRYPTION', 'off');
Configuration::updateValue('PS_MAIL_USER', '');
Configuration::updateValue('PS_MAIL_PASSWD', '');
Configuration::updateValue('SKLEPOWNIA_MAIL_FROM', $d['sender']);
sklepownia_module('%(module)s', true);
$module = Module::getInstanceByName('%(module)s');
// An installation cut short by an error leaves the module installed without its hook, and installing is skipped later.
if ($module && Module::isEnabled('%(module)s') && !$module->isRegisteredInHook('actionEmailSendBefore')) {
    $module->registerHook('actionEmailSendBefore');
}
$ready = $module && Module::isEnabled('%(module)s') && $module->isRegisteredInHook('actionEmailSendBefore');
echo "\\n%(marker)s" . ($ready ? 'enabled' : 'disabled');
""" % {"module": MAIL_MODULE, "marker": OUTPUT_MARKER}

REMOVE_SAMPLE_PRODUCTS_PHP = """
$removed = 0;
foreach ((array) json_decode((string) Configuration::get('%(samples)s'), true) as $id) {
    $product = new Product((int) $id);
    if (Validate::isLoadedObject($product) && $product->delete()) { $removed++; }
}
Configuration::updateValue('%(samples)s', '[]');
echo "\\n%(marker)s" . $removed;
""" % {"samples": SAMPLE_PRODUCTS_KEY, "marker": OUTPUT_MARKER}

# The samples are the products whose ids were kept at setup and that still exist.
COUNT_PRODUCTS_PHP = """
$samples = array_map('intval', (array) json_decode((string) Configuration::get('%(samples)s'), true));
$db = Db::getInstance();
$total = (int) $db->getValue('SELECT COUNT(*) FROM ' . _DB_PREFIX_ . 'product');
$left = $samples ? (int) $db->getValue(
    'SELECT COUNT(*) FROM ' . _DB_PREFIX_ . 'product WHERE id_product IN (' . implode(',', $samples) . ')'
) : 0;
echo "\\n%(marker)s" . json_encode(array('products' => $total - $left, 'samples' => $left));
""" % {"samples": SAMPLE_PRODUCTS_KEY, "marker": OUTPUT_MARKER}

# Orders straight from the database. PrestaShop stores dates in the shop's time zone (PHP's default after
# config.inc.php), so they are turned into timestamps here. A state's flags say how far the order got; the
# cancelled, refunded and payment error states are the ones the shop's configuration names.
READ_ORDERS_PHP = """
$tz = new DateTimeZone(date_default_timezone_get());
$since = (new DateTime('@' . (int) $d['since']))->setTimezone($tz)->format('Y-m-d H:i:s');
$cancelled = array_map('intval', array(
    Configuration::get('PS_OS_CANCELED'), Configuration::get('PS_OS_REFUND'), Configuration::get('PS_OS_ERROR'),
));
$p = _DB_PREFIX_;
$rows = Db::getInstance()->executeS(
    "SELECT o.id_order, o.reference, o.current_state, o.total_paid_tax_incl, o.date_add, o.date_upd,"
    . " c.iso_code, cu.firstname, cu.lastname, os.paid, os.shipped, os.delivery,"
    . " (SELECT COALESCE(SUM(od.product_quantity), 0) FROM {$p}order_detail od WHERE od.id_order = o.id_order) AS items"
    . " FROM {$p}orders o"
    . " LEFT JOIN {$p}currency c ON c.id_currency = o.id_currency"
    . " LEFT JOIN {$p}customer cu ON cu.id_customer = o.id_customer"
    . " LEFT JOIN {$p}order_state os ON os.id_order_state = o.current_state"
    . " WHERE o.date_upd >= '" . pSQL($since) . "'"
    . " ORDER BY o.date_upd, o.id_order LIMIT " . (int) $d['limit']
) ?: array();
$stamp = function ($value) use ($tz) { return (new DateTime($value, $tz))->getTimestamp(); };
$out = array();
foreach ($rows as $r) {
    if (in_array((int) $r['current_state'], $cancelled, true)) { $status = 'cancelled'; }
    elseif ($r['shipped'] || $r['delivery']) { $status = 'completed'; }
    elseif ($r['paid']) { $status = 'processing'; }
    else { $status = 'new'; }
    $out[] = array(
        'id' => (string) $r['id_order'],
        'number' => (string) $r['reference'],
        'status' => $status,
        'total' => (string) $r['total_paid_tax_incl'],
        'currency' => (string) $r['iso_code'],
        'items' => (int) $r['items'],
        'first_name' => (string) $r['firstname'],
        'last_name' => (string) $r['lastname'],
        'created' => $stamp($r['date_add']),
        'modified' => $stamp($r['date_upd']),
    );
}
echo "\n%(marker)s" . json_encode($out);
""" % {"marker": OUTPUT_MARKER}

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
        # Order confirmations and the owner's new-order alerts.
        relay = mail_relay(shop)
        if relay is not None:
            self._configure_mail(shop, relay)

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
        przelewy24, payu = data["online"]["przelewy24"], data["online"]["payu"]
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
                "przelewy24_enabled": przelewy24["active"],
                "przelewy24_sandbox": przelewy24["sandbox"],
                "przelewy24_merchant_id": przelewy24["merchant_id"],
                "przelewy24_keys_saved": przelewy24["keys"],
                "payu_enabled": payu["active"],
                "payu_sandbox": payu["sandbox"],
                "payu_pos_id": payu["pos_id"],
                "payu_client_id": payu["client_id"],
                "payu_keys_saved": payu["keys"],
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
            self._apply_online_payments(shop, changes["payments"], payments)
        if "theme" in changes.get("appearance", {}):
            self._php(shop, THEME_PHP, {"theme": shop.config.template.theme})

    def publish_documents(self, shop, documents):
        return json.loads(self._php(shop, DOCUMENTS_PHP, {"documents": [
            {"key": document.key, "title": document.title, "slug": document.slug,
             "html": document.html.replace("<ol>", NUMBERED_LIST)}
            for document in documents
        ]}))

    def reset_admin_password(self, shop):
        credentials = self._credentials(shop)
        password = secrets.token_urlsafe(18)
        # Also logs out whoever was signed in with the old one.
        self._php(shop, ADMIN_PHP, {"email": credentials.admin_login, "password": password})
        credentials.admin_password = password
        credentials.save(update_fields=["admin_password", "updated_at"])

    def remove_sample_products(self, shop):
        return int(self._php(shop, REMOVE_SAMPLE_PRODUCTS_PHP))

    def count_products(self, shop):
        counted = json.loads(self._php(shop, COUNT_PRODUCTS_PHP))
        return ProductCount(products=int(counted["products"]), samples=int(counted["samples"]))

    def read_orders(self, shop, since, limit):
        rows = json.loads(self._php(shop, READ_ORDERS_PHP, {"since": int(since.timestamp()), "limit": limit}))
        return [
            Order(
                external_id=row["id"],
                number=row["number"] or row["id"],
                status=row["status"],
                total=Decimal(row["total"] or "0").quantize(Decimal("0.01")),
                currency=row["currency"] or shop.config.currency,
                items=row["items"],
                customer=customer_label(row["first_name"], row["last_name"]),
                placed_at=from_timestamp(row["created"]),
                changed_at=from_timestamp(row["modified"]),
            )
            for row in rows
        ]

    def update_address(self, shop):
        if self._find_container(shop) is None:
            return None
        self.step_start_container(shop)
        previous = self._php(shop, ADDRESS_PHP, {"domain": _host(shop)})
        return f"{shop.url.split('://', 1)[0]}://{previous}"

    def _apply_online_payments(self, shop, changed, payments):
        """Install, configure and turn on or off the operators whose fields are in `changed`."""
        for key, package in ONLINE_PAYMENTS.items():
            if not any(field.startswith(f"{key}_") for field in changed):
                continue
            enabled = payments[f"{key}_enabled"]
            installed = self._php(
                shop, f'echo "\\n{OUTPUT_MARKER}" . (Module::isInstalled($d["name"]) ? "yes" : "no");',
                {"name": package.folder},
            ) == "yes"
            if not installed and not enabled:
                continue
            if not installed:
                self._install_module(shop, package)
            # Keys only when given: blank means the shop keeps its own.
            keys = {
                field.removeprefix(f"{key}_"): payments[field] for field in OPERATORS[key].keys if payments.get(field)
            }
            account = {"sandbox": payments[f"{key}_sandbox"], **keys}
            if key == "przelewy24":
                self._php(shop, PRZELEWY24_ACCOUNT_PHP, {**account, "merchant_id": payments["przelewy24_merchant_id"]})
            else:
                self._php(shop, PAYU_ACCOUNT_PHP, {
                    **account, "pos_id": payments["payu_pos_id"], "client_id": payments["payu_client_id"],
                    "fresh": not installed,
                })
            # Turning a module on or off may update its translations, which needs the back office's kernel.
            self._php(shop, "sklepownia_module($d['name'], $d['enabled']);",
                      {"name": package.folder, "enabled": enabled}, kernel=True)

    def _install_module(self, shop, package):
        path = f"/tmp/{package.filename}"
        self._upload(shop, path, packages.fetch(package))
        try:
            # Installing builds the module's tables and translations, which needs the back office's kernel.
            self._php(shop, INSTALL_MODULE_PHP, {"zip": path, "name": package.folder}, kernel=True)
        finally:
            self._exec(container_name(shop), ["rm", "-f", path])

    def _configure_mail(self, shop, relay):
        self._write_file(shop, f"{FILES_PATH}/modules/{MAIL_MODULE}/{MAIL_MODULE}.php", MAIL_MODULE_FILE.read_text())
        # Installing a module updates its translations, which needs the back office's kernel.
        if self._php(shop, MAIL_PHP, relay, kernel=True) != "enabled":
            raise CommandError(f"module {MAIL_MODULE} is not enabled on actionEmailSendBefore")

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
