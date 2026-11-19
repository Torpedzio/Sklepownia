"""Terms and privacy policy with the fake provisioner; platform publishing is tested in test_<platform>.py."""

from datetime import date

import pytest
from django.core.management import call_command

from billing.models import BillingProfile
from shops import documents, services
from shops.models import Shop, ShopChecklist, ShopOperation, ShopSettings
from shops.provisioning.operations import PUBLISH_ERROR
from shops.shop_settings import default_settings

pytestmark = pytest.mark.django_db

PUBLISH = "shops.provisioning.fake.FakeProvisioner.publish_documents"
SELLER = {
    "seller_name": "Palarnia Kawy Anna Nowak", "register": "ceidg", "street": "ul. Kwiatowa 1/2",
    "postal_code": "00-001", "city": "Łódź", "tax_id": "526-000-12-46",
}


@pytest.fixture
def shop(auth_client, django_capture_on_commit_callbacks):
    payload = {"name": "Palarnia", "slug": "palarnia", "industry": "fashion", "template": "storefront"}
    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client.post("/api/shops/", payload, format="json")
    assert response.status_code == 201, response.data
    return Shop.objects.get(pk=response.data["id"])


@pytest.fixture
def published(monkeypatch):
    """One {key: Document} per publish_documents call."""
    calls = []

    def publish(self, shop, rendered):
        calls.append({document.key: document for document in rendered})
        return {document.key: f"{shop.url}/{document.slug}/" for document in rendered}

    monkeypatch.setattr(PUBLISH, publish)
    return calls


def patch(client, shop, captured, **sections):
    with captured(execute=True):
        return client.patch(f"/api/shops/{shop.pk}/settings/", sections, format="json")


def turn_on(client, shop, captured, **fields):
    return patch(client, shop, captured, documents={"managed": True, **SELLER, **fields})


def values(**changes):
    shop = Shop.objects.first()
    result = default_settings(shop)
    result["documents"].update(managed=True, **{**SELLER, "tax_id": "5260001246"})
    for section, fields in changes.items():
        result[section].update(fields)
    return result


def text(document):
    lines = []
    for block in document.blocks:
        if block["type"] == "list":
            for item in block["items"]:
                lines.append(item["text"])
                lines += [sub["text"] for sub in item.get("items", [])]
        else:
            lines.append(block["text"])
    return "\n".join(lines)


def render(**changes):
    return {document.key: document for document in documents.render(values(**changes), "https://palarnia.example.com",
                                                                    date(2026, 11, 18))}


def test_documents_are_off_until_the_owner_turns_them_on(auth_client, shop, verified_user):
    BillingProfile.objects.create(
        user=verified_user, kind="company", full_name="Anna Nowak", company_name="Palarnia sp. z o.o.",
        tax_id="PL 526-000-12-46", street="Kwiatowa 1", postal_code="00-001", city="Warszawa",
    )
    ShopSettings.objects.filter(shop=shop).delete()

    data = auth_client.get(f"/api/shops/{shop.pk}/settings/").data

    assert "documents" in data["sections"]
    assert data["values"]["documents"] == {
        "managed": False, "seller_name": "Palarnia sp. z o.o.", "register": "ceidg", "street": "Kwiatowa 1",
        "postal_code": "00-001", "city": "Warszawa", "tax_id": "5260001246", "regon": "", "krs": "", "phone": "",
        "return_days": 14, "free_returns": False, "dispatch_days": 2, "terms_url": "", "privacy_url": "",
        "version": "",
    }


def test_turning_documents_on_publishes_them(auth_client, shop, published, django_capture_on_commit_callbacks):
    response = turn_on(auth_client, shop, django_capture_on_commit_callbacks)

    assert response.status_code == 202, response.data
    [rendered] = published
    assert set(rendered) == {"terms", "privacy"}
    assert "Palarnia Kawy Anna Nowak" in rendered["terms"].html
    stored = ShopSettings.objects.get(shop=shop).values["documents"]
    assert stored["terms_url"] == "https://palarnia.localhost/regulamin/"
    assert stored["privacy_url"] == "https://palarnia.localhost/polityka-prywatnosci/"
    assert stored["version"] == documents.VERSION
    assert stored["tax_id"] == "5260001246"
    operation = ShopOperation.objects.get(shop=shop)
    assert operation.status == ShopOperation.Status.SUCCEEDED
    changed = auth_client.get(f"/api/shops/{shop.pk}/operations/").data[0]["changed_fields"]
    assert changed[:2] == ["Regulamin i polityka prywatności z aplikacji", "Nazwa sprzedawcy"]


