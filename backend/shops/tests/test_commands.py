from io import StringIO

import pytest
from django.core.management import CommandError, call_command

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


class MailProvisioner(BaseProvisioner):
    """configure_mail answers by slug: configured, nothing running, or a failure."""

    results = {}

    def configure_mail(self, shop):
        result = self.results[shop.slug]
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def mail_shops(settings):
    settings.SHOP_PROVISIONER = "shops.tests.test_commands.MailProvisioner"
    settings.SHOPS_SMTP_HOST = "shops-mail"
    settings.SHOPS_MAIL_DOMAIN = "sklepy.example.pl"
    owner = User.objects.create_user(email="wlasciciel@example.com", password="Sekretne-haslo-123")
    statuses = {
        "palarnia": Shop.Status.ACTIVE, "bez-kontenera": Shop.Status.ACTIVE, "zepsuty": Shop.Status.ACTIVE,
        "zawieszony": Shop.Status.SUSPENDED, "usuniety": Shop.Status.DELETED,
    }
    for slug, status in statuses.items():
        Shop.objects.create(owner=owner, name=slug, slug=slug, status=status)
    MailProvisioner.results = {
        "palarnia": True, "bez-kontenera": False, "zepsuty": RuntimeError("brak połączenia z Dockerem"),
    }


def test_configure_shop_mail_reports_every_running_shop(mail_shops):
    out, err = StringIO(), StringIO()

    call_command("configure_shop_mail", stdout=out, stderr=err)

    lines = out.getvalue().splitlines()
    assert "palarnia: wysyła jako palarnia@sklepy.example.pl" in lines
    assert "bez-kontenera: pominięty, brak kontenera sklepu" in lines
    assert "zepsuty: nie udało się ustawić poczty (brak połączenia z Dockerem)" in err.getvalue()
    assert "Zawieszone sklepy (1) są pominięte: uruchom polecenie ponownie po ich przywróceniu." in lines
    assert "usuniety" not in out.getvalue() + err.getvalue()


def test_configure_shop_mail_for_chosen_shops(mail_shops):
    out, err = StringIO(), StringIO()

    call_command("configure_shop_mail", "palarnia", "nieznany", stdout=out, stderr=err)

    assert out.getvalue().splitlines() == ["palarnia: wysyła jako palarnia@sklepy.example.pl"]
    assert err.getvalue().splitlines() == ["nieznany: nie ma takiego działającego sklepu"]


def test_configure_shop_mail_needs_a_mail_server(mail_shops, settings):
    settings.SHOPS_SMTP_HOST = ""

    with pytest.raises(CommandError, match="SHOPS_SMTP_HOST"):
        call_command("configure_shop_mail")


def test_base_provisioner_defaults():
    provisioner = BaseProvisioner()
    shop = Shop(slug="sklep")

    assert provisioner.cleanup(shop) is None
    assert provisioner.teardown(shop) is None
    assert provisioner.update_address(shop) is None
    assert provisioner.configure_mail(shop) is False
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
