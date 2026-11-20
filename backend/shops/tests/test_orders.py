from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from shops import orders
from shops.models import Shop, ShopConfig, ShopEvent, ShopMember, ShopOrder, ShopOrderNote, ShopTemplate
from shops.orders import Address
from shops.platforms.magento import MagentoProvisioner
from shops.platforms.prestashop import PrestaShopProvisioner
from shops.platforms.woocommerce import WooCommerceProvisioner
from shops.remote import NotInShop, ShopApiError, ShopUnavailable
from shops.remote.fake import FakeApi

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(auth_client, django_capture_on_commit_callbacks):
    payload = {"name": "Mój Sklep", "slug": "moj-sklep", "industry": "fashion", "template": "storefront"}
    with django_capture_on_commit_callbacks(execute=True):
        shop_id = auth_client.post("/api/shops/", payload, format="json").data["id"]
    shop = Shop.objects.get(pk=shop_id)
    assert shop.status == Shop.Status.ACTIVE
    return shop


def add_order(shop, number, *, status="new", customer="Anna N.", days_ago=0, total="120.00", items=2):
    at = timezone.now() - timedelta(days=days_ago)
    return ShopOrder.objects.create(
        shop=shop, external_id=str(number), number=f"#{number}", status=status, total=Decimal(total), currency="PLN",
        items=items, customer=customer, placed_at=at, changed_at=at,
    )


def staff_client_for(shop):
    helper = User.objects.create_user(email="pomocnik@example.com", password="Sekretne-haslo-123",
                                      is_email_verified=True)
    ShopMember.objects.create(shop=shop, user=helper)
    client = APIClient()
    client.force_authenticate(helper)
    return client


# --- the list, from the local copy ---


def test_the_list_is_newest_first_with_counts_per_status(auth_client, shop):
    add_order(shop, 1, status="completed", days_ago=3)
    add_order(shop, 2, status="new", days_ago=1)
    add_order(shop, 3, status="cancelled", days_ago=2)

    response = auth_client.get(f"/api/shops/{shop.pk}/orders/")

    assert response.status_code == 200
    assert [order["external_id"] for order in response.data["orders"]] == ["2", "3", "1"]
    assert response.data["orders"][0]["status_display"] == "Nowe"
    assert response.data["counts"] == {"new": 1, "processing": 0, "completed": 1, "cancelled": 1, "unfinished": 0}
    assert response.data["has_more"] is False
    assert response.data["available"] is True


def test_the_list_is_filtered_by_status_and_searched_by_number_or_customer(auth_client, shop):
    add_order(shop, 101, status="new", customer="Anna N.")
    add_order(shop, 102, status="processing", customer="Jan K.")
    add_order(shop, 203, status="processing", customer="Ewa W.")

    def ids(query):
        return [order["external_id"] for order in auth_client.get(f"/api/shops/{shop.pk}/orders/{query}").data["orders"]]

    assert ids("?status=processing") == ["203", "102"]
    assert ids("?q=%2310") == ["102", "101"]
    assert ids("?q=jan") == ["102"]
    assert ids("?status=new&q=jan") == []
    # The counts are of the whole copy, for the filter chips.
    assert auth_client.get(f"/api/shops/{shop.pk}/orders/?q=jan").data["counts"]["processing"] == 2


def test_the_list_comes_in_pages(auth_client, shop, monkeypatch):
    monkeypatch.setattr(orders, "PAGE", 2)
    for number in range(1, 6):
        add_order(shop, number, days_ago=10 - number)

    first = auth_client.get(f"/api/shops/{shop.pk}/orders/").data
    second = auth_client.get(f"/api/shops/{shop.pk}/orders/?before=4").data
    last = auth_client.get(f"/api/shops/{shop.pk}/orders/?before=2").data

    assert ([o["external_id"] for o in first["orders"]], first["has_more"]) == (["5", "4"], True)
    assert ([o["external_id"] for o in second["orders"]], second["has_more"]) == (["3", "2"], True)
    assert ([o["external_id"] for o in last["orders"]], last["has_more"]) == (["1"], False)


def test_orders_placed_at_the_same_time_are_not_skipped_between_pages(auth_client, shop, monkeypatch):
    monkeypatch.setattr(orders, "PAGE", 1)
    first, second = add_order(shop, 1), add_order(shop, 2)
    ShopOrder.objects.filter(pk=second.pk).update(placed_at=first.placed_at)

    page = auth_client.get(f"/api/shops/{shop.pk}/orders/").data
    rest = auth_client.get(f"/api/shops/{shop.pk}/orders/?before={page['orders'][0]['external_id']}").data

    assert {page["orders"][0]["external_id"], rest["orders"][0]["external_id"]} == {"1", "2"}


