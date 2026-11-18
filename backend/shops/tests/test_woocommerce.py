"""
WooCommerceProvisioner without Docker: commands it would run inside containers go to a fake shell,
which records them and answers with scripted output. The real setup is checked by hand on a live shop.
"""

import base64
import json
import re
from unittest.mock import MagicMock

import pytest
from docker.errors import NotFound

from accounts.models import User
from shops.models import Server, Shop, ShopConfig, ShopCredentials, ShopTemplate
from shops.provisioning.base import ProvisioningError
from shops.documents import Document
from shops.platforms.woocommerce import (
    DOCUMENTS_PLUGIN,
    DOCUMENTS_PLUGIN_PATH,
    MAIL_PLUGIN,
    MAIL_PLUGIN_PATH,
    OUTPUT_MARKER,
    SAMPLE_PRODUCT_META,
    CommandError,
    WooCommerceProvisioner,
    _currency_options,
    _env,
    _int,
)

pytestmark = pytest.mark.django_db


class Shell:
    """Stands in for `docker exec`. Later rules win, so a test can override a default answer."""

    def __init__(self):
        self.calls = []
        self.rules = []

    def on(self, *prefix, output="", fail=False):
        """Answer commands starting with `prefix` (for WP-CLI: the arguments after `wp --path=…`)."""
        self.rules.insert(0, (lambda args: tuple(args[: len(prefix)]) == prefix, output, fail))

    def on_php(self, snippet, output="", fail=False):
        """Answer `wp eval` scripts that contain `snippet`."""
        self.rules.insert(0, (lambda args: args[0] == "eval" and snippet in args[1], output, fail))

    def __call__(self, container, command, user="", environment=None):
        args = command[2:] if command[0] == "wp" else command
        self.calls.append({"container": container, "args": list(args), "user": user, "environment": environment})
        for matches, output, fail in self.rules:
            if matches(args):
                if fail:
                    raise CommandError(f"{args[0]} failed")
                return output
        return ""

    def wp(self):
        """WP-CLI argument lists in the order they ran, `wp eval` scripts left out."""
        return [call["args"] for call in self.calls if call["args"][0] != "eval" and call["user"] == "www-data"]

    def ran(self, *prefix):
        return any(tuple(args[: len(prefix)]) == prefix for args in self.wp())

    def php(self, snippet=""):
        """(script, data) of every `wp eval` whose script contains `snippet`."""
        result = []
        for call in self.calls:
            args = call["args"]
            if args[0] != "eval" or snippet not in args[1]:
                continue
            match = re.search(r"base64_decode\('([^']*)'\)", args[1])
            data = json.loads(base64.b64decode(match.group(1))) if match else None
            result.append((args[1], data))
        return result

    def options(self):
        """Every option set through _set_options, merged in order."""
        merged = {}
        for _, data in self.php("update_option($name, $value)"):
            merged.update(data)
        return merged

    def position(self, *prefix):
        return next(i for i, call in enumerate(self.calls) if tuple(call["args"][: len(prefix)]) == prefix)


@pytest.fixture
def shell(monkeypatch):
    fake = Shell()
    monkeypatch.setattr(
        WooCommerceProvisioner,
        "_exec",
        lambda self, container, command, user="", environment=None: fake(container, command, user, environment),
    )
    return fake


@pytest.fixture
def provisioner():
    instance = WooCommerceProvisioner()
    # cached_property: an instance attribute replaces the real Docker client.
    instance.__dict__["client"] = MagicMock()
    return instance


@pytest.fixture
def shop(db, settings):
    settings.SHOPS_DB_ROOT_PASSWORD = "root-secret"
    owner = User.objects.create_user(email="wlasciciel@example.com", password="Sekretne-haslo-123")
    shop = Shop.objects.create(owner=owner, name="Palarnia", slug="palarnia", status=Shop.Status.PROVISIONING)
    ShopConfig.objects.create(
        shop=shop,
        industry="food",
        template=ShopTemplate.objects.get(slug="storefront"),
        category_count=3,
        contact_email="kontakt@example.com",
        description="Kawa z małych palarni",
    )
    return shop


def settings_values(**overrides):
    values = {
        "general": {"name": "Palarnia", "description": "Kawa", "contact_email": "kontakt@example.com"},
        "availability": {"is_open": True},
        "shopping": {
            "guest_checkout": True, "signup_at_checkout": False, "reviews": True,
            "manage_stock": True, "low_stock_threshold": 2,
        },
        "payments": {
            "bank_transfer_enabled": False, "bank_account_name": "", "bank_account_number": "",
            "bank_name": "", "cash_on_delivery_enabled": False,
        },
        "shipping": {
            "courier_enabled": True, "courier_cost": "15.00", "free_shipping_enabled": True,
            "free_shipping_min_amount": "0.00", "local_pickup_enabled": False,
        },
        "taxes": {"enabled": True, "prices_include_tax": True, "standard_rate": "23.00"},
        "region": {"language": "pl_PL", "currency": "PLN", "country": "PL", "timezone": "Europe/Warsaw"},
        "appearance": {"theme": "storefront"},
    }
    for section, fields in overrides.items():
        values[section] = {**values[section], **fields}
    return values


# --- running PHP and reading options ---


def test_php_passes_data_safely_and_returns_what_follows_the_marker(provisioner, shell, shop):
    shell.on_php("echo", output=f"PHP Notice: something\n{OUTPUT_MARKER}42")
    data = {"text": "zażółć ' \" $x"}

    result = provisioner._php(shop, "echo 1;", data)

    assert result == "42"
    script, sent = shell.php("echo 1;")[0]
    assert sent == data
    # Nothing from the data appears in the script as PHP source.
    assert "zażółć" not in script


