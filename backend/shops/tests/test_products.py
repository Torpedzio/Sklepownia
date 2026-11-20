from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from shops.models import Shop, ShopConfig, ShopEvent, ShopMember, ShopTemplate
from shops.platforms.magento import MagentoProvisioner
from shops.platforms.prestashop import PrestaShopProvisioner
from shops.platforms.woocommerce import WooCommerceProvisioner
from shops.products import Category, Filter, description_markup, description_text
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
    assert response.data["categories"] == [{"id": "2", "name": "Dom"}, {"id": "3", "name": "Kuchnia"}]
    assert response.data["url"].endswith("/produkt/12/")
    assert (response.data["description"], response.data["formatted_description"]) == (
        "Ręcznie robiony.\n\nPakowany na prezent.", False)
    assert auth_client.get(products_path(shop, "13/")).data["formatted_description"] is True
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


# --- editing, adding and deleting ---


def test_the_categories_to_choose_from(auth_client, shop):
    response = auth_client.get(products_path(shop, "categories/"))

    assert response.status_code == 200
    assert response.data["categories"] == [
        {"id": "1", "name": "Prezenty"}, {"id": "2", "name": "Dom"}, {"id": "3", "name": "Kuchnia"},
    ]


def test_the_staff_edits_and_only_what_differs_is_saved_and_recorded(auth_client, shop):
    staff = staff_client_for(shop)
    product = staff.get(products_path(shop, "11/")).data

    response = staff.patch(products_path(shop, "11/"), {
        "name": " Kubek z uchem ", "price": product["price"], "categories": ["2"], "visible": True,
        "description": product["description"],
    }, format="json")

    assert response.status_code == 200
    assert (response.data["name"], response.data["visible"]) == ("Kubek z uchem", True)
    assert response.data["categories"] == [{"id": "2", "name": "Dom"}]
    event = shop.events.get(kind=ShopEvent.Kind.PRODUCT_UPDATED)
    assert event.actor.email == "pomocnik@example.com"
    assert event.data == {"name": "Kubek z uchem", "fields": ["Nazwa", "Kategorie", "Widoczność"]}
    history = auth_client.get(f"/api/shops/{shop.pk}/history/").data["events"][0]
    assert (history["title"], history["detail"]) == ("Zmiana produktu", "Kubek z uchem: Nazwa, Kategorie, Widoczność")


def test_a_form_sent_unchanged_saves_nothing(auth_client, shop, settings):
    product = auth_client.get(products_path(shop, "12/")).data
    settings.FAKE_PROVISIONER_FAIL_AT_STEP = "update_product"

    response = auth_client.patch(products_path(shop, "12/"), {
        "name": product["name"], "price": product["regular_price"], "sale_price": product["price"],
        "sku": product["sku"], "categories": ["2", "3"], "visible": product["visible"],
    }, format="json")

    assert response.status_code == 200
    assert not shop.events.filter(kind=ShopEvent.Kind.PRODUCT_UPDATED).exists()


def test_a_new_price_keeps_the_sale_and_the_sale_ends(auth_client, shop):
    sale = auth_client.get(products_path(shop, "12/")).data["price"]

    repriced = auth_client.patch(products_path(shop, "12/"), {"price": "250.00"}, format="json").data
    ended = auth_client.patch(products_path(shop, "12/"), {"sale_price": None}, format="json").data

    assert (repriced["price"], repriced["regular_price"]) == (sale, "250.00")
    assert (ended["price"], ended["regular_price"]) == ("250.00", None)
    fields = [event.data["fields"] for event in shop.events.filter(kind=ShopEvent.Kind.PRODUCT_UPDATED).order_by("pk")]
    assert fields == [["Cena"], ["Cena promocyjna"]]


def test_a_sale_must_be_below_the_price(auth_client, shop):
    response = auth_client.patch(products_path(shop, "11/"), {"sale_price": "999.00"}, format="json")
    created = auth_client.post(products_path(shop), {"name": "Kubek", "price": "20", "sale_price": "20"},
                               format="json")

    assert response.status_code == 400
    assert response.data["sale_price"] == ["Cena promocyjna musi być niższa od ceny."]
    assert created.status_code == 400
    assert not shop.events.filter(kind__in=[ShopEvent.Kind.PRODUCT_UPDATED, ShopEvent.Kind.PRODUCT_CREATED]).exists()


