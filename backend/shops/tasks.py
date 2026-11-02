from celery import shared_task

from .provisioning.runner import run_job


@shared_task
def provision_shop(job_id):
    run_job(job_id)