def test_what_the_documents_describe_publishes_them_again(auth_client, shop, published,
                                                          django_capture_on_commit_callbacks):
    turn_on(auth_client, shop, django_capture_on_commit_callbacks)

    patch(auth_client, shop, django_capture_on_commit_callbacks, payments={"cash_on_delivery_enabled": True})
    patch(auth_client, shop, django_capture_on_commit_callbacks, taxes={"enabled": True})

    assert len(published) == 2
    assert "płatność przy odbiorze" in published[1]["terms"].html


def test_documents_off_are_left_alone(auth_client, shop, published, django_capture_on_commit_callbacks):
    turn_on(auth_client, shop, django_capture_on_commit_callbacks)
    patch(auth_client, shop, django_capture_on_commit_callbacks, documents={"managed": False})

    patch(auth_client, shop, django_capture_on_commit_callbacks, payments={"cash_on_delivery_enabled": True})

    assert len(published) == 1
    # Turning documents off leaves the pages in the shop.
    assert ShopSettings.objects.get(shop=shop).values["documents"]["terms_url"]


def test_a_failed_publication_keeps_the_details_out(auth_client, shop, settings, django_capture_on_commit_callbacks):
    settings.FAKE_PROVISIONER_FAIL_AT_STEP = "publish_documents"

    turn_on(auth_client, shop, django_capture_on_commit_callbacks)

    operation = ShopOperation.objects.get(shop=shop)
    assert operation.status == ShopOperation.Status.FAILED
    assert operation.error == PUBLISH_ERROR
    assert ShopSettings.objects.get(shop=shop).values["documents"]["managed"] is False


def test_documents_need_the_sellers_details(auth_client, shop):
    response = auth_client.patch(f"/api/shops/{shop.pk}/settings/", {"documents": {"managed": True}}, format="json")

    assert response.status_code == 400
    assert response.data["documents"] == {
        field: ["Potrzebne do regulaminu."] for field in ("seller_name", "street", "postal_code", "city", "tax_id")
    }


@pytest.mark.parametrize(("register", "required"), [
    ("krs", {"tax_id", "krs"}),
    ("unregistered", set()),
])
def test_what_identifies_the_seller_depends_on_the_register(auth_client, shop, register, required):
    response = auth_client.patch(f"/api/shops/{shop.pk}/settings/", {"documents": {
        **SELLER, "managed": True, "register": register, "tax_id": "",
    }}, format="json")

    if required:
        assert set(response.data["documents"]) == required
    else:
        assert response.status_code == 202


@pytest.mark.parametrize(("field", "value", "message"), [
    ("tax_id", "5260001247", "Ten NIP ma błąd. Sprawdź, czy nie brakuje cyfry."),
    ("postal_code", "00001", "Kod pocztowy w formacie 00-000."),
    ("krs", "12345", "Numer KRS ma 10 cyfr, np. 0000123456."),
    ("regon", "12345", "REGON ma 9 albo 14 cyfr."),
    ("phone", "zadzwoń", "Wpisz numer telefonu, np. 600 100 200."),
    ("return_days", 7, "Upewnij się, że ta wartość jest większa lub równa 14."),
])
def test_the_sellers_details_are_checked(auth_client, shop, field, value, message):
    response = auth_client.patch(f"/api/shops/{shop.pk}/settings/", {"documents": {field: value}}, format="json")

    assert response.status_code == 400
    assert response.data["documents"][field] == [message]


def test_the_documents_are_for_shops_selling_from_poland(auth_client, shop, published,
                                                         django_capture_on_commit_callbacks):
    response = auth_client.patch(f"/api/shops/{shop.pk}/settings/", {
        "region": {"country": "DE"}, "documents": {"managed": True, **SELLER},
    }, format="json")
    assert response.data["documents"]["managed"] == [
        "Wzory regulaminu i polityki prywatności są na razie dla sklepów sprzedających z Polski.",
    ]

    turn_on(auth_client, shop, django_capture_on_commit_callbacks)
    response = auth_client.patch(f"/api/shops/{shop.pk}/settings/", {"region": {"country": "DE"}}, format="json")
    assert response.status_code == 400
    assert "Najpierw wyłącz go w sekcji Regulamin" in response.data["region"]["country"][0]