def test_option_falls_back_to_the_default(provisioner, shell, shop):
    shell.on_php("get_option", output=f"\n{OUTPUT_MARKER}no")

    assert provisioner._option(shop, "woocommerce_enable_reviews", "yes") == "no"
    assert shell.php("get_option")[0][1] == {"name": "woocommerce_enable_reviews", "default": "yes"}


# --- settings ---


def wordpress_state(**overrides):
    state = {
        "options": {
            "blogname": "Palarnia", "blogdescription": "Kawa", "admin_email": "admin@example.com",
            "WPLANG": "pl_PL", "timezone_string": "Europe/Warsaw", "stylesheet": "astra",
            "woocommerce_email_from_address": "", "woocommerce_coming_soon": "yes",
            "woocommerce_enable_guest_checkout": "yes", "woocommerce_enable_signup_and_login_from_checkout": "no",
            "woocommerce_enable_reviews": "yes", "woocommerce_manage_stock": "no",
            "woocommerce_notify_low_stock_amount": "4", "woocommerce_currency": "EUR",
            "woocommerce_default_country": "DE:BE", "woocommerce_calc_taxes": "yes",
            "woocommerce_prices_include_tax": "no",
        },
        "bacs_enabled": True,
        "bacs_account": {"account_name": "Jan", "account_number": "", "iban": "DE89370400440532013000", "bank_name": ""},
        "cod_enabled": False,
        "methods": {
            "flat_rate": {"enabled": True, "cost": "12,5", "min_amount": ""},
            "free_shipping": {"enabled": False, "cost": "", "min_amount": "199"},
        },
        "tax_rate": "19.0000",
        "online": {
            # Without the plugin WordPress has no p24_mode, which the plugin reads as sandbox.
            "przelewy24": {"active": False, "enabled": False, "sandbox": True, "merchant_id": "", "keys": False},
            "payu": {"active": True, "enabled": True, "sandbox": True, "pos_id": "300746", "client_id": "300746",
                     "keys": True},
        },
    }
    state.update(overrides)
    return f"\n{OUTPUT_MARKER}{json.dumps(state)}"


def test_read_settings_turns_wordpress_options_into_sections(provisioner, shell, shop):
    shell.on_php("bacs_account", output=wordpress_state())

    values = provisioner.read_settings(shop)

    assert values == {
        "general": {"name": "Palarnia", "description": "Kawa", "contact_email": "admin@example.com"},
        "availability": {"is_open": False},
        "shopping": {
            "guest_checkout": True, "signup_at_checkout": False, "reviews": True,
            "manage_stock": False, "low_stock_threshold": 4,
        },
        "payments": {
            "bank_transfer_enabled": True, "bank_account_name": "Jan",
            "bank_account_number": "DE89370400440532013000", "bank_name": "", "cash_on_delivery_enabled": False,
            "przelewy24_enabled": False, "przelewy24_sandbox": False, "przelewy24_merchant_id": "",
            "przelewy24_keys_saved": False,
            "payu_enabled": True, "payu_sandbox": True, "payu_pos_id": "300746", "payu_client_id": "300746",
            "payu_keys_saved": True,
        },
        "shipping": {
            "courier_enabled": True, "courier_cost": "12.50",
            "free_shipping_enabled": False, "free_shipping_min_amount": "199.00", "local_pickup_enabled": False,
        },
        "taxes": {"enabled": True, "prices_include_tax": False, "standard_rate": "19.00"},
        "region": {"language": "pl_PL", "currency": "EUR", "country": "DE", "timezone": "Europe/Warsaw"},
        "appearance": {"theme": "astra"},
    }


def test_read_settings_leaves_out_what_the_shop_does_not_have(provisioner, shell, shop):
    state = json.loads(wordpress_state(methods={}, tax_rate=None, bacs_account=None).split(OUTPUT_MARKER)[1])
    state["options"].update({"stylesheet": "twentytwentyfive", "WPLANG": "", "woocommerce_notify_low_stock_amount": False})
    shell.on_php("bacs_account", output=OUTPUT_MARKER + json.dumps(state))

    values = provisioner.read_settings(shop)

    # Missing fields are filled from what the platform stored before (shop_settings.complete).
    assert "courier_cost" not in values["shipping"]
    assert "standard_rate" not in values["taxes"]
    assert "appearance" not in values
    assert values["region"]["language"] == "en_US"
    assert values["shopping"]["low_stock_threshold"] == 2
    assert values["payments"]["bank_account_number"] == ""


def test_apply_settings_touches_only_changed_sections(provisioner, shell, shop):
    values = settings_values(general={"name": "Nowa nazwa", "contact_email": "nowy@example.com"})

    provisioner.apply_settings(shop, {"general": {"name": "Nowa nazwa", "contact_email": "nowy@example.com"}}, values)

    assert shell.options() == {
        "blogname": "Nowa nazwa",
        "blogdescription": "Kawa",
        "admin_email": "nowy@example.com",
        "woocommerce_email_from_address": "nowy@example.com",
        "woocommerce_email_from_name": "Nowa nazwa",
    }
    assert shell.wp() == []
    assert len(shell.php()) == 1


def test_apply_settings_writes_availability_and_shopping_options(provisioner, shell, shop):
    values = settings_values(availability={"is_open": False}, shopping={"manage_stock": False, "low_stock_threshold": 7})

    provisioner.apply_settings(shop, {"availability": {"is_open": False}, "shopping": {"low_stock_threshold": 7}}, values)

    options = shell.options()
    assert options["woocommerce_coming_soon"] == "yes"
    assert options["woocommerce_manage_stock"] == "no"
    assert options["woocommerce_notify_low_stock_amount"] == "7"
    assert options["woocommerce_enable_guest_checkout"] == "yes"


