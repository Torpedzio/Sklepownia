from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import User

from . import shop_settings
from .choices import COUNTRY_TIMEZONES
from .models import ProvisioningJob, ProvisioningStep, Shop, ShopConfig, ShopOperation, ShopSettings
from .provisioning import get_provisioner
from .tasks import provision_shop, run_shop_operation, teardown_shop

# An operation older than this no longer blocks new ones (e.g. the worker died while running it).
OPERATION_TIMEOUT = timedelta(minutes=15)


class ShopLimitReached(Exception):
    pass


class SlugTaken(Exception):
    pass


class ShopNotActive(Exception):
    pass


class OperationInProgress(Exception):
    pass


def create_shop(owner, *, name, slug, **config):
    try:
        with transaction.atomic():
            # Lock the owner so concurrent requests can't both pass the limit check.
            User.objects.select_for_update().get(pk=owner.pk)
            live_shops = owner.shops.exclude(status=Shop.Status.DELETED).count()
            if live_shops >= settings.SHOPS_MAX_PER_USER:
                raise ShopLimitReached()
            shop = Shop.objects.create(owner=owner, name=name, slug=slug)
            ShopConfig.objects.create(shop=shop, **config)
            _enqueue_provisioning(shop)
    except IntegrityError as exc:
        if "unique_slug_for_live_shops" in str(exc):
            raise SlugTaken() from exc
        raise
    return shop


def retry_shop(shop):
    with transaction.atomic():
        shop = Shop.objects.select_for_update().get(pk=shop.pk)
        shop.transition_to(Shop.Status.PENDING)
        _enqueue_provisioning(shop)
    return shop


def delete_shop(shop):
    with transaction.atomic():
        shop = Shop.objects.select_for_update().get(pk=shop.pk)
        shop.transition_to(Shop.Status.DELETED)
        transaction.on_commit(lambda: teardown_shop.delay(shop.pk))


def _enqueue_provisioning(shop):
    job = ProvisioningJob.objects.create(shop=shop)
    ProvisioningStep.objects.bulk_create(
        ProvisioningStep(job=job, key=key, label=label, order=order)
        for order, (key, label) in enumerate(get_provisioner().STEPS)
    )
    transaction.on_commit(lambda: provision_shop.delay(job.pk))
    return job


def get_settings(shop):
    """The shop's settings, every section and field present."""
    stored, _ = ShopSettings.objects.get_or_create(shop=shop)
    defaults = shop_settings.default_settings(shop)
    complete = shop_settings.complete(stored.values, defaults)
    if complete != stored.values:
        stored.values = complete
        stored.save(update_fields=["values", "updated_at"])
    return stored


def current_operation(shop):
    """The operation that is queued or running and still blocks new ones, or None."""
    return (
        shop.operations.filter(
            status__in=[ShopOperation.Status.QUEUED, ShopOperation.Status.RUNNING],
            created_at__gte=timezone.now() - OPERATION_TIMEOUT,
        )
        .order_by("-created_at")
        .first()
    )


def update_settings(shop, user, changes):
    """
    Queues applying `changes` (validated input of SettingsUpdateSerializer) to the shop.
    Returns the operation, or None when nothing would change.
    """
    current = get_settings(shop).values
    changes = shop_settings.diff(current, shop_settings.normalize(changes))
    region = changes.get("region", {})
    # A new country brings its time zone and standard VAT rate, unless the owner picks them too.
    if "country" in region:
        timezone_name = COUNTRY_TIMEZONES.get(region["country"])
        if "timezone" not in region and timezone_name and timezone_name != current["region"]["timezone"]:
            region["timezone"] = timezone_name
        rate = shop_settings.suggested_vat_rate(region["country"])
        if "standard_rate" not in changes.get("taxes", {}) and rate != current["taxes"]["standard_rate"]:
            changes.setdefault("taxes", {})["standard_rate"] = rate
    if not changes:
        return None
    return start_operation(shop, user, ShopOperation.Kind.UPDATE_SETTINGS, changes)


def start_operation(shop, user, kind, changes=None):
    with transaction.atomic():
        # Locks the shop, so two requests can't both pass the checks below.
        shop = Shop.objects.select_for_update().get(pk=shop.pk)
        if shop.status != Shop.Status.ACTIVE:
            raise ShopNotActive()
        if current_operation(shop) is not None:
            raise OperationInProgress()
        operation = ShopOperation.objects.create(shop=shop, kind=kind, changes=changes or {}, requested_by=user)
        transaction.on_commit(lambda: run_shop_operation.delay(operation.pk))
    return operation
