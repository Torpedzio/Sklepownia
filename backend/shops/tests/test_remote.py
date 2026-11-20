import json
from io import StringIO

import pytest
import requests
from django.core.management import call_command

from accounts.models import User
from shops.models import Shop, ShopCredentials
from shops.provisioning.fake import FakeProvisioner
from shops.remote import NotInShop, ShopApiError, ShopNotConnected, ShopRejected, ShopUnavailable, connect
from shops.remote.fake import FakeApi
from shops.remote.magento import MagentoApi
from shops.remote.prestashop import PrestaShopApi
from shops.remote.woocommerce import WooCommerceApi

pytestmark = pytest.mark.django_db


def answer(status=200, body=None, text="", headers=None):
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(body).encode() if body is not None else text.encode()
    response.headers.update(headers or {})
    return response


class Http:
    """Stands in for the network: records requests and gives `replies` in order (an exception is raised)."""

    def __init__(self):
        self.calls = []
        self.replies = []

    def __call__(self, session, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, "auth": session.auth, "session_headers": dict(session.headers),
                           **kwargs})
        reply = self.replies.pop(0) if self.replies else answer(body={})
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def http(monkeypatch):
    fake = Http()
    monkeypatch.setattr(requests.Session, "request", lambda session, *args, **kwargs: fake(session, *args, **kwargs))
    return fake


@pytest.fixture
def shop(db, settings):
    settings.SHOPS_BASE_DOMAIN = "sklepy.example.com"
    settings.SHOPS_URL_SCHEME = "https"
    settings.SHOPS_HTTP_PORT = 443
    owner = User.objects.create_user(email="wlasciciel@example.com", password="Sekretne-haslo-123")
    shop = Shop.objects.create(owner=owner, name="Palarnia", slug="palarnia", status=Shop.Status.ACTIVE)
    ShopCredentials.objects.create(shop=shop, admin_login="admin", api_key="klucz-api")
    return shop


def test_woocommerce_signs_in_as_the_administrator(http, shop):
    http.replies = [answer(body={"code": "PLN"})]

    assert WooCommerceApi(shop).get("data/currencies/current") == {"code": "PLN"}

    [call] = http.calls
    assert call["url"] == "https://palarnia.sklepy.example.com/wp-json/wc/v3/data/currencies/current"
    assert call["auth"] == ("admin", "klucz-api")
    assert call["allow_redirects"] is False
    assert call["timeout"] == (5, 30)


def test_prestashop_goes_through_the_dispatcher_with_the_key_as_login(http, shop):
    PrestaShopApi(shop).get("/orders/7", params={"display": "full"})

    [call] = http.calls
    assert call["url"] == "https://palarnia.sklepy.example.com/webservice/dispatcher.php"
    assert call["params"] == {"display": "full", "url": "orders/7", "output_format": "JSON"}
    assert call["auth"] == ("klucz-api", "")


def test_magento_uses_the_integration_token(http, shop):
    MagentoApi(shop).ping()

    [call] = http.calls
    assert call["url"] == "https://palarnia.sklepy.example.com/rest/all/V1/store/storeViews"
    assert call["session_headers"]["Authorization"] == "Bearer klucz-api"


def test_a_shop_without_a_key_is_not_connected(shop):
    ShopCredentials.objects.filter(shop=shop).update(api_key="")

    with pytest.raises(ShopNotConnected):
        WooCommerceApi(shop)


@pytest.mark.parametrize("reply, error, message", [
    (requests.ConnectionError("refused"), ShopUnavailable, "Nie da się połączyć ze sklepem."),
    (requests.ReadTimeout("slow"), ShopUnavailable, "Sklep nie odpowiedział na czas."),
    (answer(503, text="<html>", headers={"X-Shop-Unavailable": "suspended"}), ShopUnavailable, "chwilowo niedostępny"),
    (answer(502, text="Bad Gateway"), ShopUnavailable, "chwilowo niedostępny"),
    (answer(401, body={"code": "rest_forbidden"}), ShopRejected, "nie przyjął klucza"),
    (answer(301, headers={"Location": "https://inny.example.com/"}), ShopApiError, "przekierował"),
    (answer(404, body={"message": "Nieprawidłowy ID."}), NotInShop, "Nieprawidłowy ID."),
    (answer(500, text="Fatal error"), ShopApiError, "Sklep zwrócił błąd 500."),
    (answer(200, text="<html>nie JSON</html>"), ShopApiError, "w nieoczekiwany sposób"),
])
def test_failures_become_messages_for_the_owner(http, shop, reply, error, message):
    http.replies = [reply]

    with pytest.raises(error, match=message):
        WooCommerceApi(shop).get("orders")


