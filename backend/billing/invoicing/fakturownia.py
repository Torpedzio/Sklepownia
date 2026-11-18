"""
Invoices issued in Fakturownia (fakturownia.pl, API: github.com/fakturownia/api). Fakturownia numbers them, sends
company invoices to KSeF (with FAKTUROWNIA_KSEF) and renders the PDF, with the KSeF code once KSeF accepts it.
"""

import json
import urllib.error
import urllib.request
from datetime import date

from django.conf import settings
from django.utils import timezone

from ..models import Invoice
from . import tax
from .base import BaseIssuer, InvoicingError

USER_AGENT = "Sklepownia/1.0 (+billing)"
TIMEOUT = 30
# Fakturownia's gov_status, without the "demo_" prefix it has with the KSeF test environment.
ACCEPTED = {"ok"}
SENDING = {"processing", "offline", "status_check_error"}
# KSeF did not answer; Fakturownia does not try again by itself.
SERVER_ERROR = {"server_error"}
REJECTED = {"send_error", "duplicate_error", "blocked_403_error", "offline_error"}
NOT_CONNECTED = "not_connected"
MAX_RESENDS = 3


class FakturowniaIssuer(BaseIssuer):
    name = "fakturownia"

    def issue(self, invoice):
        body = {"invoice": self.payload(invoice)}
        if settings.FAKTUROWNIA_KSEF and invoice.buyer.get("kind") == "company":
            body["gov_save_and_send"] = True
        data = self._call("POST", "/invoices.json", body)
        if not data.get("id"):
            raise InvoicingError(f"Fakturownia nie zwróciła faktury: {json.dumps(data)[:300]}")
        invoice.external_id = str(data["id"])
        invoice.number = data.get("number") or ""
        invoice.issue_date = _date(data.get("issue_date")) or timezone.localdate()
        invoice.seller = {
            "name": data.get("seller_name") or "",
            "tax_id": data.get("seller_tax_no") or "",
            "street": data.get("seller_street") or "",
            "postal_code": data.get("seller_post_code") or "",
            "city": data.get("seller_city") or "",
        }
        self._apply_ksef(invoice, data)
        invoice.pdf = self._pdf(invoice)

    def check_ksef(self, invoice):
        data = self._call("GET", f"/invoices/{invoice.external_id}.json")
        state = _state(data.get("gov_status"))
        if state in SERVER_ERROR:
            if invoice.attempts >= MAX_RESENDS:
                invoice.ksef_status = Invoice.Ksef.REJECTED
                invoice.error = f"KSeF nie odpowiedział mimo {MAX_RESENDS} ponownych wysyłek."
                return
            self._call("GET", f"/invoices/{invoice.external_id}.json?send_to_ksef=yes")
            invoice.attempts += 1
            invoice.ksef_status = Invoice.Ksef.SENDING
            invoice.error = "KSeF chwilowo nie odpowiada; faktura wysłana ponownie."
            return
        was_accepted = invoice.ksef_status == Invoice.Ksef.ACCEPTED
        self._apply_ksef(invoice, data)
        if invoice.ksef_status == Invoice.Ksef.ACCEPTED and not was_accepted:
            # With the KSeF number and the verification QR code now.
            invoice.pdf = self._pdf(invoice)

    def payload(self, invoice):
        buyer = invoice.buyer
        company = buyer.get("kind") == "company"
        country = buyer.get("country") or "PL"
        paid_on = invoice.sale_date.isoformat()
        payload = {
            "kind": "vat",
            "issue_date": timezone.localdate().isoformat(),
            "sell_date": paid_on,
            "payment_to": paid_on,
            "status": "paid",
            "paid": str(invoice.gross),
            "paid_date": paid_on,
            "payment_type": "card",
            "currency": invoice.currency,
            "lang": "pl",
            # Our payment: Fakturownia refuses a second invoice for it, should a retry follow a lost answer.
            "oid": invoice.payment.reference,
            "oid_unique": "yes",
            "buyer_company": company,
            "buyer_name": buyer.get("company_name") if company else buyer.get("full_name"),
            "buyer_street": buyer.get("street", ""),
            "buyer_post_code": buyer.get("postal_code", ""),
            "buyer_city": buyer.get("city", ""),
            "buyer_country": country,
            "positions": [{
                "name": invoice.item,
                "tax": int(invoice.vat_rate) if invoice.vat_rate.isdigit() else invoice.vat_rate,
                "total_price_gross": str(invoice.gross),
                "quantity": 1,
                "quantity_unit": "usł.",
            }],
        }
        if company:
            payload["buyer_tax_no"] = buyer.get("tax_id", "")
            if country != "PL":
                payload["buyer_tax_no_kind"] = "nip_ue" if country in tax.EU else "other"
        else:
            first, _, last = (buyer.get("full_name") or "").strip().rpartition(" ")
            payload["buyer_first_name"] = first or last
            payload["buyer_last_name"] = last if first else ""
        notes = tax.notes(invoice)
        if notes:
            payload["description"] = " ".join(notes)
        return payload

    def _apply_ksef(self, invoice, data):
        state = _state(data.get("gov_status"))
        if state in ACCEPTED:
            invoice.ksef_status = Invoice.Ksef.ACCEPTED
            invoice.ksef_number = data.get("gov_id") or ""
            invoice.error = ""
        elif state in SENDING or state in SERVER_ERROR:
            invoice.ksef_status = Invoice.Ksef.SENDING
        elif state in REJECTED:
            invoice.ksef_status = Invoice.Ksef.REJECTED
            invoice.error = "; ".join(data.get("gov_error_messages") or []) or f"KSeF: {state}"
        elif state == NOT_CONNECTED and settings.FAKTUROWNIA_KSEF and invoice.buyer.get("kind") == "company":
            # A company's invoice must reach KSeF; the payer gets it only once it does.
            invoice.ksef_status = Invoice.Ksef.REJECTED
            invoice.error = "Konto Fakturowni nie jest połączone z KSeF (Ustawienia → KSeF)."
        else:
            invoice.ksef_status = Invoice.Ksef.NONE

    def _pdf(self, invoice):
        return self._call("GET", f"/invoices/{invoice.external_id}.pdf", accept="application/pdf")

    def _call(self, method, path, body=None, *, accept="application/json"):
        if not settings.FAKTUROWNIA_DOMAIN or not settings.FAKTUROWNIA_API_TOKEN:
            raise InvoicingError("Brak FAKTUROWNIA_DOMAIN albo FAKTUROWNIA_API_TOKEN.")
        request = urllib.request.Request(
            f"https://{settings.FAKTUROWNIA_DOMAIN}.fakturownia.pl{path}",
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {settings.FAKTUROWNIA_API_TOKEN}",
                "Content-Type": "application/json",
                "Accept": accept,
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                content = response.read()
        except urllib.error.HTTPError as error:
            details = error.read().decode(errors="replace")[:600]
            raise InvoicingError(f"Fakturownia {method} {path.split('?')[0]}: {error.code} {details}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise InvoicingError(f"Fakturownia nie odpowiada: {error}") from error
        if accept != "application/json":
            return content
        try:
            return json.loads(content or b"{}")
        except ValueError as error:
            raise InvoicingError(f"Fakturownia zwróciła coś innego niż JSON: {content[:200]!r}") from error


def _state(gov_status):
    return (gov_status or "").removeprefix("demo_")


def _date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None
