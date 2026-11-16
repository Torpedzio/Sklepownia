import pytest
from django.utils import timezone

from accounts.models import User
from shops.models import Shop, ShopOperation, ShopTemplate
from shops.platforms.woocommerce import _money

pytestmark = pytest.mark.django_db

SAVE_SETTINGS = "shops.provisioning.fake.FakeProvisioner.apply_settings"


@pytest.fixture
def shop(auth_client, django_capture_on_commit_callbacks):
    payload = {"name": "Mój Sklep", "slug": "moj-sklep", "industry": "fashion", "template": "storefront"}
    with django_capture_on_commit_callbacks(execute=True):
        shop_id = auth_client.post("/api/shops/", payload, format="json").data["id"]
    return Shop.objects.get(pk=shop_id)


def settings_url(shop, suffix=""):
    return f"/api/shops/{shop.pk}/settings/{suffix}"


def patch(client, shop, captured, data):
    with captured(execute=True):
        return client.patch(settings_url(shop), data, format="json")


def test_settings_start_from_what_the_creation_form_chose(auth_client, shop):
    response = auth_client.get(settings_url(shop))

    assert response.status_code == 200
    values = response.data["values"]
    assert values["general"]["name"] == "Mój Sklep"
    assert values["region"] == {
        "language": "pl_PL", "currency": "PLN", "country": "PL", "timezone": "Europe/Warsaw",
    }
    assert values["appearance"] == {"theme": "storefront"}
    assert values["taxes"]["standard_rate"] == "23.00"
    assert response.data["busy"] is False
    assert response.data["synced_at"] is None
    assert response.data["options"]["vat_rates"]["PL"][0] == "23.00"
    assert {"value": "storefront", "label": "Storefront"} in response.data["options"]["themes"]


def test_change_is_applied_to_the_shop_and_recorded(auth_client, shop, django_capture_on_commit_callbacks):
    response = patch(auth_client, shop, django_capture_on_commit_callbacks, {
        "general": {"name": "Nowa Nazwa"},
        "shipping": {"courier_enabled": True, "courier_cost": "12.5"},
        "region": {"currency": "EUR"},
    })

    assert response.status_code == 202
    operation = ShopOperation.objects.get(shop=shop)
    assert operation.kind == ShopOperation.Kind.UPDATE_SETTINGS
    assert operation.status == ShopOperation.Status.SUCCEEDED
    assert operation.changes == {
        "general": {"name": "Nowa Nazwa"},
        "shipping": {"courier_enabled": True, "courier_cost": "12.50"},
        "region": {"currency": "EUR"},
    }

    after = auth_client.get(settings_url(shop)).data
    assert after["values"]["general"]["name"] == "Nowa Nazwa"
    assert after["values"]["shipping"]["courier_cost"] == "12.50"
    assert after["synced_at"] is not None
    assert after["operation"]["changed_fields"] == ["Nazwa sklepu", "Kurier", "Cena wysyłki kurierem", "Waluta"]
    shop.refresh_from_db()
    assert shop.name == "Nowa Nazwa"
    assert shop.config.currency == "EUR"


def test_unchanged_values_start_nothing(auth_client, shop, django_capture_on_commit_callbacks):
    response = patch(auth_client, shop, django_capture_on_commit_callbacks, {"general": {"name": "Mój Sklep"}})

    assert response.status_code == 200
    assert not ShopOperation.objects.filter(shop=shop).exists()


def test_new_country_brings_its_time_zone_and_vat_rate(auth_client, shop, django_capture_on_commit_callbacks):
    patch(auth_client, shop, django_capture_on_commit_callbacks, {"region": {"country": "DE"}})

    operation = ShopOperation.objects.get(shop=shop)
    assert operation.changes == {
        "region": {"country": "DE", "timezone": "Europe/Berlin"},
        "taxes": {"standard_rate": "19.00"},
    }


def test_time_zone_and_vat_rate_chosen_with_the_country_are_kept(
    auth_client, shop, django_capture_on_commit_callbacks,
):
    patch(auth_client, shop, django_capture_on_commit_callbacks, {
        "region": {"country": "DE", "timezone": "UTC"}, "taxes": {"standard_rate": "7"},
    })

    operation = ShopOperation.objects.get(shop=shop)
    assert operation.changes == {"region": {"country": "DE", "timezone": "UTC"}, "taxes": {"standard_rate": "7.00"}}


def test_new_theme_is_written_to_the_shop_config(auth_client, shop, django_capture_on_commit_callbacks):
    ShopTemplate.objects.get_or_create(slug="astra", defaults={"name": "Astra", "theme": "astra"})

    patch(auth_client, shop, django_capture_on_commit_callbacks, {"appearance": {"theme": "astra"}})

    shop.config.refresh_from_db()
    assert shop.config.template.slug == "astra"


