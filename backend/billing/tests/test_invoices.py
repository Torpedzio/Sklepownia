import io
import json
import urllib.error
import urllib.parse
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from billing import invoices, services
from billing.invoicing import tax
from billing.models import BillingProfile, Invoice, InvoiceSequence, Payment, Plan, Subscription
from conftest import subscribe

pytestmark = pytest.mark.django_db

RETURN_URL = "http://localhost:8081/billing/return"
PERSON = {
    "kind": "individual", "full_name": "Anna Nowak", "street": "Kwiatowa 1", "postal_code": "00-001", "city": "Warszawa",
}
COMPANY = {**PERSON, "kind": "company", "company_name": "Palarnia sp. z o.o.", "tax_id": "PL 526-000-12-46"}
GERMAN_COMPANY = {**COMPANY, "company_name": "Rösterei GmbH", "tax_id": "DE123456789", "postal_code": "10115",
                  "city": "Berlin", "country": "DE"}


@pytest.fixture
def client(api_client, unsubscribed_user):
    api_client.force_authenticate(unsubscribed_user)
    return api_client


def pay(client, captured, details=PERSON):
    """Fills in invoice details and pays for Standard on the fake gateway's page."""
    assert client.put("/api/billing/profile/", details, format="json").status_code == 200
    with captured(execute=True):
        response = client.post("/api/billing/checkout/", {
            "plan": "standard", "return_url": RETURN_URL, "accept_terms": True, "immediate_start_consent": True,
        }, format="json")
    payment_id = response.data["payment"]["id"]
    with captured(execute=True):
        client.post(f"/api/billing/fake-gateway/{payment_id}/", {"action": "pay"})
    return Payment.objects.get(pk=payment_id)


def invoice_mails(mailoutbox):
    return [message for message in mailoutbox if message.subject.startswith("Faktura ")]


def this_month_number(number):
    today = timezone.localdate()
    return f"FV/{today:%Y}/{today:%m}/{number:04}"


# --- issued by the platform ---


def test_a_paid_plan_gets_an_invoice_by_email_and_in_the_app(client, django_capture_on_commit_callbacks, mailoutbox):
    payment = pay(client, django_capture_on_commit_callbacks)

    invoice = Invoice.objects.get(payment=payment)
    assert (invoice.status, invoice.issuer, invoice.number) == ("issued", "platform", this_month_number(1))
    assert (invoice.net, invoice.vat, invoice.gross, invoice.vat_rate) == (
        Decimal("39.84"), Decimal("9.16"), Decimal("49.00"), "23")
    assert invoice.issue_date == invoice.sale_date == timezone.localdate()
    assert invoice.item.startswith("Abonament Sklepownia, plan Standard, okres ")
    assert invoice.buyer["full_name"] == "Anna Nowak"
    assert invoice.seller["tax_id"] == "5260001246"
    assert bytes(invoice.pdf).startswith(b"%PDF")
    assert invoice.sent_at is not None

    [message] = invoice_mails(mailoutbox)
    assert message.subject == f"Faktura {invoice.number}"
    assert message.to == ["anna@example.com"]
    assert "49,00 PLN" in message.body
    filename = f"Faktura-FV-{timezone.localdate():%Y-%m}-0001.pdf"
    assert message.attachments == [(filename, bytes(invoice.pdf), "application/pdf")]
    paid = next(message for message in mailoutbox if message.subject == "Plan Standard jest aktywny")
    assert "Fakturę wyślemy w osobnej wiadomości." in paid.body

    listed = client.get("/api/billing/").data["payments"][0]["invoice"]
    assert (listed["number"], listed["gross"], listed["ready"], listed["ksef_number"]) == (
        invoice.number, "49.00", True, "")
    document = client.get(listed["url"])
    assert document.status_code == 200
    assert document["Content-Type"] == "application/pdf"
    assert document["Content-Disposition"] == f'inline; filename="{filename}"'
    assert document.content == bytes(invoice.pdf)


