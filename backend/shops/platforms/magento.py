"""
Magento (the Mage-OS distribution): every shop is its own container of the image from infra/shops/magento.
The code, compiled classes and static files are in the image; the shop's volume holds only its own data
(settings, product images, cache). Products are searched with the shared OpenSearch, each shop with its
own indexes. Everything inside the shop goes through `bin/magento`, mostly the `sklepownia:run` command
of our module (infra/shops/magento/Sklepownia).
"""

import base64
import json
import re
import secrets
import string
from decimal import Decimal

from django.conf import settings

from ..categories import category_names
from ..choices import COUNTRY_TIMEZONES
from ..orders import Order, Status as OrderStatus, customer_label, from_timestamp
from ..provisioning.base import ProvisioningError
from ..provisioning.container import (
    FILES_PATH, CommandError, ContainerProvisioner, container_memory, container_name, db_name, mail_relay,
    memory_bytes,
)
from .woocommerce import _money

SAMPLE_PRODUCT_CATEGORIES = 3
SAMPLE_PRODUCTS_PER_CATEGORY = 2
# The shop's own files (see infra/shops/magento/entrypoint.sh).
DATA_PATH = "/var/www/data"
ADMIN_USERNAME = "admin"

# Output after this marker is the result, so notices Magento might print before it don't break parsing.
OUTPUT_MARKER = "@@sklepownia@@"

# Titles customers see, in the shop's language. Magento keeps them as settings, untranslated.
TITLES = {
    "pl_PL": {
        "flatrate": "Kurier", "freeshipping": "Darmowa dostawa", "sklepowniapickup": "Odbiór osobisty",
        "banktransfer": "Przelew bankowy", "cashondelivery": "Płatność przy odbiorze",
        "recipient": "Odbiorca", "account": "Numer konta", "bank": "Bank",
    },
    "en_US": {
        "flatrate": "Courier", "freeshipping": "Free shipping", "sklepowniapickup": "Local pickup",
        "banktransfer": "Bank transfer", "cashondelivery": "Cash on delivery",
        "recipient": "Recipient", "account": "Account number", "bank": "Bank",
    },
    "de_DE": {
        "flatrate": "Kurier", "freeshipping": "Kostenloser Versand", "sklepowniapickup": "Abholung",
        "banktransfer": "Banküberweisung", "cashondelivery": "Nachnahme",
        "recipient": "Empfänger", "account": "Kontonummer", "bank": "Bank",
    },
}

# The address the shop's e-mail goes out from (see infra/shops/magento/Sklepownia/Provisioning/Plugin/MailSender.php).
MAIL_SENDER_PATH = "sklepownia/mail/sender"

# Where the bank details the owner typed are kept, so the app can show them again (Magento itself only
# has the instructions text made from them).
BANK_PATH = "sklepownia/bank/"
CARRIERS = ("flatrate", "freeshipping", "sklepowniapickup")

# The home page: the newest products, under the shop's description.
PRODUCTS_WIDGET = (
    '{{widget type="Magento\\CatalogWidget\\Block\\Product\\ProductsList" show_pager="0" products_count="8"'
    ' template="Magento_CatalogWidget::product/widget/content/grid.phtml"'
    ' conditions_encoded="^[`1`:^[`type`:`Magento||CatalogWidget||Model||Rule||Condition||Combine`,'
    '`aggregator`:`all`,`value`:`1`,`new_child`:``^]^]"}}'
)


# Orders straight from the database: timestamps are compared as Unix time, so the session's time zone doesn't matter.
READ_ORDERS_SQL = (
    "SELECT JSON_OBJECT('id', entity_id, 'number', increment_id, 'state', state, 'total', grand_total,"
    " 'currency', order_currency_code, 'items', total_qty_ordered, 'first_name', customer_firstname,"
    " 'last_name', customer_lastname, 'created', UNIX_TIMESTAMP(created_at), 'modified', UNIX_TIMESTAMP(updated_at))"
    " FROM sales_order WHERE updated_at >= FROM_UNIXTIME({since}) ORDER BY updated_at, entity_id LIMIT {limit}"
)
# Magento's order states; "pending_payment" waits for an online payment.
ORDER_STATES = {
    "new": OrderStatus.NEW,
    "holded": OrderStatus.NEW,
    "payment_review": OrderStatus.NEW,
    "pending_payment": OrderStatus.UNFINISHED,
    "processing": OrderStatus.PROCESSING,
    "complete": OrderStatus.COMPLETED,
    "closed": OrderStatus.CANCELLED,
    "canceled": OrderStatus.CANCELLED,
}


