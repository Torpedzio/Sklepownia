from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from push.models import PushDevice
from shops import checklist
from shops.models import Shop, ShopChecklist, ShopOrder, ShopSettings
from shops.provisioning.base import ProductCount, ProvisioningError

pytestmark = pytest.mark.django_db

COUNT_PRODUCTS = "shops.provisioning.fake.FakeProvisioner.count_products"
ALL_STEPS = ["payments", "shipping", "documents", "products", "sample_products", "notifications", "test_order"]


@pytest.fixture(autouse=True)
def no_orders(monkeypatch):
    """The fake shop makes up orders; these tests place them themselves."""
    monkeypatch.setattr("shops.provisioning.fake.FakeProvisioner.read_orders", lambda self, shop, since, limit: [])


@pytest.fixture
def new_shop(auth_client, django_capture_on_commit_callbacks):
    def create(platform="woocommerce", template="storefront", **fields):
        payload = {"name": "Mój Sklep", "slug": f"sklep-{platform}", "industry": "fashion", "template": template,
                   "platform": platform, **fields}
        with django_capture_on_commit_callbacks(execute=True):
            response = auth_client.post("/api/shops/", payload, format="json")
        assert response.status_code == 201, response.data
        shop = Shop.objects.get(pk=response.data["id"])
        assert shop.status == Shop.Status.ACTIVE
        return shop

    return create


@pytest.fixture
def shop(new_shop):
    return new_shop()


class Counts:
    """Stands in for count_products: answers with what a test sets and records the calls."""

    def __init__(self):
        self.answer = ProductCount(products=0, samples=6)
        self.calls = 0

    def __call__(self, shop):
        self.calls += 1
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture
def counts(monkeypatch):
    fake = Counts()
    monkeypatch.setattr(COUNT_PRODUCTS, lambda provisioner, shop: fake(shop))
    return fake


def get_checklist(client, shop, captured):
    with captured(execute=True):
        response = client.get(f"/api/shops/{shop.pk}/checklist/")
    assert response.status_code == 200
    return response.data


def steps(data):
    return {step["key"]: step["done"] for step in data["steps"]}


def set_settings(shop, section, **values):
    stored = ShopSettings.objects.get(shop=shop)
    stored.values[section].update(values)
    stored.save()


def counted_long_ago(shop, ago):
    then = timezone.now() - ago
    ShopChecklist.objects.filter(shop=shop).update(requested_at=then - timedelta(seconds=1), attempted_at=then)


def an_order(shop, number="1001", status=ShopOrder.Status.NEW):
    now = timezone.now()
    return ShopOrder.objects.create(shop=shop, external_id=number, number=number, status=status,
                                    total=Decimal("49.99"), currency="PLN", placed_at=now, changed_at=now)


def test_a_new_shop_starts_with_every_step_open_and_its_products_counted(auth_client, shop, counts,
                                                                         django_capture_on_commit_callbacks):
    data = get_checklist(auth_client, shop, django_capture_on_commit_callbacks)

    assert data["available"] and not data["hidden"]
    assert [step["key"] for step in data["steps"]] == ALL_STEPS
    assert not any(step["done"] for step in data["steps"])
    assert counts.calls == 1
    stored = ShopChecklist.objects.get(shop=shop)
    assert (stored.products, stored.sample_products) == (0, 6)
    assert stored.counted_at is not None

    # The count is there on the next look.
    data = get_checklist(auth_client, shop, django_capture_on_commit_callbacks)
    assert (data["products"], data["sample_products"]) == (0, 6)
    assert data["counted_at"] is not None


def test_a_count_on_its_way_is_reported_and_not_queued_twice(auth_client, shop, counts):
    first = auth_client.get(f"/api/shops/{shop.pk}/checklist/").data
    second = auth_client.get(f"/api/shops/{shop.pk}/checklist/").data

    assert first["refreshing"] and second["refreshing"]
    # Queued on commit, which the test never reaches: nothing was counted yet.
    assert counts.calls == 0
    assert ShopChecklist.objects.get(shop=shop).requested_at is not None