def test_invoice_links_are_signed_and_expire(client, django_capture_on_commit_callbacks, monkeypatch):
    invoice = pay(client, django_capture_on_commit_callbacks).invoice
    url = client.get("/api/billing/").data["payments"][0]["invoice"]["url"]
    token = url.rstrip("/").rsplit("/", 1)[1]

    assert client.get(f"/api/billing/invoices/{token[:-2]}xx/").status_code == 404
    assert client.get(f"/api/billing/invoices/{invoice.pk}/").status_code == 404
    monkeypatch.setattr(invoices, "LINK_MAX_AGE", -1)
    assert client.get(url).status_code == 404


def test_a_company_invoice_carries_its_nip(client, django_capture_on_commit_callbacks):
    invoice = pay(client, django_capture_on_commit_callbacks, COMPANY).invoice

    assert (invoice.buyer["company_name"], invoice.buyer["tax_id"]) == ("Palarnia sp. z o.o.", "5260001246")
    assert (invoice.vat_rate, invoice.vat) == ("23", Decimal("9.16"))


def test_a_company_from_abroad_pays_no_polish_vat(client, django_capture_on_commit_callbacks):
    invoice = pay(client, django_capture_on_commit_callbacks, GERMAN_COMPANY).invoice

    assert (invoice.vat_rate, invoice.net, invoice.vat, invoice.gross) == (
        "np", Decimal("49.00"), Decimal("0.00"), Decimal("49.00"))
    assert tax.notes(invoice) == ["Odwrotne obciążenie: VAT rozlicza nabywca."]


@pytest.mark.parametrize("buyer, rate, note", [
    ({"kind": "individual", "country": "DE"}, "23", None),
    ({"kind": "company", "country": "PL"}, "23", None),
    ({"kind": "company", "country": "US"}, "np", "art. 28b"),
])
def test_vat_by_buyer(buyer, rate, note):
    assert tax.rate_for(buyer, Decimal("23.00")) == rate
    invoice = Invoice(buyer=buyer, vat_rate=rate)
    assert (note in " ".join(tax.notes(invoice))) if note else tax.notes(invoice) == []


@pytest.mark.parametrize("gross, net, vat", [
    ("49.00", "39.84", "9.16"), ("29.00", "23.58", "5.42"), ("0.01", "0.01", "0.00"), ("25.00", "20.33", "4.67"),
])
def test_vat_is_split_off_the_gross_amount(gross, net, vat):
    assert tax.split(Decimal(gross), "23") == (Decimal(net), Decimal(vat))


def test_numbers_follow_each_other_and_start_over_every_month():
    from billing.invoicing.platform import next_number

    assert [next_number(date(2026, 11, day)) for day in (1, 15, 30)] == [
        "FV/2026/11/0001", "FV/2026/11/0002", "FV/2026/11/0003"]
    assert next_number(date(2026, 12, 1)) == "FV/2026/12/0001"
    assert next_number(date(2026, 11, 30)) == "FV/2026/11/0004"


def test_renewals_are_invoiced_for_what_the_card_paid(unsubscribed_user, django_capture_on_commit_callbacks,
                                                      mailoutbox):
    start = Plan.objects.get(code="start")
    BillingProfile.objects.create(user=unsubscribed_user, **PERSON)
    subscribe(unsubscribed_user, start, current_period_end=timezone.now() - timedelta(minutes=1),
              credit=Decimal("10.00"))

    with django_capture_on_commit_callbacks(execute=True):
        services.renew_due()

    invoice = Invoice.objects.get(payment__user=unsubscribed_user)
    assert (invoice.gross, invoice.item.startswith("Abonament Sklepownia, plan Start")) == (Decimal("19.00"), True)
    assert len(invoice_mails(mailoutbox)) == 1