def test_variants_keep_their_prices_but_take_a_new_name(auth_client, shop):
    priced = auth_client.patch(products_path(shop, "14/"), {"price": "10.00"}, format="json")
    named = auth_client.patch(products_path(shop, "14/"), {"name": "Koszulka"}, format="json")

    assert priced.status_code == 409
    assert "warianty" in priced.data["detail"]
    assert named.data["name"] == "Koszulka"


def test_a_name_is_needed_and_values_are_checked(auth_client, shop):
    assert auth_client.patch(products_path(shop, "12/"), {"name": "  "}, format="json").data["name"] == [
        "Podaj nazwę produktu."]
    assert auth_client.patch(products_path(shop, "12/"), {"price": "-1"}, format="json").status_code == 400
    assert auth_client.patch(products_path(shop, "12/"), {"categories": ["x"]}, format="json").status_code == 400
    assert auth_client.patch(products_path(shop, "99/"), {"name": "Kubek"}, format="json").status_code == 404


def test_the_staff_adds_a_product_that_comes_first_in_the_list(auth_client, shop):
    staff = staff_client_for(shop)

    response = staff.post(products_path(shop), {
        "name": "Świeca sojowa", "price": "39.90", "sku": "SW-1", "description": "Pachnie lasem.",
        "categories": ["1"], "stock": 12,
    }, format="json")

    assert response.status_code == 201
    assert response.data["external_id"] == "41"
    assert (response.data["name"], response.data["price"], response.data["stock"], response.data["visible"]) == (
        "Świeca sojowa", "39.90", 12, True)
    assert response.data["categories"] == [{"id": "1", "name": "Prezenty"}]
    assert auth_client.get(products_path(shop)).data["products"][0]["external_id"] == "41"
    event = shop.events.get(kind=ShopEvent.Kind.PRODUCT_CREATED)
    assert (event.actor.email, event.data) == ("pomocnik@example.com", {"name": "Świeca sojowa"})


def test_a_new_product_needs_a_name_and_a_price(auth_client, shop):
    response = auth_client.post(products_path(shop), {"sku": "X"}, format="json")

    assert response.status_code == 400
    assert set(response.data) == {"name", "price"}


def test_only_the_owner_deletes_a_product(auth_client, shop):
    name = auth_client.get(products_path(shop, "12/")).data["name"]

    refused = staff_client_for(shop).delete(products_path(shop, "12/"))
    deleted = auth_client.delete(products_path(shop, "12/"))

    assert refused.status_code == 403
    assert deleted.status_code == 204
    assert auth_client.get(products_path(shop, "12/")).status_code == 404
    assert "12" not in [product["external_id"] for product in auth_client.get(products_path(shop), {"page": 2})
                        .data["products"]]
    event = shop.events.get(kind=ShopEvent.Kind.PRODUCT_DELETED)
    assert event.data == {"name": name}
    assert auth_client.get(f"/api/shops/{shop.pk}/history/").data["events"][0]["title"] == "Usunięcie produktu"


def test_a_refused_edit_or_addition_is_a_503_without_history(auth_client, shop, settings):
    settings.FAKE_PROVISIONER_FAIL_AT_STEP = "update_product"
    edited = auth_client.patch(products_path(shop, "12/"), {"name": "Nowa"}, format="json")
    settings.FAKE_PROVISIONER_FAIL_AT_STEP = "create_product"
    added = auth_client.post(products_path(shop), {"name": "Nowa", "price": "5"}, format="json")

    assert (edited.status_code, added.status_code) == (503, 503)
    assert not shop.events.filter(kind__in=[ShopEvent.Kind.PRODUCT_UPDATED, ShopEvent.Kind.PRODUCT_CREATED]).exists()


