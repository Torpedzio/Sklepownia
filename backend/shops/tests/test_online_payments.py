"""
Online payments in the shop settings: the operator's account in the settings, its keys only on their way to the shop.
The shop itself is the fake provisioner; what the platforms do with the values is in test_woocommerce/test_prestashop.
"""

import json
from datetime import timedelta

import pytest
from django.utils import timezone

from shops.models import Server, Shop, ShopOperation, ShopSettings
from shops.shop_settings import SECRET_PLACEHOLDER

pytestmark = pytest.mark.django_db

SAVE_SETTINGS = "shops.provisioning.fake.FakeProvisioner.apply_settings"
CRC = "0123456789abcdef"
API_KEY = "fedcba9876543210fedcba9876543210"
P24 = {"przelewy24_enabled": True, "przelewy24_merchant_id": "123456", "przelewy24_crc_key": CRC,
       "przelewy24_api_key": API_KEY}


@pytest.fixture
def new_shop(auth_client, django_capture_on_commit_callbacks):
    def create(platform="woocommerce", template="storefront"):
        payload = {"name": "Mój Sklep", "slug": f"sklep-{platform}", "industry": "fashion", "template": template,
                   "platform": platform}
        with django_capture_on_commit_callbacks(execute=True):
            response = auth_client.post("/api/shops/", payload, format="json")
        assert response.status_code == 201, response.data
        return Shop.objects.get(pk=response.data["id"])

    return create


@pytest.fixture
def shop(new_shop):
    return new_shop()


@pytest.fixture
def applied(monkeypatch):
    """What the shop was given: (changes, values) of every apply_settings."""
    calls = []
    monkeypatch.setattr(SAVE_SETTINGS, lambda self, shop, changes, values: calls.append((changes, values)))
    return calls


def patch(client, shop, captured, payments):
    with captured(execute=True):
        return client.patch(f"/api/shops/{shop.pk}/settings/", {"payments": payments}, format="json")


def stored_payments(shop, **fields):
    from shops import services

    stored = services.get_settings(shop)
    stored.values["payments"].update(fields)
    stored.save()


def test_the_settings_say_which_operators_the_app_sets_up_and_where_the_shop_connects_from(auth_client, shop):
    Server.objects.filter(pk=shop.server_id).update(public_ip="203.0.113.7")

    data = auth_client.get(f"/api/shops/{shop.pk}/settings/").data

    assert data["payment_operators"] == ["przelewy24", "payu"]
    assert data["server_ip"] == "203.0.113.7"
    payments = data["values"]["payments"]
    assert payments["przelewy24_enabled"] is False and payments["przelewy24_keys_saved"] is False
    assert "przelewy24_crc_key" not in payments


def test_keys_go_to_the_shop_but_are_never_kept_or_shown(auth_client, shop, applied,
                                                         django_capture_on_commit_callbacks):
    response = patch(auth_client, shop, django_capture_on_commit_callbacks, P24)

    assert response.status_code == 202
    [(changes, values)] = applied
    assert changes["payments"]["przelewy24_crc_key"] == CRC
    assert values["payments"]["przelewy24_api_key"] == API_KEY

    operation = ShopOperation.objects.get(shop=shop)
    assert operation.status == ShopOperation.Status.SUCCEEDED
    assert operation.changes["payments"]["przelewy24_crc_key"] == SECRET_PLACEHOLDER
    assert operation.secrets == ""
    stored = ShopSettings.objects.get(shop=shop).values
    assert CRC not in json.dumps(stored) and API_KEY not in json.dumps(stored)

    data = auth_client.get(f"/api/shops/{shop.pk}/settings/").data
    payments = data["values"]["payments"]
    assert payments["przelewy24_enabled"] is True
    assert payments["przelewy24_merchant_id"] == "123456"
    assert payments["przelewy24_keys_saved"] is True
    assert CRC not in json.dumps(data, default=str)
    assert data["operation"]["changed_fields"] == [
        "Płatności Przelewy24", "ID sprzedawcy Przelewy24", "Klucz CRC Przelewy24", "Klucz API Przelewy24",
    ]


def test_a_failed_change_forgets_the_keys(auth_client, shop, settings, django_capture_on_commit_callbacks):
    settings.FAKE_PROVISIONER_FAIL_AT_STEP = "apply_settings"

    patch(auth_client, shop, django_capture_on_commit_callbacks, P24)

    operation = ShopOperation.objects.get(shop=shop)
    assert operation.status == ShopOperation.Status.FAILED
    assert operation.secrets == ""
    assert ShopSettings.objects.get(shop=shop).values["payments"]["przelewy24_keys_saved"] is False


def test_keys_wait_encrypted_until_the_worker_takes_them(auth_client, shop):
    from django.db import connection

    response = auth_client.patch(f"/api/shops/{shop.pk}/settings/", {"payments": P24}, format="json")
    assert response.status_code == 202

    operation = ShopOperation.objects.get(shop=shop)
    assert operation.secret_values == {"payments": {"przelewy24_crc_key": CRC, "przelewy24_api_key": API_KEY}}
    with connection.cursor() as cursor:
        cursor.execute("SELECT secrets FROM shops_shopoperation WHERE id = %s", [operation.pk])
        assert CRC not in cursor.fetchone()[0]


