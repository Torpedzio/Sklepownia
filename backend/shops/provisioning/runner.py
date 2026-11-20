import logging

from django.db import transaction
from django.utils import timezone

from ..models import ProvisioningJob, ProvisioningStep, Shop
from . import get_provisioner
from .base import ProvisioningError

logger = logging.getLogger(__name__)

GENERIC_STEP_ERROR = "Wystąpił nieoczekiwany błąd."


def run_job(job_id):
    """Returns the shop when it ended up active, otherwise None."""
    with transaction.atomic():
        job = ProvisioningJob.objects.select_for_update().select_related("shop").get(pk=job_id)
        if job.status != ProvisioningJob.Status.QUEUED:
            logger.info("Provisioning job %s already %s, skipping", job_id, job.status)
            return None
        shop = Shop.objects.select_for_update().get(pk=job.shop_id)
        shop.transition_to(Shop.Status.PROVISIONING)
        job.status = ProvisioningJob.Status.RUNNING
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at"])

    try:
        provisioner = get_provisioner(shop.platform)
    except Exception:
        # E.g. code half-updated in a running worker. The job is already running, so it has to fail here, or the shop
        # would stay in provisioning with nothing to retry.
        logger.exception("Provisioner for shop %s could not be loaded", shop.pk)
        step = job.steps.exclude(status=ProvisioningStep.Status.DONE).first()
        if step is not None:
            _mark(step, ProvisioningStep.Status.FAILED, finished_at=timezone.now(), error=GENERIC_STEP_ERROR)
        _fail(job, shop, None, GENERIC_STEP_ERROR)
        return None
    for step in job.steps.all():
        _mark(step, ProvisioningStep.Status.RUNNING, started_at=timezone.now())
        try:
            provisioner.run_step(step.key, shop)
        except Exception as exc:
            logger.exception("Provisioning of shop %s failed at step %s", shop.pk, step.key)
            # Raw exception text may contain hostnames or credentials, so the user only sees it for known errors.
            message = str(exc) if isinstance(exc, ProvisioningError) else GENERIC_STEP_ERROR
            _mark(step, ProvisioningStep.Status.FAILED, finished_at=timezone.now(), error=message)
            _fail(job, shop, provisioner, message)
            return None
        _mark(step, ProvisioningStep.Status.DONE, finished_at=timezone.now())

    job.status = ProvisioningJob.Status.SUCCEEDED
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "finished_at"])
    shop.transition_to(Shop.Status.ACTIVE)
    return shop


def _mark(step, status, **fields):
    step.status = status
    for name, value in fields.items():
        setattr(step, name, value)
    step.save(update_fields=["status", *fields])


def _fail(job, shop, provisioner, message):
    """`provisioner`: None when it couldn't be loaded, so there's nothing to clean up with."""
    try:
        if provisioner is not None:
            provisioner.cleanup(shop)
    except Exception:
        logger.exception("Cleanup after failed provisioning of shop %s failed", shop.pk)
    job.status = ProvisioningJob.Status.FAILED
    job.error = message
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "error", "finished_at"])
    shop.transition_to(Shop.Status.FAILED)
