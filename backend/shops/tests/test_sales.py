from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from accounts.models import User
from shops import sales
from shops.models import SalesSync, Shop, ShopOrder
from shops.orders import Order
from shops.provisioning.fake import FakeProvisioner

pytestmark = pytest.mark.django_db

READ_ORDERS = "shops.provisioning.fake.FakeProvisioner.read_orders"


@pytest.fixture
def shop(auth_client, django_capture_on_commit_callbacks):
    payload = {"name": "Mój Sklep", "slug": "moj-sklep", "industry": "fashion", "template": "storefront"}
    with django_capture_on_commit_callbacks(execute=True):
        shop_id = auth_client.post("/api/shops/", payload, format="json").data["id"]
    shop = Shop.objects.get(pk=shop_id)
    assert shop.status == Shop.Status.ACTIVE
    return shop


def placed(days_ago, hour=0, minute=5):
    """A moment `days_ago` days before today, local time."""
    return timezone.make_aware(datetime.combine(timezone.localdate() - timedelta(days=days_ago), time(hour, minute)))


def order(number, days_ago, status="completed", total="100.00", currency="PLN", changed=None):
    at = placed(days_ago)
    return Order(external_id=str(number), number=str(number), status=status, total=Decimal(total),
                 currency=currency, items=1, customer="Anna N.", placed_at=at, changed_at=changed or at)


class Orders:
    """Stands in for read_orders: hands over the orders a test sets and records what was asked."""

    def __init__(self, orders=()):
        self.orders = list(orders)
        self.calls = []

    def __call__(self, shop, since, limit):
        self.calls.append((since, limit))
        return [o for o in sorted(self.orders, key=lambda o: o.changed_at) if o.changed_at >= since][:limit]


@pytest.fixture
def orders(monkeypatch):
    fake = Orders()
    monkeypatch.setattr(READ_ORDERS, lambda provisioner, shop, since, limit: fake(shop, since, limit))
    return fake


def get_sales(client, shop, captured):
    with captured(execute=True):
        return client.get(f"/api/shops/{shop.pk}/sales/")


# --- reading the shop ---


def test_opening_the_overview_reads_the_shop_and_counts_sales(auth_client, shop, orders,
                                                               django_capture_on_commit_callbacks):
    orders.orders = [
        order(1, 0, total="50.00", status="new"),
        order(2, 0, total="70.00", status="processing"),
        order(3, 3, total="30.00"),
        order(4, 20, total="200.00"),
        order(5, 45, total="80.00"),
        order(6, 1, total="999.00", status="cancelled"),
        order(7, 1, total="999.00", status="unfinished"),
        order(8, 2, total="999.00", currency="EUR"),
    ]

    first = get_sales(auth_client, shop, django_capture_on_commit_callbacks)

    assert first.status_code == 200
    assert (first.data["available"], first.data["refreshing"], first.data["synced_at"]) == (True, True, None)
    assert first.data["last_30_days"]["orders"] == 0

    data = auth_client.get(f"/api/shops/{shop.pk}/sales/").data
    assert data["refreshing"] is False and data["synced_at"] is not None and data["error"] == ""
    assert data["currency"] == "PLN"
    assert data["today"] == {"orders": 2, "revenue": "120.00", "average": "60.00"}
    assert data["last_7_days"] == {"orders": 3, "revenue": "150.00", "average": "50.00"}
    assert data["last_30_days"] == {"orders": 4, "revenue": "350.00", "average": "87.50"}
    assert data["previous_30_days"] == {"orders": 1, "revenue": "80.00", "average": "80.00"}
    assert len(data["daily"]) == 30
    assert data["daily"][-1] == {"date": timezone.localdate().isoformat(), "orders": 2, "revenue": "120.00"}
    assert data["daily"][0]["date"] == (timezone.localdate() - timedelta(days=29)).isoformat()
    assert data["to_handle"] == {"new": 1, "processing": 1}
    assert [o["number"] for o in data["recent"]] == ["2", "1", "6", "8", "3", "4", "5"]
    assert data["recent"][0] == {
        "number": "2", "status": "processing", "status_display": "W realizacji", "total": "70.00", "currency": "PLN",
        "items": 1, "customer": "Anna N.", "placed_at": data["recent"][0]["placed_at"],
    }


def test_the_average_order_is_rounded_like_money(shop, orders):
    orders.orders = [order(1, 0, total="0.01"), order(2, 0, total="0.02")]
    sales.sync(shop.pk)

    assert sales.overview(shop)["today"]["average"] == Decimal("0.02")


def test_later_reads_continue_from_the_last_change(shop, orders):
    orders.orders = [order(1, 5, status="new"), order(2, 2)]
    assert sales.sync(shop.pk) is True

    (since, limit), = orders.calls
    assert since == pytest.approx(timezone.now() - sales.KEPT_FOR, abs=timedelta(seconds=5))
    assert limit == sales.BATCH
    cursor = SalesSync.objects.get(shop=shop).cursor
    assert cursor == placed(2)

    orders.orders = [order(1, 5, status="completed", changed=placed(0)), order(3, 0)]
    sales.sync(shop.pk)

    assert orders.calls[-1][0] == cursor - sales.OVERLAP
    assert dict(ShopOrder.objects.values_list("number", "status")) == {"1": "completed", "2": "completed",
                                                                        "3": "completed"}


def test_big_shops_are_read_in_batches(shop, orders, monkeypatch):
    monkeypatch.setattr(sales, "BATCH", 2)
    orders.orders = [order(number, 10 - number) for number in range(1, 6)]

    sales.sync(shop.pk)

    # Each batch starts at the last change of the one before, so it reads that order again.
    assert len(orders.calls) == 5
    assert ShopOrder.objects.filter(shop=shop).count() == 5


