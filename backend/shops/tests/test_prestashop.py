"""
PrestaShopProvisioner without Docker: commands it would run inside containers go to a fake shell,
which records them and answers with scripted output. The real setup is checked by hand on a live shop.
"""

import base64
import json
import re
from unittest.mock import MagicMock

import pytest

from accounts.models import User
from shops.models import Shop, ShopConfig, ShopCredentials, ShopTemplate
from shops.provisioning.base import ProvisioningError
from shops.provisioning.container import CommandError
from shops.platforms.prestashop import MAIL_MODULE_FILE, OUTPUT_MARKER, PrestaShopProvisioner

pytestmark = pytest.mark.django_db


class Shell:
    """Stands in for `docker exec`. Later rules win, so a test can override a default answer."""

    def __init__(self):
        self.calls = []
        self.rules = []

    def on(self, matches, output="", fail=False):
        self.rules.insert(0, (matches, output, fail))

    def on_command(self, *prefix, output="", fail=False):
        self.on(lambda command: tuple(command[: len(prefix)]) == prefix, output, fail)

    def on_php(self, snippet, output="", fail=False):
        self.on(lambda command: command[0] == "php" and "-r" in command and snippet in command[-1], output, fail)

    def __call__(self, container, command, user="", environment=None):
        self.calls.append({"container": container, "command": list(command), "user": user, "env": environment})
        for matches, output, fail in self.rules:
            if matches(command):
                if fail:
                    raise CommandError(f"{command[0]} failed")
                return output
        return ""

    def php(self, snippet=""):
        """(script, data) of every PHP script run whose code contains `snippet`."""
        result = []
        for call in self.calls:
            command = call["command"]
            if command[0] != "php" or "-r" not in command or snippet not in command[-1]:
                continue
            data = json.loads(base64.b64decode(re.search(r"base64_decode\('([^']*)'\)", command[-1]).group(1)))
            result.append((command[-1], data))
        return result

    def installer(self):
        return [call for call in self.calls if any("index_cli.php" in part for part in call["command"])]


@pytest.fixture
def shell(monkeypatch):
    fake = Shell()
    fake.on_command("sh", "-c", output="admin-api/\nadmin4f7k2x/")
    fake.on_php("PS_CURRENCY_DEFAULT", output=f"Notice\n{OUTPUT_MARKER}PLN")
    fake.on_php("SKLEPOWNIA_MAIL_FROM", output=f"{OUTPUT_MARKER}enabled")
    monkeypatch.setattr(
        PrestaShopProvisioner,
        "_exec",
        lambda self, container, command, user="", environment=None: fake(container, command, user, environment),
    )
    return fake


@pytest.fixture
def provisioner():
    instance = PrestaShopProvisioner()
    instance.__dict__["client"] = MagicMock()
    return instance


@pytest.fixture
def shop(db, settings):
    settings.SHOPS_DB_ROOT_PASSWORD = "root-secret"
    owner = User.objects.create_user(email="wlasciciel@example.com", password="Sekretne-haslo-123")
    shop = Shop.objects.create(
        owner=owner, name="Palarnia", slug="palarnia", platform="prestashop", status=Shop.Status.PROVISIONING,
    )
    ShopConfig.objects.create(
        shop=shop,
        industry="food",
        template=ShopTemplate.objects.get(slug="hummingbird"),
        category_count=3,
        contact_email="kontakt@example.com",
        description="Kawa z małych palarni",
    )
    ShopCredentials.objects.create(shop=shop, admin_login="kontakt@example.com", db_password="db-secret")
    return shop


