import pytest
from django.db import connection

from accounts.models import User
from shops.categories import category_names
from shops.models import InvalidTransition, ProvisioningStep, Shop
from shops.provisioning.base import BaseProvisioner

pytestmark = pytest.mark.django_db


def shop_payload(**overrides):
    return {"name": "Mój Sklep", "slug": "moj-sklep", "industry": "fashion", "template": "storefront", **overrides}


def create_shop(client, django_capture_on_commit_callbacks, **overrides):
    with django_capture_on_commit_callbacks(execute=True):
        return client.post("/api/shops/", shop_payload(**overrides), format="json")


def test_health_needs_no_auth(api_client):
    response = api_client.get("/api/health/")

    assert response.status_code == 200
    assert response.data == {"status": "OK"}


def test_creating_shop_requires_verified_email(api_client, user):
    api_client.force_authenticate(user)

    assert api_client.post("/api/shops/", shop_payload(), format="json").status_code == 403


def test_create_shop_provisions_it_to_active(auth_client, verified_user, django_capture_on_commit_callbacks):
    response = create_shop(auth_client, django_capture_on_commit_callbacks, category_count=8)

    assert response.status_code == 201
    assert response.data["status"] == "pending"
    assert response.data["config"]["category_count"] == 8
    assert response.data["config"]["contact_email"] == verified_user.email
    assert response.data["provisioning"]["total_steps"] == len(BaseProvisioner.STEPS)

    detail = auth_client.get(f"/api/shops/{response.data['id']}/").data
    assert detail["status"] == "active"
    assert detail["url"] == "https://moj-sklep.localhost"
    assert detail["provisioning"]["status"] == "succeeded"
    assert detail["provisioning"]["completed_steps"] == len(BaseProvisioner.STEPS)


def test_credentials_are_encrypted_at_rest(auth_client, django_capture_on_commit_callbacks):
    shop_id = create_shop(auth_client, django_capture_on_commit_callbacks).data["id"]
    password = Shop.objects.get(pk=shop_id).credentials.wp_admin_password

    with connection.cursor() as cursor:
        cursor.execute("SELECT wp_admin_password FROM shops_shopcredentials WHERE shop_id = %s", [shop_id])
        raw = cursor.fetchone()[0]

    assert password
    assert raw != password


@pytest.mark.parametrize("slug", ["ab", "-sklep", "sklep-", "Duże Litery!", "a--b", "www", "x" * 31])
def test_create_shop_rejects_invalid_slugs(auth_client, slug):
    response = auth_client.post("/api/shops/", shop_payload(slug=slug), format="json")

    assert response.status_code == 400
    assert "slug" in response.data


def test_slug_is_normalized_to_lowercase(auth_client, django_capture_on_commit_callbacks):
    response = create_shop(auth_client, django_capture_on_commit_callbacks, slug="  Moj-Sklep ")

    assert response.data["slug"] == "moj-sklep"


def test_slug_must_be_unique_but_deleted_shops_free_it(auth_client, django_capture_on_commit_callbacks):
    shop_id = create_shop(auth_client, django_capture_on_commit_callbacks).data["id"]
    assert create_shop(auth_client, django_capture_on_commit_callbacks).status_code == 400

    assert auth_client.delete(f"/api/shops/{shop_id}/").status_code == 204
    assert create_shop(auth_client, django_capture_on_commit_callbacks).status_code == 201


def test_shop_limit_per_user(auth_client, django_capture_on_commit_callbacks, settings):
    settings.SHOPS_MAX_PER_USER = 2
    for i in range(2):
        assert create_shop(auth_client, django_capture_on_commit_callbacks, slug=f"sklep-{i}").status_code == 201

    response = create_shop(auth_client, django_capture_on_commit_callbacks, slug="sklep-3")

    assert response.status_code == 400
    assert "maksymalnie" in response.data["detail"]


def test_user_sees_only_own_shops(auth_client, api_client, django_capture_on_commit_callbacks):
    shop_id = create_shop(auth_client, django_capture_on_commit_callbacks).data["id"]
    other = User.objects.create_user(email="obcy@example.com", password="x", is_email_verified=True)
    api_client.force_authenticate(other)

    assert api_client.get("/api/shops/").data == []
    assert api_client.get(f"/api/shops/{shop_id}/").status_code == 404
    assert api_client.delete(f"/api/shops/{shop_id}/").status_code == 404


def test_failed_step_marks_shop_failed_and_retry_recovers(auth_client, django_capture_on_commit_callbacks, settings):
    settings.FAKE_PROVISIONER_FAIL_AT_STEP = "install_theme"
    shop_id = create_shop(auth_client, django_capture_on_commit_callbacks).data["id"]

    detail = auth_client.get(f"/api/shops/{shop_id}/").data
    steps = {step["key"]: step for step in detail["provisioning"]["steps"]}
    assert detail["status"] == "failed"
    assert detail["provisioning"]["status"] == "failed"
    assert steps["install_theme"]["status"] == "failed"
    assert "install_theme" in steps["install_theme"]["error"]
    assert steps["create_categories"]["status"] == "pending"

    settings.FAKE_PROVISIONER_FAIL_AT_STEP = ""
    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client.post(f"/api/shops/{shop_id}/retry/")

    assert response.status_code == 202
    assert auth_client.get(f"/api/shops/{shop_id}/").data["status"] == "active"