def test_a_renewal_paid_from_the_balance_has_no_invoice(unsubscribed_user, django_capture_on_commit_callbacks):
    subscribe(unsubscribed_user, Plan.objects.get(code="start"),
              current_period_end=timezone.now() - timedelta(minutes=1), credit=Decimal("40.00"), card_token="")

    with django_capture_on_commit_callbacks(execute=True):
        services.renew_due()

    assert Payment.objects.get(user=unsubscribed_user).status == Payment.Status.PAID
    assert not Invoice.objects.exists()


def test_an_upgrade_surcharge_is_invoiced(auth_client, verified_user, django_capture_on_commit_callbacks, mailoutbox):
    BillingProfile.objects.create(user=verified_user, **PERSON)
    now = timezone.now()
    Subscription.objects.filter(user=verified_user).update(
        current_period_start=now - timedelta(days=15), current_period_end=now + timedelta(days=15),
    )
    with django_capture_on_commit_callbacks(execute=True):
        payment_id = auth_client.post("/api/billing/subscription/change/",
                                      {"plan": "business", "return_url": RETURN_URL}, format="json").data["payment"]["id"]
    with django_capture_on_commit_callbacks(execute=True):
        auth_client.post(f"/api/billing/fake-gateway/{payment_id}/", {"action": "pay"})

    invoice = Invoice.objects.get(payment_id=payment_id)
    assert invoice.item.startswith("Dopłata za zmianę na plan Biznes w Sklepownia, okres ")
    assert invoice.gross == Decimal("25.00")
    changed = next(message for message in mailoutbox if message.subject == "Zmieniliśmy plan na Biznes")
    assert "Fakturę za dopłatę wyślemy w osobnej wiadomości." in changed.body
    [mail] = invoice_mails(mailoutbox)
    assert "dopłatę do planu Biznes" in mail.body


# --- when issuing fails ---


def test_without_seller_details_the_invoice_waits_and_is_tried_again(
    client, settings, django_capture_on_commit_callbacks, mailoutbox,
):
    complete = settings.INVOICE_SELLER
    settings.INVOICE_SELLER = {**complete, "name": "", "tax_id": ""}
    payment = pay(client, django_capture_on_commit_callbacks)

    invoice = Invoice.objects.get(payment=payment)
    assert (invoice.status, invoice.number, invoice.attempts) == ("pending", "", 1)
    assert "INVOICE_SELLER_NAME, INVOICE_SELLER_TAX_ID" in invoice.error
    assert not invoice_mails(mailoutbox)
    assert client.get("/api/billing/").data["payments"][0]["invoice"] == {
        "number": "", "issue_date": None, "gross": "49.00", "currency": "PLN", "ksef_number": "", "ready": False,
        "url": None,
    }

    settings.INVOICE_SELLER = complete
    invoices.process(now=timezone.now())
    assert Invoice.objects.get(pk=invoice.pk).status == "pending"

    with django_capture_on_commit_callbacks(execute=True):
        invoices.process(now=timezone.now() + timedelta(minutes=6))

    invoice.refresh_from_db()
    assert (invoice.status, invoice.number, invoice.error, invoice.attempts) == ("issued", this_month_number(1), "", 0)
    assert len(invoice_mails(mailoutbox)) == 1


def test_a_failed_attempt_gives_its_number_back(client, monkeypatch, django_capture_on_commit_callbacks):
    def broken(*args, **kwargs):
        raise RuntimeError("PDF się nie udał")

    monkeypatch.setattr("billing.invoicing.platform.render", broken)
    payment = pay(client, django_capture_on_commit_callbacks)

    invoice = Invoice.objects.get(payment=payment)
    assert (invoice.status, invoice.number, invoice.error) == ("pending", "", "PDF się nie udał")
    assert not InvoiceSequence.objects.filter(last__gt=0).exists()

    monkeypatch.undo()
    assert invoices.issue(invoice.pk).number == this_month_number(1)