def test_container_runs_the_prestashop_image_without_auto_install(provisioner, shop, settings):
    from docker.errors import NotFound

    settings.SHOPS_PRESTASHOP_IMAGE = "prestashop/prestashop:test"
    provisioner.client.containers.get.side_effect = NotFound("brak")
    provisioner.client.containers.run.return_value.exec_run.return_value.exit_code = 0

    provisioner.step_start_container(shop)

    args, kwargs = provisioner.client.containers.run.call_args
    assert args == ("prestashop/prestashop:test",)
    assert kwargs["environment"]["PS_INSTALL_AUTO"] == "0"
    assert kwargs["volumes"] == {f"shop-{shop.pk}": {"bind": "/var/www/html", "mode": "rw"}}


def test_install_runs_the_installer_once_and_finds_the_panel(provisioner, shell, shop):
    shell.on_command("test", "-f", fail=True)

    provisioner.step_install_prestashop(shop)

    [install] = shell.installer()
    command = install["command"]
    assert install["user"] == "www-data"
    assert f"--domain={shop.url.split('://')[1]}" in command
    assert f"--db_name=shop_{shop.pk}" in command
    assert "--language=pl" in command and "--country=pl" in command
    assert "--theme=hummingbird" in command and "--fixtures=0" in command
    credentials = ShopCredentials.objects.get(shop=shop)
    assert f"--password={credentials.admin_password}" in command
    assert "--email=kontakt@example.com" in command
    shop.refresh_from_db()
    assert shop.admin_path == "admin4f7k2x"
    # The stored login is set on the employee, whoever installed the shop.
    [(_, data)] = shell.php("employee_session")
    assert data == {"email": "kontakt@example.com", "password": credentials.admin_password}


def test_installed_shop_is_not_installed_again(provisioner, shell, shop):
    provisioner.step_install_prestashop(shop)

    assert shell.installer() == []


def test_panel_folder_must_be_found(provisioner, shell, shop):
    shell.on_command("sh", "-c", output="admin-api/")

    with pytest.raises(ProvisioningError, match="panelu"):
        provisioner.step_install_prestashop(shop)


def test_configure_shop_sets_currency_and_turns_payments_off(provisioner, shell, shop):
    provisioner.step_configure_shop(shop)

    [(script, data)] = shell.php("PS_CURRENCY_DEFAULT")
    assert "AdminKernel" in script
    assert data["currency"] == "PLN"
    assert data["config"]["PS_SHOP_EMAIL"] == "kontakt@example.com"
    assert "sklepownia_module('ps_wirepayment', false)" in script
    assert shell.php("Meta::getMetaByPage")[0][1]["description"] == "Kawa z małych palarni"


def test_configure_shop_installs_the_mail_module_and_points_at_the_relay(provisioner, shell, shop, settings):
    settings.SHOPS_SMTP_HOST = "shops-mail"
    settings.SHOPS_SMTP_PORT = 1025
    settings.SHOPS_MAIL_DOMAIN = "sklepy.example.pl"

    provisioner.step_configure_shop(shop)

    [write] = [call for call in shell.calls if call["env"] and "FILE" in call["env"]]
    assert write["env"]["FILE"] == "/var/www/html/modules/sklepowniamail/sklepowniamail.php"
    assert write["env"]["CONTENT"] == MAIL_MODULE_FILE.read_text()
    assert write["user"] == "www-data"
    [(script, data)] = shell.php("SKLEPOWNIA_MAIL_FROM")
    assert data == {"host": "shops-mail", "port": 1025, "sender": "palarnia@sklepy.example.pl"}
    assert "sklepownia_module('sklepowniamail', true)" in script
    assert "AdminKernel" in script
    # A module left without its hook by an interrupted installation gets it back.
    assert "registerHook('actionEmailSendBefore')" in script
    assert "Configuration::updateValue('PS_MAIL_METHOD', 2)" in script
    # The shop's contact address stays as it was: customers see it, and replies go to it.
    assert shell.php("PS_CURRENCY_DEFAULT")[0][1]["config"]["PS_SHOP_EMAIL"] == "kontakt@example.com"


