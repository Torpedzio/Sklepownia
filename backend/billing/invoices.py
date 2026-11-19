"""Invoices: created with the paid payment, issued in the background, followed in KSeF, e-mailed once final."""

import logging
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .invoicing import get_issuer, tax
from .invoicing.base import InvoicingError
from .models import Invoice, Payment

logger = logging.getLogger(__name__)

# Failed issuing is retried with doubling delays (5 min, 10, 20 … up to 6 h) until the admin steps in.
RETRY_FIRST = timedelta(minutes=5)
RETRY_LONGEST = timedelta(hours=6)
MAX_ATTEMPTS = 15
# process() leaves freshly issued invoices to their own e-mail for this long.
DELIVERY_GRACE = timedelta(minutes=10)
LINK_SALT = "billing.invoice-pdf"
LINK_MAX_AGE = 24 * 60 * 60


def create_for(payment):
    """Call in the payment's transaction. Nothing for zero amounts: the balance came from invoiced payments."""
    if payment.amount <= 0 or Invoice.objects.filter(payment=payment).exists():
        return None
    buyer = payment.billing_details or {}
    rate = tax.rate_for(buyer, payment.plan.vat_rate)
    net, vat = tax.split(payment.amount, rate)
    invoice = Invoice.objects.create(
        payment=payment,
        sale_date=timezone.localdate(payment.paid_at),
        buyer=buyer,
        item=_item(payment),
        vat_rate=rate,
        net=net,
        vat=vat,
        gross=payment.amount,
        currency=payment.currency,
    )
    transaction.on_commit(lambda: _later("issue_invoice", invoice.pk))
    return invoice


def issue(invoice_id):
    """A failure is recorded and retried by process(). Returns the invoice."""
    with transaction.atomic():
        invoice = Invoice.objects.select_for_update().select_related("payment__plan").get(pk=invoice_id)
        if invoice.status != Invoice.Status.PENDING:
            return invoice
        issuer = get_issuer()
        invoice.attempts += 1
        invoice.checked_at = timezone.now()
        try:
            if not (invoice.buyer.get("company_name") or invoice.buyer.get("full_name")):
                raise InvoicingError("Brak danych nabywcy w płatności.")
            # A failed attempt gives back the number it took.
            with transaction.atomic():
                issuer.issue(invoice)
        except Exception as error:  # noqa: BLE001 – whatever went wrong, the invoice waits for the next try
            if not isinstance(error, InvoicingError):
                logger.exception("Issuing invoice %s failed", invoice.pk)
            else:
                logger.warning("Invoice %s not issued (attempt %s): %s", invoice.pk, invoice.attempts, error)
            Invoice.objects.filter(pk=invoice.pk).update(
                attempts=invoice.attempts, checked_at=invoice.checked_at, error=str(error)[:1000],
            )
            return Invoice.objects.get(pk=invoice.pk)
        invoice.status = Invoice.Status.ISSUED
        invoice.issuer = issuer.name
        invoice.issued_at = timezone.now()
        invoice.attempts = 0
        if invoice.ksef_status != Invoice.Ksef.REJECTED:
            invoice.error = ""
        invoice.save()
        _after_change(invoice)
    return invoice


def check_ksef(invoice_id):
    with transaction.atomic():
        invoice = Invoice.objects.select_for_update().select_related("payment__plan").get(pk=invoice_id)
        if invoice.status != Invoice.Status.ISSUED or invoice.ksef_status == Invoice.Ksef.NONE:
            return invoice
        issuer = get_issuer()
        if issuer.name != invoice.issuer:
            # INVOICE_ISSUER changed since: only the issuer that sent it can ask about it.
            logger.warning("Invoice %s was issued by %s, not %s; KSeF not checked", invoice.pk, invoice.issuer,
                           issuer.name)
            return invoice
        before = invoice.ksef_status
        invoice.checked_at = timezone.now()
        try:
            issuer.check_ksef(invoice)
        except InvoicingError as error:
            logger.warning("Checking invoice %s in KSeF failed: %s", invoice.pk, error)
            Invoice.objects.filter(pk=invoice.pk).update(checked_at=invoice.checked_at)
            return invoice
        invoice.save()
        if invoice.ksef_status != before:
            _after_change(invoice)
    return invoice


def deliver(invoice_id):
    """At most once; deleted accounts get nothing. Returns whether it was sent."""
    from .emails import invoice_message

    invoice = Invoice.objects.select_related("payment__plan", "payment__user").get(pk=invoice_id)
    user = invoice.payment.user
    if not invoice.is_final or invoice.sent_at or not user.is_active:
        return False
    # Claimed first, so two workers don't both send it.
    if not Invoice.objects.filter(pk=invoice.pk, sent_at__isnull=True).update(sent_at=timezone.now()):
        return False
    try:
        invoice_message(invoice).send()
    except Exception:
        Invoice.objects.filter(pk=invoice.pk).update(sent_at=None)
        raise
    return True


def process(now=None):
    """Background round: retries pending invoices, polls KSeF and e-mails final invoices that never left."""
    now = now or timezone.now()
    for invoice in Invoice.objects.filter(status=Invoice.Status.PENDING, attempts__lt=MAX_ATTEMPTS):
        if invoice.checked_at is None or invoice.checked_at + _retry_delay(invoice.attempts) <= now:
            issue(invoice.pk)
    for invoice_id in Invoice.objects.filter(
        status=Invoice.Status.ISSUED, ksef_status=Invoice.Ksef.SENDING,
    ).values_list("pk", flat=True):
        check_ksef(invoice_id)
    unsent = Invoice.objects.filter(
        Q(ksef_status=Invoice.Ksef.NONE) | Q(ksef_status=Invoice.Ksef.ACCEPTED),
        status=Invoice.Status.ISSUED, sent_at__isnull=True, issued_at__lte=now - DELIVERY_GRACE,
        payment__user__is_active=True,
    )
    for invoice_id in unsent.values_list("pk", flat=True):
        _later("deliver_invoice", invoice_id)


def download_url(invoice, request):
    """Works without signing in, for LINK_MAX_AGE: the app opens it in the browser."""
    token = signing.dumps(invoice.pk, salt=LINK_SALT)
    return request.build_absolute_uri(reverse("billing-invoice-pdf", args=[token]))


def from_link(token):
    """None when the link is wrong or too old."""
    try:
        invoice_id = signing.loads(token, salt=LINK_SALT, max_age=LINK_MAX_AGE)
    except signing.BadSignature:
        return None
    return Invoice.objects.filter(pk=invoice_id, status=Invoice.Status.ISSUED).first()


def _after_change(invoice):
    if invoice.is_final:
        transaction.on_commit(lambda: _later("deliver_invoice", invoice.pk))
    elif invoice.ksef_status == Invoice.Ksef.REJECTED:
        logger.error("KSeF did not accept invoice %s (%s): %s", invoice.pk, invoice.number, invoice.error)


def _retry_delay(attempts):
    return min(RETRY_FIRST * 2 ** max(attempts - 1, 0), RETRY_LONGEST)


def _item(payment):
    def day(value):
        return timezone.localtime(value).strftime("%d.%m.%Y") if value else ""

    period = f"{day(payment.period_start)}–{day(payment.period_end)}"
    if payment.kind == Payment.Kind.UPGRADE:
        return f"Dopłata za zmianę na plan {payment.plan.name} w {settings.PLATFORM_NAME}, okres {period}"
    return f"Abonament {settings.PLATFORM_NAME}, plan {payment.plan.name}, okres {period}"


def _later(task, invoice_id):
    from . import tasks

    getattr(tasks, task).delay(invoice_id)
