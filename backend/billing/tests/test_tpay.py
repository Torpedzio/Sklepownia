import base64
import hashlib
import io
import json
import urllib.error
import urllib.parse
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from django.core.cache import cache

from billing.gateways.base import GatewayError, Payer
from billing.gateways.tpay import TpayGateway
from billing.models import Payment, Subscription

pytestmark = pytest.mark.django_db

SANDBOX_CERTS = "https://secure.sandbox.tpay.com"
SIGNING_CERT = f"{SANDBOX_CERTS}/x509/notifications-jws.pem"
ROOT_CERT = f"{SANDBOX_CERTS}/x509/tpay-jws-root.pem"
SECURITY_CODE = "kod-bezpieczenstwa"


def make_certificate(name, key, issuer_name=None, issuer_key=None, ca=False):
    now = datetime.now(UTC)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_name)]) if issuer_name else subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
    )
    return builder.sign(issuer_key or key, hashes.SHA256())


def pem(certificate):
    return certificate.public_bytes(serialization.Encoding.PEM)


@pytest.fixture(scope="module")
def keys():
    root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    root = make_certificate("Tpay test root", root_key, ca=True)
    signing = make_certificate("Tpay notifications", signing_key, "Tpay test root", root_key)
    return {"root": root, "signing": signing, "signing_key": signing_key}


@pytest.fixture
def tpay(settings, keys, monkeypatch):
    settings.PAYMENT_GATEWAY = "billing.gateways.tpay.TpayGateway"
    settings.TPAY_SANDBOX = True
    settings.TPAY_SECURITY_CODE = SECURITY_CODE
    settings.TPAY_CLIENT_ID = "client"
    settings.TPAY_CLIENT_SECRET = "secret"
    settings.TPAY_NOTIFICATION_URL = "https://sklepownia.example/api/billing/notifications/"
    certificates = {SIGNING_CERT: pem(keys["signing"]), ROOT_CERT: pem(keys["root"])}
    monkeypatch.setattr("billing.gateways.tpay._fetch_certificate", lambda url: certificates[url])
    cache.clear()
    return certificates


