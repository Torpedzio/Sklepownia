import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from accounts.models import User
from config.celery import app as celery_app


@pytest.fixture(autouse=True)
def _test_settings(settings):
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
    # Throttle counters live in the cache; keep tests independent.
    cache.clear()


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