def test_a_preview_shows_the_documents_without_changing_anything(auth_client, shop, published):
    response = auth_client.post(f"/api/shops/{shop.pk}/documents/preview/", {"documents": SELLER}, format="json")

    assert response.status_code == 200
    terms, privacy = response.data["documents"]
    assert (terms["key"], terms["title"]) == ("terms", "Regulamin sklepu")
    assert terms["blocks"][0] == {"type": "heading", "level": 2, "text": "§ 1. Postanowienia ogólne"}
    assert privacy["title"] == "Polityka prywatności"
    assert published == []
    assert not ShopOperation.objects.filter(shop=shop).exists()
    assert ShopSettings.objects.get(shop=shop).values["documents"]["seller_name"] == ""


def test_a_preview_says_what_is_missing(auth_client, shop):
    response = auth_client.post(f"/api/shops/{shop.pk}/documents/preview/", {"documents": {"city": "Łódź"}},
                                format="json")

    assert response.status_code == 400
    assert set(response.data["documents"]) == {"seller_name", "street", "postal_code", "tax_id"}


def test_a_preview_checks_the_fields(auth_client, shop):
    response = auth_client.post(f"/api/shops/{shop.pk}/documents/preview/",
                                {"documents": {**SELLER, "tax_id": "123"}}, format="json")

    assert response.data["documents"]["tax_id"] == ["NIP ma 10 cyfr."]


def test_only_the_owner_sees_a_preview(api_client, shop, user):
    user.is_email_verified = True
    user.save()
    api_client.force_authenticate(user)

    response = api_client.post(f"/api/shops/{shop.pk}/documents/preview/", {"documents": SELLER}, format="json")

    assert response.status_code == 404


def test_the_terms_name_the_seller_and_how_to_reach_them(shop):
    terms = text(render(documents={"phone": "600 100 200", "regon": "123456785"})["terms"])

    assert "Sklep prowadzi Palarnia Kawy Anna Nowak, ul. Kwiatowa 1/2, 00-001 Łódź, NIP 5260001246, REGON 123456785" \
        in terms
    assert "wpisany do Centralnej Ewidencji i Informacji o Działalności Gospodarczej (CEIDG)" in terms
    assert "telefon 600 100 200" in terms
    assert "https://palarnia.example.com" in terms
    assert "Regulamin obowiązuje od 18 listopada 2026." in terms


@pytest.mark.parametrize(("register", "expected"), [
    ("krs", "wpisany do rejestru przedsiębiorców Krajowego Rejestru Sądowego pod numerem KRS 0000123456"),
    ("unregistered", "Sprzedawca prowadzi działalność nierejestrowaną"),
])
def test_the_terms_say_where_the_seller_is_registered(shop, register, expected):
    assert expected in text(render(documents={"register": register, "krs": "0000123456"})["terms"])


def test_the_terms_list_the_ways_to_pay_and_deliver_the_shop_offers(shop):
    terms = text(render(
        payments={"bank_transfer_enabled": True, "cash_on_delivery_enabled": True, "payu_enabled": True},
        shipping={"courier_enabled": True, "free_shipping_enabled": True, "free_shipping_min_amount": "199.50",
                  "local_pickup_enabled": False},
    )["terms"])

    assert "przelew tradycyjny na rachunek bankowy Sprzedawcy podany przy składaniu Zamówienia;" in terms
    assert "płatności online PayU (m.in. BLIK, szybkie przelewy i karty płatnicze), obsługiwane przez PayU S.A." \
        in terms
    assert "Przelewy24" not in terms
    assert "w terminie 7 dni od złożenia Zamówienia" in terms
    assert "darmowa dostawa przy Zamówieniach o wartości co najmniej 199,50 PLN;" in terms
    assert "odbiór osobisty" not in terms
    assert "a przy płatności przy odbiorze – od zawarcia umowy" in terms
    assert "Ceny Produktów są podane w złotych polskich." in terms


def test_without_methods_the_terms_point_to_the_order_form(shop):
    terms = text(render()["terms"])

    assert "Klient płaci za Zamówienie w sposób wybrany przy jego składaniu." in terms
    assert "Sposoby dostawy i ich koszty są podawane przy składaniu Zamówienia." in terms
    assert "przy płatności przy odbiorze" not in terms


def test_returns_follow_the_sellers_choices(shop):
    standard = text(render()["terms"])
    generous = text(render(documents={"return_days": 30, "free_returns": True, "dispatch_days": 1})["terms"])

    assert "w terminie 14 dni." in standard
    assert "Konsument ponosi bezpośredni koszt zwrotu Produktu." in standard
    assert "w terminie 30 dni (Sprzedawca wydłuża w ten sposób ustawowy termin 14 dni)" in generous
    assert "Koszt zwrotu Produktu pokrywa Sprzedawca." in generous
    assert "w ciągu 1 dnia roboczego" in generous
    assert "w ciągu 2 dni roboczych" in standard