def test_retries_wait_longer_and_longer():
    assert [invoices._retry_delay(attempts) for attempts in (1, 2, 3, 8, 14)] == [
        timedelta(minutes=5), timedelta(minutes=10), timedelta(minutes=20), timedelta(hours=6), timedelta(hours=6)]


def test_invoices_that_never_left_are_emailed_later(client, django_capture_on_commit_callbacks, mailoutbox):
    invoice = pay(client, django_capture_on_commit_callbacks).invoice
    mailoutbox.clear()
    Invoice.objects.filter(pk=invoice.pk).update(sent_at=None, issued_at=timezone.now() - timedelta(minutes=5))

    invoices.process()
    assert not mailoutbox

    invoices.process(now=timezone.now() + timedelta(minutes=6))
    assert len(invoice_mails(mailoutbox)) == 1
    invoices.process(now=timezone.now() + timedelta(minutes=6))
    assert len(invoice_mails(mailoutbox)) == 1


def test_a_deleted_account_gets_no_invoice_email(client, unsubscribed_user, django_capture_on_commit_callbacks,
                                                 mailoutbox):
    invoice = pay(client, django_capture_on_commit_callbacks).invoice
    Invoice.objects.filter(pk=invoice.pk).update(sent_at=None)
    mailoutbox.clear()
    unsubscribed_user.is_active = False
    unsubscribed_user.save()

    assert invoices.deliver(invoice.pk) is False
    assert not mailoutbox


def test_the_admin_sees_the_pdf(admin_client, client, django_capture_on_commit_callbacks):
    invoice = pay(client, django_capture_on_commit_callbacks).invoice

    assert admin_client.get("/admin/billing/invoice/").status_code == 200
    assert invoice.filename in admin_client.get(f"/admin/billing/invoice/{invoice.pk}/change/").content.decode()
    document = admin_client.get(f"/admin/billing/invoice/{invoice.pk}/pdf/")
    assert (document.status_code, document.content) == (200, bytes(invoice.pdf))


# --- issued in Fakturownia ---


class FakeFakturownia:
    """Stands in for urllib.request.urlopen: records requests, answers by "METHOD path?query"."""

    def __init__(self):
        self.requests = []
        self.answers = {}

    def __call__(self, request, timeout):
        url = urllib.parse.urlsplit(request.full_url)
        key = f"{request.get_method()} {url.path}" + (f"?{url.query}" if url.query else "")
        self.requests.append({
            "key": key, "host": url.hostname, "body": json.loads(request.data) if request.data else None,
            "authorization": request.get_header("Authorization"),
        })
        answer = self.answers[key]
        if isinstance(answer, Exception):
            raise answer
        return io.BytesIO(answer if isinstance(answer, bytes) else json.dumps(answer).encode())

    def sent(self, key):
        return [request for request in self.requests if request["key"] == key]


@pytest.fixture
def fakturownia(settings, monkeypatch):
    settings.INVOICE_ISSUER = "billing.invoicing.fakturownia.FakturowniaIssuer"
    settings.FAKTUROWNIA_DOMAIN = "firma"
    settings.FAKTUROWNIA_API_TOKEN = "tajny-token"
    settings.FAKTUROWNIA_KSEF = True
    fake = FakeFakturownia()
    fake.answers["GET /invoices/555.pdf"] = b"%PDF-fakturownia"
    monkeypatch.setattr("billing.invoicing.fakturownia.urllib.request.urlopen", fake)
    return fake


def created(gov_status=None, **fields):
    return {"id": 555, "number": "FV 7/11/2026", "issue_date": timezone.localdate().isoformat(),
            "seller_name": "Moja Firma", "seller_tax_no": "1234563218", "seller_street": "Długa 5",
            "seller_post_code": "30-001", "seller_city": "Kraków", "gov_status": gov_status, **fields}