def test_writes_need_a_running_shop(auth_client, shop):
    shop.status = Shop.Status.SUSPENDED
    shop.save()

    assert auth_client.patch(products_path(shop, "12/"), {"name": "Nowa"}, format="json").status_code == 409
    assert auth_client.post(products_path(shop), {"name": "Nowa", "price": "5"}, format="json").status_code == 409
    assert auth_client.delete(products_path(shop, "12/")).status_code == 409


def test_the_description_as_plain_text_and_back():
    text, formatted = description_text("<p>Pierwszy&nbsp;akapit<br />druga linia</p>\r\n<div>Drugi &amp; ostatni</div>")
    listed = description_text("<p>Zalety:</p><ul><li>mocna</li><li><strong>tania</strong></li></ul>")

    assert (text, formatted) == ("Pierwszy\xa0akapit\ndruga linia\n\nDrugi & ostatni", False)
    assert listed == ("Zalety:\n\nmocna\ntania", True)
    assert description_text(None) == ("", False)
    assert description_markup(" Jeden\nlinia\n\n\n<Dwa> ") == "<p>Jeden<br>linia</p><p>&lt;Dwa&gt;</p>"
    assert description_markup("") == ""


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
    "images": [{"src": "https://palarnia.example.com/kawa.jpg"}], "categories": [{"id": 16, "name": "Kawa"}],
    "description": "<p>Palona <strong>jasno</strong>.</p>",
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
        "https://palarnia.example.com/kawa.jpg", (Category("16", "Kawa"),),
        "https://palarnia.example.com/produkt/kawa-etiopia/")
    assert (simple.description, simple.formatted_description) == ("Palona jasno.", True)
    # A draft's link is a preview behind the panel's login; variants keep their stock.
    assert (variable.visible, variable.url, variable.has_variants, variable.stock) == (False, "", True, None)


def test_woocommerce_stock_starts_counting(platform_shop):
    provisioner, api = with_api(WooCommerceProvisioner, {"products/31": WOO_PRODUCT})

    provisioner.set_product_stock(platform_shop, provisioner.read_product(platform_shop, "31"), 0)

    assert api.writes == [("PUT", "products/31", {"manage_stock": True, "stock_quantity": 0})]


PRESTA_PRODUCT = {
    "id": 4, "name": "Kawa Etiopia", "reference": "KE-250", "active": "1", "visibility": "both",
    "product_type": "standard", "id_default_image": 12, "final": "35.000000", "regular": "42.000000",
    "associations": {"categories": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 5}]}, "id_category_default": 5,
    "description": [{"id": 1, "value": "<p>Z Etiopii.</p>"}], "id_tax_rules_group": 1,
}
PRESTA_BODIES = {
    "products": {"products": [PRESTA_PRODUCT]},
    "stock_availables": {"stock_availables": [{"id": 9, "id_product": 4, "id_shop": 1, "quantity": 0,
                                               "out_of_stock": 2}]},
    "configurations": {"configurations": [
        {"name": "PS_ROOT_CATEGORY", "value": "1"}, {"name": "PS_HOME_CATEGORY", "value": "2"},
        {"name": "PS_LANG_DEFAULT", "value": "1"}, {"name": "PS_COUNTRY_DEFAULT", "value": "14"},
    ]},
    "categories": {"categories": [
        {"id": 5, "name": [{"id": 1, "value": "Kawa"}, {"id": 2, "value": "Coffee"}]}, {"id": 3, "name": "Herbata"},
    ]},
}