@pytest.mark.parametrize(("number", "account"), [
    ("61 1090 1014 0000 0712 1981 2874",
     {"account_name": "Jan", "account_number": "61 1090 1014 0000 0712 1981 2874", "bank_name": "Santander"}),
    ("", None),
])
def test_apply_settings_writes_payment_methods(provisioner, shell, shop, number, account):
    payments = {
        "bank_transfer_enabled": bool(number), "bank_account_name": "Jan", "bank_account_number": number,
        "bank_name": "Santander", "cash_on_delivery_enabled": True,
    }

    provisioner.apply_settings(shop, {"payments": payments}, settings_values(payments=payments))

    [(_, data)] = shell.php("woocommerce_bacs_settings")
    assert data == {"bank_transfer": bool(number), "cash_on_delivery": True, "account": account}


def test_apply_settings_writes_tax_rate_for_the_shop_country(provisioner, shell, shop):
    values = settings_values(taxes={"prices_include_tax": False, "standard_rate": "8.00"})

    provisioner.apply_settings(shop, {"taxes": {"standard_rate": "8.00"}}, values)

    [(_, data)] = shell.php("WC_Tax::")
    assert data == {"enabled": True, "include": False, "rate": "8.00", "country": "PL"}
    assert shell.php("WC_Shipping_Zone") == []


def test_apply_settings_builds_the_shipping_zone(provisioner, shell, shop):
    values = settings_values()

    provisioner.apply_settings(shop, {"shipping": {"courier_cost": "15.00"}}, values)

    [(_, data)] = shell.php("WC_Shipping_Zone")
    assert data["zone_name"] == "Polska"
    assert data["country"] == "PL"
    methods = data["methods"]
    assert methods["flat_rate"] == {
        "enabled": True, "settings": {"title": "Kurier", "cost": "15.00", "tax_status": "taxable"},
    }
    # A free shipping threshold of 0 means always free.
    assert methods["free_shipping"]["settings"]["requires"] == ""
    assert methods["local_pickup"]["enabled"] is False


def test_new_language_country_and_theme_are_applied_in_order(provisioner, shell, shop):
    shop.config.language = "de_DE"
    shop.config.country = "DE"
    shop.config.template = ShopTemplate.objects.get(slug="astra")
    shell.on("option", "get", "stylesheet", output="storefront")
    shell.on_php("get_option", output=f"{OUTPUT_MARKER}yes")
    values = settings_values(region={"language": "de_DE", "country": "DE", "timezone": "Europe/Berlin"})
    changes = {"region": {"language": "de_DE", "country": "DE", "timezone": "Europe/Berlin"},
               "appearance": {"theme": "astra"}}

    provisioner.apply_settings(shop, changes, values)

    assert shell.ran("language", "core", "install", "de_DE")
    assert shell.ran("language", "plugin", "install", "woocommerce", "de_DE")
    [(_, titles)] = shell.php("wc_get_page_id")
    assert titles["cart"] == "Warenkorb"
    # The theme is switched after the language, and the sidebar rebuilt once, for the new theme.
    assert shell.position("site", "switch-language", "de_DE") < shell.position("theme", "activate", "astra")
    assert shell.position("theme", "activate", "astra") < shell.position("widget", "add")
    assert {args[3] for args in shell.wp() if args[:2] == ["widget", "add"]} == {"astra-woo-shop-sidebar"}
    assert [args[2] for args in shell.wp() if args[:2] == ["widget", "add"]][-1] == "woocommerce_rating_filter"
    assert shell.options()["woocommerce_default_country"] == "DE"
    assert shell.options()["timezone_string"] == "Europe/Berlin"
    assert shell.php("WC_Tax::")[0][1]["country"] == "DE"
    assert shell.php("WC_Shipping_Zone")[0][1]["methods"]["free_shipping"]["settings"]["title"] == "Kostenloser Versand"


def test_switching_back_to_english_installs_no_language_packs(provisioner, shell, shop):
    shop.config.language = "en_US"
    values = settings_values(region={"language": "en_US"})

    provisioner.apply_settings(shop, {"region": {"language": "en_US"}}, values)

    assert shell.ran("site", "switch-language", "en_US")
    assert not shell.ran("language")
    assert shell.php("wc_get_page_id")[0][1]["cart"] == "Cart"


def test_new_currency_sets_its_price_format(provisioner, shell, shop):
    provisioner.apply_settings(shop, {"region": {"currency": "USD"}}, settings_values(region={"currency": "USD"}))

    assert shell.options() == _currency_options("USD")
    assert _currency_options("USD")["woocommerce_currency_pos"] == "left"
    assert _currency_options("PLN")["woocommerce_price_decimal_sep"] == ","


def test_turning_reviews_off_rebuilds_the_sidebar_without_the_rating_filter(provisioner, shell, shop):
    shell.on_php("get_option", output=f"{OUTPUT_MARKER}no")
    values = settings_values(shopping={"reviews": False})

    provisioner.apply_settings(shop, {"shopping": {"reviews": False}}, values)

    widgets = [args[2] for args in shell.wp() if args[:2] == ["widget", "add"]]
    assert widgets == ["woocommerce_product_categories", "woocommerce_layered_nav_filters", "woocommerce_price_filter"]


def test_reset_admin_password_changes_it_in_wordpress_and_logs_everyone_out(provisioner, shell, shop):
    ShopCredentials.objects.create(shop=shop, admin_login="admin", admin_password="stare")

    provisioner.reset_admin_password(shop)

    password = ShopCredentials.objects.get(shop=shop).admin_password
    assert password != "stare"
    assert ["user", "update", "admin", f"--user_pass={password}", "--skip-email"] in shell.wp()
    assert shell.ran("user", "session", "destroy", "admin", "--all")


