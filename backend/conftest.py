import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from accounts.models import User
from config.celery import app as celery_app


def _no_downloads(package):
    raise AssertionError(f"Tests must not download {package.url}")


@pytest.fixture(autouse=True)
def _test_settings(settings, tmp_path, monkeypatch):
    celery_app.conf.task_always_eager = True
    settings.SHOP_PROVISIONER = "shops.provisioning.fake.FakeProvisioner"
    settings.SHOPS_BASE_DOMAIN = "localhost"
    settings.SHOPS_URL_SCHEME = "https"
    settings.SHOPS_HTTP_PORT = 443
    settings.FAKE_PROVISIONER_STEP_DELAY = 0
    settings.FAKE_PROVISIONER_FAIL_AT_STEP = ""
    # Never the real payment gateway from .env: tests must not call Tpay.
    settings.PAYMENT_GATEWAY = "billing.gateways.fake.FakeGateway"
    settings.FAKE_GATEWAY_DECLINE_RENEWALS = False
    settings.TPAY_CLIENT_ID = ""
    settings.TPAY_CLIENT_SECRET = ""
    settings.TPAY_SECURITY_CODE = ""
    # Invoices are numbered here, never sent to Fakturownia from .env.
    settings.INVOICE_ISSUER = "billing.invoicing.platform.PlatformIssuer"
    settings.INVOICE_SELLER = {"name": "Sklepownia sp. z o.o.", "tax_id": "5260001246", "street": "Prosta 20",
                               "postal_code": "00-850", "city": "Warszawa", "bank_account": ""}
    settings.INVOICE_NUMBER_FORMAT = "FV/{year}/{month:02}/{number:04}"
    settings.FAKTUROWNIA_DOMAIN = ""
    settings.FAKTUROWNIA_API_TOKEN = ""
    # Notifications stay in memory (push_outbox), never reach Expo.
    settings.PUSH_SENDER = "push.senders.memory.MemorySender"
    settings.EXPO_ACCESS_TOKEN = ""
    # Uploaded avatars go to a throwaway folder.
    settings.MEDIA_ROOT = tmp_path / "media"
    # Plugins for shops are never fetched from their makers; tests that install one give the archive themselves.
    settings.SHOPS_PACKAGE_CACHE = str(tmp_path / "packages")
    monkeypatch.setattr("shops.provisioning.packages._download", _no_downloads)
    # The simulated backup repository starts empty, and never the real one from .env is used.
    from shops.provisioning.fake import FakeProvisioner

    monkeypatch.setattr(FakeProvisioner, "snapshots", {})
    monkeypatch.setattr(FakeProvisioner, "restored", [])
    # Every shop and service works until a test breaks one.
    for name, value in {"containers": {}, "pages": {}, "services": {}, "disk": None, "repairs": []}.items():
        monkeypatch.setattr(FakeProvisioner, name, value)
    monkeypatch.setattr(FakeProvisioner, "repairs_help", True)
    settings.SHOPS_BACKUP_PASSWORD = "backup-secret"
    # Throttle counters live in the cache; keep tests independent.
    cache.clear()


@pytest.fixture
def push_outbox():
    """Notifications sent during the test (push.senders.base.Message)."""
    from push.senders.memory import MemorySender

    MemorySender.reset()
    yield MemorySender.outbox
    MemorySender.reset()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(email="jan@example.com", password="Sekretne-haslo-123")


@pytest.fixture
def plan(db):
    """The Standard plan added by billing's migration."""
    from billing.models import Plan

    return Plan.objects.get(code="standard")


def subscribe(user, plan, **fields):
    """Gives `user` a paid, active plan, as if the first payment went through."""
    from datetime import timedelta

    from django.utils import timezone

    from billing.models import Subscription

    now = timezone.now()
    values = {
        "plan": plan,
        "status": Subscription.Status.ACTIVE,
        "current_period_start": now,
        "current_period_end": now + timedelta(days=30),
        "card_token": "tok_saved",
        "card_brand": "Visa",
        "card_tail": "4242",
        **fields,
    }
    subscription, _ = Subscription.objects.update_or_create(user=user, defaults=values)
    return subscription


@pytest.fixture
def unsubscribed_user(db):
    """Verified, but without a plan yet."""
    return User.objects.create_user(
        email="anna@example.com", password="Sekretne-haslo-123", is_email_verified=True,
    )


@pytest.fixture
def verified_user(unsubscribed_user, plan):
    """Verified and on an active plan, so shops can be created."""
    subscribe(unsubscribed_user, plan)
    return unsubscribed_user


@pytest.fixture
def auth_client(verified_user):
    client = APIClient()
    client.force_authenticate(verified_user)
    return client