@pytest.mark.parametrize(("data", "section", "field"), [
    ({"general": {"contact_email": "to-nie-email"}}, "general", "contact_email"),
    ({"general": {"name": "x"}}, "general", "name"),
    ({"payments": {"bank_transfer_enabled": True}}, "payments", "bank_account_number"),
    ({"payments": {"bank_account_number": "61 1090 1014 0000 0712 1981 2875"}}, "payments", "bank_account_number"),
    ({"shopping": {"guest_checkout": False}}, "shopping", "guest_checkout"),
    ({"taxes": {"standard_rate": "60"}}, "taxes", "standard_rate"),
    ({"shipping": {"courier_cost": "-1"}}, "shipping", "courier_cost"),
    ({"region": {"currency": "JPY"}}, "region", "currency"),
    ({"appearance": {"theme": "nie-ma-takiego"}}, "appearance", "theme"),
])
def test_invalid_settings_are_rejected(auth_client, shop, data, section, field):
    response = auth_client.patch(settings_url(shop), data, format="json")

    assert response.status_code == 400
    assert field in response.data[section]
    assert not ShopOperation.objects.filter(shop=shop).exists()


def test_bank_account_number_is_checked_and_grouped(auth_client, shop, django_capture_on_commit_callbacks):
    response = patch(auth_client, shop, django_capture_on_commit_callbacks, {"payments": {
        "bank_transfer_enabled": True,
        "bank_account_name": "Mój Sklep sp. z o.o.",
        "bank_account_number": "61109010140000071219812874",
    }})

    assert response.status_code == 202
    values = auth_client.get(settings_url(shop)).data["values"]
    assert values["payments"]["bank_account_number"] == "61 1090 1014 0000 0712 1981 2874"


def test_one_operation_at_a_time(auth_client, shop, verified_user):
    ShopOperation.objects.create(shop=shop, kind=ShopOperation.Kind.SYNC_SETTINGS, requested_by=verified_user)

    response = auth_client.patch(settings_url(shop), {"general": {"name": "Inna"}}, format="json")

    assert response.status_code == 409
    assert auth_client.get(settings_url(shop)).data["busy"] is True


def test_stuck_operation_stops_blocking(auth_client, shop, verified_user, django_capture_on_commit_callbacks):
    stuck = ShopOperation.objects.create(shop=shop, kind=ShopOperation.Kind.SYNC_SETTINGS)
    ShopOperation.objects.filter(pk=stuck.pk).update(created_at=timezone.now() - timezone.timedelta(hours=1))

    response = patch(auth_client, shop, django_capture_on_commit_callbacks, {"general": {"name": "Inna"}})

    assert response.status_code == 202


def test_settings_need_a_running_shop(auth_client, shop):
    Shop.objects.filter(pk=shop.pk).update(status=Shop.Status.FAILED)

    response = auth_client.patch(settings_url(shop), {"general": {"name": "Inna"}}, format="json")

    assert response.status_code == 409


def test_failed_change_shows_a_message_and_keeps_old_values(
    auth_client, shop, settings, django_capture_on_commit_callbacks,
):
    settings.FAKE_PROVISIONER_FAIL_AT_STEP = "apply_settings"

    patch(auth_client, shop, django_capture_on_commit_callbacks, {"general": {"name": "Inna"}})

    operation = ShopOperation.objects.get(shop=shop)
    assert operation.status == ShopOperation.Status.FAILED
    assert operation.error == "Symulowany błąd: apply_settings"
    assert auth_client.get(settings_url(shop)).data["values"]["general"]["name"] == "Mój Sklep"
    shop.refresh_from_db()
    assert shop.name == "Mój Sklep"


def test_unexpected_error_hides_details(auth_client, shop, monkeypatch, django_capture_on_commit_callbacks):
    def explode(*args):
        raise RuntimeError("docker exec failed: password=tajne")

    monkeypatch.setattr(SAVE_SETTINGS, explode)

    patch(auth_client, shop, django_capture_on_commit_callbacks, {"general": {"name": "Inna"}})

    error = ShopOperation.objects.get(shop=shop).error
    assert "tajne" not in error
    assert error.startswith("Nie udało się")