def test_remove_sample_products_counts_what_was_removed(provisioner, shell, shop):
    shell.on_php("wc_get_products", output=f"\n{OUTPUT_MARKER}6")

    assert provisioner.remove_sample_products(shop) == 6
    script, data = shell.php("wc_get_products")[0]
    assert SAMPLE_PRODUCT_META in script
    assert re.match(data["name_pattern"][1:-2], "Przykładowy produkt 12")


# --- provisioning steps ---


def test_allocate_server_picks_one_with_room(provisioner, shop):
    Server.objects.update(max_shops=0)
    roomy = Server.objects.create(name="drugi", hostname="drugi.example.com", max_shops=5)

    provisioner.step_allocate_server(shop)

    assert shop.server == roomy


def test_allocate_server_fails_when_all_are_full(provisioner, shop):
    Server.objects.update(max_shops=0)

    with pytest.raises(ProvisioningError, match="Brak wolnego serwera"):
        provisioner.step_allocate_server(shop)


def test_create_database_makes_a_password_once_and_grants_access(provisioner, shell, shop):
    provisioner.step_create_database(shop)
    provisioner.step_create_database(shop)

    password = ShopCredentials.objects.get(shop=shop).db_password
    statements = [call for call in shell.calls if call["container"] == "shops-db"]
    assert len(statements) == 2
    assert all(password in call["args"][-1] for call in statements)
    assert f"CREATE DATABASE IF NOT EXISTS `shop_{shop.pk}`" in statements[0]["args"][-1]
    assert statements[0]["environment"] == {"MYSQL_PWD": "root-secret"}


def test_sql_needs_the_root_password(provisioner, shell, shop, settings):
    settings.SHOPS_DB_ROOT_PASSWORD = ""

    with pytest.raises(CommandError):
        provisioner.step_create_database(shop)


def test_start_container_creates_a_new_one_behind_the_proxy(provisioner, shop):
    containers = provisioner.client.containers
    containers.get.side_effect = NotFound("brak")
    container = containers.run.return_value
    container.exec_run.return_value.exit_code = 0

    provisioner.step_start_container(shop)

    kwargs = containers.run.call_args.kwargs
    assert kwargs["name"] == f"shop-{shop.pk}"
    assert kwargs["labels"][f"traefik.http.routers.shop-{shop.pk}.rule"] == f"Host(`{shop.domain}`)"
    assert kwargs["environment"]["WORDPRESS_DB_NAME"] == f"shop_{shop.pk}"
    container.start.assert_called_once()


def test_start_container_replaces_one_with_outdated_settings(provisioner, shop):
    old = MagicMock(labels={}, attrs={"Config": {"Env": ["WORDPRESS_DB_HOST=stary"]}})
    provisioner.client.containers.get.return_value = old
    provisioner.client.containers.run.return_value.exec_run.return_value.exit_code = 0

    provisioner.step_start_container(shop)

    old.remove.assert_called_once_with(force=True)
    provisioner.client.containers.run.assert_called_once()


def test_start_container_gives_up_when_wordpress_never_starts(provisioner, shop, monkeypatch):
    monkeypatch.setattr("shops.provisioning.container.time.sleep", lambda seconds: None)
    provisioner.client.containers.get.side_effect = NotFound("brak")
    provisioner.client.containers.run.return_value.exec_run.return_value.exit_code = 1

    with pytest.raises(ProvisioningError, match="nie wystartował"):
        provisioner.step_start_container(shop)


def test_install_wordpress_on_a_fresh_container(provisioner, shell, shop):
    shell.on("core", "is-installed", fail=True)
    shell.on("post", "list", output="1 2")

    provisioner.step_install_wordpress(shop)

    credentials = ShopCredentials.objects.get(shop=shop)
    assert credentials.admin_password
    install = next(args for args in shell.wp() if args[:2] == ["core", "install"])
    assert f"--admin_password={credentials.admin_password}" in install
    assert ["post", "delete", "1", "2", "--force"] in shell.wp()
    assert ["option", "update", "blogdescription", "Kawa z małych palarni"] in shell.wp()


def test_install_wordpress_fixes_a_password_that_was_never_stored(provisioner, shell, shop):
    provisioner.step_install_wordpress(shop)

    password = ShopCredentials.objects.get(shop=shop).admin_password
    assert ["user", "update", "admin", f"--user_pass={password}", "--skip-email"] in shell.wp()
    assert not shell.ran("core", "install")


@pytest.mark.parametrize(("language", "installs"), [("pl_PL", True), ("en_US", False)])
def test_configure_locale(provisioner, shell, shop, language, installs):
    shop.config.language = language

    provisioner.step_configure_locale(shop)

    assert shell.ran("language", "core", "install", language) is installs
    assert ["option", "update", "timezone_string", "Europe/Warsaw"] in shell.wp()


def test_configure_woocommerce_activates_it_and_opens_the_shop(provisioner, shell, shop):
    shell.on("plugin", "is-active", fail=True)
    shell.on("option", "get", "woocommerce_shop_page_id", output="6")

    provisioner.step_configure_woocommerce(shop)

    assert shell.position("language", "plugin", "install") < shell.position("plugin", "activate")
    assert ["option", "update", "woocommerce_coming_soon", "no"] in shell.wp()
    assert ["option", "update", "woocommerce_currency_pos", "right_space"] in shell.wp()
    assert ["option", "update", "page_on_front", "6"] in shell.wp()