def test_mail_module_that_did_not_enable_fails_the_step(provisioner, shell, shop):
    shell.on_php("SKLEPOWNIA_MAIL_FROM", output=f"{OUTPUT_MARKER}disabled")

    with pytest.raises(CommandError, match="sklepowniamail"):
        provisioner.step_configure_shop(shop)


def test_mail_module_rewrites_the_sender_and_keeps_replies():
    module = MAIL_MODULE_FILE.read_text()

    assert "class SklepowniaMail extends Module" in module
    assert "registerHook('actionEmailSendBefore')" in module
    assert "$params['replyTo'] = $from;" in module and "$params['from'] = $sender;" in module


def test_configure_shop_fails_when_the_currency_did_not_change(provisioner, shell, shop):
    shell.on_php("PS_CURRENCY_DEFAULT", output=f"{OUTPUT_MARKER}EUR")

    with pytest.raises(ProvisioningError, match="waluty"):
        provisioner.step_configure_shop(shop)


def test_categories_and_samples(provisioner, shell, shop):
    provisioner.step_create_categories(shop)

    [(_, data)] = shell.php("searchByNameAndParentCategoryId")
    assert data["names"] == ["Kawa", "Herbata", "Słodycze"]
    assert data["samples"] is True


def test_health_check_opens_the_shop_and_its_panel(provisioner, shell, shop):
    shop.admin_path = "admin4f7k2x"
    shell.on_command("curl", output="200")

    provisioner.step_health_check(shop)

    urls = [call["command"][-1] for call in shell.calls]
    assert urls == ["http://shops-proxy/", "http://shops-proxy/admin4f7k2x/login"]


def test_health_check_reports_what_failed(provisioner, shell, shop):
    shop.admin_path = "admin4f7k2x"
    shell.on(lambda command: command[0] == "curl" and command[-1].endswith("/login"), output="500")
    shell.on(lambda command: command[0] == "curl" and command[-1].endswith("/"), output="200")

    with pytest.raises(ProvisioningError, match="panel sklepu: HTTP 500"):
        provisioner.step_health_check(shop)


def test_read_settings(provisioner, shell, shop):
    shell.on_php("BANK_WIRE_OWNER", output=OUTPUT_MARKER + json.dumps({
        "name": "Palarnia", "description": "Kawa", "email": "kontakt@example.com", "enabled": True,
        "wire": True, "wire_owner": "Palarnia sp. z o.o.", "wire_details": "PL61 1090", "wire_address": "Bank",
        "cod": False, "theme": "classic",
        "online": {
            "przelewy24": {"active": True, "sandbox": True, "merchant_id": "123456", "keys": True},
            "payu": {"active": False, "sandbox": False, "pos_id": "", "client_id": "", "keys": False},
        },
    }))

    values = provisioner.read_settings(shop)

    assert values == {
        "general": {"name": "Palarnia", "description": "Kawa", "contact_email": "kontakt@example.com"},
        "availability": {"is_open": True},
        "payments": {
            "bank_transfer_enabled": True, "bank_account_name": "Palarnia sp. z o.o.",
            "bank_account_number": "PL61 1090", "bank_name": "Bank", "cash_on_delivery_enabled": False,
            "przelewy24_enabled": True, "przelewy24_sandbox": True, "przelewy24_merchant_id": "123456",
            "przelewy24_keys_saved": True,
            "payu_enabled": False, "payu_sandbox": False, "payu_pos_id": "", "payu_client_id": "",
            "payu_keys_saved": False,
        },
        "appearance": {"theme": "classic"},
    }


def test_apply_settings_touches_only_changed_sections(provisioner, shell, shop):
    values = {
        "general": {"name": "Palarnia", "description": "", "contact_email": "kontakt@example.com"},
        "availability": {"is_open": False},
        "payments": {
            "bank_transfer_enabled": True, "bank_account_name": "Palarnia", "bank_account_number": "PL61",
            "bank_name": "", "cash_on_delivery_enabled": True,
        },
    }

    provisioner.apply_settings(shop, {"payments": {"cash_on_delivery_enabled": True}}, values)

    assert shell.php("PS_SHOP_ENABLE") == []
    [(_, data)] = shell.php("BANK_WIRE_OWNER")
    assert data == {"wire": True, "cod": True, "owner": "Palarnia", "details": "PL61", "address": ""}