@pytest.mark.parametrize("query, field", [("?status=lost", "status"), ("?before=999", "before")])
def test_a_wrong_filter_is_refused(auth_client, shop, query, field):
    response = auth_client.get(f"/api/shops/{shop.pk}/orders/{query}")
    assert response.status_code == 400
    assert field in response.data


def test_opening_the_list_reads_new_orders_in_the_background(auth_client, shop, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        response = auth_client.get(f"/api/shops/{shop.pk}/orders/")
    assert response.data["refreshing"] is True
    assert len(callbacks) == 1


def test_the_staff_sees_the_orders(shop):
    add_order(shop, 7)
    client = staff_client_for(shop)

    assert client.get(f"/api/shops/{shop.pk}/orders/").status_code == 200
    assert client.get(f"/api/shops/{shop.pk}/orders/7/").status_code == 200


def test_someone_else_s_orders_are_not_found(api_client, shop):
    stranger = User.objects.create_user(email="obcy@example.com", password="Sekretne-haslo-123", is_email_verified=True)
    api_client.force_authenticate(stranger)
    add_order(shop, 7)

    assert api_client.get(f"/api/shops/{shop.pk}/orders/").status_code == 404
    assert api_client.get(f"/api/shops/{shop.pk}/orders/7/").status_code == 404


# --- the details, read from the shop ---


def test_the_details_are_read_from_the_shop(auth_client, shop):
    add_order(shop, 7, total="120.00", items=2, customer="Jan K.")

    response = auth_client.get(f"/api/shops/{shop.pk}/orders/7/")

    assert response.status_code == 200
    data = response.data
    assert (data["number"], data["status"], data["status_display"], data["total"]) == ("#7", "new", "Nowe", "120.00")
    assert data["customer_name"] == "Jan Kowalski"
    assert data["shipping"]["city"] == "Warszawa"
    assert len(data["lines"]) == 2
    assert Decimal(data["products_total"]) + Decimal(data["shipping_total"]) == Decimal("120.00")
    assert sum(Decimal(line["total"]) for line in data["lines"]) == Decimal(data["products_total"])


def test_the_local_copy_takes_the_status_the_shop_has_now(shop, monkeypatch):
    add_order(shop, 7, status="new")
    real = shop.orders.get()
    from shops.provisioning.fake import FakeProvisioner

    original = FakeProvisioner.read_order

    def shipped(self, shop, external_id):
        from dataclasses import replace
        return replace(original(self, shop, external_id), status="completed")

    monkeypatch.setattr(FakeProvisioner, "read_order", shipped)

    assert orders.read(shop, "7").status == "completed"
    real.refresh_from_db()
    assert real.status == "completed"


def test_an_order_the_shop_does_not_have(auth_client, shop):
    response = auth_client.get(f"/api/shops/{shop.pk}/orders/404/")
    assert response.status_code == 404
    assert response.data["detail"] == "Sklep nie ma takiego zamówienia."


def test_an_unreachable_shop(auth_client, shop, monkeypatch):
    add_order(shop, 7)
    monkeypatch.setattr(FakeApi, "unreachable", {shop.pk: ShopUnavailable("Sklep nie odpowiedział na czas.")})

    response = auth_client.get(f"/api/shops/{shop.pk}/orders/7/")

    assert response.status_code == 503
    assert response.data["detail"] == "Sklep nie odpowiedział na czas."


def test_an_answer_in_an_unexpected_shape(auth_client, shop, monkeypatch):
    from shops.provisioning.fake import FakeProvisioner

    def broken(self, shop, external_id):
        return {}["id"]

    monkeypatch.setattr(FakeProvisioner, "read_order", broken)

    response = auth_client.get(f"/api/shops/{shop.pk}/orders/7/")

    assert response.status_code == 503
    assert response.data["detail"] == "Sklep odpowiedział w nieoczekiwany sposób."


def test_a_suspended_shop_keeps_the_list_but_not_the_details(auth_client, shop):
    add_order(shop, 7)
    Shop.objects.filter(pk=shop.pk).update(status=Shop.Status.SUSPENDED)

    listing = auth_client.get(f"/api/shops/{shop.pk}/orders/")
    detail = auth_client.get(f"/api/shops/{shop.pk}/orders/7/")

    assert (listing.status_code, listing.data["available"], len(listing.data["orders"])) == (200, False, 1)
    assert detail.status_code == 409


# --- the platforms ---


class Api:
    """Stands in for the shop's API: {path: body}; a missing path is NotInShop, like a 404."""

    def __init__(self, bodies, answers=None):
        self.bodies = bodies
        self.calls = []
        # Writes as (method, path, body), and what a POST answers.
        self.writes = []
        self.answers = answers or {}

    def get(self, path, params=None):
        self.calls.append((path, params or {}))
        if path not in self.bodies:
            raise NotInShop("Nie ma tego w sklepie.")
        return self.bodies[path]

    def post(self, path, json=None, params=None):
        self.writes.append(("POST", path, json))
        return self.answers.get(path, {})

    def put(self, path, json=None, params=None):
        self.writes.append(("PUT", path, json))
        return {}

    def send_xml(self, method, path, resource, fields, params=None):
        self.writes.append((method, path, {resource: fields, **({"params": params} if params else {})}))
        return {}


@pytest.fixture
def platform_shop(db):
    owner = User.objects.create_user(email="wlasciciel@example.com", password="Sekretne-haslo-123")
    shop = Shop.objects.create(owner=owner, name="Palarnia", slug="palarnia", status=Shop.Status.ACTIVE)
    ShopConfig.objects.create(
        shop=shop, industry="food", template=ShopTemplate.objects.get(slug="storefront"), category_count=3,
        contact_email="kontakt@example.com",
    )
    return shop


def read_with(provisioner_class, shop, bodies, external_id="12"):
    provisioner = provisioner_class()
    api = Api(bodies)
    provisioner.api = lambda shop: api
    return provisioner.read_order(shop, external_id), api


def change_with(provisioner_class, shop, bodies, action, answers=None, **tracking):
    """Reads order 12, then does `action` on it; returns the stub with the writes."""
    order, _ = read_with(provisioner_class, shop, bodies)
    provisioner = provisioner_class()
    api = Api(bodies, answers)
    provisioner.api = lambda shop: api
    provisioner.change_order(shop, order, action, **tracking)
    return api


WOO_ORDER = {
    "id": 12, "number": "12", "status": "on-hold", "currency": "PLN", "date_created_gmt": "2026-11-18T09:30:00",
    "discount_total": "8.13", "discount_tax": "1.87", "shipping_total": "12.19", "shipping_tax": "2.80",
    "total": "112.79", "customer_note": "Proszę zadzwonić przed doręczeniem.",
    "payment_method_title": "Przelew bankowy",
    "billing": {
        "first_name": "Ewa", "last_name": "Wiśniewska", "company": "", "address_1": "ul. Polna 3", "address_2": "m. 4",
        "city": "Kraków", "postcode": "30-001", "country": "PL", "email": "ewa@example.com", "phone": "600100200",
    },
    "shipping": {"first_name": "", "last_name": "", "company": "", "address_1": "", "address_2": "", "city": "",
                 "postcode": "", "country": "", "phone": ""},
    "line_items": [
        {"name": "Kawa Etiopia", "sku": "KE-250", "quantity": 2, "subtotal": "65.04", "subtotal_tax": "14.96",
         "total": "56.91", "total_tax": "13.09"},
        {"name": "Młynek", "sku": "", "quantity": 1, "subtotal": "16.26", "subtotal_tax": "3.74"},
    ],
    "shipping_lines": [{"method_title": "Kurier DPD", "total": "12.19"}],
}


def test_woocommerce_order(platform_shop):
    order, api = read_with(WooCommerceProvisioner, platform_shop, {"orders/12": WOO_ORDER})

    assert api.calls == [("orders/12", {})]
    assert (order.number, order.status, order.currency) == ("12", "new", "PLN")
    assert [(line.name, line.sku, line.quantity, line.price, line.total) for line in order.lines] == [
        ("Kawa Etiopia", "KE-250", 2, Decimal("40.00"), Decimal("80.00")),
        ("Młynek", "", 1, Decimal("20.00"), Decimal("20.00")),
    ]
    assert (order.products_total, order.shipping_total, order.discount_total, order.total) == (
        Decimal("100.00"), Decimal("14.99"), Decimal("10.00"), Decimal("112.79"))
    assert (order.payment_method, order.shipping_method) == ("Przelew bankowy", "Kurier DPD")
    assert (order.customer_name, order.email, order.phone) == ("Ewa Wiśniewska", "ewa@example.com", "600100200")
    assert order.billing == Address(name="Ewa Wiśniewska", company="", lines=("ul. Polna 3", "m. 4"),
                                    postcode="30-001", city="Kraków", country="Polska", phone="600100200")
    assert order.shipping is None
    assert order.customer_note == "Proszę zadzwonić przed doręczeniem."
    assert order.placed_at == datetime(2026, 11, 18, 9, 30, tzinfo=UTC)


def test_a_woocommerce_checkout_draft_is_not_an_order(platform_shop):
    with pytest.raises(NotInShop):
        read_with(WooCommerceProvisioner, platform_shop, {"orders/12": {**WOO_ORDER, "status": "checkout-draft"}})


PRESTA_BODIES = {
    "orders/12": {"order": {
        "id": 12, "reference": "XKBKNABJK", "current_state": "10", "id_currency": "1", "id_customer": "5",
        "id_carrier": "3", "id_address_delivery": "8", "id_address_invoice": "9", "payment": "Przelew bankowy",
        "total_products_wt": "100.000000", "total_shipping_tax_incl": "14.990000", "total_discounts_tax_incl": "0",
        "total_paid_tax_incl": "114.990000", "date_add": "2026-11-18 10:30:00",
        "associations": {"order_rows": [
            {"product_name": "Kubek - Kolor : Biały", "product_reference": "KUB-1", "product_quantity": "2",
             "unit_price_tax_incl": "50.000000"},
        ]},
    }},
    "configurations": {"configurations": [
        {"name": "PS_OS_CANCELED", "value": "6"}, {"name": "PS_OS_REFUND", "value": "7"},
        {"name": "PS_OS_ERROR", "value": "8"}, {"name": "PS_TIMEZONE", "value": "Europe/Warsaw"},
    ]},
    "order_states": {"order_states": [{"id": 10, "paid": "0", "shipped": "0", "delivery": "0"}]},
    "addresses": {"addresses": [
        {"id": 8, "id_customer": "5", "firstname": "Jan", "lastname": "Kowalski", "company": "",
         "address1": "ul. Długa 1", "address2": "", "postcode": "00-001", "city": "Warszawa", "id_country": "14", "phone": "",
         "phone_mobile": "500600700"},
        {"id": 9, "id_customer": "5", "firstname": "Jan", "lastname": "Kowalski", "company": "Kowalski sp. z o.o.",
         "address1": "ul. Krótka 2", "address2": "", "postcode": "00-002", "city": "Warszawa", "id_country": "1",
         "phone": "221234567", "phone_mobile": ""},
    ]},
    "countries": {"countries": [{"id": 14, "iso_code": "PL"}, {"id": 1, "iso_code": "DE"}]},
    "customers": {"customers": [{"id": 5, "email": "jan@example.com", "firstname": "Jan", "lastname": "Kowalski"}]},
    "carriers": {"carriers": [{"id": 3, "name": "InPost Paczkomaty"}]},
    # Nothing matches: PrestaShop gives an empty list instead of {"messages": []}.
    "messages": [],
    "currencies": {"currencies": [{"id": 1, "iso_code": "PLN"}]},
    "order_carriers": [],
}


def test_prestashop_order(platform_shop):
    order, api = read_with(PrestaShopProvisioner, platform_shop, PRESTA_BODIES)

    assert (order.number, order.status, order.currency) == ("XKBKNABJK", "new", "PLN")
    assert [(line.name, line.sku, line.quantity, line.price, line.total) for line in order.lines] == [
        ("Kubek - Kolor : Biały", "KUB-1", 2, Decimal("50.00"), Decimal("100.00")),
    ]
    assert (order.products_total, order.shipping_total, order.discount_total, order.total) == (
        Decimal("100.00"), Decimal("14.99"), Decimal("0.00"), Decimal("114.99"))
    assert (order.payment_method, order.shipping_method) == ("Przelew bankowy", "InPost Paczkomaty")
    assert (order.customer_name, order.email, order.phone) == ("Jan Kowalski", "jan@example.com", "500600700")
    assert (order.shipping.lines, order.shipping.country) == (("ul. Długa 1",), "Polska")
    assert (order.billing.company, order.billing.country, order.billing.phone) == (
        "Kowalski sp. z o.o.", "Niemcy", "221234567")
    assert order.customer_note == ""
    # Stored in the shop's own time zone.
    assert order.placed_at == datetime(2026, 11, 18, 9, 30, tzinfo=UTC)
    assert dict(api.calls)["addresses"]["filter[id]"] == "[8|9]"
    assert dict(api.calls)["customers"]["filter[id]"] == "[5]"
    assert dict(api.calls)["messages"] == {"filter[id_order]": "[12]", "filter[private]": "[0]",
                                           "display": "[id,message]"}


def test_a_prestashop_order_without_its_customer_link_takes_the_one_of_its_address(platform_shop):
    # The webservice leaves out a link that is 0.
    order = {key: value for key, value in PRESTA_BODIES["orders/12"]["order"].items() if key != "id_customer"}
    detail, api = read_with(PrestaShopProvisioner, platform_shop, {**PRESTA_BODIES, "orders/12": {"order": order}})

    assert dict(api.calls)["customers"]["filter[id]"] == "[5]"
    assert detail.email == "jan@example.com"


@pytest.mark.parametrize("state, flags, status", [
    ("6", {"paid": "0", "shipped": "0", "delivery": "0"}, "cancelled"),
    ("7", {"paid": "1", "shipped": "1", "delivery": "1"}, "cancelled"),
    ("4", {"paid": "1", "shipped": "1", "delivery": "0"}, "completed"),
    ("2", {"paid": "1", "shipped": "0", "delivery": "0"}, "processing"),
])
def test_prestashop_order_states(platform_shop, state, flags, status):
    bodies = {
        **PRESTA_BODIES,
        "orders/12": {"order": {**PRESTA_BODIES["orders/12"]["order"], "current_state": state}},
        "order_states": {"order_states": [{"id": int(state), **flags}]},
        "messages": {"messages": [{"id": 1, "message": " Bez folii, proszę. "}]},
    }
    order, _ = read_with(PrestaShopProvisioner, platform_shop, bodies)
    assert order.status == status
    assert order.customer_note == "Bez folii, proszę."


MAGENTO_ORDER = {
    "entity_id": 12, "increment_id": "000000012", "state": "processing", "order_currency_code": "PLN",
    "created_at": "2026-11-18 09:30:00", "subtotal_incl_tax": 100, "shipping_incl_tax": 14.99,
    "discount_amount": -10, "grand_total": 104.99, "customer_firstname": None, "customer_lastname": None,
    "customer_email": "guest@example.com", "shipping_description": "Flat Rate - Fixed",
    "payment": {"method": "banktransfer", "additional_information": ["Przelew bankowy", "Nr konta: 123"]},
    "billing_address": {"firstname": "Maria", "lastname": "Lewandowska", "street": ["ul. Lipowa 5", ""],
                        "postcode": "80-001", "city": "Gdańsk", "country_id": "PL", "telephone": "511222333"},
    "extension_attributes": {"shipping_assignments": [{"shipping": {
        "address": {"firstname": "Maria", "lastname": "Lewandowska", "company": "Biuro", "street": ["ul. Morska 1"],
                    "postcode": "81-001", "city": "Gdynia", "country_id": "CZ", "telephone": "511222333"},
    }}]},
    "items": [
        {"item_id": 1, "name": "Koszulka", "sku": "KOSZ-M", "qty_ordered": 2.0, "price_incl_tax": 50,
         "row_total_incl_tax": 100, "parent_item_id": None},
        {"item_id": 2, "parent_item_id": 1, "name": "Koszulka M", "sku": "KOSZ-M", "qty_ordered": 2.0,
         "price_incl_tax": 0, "row_total_incl_tax": 0},
    ],
}


def test_magento_order(platform_shop):
    order, api = read_with(MagentoProvisioner, platform_shop, {"orders/12": MAGENTO_ORDER})

    assert api.calls == [("orders/12", {})]
    assert (order.number, order.status, order.currency) == ("000000012", "processing", "PLN")
    assert [(line.name, line.quantity, line.price, line.total) for line in order.lines] == [
        ("Koszulka", 2, Decimal("50.00"), Decimal("100.00")),
    ]
    assert (order.products_total, order.shipping_total, order.discount_total, order.total) == (
        Decimal("100.00"), Decimal("14.99"), Decimal("10.00"), Decimal("104.99"))
    assert (order.payment_method, order.shipping_method) == ("Przelew bankowy", "Flat Rate - Fixed")
    assert (order.customer_name, order.email, order.phone) == ("Maria Lewandowska", "guest@example.com", "511222333")
    assert order.billing.lines == ("ul. Lipowa 5",)
    assert (order.shipping.company, order.shipping.city, order.shipping.country) == ("Biuro", "Gdynia", "Czechy")
    assert order.placed_at == datetime(2026, 11, 18, 9, 30, tzinfo=UTC)


def test_an_api_error_is_passed_on(platform_shop):
    provisioner = MagentoProvisioner()

    class Failing:
        def get(self, path, params=None):
            raise ShopApiError("Sklep zwrócił błąd 500.")

    provisioner.api = lambda shop: Failing()
    with pytest.raises(ShopApiError, match="500"):
        provisioner.read_order(platform_shop, "12")


# --- changing an order ---


def act(client, shop, order_id, action, **fields):
    return client.post(f"/api/shops/{shop.pk}/orders/{order_id}/actions/", {"action": action, **fields}, format="json")


def test_the_details_say_what_can_be_done(auth_client, shop):
    add_order(shop, 1, status="new")
    add_order(shop, 2, status="processing")
    add_order(shop, 3, status="completed")
    add_order(shop, 4, status="unfinished")

    def actions(number):
        return auth_client.get(f"/api/shops/{shop.pk}/orders/{number}/").data["actions"]

    assert actions(1) == ["mark_paid", "mark_shipped", "cancel"]
    assert actions(2) == ["mark_shipped", "cancel"]
    assert actions(3) == []
    assert actions(4) == ["cancel"]


def test_marking_an_order_paid(auth_client, shop, verified_user):
    add_order(shop, 7, status="new")

    response = act(auth_client, shop, 7, "mark_paid")

    assert response.status_code == 200
    assert (response.data["status"], response.data["actions"]) == ("processing", ["mark_shipped", "cancel"])
    assert shop.orders.get().status == "processing"
    event = shop.events.get(kind=ShopEvent.Kind.ORDER_PAID)
    assert (event.actor, event.data) == (verified_user, {"number": "#7"})


def test_shipping_with_a_parcel_number(auth_client, shop):
    add_order(shop, 7, status="processing")

    response = act(auth_client, shop, 7, "mark_shipped", tracking_number=" 6200123 ", carrier="InPost")

    assert response.status_code == 200
    data = response.data
    assert (data["status"], data["tracking_number"], data["carrier"], data["actions"]) == (
        "completed", "6200123", "InPost", [])
    history = auth_client.get(f"/api/shops/{shop.pk}/history/").data["events"][0]
    assert (history["title"], history["detail"]) == ("Wysłanie zamówienia", "Nr #7, przesyłka 6200123 (InPost)")


def test_the_history_keeps_the_parcel_as_the_shop_has_it(auth_client, shop, monkeypatch):
    # E.g. PrestaShop ships with the order's own carrier, whatever was typed in.
    from shops.provisioning.fake import FakeProvisioner

    original = FakeProvisioner.change_order

    def own_carrier(self, shop, order, action, *, tracking_number="", carrier=""):
        original(self, shop, order, action, tracking_number=tracking_number, carrier="Kurier DPD")

    monkeypatch.setattr(FakeProvisioner, "change_order", own_carrier)
    add_order(shop, 7, status="processing")

    response = act(auth_client, shop, 7, "mark_shipped", tracking_number="6200123", carrier="InPost")

    assert response.data["carrier"] == "Kurier DPD"
    assert shop.events.get(kind=ShopEvent.Kind.ORDER_SHIPPED).data == {
        "number": "#7", "tracking_number": "6200123", "carrier": "Kurier DPD",
    }


def test_a_change_done_in_the_shop_is_in_the_history_even_if_reading_it_again_fails(auth_client, shop, monkeypatch):
    add_order(shop, 7, status="processing")
    real_read = orders.read
    reads = []

    def read(shop, external_id):
        reads.append(external_id)
        if len(reads) > 1:
            raise ShopUnavailable("Sklep nie odpowiedział na czas.")
        return real_read(shop, external_id)

    monkeypatch.setattr(orders, "read", read)

    response = act(auth_client, shop, 7, "mark_shipped", tracking_number="6200123", carrier="InPost")

    assert response.status_code == 503
    assert shop.orders.get().status == "completed"
    assert shop.events.get(kind=ShopEvent.Kind.ORDER_SHIPPED).data == {
        "number": "#7", "tracking_number": "6200123", "carrier": "InPost",
    }


def test_a_parcel_number_only_goes_with_shipping(auth_client, shop):
    add_order(shop, 7, status="new")

    response = act(auth_client, shop, 7, "cancel", tracking_number="6200123")

    assert (response.data["status"], response.data["tracking_number"]) == ("cancelled", "")
    assert shop.events.get(kind=ShopEvent.Kind.ORDER_CANCELLED).data == {"number": "#7"}


def test_an_action_the_order_no_longer_offers(auth_client, shop):
    add_order(shop, 7, status="completed")

    response = act(auth_client, shop, 7, "cancel")

    assert response.status_code == 409
    assert "obecny stan" in response.data["detail"]
    assert not shop.events.filter(kind=ShopEvent.Kind.ORDER_CANCELLED).exists()


def test_an_unknown_action_is_refused(auth_client, shop):
    add_order(shop, 7)
    assert act(auth_client, shop, 7, "refund").status_code == 400


def test_an_order_is_changed_only_in_a_running_shop(auth_client, shop):
    add_order(shop, 7)
    Shop.objects.filter(pk=shop.pk).update(status=Shop.Status.SUSPENDED)
    assert act(auth_client, shop, 7, "cancel").status_code == 409


def test_a_shop_that_fails_the_change(auth_client, shop, settings):
    add_order(shop, 7)
    settings.FAKE_PROVISIONER_FAIL_AT_STEP = "change_order"

    response = act(auth_client, shop, 7, "mark_paid")

    assert response.status_code == 503
    assert shop.orders.get().status == "new"
    assert not shop.events.filter(kind=ShopEvent.Kind.ORDER_PAID).exists()


def test_the_staff_handles_orders_and_the_history_says_who(shop):
    add_order(shop, 7, status="new")
    client = staff_client_for(shop)

    assert act(client, shop, 7, "mark_paid").status_code == 200
    assert shop.events.get(kind=ShopEvent.Kind.ORDER_PAID).actor.email == "pomocnik@example.com"


# --- notes ---


def notes_path(shop, order_id=7):
    return f"/api/shops/{shop.pk}/orders/{order_id}/notes/"


def test_team_notes_come_with_the_order(auth_client, shop):
    add_order(shop, 7)
    staff = staff_client_for(shop)

    created = auth_client.post(notes_path(shop), {"text": "  Klient prosi o fakturę.  "}, format="json")
    staff.post(notes_path(shop), {"text": "Wysłane w poniedziałek."}, format="json")
    staff.post(notes_path(shop, 8), {"text": "Inne zamówienie."}, format="json")

    assert created.status_code == 201
    assert created.data["text"] == "Klient prosi o fakturę."
    notes = staff.get(f"/api/shops/{shop.pk}/orders/7/").data["notes"]
    assert [(note["text"], note["author"]["email"], note["can_delete"]) for note in notes] == [
        ("Klient prosi o fakturę.", shop.owner.email, False),
        ("Wysłane w poniedziałek.", "pomocnik@example.com", True),
    ]


def test_a_note_is_deleted_by_its_author_or_the_owner(auth_client, shop):
    staff = staff_client_for(shop)
    owners = auth_client.post(notes_path(shop), {"text": "Od właściciela"}, format="json").data
    helpers = staff.post(notes_path(shop), {"text": "Od obsługi"}, format="json").data

    assert staff.delete(f"{notes_path(shop)}{owners['id']}/").status_code == 403
    assert auth_client.delete(f"{notes_path(shop)}{helpers['id']}/").status_code == 204
    assert staff.delete(f"{notes_path(shop, 8)}{owners['id']}/").status_code == 404
    assert list(ShopOrderNote.objects.values_list("text", flat=True)) == ["Od właściciela"]


def test_an_empty_note_is_refused(auth_client, shop):
    assert auth_client.post(notes_path(shop), {"text": ""}, format="json").status_code == 400
    assert auth_client.post(notes_path(shop), {"text": "x" * 2001}, format="json").status_code == 400


def test_someone_else_s_notes_are_not_found(api_client, shop):
    stranger = User.objects.create_user(email="obcy@example.com", password="Sekretne-haslo-123", is_email_verified=True)
    api_client.force_authenticate(stranger)
    assert api_client.post(notes_path(shop), {"text": "Hej"}, format="json").status_code == 404


# --- changing an order, per platform ---


def test_woocommerce_actions(platform_shop):
    bodies = {"orders/12": WOO_ORDER}

    paid = change_with(WooCommerceProvisioner, platform_shop, bodies, "mark_paid")
    cancelled = change_with(WooCommerceProvisioner, platform_shop, bodies, "cancel")
    shipped = change_with(
        WooCommerceProvisioner, platform_shop, bodies, "mark_shipped", tracking_number="6200123", carrier="InPost",
    )
    bare = change_with(WooCommerceProvisioner, platform_shop, bodies, "mark_shipped")

    assert paid.writes == [("PUT", "orders/12", {"status": "processing", "set_paid": True})]
    assert cancelled.writes == [("PUT", "orders/12", {"status": "cancelled"})]
    assert shipped.writes == [
        ("PUT", "orders/12", {"status": "completed", "meta_data": [
            {"key": "sklepownia_tracking_number", "value": "6200123"},
            {"key": "sklepownia_tracking_carrier", "value": "InPost"},
        ]}),
        ("POST", "orders/12/notes", {
            "note": "Zamówienie zostało wysłane. Numer przesyłki: 6200123 (InPost).", "customer_note": True,
        }),
    ]
    assert bare.writes == [("PUT", "orders/12", {"status": "completed"})]


def test_woocommerce_parcel_and_actions_are_read(platform_shop):
    meta = [{"id": 1, "key": "sklepownia_tracking_number", "value": "6200123"},
            {"id": 2, "key": "sklepownia_tracking_carrier", "value": "InPost"}]
    order, _ = read_with(WooCommerceProvisioner, platform_shop, {
        "orders/12": {**WOO_ORDER, "status": "completed", "meta_data": meta},
    })
    assert (order.tracking_number, order.carrier, order.actions) == ("6200123", "InPost", ())

    order, _ = read_with(WooCommerceProvisioner, platform_shop, {"orders/12": WOO_ORDER})
    assert (order.tracking_number, order.actions) == ("", ("mark_paid", "mark_shipped", "cancel"))


def test_prestashop_shipping_saves_the_parcel_then_the_state(platform_shop):
    bodies = {
        **PRESTA_BODIES,
        "configurations": {"configurations": [
            *PRESTA_BODIES["configurations"]["configurations"],
            {"name": "PS_OS_PAYMENT", "value": "2"}, {"name": "PS_OS_SHIPPING", "value": "4"},
        ]},
        "order_carriers": {"order_carriers": [{
            "id": 3, "id_order": "12", "id_carrier": "3", "id_order_invoice": "0", "weight": "0.000000",
            "shipping_cost_tax_excl": "12.19", "shipping_cost_tax_incl": "14.99", "tracking_number": "",
            "date_add": "2026-11-18 10:30:00",
        }]},
    }

    api = change_with(PrestaShopProvisioner, platform_shop, bodies, "mark_shipped", tracking_number="6200123",
                      carrier="ignorowany")
    paid = change_with(PrestaShopProvisioner, platform_shop, bodies, "mark_paid")

    carrier = bodies["order_carriers"]["order_carriers"][0]
    assert api.writes == [
        ("PUT", "order_carriers/3", {"order_carrier": {**carrier, "tracking_number": "6200123"}}),
        ("POST", "order_histories", {"order_history": {"id_order": 12, "id_order_state": 4},
                                     "params": {"sendemail": 1}}),
    ]
    assert paid.writes == [("POST", "order_histories", {"order_history": {"id_order": 12, "id_order_state": 2},
                                                        "params": {"sendemail": 1}})]


def test_prestashop_parcel_is_read_with_the_order_s_carrier(platform_shop):
    bodies = {**PRESTA_BODIES, "order_carriers": {"order_carriers": [{"id": 3, "tracking_number": "6200123"}]}}
    order, _ = read_with(PrestaShopProvisioner, platform_shop, bodies)
    assert (order.tracking_number, order.carrier) == ("6200123", "InPost Paczkomaty")


def test_prestashop_without_the_state_refuses(platform_shop):
    with pytest.raises(ShopApiError, match="stanu"):
        change_with(PrestaShopProvisioner, platform_shop, PRESTA_BODIES, "mark_paid")


def test_magento_marks_paid_with_an_invoice_and_ships_with_the_parcel(platform_shop):
    new = {**MAGENTO_ORDER, "state": "new", "total_invoiced": None}
    invoiced = {**MAGENTO_ORDER, "total_invoiced": 104.99}

    paid = change_with(MagentoProvisioner, platform_shop, {"orders/12": new}, "mark_paid")
    shipped_unpaid = change_with(MagentoProvisioner, platform_shop, {"orders/12": new}, "mark_shipped",
                                 tracking_number="6200123", carrier="DPD")
    shipped_paid = change_with(MagentoProvisioner, platform_shop, {"orders/12": invoiced}, "mark_shipped")

    assert paid.writes == [("POST", "order/12/invoice", {"capture": False, "notify": True})]
    assert shipped_unpaid.writes == [
        ("POST", "order/12/invoice", {"capture": False, "notify": False}),
        ("POST", "order/12/ship", {"notify": True, "tracks": [
            {"track_number": "6200123", "title": "DPD", "carrier_code": "custom"},
        ]}),
    ]
    assert shipped_paid.writes == [("POST", "order/12/ship", {"notify": True, "tracks": []})]


def test_magento_cancels_only_before_the_invoice(platform_shop):
    new = {**MAGENTO_ORDER, "state": "new", "total_invoiced": None}
    invoiced = {**MAGENTO_ORDER, "total_invoiced": 104.99}

    assert read_with(MagentoProvisioner, platform_shop, {"orders/12": new})[0].actions == (
        "mark_paid", "mark_shipped", "cancel")
    assert read_with(MagentoProvisioner, platform_shop, {"orders/12": invoiced})[0].actions == ("mark_shipped",)
    api = change_with(MagentoProvisioner, platform_shop, {"orders/12": new}, "cancel",
                      answers={"orders/12/cancel": True})
    assert api.writes == [("POST", "orders/12/cancel", None)]
    with pytest.raises(ShopApiError, match="anulować"):
        change_with(MagentoProvisioner, platform_shop, {"orders/12": new}, "cancel",
                    answers={"orders/12/cancel": False})


def test_magento_parcel_is_read_from_the_shipments(platform_shop):
    items = [{**item, "qty_shipped": 2.0} for item in MAGENTO_ORDER["items"]]
    shipments = {"items": [{"tracks": [{"track_number": "6200123", "title": "DPD"}]}]}

    order, api = read_with(MagentoProvisioner, platform_shop, {
        "orders/12": {**MAGENTO_ORDER, "state": "complete", "items": items}, "shipments": shipments,
    })

    assert (order.tracking_number, order.carrier, order.actions) == ("6200123", "DPD", ())
    assert dict(api.calls)["shipments"]["searchCriteria[filterGroups][0][filters][0][value]"] == 12