def test_prestashop_details_with_gross_prices_stock_and_categories(platform_shop):
    provisioner, api = with_api(PrestaShopProvisioner, PRESTA_BODIES)

    product = provisioner.read_product(platform_shop, "4")

    assert (product.price, product.regular_price, product.stock, product.in_stock) == (
        Decimal("35.00"), Decimal("42.00"), 0, False)
    assert product.image == f"{platform_shop.url}/img/p/1/2/12-home_default.jpg"
    # The main category first.
    assert product.categories == (Category("5", "Kawa"), Category("3", "Herbata"))
    assert product.description == "Z Etiopii."
    assert product.url == f"{platform_shop.url}/index.php?controller=product&id_product=4"
    params = api.calls[0][1]
    assert (params["filter[id]"], params["price[final][use_tax]"], params["price[regular][use_reduction]"]) == (
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
        {"attribute_code": "description", "value": "<p>Z Etiopii.</p>"},
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
    assert (product.categories, product.url) == ((Category("5", "Kawa"),), f"{platform_shop.url}/kawa-etiopia.html")
    assert product.description == "Z Etiopii."


def test_magento_sold_out_and_stock(platform_shop):
    provisioner, api = with_api(MagentoProvisioner, MAGENTO_BODIES)

    provisioner.read_products(platform_shop, query="", stock_filter=Filter.OUT_OF_STOCK, offset=0, limit=30)
    provisioner.set_product_stock(platform_shop, provisioner.read_product(platform_shop, "4"), 0)

    assert api.calls[0][0] == "inventory/source-items"
    assert api.calls[1][1]["searchCriteria[filterGroups][0][filters][0][value]"] == "kawa-etiopia"
    assert api.writes == [("POST", "inventory/source-items", {"sourceItems": [
        {"sku": "kawa-etiopia", "source_code": "default", "quantity": 0, "status": 0},
    ]})]


def test_woocommerce_writes(platform_shop):
    provisioner, api = with_api(WooCommerceProvisioner, {"products/31": WOO_PRODUCT})
    api.answers["products"] = {"id": 32}
    product = provisioner.read_product(platform_shop, "31")

    provisioner.update_product(platform_shop, product, {
        "name": "Kawa Kenia", "price": Decimal("40"), "sale_price": None, "sku": "KK", "description": "Mocna.",
        "categories": ["16", "17"], "visible": False,
    })
    provisioner.update_product(platform_shop, product, {"visible": True})
    created = provisioner.create_product(platform_shop, {"name": "Kubek", "price": Decimal("20.5"), "stock": 4})
    provisioner.delete_product(platform_shop, product)

    assert api.writes == [
        ("PUT", "products/31", {
            "name": "Kawa Kenia", "regular_price": "40.00", "sale_price": "", "sku": "KK",
            "description": "<p>Mocna.</p>", "categories": [{"id": 16}, {"id": 17}], "status": "draft",
        }),
        ("PUT", "products/31", {"status": "publish", "catalog_visibility": "visible"}),
        ("POST", "products", {
            "type": "simple", "status": "publish", "name": "Kubek", "regular_price": "20.50", "manage_stock": True,
            "stock_quantity": 4,
        }),
        ("DELETE", "products/31", None),
    ]
    assert created == "32"


def test_woocommerce_a_product_in_the_bin_is_not_in_the_shop(platform_shop):
    provisioner, _ = with_api(WooCommerceProvisioner, {"products/31": {**WOO_PRODUCT, "status": "trash"}})

    with pytest.raises(NotInShop):
        provisioner.read_product(platform_shop, "31")


def test_woocommerce_categories(platform_shop):
    provisioner, api = with_api(WooCommerceProvisioner, {"products/categories": [{"id": 16, "name": "Kawa"}]})

    assert provisioner.read_categories(platform_shop) == (Category("16", "Kawa"),)
    assert api.calls[0][1]["hide_empty"] is False


PRESTA_WRITE_BODIES = {
    **PRESTA_BODIES,
    "tax_rules": {"tax_rules": [{"id_tax": 1}]},
    "taxes": {"taxes": [{"rate": "23.000"}]},
    "specific_prices": {"specific_prices": [
        {"id": 7, "id_product_attribute": 0, "id_shop": 1, "id_shop_group": 0, "id_cart": 0, "id_currency": 0,
         "id_country": 0, "id_group": 0, "id_customer": 0, "from_quantity": 1},
        # For a customer group: the owner's, it stays.
        {"id": 8, "id_product_attribute": 0, "id_shop": 0, "id_shop_group": 0, "id_cart": 0, "id_currency": 0,
         "id_country": 0, "id_group": 3, "id_customer": 0, "from_quantity": 1},
    ]},
}


def test_prestashop_an_edit_sends_the_net_price_and_replaces_the_sale(platform_shop):
    provisioner, api = with_api(PrestaShopProvisioner, PRESTA_WRITE_BODIES)
    product = provisioner.read_product(platform_shop, "4")

    provisioner.update_product(platform_shop, product, {
        "name": "Kawa Kenia", "price": Decimal("61.50"), "sale_price": Decimal("50.00"), "sku": "KK",
        "description": "Mocna.", "categories": ["5", "2"], "visible": True,
    })

    patch, removed, sale = api.writes
    assert patch == ("PATCH", "products/4", {"product": {
        "id": 4, "name": {"1": "Kawa Kenia"}, "price": "50.000000", "reference": "KK",
        "description": {"1": "<p>Mocna.</p>"}, "id_category_default": "5",
        "associations": {"categories": [("category", {"id": "2"}), ("category", {"id": "5"})]}, "active": 1,
    }})
    assert removed == ("DELETE", "specific_prices/7", None)
    assert sale == ("POST", "specific_prices", {"specific_price": {
        "id_product_attribute": 0, "id_shop": 0, "id_shop_group": 0, "id_cart": 0, "id_currency": 0,
        "id_country": 0, "id_group": 0, "id_customer": 0, "from_quantity": 1, "id_product": 4, "price": -1,
        "reduction": "11.50", "reduction_tax": 1, "reduction_type": "amount", "from": "0000-00-00 00:00:00",
        "to": "0000-00-00 00:00:00",
    }})


def test_prestashop_the_sale_ends_and_a_hidden_product_is_shown(platform_shop):
    hidden = {**PRESTA_PRODUCT, "visibility": "none", "id_tax_rules_group": 0}
    provisioner, api = with_api(PrestaShopProvisioner, {**PRESTA_WRITE_BODIES, "products": {"products": [hidden]}})
    product = provisioner.read_product(platform_shop, "4")

    provisioner.update_product(platform_shop, product, {"sale_price": None, "visible": True})

    assert api.writes == [
        ("PATCH", "products/4", {"product": {"id": 4, "active": 1, "visibility": "both"}}),
        ("DELETE", "specific_prices/7", None),
    ]


def test_prestashop_a_new_product_without_tax_with_stock_and_a_sale(platform_shop):
    provisioner, api = with_api(PrestaShopProvisioner, PRESTA_WRITE_BODIES)
    api.answers["products"] = {"product": {"id": "9"}}

    created = provisioner.create_product(platform_shop, {
        "name": "Łyżka drewniana", "price": Decimal("20"), "sale_price": Decimal("15"), "stock": 3,
    })

    product, stock, *sale = api.writes
    assert created == "9"
    assert product == ("POST", "products", {"product": {
        "id_tax_rules_group": 0, "active": 1, "visibility": "both", "state": 1, "product_type": "standard",
        "link_rewrite": {"1": "lyzka-drewniana"}, "name": {"1": "Łyżka drewniana"}, "price": "20.000000",
        "id_category_default": "2", "associations": {"categories": [("category", {"id": "2"})]},
    }})
    assert stock[:2] == ("PUT", "stock_availables/9")
    assert sale[-1][2]["specific_price"]["reduction"] == "5.00"


def test_prestashop_categories_below_home_depth_first(platform_shop):
    provisioner, _ = with_api(PrestaShopProvisioner, {**PRESTA_BODIES, "categories": {"categories": [
        {"id": 1, "name": "Root", "id_parent": 0, "position": 0},
        {"id": 2, "name": "Strona główna", "id_parent": 1, "position": 0},
        {"id": 6, "name": "Herbata", "id_parent": 2, "position": 1},
        {"id": 5, "name": "Kawa", "id_parent": 2, "position": 0},
        {"id": 7, "name": "Ziarnista", "id_parent": 5, "position": 0},
    ]}})

    assert [category.name for category in provisioner.read_categories(platform_shop)] == [
        "Kawa", "Ziarnista", "Herbata"]


def test_prestashop_delete(platform_shop):
    provisioner, api = with_api(PrestaShopProvisioner, PRESTA_BODIES)

    provisioner.delete_product(platform_shop, provisioner.read_product(platform_shop, "4"))

    assert api.writes == [("DELETE", "products/4", None)]


def test_magento_an_edit_is_saved_by_id_and_an_ended_sale_removed(platform_shop):
    provisioner, api = with_api(MagentoProvisioner, MAGENTO_BODIES)
    api.answers["products/special-price-information"] = [{"sku": "KK/1", "price": 35}]
    product = provisioner.read_product(platform_shop, "4")

    provisioner.update_product(platform_shop, product, {
        "name": "Kawa Kenia", "price": Decimal("40"), "sale_price": None, "sku": "KK/1", "description": "Mocna.",
        "categories": ["5", "6"], "visible": False,
    })

    assert api.writes == [
        ("POST", "products", {"product": {
            "name": "Kawa Kenia", "price": 40.0, "sku": "KK/1",
            "extension_attributes": {"category_links": [
                {"position": 0, "category_id": "5"}, {"position": 1, "category_id": "6"},
            ]},
            "status": 2, "custom_attributes": [{"attribute_code": "description", "value": "<p>Mocna.</p>"}], "id": 4,
        }}),
        ("POST", "products/special-price-information", {"skus": ["KK/1"]}),
        ("POST", "products/special-price-delete", {"prices": [{"sku": "KK/1", "price": 35}]}),
    ]


def test_magento_a_new_product_gets_a_sku_an_address_and_stock(platform_shop, monkeypatch):
    monkeypatch.setattr("shops.platforms.magento_products.secrets.token_hex", lambda size: "a1b2c3")
    provisioner, api = with_api(MagentoProvisioner, MAGENTO_BODIES)
    api.answers["products"] = {"id": 12}

    created = provisioner.create_product(platform_shop, {
        "name": "Łyżka drewniana", "price": Decimal("20"), "sale_price": Decimal("15"), "stock": 3,
    })

    product, stock = api.writes
    assert created == "12"
    assert product == ("POST", "products", {"product": {
        "sku": "lyzka-drewniana-a1b2c3", "attribute_set_id": 4, "type_id": "simple", "visibility": 4, "status": 1,
        "name": "Łyżka drewniana", "price": 20.0,
        "custom_attributes": [
            {"attribute_code": "special_price", "value": "15"},
            {"attribute_code": "url_key", "value": "lyzka-drewniana-a1b2c3"},
        ],
        "extension_attributes": {"website_ids": [1]},
    }})
    assert stock == ("POST", "inventory/source-items", {"sourceItems": [
        {"sku": "lyzka-drewniana-a1b2c3", "source_code": "default", "quantity": 3, "status": 1},
    ]})


def test_magento_a_sku_with_a_slash_is_renamed_to_be_deleted(platform_shop):
    provisioner, api = with_api(MagentoProvisioner, MAGENTO_BODIES)
    product = provisioner.read_product(platform_shop, "4")

    provisioner.delete_product(platform_shop, product)
    provisioner.delete_product(platform_shop, type(product)(**{**vars(product), "sku": "KK/1 b"}))

    assert api.writes == [
        ("DELETE", "products/kawa-etiopia", None),
        ("POST", "products", {"product": {"id": 4, "sku": "usuwany-4"}}),
        ("DELETE", "products/usuwany-4", None),
    ]


def test_magento_categories_below_the_store_root(platform_shop):
    provisioner, _ = with_api(MagentoProvisioner, {"categories": {"id": 1, "level": 0, "children_data": [
        {"id": 2, "level": 1, "name": "Default Category", "children_data": [
            {"id": 3, "level": 2, "name": "Kawa", "children_data": [{"id": 5, "level": 3, "name": "Ziarnista"}]},
            {"id": 4, "level": 2, "name": "Herbata", "children_data": []},
        ]},
    ]}})

    assert provisioner.read_categories(platform_shop) == (
        Category("3", "Kawa"), Category("5", "Ziarnista"), Category("4", "Herbata"))
