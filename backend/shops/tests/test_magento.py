"""MagentoProvisioner against a fake `docker exec` shell with scripted answers; real setups are checked by hand."""

import base64
import json
from unittest.mock import MagicMock

import pytest

from accounts.models import User
from billing.models import Plan, Subscription
from shops.models import Shop, ShopConfig, ShopCredentials, ShopTemplate
from shops.platforms.magento import OUTPUT_MARKER, MagentoProvisioner
from shops.provisioning.base import ProvisioningError
from shops.provisioning.container import CommandError

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

    def on_magento(self, *arguments, output="", fail=False):
        self.on(lambda command: command[1:2] == ["/var/www/html/bin/magento"]
                and tuple(command[2: 2 + len(arguments)]) == arguments, output, fail)

    def on_run(self, action, result):
        self.on_magento("sklepownia:run", action, output=f"Notice\n{OUTPUT_MARKER}{json.dumps(result)}")

    def __call__(self, container, command, user="", environment=None):
        self.calls.append({"container": container, "command": list(command), "user": user, "env": environment})
        for matches, output, fail in self.rules:
            if matches(command):
                if fail:
                    raise CommandError(f"{command[0]} failed")
                return output
        return ""

    def magento(self, *arguments):
        """Every `bin/magento` call starting with `arguments`."""
        return [
            call for call in self.calls
            if call["command"][1:2] == ["/var/www/html/bin/magento"]
            and tuple(call["command"][2: 2 + len(arguments)]) == arguments
        ]

    def runs(self, action):
        """Data passed to every `sklepownia:run <action>`."""
        return [
            json.loads(base64.b64decode(call["env"]["SKLEPOWNIA_DATA"]))
            for call in self.magento("sklepownia:run", action)
        ]


@pytest.fixture
def shell(monkeypatch):
    fake = Shell()
    # Every action answers with something, as the real command does.
    fake.on_magento("sklepownia:run", output=f"{OUTPUT_MARKER}{{}}")
    monkeypatch.setattr(
        MagentoProvisioner,
        "_exec",
        lambda self, container, command, user="", environment=None: fake(container, command, user, environment),
    )
    return fake


@pytest.fixture
def provisioner():
    instance = MagentoProvisioner()
    instance.__dict__["client"] = MagicMock()
    # The proxy reaches the container at once (the waiting is tested in monitoring/tests/test_docker.py).
    instance._wait_until_routed = lambda shop, timeout=None: True
    return instance


@pytest.fixture
def shop(db, settings):
    settings.SHOPS_DB_ROOT_PASSWORD = "root-secret"
    owner = User.objects.create_user(email="wlasciciel@example.com", password="Sekretne-haslo-123")
    shop = Shop.objects.create(
        owner=owner, name="Palarnia", slug="palarnia", platform="magento", status=Shop.Status.PROVISIONING,
    )
    ShopConfig.objects.create(
        shop=shop,
        industry="food",
        template=ShopTemplate.objects.get(slug="luma"),
        category_count=3,
        contact_email="kontakt@example.com",
        description="Kawa z małych palarni",
    )
    ShopCredentials.objects.create(shop=shop, admin_login="admin", db_password="db-secret")
    return shop


def settings_values(**overrides):
    values = {
        "general": {"name": "Palarnia", "description": "Kawa", "contact_email": "kontakt@example.com"},
        "payments": {
            "bank_transfer_enabled": True, "bank_account_name": "Palarnia sp. z o.o.",
            "bank_account_number": "61 1090 1014", "bank_name": "", "cash_on_delivery_enabled": False,
        },
        "shipping": {
            "courier_enabled": True, "courier_cost": "15.00", "free_shipping_enabled": False,
            "free_shipping_min_amount": "200.00", "local_pickup_enabled": True,
        },
        "taxes": {"enabled": True, "prices_include_tax": True, "standard_rate": "23.00"},
        "region": {"language": "pl_PL", "currency": "PLN", "country": "PL", "timezone": "Europe/Warsaw"},
    }
    for section, fields in overrides.items():
        values[section] = {**values[section], **fields}
    return values


def test_container_keeps_only_the_shop_data_in_its_volume(provisioner, shop, settings):
    from docker.errors import NotFound

    settings.SHOPS_MAGENTO_IMAGE = "shops/magento:test"
    provisioner.client.containers.get.side_effect = NotFound("brak")
    provisioner.client.containers.run.return_value.exec_run.return_value.exit_code = 0

    provisioner.step_start_container(shop)

    args, kwargs = provisioner.client.containers.run.call_args
    assert args == ("shops/magento:test",)
    assert kwargs["volumes"] == {f"shop-{shop.pk}": {"bind": "/var/www/data", "mode": "rw"}}


