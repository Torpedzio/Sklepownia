import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from accounts.models import User
from config.celery import app as celery_app


@pytest.fixture(autouse=True)
def _test_settings(settings):
    celery_app.conf.task_always_eager = True
    settings.SHOP_PROVISIONER = "shops.provisioning.fake.FakeProvisioner"
    settings.SHOPS_URL_SCHEME = "https"
    settings.SHOPS_HTTP_PORT = 443
    settings.FAKE_PROVISIONER_STEP_DELAY = 0
    settings.FAKE_PROVISIONER_FAIL_AT_STEP = ""
    # Throttle counters live in the cache; keep tests independent.
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(email="jan@example.com", password="Sekretne-haslo-123")


@pytest.fixture
def verified_user(db):
    return User.objects.create_user(
        email="anna@example.com", password="Sekretne-haslo-123", is_email_verified=True,
    )


@pytest.fixture
def auth_client(verified_user):
    client = APIClient()
    client.force_authenticate(verified_user)
    return client