def test_new_theme_is_enabled(provisioner, shell, shop):
    shop.config.template = ShopTemplate.objects.get(slug="classic")

    provisioner.apply_settings(shop, {"appearance": {"theme": "classic"}}, {})

    [(_, data)] = shell.php("ThemeManagerBuilder")
    assert data == {"theme": "classic"}


def test_reset_admin_password_stores_the_new_one(provisioner, shell, shop):
    provisioner.reset_admin_password(shop)

    credentials = ShopCredentials.objects.get(shop=shop)
    [(_, data)] = shell.php("employee_session")
    assert data == {"email": "kontakt@example.com", "password": credentials.admin_password}


def test_remove_sample_products_counts_what_was_removed(provisioner, shell, shop):
    shell.on_php("SKLEPOWNIA_SAMPLE_PRODUCTS", output=f"{OUTPUT_MARKER}6")

    assert provisioner.remove_sample_products(shop) == 6


def test_update_address_moves_the_shop(provisioner, shell, shop, monkeypatch):
    monkeypatch.setattr(PrestaShopProvisioner, "step_start_container", lambda self, shop: None)
    shell.on_php("shop_url", output=f"{OUTPUT_MARKER}palarnia.stary.example")

    previous = provisioner.update_address(shop)

    assert previous == f"{shop.url.split('://')[0]}://palarnia.stary.example"
    assert shell.php("shop_url")[0][1] == {"domain": shop.url.split("://")[1]}


# --- orders for the sales overview ---


def test_orders_are_read_from_prestashop(provisioner, shell, shop):
    from datetime import UTC, datetime
    from decimal import Decimal

    rows = [
        {"id": "7", "number": "XKBKNABJK", "status": "processing", "total": "123.456000", "currency": "PLN",
         "items": 2, "first_name": "Ewa", "last_name": "Wiśniewska", "created": 1794000000, "modified": 1794000300},
    ]
    shell.on_php("PS_OS_CANCELED", output=f"Notice\n{OUTPUT_MARKER}{json.dumps(rows)}")

    [order] = provisioner.read_orders(shop, datetime(2026, 11, 1, tzinfo=UTC), 100)

    [(script, data)] = shell.php("PS_OS_CANCELED")
    assert "date_default_timezone_get()" in script
    assert data == {"since": int(datetime(2026, 11, 1, tzinfo=UTC).timestamp()), "limit": 100}
    assert (order.external_id, order.number, order.status, order.total, order.items, order.customer) == (
        "7", "XKBKNABJK", "processing", Decimal("123.46"), 2, "Ewa W.")
    assert order.placed_at == datetime.fromtimestamp(1794000000, tz=UTC)


def test_products_are_counted_with_the_samples_apart(provisioner, shell, shop):
    from shops.provisioning.base import ProductCount

    counted = json.dumps({"products": 0, "samples": 6})
    shell.on_php("SKLEPOWNIA_SAMPLE_PRODUCTS", output=f"Notice\n{OUTPUT_MARKER}{counted}")

    assert provisioner.count_products(shop) == ProductCount(products=0, samples=6)
    [(script, _)] = shell.php("SKLEPOWNIA_SAMPLE_PRODUCTS")
    assert "id_product IN" in script


# --- online payments ---

P24_KEYS = {"przelewy24_crc_key": "0123456789abcdef", "przelewy24_api_key": "0123456789abcdef0123456789abcdef"}
PAYU_KEYS = {"payu_md5_key": "13a980d4f851f3d9a1cfc792fb1f5e50", "payu_client_secret": "12f071174cb7eb79d4aac5bc2f07563f"}


