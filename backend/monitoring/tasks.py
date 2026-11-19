from datetime import datetime
from smtplib import SMTPException

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

from shops.models import Shop

from . import checks, texts


@shared_task
def check_shops():
    """Scheduled by Celery beat every MONITOR_INTERVAL_MINUTES."""
    checks.run()


@shared_task
def repair_shop(shop_id, action):
    checks.repair(shop_id, action)


# An alert shouldn't be lost because the mail server is briefly down.
@shared_task(autoretry_for=(OSError, SMTPException), retry_backoff=True, max_retries=5)
def send_staff_alert(subject, body):
    if settings.ALERT_EMAILS:
        send_mail(f"[{settings.PLATFORM_NAME}] {subject}", body, None, settings.ALERT_EMAILS)


@shared_task(autoretry_for=(OSError, SMTPException), retry_backoff=True, max_retries=5)
def send_shop_email(shop_id, reason, since, until=None):
    """Tells the owner the shop is down ("down") or works again ("back"); see texts.shop_email."""
    shop = Shop.objects.select_related("owner").exclude(status=Shop.Status.DELETED).filter(pk=shop_id).first()
    if shop is None:
        return
    until = datetime.fromisoformat(until) if until else None
    texts.shop_email(shop, reason, datetime.fromisoformat(since), until).send()