class MagentoProvisioner(ContainerProvisioner):
    START_FAILED = "Magento nie wystartował."
    VOLUME_PATH = DATA_PATH

    def image(self):
        return settings.SHOPS_MAGENTO_IMAGE

    def container_environment(self, shop):
        return {}

    def ready_command(self):
        # The entrypoint has prepared the shop's files and the web server answers.
        return ["sh", "-c", f"test -d {DATA_PATH}/var && curl -s -o /dev/null http://localhost/"]

    def default_admin_login(self, shop):
        return ADMIN_USERNAME

    def memory(self, shop):
        # Magento doesn't run on less, whatever the plan.
        plan, minimum = container_memory(shop), settings.SHOPS_MAGENTO_MEMORY
        return plan if memory_bytes(plan) >= memory_bytes(minimum) else minimum

    # --- steps ---

    def step_install_magento(self, shop):
        config = shop.config
        credentials = self._credentials(shop)
        if not credentials.admin_password:
            credentials.admin_login = ADMIN_USERNAME
            credentials.admin_password = _password()
            credentials.save(update_fields=["admin_login", "admin_password", "updated_at"])
        # The panel's address is random, which keeps it hidden from bots.
        if not shop.admin_path:
            shop.admin_path = f"admin_{secrets.token_hex(4)}"
            shop.save(update_fields=["admin_path", "updated_at"])
        if not self._installed(shop):
            secure = settings.SHOPS_URL_SCHEME == "https"
            # A retry after a failed installation starts over with an empty database.
            self._magento(shop, [
                "setup:install",
                "--cleanup-database",
                f"--base-url={_base_url(shop)}",
                # Magento takes only an https address as the secure one.
                *([f"--base-url-secure={_base_url(shop)}", "--use-secure=1", "--use-secure-admin=1"] if secure else []),
                f"--db-host={settings.SHOPS_DB_CONTAINER}",
                f"--db-name={db_name(shop)}",
                f"--db-user={db_name(shop)}",
                f"--db-password={credentials.db_password}",
                f"--backend-frontname={shop.admin_path}",
                f"--admin-user={credentials.admin_login}",
                f"--admin-password={credentials.admin_password}",
                f"--admin-email={config.contact_email}",
                "--admin-firstname=Właściciel",
                "--admin-lastname=Sklepu",
                f"--language={config.language}",
                f"--currency={config.currency}",
                f"--timezone={COUNTRY_TIMEZONES.get(config.country, 'UTC')}",
                "--use-rewrites=1",
                "--search-engine=opensearch",
                f"--opensearch-host={settings.SHOPS_SEARCH_CONTAINER}",
                "--opensearch-port=9200",
                f"--opensearch-index-prefix={index_prefix(shop)}",
                "--opensearch-enable-auth=0",
                "--session-save=files",
                "--no-interaction",
            ])
            # The code is compiled in the image already; only the mode is switched.
            self._magento(shop, ["deploy:mode:set", "production", "--skip-compilation"])
        # The web server still remembers the shop from before the installation (no env.php) and would send
        # visitors to /setup/; a graceful restart lets it read the shop afresh.
        self._exec(container_name(shop), ["apachectl", "-k", "graceful"])
        # Also covers an installation from an earlier attempt: the login is always what we stored.
        self._set_admin(shop, credentials.admin_password)

    def step_configure_shop(self, shop):
        config = shop.config
        values = {
            "general/country/default": config.country,
            "general/store_information/country_id": config.country,
            "shipping/origin/country_id": config.country,
            "design/head/default_description": config.description,
            **_name_values(shop.name),
            # Cheques are switched off for good; the app turns the others on.
            "payment/checkmo/active": "0",
            "payment/banktransfer/active": "0",
            "payment/cashondelivery/active": "0",
            # Magento's courier charges per item by default; the app sets one price per order.
            "carriers/flatrate/type": "O",
            "carriers/flatrate/active": "0",
            "carriers/freeshipping/active": "0",
            "carriers/sklepowniapickup/active": "0",
            # Guests can buy without an account, stock is tracked.
            "checkout/options/guest_checkout": "1",
            "cataloginventory/item_options/manage_stock": "1",
            **_email_values(shop.name, config.contact_email),
            **_title_values(config.language),
        }
        self._run(shop, "config", values)
        self._run(shop, "home", {"title": shop.name, "content": _home_content(config.description)})
        # Order confirmations and the copies of them for the owner.
        relay = mail_relay(shop)
        if relay is not None:
            self._configure_mail(shop, relay)

    def step_create_categories(self, shop):
        config = shop.config
        self._run(shop, "catalog", {
            "names": category_names(config.industry, config.category_count),
            "samples": config.include_sample_products,
            "sample_categories": SAMPLE_PRODUCT_CATEGORIES,
            "per_category": SAMPLE_PRODUCTS_PER_CATEGORY,
            "description": "To jest przykładowy produkt. Zmień jego opis, zdjęcia i cenę w panelu sklepu.",
        })

    def step_configure_navigation(self, shop):
        # Categories are in Luma's menu by themselves; search and filters need the indexes built.
        self._magento(shop, ["indexer:reindex"])
        self._magento(shop, ["cache:flush"])

    def step_health_check(self, shop):
        self._check_pages(shop, [
            ("strona sklepu", [self.proxy_url("/")]),
            ("wyszukiwarka", [self.proxy_url("/catalogsearch/result/?q=produkt")]),
            ("panel sklepu", [self.proxy_url(f"/{shop.admin_path}/")]),
        ])

    # --- running shops ---

    def read_settings(self, shop):
        data = self._run(shop, "read")
        rate = data["tax_rate"]
        return {
            "general": {
                "name": data["name"] or "",
                "description": data["description"] or "",
                "contact_email": data["email"] or "",
            },
            "payments": {
                "bank_transfer_enabled": _yes(data["bank_transfer"]),
                "bank_account_name": data["bank_owner"] or "",
                "bank_account_number": data["bank_number"] or "",
                "bank_name": data["bank_bank"] or "",
                "cash_on_delivery_enabled": _yes(data["cash_on_delivery"]),
            },
            "shipping": {
                "courier_enabled": _yes(data["flatrate"]),
                "courier_cost": _money(data["flatrate_price"]),
                "free_shipping_enabled": _yes(data["freeshipping"]),
                "free_shipping_min_amount": _money(data["freeshipping_subtotal"]),
                "local_pickup_enabled": _yes(data["pickup"]),
            },
            "taxes": {
                "enabled": data["tax_enabled"],
                "prices_include_tax": _yes(data["prices_include_tax"]),
                **({"standard_rate": _money(rate)} if rate is not None else {}),
            },
            "region": {
                "language": data["locale"] or "en_US",
                "currency": data["currency"] or "",
                "country": data["country"] or "",
                "timezone": data["timezone"] or "UTC",
            },
        }

    def apply_settings(self, shop, changes, values):
        region = changes.get("region", {})
        updates = {}
        if "general" in changes:
            general = values["general"]
            updates.update({
                "design/head/default_description": general["description"],
                **_name_values(general["name"]),
                **_email_values(general["name"], general["contact_email"]),
            })
        if "language" in region:
            updates["general/locale/code"] = region["language"]
            updates.update(_title_values(region["language"]))
        if "currency" in region:
            updates.update({
                "currency/options/base": region["currency"],
                "currency/options/default": region["currency"],
                "currency/options/allow": region["currency"],
            })
        if "country" in region:
            updates.update({
                "general/country/default": region["country"],
                "general/store_information/country_id": region["country"],
                "shipping/origin/country_id": region["country"],
            })
        if "timezone" in region:
            updates["general/locale/timezone"] = region["timezone"]
        # The transfer instructions are in the shop's language.
        if "payments" in changes or "language" in region:
            payments = values["payments"]
            updates.update({
                "payment/banktransfer/active": _flag(payments["bank_transfer_enabled"]),
                "payment/banktransfer/instructions": _bank_instructions(payments, values["region"]["language"]),
                "payment/cashondelivery/active": _flag(payments["cash_on_delivery_enabled"]),
                BANK_PATH + "owner": payments["bank_account_name"],
                BANK_PATH + "number": payments["bank_account_number"],
                BANK_PATH + "bank": payments["bank_name"],
            })
        if "shipping" in changes:
            shipping = values["shipping"]
            updates.update({
                "carriers/flatrate/active": _flag(shipping["courier_enabled"]),
                "carriers/flatrate/type": "O",
                "carriers/flatrate/price": shipping["courier_cost"],
                "carriers/freeshipping/active": _flag(shipping["free_shipping_enabled"]),
                "carriers/freeshipping/free_shipping_subtotal": shipping["free_shipping_min_amount"],
                "carriers/sklepowniapickup/active": _flag(shipping["local_pickup_enabled"]),
            })
        if updates:
            self._run(shop, "config", updates)
        # The VAT rate belongs to the country.
        if "taxes" in changes or "country" in region:
            taxes = values["taxes"]
            self._run(shop, "taxes", {
                "enabled": taxes["enabled"],
                "include": taxes["prices_include_tax"],
                "rate": taxes["standard_rate"],
                "country": values["region"]["country"],
            })
        if "general" in changes:
            self._run(shop, "home", {
                "title": values["general"]["name"], "content": _home_content(values["general"]["description"]),
            })
        if "language" in region:
            self._set_admin(shop, self._credentials(shop).admin_password)

    def reset_admin_password(self, shop):
        credentials = self._credentials(shop)
        password = _password()
        # Also logs out whoever was signed in with the old one.
        self._set_admin(shop, password)
        credentials.admin_password = password
        credentials.save(update_fields=["admin_password", "updated_at"])

    def remove_sample_products(self, shop):
        return int(self._run(shop, "remove_samples")["removed"])

    def update_address(self, shop):
        if self._find_container(shop) is None:
            return None
        self.step_start_container(shop)
        previous = self._run(shop, "read")["base_url"]
        self._run(shop, "config", {
            "web/unsecure/base_url": _base_url(shop),
            "web/secure/base_url": _base_url(shop),
        })
        return previous.rstrip("/")

    def teardown(self, shop):
        super().teardown(shop)
        # The shop's indexes in the shared search engine; the prefix ends with "_" so shop_1 never matches shop_12.
        self._exec(settings.SHOPS_SEARCH_CONTAINER, [
            "curl", "-s", "-f", "-X", "DELETE", f"http://localhost:9200/{index_prefix(shop)}_*",
        ])

    def _configure_mail(self, shop, relay):
        # Magento's own SMTP client, without logging in. Our module's plugin sets the sender (Plugin/MailSender.php).
        self._run(shop, "config", {
            "system/smtp/disable": "0",
            "system/smtp/transport": "smtp",
            "system/smtp/host": relay["host"],
            "system/smtp/port": str(relay["port"]),
            "system/smtp/auth": "none",
            "system/smtp/ssl": "",
            "system/smtp/username": "",
            MAIL_SENDER_PATH: relay["sender"],
        })

    def read_orders(self, shop, since, limit):
        output = self._sql(
            READ_ORDERS_SQL.format(since=int(since.timestamp()), limit=int(limit)), database=db_name(shop), raw=True,
        )
        orders = []
        for line in filter(None, output.splitlines()):
            row = json.loads(line, parse_float=Decimal)
            orders.append(Order(
                external_id=str(row["id"]),
                number=row["number"] or str(row["id"]),
                status=ORDER_STATES.get(row["state"], OrderStatus.NEW),
                total=Decimal(row["total"] or 0).quantize(Decimal("0.01")),
                currency=row["currency"] or shop.config.currency,
                items=int(row["items"] or 0),
                customer=customer_label(row["first_name"], row["last_name"]),
                placed_at=from_timestamp(row["created"]),
                changed_at=from_timestamp(row["modified"] or row["created"]),
            ))
        return orders

    # --- helpers ---

    def _installed(self, shop):
        """The installation finished: it writes the installation date into env.php last."""
        try:
            self._exec(container_name(shop), ["grep", "-q", "'date'", f"{DATA_PATH}/env.php"])
        except CommandError:
            return False
        return True

    def _set_admin(self, shop, password):
        config = shop.config
        self._run(shop, "admin", {
            "username": self._credentials(shop).admin_login,
            "email": config.contact_email,
            "password": password,
            "locale": config.language,
        })

    def _magento(self, shop, arguments, environment=None):
        # As the web server's user, so files it writes (cache, generated code) stay readable for the shop.
        return self._exec(
            container_name(shop), ["php", f"{FILES_PATH}/bin/magento", *arguments],
            user="www-data", environment=environment,
        )

    def _run(self, shop, action, data=None):
        """`sklepownia:run <action>` with `data`; returns its JSON result."""
        # In the environment, not the arguments: passwords never show up in the process list.
        encoded = base64.b64encode(json.dumps(data if data is not None else {}).encode()).decode()
        output = self._magento(shop, ["sklepownia:run", action], environment={"SKLEPOWNIA_DATA": encoded})
        if OUTPUT_MARKER not in output:
            raise CommandError(f"sklepownia:run {action}: no result: {output[-2000:]}")
        return json.loads(output.rsplit(OUTPUT_MARKER, 1)[1])


