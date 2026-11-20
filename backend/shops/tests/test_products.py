from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from shops.models import Shop, ShopConfig, ShopEvent, ShopMember, ShopTemplate
from shops.platforms.magento import MagentoProvisioner
from shops.platforms.prestashop import PrestaShopProvisioner
from shops.platforms.woocommerce import WooCommerceProvisioner
from shops.products import Filter
from shops.remote import NotInShop, ShopUnavailable
from shops.remote.fake import FakeApi
from shops.tests.test_orders import Api

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(auth_client, django_capture_on_commit_callbacks):
    payload = {"name": "Mój Sklep", "slug": "moj-sklep", "industry": "fashion", "template": "storefront"}
    with django_capture_on_commit_callbacks(execute=True):
        shop_id = auth_client.post("/api/shops/", payload, format="json").data["id"]
    shop = Shop.objects.get(pk=shop_id)
    assert shop.status == Shop.Status.ACTIVE
    return shop


def staff_client_for(shop):
    helper = User.objects.create_user(email="pomocnik@example.com", password="Sekretne-haslo-123",
                                      is_email_verified=True)
    ShopMember.objects.create(shop=shop, user=helper)
    client = APIClient()
    client.force_authenticate(helper)
    return client


def products_path(shop, suffix=""):
    return f"/api/shops/{shop.pk}/products/{suffix}"


# --- the list ---


def test_the_list_is_read_from_the_shop_newest_first_by_pages(auth_client, shop):
    first = auth_client.get(products_path(shop))
    second = auth_client.get(products_path(shop), {"page": 2})

    assert first.status_code == 200
    assert first.data["currency"] == "PLN"
    assert [product["external_id"] for product in first.data["products"]][:3] == ["40", "39", "38"]
    assert (len(first.data["products"]), first.data["has_more"]) == (30, True)
    assert [product["external_id"] for product in second.data["products"]] == [str(n) for n in range(10, 0, -1)]
    assert second.data["has_more"] is False
    product = first.data["products"][0]
    assert set(product) == {
        "external_id", "name", "sku", "price", "regular_price", "stock", "in_stock", "visible", "image",
        "has_variants",
    }


def test_the_list_is_searched_and_filtered(auth_client, shop):
    found = auth_client.get(products_path(shop), {"q": " sku-012 "}).data["products"]
    sold_out = auth_client.get(products_path(shop), {"stock": "out_of_stock"}).data["products"]

    assert [product["external_id"] for product in found] == ["12"]
    assert sold_out and all(not product["in_stock"] for product in sold_out)


def test_unknown_filters_and_pages_are_refused(auth_client, shop):
    assert auth_client.get(products_path(shop), {"stock": "low"}).status_code == 400
    assert auth_client.get(products_path(shop), {"page": "0"}).status_code == 400
    assert auth_client.get(products_path(shop), {"page": "x"}).status_code == 400


def test_a_shop_that_is_not_running(auth_client, shop):
    shop.status = Shop.Status.SUSPENDED
    shop.save()
    assert auth_client.get(products_path(shop)).status_code == 409
    assert auth_client.get(products_path(shop, "12/")).status_code == 409


def test_an_unreachable_shop_is_a_503(auth_client, shop, monkeypatch):
    def down(self):
        raise ShopUnavailable("Sklep nie odpowiedział na czas.")

    monkeypatch.setattr(FakeApi, "ping", down)

    response = auth_client.get(products_path(shop))

    assert response.status_code == 503
    assert response.data["detail"] == "Sklep nie odpowiedział na czas."


def test_someone_else_s_shop_is_not_found(api_client, shop):
    stranger = User.objects.create_user(email="obcy@example.com", password="Sekretne-haslo-123", is_email_verified=True)
    api_client.force_authenticate(stranger)
    assert api_client.get(products_path(shop)).status_code == 404


# --- one product and its stock ---


def test_the_details(auth_client, shop):
    response = auth_client.get(products_path(shop, "12/"))

    assert response.status_code == 200
    assert response.data["name"] == "Notes w kratkę 12"
    assert response.data["currency"] == "PLN"
    assert response.data["categories"] == ["Dom", "Kuchnia"]
    assert response.data["url"].endswith("/produkt/12/")
    assert auth_client.get(products_path(shop, "99/")).status_code == 404


