from smtplib import SMTPException

from celery import shared_task

from . import emails, invoices, services
from .models import Payment, Subscription


@shared_task
def renew_subscriptions():
    """Scheduled by Celery beat (CELERY_BEAT_SCHEDULE)."""
    services.renew_due()


@shared_task
def reconcile_payments():
    """Scheduled by Celery beat: settles payments whose outcome never reached the platform."""
    services.reconcile_pending()


@shared_task(autoretry_for=(OSError, SMTPException), retry_backoff=True, max_retries=5)
def send_billing_email(kind, object_id, context=None):
    if kind == "changed":
        subscription = Subscription.objects.select_related("plan", "user").get(pk=object_id)
        message = emails.plan_changed_message(subscription, **(context or {}))
    elif kind == "ended":
        message = emails.ended_message(Subscription.objects.select_related("plan", "user").get(pk=object_id))
    else:
        payment = Payment.objects.select_related("plan", "user", "subscription").get(pk=object_id)
        message = emails.payment_message(kind, payment)
    message.send()


@shared_task
def issue_invoice(invoice_id):
    invoices.issue(invoice_id)


@shared_task(autoretry_for=(OSError, SMTPException), retry_backoff=True, max_retries=5)
def deliver_invoice(invoice_id):
    invoices.deliver(invoice_id)


@shared_task
def process_invoices():
    """Scheduled by Celery beat: retries issuing, follows KSeF, e-mails invoices that never left."""
    invoices.process()