@pytest.mark.parametrize("api, body, message", [
    (WooCommerceApi, {"code": "woocommerce_rest_invalid", "message": "Niepoprawna cena."}, "Niepoprawna cena."),
    (MagentoApi, {"message": "Brak produktu %1 w sklepie %2.", "parameters": ["SKU-1", "default"]},
     "Brak produktu SKU-1 w sklepie default."),
    (MagentoApi, {"message": "Pole %fieldName jest wymagane.", "parameters": {"fieldName": "sku"}},
     "Pole sku jest wymagane."),
    (PrestaShopApi, {"errors": [{"code": 85, "message": "Validation error"}, {"code": 86, "message": "Bad price"}]},
     "Validation error; Bad price"),
])
def test_the_platforms_own_error_text_is_kept(http, shop, api, body, message):
    http.replies = [answer(400, body=body)]

    with pytest.raises(ShopApiError) as error:
        api(shop).get("orders")

    assert str(error.value) == f"Sklep zwrócił błąd: {message}"


def test_an_error_body_of_another_shape_gives_the_status(http, shop):
    http.replies = [answer(400, body={"unexpected": True})]

    with pytest.raises(ShopApiError, match="Sklep zwrócił błąd 400."):
        PrestaShopApi(shop).get("orders")


def test_the_fake_provisioner_connects_to_a_simulated_api(shop, settings):
    settings.SHOP_PROVISIONER = "shops.provisioning.fake.FakeProvisioner"

    connect(shop).ping()

    assert isinstance(connect(shop), FakeApi)


def test_the_simulated_api_can_be_made_unreachable(shop, monkeypatch):
    monkeypatch.setattr(FakeApi, "unreachable", {shop.pk: ShopUnavailable("Sklep jest chwilowo niedostępny.")})

    with pytest.raises(ShopUnavailable):
        FakeApi(shop).ping()


def test_the_fake_step_keeps_the_administrator_and_gives_a_new_key(shop):
    ShopCredentials.objects.filter(shop=shop).update(admin_login="kontakt@example.com", admin_password="haslo")

    FakeProvisioner().step_generate_api_keys(shop)

    credentials = ShopCredentials.objects.get(shop=shop)
    assert (credentials.admin_login, credentials.admin_password) == ("kontakt@example.com", "haslo")
    assert credentials.api_key not in ("", "klucz-api")


@pytest.fixture
def fake_shops(settings):
    settings.SHOP_PROVISIONER = "shops.provisioning.fake.FakeProvisioner"


def test_connect_shop_api_gives_new_keys_and_checks_them(shop, fake_shops):
    out, err = StringIO(), StringIO()

    call_command("connect_shop_api", "palarnia", "nie-ma-takiego", stdout=out, stderr=err)

    assert "palarnia: połączony" in out.getvalue()
    assert "nie-ma-takiego: nie ma takiego działającego sklepu" in err.getvalue()
    assert ShopCredentials.objects.get(shop=shop).api_key != "klucz-api"


def test_connect_shop_api_check_only_reports_what_fails(shop, fake_shops, monkeypatch):
    monkeypatch.setattr(FakeApi, "unreachable", {shop.pk: ShopRejected("Sklep nie przyjął klucza aplikacji.")})
    err = StringIO()

    call_command("connect_shop_api", "--check", stdout=StringIO(), stderr=err)

    assert "palarnia: brak połączenia (Sklep nie przyjął klucza aplikacji.)" in err.getvalue()
    assert ShopCredentials.objects.get(shop=shop).api_key == "klucz-api"