@pytest.mark.parametrize(("active", "activates"), [("twentytwentyfive", True), ("storefront", False)])
def test_install_theme(provisioner, shell, shop, active, activates):
    shell.on("option", "get", "stylesheet", output=active)

    provisioner.step_install_theme(shop)

    assert shell.ran("theme", "activate", "storefront") is activates
    assert shell.ran("language", "theme", "install", "storefront", "pl_PL")


def test_create_categories_replaces_the_default_and_adds_marked_samples(provisioner, shell, shop):
    shell.on("term", "list", output="")
    shell.on("wc", "product_cat", "create", output="11")
    shell.on("option", "get", "default_product_cat", output="1")
    shell.on("wc", "product", "list", output="0")

    provisioner.step_create_categories(shop)

    assert ["option", "update", "default_product_cat", "11"] in shell.wp()
    assert shell.ran("term", "delete", "product_cat", "1")
    products = [args for args in shell.wp() if args[:3] == ["wc", "product", "create"]]
    assert len(products) == 6
    assert all(any(SAMPLE_PRODUCT_META in arg for arg in args) for args in products)


def test_create_categories_keeps_existing_products(provisioner, shell, shop):
    shell.on("term", "list", output="5")
    shell.on("option", "get", "default_product_cat", output="5")
    shell.on("wc", "product", "list", output="3")

    provisioner.step_create_categories(shop)

    assert not shell.ran("wc", "product_cat", "create")
    assert not shell.ran("wc", "product", "create")


def test_configure_navigation_skips_unknown_themes(provisioner, shell, shop):
    shop.config.template = ShopTemplate(slug="inny", name="Inny", theme="inny")

    provisioner.step_configure_navigation(shop)

    assert shell.calls == []


def test_generate_api_keys_replaces_the_old_one(provisioner, shell, shop):
    ShopCredentials.objects.create(shop=shop, admin_login="admin")
    shell.on("user", "application-password", "list", output="uuid-1")
    shell.on("user", "application-password", "create", output="nowe-haslo")

    provisioner.step_generate_api_keys(shop)

    assert shell.ran("user", "application-password", "delete", "admin", "uuid-1")
    assert ShopCredentials.objects.get(shop=shop).wp_application_password == "nowe-haslo"


def test_health_check_passes_when_shop_and_api_answer(provisioner, shell, shop):
    shell.on("curl", output="200")

    provisioner.step_health_check(shop)

    assert all(f"Host: {shop.domain}" in " ".join(call["args"]) for call in shell.calls)


def test_health_check_reports_what_failed(provisioner, shell, shop):
    shell.on("curl", output="500")

    with pytest.raises(ProvisioningError, match="strona sklepu: HTTP 500"):
        provisioner.step_health_check(shop)


# --- lifecycle ---


def test_teardown_removes_container_volume_and_database(provisioner, shell, shop):
    container = provisioner.client.containers.get.return_value
    provisioner.client.volumes.get.side_effect = NotFound("brak")

    provisioner.teardown(shop)

    container.remove.assert_called_once_with(force=True)
    assert f"DROP DATABASE IF EXISTS `shop_{shop.pk}`" in shell.calls[-1]["args"][-1]


def test_update_address_skips_shops_without_a_container(provisioner, shop):
    provisioner.client.containers.get.side_effect = NotFound("brak")

    assert provisioner.update_address(shop) is None


def test_update_address_replaces_the_old_address(provisioner, shell, shop, monkeypatch):
    monkeypatch.setattr(WooCommerceProvisioner, "step_start_container", lambda self, shop: None)
    shell.on("option", "get", "home", output="http://palarnia.stary.example")

    previous = provisioner.update_address(shop)

    assert previous == "http://palarnia.stary.example"
    assert ["search-replace", previous, shop.url, "--all-tables-with-prefix", "--skip-columns=guid"] in shell.wp()


# --- e-mail ---


@pytest.fixture
def relay(settings):
    settings.SHOPS_SMTP_HOST = "shops-mail"
    settings.SHOPS_SMTP_PORT = 1025
    settings.SHOPS_MAIL_DOMAIN = "sklepy.example.pl"


def test_configure_woocommerce_sends_mail_through_the_relay(provisioner, shell, shop, relay):
    provisioner.step_configure_woocommerce(shop)

    [write] = [call for call in shell.calls if call["args"][:2] == ["sh", "-c"]]
    assert write["user"] == "www-data"
    assert write["environment"] == {"FILE": MAIL_PLUGIN_PATH, "CONTENT": MAIL_PLUGIN.read_text()}
    assert shell.options()["sklepownia_mail"] == {
        "host": "shops-mail", "port": 1025, "sender": "palarnia@sklepy.example.pl",
    }
    # The owner's address stays the sender WooCommerce knows; the plugin turns it into the Reply-To.
    assert ["option", "update", "woocommerce_email_from_address", "kontakt@example.com"] in shell.wp()


def test_without_a_mail_server_shops_are_left_as_they_are(provisioner, shell, shop, settings):
    settings.SHOPS_SMTP_HOST = ""

    provisioner.step_configure_woocommerce(shop)

    assert not any(call["args"][:2] == ["sh", "-c"] for call in shell.calls)
    assert "sklepownia_mail" not in shell.options()


def test_mail_plugin_keeps_the_owner_as_reply_to():
    plugin = MAIL_PLUGIN.read_text()

    assert "add_action('phpmailer_init'" in plugin
    assert "$mailer->addReplyTo(" in plugin and "$mailer->setFrom($mail['sender']" in plugin
    assert "get_option('sklepownia_mail')" in plugin


