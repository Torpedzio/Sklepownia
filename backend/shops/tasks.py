from celery import shared_task

from .models import Shop
from .provisioning import get_provisioner
from .provisioning.runner import run_job


@shared_task
def provision_shop(job_id):
    run_job(job_id)


@shared_task
def teardown_shop(shop_id):
    get_provisioner().teardown(Shop.objects.get(pk=shop_id))
