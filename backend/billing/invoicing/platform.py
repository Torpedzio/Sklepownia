from django.conf import settings
from django.utils import timezone

from ..models import Invoice, InvoiceSequence
from . import tax
from .base import BaseIssuer, InvoicingError
from .pdf import render

SELLER_FIELDS = {"name": "NAME", "tax_id": "TAX_ID", "street": "STREET", "postal_code": "POSTAL_CODE", "city": "CITY"}


class PlatformIssuer(BaseIssuer):
    name = "platform"

    def issue(self, invoice):
        seller = settings.INVOICE_SELLER
        missing = [f"INVOICE_SELLER_{env}" for key, env in SELLER_FIELDS.items() if not seller.get(key)]
        if missing:
            raise InvoicingError(f"Brak danych sprzedawcy: {', '.join(missing)}.")
        today = timezone.localdate()
        invoice.seller = {key: value for key, value in seller.items() if value}
        invoice.issue_date = today
        invoice.number = next_number(today)
        invoice.ksef_status = Invoice.Ksef.NONE
        invoice.pdf = render(invoice, notes=tax.notes(invoice))

    def check_ksef(self, invoice):
        """Not sent to KSeF."""


def next_number(day):
    """Call inside a transaction: the month's counter stays locked until it ends."""
    sequence, _ = InvoiceSequence.objects.select_for_update().get_or_create(period=day.strftime("%Y-%m"))
    sequence.last += 1
    sequence.save(update_fields=["last"])
    return settings.INVOICE_NUMBER_FORMAT.format(year=day.year, month=day.month, number=sequence.last)
