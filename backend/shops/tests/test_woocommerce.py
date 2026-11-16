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
from shops.platforms.woocommerce import (
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