def test_magento_gets_at_least_its_minimum_memory(provisioner, shop, settings):
    settings.SHOPS_CONTAINER_MEMORY = "512m"
    settings.SHOPS_MAGENTO_MEMORY = "1536m"
    assert provisioner.memory(shop) == "1536m"

    plan = Plan.objects.create(code="duzy", name="Duży", price="99.00", max_shops=5, shop_memory_mb=3072)
    Subscription.objects.create(user=shop.owner, plan=plan, status=Subscription.Status.ACTIVE)
    assert provisioner.memory(shop) == "3072m"


def test_install_runs_setup_once_with_the_shop_settings(provisioner, shell, shop):
    shell.on_command("grep", fail=True)

    provisioner.step_install_magento(shop)

    [install] = shell.magento("setup:install")
    command = install["command"]
    assert install["user"] == "www-data"
    shop.refresh_from_db()
    assert shop.admin_path.startswith("admin_")
    credentials = ShopCredentials.objects.get(shop=shop)
    assert f"--backend-frontname={shop.admin_path}" in command
    assert f"--admin-password={credentials.admin_password}" in command
    assert any(c.isdigit() for c in credentials.admin_password)
    assert f"--db-name=shop_{shop.pk}" in command
    assert f"--opensearch-index-prefix=shop_{shop.pk}" in command
    assert "--language=pl_PL" in command and "--currency=PLN" in command
    assert "--timezone=Europe/Warsaw" in command
    assert f"--base-url={shop.url}/" in command
    assert shell.magento("deploy:mode:set", "production", "--skip-compilation")
    # The stored login is set on the administrator, whoever installed the shop.
    assert shell.runs("admin") == [{
        "username": "admin", "email": "kontakt@example.com", "password": credentials.admin_password, "locale": "pl_PL",
    }]
    # Passwords go through the environment, never the arguments.
    [admin] = shell.magento("sklepownia:run", "admin")
    assert credentials.admin_password not in " ".join(admin["command"])


def test_installed_shop_is_not_installed_again(provisioner, shell, shop):
    provisioner.step_install_magento(shop)

    assert shell.magento("setup:install") == []
    assert len(shell.runs("admin")) == 1


def test_configure_shop_turns_payments_and_shipping_off_and_sets_titles(provisioner, shell, shop):
    provisioner.step_configure_shop(shop)

    values, _mail = shell.runs("config")
    assert values["general/store_information/name"] == "Palarnia"
    assert values["payment/checkmo/active"] == "0"
    assert values["carriers/flatrate/active"] == "0"
    assert values["carriers/flatrate/type"] == "O"
    assert values["carriers/sklepowniapickup/title"] == "Odbiór osobisty"
    assert values["trans_email/ident_sales/email"] == "kontakt@example.com"
    assert values["design/header/welcome"] == ""
    assert values["design/footer/copyright"] == "© Palarnia"
    [home] = shell.runs("home")
    assert home["title"] == "Palarnia"
    assert home["content"].startswith("<p>Kawa z małych palarni</p>")


def test_configure_shop_sends_mail_through_the_relay_with_copies_for_the_owner(provisioner, shell, shop, settings):
    settings.SHOPS_SMTP_HOST = "shops-mail"
    settings.SHOPS_SMTP_PORT = 1025
    settings.SHOPS_MAIL_DOMAIN = "sklepy.example.pl"

    provisioner.step_configure_shop(shop)

    values, mail = shell.runs("config")
    assert values["contact/email/recipient_email"] == "kontakt@example.com"
    assert values["sales_email/order/copy_to"] == "kontakt@example.com"
    assert values["sales_email/order/copy_method"] == "bcc"
    assert mail == {
        "system/smtp/disable": "0",
        "system/smtp/transport": "smtp",
        "system/smtp/host": "shops-mail",
        "system/smtp/port": "1025",
        "system/smtp/auth": "none",
        "system/smtp/ssl": "",
        "system/smtp/username": "",
        "sklepownia/mail/sender": "palarnia@sklepy.example.pl",
    }


def test_without_a_mail_server_magento_keeps_its_own(provisioner, shell, shop, settings):
    settings.SHOPS_SMTP_HOST = ""

    provisioner.step_configure_shop(shop)

    [values] = shell.runs("config")
    assert not any(path.startswith("system/smtp/") for path in values)


def test_a_new_contact_address_gets_the_order_copies_and_the_contact_form(provisioner, shell, shop):
    general = {"name": "Palarnia", "description": "Kawa", "contact_email": "nowy@example.com"}
    provisioner.apply_settings(shop, {"general": {"contact_email": "nowy@example.com"}}, settings_values(general=general))

    [values] = shell.runs("config")
    assert values["sales_email/order/copy_to"] == "nowy@example.com"
    assert values["contact/email/recipient_email"] == "nowy@example.com"
    assert values["trans_email/ident_general/email"] == "nowy@example.com"


