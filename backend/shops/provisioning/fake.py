import secrets
import time

from django.conf import settings

from ..models import Server, ShopCredentials
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

    def step_generate_api_keys(self, shop):
        ShopCredentials.objects.update_or_create(
            shop=shop,
            defaults={
                "wp_admin_username": "admin",
                "wp_admin_password": secrets.token_urlsafe(24),
                "wp_application_password": secrets.token_urlsafe(24),
            },
        )
