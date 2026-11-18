from smtplib import SMTPException

from celery import shared_task

from . import sales
from .emails import admin_access_message
from .models import SalesSync, Shop, ShopOperation, ShopOrder
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
    shop = Shop.objects.select_related("owner").filter(pk=shop_id).first()
    if shop is None:
        return
    get_provisioner(shop.platform).teardown(shop)
    # The copy of its orders goes with the shop: it holds customers' names.
    ShopOrder.objects.filter(shop=shop).delete()
    SalesSync.objects.filter(shop=shop).delete()
    if shop.owner.deleted_at is not None:
        # The owner deleted the account: nothing of the shop is kept, its settings and history included.
        shop.delete()


@shared_task
def suspend_shop(shop_id):
    shop = Shop.objects.get(pk=shop_id)
    get_provisioner(shop.platform).suspend(shop)


@shared_task
def resume_shop_container(shop_id):
    shop = Shop.objects.get(pk=shop_id)
    get_provisioner(shop.platform).resume(shop)


@shared_task
def refresh_shop_resources(shop_id):
    """After a plan change: e.g. a new memory limit for the shop's container."""
    shop = Shop.objects.get(pk=shop_id)
    if shop.status == Shop.Status.ACTIVE:
        get_provisioner(shop.platform).refresh_resources(shop)


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


@shared_task
def sync_shop_orders(shop_id):
    sales.sync(shop_id)


@shared_task
def sync_all_shop_orders():
    """Scheduled by Celery beat (SHOP_ORDERS_SYNC_MINUTES)."""
    sales.sync_all()