def test_steps_tick_off_from_the_settings(auth_client, shop, counts, django_capture_on_commit_callbacks):
    get_checklist(auth_client, shop, django_capture_on_commit_callbacks)
    set_settings(shop, "payments", cash_on_delivery_enabled=True)
    set_settings(shop, "shipping", local_pickup_enabled=True)

    data = get_checklist(auth_client, shop, django_capture_on_commit_callbacks)

    assert steps(data)["payments"] and steps(data)["shipping"]
    assert not steps(data)["products"]


def test_an_online_payment_operator_ticks_off_the_payments(auth_client, shop, counts,
                                                           django_capture_on_commit_callbacks):
    get_checklist(auth_client, shop, django_capture_on_commit_callbacks)
    set_settings(shop, "payments", payu_enabled=True)

    assert steps(get_checklist(auth_client, shop, django_capture_on_commit_callbacks))["payments"]


def test_own_products_and_removed_samples_stop_the_counting(auth_client, shop, counts,
                                                            django_capture_on_commit_callbacks):
    counts.answer = ProductCount(products=3, samples=0)
    get_checklist(auth_client, shop, django_capture_on_commit_callbacks)

    data = get_checklist(auth_client, shop, django_capture_on_commit_callbacks)
    assert steps(data)["products"] and steps(data)["sample_products"]
    assert data["refreshing"] is False

    # Both product steps are done, so the shop isn't counted again, however long it's been.
    counted_long_ago(shop, timedelta(hours=1))
    assert get_checklist(auth_client, shop, django_capture_on_commit_callbacks)["refreshing"] is False
    assert counts.calls == 1


def test_an_open_product_step_is_counted_again_after_a_while(auth_client, shop, counts,
                                                             django_capture_on_commit_callbacks):
    get_checklist(auth_client, shop, django_capture_on_commit_callbacks)
    get_checklist(auth_client, shop, django_capture_on_commit_callbacks)
    assert counts.calls == 1

    counts.answer = ProductCount(products=1, samples=6)
    counted_long_ago(shop, checklist.STALE_AFTER)
    get_checklist(auth_client, shop, django_capture_on_commit_callbacks)
    data = get_checklist(auth_client, shop, django_capture_on_commit_callbacks)

    assert counts.calls == 2
    assert steps(data)["products"] and not steps(data)["sample_products"]


def test_a_failed_count_leaves_the_steps_open_and_waits_before_trying_again(auth_client, shop, counts,
                                                                           django_capture_on_commit_callbacks):
    counts.answer = ProvisioningError("Sklep nie odpowiada")

    data = get_checklist(auth_client, shop, django_capture_on_commit_callbacks)
    data = get_checklist(auth_client, shop, django_capture_on_commit_callbacks)

    assert counts.calls == 1
    assert data["refreshing"] is False
    assert data["products"] is None
    assert not steps(data)["products"]


def test_removing_the_samples_ticks_off_their_step(auth_client, shop, counts, django_capture_on_commit_callbacks):
    get_checklist(auth_client, shop, django_capture_on_commit_callbacks)

    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client.post(f"/api/shops/{shop.pk}/remove-sample-products/")
    assert response.status_code == 202

    data = get_checklist(auth_client, shop, django_capture_on_commit_callbacks)
    assert data["sample_products"] == 0
    assert steps(data)["sample_products"]


def test_a_change_on_its_way_to_the_shop_keeps_the_list_refreshing(auth_client, shop, counts,
                                                                   django_capture_on_commit_callbacks):
    get_checklist(auth_client, shop, django_capture_on_commit_callbacks)
    # Queued, not run: the commit never comes.
    response = auth_client.patch(f"/api/shops/{shop.pk}/settings/", {"payments": {"cash_on_delivery_enabled": True}},
                                 format="json")
    assert response.status_code == 202

    assert auth_client.get(f"/api/shops/{shop.pk}/checklist/").data["refreshing"] is True


