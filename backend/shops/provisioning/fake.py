import secrets
import time

from django.conf import settings

from .. import shop_settings
from ..models import Server, ShopCredentials, ShopSettings
from ..platforms import platform_info
from .base import BaseProvisioner, ProvisioningError


class FakeProvisioner(BaseProvisioner):
    """Simulates provisioning without touching any infrastructure."""

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

    def reset_admin_password(self, shop):
        self._simulate("reset_admin_password")
        ShopCredentials.objects.filter(shop=shop).update(admin_password=secrets.token_urlsafe(18))

    def remove_sample_products(self, shop):
        self._simulate("remove_sample_products")
        return 6 if shop.config.include_sample_products else 0

    def _simulate(self, key):
        time.sleep(settings.FAKE_PROVISIONER_STEP_DELAY)
        if key == settings.FAKE_PROVISIONER_FAIL_AT_STEP:
            raise ProvisioningError(f"Symulowany błąd: {key}")