def test_only_recent_orders_are_kept(shop, orders):
    ShopOrder.objects.create(shop=shop, external_id="old", number="old", status="completed", total=1, currency="PLN",
                             placed_at=placed(120), changed_at=placed(120))
    orders.orders = [order(1, 100, changed=placed(1)), order(2, 1)]

    sales.sync(shop.pk)

    assert list(ShopOrder.objects.filter(shop=shop).values_list("number", flat=True)) == ["2"]


def test_a_failed_read_keeps_the_last_copy_and_says_so(auth_client, shop, orders, monkeypatch, caplog,
                                                       django_capture_on_commit_callbacks):
    orders.orders = [order(1, 0)]
    sales.sync(shop.pk)
    SalesSync.objects.filter(shop=shop).update(attempted_at=timezone.now() - timedelta(minutes=10))
    attempts = []

    def broken(provisioner, shop, since, limit):
        attempts.append(since)
        raise RuntimeError("docker exec failed")

    monkeypatch.setattr(READ_ORDERS, broken)
    get_sales(auth_client, shop, django_capture_on_commit_callbacks)
    # Opened again at once: the shop that just failed is not asked again.
    data = get_sales(auth_client, shop, django_capture_on_commit_callbacks).data

    assert len(attempts) == 1
    assert (data["refreshing"], data["error"]) == (False, sales.SYNC_FAILED)
    assert data["today"]["orders"] == 1
    assert "Reading the orders of shop" in caplog.text


# --- when the shop is read ---


def test_a_fresh_copy_is_not_read_again(auth_client, shop, orders, django_capture_on_commit_callbacks):
    sales.sync(shop.pk)
    calls = len(orders.calls)

    get_sales(auth_client, shop, django_capture_on_commit_callbacks)
    with django_capture_on_commit_callbacks(execute=True):
        refreshed = auth_client.post(f"/api/shops/{shop.pk}/sales/refresh/")

    assert refreshed.status_code == 202
    assert len(orders.calls) == calls


def test_the_refresh_button_reads_again_after_half_a_minute(auth_client, shop, orders,
                                                            django_capture_on_commit_callbacks):
    sales.sync(shop.pk)
    SalesSync.objects.filter(shop=shop).update(attempted_at=timezone.now() - timedelta(seconds=40))

    with django_capture_on_commit_callbacks(execute=True):
        auth_client.post(f"/api/shops/{shop.pk}/sales/refresh/")

    assert len(orders.calls) == 2


def test_a_queued_read_is_not_queued_again(shop, orders, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks() as callbacks:
        sales.request_refresh(shop)
        sales.request_refresh(shop)
        sales.request_refresh(shop, force=True)

    assert len(callbacks) == 1
    state = SalesSync.objects.get(shop=shop)
    assert sales.is_refreshing(state)
    assert not sales.is_refreshing(state, now=timezone.now() + sales.REFRESH_TIMEOUT + timedelta(seconds=1))


def test_a_shop_that_is_not_running_is_not_read(auth_client, shop, orders, django_capture_on_commit_callbacks):
    Shop.objects.filter(pk=shop.pk).update(status=Shop.Status.SUSPENDED)

    data = get_sales(auth_client, shop, django_capture_on_commit_callbacks).data

    assert (data["available"], data["refreshing"]) == (False, False)
    assert sales.sync(shop.pk) is False
    assert not orders.calls


def test_the_scheduled_round_reads_shops_with_an_old_copy(shop, orders, django_capture_on_commit_callbacks):
    other_owner = User.objects.create_user(email="inny@example.com", password="Sekretne-haslo-123")
    stopped = Shop.objects.create(owner=other_owner, name="Stary", slug="stary", status=Shop.Status.SUSPENDED)

    sales.sync_all()
    assert len(orders.calls) == 1
    sales.sync_all()
    assert len(orders.calls) == 1

    SalesSync.objects.filter(shop=shop).update(attempted_at=timezone.now() - timedelta(minutes=8))
    sales.sync_all()
    assert len(orders.calls) == 2
    assert not SalesSync.objects.filter(shop=stopped).exists()


# --- who sees it, and what happens to it ---


def test_only_the_owner_sees_the_sales(api_client, shop):
    stranger = User.objects.create_user(email="obcy@example.com", password="Sekretne-haslo-123",
                                        is_email_verified=True)
    api_client.force_authenticate(stranger)

    assert api_client.get(f"/api/shops/{shop.pk}/sales/").status_code == 404
    assert api_client.post(f"/api/shops/{shop.pk}/sales/refresh/").status_code == 404


def test_deleting_the_shop_deletes_the_copy_of_its_orders(auth_client, shop, orders,
                                                         django_capture_on_commit_callbacks):
    orders.orders = [order(1, 0)]
    sales.sync(shop.pk)

    with django_capture_on_commit_callbacks(execute=True):
        assert auth_client.delete(f"/api/shops/{shop.pk}/").status_code == 204

    assert not ShopOrder.objects.filter(shop=shop).exists()
    assert not SalesSync.objects.filter(shop=shop).exists()


def test_the_simulated_shop_has_the_same_orders_every_time(shop):
    since = timezone.now() - timedelta(days=90)

    first = FakeProvisioner().read_orders(shop, since, 500)
    second = FakeProvisioner().read_orders(shop, since, 500)

    assert first == second and len(first) > 20
    assert all(o.changed_at >= since for o in first)
    assert FakeProvisioner().read_orders(shop, timezone.now() + timedelta(days=1), 500) == []
