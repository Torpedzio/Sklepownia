import random
import secrets
import time
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from .. import shop_settings
from ..models import Server, Shop, ShopChecklist, ShopCredentials, ShopSettings
from ..orders import Action, Address, Order, OrderDetail, OrderLine, Status, actions_for, customer_label
from ..platforms import platform_info
from ..products import Category, Filter, Product, ProductDetail, ProductPage, page_of
from ..remote import NotInShop, ShopApiError
from ..remote.fake import FakeApi
from .base import (
    Backup, BaseProvisioner, ContainerState, NothingToBackUp, PageCheck, ProductCount, ProvisioningError, Snapshot,
)


FAKE_STATUSES = (Status.NEW, Status.PROCESSING, Status.COMPLETED, Status.CANCELLED, Status.UNFINISHED)
FAKE_PEOPLE = (
    ("Anna", "Nowak"), ("Jan", "Kowalski"), ("Ewa", "Wiśniewska"), ("Piotr", "Zieliński"), ("Maria", "Lewandowska"),
    ("Tomasz", "Bąk"),
)
FAKE_CUSTOMERS = tuple(customer_label(first, last) for first, last in FAKE_PEOPLE)
FAKE_PRODUCTS = ("Kubek ceramiczny", "Świeca sojowa", "Notes w kratkę", "Torba lniana", "Herbata zielona")
FAKE_SHIPPING = Decimal("14.99")
# How many made-up products a shop has, newest (highest id) first; more than one page.
FAKE_PRODUCT_COUNT = 40
FAKE_CATEGORIES = (Category("1", "Prezenty"), Category("2", "Dom"), Category("3", "Kuchnia"))


