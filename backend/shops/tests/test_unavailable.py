import pytest
from django.test import Client

from shops.models import Shop

PAGE = "/shop-unavailable/"


@pytest.fixture
def shop(auth_client, django_capture_on_commit_callbacks):
    payload = {"name": "Palarnia", "slug": "palarnia", "industry": "fashion", "template": "storefront",
               "platform": "woocommerce"}
    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client.post("/api/shops/", payload, format="json")
    assert response.status_code == 201, response.data
    return Shop.objects.get(pk=response.data["id"])


def visit(client, host, method="get"):
    """What the shops' proxy sends for a visitor of `host` when no shop container answers."""
    return getattr(client, method)(PAGE, HTTP_X_FORWARDED_HOST=host)


def set_status(shop, status):
    Shop.objects.filter(pk=shop.pk).update(status=status)


def test_a_suspended_shop_is_closed_for_now(client, shop):
    set_status(shop, Shop.Status.SUSPENDED)

    response = visit(client, "palarnia.localhost:8080")

    assert response.status_code == 503
    assert response["Retry-After"] == "3600"
    assert "no-store" in response["Cache-Control"]
    page = response.content.decode()
    assert "<h1>Palarnia</h1>" in page
    assert "Nieczynne" in page
    assert "Sklep jest chwilowo niedostępny. Zajrzyj tu później." in page


def test_a_running_shop_whose_container_is_restarting_is_closed_for_now(client, shop):
    response = visit(client, "Palarnia.LOCALHOST")

    assert response.status_code == 503
    assert "Nieczynne" in response.content.decode()


@pytest.mark.parametrize("status", [Shop.Status.PENDING, Shop.Status.PROVISIONING])
def test_a_shop_being_set_up_opens_soon(client, shop, status):
    set_status(shop, status)

    response = visit(client, "palarnia.localhost")

    assert response.status_code == 503
    assert response["Retry-After"] == "300"
    assert "Wkrótce otwarcie" in response.content.decode()


@pytest.mark.parametrize("language, lang, words", [
    ("en_US", "en", ["Closed", "The shop is temporarily unavailable."]),
    ("de_DE", "de", ["Geschlossen", "Der Shop ist vorübergehend nicht erreichbar."]),
])
def test_the_page_speaks_the_shops_language(client, shop, language, lang, words):
    shop.config.language = language
    shop.config.save()
    set_status(shop, Shop.Status.SUSPENDED)

    page = visit(client, "palarnia.localhost").content.decode()

    assert f'<html lang="{lang}">' in page
    assert all(word in page for word in words)


@pytest.mark.parametrize("host", [
    "nieznany.localhost",
    "palarnia.example.com",
    "localhost",
    "sklep.palarnia.localhost",
    "",
])
def test_an_address_without_a_shop_is_not_found(client, shop, host):
    response = visit(client, host)

    assert response.status_code == 404
    page = response.content.decode()
    assert "Nie ma tu sklepu" in page
    assert "Palarnia" not in page


def test_a_deleted_shop_is_not_found(client, shop):
    set_status(shop, Shop.Status.DELETED)

    assert visit(client, "palarnia.localhost").status_code == 404


def test_a_form_sent_to_a_shop_that_is_down_gets_the_page_too(shop):
    set_status(shop, Shop.Status.SUSPENDED)

    response = visit(Client(enforce_csrf_checks=True), "palarnia.localhost", method="post")

    assert response.status_code == 503