def test_configure_mail_on_a_running_shop_replaces_a_container_of_an_older_image(provisioner, shell, shop, relay):
    old = MagicMock(labels={}, attrs={"Config": {"Env": []}})
    old.image.id = "sha256:stary"
    provisioner.client.containers.get.return_value = old
    provisioner.client.images.get.return_value.id = "sha256:nowy"
    provisioner.client.containers.run.return_value.exec_run.return_value.exit_code = 0

    assert provisioner.configure_mail(shop) is True

    old.remove.assert_called_once_with(force=True)
    provisioner.client.containers.run.assert_called_once()
    assert shell.options()["sklepownia_mail"]["sender"] == "palarnia@sklepy.example.pl"


def test_configure_mail_skips_shops_without_a_container_or_a_mail_server(provisioner, shell, shop, settings):
    provisioner.client.containers.get.side_effect = NotFound("brak")
    assert provisioner.configure_mail(shop) is False

    provisioner.client.containers.get.side_effect = None
    settings.SHOPS_SMTP_HOST = ""
    assert provisioner.configure_mail(shop) is False
    assert shell.options() == {}


def test_a_container_of_the_current_image_is_kept(provisioner, shop):
    current = MagicMock(labels={}, attrs={"Config": {"Env": []}})
    current.image.id = "sha256:ten-sam"
    provisioner.client.images.get.return_value.id = "sha256:ten-sam"
    provisioner.client.containers.get.return_value = current
    current.exec_run.return_value.exit_code = 0
    environment = provisioner.container_environment(shop)
    current.attrs["Config"]["Env"] = [f"{key}={value}" for key, value in environment.items()]
    current.attrs["HostConfig"] = {"Memory": 512 * 1024 ** 2}
    current.labels = {
        "traefik.enable": "true",
        f"traefik.http.routers.shop-{shop.pk}.rule": f"Host(`{shop.domain}`)",
        f"traefik.http.routers.shop-{shop.pk}.entrypoints": "web",
        f"traefik.http.services.shop-{shop.pk}.loadbalancer.server.port": "80",
        "shops.id": str(shop.pk),
        "shops.slug": shop.slug,
    }

    provisioner.step_start_container(shop)

    current.remove.assert_not_called()
    current.start.assert_called_once()


def test_a_missing_image_keeps_the_container(provisioner, shop):
    container = MagicMock()
    provisioner.client.images.get.side_effect = NotFound("brak")

    assert provisioner._image_changed(container) is False


def test_shops_send_from_their_own_address(shop, settings):
    settings.SHOPS_MAIL_DOMAIN = "sklepy.example.pl"

    assert shop.mail_sender == "palarnia@sklepy.example.pl"


# --- helpers ---


def test_failed_command_names_only_the_command(provisioner):
    result = provisioner.client.containers.get.return_value.exec_run.return_value
    result.exit_code = 1
    result.output = b"Error: something"

    with pytest.raises(CommandError) as error:
        provisioner._exec("shop-1", ["wp", "--path=/var/www/html", "user", "update", "--user_pass=tajne"])

    assert "tajne" not in str(error.value)
    assert "exited with 1: Error: something" in str(error.value)


def test_helpers():
    container = MagicMock(attrs={"Config": {"Env": ["WORDPRESS_DB_NAME=shop_1", "BROKEN"]}})

    assert _env(container)["WORDPRESS_DB_NAME"] == "shop_1"
    assert _env(container)["WORDPRESS_DB_HOST"] is None
    assert _int("7", 2) == 7
    assert _int(False, 2) == 2


@pytest.mark.parametrize(("plan_code", "is_test", "memory"), [
    ("business", False, "1024m"),
    ("standard", False, "512m"),
    ("business", True, "512m"),
    (None, False, "512m"),
])
def test_shop_memory_comes_from_the_owners_plan(provisioner, shop, settings, plan_code, is_test, memory):
    from billing.models import Plan
    from conftest import subscribe

    settings.SHOPS_CONTAINER_MEMORY = "512m"
    if plan_code:
        subscribe(shop.owner, Plan.objects.get(code=plan_code))
    shop.is_test = is_test
    provisioner.client.containers.get.side_effect = NotFound("brak")
    provisioner.client.containers.run.return_value.exec_run.return_value.exit_code = 0

    provisioner.step_start_container(shop)

    assert provisioner.client.containers.run.call_args.kwargs["mem_limit"] == memory


def test_suspending_stops_the_container_and_keeps_it(provisioner, shop):
    container = provisioner.client.containers.get.return_value

    provisioner.suspend(shop)

    container.stop.assert_called_once()
    container.remove.assert_not_called()


def test_suspending_a_shop_without_a_container_does_nothing(provisioner, shop):
    provisioner.client.containers.get.side_effect = NotFound("brak")

    provisioner.suspend(shop)
    provisioner.refresh_resources(shop)

    provisioner.client.containers.run.assert_not_called()


def test_resuming_starts_the_container_again(provisioner, shop, monkeypatch):
    started = []
    monkeypatch.setattr(WooCommerceProvisioner, "step_start_container", lambda self, shop: started.append(shop.pk))

    provisioner.resume(shop)
    provisioner.refresh_resources(shop)

    assert started == [shop.pk, shop.pk]


def test_a_new_memory_limit_recreates_the_container(provisioner, shop, settings):
    from billing.models import Plan
    from conftest import subscribe

    settings.SHOPS_CONTAINER_MEMORY = "512m"
    subscribe(shop.owner, Plan.objects.get(code="business"))
    environment_probe = MagicMock(labels={}, attrs={"Config": {"Env": []}, "HostConfig": {"Memory": 512 * 1024 ** 2}})
    provisioner.client.containers.get.return_value = environment_probe
    provisioner.client.containers.run.return_value.exec_run.return_value.exit_code = 0

    provisioner.step_start_container(shop)

    environment_probe.remove.assert_called_once_with(force=True)
    assert provisioner.client.containers.run.call_args.kwargs["mem_limit"] == "1024m"