def test_the_staff_changes_the_stock_and_the_history_says_who(auth_client, shop):
    staff = staff_client_for(shop)
    before = staff.get(products_path(shop, "12/")).data["stock"]

    response = staff.post(products_path(shop, "12/stock/"), {"quantity": 25}, format="json")

    assert response.status_code == 200
    assert (response.data["stock"], response.data["in_stock"]) == (25, True)
    event = shop.events.get(kind=ShopEvent.Kind.PRODUCT_STOCK)
    assert event.actor.email == "pomocnik@example.com"
    assert event.data == {"name": "Notes w kratkę 12", "before": before, "after": 25}
    history = auth_client.get(f"/api/shops/{shop.pk}/history/").data["events"][0]
    assert (history["title"], history["detail"]) == ("Zmiana stanu produktu", f"Notes w kratkę 12: {before} → 25 szt.")


def test_zero_sells_out_and_counting_starts_when_the_shop_did_not_count(auth_client, shop):
    sold_out = auth_client.post(products_path(shop, "12/stock/"), {"quantity": 0}, format="json").data
    uncounted = auth_client.get(products_path(shop, "18/")).data

    counted = auth_client.post(products_path(shop, "18/stock/"), {"quantity": 3}, format="json").data

    assert (sold_out["stock"], sold_out["in_stock"]) == (0, False)
    assert uncounted["stock"] is None
    assert counted["stock"] == 3
    event = shop.events.filter(kind=ShopEvent.Kind.PRODUCT_STOCK).latest("pk")
    assert auth_client.get(f"/api/shops/{shop.pk}/history/").data["events"][0]["detail"] == (
        f"{uncounted['name']}: bez liczenia → 3 szt.")
    assert event.data["before"] is None


def test_variants_keep_their_stock_in_the_panel(auth_client, shop):
    response = auth_client.post(products_path(shop, "14/stock/"), {"quantity": 5}, format="json")

    assert response.status_code == 409
    assert "warianty" in response.data["detail"]
    assert not shop.events.filter(kind=ShopEvent.Kind.PRODUCT_STOCK).exists()


def test_a_stock_outside_the_range_is_refused(auth_client, shop):
    assert auth_client.post(products_path(shop, "12/stock/"), {"quantity": -1}, format="json").status_code == 400
    assert auth_client.post(products_path(shop, "12/stock/"), {"quantity": 10**6}, format="json").status_code == 400
    assert auth_client.post(products_path(shop, "12/stock/"), {}, format="json").status_code == 400


def test_a_refused_change_is_a_503_without_history(auth_client, shop, settings):
    settings.FAKE_PROVISIONER_FAIL_AT_STEP = "set_product_stock"
    response = auth_client.post(products_path(shop, "12/stock/"), {"quantity": 5}, format="json")

    assert response.status_code == 503
    assert not shop.events.filter(kind=ShopEvent.Kind.PRODUCT_STOCK).exists()


# --- per platform, against a stand-in for the shop's API ---

@pytest.fixture
def platform_shop(db):
    owner = User.objects.create_user(email="wlasciciel@example.com", password="Sekretne-haslo-123")
    shop = Shop.objects.create(owner=owner, name="Palarnia", slug="palarnia", status=Shop.Status.ACTIVE)
    ShopConfig.objects.create(
        shop=shop, industry="food", template=ShopTemplate.objects.get(slug="storefront"), category_count=3,
        contact_email="kontakt@example.com",
    )
    return shop


def with_api(provisioner_class, bodies):
    provisioner = provisioner_class()
    api = Api(bodies)
    provisioner.api = lambda shop: api
    return provisioner, api


WOO_PRODUCT = {
    "id": 31, "name": "Kawa Etiopia", "sku": "KE-250", "type": "simple", "status": "publish",
    "catalog_visibility": "visible", "price": "35.00", "regular_price": "42.00", "sale_price": "35.00",
    "on_sale": True, "manage_stock": True, "stock_quantity": 7, "stock_status": "instock",
    "images": [{"src": "https://palarnia.example.com/kawa.jpg"}], "categories": [{"name": "Kawa"}],
    "permalink": "https://palarnia.example.com/produkt/kawa-etiopia/",
}
WOO_VARIABLE = {
    **WOO_PRODUCT, "id": 30, "type": "variable", "on_sale": False, "manage_stock": False, "stock_quantity": None,
    "status": "draft", "images": [],
}


