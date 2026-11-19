import random
import secrets
import time
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from .. import shop_settings
from ..models import Server, ShopChecklist, ShopCredentials, ShopSettings
from ..orders import Order, Status
from ..platforms import platform_info
from .base import Backup, BaseProvisioner, NothingToBackUp, ProductCount, ProvisioningError, Snapshot


FAKE_STATUSES = (Status.NEW, Status.PROCESSING, Status.COMPLETED, Status.CANCELLED, Status.UNFINISHED)
FAKE_CUSTOMERS = ("Anna N.", "Jan K.", "Ewa W.", "Piotr Z.", "Maria L.", "Tomasz B.")


class FakeProvisioner(BaseProvisioner):
    """Simulates provisioning without touching any infrastructure."""

    # The simulated backup repository, {snapshot id: Snapshot}. It lives in the process, so it starts empty
    # whenever the worker does.
    snapshots = {}
    # Snapshot ids restored, oldest first.
    restored = []

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
        ShopCredentials.objects.update_or_create(
            shop=shop,
            defaults={
                "admin_login": "admin",
                "admin_password": secrets.token_urlsafe(24),
                "wp_application_password": secrets.token_urlsafe(24),
            },
        )

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

    # --- backups ---

    def can_back_up(self):
        return True

    def backup(self, shop, tag):
        self._simulate("backup")
        # Shops get their credentials early in the setup; before that there is nothing of them to copy.
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

    def _simulate(self, key):
        time.sleep(settings.FAKE_PROVISIONER_STEP_DELAY)
        if key == settings.FAKE_PROVISIONER_FAIL_AT_STEP:
            raise ProvisioningError(f"Symulowany błąd: {key}")