def test_categories_and_samples(provisioner, shell, shop):
    provisioner.step_create_categories(shop)

    [data] = shell.runs("catalog")
    assert len(data["names"]) == 3
    assert data["samples"] is True


def test_navigation_builds_the_indexes(provisioner, shell, shop):
    provisioner.step_configure_navigation(shop)

    assert shell.magento("indexer:reindex")


def test_health_check_opens_the_shop_search_and_panel(provisioner, shell, shop):
    shop.admin_path = "admin_4f7k"
    shell.on_command("curl", output="200")

    provisioner.step_health_check(shop)

    urls = [call["command"][-1] for call in shell.calls]
    assert urls == [
        "http://shops-proxy/", "http://shops-proxy/catalogsearch/result/?q=produkt", "http://shops-proxy/admin_4f7k/",
    ]


def test_health_check_reports_what_failed(provisioner, shell, shop):
    shop.admin_path = "admin_4f7k"
    shell.on(lambda command: command[0] == "curl", output="200")
    shell.on(lambda command: command[0] == "curl" and "catalogsearch" in command[-1], output="500")

    with pytest.raises(ProvisioningError, match="wyszukiwarka: HTTP 500"):
        provisioner.step_health_check(shop)


def test_read_settings(provisioner, shell, shop):
    shell.on_run("read", {
        "name": "Palarnia", "description": "Kawa", "email": "kontakt@example.com",
        "bank_transfer": "1", "cash_on_delivery": "0", "bank_owner": "Palarnia sp. z o.o.",
        "bank_number": "61 1090", "bank_bank": None,
        "flatrate": "1", "flatrate_price": "15,5", "freeshipping": "0", "freeshipping_subtotal": None,
        "pickup": "1", "prices_include_tax": "1", "tax_enabled": True, "tax_rate": "23.0000",
        "locale": "pl_PL", "currency": "PLN", "country": "PL", "timezone": "Europe/Warsaw",
        "base_url": "http://palarnia.localhost:8080/",
    })

    result = provisioner.read_settings(shop)

    assert result["general"] == {"name": "Palarnia", "description": "Kawa", "contact_email": "kontakt@example.com"}
    assert result["payments"]["bank_transfer_enabled"] is True
    assert result["payments"]["bank_name"] == ""
    assert result["shipping"] == {
        "courier_enabled": True, "courier_cost": "15.50", "free_shipping_enabled": False,
        "free_shipping_min_amount": "0.00", "local_pickup_enabled": True,
    }
    assert result["taxes"] == {"enabled": True, "prices_include_tax": True, "standard_rate": "23.00"}
    assert result["region"]["language"] == "pl_PL"
    assert "appearance" not in result and "availability" not in result


def test_apply_settings_touches_only_changed_sections(provisioner, shell, shop):
    provisioner.apply_settings(shop, {"shipping": {"courier_cost": "15.00"}}, settings_values())

    [values] = shell.runs("config")
    assert values["carriers/flatrate/price"] == "15.00"
    assert values["carriers/sklepowniapickup/active"] == "1"
    assert not any(path.startswith("payment/") for path in values)
    assert shell.runs("taxes") == [] and shell.runs("home") == []


def test_bank_transfer_instructions_are_made_from_the_details(provisioner, shell, shop):
    provisioner.apply_settings(shop, {"payments": {"bank_transfer_enabled": True}}, settings_values())

    [values] = shell.runs("config")
    assert values["payment/banktransfer/active"] == "1"
    assert values["payment/banktransfer/instructions"] == "Odbiorca: Palarnia sp. z o.o.\nNumer konta: 61 1090 1014"
    assert values["sklepownia/bank/number"] == "61 1090 1014"


def test_new_language_changes_titles_and_the_panel(provisioner, shell, shop):
    shop.config.language = "de_DE"
    provisioner.apply_settings(
        shop, {"region": {"language": "de_DE"}}, settings_values(region={"language": "de_DE"}),
    )

    [values] = shell.runs("config")
    assert values["general/locale/code"] == "de_DE"
    assert values["carriers/freeshipping/title"] == "Kostenloser Versand"
    assert values["payment/banktransfer/instructions"].startswith("Empfänger:")
    assert shell.runs("admin")[0]["locale"] == "de_DE"


def test_new_country_moves_the_tax_rate(provisioner, shell, shop):
    provisioner.apply_settings(
        shop, {"region": {"country": "DE"}},
        settings_values(region={"country": "DE"}, taxes={"standard_rate": "19.00"}),
    )

    assert shell.runs("taxes") == [{"enabled": True, "include": True, "rate": "19.00", "country": "DE"}]
    [values] = shell.runs("config")
    assert values["general/country/default"] == "DE"