def test_reviews_get_their_paragraph_only_where_the_shop_has_them(shop):
    with_reviews = render(shopping={"reviews": True})["terms"]
    without = render(shopping={"reviews": False})["terms"]

    headings = [block["text"] for block in with_reviews.blocks if block["type"] == "heading"]
    assert "§ 9. Opinie o Produktach" in headings
    assert "§ 12. Postanowienia końcowe" in headings
    headings = [block["text"] for block in without.blocks if block["type"] == "heading"]
    assert not any("Opinie" in heading for heading in headings)
    assert "§ 11. Postanowienia końcowe" in headings


def test_the_terms_end_with_the_withdrawal_form(shop):
    terms = render()["terms"]

    assert terms.blocks[-4] == {"type": "heading", "level": 2, "text": "Wzór formularza odstąpienia od umowy"}
    assert "Adresat: Palarnia Kawy Anna Nowak, ul. Kwiatowa 1/2, 00-001 Łódź, e-mail" in text(terms)


def test_the_privacy_policy_names_who_gets_the_data(shop, settings):
    privacy = text(render(payments={"przelewy24_enabled": True})["privacy"])

    assert "Administratorem danych osobowych jest Palarnia Kawy Anna Nowak" in privacy
    assert "Sklepownia sp. z o.o., Prosta 20, 00-850 Warszawa – dostawcy hostingu" in privacy
    assert "PayPro S.A. z siedzibą w Poznaniu – operatorowi płatności Przelewy24" in privacy
    assert "PayU" not in privacy
    assert "Prezesa Urzędu Ochrony Danych Osobowych" in privacy

    settings.INVOICE_SELLER = {**settings.INVOICE_SELLER, "name": ""}
    assert "dostawcy hostingu i oprogramowania Sklepu" in text(render()["privacy"])


def test_what_the_owner_typed_cannot_break_the_page(shop):
    terms = render(documents={"seller_name": "Palarnia <script>alert(1)</script>"})["terms"]

    assert "<script>" not in terms.html
    assert "Palarnia &lt;script&gt;" in terms.html


def test_the_pages_have_only_plain_markup(shop):
    import re

    for document in render(payments={"bank_transfer_enabled": True}).values():
        assert set(re.findall(r"</?([a-z0-9]+)", document.html)) <= {"h2", "p", "ol", "ul", "li", "strong"}


def test_new_templates_reach_every_shop_with_older_documents(auth_client, shop, published,
                                                             django_capture_on_commit_callbacks):
    turn_on(auth_client, shop, django_capture_on_commit_callbacks)
    ShopSettings.objects.filter(shop=shop).update(values={
        **ShopSettings.objects.get(shop=shop).values,
        "documents": {**ShopSettings.objects.get(shop=shop).values["documents"], "version": "2026-01-01"},
    })

    with django_capture_on_commit_callbacks(execute=True):
        call_command("publish_shop_documents")

    assert len(published) == 2
    operation = ShopOperation.objects.filter(shop=shop).first()
    assert operation.kind == ShopOperation.Kind.PUBLISH_DOCUMENTS
    assert operation.status == ShopOperation.Status.SUCCEEDED
    assert ShopSettings.objects.get(shop=shop).values["documents"]["version"] == documents.VERSION

    # Up to date now: only --all republishes.
    with django_capture_on_commit_callbacks(execute=True):
        call_command("publish_shop_documents")
    assert len(published) == 2
    with django_capture_on_commit_callbacks(execute=True):
        call_command("publish_shop_documents", "--all")
    assert len(published) == 3


def test_shops_without_documents_from_the_app_are_skipped(shop, published, django_capture_on_commit_callbacks):
    services.get_settings(shop)

    with django_capture_on_commit_callbacks(execute=True):
        call_command("publish_shop_documents", "--all")

    assert published == []


def test_published_documents_tick_off_the_checklist(auth_client, shop, published, django_capture_on_commit_callbacks):
    ShopChecklist.objects.create(shop=shop, products=3, sample_products=0)

    def step():
        steps = auth_client.get(f"/api/shops/{shop.pk}/checklist/").data["steps"]
        return next(item["done"] for item in steps if item["key"] == "documents")

    assert step() is False
    turn_on(auth_client, shop, django_capture_on_commit_callbacks)
    assert step() is True