@pytest.mark.parametrize(("limit", "expected"), [("512m", 512 * 1024 ** 2), ("1g", 1024 ** 3), ("1048576", 1048576)])
def test_memory_limits_in_bytes(limit, expected):
    from shops.provisioning.container import memory_bytes as _memory_bytes

    assert _memory_bytes(limit) == expected


# --- orders for the sales overview ---


def test_orders_are_read_through_woocommerce_and_named_by_initial(provisioner, shell, shop):
    from datetime import UTC, datetime
    from decimal import Decimal

    rows = [
        {"id": "41", "number": "41", "status": "on-hold", "total": "149.9", "currency": "PLN", "items": 3,
         "first_name": "Anna", "last_name": "Nowak", "created": 1794000000, "modified": 1794000600},
        {"id": "42", "number": "", "status": "completed", "total": "20.00", "currency": "", "items": 1,
         "first_name": "", "last_name": "", "created": 1794001000, "modified": 0},
        {"id": "43", "number": "43", "status": "checkout-draft", "total": "5.00", "currency": "PLN", "items": 1,
         "first_name": "", "last_name": "", "created": 1794002000, "modified": 1794002000},
        {"id": "44", "number": "44", "status": "custom-packing", "total": "5.00", "currency": "EUR", "items": 1,
         "first_name": "Jan", "last_name": "", "created": 1794003000, "modified": 1794003000},
    ]
    shell.on_php("wc_get_orders", output=f"Notice\n{OUTPUT_MARKER}{json.dumps(rows)}")

    orders = provisioner.read_orders(shop, datetime(2026, 11, 1, tzinfo=UTC), 500)

    [(script, data)] = shell.php("wc_get_orders")
    assert data == {"since": int(datetime(2026, 11, 1, tzinfo=UTC).timestamp()), "limit": 500}
    assert [(o.external_id, o.number, o.status, o.total, o.currency, o.items, o.customer) for o in orders] == [
        ("41", "41", "new", Decimal("149.90"), "PLN", 3, "Anna N."),
        ("42", "42", "completed", Decimal("20.00"), "PLN", 1, ""),
        ("44", "44", "new", Decimal("5.00"), "EUR", 1, "Jan"),
    ]
    assert orders[0].placed_at == datetime.fromtimestamp(1794000000, tz=UTC)
    assert orders[0].changed_at == datetime.fromtimestamp(1794000600, tz=UTC)
    assert orders[1].changed_at == orders[1].placed_at


def test_products_are_counted_with_the_samples_apart(provisioner, shell, shop):
    from shops.provisioning.base import ProductCount

    shell.on_php("_sklepownia_sample", output=f"Notice\n{OUTPUT_MARKER}" + json.dumps({"products": 4, "samples": 2}))

    assert provisioner.count_products(shop) == ProductCount(products=4, samples=2)

    [(script, data)] = shell.php("$wpdb->posts")
    # Older shops' samples have no mark, only the name.
    assert data == {"name_pattern": "/^Przykładowy produkt \\d+$/u"}
    assert "LIKE %s" in script and "'trash'" not in script


# --- online payments ---

P24_KEYS = {"przelewy24_crc_key": "0123456789abcdef", "przelewy24_api_key": "0123456789abcdef0123456789abcdef"}
PAYU_KEYS = {"payu_md5_key": "13a980d4f851f3d9a1cfc792fb1f5e50", "payu_client_secret": "12f071174cb7eb79d4aac5bc2f07563f"}


@pytest.fixture
def archives(monkeypatch):
    """The checked archives the worker would hand the shop, without downloading anything."""
    fetched = []

    def fetch(package):
        fetched.append(package)
        return f"archiwum {package.folder}".encode()

    monkeypatch.setattr("shops.provisioning.packages.fetch", fetch)
    return fetched


def plugin_state(shell, installed, active):
    shell.on_php("get_plugins()", output=f"\n{OUTPUT_MARKER}" + json.dumps({"installed": installed, "active": active}))


def change_payments(provisioner, shop, **changed):
    from shops.shop_settings import _operator_defaults

    payments = {**settings_values()["payments"], **_operator_defaults(), **changed}
    provisioner.apply_settings(shop, {"payments": changed}, settings_values(payments=payments))


def index_of(shell, snippet):
    """Where in the run the PHP script containing `snippet`, or the WP-CLI command (tuple), came."""
    for i, call in enumerate(shell.calls):
        args = call["args"]
        if isinstance(snippet, tuple) and tuple(args[: len(snippet)]) == snippet:
            return i
        if isinstance(snippet, str) and args[0] == "eval" and snippet in args[1]:
            return i
    raise AssertionError(f"{snippet} did not run")


def uploaded(provisioner):
    """(folder, {name: content}) of what was put in the container."""
    import io
    import tarfile

    folder, data = provisioner.client.containers.get.return_value.put_archive.call_args.args
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        return folder, {member.name: archive.extractfile(member).read() for member in archive.getmembers()}