def test_reset_admin_password_stores_the_new_one(provisioner, shell, shop):
    provisioner.reset_admin_password(shop)

    credentials = ShopCredentials.objects.get(shop=shop)
    assert shell.runs("admin")[0]["password"] == credentials.admin_password


def test_remove_sample_products_counts_what_was_removed(provisioner, shell, shop):
    shell.on_run("remove_samples", {"removed": 6})

    assert provisioner.remove_sample_products(shop) == 6


def test_missing_result_is_an_error(provisioner, shell, shop):
    shell.on_magento("sklepownia:run", "read", output="Fatal error")

    with pytest.raises(CommandError, match="no result"):
        provisioner.read_settings(shop)


def test_teardown_removes_the_search_indexes(provisioner, shell, shop, settings):
    from docker.errors import NotFound

    provisioner.client.containers.get.side_effect = NotFound("brak")
    provisioner.client.volumes.get.side_effect = NotFound("brak")

    provisioner.teardown(shop)

    [delete] = [call for call in shell.calls if call["container"] == "shops-search"]
    assert delete["command"][-1] == f"http://localhost:9200/shop_{shop.pk}_*"


def test_orders_are_read_from_magento_s_database(provisioner, shell, shop):
    from datetime import UTC, datetime
    from decimal import Decimal

    lines = [
        {"id": 3, "number": "000000003", "state": "processing", "total": 89.5, "currency": "PLN", "items": 2.0,
         "first_name": "Piotr", "last_name": "Zieliński", "created": 1794000000, "modified": 1794000900},
        {"id": 4, "number": "000000004", "state": "pending_payment", "total": 10, "currency": None, "items": None,
         "first_name": None, "last_name": None, "created": 1794001000, "modified": None},
    ]
    shell.on_command("mariadb", output="\n".join(json.dumps(line) for line in lines) + "\n")

    orders = provisioner.read_orders(shop, datetime(2026, 11, 1, tzinfo=UTC), 500)

    [call] = [call for call in shell.calls if call["command"][0] == "mariadb"]
    assert "--raw" in call["command"]
    assert call["command"][call["command"].index("-e") - 1] == f"shop_{shop.pk}"
    statement = call["command"][-1]
    assert f"FROM_UNIXTIME({int(datetime(2026, 11, 1, tzinfo=UTC).timestamp())})" in statement
    assert statement.endswith("LIMIT 500")
    assert [(o.external_id, o.number, o.status, o.total, o.currency, o.items, o.customer) for o in orders] == [
        ("3", "000000003", "processing", Decimal("89.50"), "PLN", 2, "Piotr Z."),
        ("4", "000000004", "unfinished", Decimal("10.00"), shop.config.currency, 0, ""),
    ]
    assert orders[1].changed_at == orders[1].placed_at


def test_products_are_counted_in_magento_s_database(provisioner, shell, shop):
    from shops.provisioning.base import ProductCount

    shell.on_command("mariadb", output="9\t6\n")

    assert provisioner.count_products(shop) == ProductCount(products=3, samples=6)

    # Without starting Magento's console.
    assert not shell.magento()
    [call] = [call for call in shell.calls if call["command"][0] == "mariadb"]
    assert call["command"][call["command"].index("-e") - 1] == f"shop_{shop.pk}"
    assert "sklepownia/samples/ids" in call["command"][-1]


def test_documents_become_cms_pages_and_the_checkout_agreement(provisioner, shell, shop, monkeypatch):
    from shops.documents import Document

    started = []
    monkeypatch.setattr(MagentoProvisioner, "step_start_container", lambda self, shop: started.append(shop.pk))
    shell.on_run("documents", {"pages": {"terms": "regulamin", "privacy": "privacy-policy-cookie-restriction-mode"}})

    urls = provisioner.publish_documents(shop, [
        Document(key="terms", title="Regulamin sklepu", slug="regulamin", html="<p>Regulamin</p>"),
        Document(key="privacy", title="Polityka prywatności", slug="polityka-prywatnosci", html="<p>Dane</p>"),
    ])

    # A container of an older image doesn't have the action yet.
    assert started == [shop.pk]
    assert urls == {"terms": f"{shop.url}/regulamin", "privacy": f"{shop.url}/privacy-policy-cookie-restriction-mode"}
    [data] = shell.runs("documents")
    assert data == {
        "documents": [
            {"key": "terms", "title": "Regulamin sklepu", "slug": "regulamin", "html": "<p>Regulamin</p>"},
            {"key": "privacy", "title": "Polityka prywatności", "slug": "polityka-prywatnosci", "html": "<p>Dane</p>"},
        ],
        "checkbox": "Akceptuję regulamin sklepu",
    }
