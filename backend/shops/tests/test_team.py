import pytest
from rest_framework.test import APIClient

from accounts.models import User
from accounts.services import delete_account
from shops.models import Shop, ShopMember

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(auth_client, django_capture_on_commit_callbacks):
    payload = {"name": "Mój Sklep", "slug": "moj-sklep", "industry": "fashion", "template": "storefront"}
    with django_capture_on_commit_callbacks(execute=True):
        shop_id = auth_client.post("/api/shops/", payload, format="json").data["id"]
    return Shop.objects.get(pk=shop_id)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def helper(db):
    return User.objects.create_user(email="pomocnik@example.com", password="Sekretne-haslo-123", is_email_verified=True)


@pytest.fixture
def staff_client(shop, helper):
    ShopMember.objects.create(shop=shop, user=helper)
    return client_for(helper)


def test_each_person_sees_their_role(auth_client, staff_client, shop):
    assert [item["role"] for item in auth_client.get("/api/shops/").data] == ["owner"]
    assert [(item["id"], item["role"]) for item in staff_client.get("/api/shops/").data] == [(shop.pk, "staff")]
    assert staff_client.get(f"/api/shops/{shop.pk}/").data["role"] == "staff"


def test_a_stranger_does_not_see_the_shop(shop):
    stranger = User.objects.create_user(email="obcy@example.com", password="Sekretne-haslo-123", is_email_verified=True)

    assert client_for(stranger).get("/api/shops/").data == []
    assert client_for(stranger).get(f"/api/shops/{shop.pk}/sales/").status_code == 404


def test_the_staff_sees_the_sales(staff_client, shop):
    assert staff_client.get(f"/api/shops/{shop.pk}/sales/").status_code == 200
    assert staff_client.post(f"/api/shops/{shop.pk}/sales/refresh/").status_code == 202


@pytest.mark.parametrize("method, path", [
    ("delete", ""),
    ("post", "retry/"),
    ("post", "resume/"),
    ("get", "admin-access/"),
    ("post", "send-admin-access/"),
    ("get", "settings/"),
    ("patch", "settings/"),
    ("post", "settings/refresh/"),
    ("post", "documents/preview/"),
    ("post", "reset-admin-password/"),
    ("post", "remove-sample-products/"),
    ("get", "operations/"),
    ("get", "checklist/"),
    ("get", "backups/"),
    ("post", "backups/"),
    ("post", "backups/1/restore/"),
])
def test_everything_else_is_only_for_the_owner(staff_client, shop, method, path):
    response = getattr(staff_client, method)(f"/api/shops/{shop.pk}/{path}", {}, format="json")

    assert response.status_code == 403
    assert response.data["detail"] == "Tylko właściciel sklepu może to zrobić."
    assert Shop.objects.get(pk=shop.pk).status == Shop.Status.ACTIVE


def test_the_owners_plan_counts_only_the_shops_they_own(staff_client, shop, verified_user):
    # The helper has no plan of their own, so serving a shop gives them none to create shops with.
    payload = {"name": "Drugi", "slug": "drugi-sklep", "industry": "fashion", "template": "storefront"}

    assert staff_client.post("/api/shops/", payload, format="json").status_code == 402
    assert list(verified_user.shops.all()) == [shop]


def test_a_deleted_shop_is_gone_for_the_staff_too(auth_client, staff_client, shop):
    auth_client.delete(f"/api/shops/{shop.pk}/")

    assert staff_client.get("/api/shops/").data == []


def test_a_deleted_account_leaves_the_teams(staff_client, shop, helper):
    delete_account(helper)

    assert not ShopMember.objects.filter(user=helper).exists()