def test_a_company_invoice_goes_through_ksef_before_the_payer_gets_it(
    client, fakturownia, django_capture_on_commit_callbacks, mailoutbox,
):
    fakturownia.answers["POST /invoices.json"] = created("demo_processing")
    payment = pay(client, django_capture_on_commit_callbacks, COMPANY)

    [request] = fakturownia.sent("POST /invoices.json")
    assert (request["host"], request["authorization"]) == ("firma.fakturownia.pl", "Bearer tajny-token")
    assert request["body"]["gov_save_and_send"] is True
    sent = request["body"]["invoice"]
    assert {key: sent[key] for key in ("kind", "status", "paid", "payment_type", "oid", "oid_unique", "buyer_company",
                                       "buyer_name", "buyer_tax_no", "buyer_post_code", "buyer_country")} == {
        "kind": "vat", "status": "paid", "paid": "49.00", "payment_type": "card", "oid": f"payment-{payment.pk}",
        "oid_unique": "yes", "buyer_company": True, "buyer_name": "Palarnia sp. z o.o.", "buyer_tax_no": "5260001246",
        "buyer_post_code": "00-001", "buyer_country": "PL",
    }
    assert sent["positions"] == [{"name": Invoice.objects.get().item, "tax": 23, "total_price_gross": "49.00",
                                  "quantity": 1, "quantity_unit": "usł."}]

    invoice = Invoice.objects.get(payment=payment)
    assert (invoice.status, invoice.issuer, invoice.number, invoice.external_id, invoice.ksef_status) == (
        "issued", "fakturownia", "FV 7/11/2026", "555", "sending")
    assert invoice.seller["name"] == "Moja Firma"
    assert not invoice_mails(mailoutbox)
    assert client.get("/api/billing/").data["payments"][0]["invoice"]["ready"] is False

    fakturownia.answers["GET /invoices/555.json"] = created("demo_processing")
    invoices.process()
    assert Invoice.objects.get(pk=invoice.pk).ksef_status == "sending"

    fakturownia.answers["GET /invoices/555.json"] = created("demo_ok", gov_id="1234563218-20261118-ABC123")
    fakturownia.answers["GET /invoices/555.pdf"] = b"%PDF-z-kodem-ksef"
    with django_capture_on_commit_callbacks(execute=True):
        invoices.process()

    invoice.refresh_from_db()
    assert (invoice.ksef_status, invoice.ksef_number, bytes(invoice.pdf)) == (
        "accepted", "1234563218-20261118-ABC123", b"%PDF-z-kodem-ksef")
    [message] = invoice_mails(mailoutbox)
    assert "Numer KSeF: 1234563218-20261118-ABC123" in message.body
    assert message.attachments[0][1] == b"%PDF-z-kodem-ksef"


def test_a_person_s_invoice_skips_ksef_and_leaves_at_once(
    client, fakturownia, django_capture_on_commit_callbacks, mailoutbox,
):
    fakturownia.answers["POST /invoices.json"] = created(None)
    pay(client, django_capture_on_commit_callbacks)

    [request] = fakturownia.sent("POST /invoices.json")
    assert "gov_save_and_send" not in request["body"]
    sent = request["body"]["invoice"]
    assert (sent["buyer_company"], sent["buyer_first_name"], sent["buyer_last_name"]) == (False, "Anna", "Nowak")
    assert "buyer_tax_no" not in sent
    assert Invoice.objects.get().ksef_status == ""
    [message] = invoice_mails(mailoutbox)
    assert message.attachments[0][1] == b"%PDF-fakturownia"


def test_a_company_from_abroad_is_sent_without_polish_vat(client, fakturownia, django_capture_on_commit_callbacks):
    fakturownia.answers["POST /invoices.json"] = created("processing")
    pay(client, django_capture_on_commit_callbacks, GERMAN_COMPANY)

    sent = fakturownia.sent("POST /invoices.json")[0]["body"]["invoice"]
    assert (sent["buyer_tax_no"], sent["buyer_tax_no_kind"], sent["positions"][0]["tax"]) == (
        "DE123456789", "nip_ue", "np")
    assert sent["description"] == "Odwrotne obciążenie: VAT rozlicza nabywca."