def jws(body, key, x5u=SIGNING_CERT):
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "x5u": x5u}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(body).rstrip(b"=").decode()
    signature = key.sign(f"{header}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{header}..{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def notification(payment, **overrides):
    fields = {
        "id": "1010", "tr_id": "TR-ABC-123", "tr_date": "2026-11-05 12:00:00", "tr_crc": payment.reference,
        "tr_amount": "49.00", "tr_paid": "49.00", "tr_desc": "Plan", "tr_status": "TRUE", "tr_error": "none",
        "tr_email": "anna@example.com", "test_mode": "1",
        "card_token": "t59c2810d59285e3e0ee9d1f1eda1c2f4c554e24", "card_tail": "1234", "card_brand": "Mastercard",
        "token_expiry_date": "1229",
    }
    fields.update(overrides)
    if "md5sum" not in overrides:
        raw = fields["id"] + fields["tr_id"] + fields["tr_amount"] + fields["tr_crc"] + SECURITY_CODE
        fields["md5sum"] = hashlib.md5(raw.encode()).hexdigest()
    return urllib.parse.urlencode(fields).encode()


@pytest.fixture
def payment(unsubscribed_user, plan):
    subscription = Subscription.objects.create(user=unsubscribed_user, plan=plan)
    return Payment.objects.create(user=unsubscribed_user, subscription=subscription, plan=plan,
                                  kind=Payment.Kind.INITIAL, amount=plan.price, currency="PLN", gateway="tpay",
                                  gateway_id="01K0TRANSACTION")


def post(client, body, signature):
    return client.post("/api/billing/notifications/", body, content_type="application/x-www-form-urlencoded",
                       HTTP_X_JWS_SIGNATURE=signature)


# --- notifications ---


def test_a_signed_notification_activates_the_plan_and_saves_the_card(client, tpay, keys, payment):
    body = notification(payment)

    response = post(client, body, jws(body, keys["signing_key"]))

    assert response.status_code == 200
    assert response.content == b"TRUE"
    payment.refresh_from_db()
    subscription = payment.subscription
    subscription.refresh_from_db()
    assert (payment.status, payment.gateway_title) == (Payment.Status.PAID, "TR-ABC-123")
    assert subscription.status == Subscription.Status.ACTIVE
    assert subscription.card_token == "t59c2810d59285e3e0ee9d1f1eda1c2f4c554e24"
    assert (subscription.card_brand, subscription.card_tail, subscription.card_expiry) == ("Mastercard", "1234", "1229")


def test_a_repeated_notification_changes_nothing(client, tpay, keys, payment):
    body = notification(payment)
    post(client, body, jws(body, keys["signing_key"]))
    end = Subscription.objects.get(pk=payment.subscription_id).current_period_end

    assert post(client, body, jws(body, keys["signing_key"])).content == b"TRUE"
    assert Subscription.objects.get(pk=payment.subscription_id).current_period_end == end


def test_a_chargeback_notification_does_not_activate(client, tpay, keys, payment):
    body = notification(payment, tr_status="chargeback")

    post(client, body, jws(body, keys["signing_key"]))

    payment.refresh_from_db()
    assert payment.status == Payment.Status.FAILED


def forged_signature(body, keys):
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return jws(body, other_key)


@pytest.mark.parametrize("forgery", ["tampered_body", "other_key", "foreign_certificate_url", "no_signature",
                                     "bad_md5", "not_from_tpay_root"])
def test_forged_notifications_are_rejected(client, tpay, keys, payment, forgery):
    body = notification(payment)
    signature = jws(body, keys["signing_key"])
    if forgery == "tampered_body":
        body = notification(payment, tr_paid="4900.00")
    elif forgery == "other_key":
        signature = forged_signature(body, keys)
    elif forgery == "foreign_certificate_url":
        signature = jws(body, keys["signing_key"], x5u="https://evil.example/x509/notifications-jws.pem")
    elif forgery == "no_signature":
        signature = ""
    elif forgery == "bad_md5":
        body = notification(payment, md5sum="0" * 32)
        signature = jws(body, keys["signing_key"])
    elif forgery == "not_from_tpay_root":
        rogue_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        tpay[SIGNING_CERT] = pem(make_certificate("Rogue", rogue_key))
        signature = jws(body, rogue_key)

    response = post(client, body, signature)

    assert response.status_code == 400
    payment.refresh_from_db()
    assert payment.status == Payment.Status.PENDING


def test_production_takes_certificates_only_from_production(client, tpay, keys, payment, settings):
    settings.TPAY_SANDBOX = False
    body = notification(payment)

    assert post(client, body, jws(body, keys["signing_key"])).status_code == 400


# --- API calls ---


class FakeTpayApi:
    """Stands in for urllib.request.urlopen: records requests, answers by "METHOD path"."""

    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def __call__(self, request, timeout=None):
        path = urllib.parse.urlparse(request.full_url).path
        key = f"{request.get_method()} {path}"
        body = request.data.decode() if request.data else None
        self.requests.append({"key": key, "url": request.full_url, "headers": dict(request.header_items()),
                              "body": body})
        answer = self.responses[key]
        if isinstance(answer, tuple):
            status, data = answer
            raise urllib.error.HTTPError(request.full_url, status, "error", {}, io.BytesIO(json.dumps(data).encode()))
        return io.BytesIO(json.dumps(answer).encode())

    def sent(self, key):
        return [json.loads(r["body"]) for r in self.requests if r["key"] == key]


AUTH = {"access_token": "token-1", "expires_in": 7200}


@pytest.fixture
def api(monkeypatch):
    def install(responses):
        fake = FakeTpayApi({"POST /oauth/auth": AUTH, **responses})
        monkeypatch.setattr("billing.gateways.tpay.urllib.request.urlopen", fake)
        return fake
    return install


PAYER = Payer(email="anna@example.com", name="Palarnia sp. z o.o.", street="Kwiatowa 1", postal_code="00-001",
              city="Warszawa", tax_id="5260001246")


def test_first_payment_saves_the_card_and_returns_the_payment_page(tpay, api, payment):
    fake = api({"POST /transactions": {"result": "success", "transactionId": "01K0", "title": "TR-1",
                                       "transactionPaymentUrl": "https://secure.sandbox.tpay.com/?title=TR-1"}})

    checkout = TpayGateway().start_payment(payment, PAYER, return_url="mobile://billing/return", site_url="")

    assert checkout.redirect_url == "https://secure.sandbox.tpay.com/?title=TR-1"
    assert (checkout.gateway_id, checkout.title) == ("01K0", "TR-1")
    [sent] = fake.sent("POST /transactions")
    assert sent["amount"] == 49.0
    assert sent["hiddenDescription"] == payment.reference
    assert sent["pay"] == {"groupId": 103, "cardPaymentData": {"save": 1}}
    assert sent["payer"] == {"email": "anna@example.com", "name": "Palarnia sp. z o.o.", "address": "Kwiatowa 1",
                             "code": "00-001", "city": "Warszawa", "country": "PL", "taxId": "5260001246"}
    assert sent["callbacks"] == {
        "notification": {"url": "https://sklepownia.example/api/billing/notifications/"},
        "payerUrls": {"success": "mobile://billing/return", "error": "mobile://billing/return"},
    }
    assert fake.requests[0]["url"] == "https://openapi.sandbox.tpay.com/oauth/auth"
    assert fake.requests[1]["headers"]["Authorization"] == "Bearer token-1"
    # Without its own agent the request is blocked by Cloudflare in front of Tpay.
    assert all(request["headers"]["User-agent"].startswith("Sklepownia/") for request in fake.requests)


def test_the_access_token_is_reused(tpay, api, payment):
    fake = api({"POST /transactions": {"transactionId": "01K0", "transactionPaymentUrl": "https://x"}})

    gateway = TpayGateway()
    gateway.start_payment(payment, PAYER, return_url="mobile://r", site_url="")
    gateway.start_payment(payment, PAYER, return_url="mobile://r", site_url="")

    assert [r["key"] for r in fake.requests].count("POST /oauth/auth") == 1


@pytest.mark.parametrize(("answer", "paid"), [
    ({"result": "success", "status": "correct"}, True),
    ({"result": "success", "status": "pending"}, None),
    ((400, {"result": "failure", "errors": [{"errorMessage": "declined"}]}), False),
])
def test_renewal_charges_the_token_as_a_recurring_payment(tpay, api, payment, answer, paid):
    fake = api({
        "POST /transactions": {"transactionId": "01K1", "title": "TR-2", "transactionPaymentUrl": "https://x"},
        "POST /transactions/01K1/pay": answer,
    })

    result = TpayGateway().charge_saved_card(payment, PAYER, "tok-saved")

    assert result.paid is paid
    assert (result.gateway_id, result.title) == ("01K1", "TR-2")
    assert fake.sent("POST /transactions/01K1/pay") == [
        {"groupId": 103, "cardPaymentData": {"token": "tok-saved"}, "cof": "recurring"},
    ]
    # No card saving and no payer pages for a charge without the payer.
    [created] = fake.sent("POST /transactions")
    assert created["pay"] == {"groupId": 103}
    assert "payerUrls" not in created["callbacks"]


@pytest.mark.parametrize("status", ["correct", "paid"])
def test_asking_about_a_payment(tpay, api, payment, status):
    api({"GET /transactions/01K0TRANSACTION": {"status": status, "amountPaid": 49, "title": "TR-9"}})

    result = TpayGateway().fetch_result(payment)

    assert (result.paid, result.amount, result.title) == (True, Decimal("49.00"), "TR-9")


def test_an_unpaid_payment_has_no_result_yet(tpay, api, payment):
    api({"GET /transactions/01K0TRANSACTION": {"status": "pending"}})

    assert TpayGateway().fetch_result(payment) is None


def test_gateway_errors_say_what_failed(tpay, api, payment):
    api({"POST /transactions": (500, {"result": "failure"})})

    with pytest.raises(GatewayError, match="returned 500"):
        TpayGateway().start_payment(payment, PAYER, return_url="mobile://r", site_url="")


def test_checkout_reports_an_unreachable_gateway(api_client, unsubscribed_user, tpay, api):
    api({"POST /transactions": (503, {"result": "failure"})})
    api_client.force_authenticate(unsubscribed_user)
    api_client.put("/api/billing/profile/", {"kind": "company", "full_name": "Anna", "company_name": "Firma",
                                             "tax_id": "5260001246", "street": "Ulica 1", "postal_code": "00-001",
                                             "city": "Warszawa"}, format="json")

    response = api_client.post("/api/billing/checkout/", {"plan": "standard", "return_url": "mobile://r",
                                                          "accept_terms": True}, format="json")

    assert response.status_code == 502
    assert Payment.objects.get().status == Payment.Status.FAILED


def test_the_return_screen_asks_tpay_when_notifications_are_late(api_client, unsubscribed_user, tpay, api, payment):
    api({"GET /transactions/01K0TRANSACTION": {"status": "correct", "amountPaid": "49.00", "title": "TR-9"}})
    api_client.force_authenticate(unsubscribed_user)

    response = api_client.get(f"/api/billing/payments/{payment.pk}/")

    assert response.data["status"] == "paid"


def test_the_payer_comes_back_to_the_screen_of_this_payment(api_client, unsubscribed_user, tpay, api):
    fake = api({"POST /transactions": {"transactionId": "01K0", "title": "TR-1", "transactionPaymentUrl": "https://x"}})
    api_client.force_authenticate(unsubscribed_user)
    api_client.put("/api/billing/profile/", {"kind": "company", "full_name": "Anna", "company_name": "Firma",
                                             "tax_id": "5260001246", "street": "Ulica 1", "postal_code": "00-001",
                                             "city": "Warszawa"}, format="json")

    response = api_client.post("/api/billing/checkout/", {
        "plan": "standard", "return_url": "http://localhost:8081/billing/return", "accept_terms": True,
    }, format="json")

    payment_id = response.data["payment"]["id"]
    [sent] = fake.sent("POST /transactions")
    expected = f"http://localhost:8081/billing/return?payment={payment_id}"
    assert sent["callbacks"]["payerUrls"] == {"success": expected, "error": expected}