def test_turning_on_przelewy24_installs_its_checked_plugin_with_the_account_written_first(
    provisioner, shell, shop, archives,
):
    plugin_state(shell, installed=False, active=False)

    change_payments(provisioner, shop, przelewy24_enabled=True, przelewy24_merchant_id="123456", **P24_KEYS)

    assert [package.folder for package in archives] == ["woo-przelewy24"]
    assert uploaded(provisioner) == ("/tmp", {"woo-przelewy24-1.2.1.zip": b"archiwum woo-przelewy24"})
    assert shell.wp() == [
        ["plugin", "install", "/tmp/woo-przelewy24-1.2.1.zip"],
        ["plugin", "activate", "woo-przelewy24"],
    ]
    assert ["rm", "-f", "/tmp/woo-przelewy24-1.2.1.zip"] in [call["args"] for call in shell.calls]
    [(_, account)] = shell.php("p24_merchant_id")
    assert account == {
        "sandbox": False, "merchant_id": "123456",
        "crc_key": "0123456789abcdef", "api_key": "0123456789abcdef0123456789abcdef",
    }
    # Activating asks Przelewy24 for the account's payment methods, so the account is there by then.
    assert index_of(shell, "p24_merchant_id") < index_of(shell, ("plugin", "activate"))
    [(_, gateways)] = shell.php("payment_gateways()->payment_gateways() as $id")
    assert gateways == {"prefix": "p24-", "main": "p24-online-payments", "enabled": True, "fresh": True,
                        "options": {}}


def test_turning_on_payu_sets_it_up_after_activating_with_its_own_defaults_off(provisioner, shell, shop, archives):
    plugin_state(shell, installed=False, active=False)

    change_payments(provisioner, shop, payu_enabled=True, payu_sandbox=True, payu_pos_id="300746",
                    payu_client_id="300746", **PAYU_KEYS)

    assert [package.folder for package in archives] == ["woo-payu-payment-gateway"]
    [(_, account)] = shell.php("payu_settings_option_name")
    assert account == {
        "sandbox": True, "pos_id": "300746", "client_id": "300746", "fresh": True,
        "md5_key": "13a980d4f851f3d9a1cfc792fb1f5e50", "client_secret": "12f071174cb7eb79d4aac5bc2f07563f",
    }
    # Activating adds PayU's defaults, which the account settings build on.
    assert index_of(shell, ("plugin", "activate")) < index_of(shell, "payu_settings_option_name")
    [(_, gateways)] = shell.php("payment_gateways()->payment_gateways() as $id")
    assert gateways == {
        "prefix": "payu", "main": "payustandard", "enabled": True, "fresh": True,
        "options": {"payustandard": {"sandbox": "yes", "use_global": "yes", "enable_for_virtual": "yes"}},
    }


def test_keys_left_blank_keep_the_shops_own(provisioner, shell, shop, archives):
    plugin_state(shell, installed=True, active=True)

    change_payments(provisioner, shop, przelewy24_enabled=True, przelewy24_merchant_id="654321")

    assert archives == []
    assert shell.wp() == []
    [(_, account)] = shell.php("p24_merchant_id")
    assert account == {"sandbox": False, "merchant_id": "654321"}
    [(_, gateways)] = shell.php("payment_gateways()->payment_gateways() as $id")
    assert gateways["fresh"] is False


def test_turning_off_keeps_the_plugin_for_payments_on_their_way(provisioner, shell, shop, archives):
    plugin_state(shell, installed=True, active=True)

    change_payments(provisioner, shop, payu_enabled=False)

    assert shell.wp() == []
    [(_, gateways)] = shell.php("payment_gateways()->payment_gateways() as $id")
    assert gateways["enabled"] is False


def test_turning_off_an_operator_the_shop_never_had_does_nothing(provisioner, shell, shop, archives):
    plugin_state(shell, installed=False, active=False)

    change_payments(provisioner, shop, przelewy24_enabled=False, przelewy24_merchant_id="")

    assert archives == []
    assert shell.wp() == []
    assert shell.php("p24_merchant_id") == []


def test_operators_untouched_by_the_change_are_left_alone(provisioner, shell, shop, archives):
    change_payments(provisioner, shop, cash_on_delivery_enabled=True)

    assert shell.php("get_plugins()") == []
    assert archives == []


# --- terms and privacy policy ---

DOCUMENTS = [
    Document(key="terms", title="Regulamin sklepu", slug="regulamin", html="<h2>§ 1</h2>\n<p>Treść</p>"),
    Document(key="privacy", title="Polityka prywatności", slug="polityka-prywatnosci", html="<p>Dane</p>"),
]


def test_documents_become_the_pages_woocommerce_and_wordpress_name_as_terms_and_privacy_policy(
    provisioner, shell, shop,
):
    urls = {"terms": "http://palarnia.localhost:8080/regulamin/",
            "privacy": "http://palarnia.localhost:8080/polityka-prywatnosci/"}
    shell.on_php("wp_insert_post", output=f"\n{OUTPUT_MARKER}{json.dumps(urls)}")

    assert provisioner.publish_documents(shop, DOCUMENTS) == urls

    [(script, data)] = shell.php("wp_insert_post")
    assert data == {"documents": [
        {"key": "terms", "option": "woocommerce_terms_page_id", "title": "Regulamin sklepu", "slug": "regulamin",
         "html": "<h2>§ 1</h2>\n<p>Treść</p>"},
        {"key": "privacy", "option": "wp_page_for_privacy_policy", "title": "Polityka prywatności",
         "slug": "polityka-prywatnosci", "html": "<p>Dane</p>"},
    ]}
    # The page the shop already names is updated, not duplicated; the footer links follow the option.
    assert "$page['ID'] = $id;" in script
    assert "update_option('sklepownia_documents', $ids);" in script


def test_documents_bring_the_footer_links_with_them(provisioner, shell, shop):
    shell.on_php("wp_insert_post", output=f"\n{OUTPUT_MARKER}{{}}")

    provisioner.publish_documents(shop, DOCUMENTS)

    [write] = [call for call in shell.calls if call["args"][:2] == ["sh", "-c"]]
    assert write["environment"] == {"FILE": DOCUMENTS_PLUGIN_PATH, "CONTENT": DOCUMENTS_PLUGIN.read_text()}
    assert shell.calls.index(write) < shell.position("eval")