def test_woocommerce_list_and_details(platform_shop):
    provisioner, api = with_api(WooCommerceProvisioner, {
        "products": [WOO_PRODUCT, WOO_VARIABLE], "products/31": WOO_PRODUCT, "products/30": WOO_VARIABLE,
    })

    page = provisioner.read_products(platform_shop, query="kawa", stock_filter=Filter.OUT_OF_STOCK, offset=30,
                                     limit=1)
    simple, variable = provisioner.read_product(platform_shop, "31"), provisioner.read_product(platform_shop, "30")

    assert page.has_more is True
    assert [product.external_id for product in page.products] == ["31"]
    assert api.calls[0] == ("products", {
        "status": "any", "orderby": "date", "order": "desc", "offset": 30, "per_page": 2, "search": "kawa",
        "stock_status": "outofstock",
    })
    assert (simple.price, simple.regular_price, simple.stock, simple.in_stock) == (
        Decimal("35.00"), Decimal("42.00"), 7, True)
    assert (simple.image, simple.categories, simple.url) == (
        "https://palarnia.example.com/kawa.jpg", ("Kawa",), "https://palarnia.example.com/produkt/kawa-etiopia/")
    # A draft's link is a preview behind the panel's login; variants keep their stock.
    assert (variable.visible, variable.url, variable.has_variants, variable.stock) == (False, "", True, None)


def test_woocommerce_stock_starts_counting(platform_shop):
    provisioner, api = with_api(WooCommerceProvisioner, {"products/31": WOO_PRODUCT})

    provisioner.set_product_stock(platform_shop, provisioner.read_product(platform_shop, "31"), 0)

    assert api.writes == [("PUT", "products/31", {"manage_stock": True, "stock_quantity": 0})]


PRESTA_PRODUCT = {
    "id": 4, "name": "Kawa Etiopia", "reference": "KE-250", "active": "1", "visibility": "both",
    "product_type": "standard", "id_default_image": 12, "final": "35.000000", "regular": "42.000000",
    "associations": {"categories": [{"id": 1}, {"id": 2}, {"id": 5}]},
}
PRESTA_BODIES = {
    "products": {"products": [PRESTA_PRODUCT]},
    "stock_availables": {"stock_availables": [{"id": 9, "id_product": 4, "id_shop": 1, "quantity": 0,
                                               "out_of_stock": 2}]},
    "configurations": {"configurations": [{"name": "PS_ROOT_CATEGORY", "value": "1"},
                                          {"name": "PS_HOME_CATEGORY", "value": "2"}]},
    "categories": {"categories": [{"id": 5, "name": [{"id": 1, "value": "Kawa"}, {"id": 2, "value": "Coffee"}]}]},
}


def test_prestashop_details_with_gross_prices_stock_and_categories(platform_shop):
    provisioner, api = with_api(PrestaShopProvisioner, PRESTA_BODIES)

    product = provisioner.read_product(platform_shop, "4")

    assert (product.price, product.regular_price, product.stock, product.in_stock) == (
        Decimal("35.00"), Decimal("42.00"), 0, False)
    assert product.image == f"{platform_shop.url}/img/p/1/2/12-home_default.jpg"
    assert product.categories == ("Kawa",)
    assert product.url == f"{platform_shop.url}/index.php?controller=product&id_product=4"
    params = api.calls[0][1]
    assert (params["filter[id]"], params["price[final][use_tax]"], params["price[regular][use_reduc]"]) == (
        "[4]", "1", "0")


def test_prestashop_sold_out_reads_the_stock_first(platform_shop):
    provisioner, api = with_api(PrestaShopProvisioner, PRESTA_BODIES)

    page = provisioner.read_products(platform_shop, query="", stock_filter=Filter.OUT_OF_STOCK, offset=0, limit=30)

    assert [product.external_id for product in page.products] == ["4"]
    assert api.calls[0][0] == "stock_availables"
    assert api.calls[0][1]["filter[quantity]"] == "[-999999999,0]"
    assert api.calls[1][1]["filter[id]"] == "[4]"


def test_prestashop_nothing_sold_out(platform_shop):
    provisioner, api = with_api(PrestaShopProvisioner, {**PRESTA_BODIES, "stock_availables": []})

    page = provisioner.read_products(platform_shop, query="", stock_filter=Filter.OUT_OF_STOCK, offset=0, limit=30)

    assert (page.products, page.has_more) == ((), False)
    assert [path for path, _ in api.calls] == ["stock_availables"]