def index_prefix(shop):
    return f"shop_{shop.pk}"


def _base_url(shop):
    return f"{shop.url}/"


def _password():
    """Magento wants both letters and digits in an administrator's password."""
    alphabet = string.ascii_letters + string.digits
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(20))
        if re.search(r"[a-zA-Z]", password) and re.search(r"\d", password):
            return password


def _name_values(name):
    """Where the shop's name shows: page titles, the logo's text, the footer. Also drops Luma's "Default welcome msg!"."""
    return {
        "general/store_information/name": name,
        "design/head/default_title": name,
        "design/head/title_suffix": f" | {name}",
        "design/header/logo_alt": name,
        "design/header/welcome": "",
        "design/footer/copyright": f"© {name}",
    }


def _email_values(name, email):
    """
    Every sender address Magento has (general, sales, support and the two custom ones), where the contact form
    goes, and who gets a copy of every order confirmation: the owner, like WooCommerce's new-order alert.
    """
    values = {
        "contact/email/recipient_email": email,
        "sales_email/order/copy_to": email,
        "sales_email/order/copy_method": "bcc",
    }
    for ident in ("general", "sales", "support", "custom1", "custom2"):
        values[f"trans_email/ident_{ident}/email"] = email
        values[f"trans_email/ident_{ident}/name"] = name
    return values


def _title_values(language):
    titles = TITLES.get(language, TITLES["en_US"])
    values = {f"carriers/{carrier}/title": titles[carrier] for carrier in CARRIERS}
    values.update({f"carriers/{carrier}/name": titles[carrier] for carrier in CARRIERS})
    values["payment/banktransfer/title"] = titles["banktransfer"]
    values["payment/cashondelivery/title"] = titles["cashondelivery"]
    return values


def _bank_instructions(payments, language):
    titles = TITLES.get(language, TITLES["en_US"])
    lines = [
        (titles["recipient"], payments["bank_account_name"]),
        (titles["account"], payments["bank_account_number"]),
        (titles["bank"], payments["bank_name"]),
    ]
    return "\n".join(f"{label}: {value}" for label, value in lines if value)


def _home_content(description):
    paragraph = f"<p>{_escape(description)}</p>\n" if description else ""
    return paragraph + PRODUCTS_WIDGET


def _escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _flag(value):
    return "1" if value else "0"


def _yes(value):
    return str(value) == "1"