def test_keys_of_an_operation_that_never_finished_are_cleared(auth_client, shop, verified_user,
                                                              django_capture_on_commit_callbacks):
    stuck = ShopOperation.objects.create(shop=shop, kind=ShopOperation.Kind.UPDATE_SETTINGS,
                                         status=ShopOperation.Status.RUNNING, secrets=json.dumps({"payments": {}}),
                                         requested_by=verified_user)
    ShopOperation.objects.filter(pk=stuck.pk).update(created_at=timezone.now() - timedelta(hours=1))

    patch(auth_client, shop, django_capture_on_commit_callbacks, {"cash_on_delivery_enabled": True})

    stuck.refresh_from_db()
    assert stuck.secrets == ""


def test_turning_on_an_operator_needs_its_account_and_keys(auth_client, shop):
    response = auth_client.patch(f"/api/shops/{shop.pk}/settings/",
                                 {"payments": {"przelewy24_enabled": True}}, format="json")

    assert response.status_code == 400
    assert set(response.data["payments"]) == {"przelewy24_merchant_id", "przelewy24_crc_key", "przelewy24_api_key"}
    assert response.data["payments"]["przelewy24_crc_key"] == ["Wpisz z panelu Przelewy24."]


def test_with_keys_in_the_shop_the_account_changes_without_them(auth_client, shop, applied,
                                                                django_capture_on_commit_callbacks):
    stored_payments(shop, payu_enabled=True, payu_pos_id="300746", payu_client_id="300746", payu_keys_saved=True)

    response = patch(auth_client, shop, django_capture_on_commit_callbacks, {"payu_pos_id": "300747"})

    assert response.status_code == 202
    [(changes, values)] = applied
    assert changes == {"payments": {"payu_pos_id": "300747"}}
    assert "payu_md5_key" not in values["payments"]


def test_a_new_mode_needs_the_keys_again(auth_client, shop):
    stored_payments(shop, payu_enabled=True, payu_pos_id="300746", payu_client_id="300746", payu_keys_saved=True)

    response = auth_client.patch(f"/api/shops/{shop.pk}/settings/", {"payments": {"payu_sandbox": True}},
                                 format="json")

    assert response.status_code == 400
    assert response.data["payments"]["payu_md5_key"] == [
        "Klucze testowe i produkcyjne są różne. Wpisz klucz do nowego trybu.",
    ]


def test_an_operator_set_up_in_the_panel_does_not_block_other_changes(auth_client, shop,
                                                                     django_capture_on_commit_callbacks):
    # Turned on in the shop's panel, keys not filled in yet.
    stored_payments(shop, przelewy24_enabled=True)

    response = patch(auth_client, shop, django_capture_on_commit_callbacks, {"cash_on_delivery_enabled": True})

    assert response.status_code == 202


@pytest.mark.parametrize(("field", "value", "message"), [
    ("przelewy24_merchant_id", "12a456", "ID sprzedawcy składa się z samych cyfr."),
    ("przelewy24_crc_key", "0123456789abcde", "Klucz ma 16 znaków: cyfry i litery od a do f."),
    ("przelewy24_api_key", "z" * 32, "Klucz ma 32 znaki: cyfry i litery od a do f."),
    ("payu_client_secret", "12f07117", "Klucz ma 32 znaki: cyfry i litery od a do f."),
])
def test_ids_and_keys_are_checked_before_they_reach_the_shop(auth_client, shop, field, value, message):
    response = auth_client.patch(f"/api/shops/{shop.pk}/settings/", {"payments": {field: value}}, format="json")

    assert response.status_code == 400
    assert response.data["payments"][field] == [message]


def test_pasted_keys_are_tidied(auth_client, shop, applied, django_capture_on_commit_callbacks):
    patch(auth_client, shop, django_capture_on_commit_callbacks, {
        **P24, "przelewy24_merchant_id": " 123 456 ", "przelewy24_crc_key": " 0123 4567 89AB CDEF ",
    })

    [(changes, _)] = applied
    assert changes["payments"]["przelewy24_merchant_id"] == "123456"
    assert changes["payments"]["przelewy24_crc_key"] == CRC


def test_magento_has_no_online_payments_yet(new_shop, auth_client):
    magento = new_shop("magento", template="luma")

    response = auth_client.patch(f"/api/shops/{magento.pk}/settings/", {"payments": {"payu_enabled": True}},
                                 format="json")

    assert response.status_code == 400
    assert response.data["payments"]["payu_enabled"] == [
        "Płatności PayU nie są jeszcze dostępne na platformie tego sklepu.",
    ]
    assert auth_client.get(f"/api/shops/{magento.pk}/settings/").data["payment_operators"] == []