class FakeProvisioner(BaseProvisioner):
    """Simulates provisioning without touching any infrastructure."""

    # Simulated backup repository {snapshot id: Snapshot}; per process, so empty whenever the worker starts.
    snapshots = {}
    # Snapshot ids restored, oldest first.
    restored = []
    # Breakdowns set by tests: {shop id: ContainerState, or None when the container is gone}, {shop id: PageCheck},
    # {service name: problem} and (free, total) disk bytes.
    containers = {}
    pages = {}
    services = {}
    disk = None
    # (shop id, "start" or "restart") done by the monitor, oldest first; whether they fix the shop.
    repairs = []
    repairs_help = True
    # Parcels given with "shipped": {(shop id, order id): (number, carrier)}.
    parcels = {}
    # {(shop pk, product id): pieces} set from the app.
    stocks = {}
    # {(shop pk, product id): {field: value}} changed from the app; "created" and "deleted" mark the product's fate.
    product_edits = {}

    def run_step(self, key, shop):
        time.sleep(settings.FAKE_PROVISIONER_STEP_DELAY)
        if key == settings.FAKE_PROVISIONER_FAIL_AT_STEP:
            raise ProvisioningError(f"Symulowany błąd w kroku {key}")
        handler = getattr(self, f"step_{key}", None)
        if handler:
            handler(shop)

    def step_allocate_server(self, shop):
        shop.server = Server.objects.filter(is_active=True).first()
        shop.save(update_fields=["server", "updated_at"])

    def step_install_prestashop(self, shop):
        shop.admin_path = "admin-demo"
        shop.save(update_fields=["admin_path", "updated_at"])
        ShopCredentials.objects.update_or_create(
            shop=shop,
            defaults={"admin_login": shop.config.contact_email, "admin_password": secrets.token_urlsafe(24)},
        )

    def step_install_magento(self, shop):
        shop.admin_path = "admin_demo"
        shop.save(update_fields=["admin_path", "updated_at"])
        ShopCredentials.objects.update_or_create(
            shop=shop, defaults={"admin_login": "admin", "admin_password": secrets.token_urlsafe(24)},
        )

    def step_generate_api_keys(self, shop):
        # WooCommerce's administrator is only made here.
        credentials, _ = ShopCredentials.objects.get_or_create(
            shop=shop, defaults={"admin_login": "admin", "admin_password": secrets.token_urlsafe(24)},
        )
        credentials.api_key = secrets.token_urlsafe(24)
        credentials.save(update_fields=["api_key", "updated_at"])

    def api(self, shop):
        return FakeApi(shop)

    # Settings live only in the platform's database: what was saved is what the shop "has".

    def read_settings(self, shop):
        stored = ShopSettings.objects.filter(shop=shop).first()
        values = stored.values if stored else shop_settings.default_settings(shop)
        # Like a real shop: only what the platform has.
        return {section: values[section] for section in platform_info(shop.platform).settings_sections}

    def apply_settings(self, shop, changes, values):
        self._simulate("apply_settings")

    def publish_documents(self, shop, documents):
        self._simulate("publish_documents")
        return {document.key: f"{shop.url}/{document.slug}/" for document in documents}

    def reset_admin_password(self, shop):
        self._simulate("reset_admin_password")
        ShopCredentials.objects.filter(shop=shop).update(admin_password=secrets.token_urlsafe(18))

    def set_admin_password(self, shop, password):
        self._simulate("set_admin_password")

    def can_back_up(self):
        return True

    def backup(self, shop, tag):
        self._simulate("backup")
        # Shops get their credentials early in the setup; before that there is nothing to copy.
        if not ShopCredentials.objects.filter(shop=shop).exists():
            raise NothingToBackUp()
        snapshot = Snapshot(
            id=secrets.token_hex(32), host=f"shop-{shop.pk}", time=timezone.now(), tags=(tag,), size=48_000_000,
        )
        self.snapshots[snapshot.id] = snapshot
        return Backup(snapshot_id=snapshot.id, size=snapshot.size)

    def restore_backup(self, shop, snapshot_id):
        self._simulate("restore_backup")
        self.restored.append(snapshot_id)

    def list_backups(self):
        return list(self.snapshots.values())

    def forget_backups(self, snapshot_ids):
        for snapshot_id in snapshot_ids:
            self.snapshots.pop(snapshot_id, None)

    def prune_backups(self):
        pass

    def can_monitor(self):
        return True

    def container_states(self):
        """Running shops have a running container, suspended ones a stopped one."""
        live = {
            Shop.Status.ACTIVE: ContainerState("running", "healthy"),
            Shop.Status.SUSPENDED: ContainerState("exited"),
        }
        states = {
            shop_id: live[status]
            for shop_id, status in Shop.objects.filter(status__in=live).values_list("pk", "status")
        }
        for shop_id, state in self.containers.items():
            if state is None:
                states.pop(shop_id, None)
            else:
                states[shop_id] = state
        return states

    def check_page(self, shop):
        return self.pages.get(shop.pk, PageCheck(status=200, seconds=0.12))

    def start_shop(self, shop):
        return self._repair(shop, "start")

    def restart_shop(self, shop):
        return self._repair(shop, "restart")

    def service_problems(self, required, optional=()):
        if "docker" in self.services:
            return {"docker": self.services["docker"]}
        return {name: problem for name, problem in self.services.items() if name in [*required, *optional]}

    def disk_space(self):
        return self.disk

    def _repair(self, shop, action):
        self._simulate(action)
        type(self).repairs.append((shop.pk, action))
        if self.repairs_help:
            self.containers.pop(shop.pk, None)
            self.pages.pop(shop.pk, None)
        return self.repairs_help

    def remove_sample_products(self, shop):
        self._simulate("remove_sample_products")
        return 6 if shop.config.include_sample_products else 0

    def count_products(self, shop):
        """What was counted last (the samples are gone once removed); at first, the samples only."""
        self._simulate("count_products")
        stored = ShopChecklist.objects.filter(shop=shop).first()
        samples = 6 if shop.config.include_sample_products else 0
        if stored and stored.sample_products is not None:
            samples = stored.sample_products
        return ProductCount(products=(stored.products if stored else None) or 0, samples=samples)

    def read_orders(self, shop, since, limit):
        """Made-up orders, the same on every read: from 45 days before the shop was created until now."""
        self._simulate("read_orders")
        rng = random.Random(shop.pk)
        now = timezone.now()
        placed = shop.created_at - timedelta(days=45)
        number = 1000
        orders = []
        while placed <= now:
            number += 1
            status = rng.choices(FAKE_STATUSES, weights=(2, 3, 8, 1, 1))[0]
            orders.append(Order(
                external_id=str(number), number=str(number), status=status,
                total=Decimal(rng.randrange(2900, 39900)) / 100, currency=shop.config.currency,
                items=rng.randint(1, 4), customer=rng.choice(FAKE_CUSTOMERS), placed_at=placed, changed_at=placed,
            ))
            placed += timedelta(hours=rng.randint(5, 30))
        return [order for order in orders if order.changed_at >= since][:limit]

    def read_order(self, shop, external_id):
        """The order from the local copy, filled in with made-up details that are the same on every read."""
        FakeApi(shop).ping()
        order = shop.orders.filter(external_id=str(external_id)).first()
        if order is None:
            raise NotInShop("Nie ma tego zamówienia w sklepie.")
        rng = random.Random(f"{shop.pk}:{order.external_id}")
        first, last = next(
            (person for person in FAKE_PEOPLE if customer_label(*person) == order.customer), rng.choice(FAKE_PEOPLE),
        )
        shipping = FAKE_SHIPPING if order.total > FAKE_SHIPPING * 2 else Decimal("0.00")
        products = order.total - shipping
        count = max(order.items, 1)
        names = rng.sample(FAKE_PRODUCTS, min(count, len(FAKE_PRODUCTS)))
        prices = [(products / len(names)).quantize(Decimal("0.01"))] * len(names)
        prices[-1] = products - sum(prices[:-1])
        address = Address(
            name=f"{first} {last}", company="", lines=(f"ul. Polna {rng.randint(1, 80)}",), postcode="00-950",
            city="Warszawa", country="Polska", phone=f"+48 600 {rng.randint(100, 999)} {rng.randint(100, 999)}",
        )
        return OrderDetail(
            external_id=order.external_id, number=order.number, status=order.status, currency=order.currency,
            products_total=products, shipping_total=shipping, discount_total=Decimal("0.00"), total=order.total,
            payment_method="Przelew bankowy", shipping_method="Kurier" if shipping else "Odbiór osobisty",
            customer_name=address.name, email=f"{first.lower()}@example.com", phone=address.phone,
            billing=address, shipping=address,
            lines=tuple(
                OrderLine(name=name, sku=f"SKU-{index + 1:03}", quantity=1, price=price, total=price)
                for index, (name, price) in enumerate(zip(names, prices))
            ),
            customer_note="Proszę o kontakt przed wysyłką." if rng.random() < 0.3 else "",
            placed_at=order.placed_at,
            tracking_number=self.parcels.get((shop.pk, order.external_id), ("", ""))[0],
            carrier=self.parcels.get((shop.pk, order.external_id), ("", ""))[1],
            actions=actions_for(order.status),
        )

    def read_products(self, shop, *, query, stock_filter, offset, limit):
        """Made-up products, the same on every read, with what the app changed."""
        FakeApi(shop).ping()
        products = [self._detail(shop, id) for id in self._product_ids(shop)]
        if query:
            products = [p for p in products if query.lower() in p.name.lower() or query.lower() in p.sku.lower()]
        if stock_filter == Filter.OUT_OF_STOCK:
            products = [product for product in products if not product.in_stock]
        rows, has_more = page_of(products[offset:offset + limit + 1], limit)
        return ProductPage(products=tuple(Product(**{
            name: getattr(row, name) for name in Product.__dataclass_fields__
        }) for row in rows), has_more=has_more)

    def read_product(self, shop, external_id):
        FakeApi(shop).ping()
        if str(external_id) not in self._product_ids(shop):
            raise NotInShop("Nie ma tego produktu w sklepie.")
        return self._detail(shop, str(external_id))

    def read_categories(self, shop):
        FakeApi(shop).ping()
        return FAKE_CATEGORIES

    def set_product_stock(self, shop, product, quantity):
        self._fail_at("set_product_stock", shop)
        self.stocks[(shop.pk, product.external_id)] = quantity

    def update_product(self, shop, product, changes):
        self._fail_at("update_product", shop)
        self.product_edits.setdefault((shop.pk, product.external_id), {}).update(changes)

    def create_product(self, shop, fields):
        self._fail_at("create_product", shop)
        ids = [int(id) for id in self._product_ids(shop)] + [FAKE_PRODUCT_COUNT]
        external_id = str(max(ids) + 1)
        self.product_edits[(shop.pk, external_id)] = {"created": True, **fields}
        if fields.get("stock") is not None:
            self.stocks[(shop.pk, external_id)] = fields["stock"]
        return external_id

    def delete_product(self, shop, product):
        self._fail_at("delete_product", shop)
        self.product_edits[(shop.pk, product.external_id)] = {"deleted": True}

    def _fail_at(self, step, shop):
        FakeApi(shop).ping()
        if settings.FAKE_PROVISIONER_FAIL_AT_STEP == step:
            raise ShopApiError(f"Symulowany błąd: {step}")

    def _product_ids(self, shop):
        """Newest first: the ones added from the app, then the made-up ones; without the deleted ones."""
        added = sorted(
            (int(id) for (pk, id), edits in self.product_edits.items() if pk == shop.pk and edits.get("created")),
            reverse=True,
        )
        ids = [str(id) for id in [*added, *range(FAKE_PRODUCT_COUNT, 0, -1)]]
        return [id for id in ids if not self.product_edits.get((shop.pk, id), {}).get("deleted")]

    def _detail(self, shop, external_id):
        """
        A made-up product with the app's changes. Every 7th has variants, every 9th isn't counted, every 11th is
        hidden, every 5th is sold out and every 4th on sale.
        """
        number = int(external_id)
        edits = self.product_edits.get((shop.pk, external_id), {})
        key = (shop.pk, external_id)
        if edits.get("created"):
            price, sale, counted, variants = edits["price"], edits.get("sale_price"), key in self.stocks, False
            fields = {"name": edits["name"], "sku": edits.get("sku", ""), "visible": edits.get("visible", True),
                      "description": edits.get("description", ""), "categories": edits.get("categories", [])}
            stock = self.stocks.get(key, 0)
        else:
            rng = random.Random(f"{shop.pk}:product:{number}")
            price = Decimal(rng.randrange(1900, 19900)) / 100
            sale = (price * Decimal("0.8")).quantize(Decimal("0.01")) if number % 4 == 0 else None
            # Setting the stock from the app starts counting it.
            counted, variants = number % 9 != 0 or key in self.stocks, number % 7 == 0
            stock = self.stocks.get(key, 0 if number % 5 == 0 else rng.randint(1, 60))
            fields = {
                "name": f"{FAKE_PRODUCTS[number % len(FAKE_PRODUCTS)]} {number}", "sku": f"SKU-{number:03}",
                "visible": number % 11 != 0, "description": "Ręcznie robiony.\n\nPakowany na prezent.",
                "categories": ["1"] if number % 2 else ["2", "3"],
            }
            price, sale = edits.get("price", price), edits.get("sale_price", sale)
            fields.update({name: edits[name] for name in fields if name in edits})
        names = dict((category.id, category) for category in FAKE_CATEGORIES)
        return ProductDetail(
            external_id=external_id, name=fields["name"], sku=fields["sku"],
            price=sale if sale is not None else price, regular_price=price if sale is not None else None,
            stock=stock if counted else None, in_stock=stock > 0 if counted else True, visible=fields["visible"],
            image="", has_variants=variants,
            categories=tuple(names[id] for id in fields["categories"] if id in names),
            url=f"{shop.url}/produkt/{external_id}/" if fields["visible"] else "",
            description=fields["description"], formatted_description=number % 13 == 0,
        )

    def change_order(self, shop, order, action, *, tracking_number="", carrier=""):
        """Changes the order in the local copy, which read_order fills in."""
        FakeApi(shop).ping()
        time.sleep(settings.FAKE_PROVISIONER_STEP_DELAY)
        if settings.FAKE_PROVISIONER_FAIL_AT_STEP == "change_order":
            raise ShopApiError("Symulowany błąd: change_order")
        status = {
            Action.MARK_PAID: Status.PROCESSING, Action.MARK_SHIPPED: Status.COMPLETED, Action.CANCEL: Status.CANCELLED,
        }[action]
        shop.orders.filter(external_id=order.external_id).update(status=status, changed_at=timezone.now())
        if action == Action.MARK_SHIPPED and tracking_number:
            self.parcels[(shop.pk, order.external_id)] = (tracking_number, carrier)

    def _simulate(self, key):
        time.sleep(settings.FAKE_PROVISIONER_STEP_DELAY)
        if key == settings.FAKE_PROVISIONER_FAIL_AT_STEP:
            raise ProvisioningError(f"Symulowany błąd: {key}")