def test_ksef_rejection_waits_for_the_admin(client, fakturownia, django_capture_on_commit_callbacks, mailoutbox,
                                            caplog):
    fakturownia.answers["POST /invoices.json"] = created("processing")
    payment = pay(client, django_capture_on_commit_callbacks, COMPANY)
    fakturownia.answers["GET /invoices/555.json"] = created(
        "send_error", gov_error_messages=["Nieprawidłowy NIP nabywcy", "Brak adresu"])

    invoices.process()

    invoice = Invoice.objects.get(payment=payment)
    assert (invoice.ksef_status, invoice.error) == ("rejected", "Nieprawidłowy NIP nabywcy; Brak adresu")
    assert "KSeF did not accept invoice" in caplog.text
    assert not invoice_mails(mailoutbox)
    invoices.process()
    assert len(fakturownia.sent("GET /invoices/555.json")) == 1


def test_ksef_server_errors_are_sent_again_three_times(client, fakturownia, django_capture_on_commit_callbacks):
    fakturownia.answers["POST /invoices.json"] = created("processing")
    payment = pay(client, django_capture_on_commit_callbacks, COMPANY)
    fakturownia.answers["GET /invoices/555.json"] = created("server_error")
    fakturownia.answers["GET /invoices/555.json?send_to_ksef=yes"] = created("processing")

    for _ in range(4):
        invoices.process()

    invoice = Invoice.objects.get(payment=payment)
    assert len(fakturownia.sent("GET /invoices/555.json?send_to_ksef=yes")) == 3
    assert (invoice.ksef_status, invoice.attempts) == ("rejected", 3)


def test_a_company_invoice_without_ksef_connected_is_held(client, fakturownia, django_capture_on_commit_callbacks,
                                                          mailoutbox):
    fakturownia.answers["POST /invoices.json"] = created("not_connected")
    pay(client, django_capture_on_commit_callbacks, COMPANY)

    invoice = Invoice.objects.get()
    assert (invoice.status, invoice.ksef_status) == ("issued", "rejected")
    assert "nie jest połączone z KSeF" in invoice.error
    assert not invoice_mails(mailoutbox)


def test_fakturownia_refusing_the_invoice_leaves_it_pending(client, fakturownia, django_capture_on_commit_callbacks):
    fakturownia.answers["POST /invoices.json"] = urllib.error.HTTPError(
        "https://firma.fakturownia.pl/invoices.json", 422, "Unprocessable Entity", {},
        io.BytesIO('{"buyer_tax_no": ["- nie może być puste"]}'.encode()),
    )
    payment = pay(client, django_capture_on_commit_callbacks, COMPANY)

    invoice = Invoice.objects.get(payment=payment)
    assert (invoice.status, invoice.attempts) == ("pending", 1)
    assert invoice.error.startswith("Fakturownia POST /invoices.json: 422")
    assert "nie może być puste" in invoice.error


def test_fakturownia_needs_its_keys(client, fakturownia, settings, django_capture_on_commit_callbacks):
    settings.FAKTUROWNIA_API_TOKEN = ""
    payment = pay(client, django_capture_on_commit_callbacks)

    assert Invoice.objects.get(payment=payment).error == "Brak FAKTUROWNIA_DOMAIN albo FAKTUROWNIA_API_TOKEN."
    assert not fakturownia.requests


def test_only_the_issuer_that_sent_it_asks_ksef(client, fakturownia, settings, django_capture_on_commit_callbacks):
    fakturownia.answers["POST /invoices.json"] = created("processing")
    payment = pay(client, django_capture_on_commit_callbacks, COMPANY)
    settings.INVOICE_ISSUER = "billing.invoicing.platform.PlatformIssuer"

    invoices.process()

    assert Invoice.objects.get(payment=payment).ksef_status == "sending"
    assert not fakturownia.sent("GET /invoices/555.json")
