from smtplib import SMTPException

from celery import shared_task

from .emails import admin_access_message
from .models import Shop, ShopOperation
from .provisioning import get_provisioner
from .provisioning.operations import run_operation
from .provisioning.runner import run_job


@shared_task
def provision_shop(job_id):
    shop = run_job(job_id)
    if shop is not None:
        send_admin_access_email.delay(shop.pk, "ready")


@shared_task
def teardown_shop(shop_id):
    get_provisioner().teardown(Shop.objects.get(pk=shop_id))


@shared_task
def run_shop_operation(operation_id):
    operation = run_operation(operation_id)
    if (
        operation is not None
        and operation.kind == ShopOperation.Kind.RESET_ADMIN_PASSWORD
        and operation.status == ShopOperation.Status.SUCCEEDED
    ):
        send_admin_access_email.delay(operation.shop_id, "new_password")


# A mail server that is briefly down shouldn't lose the only copy of the admin password.
@shared_task(autoretry_for=(OSError, SMTPException), retry_backoff=True, max_retries=5)
def send_admin_access_email(shop_id, reason):
    """Sends the owner the shop's details and admin login (see shops/emails.py)."""
    shop = (
        Shop.objects.select_related("owner", "config__template", "credentials")
        .exclude(status=Shop.Status.DELETED)
        .filter(pk=shop_id)
        .first()
    )
    if shop is None:
        return
    admin_access_message(shop, reason).send()