@pytest.fixture
def archives(monkeypatch):
    fetched = []

    def fetch(package):
        fetched.append(package)
        return f"archiwum {package.folder}".encode()

    monkeypatch.setattr("shops.provisioning.packages.fetch", fetch)
    return fetched


def module_installed(shell, installed):
    shell.on_php("Module::isInstalled($d[\"name\"])", output=f"\n{OUTPUT_MARKER}{'yes' if installed else 'no'}")


def change_payments(provisioner, shop, **changed):
    from shops.shop_settings import _operator_defaults

    payments = {
        "bank_transfer_enabled": False, "bank_account_name": "", "bank_account_number": "", "bank_name": "",
        "cash_on_delivery_enabled": False, **_operator_defaults(), **changed,
    }
    provisioner.apply_settings(shop, {"payments": changed}, {"payments": payments})


def test_turning_on_przelewy24_installs_its_checked_module(provisioner, shell, shop, archives):
    module_installed(shell, False)

    change_payments(provisioner, shop, przelewy24_enabled=True, przelewy24_sandbox=True,
                    przelewy24_merchant_id="123456", **P24_KEYS)

    assert [package.folder for package in archives] == ["przelewy24payment"]
    folder, data = provisioner.client.containers.get.return_value.put_archive.call_args.args
    assert folder == "/tmp"
    [(script, unpacked)] = shell.php("ZipArchive")
    assert unpacked == {"zip": "/tmp/przelewy24payment-1.2.1.zip", "name": "przelewy24payment"}
    # Installing builds translations, which needs the back office's kernel.
    assert "AdminKernel" in script
    assert ["rm", "-f", "/tmp/przelewy24payment-1.2.1.zip"] in [call["command"] for call in shell.calls]
    [(_, account)] = shell.php("przelewy24_credentials_config WHERE")
    assert account == {
        "sandbox": True, "merchant_id": "123456",
        "crc_key": "0123456789abcdef", "api_key": "0123456789abcdef0123456789abcdef",
    }
    [(_, switched)] = shell.php("sklepownia_module($d['name']")
    assert switched == {"name": "przelewy24payment", "enabled": True}


def test_turning_on_payu_turns_its_installments_promotion_off_once(provisioner, shell, shop, archives):
    module_installed(shell, False)

    change_payments(provisioner, shop, payu_enabled=True, payu_pos_id="300746", payu_client_id="300746", **PAYU_KEYS)

    [(code, account)] = shell.php("PAYU_MC_POS_ID")
    assert "Configuration::updateValue('PAYU_SEPARATE_INSTALLMENTS', 0)" in code
    assert account == {
        "sandbox": False, "pos_id": "300746", "client_id": "300746", "fresh": True,
        "md5_key": "13a980d4f851f3d9a1cfc792fb1f5e50", "client_secret": "12f071174cb7eb79d4aac5bc2f07563f",
    }


def test_turning_off_keeps_the_module_installed(provisioner, shell, shop, archives):
    module_installed(shell, True)

    change_payments(provisioner, shop, payu_enabled=False, payu_pos_id="300746", payu_client_id="300746")

    assert archives == []
    assert shell.php("ZipArchive") == []
    [(_, account)] = shell.php("PAYU_MC_POS_ID")
    assert account["fresh"] is False and "md5_key" not in account
    [(_, switched)] = shell.php("sklepownia_module($d['name']")
    assert switched == {"name": "payu", "enabled": False}


def test_an_operator_the_shop_never_had_stays_away_when_off(provisioner, shell, shop, archives):
    module_installed(shell, False)

    change_payments(provisioner, shop, przelewy24_enabled=False, przelewy24_merchant_id="")

    assert archives == []
    assert shell.php("przelewy24_credentials_config WHERE") == []
    assert shell.php("sklepownia_module($d['name']") == []
