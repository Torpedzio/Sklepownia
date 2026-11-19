"""
Tpay Open API (https://docs-api.tpay.com).
- First payment: POST /transactions with pay.groupId 103 and pay.cardPaymentData.save; the card token comes in
  the notification (card_token).
- Renewal: POST /transactions, then POST /transactions/{id}/pay with the token and cof "recurring".
- Notifications: form posts checked by md5sum (merchant security code) and X-JWS-Signature (Tpay's root CA).
"""

import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from django.conf import settings
from django.core.cache import cache

from .base import BaseGateway, Checkout, GatewayError, InvalidNotification, PaymentResult, SavedCard

API_URL = {True: "https://openapi.sandbox.tpay.com", False: "https://api.tpay.com"}
# Where notification signing certificates may come from.
CERTIFICATES_URL = {True: "https://secure.sandbox.tpay.com", False: "https://secure.tpay.com"}
CARD_GROUP = 103
# Tpay sits behind Cloudflare, which refuses urllib's default "Python-urllib" agent (error 1010).
USER_AGENT = "Sklepownia/1.0 (+billing)"
TIMEOUT = 20
CERTIFICATE_CACHE_SECONDS = 2 * 60 * 60


class TpayGateway(BaseGateway):
    name = "tpay"

    def __init__(self):
        self.sandbox = settings.TPAY_SANDBOX
        self.api_url = API_URL[self.sandbox]

    # --- payments ---

    def start_payment(self, payment, payer, *, return_url, site_url):
        transaction = self._create_transaction(payment, payer, return_url=return_url, save_card=True)
        return Checkout(
            gateway_id=transaction["transactionId"],
            title=transaction.get("title", ""),
            redirect_url=transaction["transactionPaymentUrl"],
        )

    def charge_saved_card(self, payment, payer, card_token):
        transaction = self._create_transaction(payment, payer)
        result = self._call(
            "POST",
            f"/transactions/{transaction['transactionId']}/pay",
            {"groupId": CARD_GROUP, "cardPaymentData": {"token": card_token}, "cof": "recurring"},
            accept_errors=True,
        )
        paid = None
        if result.get("status") == "correct":
            paid = True
        elif result.get("result") != "success":
            paid = False
        return PaymentResult(
            reference=payment.reference,
            paid=paid,
            amount=payment.amount if paid else None,
            gateway_id=transaction["transactionId"],
            title=transaction.get("title", ""),
            error="" if paid is not False else "Bank odrzucił płatność zapisaną kartą.",
        )

    def fetch_result(self, payment):
        if not payment.gateway_id:
            return None
        transaction = self._call("GET", f"/transactions/{payment.gateway_id}")
        # "correct": paid and credited; "paid": paid, crediting still in progress. Both mean the payer paid.
        if transaction.get("status") in ("correct", "paid"):
            return PaymentResult(
                reference=payment.reference,
                paid=True,
                amount=_amount(transaction.get("amountPaid") or transaction.get("amount")),
                gateway_id=payment.gateway_id,
                title=transaction.get("title", ""),
            )
        return None

    def _create_transaction(self, payment, payer, *, return_url=None, save_card=False):
        body = {
            "amount": float(payment.amount),
            "description": f"{settings.PLATFORM_NAME}: plan {payment.plan.name}",
            "hiddenDescription": payment.reference,
            "lang": "pl",
            "payer": _payer(payer),
            "callbacks": {"notification": {"url": settings.TPAY_NOTIFICATION_URL}},
            "pay": {"groupId": CARD_GROUP, **({"cardPaymentData": {"save": 1}} if save_card else {})},
        }
        if return_url:
            body["callbacks"]["payerUrls"] = {"success": return_url, "error": return_url}
        transaction = self._call("POST", "/transactions", body)
        if not transaction.get("transactionId"):
            raise GatewayError(f"Tpay did not create a transaction: {transaction}")
        return transaction

    # --- notifications ---

    def parse_notification(self, request):
        body = request.body
        verify_jws(request.headers.get("X-JWS-Signature", ""), body, CERTIFICATES_URL[self.sandbox])
        fields = {key: values[0] for key, values in urllib.parse.parse_qs(body.decode()).items()}
        if "tr_id" not in fields:
            raise InvalidNotification("Not a transaction notification.")
        expected = hashlib.md5(
            (fields.get("id", "") + fields["tr_id"] + _md5_amount(fields.get("tr_amount"))
             + fields.get("tr_crc", "") + settings.TPAY_SECURITY_CODE).encode(),
        ).hexdigest()
        if not hmac.compare_digest(expected, fields.get("md5sum", "")):
            raise InvalidNotification("md5sum does not match.")
        card = None
        if fields.get("card_token"):
            card = SavedCard(
                token=fields["card_token"],
                brand=fields.get("card_brand", ""),
                tail=fields.get("card_tail", ""),
                expiry=fields.get("token_expiry_date", ""),
            )
        return PaymentResult(
            reference=fields.get("tr_crc", ""),
            paid=fields.get("tr_status", "").lower() == "true",
            amount=_amount(fields.get("tr_paid")),
            title=fields["tr_id"],
            card=card,
        )

    # --- HTTP ---

    def _call(self, method, path, body=None, *, accept_errors=False):
        request = urllib.request.Request(
            self.api_url + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {self._access_token()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            details = error.read().decode(errors="replace")[:2000]
            if accept_errors and error.code < 500:
                try:
                    return json.loads(details)
                except ValueError:
                    pass
            raise GatewayError(f"Tpay {method} {path} returned {error.code}: {details}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise GatewayError(f"Tpay {method} {path} unreachable: {error}") from error

    def _access_token(self):
        key = f"tpay-token-{settings.TPAY_CLIENT_ID}-{self.sandbox}"
        token = cache.get(key)
        if token:
            return token
        request = urllib.request.Request(
            self.api_url + "/oauth/auth",
            method="POST",
            data=urllib.parse.urlencode(
                {"client_id": settings.TPAY_CLIENT_ID, "client_secret": settings.TPAY_CLIENT_SECRET},
            ).encode(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                data = json.loads(response.read())
        except (urllib.error.URLError, TimeoutError) as error:
            raise GatewayError(f"Tpay authorization failed: {error}") from error
        # Renewed a minute early, so a token never expires mid-request.
        cache.set(key, data["access_token"], max(int(data.get("expires_in", 7200)) - 60, 60))
        return data["access_token"]


def verify_jws(signature, body, certificates_url, fetch=None):
    """
    Checks Tpay's detached JWS (RFC 7515) over the raw body: the certificate must come from Tpay's address,
    be issued by Tpay's root CA, be valid now and verify the RSA SHA-256 signature of "<header>.<base64url(body)>".
    """
    fetch = fetch or _fetch_certificate
    parts = signature.split(".")
    if len(parts) != 3 or not parts[0] or not parts[2]:
        raise InvalidNotification("Missing or malformed X-JWS-Signature.")
    header_b64, _, signature_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64))
    except ValueError as error:
        raise InvalidNotification("Unreadable JWS header.") from error
    x5u = header.get("x5u", "")
    if not x5u.startswith(certificates_url + "/"):
        raise InvalidNotification(f"Certificate from an unexpected address: {x5u!r}")
    try:
        certificate = x509.load_pem_x509_certificate(fetch(x5u))
        root = x509.load_pem_x509_certificate(fetch(f"{certificates_url}/x509/tpay-jws-root.pem"))
        certificate.verify_directly_issued_by(root)
    except (ValueError, TypeError, InvalidSignature) as error:
        raise InvalidNotification("Signing certificate is not issued by Tpay.") from error
    now = datetime.now(UTC)
    if not certificate.not_valid_before_utc <= now <= certificate.not_valid_after_utc:
        raise InvalidNotification("Signing certificate is not valid now.")
    payload = base64.urlsafe_b64encode(body).rstrip(b"=")
    try:
        certificate.public_key().verify(
            _b64url_decode(signature_b64), header_b64.encode() + b"." + payload, padding.PKCS1v15(), hashes.SHA256(),
        )
    except InvalidSignature as error:
        raise InvalidNotification("JWS signature does not match.") from error


def _fetch_certificate(url):
    key = "tpay-cert-" + hashlib.sha256(url.encode()).hexdigest()
    pem = cache.get(key)
    if pem is None:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                pem = response.read()
        except (urllib.error.URLError, TimeoutError) as error:
            raise InvalidNotification(f"Certificate unavailable: {url}") from error
        cache.set(key, pem, CERTIFICATE_CACHE_SECONDS)
    return pem


def _b64url_decode(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _amount(value):
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _md5_amount(value):
    """tr_amount as Tpay formats it for the checksum: two decimals, dot."""
    amount = _amount(value)
    return f"{amount:.2f}" if amount is not None else (value or "")


def _payer(payer):
    data = {"email": payer.email, "name": payer.name}
    optional = {"address": payer.street, "code": payer.postal_code, "city": payer.city,
                "country": payer.country, "taxId": payer.tax_id}
    data.update({key: value for key, value in optional.items() if value})
    return data