def test_a_phone_with_notifications_ticks_off_its_step(auth_client, shop, verified_user, counts,
                                                       django_capture_on_commit_callbacks):
    PushDevice.objects.create(user=verified_user, token="ExponentPushToken[abc]", platform="android")

    data = get_checklist(auth_client, shop, django_capture_on_commit_callbacks)

    assert steps(data)["notifications"]


def test_the_first_order_ticks_off_the_test_order(auth_client, shop, counts, django_capture_on_commit_callbacks):
    an_order(shop, status=ShopOrder.Status.CANCELLED)

    data = get_checklist(auth_client, shop, django_capture_on_commit_callbacks)

    assert steps(data)["test_order"]


def test_without_orders_the_list_reads_them_like_the_sales_overview(auth_client, shop, counts, monkeypatch,
                                                                     django_capture_on_commit_callbacks):
    from shops.orders import Order

    now = timezone.now()
    placed = Order(external_id="7", number="7", status="new", total=Decimal("20.00"), currency="PLN", items=1,
                   customer="Anna N.", placed_at=now, changed_at=now)
    monkeypatch.setattr("shops.provisioning.fake.FakeProvisioner.read_orders",
                        lambda self, shop, since, limit: [placed])

    get_checklist(auth_client, shop, django_capture_on_commit_callbacks)
    data = get_checklist(auth_client, shop, django_capture_on_commit_callbacks)

    assert steps(data)["test_order"]


def test_only_the_steps_the_platform_and_the_shop_have(new_shop, auth_client, counts,
                                                       django_capture_on_commit_callbacks):
    prestashop = new_shop("prestashop", template="classic", include_sample_products=False)

    data = get_checklist(auth_client, prestashop, django_capture_on_commit_callbacks)

    # PrestaShop's shipping is set in its panel, and this shop got no samples.
    assert [step["key"] for step in data["steps"]] == ["payments", "documents", "products", "notifications", "test_order"]


def test_hiding_the_list_stops_the_counting_until_it_is_shown_again(auth_client, shop, counts,
                                                                    django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client.patch(f"/api/shops/{shop.pk}/checklist/", {"hidden": True}, format="json")
    assert response.status_code == 200
    assert response.data["hidden"] and not response.data["available"]
    assert response.data["steps"] == []
    assert get_checklist(auth_client, shop, django_capture_on_commit_callbacks)["available"] is False
    assert counts.calls == 0

    response = auth_client.patch(f"/api/shops/{shop.pk}/checklist/", {"hidden": False}, format="json")
    assert response.data["available"] and not response.data["hidden"]


def test_a_shop_that_is_not_running_has_no_list(auth_client, shop, counts, django_capture_on_commit_callbacks):
    Shop.objects.filter(pk=shop.pk).update(status=Shop.Status.SUSPENDED)

    data = get_checklist(auth_client, shop, django_capture_on_commit_callbacks)

    assert data["available"] is False and data["steps"] == []
    assert counts.calls == 0


def test_the_list_belongs_to_the_shop_s_owner(api_client, shop, verified_user):
    from accounts.models import User
    from conftest import subscribe

    stranger = User.objects.create_user(email="obcy@example.com", password="Sekretne-haslo-123", is_email_verified=True)
    subscribe(stranger, shop.owner.subscription.plan)
    api_client.force_authenticate(stranger)

    assert api_client.get(f"/api/shops/{shop.pk}/checklist/").status_code == 404
    assert api_client.patch(f"/api/shops/{shop.pk}/checklist/", {"hidden": True}, format="json").status_code == 404
    assert not ShopChecklist.objects.filter(shop=shop, hidden_at__isnull=False).exists()