def test_refresh_reads_the_shop(auth_client, shop, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client.post(settings_url(shop, "refresh/"))

    assert response.status_code == 202
    assert ShopOperation.objects.get(shop=shop).kind == ShopOperation.Kind.SYNC_SETTINGS
    assert auth_client.get(settings_url(shop)).data["synced_at"] is not None


def test_reset_admin_password_gives_a_new_one(auth_client, shop, django_capture_on_commit_callbacks):
    before = shop.credentials.admin_password

    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client.post(f"/api/shops/{shop.pk}/reset-admin-password/")

    assert response.status_code == 202
    assert response.data["kind"] == "reset_admin_password"
    assert Shop.objects.get(pk=shop.pk).credentials.admin_password != before


def test_remove_sample_products_reports_how_many(auth_client, shop, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        operation_id = auth_client.post(f"/api/shops/{shop.pk}/remove-sample-products/").data["id"]

    response = auth_client.get(f"/api/shops/{shop.pk}/operations/{operation_id}/")

    assert response.status_code == 200
    assert response.data["status"] == "succeeded"
    assert response.data["result"] == {"removed": 6}


def test_operation_history_is_newest_first(auth_client, shop, django_capture_on_commit_callbacks):
    for name in ("Pierwsza", "Druga"):
        patch(auth_client, shop, django_capture_on_commit_callbacks, {"general": {"name": name}})

    history = auth_client.get(f"/api/shops/{shop.pk}/operations/").data

    assert [item["changes"]["general"]["name"] for item in history] == ["Druga", "Pierwsza"]


def test_other_owners_shop_settings_are_hidden(api_client, shop):
    stranger = User.objects.create_user(email="obcy@example.com", password="Sekretne-haslo-123", is_email_verified=True)
    api_client.force_authenticate(stranger)

    assert api_client.get(settings_url(shop)).status_code == 404
    assert api_client.post(f"/api/shops/{shop.pk}/reset-admin-password/").status_code == 404


@pytest.mark.parametrize(("raw", "expected"), [("15", "15.00"), ("12,5", "12.50"), ("23.0000", "23.00"),
                                               ("", "0.00"), (None, "0.00"), ("10 * [qty]", "0.00")])
def test_prices_read_from_woocommerce(raw, expected):
    assert _money(raw) == expected


@pytest.mark.parametrize(("number", "stored"), [
    ("DE89 3704 0044 0532 0130 00", "DE89 3704 0044 0532 0130 00"),
    ("GB82-WEST-1234-5698-7654-32", "GB82 WEST 1234 5698 7654 32"),
    ("  ", ""),
])
def test_bank_account_numbers_from_other_countries(auth_client, shop, django_capture_on_commit_callbacks, number, stored):
    patch(auth_client, shop, django_capture_on_commit_callbacks, {"payments": {"bank_account_number": number}})

    assert auth_client.get(settings_url(shop)).data["values"]["payments"]["bank_account_number"] == stored


def test_bank_account_number_with_odd_characters_is_rejected(auth_client, shop):
    response = auth_client.patch(settings_url(shop), {"payments": {"bank_account_number": "12/34/56/78"}}, format="json")

    assert response.data["payments"]["bank_account_number"] == ["Numer konta może zawierać tylko litery i cyfry."]


def test_description_and_contact_email_are_written_to_the_shop_config(
    auth_client, shop, django_capture_on_commit_callbacks,
):
    patch(auth_client, shop, django_capture_on_commit_callbacks, {
        "general": {"description": "Nowy opis", "contact_email": "nowy@example.com"},
    })

    shop.config.refresh_from_db()
    assert shop.config.description == "Nowy opis"
    assert shop.config.contact_email == "nowy@example.com"


def test_failed_read_after_a_change_does_not_fail_the_change(
    auth_client, shop, monkeypatch, django_capture_on_commit_callbacks,
):
    def unreachable(self, shop):
        raise RuntimeError("sklep nie odpowiada")

    monkeypatch.setattr("shops.provisioning.fake.FakeProvisioner.read_settings", unreachable)

    patch(auth_client, shop, django_capture_on_commit_callbacks, {"general": {"name": "Inna"}})

    operation = ShopOperation.objects.get(shop=shop)
    assert operation.status == ShopOperation.Status.SUCCEEDED
    assert auth_client.get(settings_url(shop)).data["values"]["general"]["name"] == "Inna"


def test_an_operation_runs_only_once(shop, verified_user):
    from shops.provisioning.operations import run_operation

    operation = ShopOperation.objects.create(
        shop=shop, kind=ShopOperation.Kind.SYNC_SETTINGS, status=ShopOperation.Status.SUCCEEDED,
    )

    run_operation(operation.pk)

    operation.refresh_from_db()
    assert operation.started_at is None
    assert str(operation) == f"Odczyt ustawień ze sklepu – {shop}"


def test_refresh_and_actions_wait_for_a_running_operation(auth_client, shop, verified_user):
    ShopOperation.objects.create(shop=shop, kind=ShopOperation.Kind.SYNC_SETTINGS)

    assert auth_client.post(settings_url(shop, "refresh/")).status_code == 409
    assert auth_client.post(f"/api/shops/{shop.pk}/remove-sample-products/").status_code == 409


def test_unknown_operation_is_not_found(auth_client, shop):
    assert auth_client.get(f"/api/shops/{shop.pk}/operations/999999/").status_code == 404
