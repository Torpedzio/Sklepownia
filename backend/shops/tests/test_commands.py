from io import StringIO

import pytest
from django.core.management import call_command

from accounts.models import User
from shops.models import Shop
from shops.provisioning.base import BaseProvisioner

pytestmark = pytest.mark.django_db


class MovingProvisioner(BaseProvisioner):
    """update_address answers by slug: where the shop was before, or a failure."""

    previous = {}

    def update_address(self, shop):
        result = self.previous[shop.slug]
        if isinstance(result, Exception):
            raise result
        return result if result != "same" else shop.url


@pytest.fixture
def shops(settings):
    settings.SHOP_PROVISIONER = "shops.tests.test_commands.MovingProvisioner"
    owner = User.objects.create_user(email="wlasciciel@example.com", password="Sekretne-haslo-123")
    for slug in ("bez-kontenera", "bez-zmian", "przeniesiony", "zepsuty", "usuniety"):
        status = Shop.Status.DELETED if slug == "usuniety" else Shop.Status.ACTIVE
        Shop.objects.create(owner=owner, name=slug, slug=slug, status=status)
    MovingProvisioner.previous = {
        "bez-kontenera": None,
        "bez-zmian": "same",
        "przeniesiony": "https://przeniesiony.stara-domena",
        "zepsuty": RuntimeError("brak połączenia z Dockerem"),
    }


def test_update_shop_addresses_reports_every_running_shop(shops):
    out, err = StringIO(), StringIO()

    call_command("update_shop_addresses", stdout=out, stderr=err)

    lines = out.getvalue().splitlines()
    assert "bez-kontenera: pominięty, brak kontenera sklepu" in lines
    assert "bez-zmian: bez zmian, https://bez-zmian.localhost" in lines
    assert "przeniesiony: https://przeniesiony.stara-domena → https://przeniesiony.localhost" in lines
    assert "zepsuty: nie udało się przenieść (brak połączenia z Dockerem)" in err.getvalue()
    # Deleted shops are left alone.
    assert "usuniety" not in out.getvalue() + err.getvalue()


def test_base_provisioner_defaults():
    provisioner = BaseProvisioner()
    shop = Shop(slug="sklep")

    assert provisioner.cleanup(shop) is None
    assert provisioner.teardown(shop) is None
    assert provisioner.update_address(shop) is None
    for method in ("read_settings", "reset_admin_password", "remove_sample_products"):
        with pytest.raises(NotImplementedError):
            getattr(provisioner, method)(shop)
    with pytest.raises(NotImplementedError):
        provisioner.apply_settings(shop, {}, {})


def test_run_step_calls_the_matching_method():
    class Recording(BaseProvisioner):
        ran = []

        def step_create_database(self, shop):
            self.ran.append(shop.slug)

    Recording().run_step("create_database", Shop(slug="sklep"))

    assert Recording.ran == ["sklep"]