def test_unexpected_errors_are_not_shown_to_user(auth_client, django_capture_on_commit_callbacks, monkeypatch):
    def boom(self, shop):
        raise RuntimeError("password=tajne host=10.0.0.5")

    monkeypatch.setattr("shops.provisioning.fake.FakeProvisioner.step_generate_api_keys", boom)
    shop_id = create_shop(auth_client, django_capture_on_commit_callbacks).data["id"]

    error = auth_client.get(f"/api/shops/{shop_id}/").data["provisioning"]["error"]
    assert "tajne" not in error


def test_retry_only_allowed_for_failed_shops(auth_client, django_capture_on_commit_callbacks):
    shop_id = create_shop(auth_client, django_capture_on_commit_callbacks).data["id"]

    assert auth_client.post(f"/api/shops/{shop_id}/retry/").status_code == 409


def test_cannot_delete_shop_while_provisioning(auth_client, django_capture_on_commit_callbacks):
    shop_id = create_shop(auth_client, django_capture_on_commit_callbacks).data["id"]
    Shop.objects.filter(pk=shop_id).update(status=Shop.Status.PROVISIONING)

    assert auth_client.delete(f"/api/shops/{shop_id}/").status_code == 409


def test_deleted_shop_disappears_from_list(auth_client, django_capture_on_commit_callbacks):
    shop_id = create_shop(auth_client, django_capture_on_commit_callbacks).data["id"]
    auth_client.delete(f"/api/shops/{shop_id}/")

    assert auth_client.get("/api/shops/").data == []
    assert Shop.objects.get(pk=shop_id).status == Shop.Status.DELETED


def test_check_slug(auth_client, django_capture_on_commit_callbacks):
    create_shop(auth_client, django_capture_on_commit_callbacks)

    assert auth_client.get("/api/shops/check-slug/", {"slug": "wolny-adres"}).data["available"] is True
    taken = auth_client.get("/api/shops/check-slug/", {"slug": "Moj-Sklep"}).data
    assert taken["available"] is False
    assert taken["reason"]


def test_form_options(auth_client):
    data = auth_client.get("/api/shops/form-options/").data

    assert [t["slug"] for t in data["templates"]] == ["storefront", "astra", "kadence"]
    assert {"value": "PLN", "label": "Złoty (PLN)"} in data["currencies"]
    assert data["category_count"] == {"min": 1, "max": 20, "default": 5}


def test_state_machine_rejects_invalid_transition(verified_user):
    shop = Shop.objects.create(owner=verified_user, name="X", slug="xyz", status=Shop.Status.DELETED)

    with pytest.raises(InvalidTransition):
        shop.transition_to(Shop.Status.ACTIVE)


def test_steps_are_created_in_order(auth_client, django_capture_on_commit_callbacks):
    shop_id = create_shop(auth_client, django_capture_on_commit_callbacks).data["id"]
    keys = list(ProvisioningStep.objects.filter(job__shop_id=shop_id).values_list("key", flat=True))

    assert keys == [key for key, _ in BaseProvisioner.STEPS]


def test_openapi_schema_generates(api_client, user):
    api_client.force_authenticate(user)

    assert api_client.get("/api/schema/").status_code == 200


def test_shop_url_includes_non_default_port(verified_user, settings):
    settings.SHOPS_URL_SCHEME = "http"
    settings.SHOPS_HTTP_PORT = 8080
    shop = Shop(owner=verified_user, name="X", slug="ceramika")

    assert shop.url == "http://ceramika.localhost:8080"
    assert shop.admin_url == "http://ceramika.localhost:8080/wp-admin/"


def test_category_names_follow_industry_then_fill_up():
    assert category_names("handmade", 2) == ["Biżuteria", "Ceramika"]
    assert category_names("handmade", 12)[-2:] == ["Kategoria 11", "Kategoria 12"]
    assert category_names("other", 2) == ["Kategoria 1", "Kategoria 2"]


def test_admin_access_for_active_shop(auth_client, django_capture_on_commit_callbacks):
    shop_id = create_shop(auth_client, django_capture_on_commit_callbacks).data["id"]

    data = auth_client.get(f"/api/shops/{shop_id}/admin-access/").data

    assert data["admin_url"] == "https://moj-sklep.localhost/wp-admin/"
    assert data["username"] == "admin"
    assert data["password"] == Shop.objects.get(pk=shop_id).credentials.wp_admin_password


def test_admin_access_unavailable_until_shop_is_active(auth_client, django_capture_on_commit_callbacks, settings):
    settings.FAKE_PROVISIONER_FAIL_AT_STEP = "install_wordpress"
    shop_id = create_shop(auth_client, django_capture_on_commit_callbacks).data["id"]

    assert auth_client.get(f"/api/shops/{shop_id}/admin-access/").status_code == 409


def test_deleting_shop_tears_down_its_infrastructure(auth_client, django_capture_on_commit_callbacks, monkeypatch):
    torn_down = []
    monkeypatch.setattr("shops.provisioning.fake.FakeProvisioner.teardown", lambda self, shop: torn_down.append(shop.pk))
    shop_id = create_shop(auth_client, django_capture_on_commit_callbacks).data["id"]

    with django_capture_on_commit_callbacks(execute=True):
        auth_client.delete(f"/api/shops/{shop_id}/")

    assert torn_down == [shop_id]