def test_prestashop_combinations_are_variants_and_a_missing_product_is_not_in_the_shop(platform_shop):
    combined = {**PRESTA_PRODUCT, "associations": {"combinations": [{"id": 1}]}}
    provisioner, _ = with_api(PrestaShopProvisioner, {**PRESTA_BODIES, "products": {"products": [combined]}})
    assert provisioner.read_product(platform_shop, "4").has_variants is True

    provisioner, _ = with_api(PrestaShopProvisioner, {**PRESTA_BODIES, "products": []})
    with pytest.raises(NotInShop):
        provisioner.read_product(platform_shop, "4")


def test_prestashop_stock_puts_the_whole_row_with_the_fields_left_out_for_0(platform_shop):
    provisioner, api = with_api(PrestaShopProvisioner, PRESTA_BODIES)

    provisioner.set_product_stock(platform_shop, provisioner.read_product(platform_shop, "4"), 15)

    assert api.writes == [("PUT", "stock_availables/9", {"stock_available": {
        "id": 9, "id_product": 4, "id_product_attribute": 0, "id_shop": 1, "id_shop_group": 0, "quantity": 15,
        "depends_on_stock": 0, "out_of_stock": 2, "location": "",
    }})]


MAGENTO_PRODUCT = {
    "id": 4, "sku": "kawa-etiopia", "name": "Kawa Etiopia", "price": 42, "status": 1, "visibility": 4,
    "type_id": "simple",
    "custom_attributes": [
        {"attribute_code": "special_price", "value": "35.0000"},
        {"attribute_code": "special_to_date", "value": "2000-01-01 00:00:00"},
        {"attribute_code": "thumbnail", "value": "/k/a/kawa.jpg"},
        {"attribute_code": "url_key", "value": "kawa-etiopia"},
        {"attribute_code": "category_ids", "value": ["5"]},
    ],
}
MAGENTO_BODIES = {
    "products": {"items": [MAGENTO_PRODUCT], "total_count": 31},
    "inventory/source-items": {"items": [{"sku": "kawa-etiopia", "source_code": "default", "quantity": 3.0,
                                          "status": 1}]},
    "categories/list": {"items": [{"id": 5, "name": "Kawa"}]},
}


def test_magento_list_pages_and_searches_name_or_sku(platform_shop):
    provisioner, api = with_api(MagentoProvisioner, MAGENTO_BODIES)

    page = provisioner.read_products(platform_shop, query="kawa", stock_filter=Filter.ALL, offset=30, limit=30)

    assert page.has_more is False
    params = api.calls[0][1]
    assert params["searchCriteria[currentPage]"] == 2
    assert (params["searchCriteria[filterGroups][0][filters][0][field]"],
            params["searchCriteria[filterGroups][0][filters][1][field]"]) == ("name", "sku")
    assert params["searchCriteria[filterGroups][0][filters][1][value]"] == "%kawa%"


def test_magento_details_stock_from_the_source_and_an_ended_sale(platform_shop):
    provisioner, _ = with_api(MagentoProvisioner, MAGENTO_BODIES)

    product = provisioner.read_product(platform_shop, "4")

    # The special price ended in 2000.
    assert (product.price, product.regular_price, product.stock, product.in_stock) == (Decimal("42.00"), None, 3, True)
    assert product.image == f"{platform_shop.url}/media/catalog/product/k/a/kawa.jpg"
    assert (product.categories, product.url) == (("Kawa",), f"{platform_shop.url}/kawa-etiopia.html")


def test_magento_sold_out_and_stock(platform_shop):
    provisioner, api = with_api(MagentoProvisioner, MAGENTO_BODIES)

    provisioner.read_products(platform_shop, query="", stock_filter=Filter.OUT_OF_STOCK, offset=0, limit=30)
    provisioner.set_product_stock(platform_shop, provisioner.read_product(platform_shop, "4"), 0)

    assert api.calls[0][0] == "inventory/source-items"
    assert api.calls[1][1]["searchCriteria[filterGroups][0][filters][0][value]"] == "kawa-etiopia"
    assert api.writes == [("POST", "inventory/source-items", {"sourceItems": [
        {"sku": "kawa-etiopia", "source_code": "default", "quantity": 0, "status": 0},
    ]})]
