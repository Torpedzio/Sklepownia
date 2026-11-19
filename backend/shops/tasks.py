from smtplib import SMTPException

from celery import shared_task
from django.utils import timezone

from push import messages
from push import services as push

from . import backups, sales
from .emails import admin_access_message
from .models import ProvisioningJob, SalesSync, Shop, ShopOperation, ShopOrder
from .provisioning import get_provisioner
from .provisioning.operations import run_operation
from .provisioning.runner import run_job


@shared_task
def provision_shop(job_id):
    shop = run_job(job_id)
    if shop is not None:
        send_admin_access_email.delay(shop.pk, "ready")
        push.notify(shop.owner_id, messages.shop_ready(shop))
        return
    job = ProvisioningJob.objects.select_related("shop").get(pk=job_id)
    if job.status == ProvisioningJob.Status.FAILED:
        push.notify(job.shop.owner_id, messages.shop_failed(job.shop))


@shared_task
def teardown_shop(shop_id):
    shop = Shop.objects.select_related("owner").filter(pk=shop_id).first()
    if shop is None:
        return
    account_deleted = shop.owner.deleted_at is not None
    if not account_deleted:
        # So a shop deleted by mistake can be brought back (manage.py restore_shop).
        backups.back_up_before_delete(shop)
    get_provisioner(shop.platform).teardown(shop)
    # The order copy holds customers' names.
    ShopOrder.objects.filter(shop=shop).delete()
    SalesSync.objects.filter(shop=shop).delete()
    if account_deleted:
        # Nothing of the shop is kept, backups, settings and history included.
        backups.forget_all(shop)
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
    """After a plan change, e.g. a new container memory limit."""
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
def count_shop_products(shop_id):
    """Imported here: the checklist uses services, which import these tasks."""
    from . import checklist

    checklist.count(shop_id)


@shared_task
def sync_all_shop_orders():
    sales.sync_all()


@shared_task
def back_up_all_shops():
    from monitoring import alerts

    started = timezone.now()
    failed = backups.back_up_all()
    if backups.enabled():
        # Heartbeat for the monitor's late-backup check; also reports the failures.
        alerts.nightly_backups_done(failed, started)
