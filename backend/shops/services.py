import json
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import User

from . import backups, shop_settings
from .choices import COUNTRY_TIMEZONES
from .models import (
    InvalidTransition,
    ProvisioningJob,
    ProvisioningStep,
    Shop,
    ShopConfig,
    ShopOperation,
    ShopSettings,
)
from .platforms import Platform, platform_info
from .tasks import provision_shop, resume_shop_container, run_shop_operation, suspend_shop, teardown_shop

# An operation older than this no longer blocks new ones (e.g. the worker died while running it).
OPERATION_TIMEOUT = timedelta(minutes=15)


class ShopLimitReached(Exception):
    def __init__(self, limit):
        super().__init__(limit)
        self.limit = limit


class PlatformLimitReached(Exception):
    """The plan allows only `limit` shops on `platform` (none at all when 0)."""

    def __init__(self, plan, platform, limit):
        super().__init__(platform, limit)
        self.plan = plan
        self.platform = platform
        self.limit = limit


class PlanRequired(Exception):
    """Creating shops needs an active paid plan."""


class ShopBeingSetUp(Exception):
    """A shop is being set up right now, so it can't be removed yet."""

    def __init__(self, shop):
        super().__init__(shop.pk)
        self.shop = shop


class SlugTaken(Exception):
    pass


class ShopNotActive(Exception):
    pass


class OperationInProgress(Exception):
    pass


class BackupsDisabled(Exception):
    """Backups aren't set up on this platform (SHOPS_BACKUP_PASSWORD)."""


class BackupLimitReached(Exception):
    """The owner made as many backups today as SHOPS_BACKUP_MANUAL_PER_DAY allows."""


def create_shop(owner, *, name, slug, platform=None, **config):
    """`platform` defaults to the template's; the serializer makes sure they match."""
    platform = platform or config["template"].platform
    try:
        with transaction.atomic():
            # Lock the owner so concurrent requests can't both pass the limit check.
            User.objects.select_for_update().get(pk=owner.pk)
            plan = active_plan(owner)
            if plan is None:
                raise PlanRequired()
            _check_room(owner, plan, platform)
            shop = Shop.objects.create(owner=owner, name=name, slug=slug, platform=platform)
            ShopConfig.objects.create(shop=shop, **config)
            _enqueue_provisioning(shop)
    except IntegrityError as exc:
        if "unique_slug_for_live_shops" in str(exc):
            raise SlugTaken() from exc
        raise
    return shop


def active_plan(user):
    """The plan that lets the user create shops now, or None."""
    from billing.models import Subscription

    subscription = Subscription.objects.select_related("plan").filter(user=user).first()
    return subscription.plan if subscription and subscription.allows_new_shops else None


def counted_shops(user):
    """Shops that take up the plan's limit: not deleted, not suspended, not test shops from before paid plans."""
    return (
        user.shops.exclude(status__in=[Shop.Status.DELETED, Shop.Status.SUSPENDED])
        .filter(is_test=False)
        .order_by("created_at", "pk")
    )


def paid_shop_count(user):
    return counted_shops(user).count()


# Platforms that plans allow only a few shops on, and the plan field with that number.
PLATFORM_LIMIT_FIELDS = {Platform.MAGENTO: "max_magento_shops"}


def platform_limit(plan, platform):
    """How many shops on `platform` the plan allows, or None when only its total limit counts."""
    field = PLATFORM_LIMIT_FIELDS.get(platform)
    return getattr(plan, field) if field else None


def platform_usage(user, plan, platform):
    """(shops on `platform` that count, the plan's limit for it), or None when the platform has no own limit."""
    limit = platform_limit(plan, platform)
    if limit is None:
        return None
    return counted_shops(user).filter(platform=platform).count(), limit


def _check_room(user, plan, platform):
    if paid_shop_count(user) >= plan.max_shops:
        raise ShopLimitReached(plan.max_shops)
    usage = platform_usage(user, plan, platform)
    if usage and usage[0] >= usage[1]:
        raise PlatformLimitReached(plan, platform, usage[1])


def shops_that_fit(plan, shops, kept=()):
    """
    `shops` in their order, as many as fit in the plan next to the `kept` ones: within its total limit and the
    limits for single platforms (e.g. Magento). A shop that doesn't fit is skipped, so a later one may still fit.
    """
    total = len(kept)
    per_platform = Counter(shop.platform for shop in kept)
    fitting = []
    for shop in shops:
        if total >= plan.max_shops:
            break
        limit = platform_limit(plan, shop.platform)
        if limit is not None and per_platform[shop.platform] >= limit:
            continue
        fitting.append(shop)
        total += 1
        per_platform[shop.platform] += 1
    return fitting


def suspend_shops(shops):
    """Takes shops beyond the plan's limit offline. Their files and data stay; resume_shop brings them back."""
    for shop in shops:
        with transaction.atomic():
            shop = Shop.objects.select_for_update().get(pk=shop.pk)
            if shop.status == Shop.Status.SUSPENDED:
                continue
            shop.transition_to(Shop.Status.SUSPENDED)
            transaction.on_commit(lambda shop_id=shop.pk: suspend_shop.delay(shop_id))


def resume_shop(shop):
    """Brings a suspended shop back when the plan has room for it."""
    with transaction.atomic():
        User.objects.select_for_update().get(pk=shop.owner_id)
        shop = Shop.objects.select_for_update().get(pk=shop.pk)
        if shop.status != Shop.Status.SUSPENDED:
            raise InvalidTransition(f"{shop.status} -> active")
        plan = active_plan(shop.owner)
        if plan is None:
            raise PlanRequired()
        _check_room(shop.owner, plan, shop.platform)
        _bring_back(shop)
    return shop


def suspended_shops(user):
    return user.shops.filter(status=Shop.Status.SUSPENDED, is_test=False).order_by("created_at", "pk")


def resume_up_to_limit(user, plan):
    """After a plan change gives room: brings back suspended shops, oldest first, as far as the plan allows."""
    resumed = []
    for shop in shops_that_fit(plan, suspended_shops(user), kept=list(counted_shops(user))):
        with transaction.atomic():
            shop = Shop.objects.select_for_update().get(pk=shop.pk)
            if shop.status == Shop.Status.SUSPENDED:
                _bring_back(shop)
                resumed.append(shop)
    return resumed


def _bring_back(shop):
    # A shop whose setup never finished comes back as failed, so it can be retried; others come back running.
    job = shop.provisioning_jobs.first()
    finished = job is not None and job.status == ProvisioningJob.Status.SUCCEEDED
    shop.transition_to(Shop.Status.ACTIVE if finished else Shop.Status.FAILED)
    if finished:
        transaction.on_commit(lambda: resume_shop_container.delay(shop.pk))


def retry_shop(shop):
    if not shop.is_test and active_plan(shop.owner) is None:
        raise PlanRequired()
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


def delete_all_shops(user):
    """
    For a deleted account: every shop of the user is torn down and then removed from the database too
    (teardown_shop does that for owners without an account). Returns the names of shops that were still live.
    Shops deleted earlier are torn down again, which is harmless, so nothing is left behind if that failed.
    """
    shops = list(Shop.objects.select_for_update().filter(owner=user).order_by("created_at", "pk"))
    # A queued shop would be picked up by the worker after its row is gone, so it has to finish like one being set up.
    setting_up = (Shop.Status.PENDING, Shop.Status.PROVISIONING)
    busy = next((shop for shop in shops if shop.status in setting_up), None)
    if busy is not None:
        raise ShopBeingSetUp(busy)
    removed = []
    for shop in shops:
        if shop.status != Shop.Status.DELETED:
            shop.transition_to(Shop.Status.DELETED)
            removed.append(shop.name)
        transaction.on_commit(lambda shop_id=shop.pk: teardown_shop.delay(shop_id))
    return removed


def _enqueue_provisioning(shop):
    job = ProvisioningJob.objects.create(shop=shop)
    ProvisioningStep.objects.bulk_create(
        ProvisioningStep(job=job, key=key, label=label, order=order)
        for order, (key, label) in enumerate(platform_info(shop.platform).steps)
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
    # Payment keys travel with the operation, not in its changes: see ShopOperation.secrets.
    changes, keys = shop_settings.split_secrets(shop_settings.normalize(changes))
    changes = shop_settings.diff(current, changes)
    region = changes.get("region", {})
    # A new country brings its time zone and standard VAT rate, unless the owner picks them too.
    if "country" in region:
        timezone_name = COUNTRY_TIMEZONES.get(region["country"])
        if "timezone" not in region and timezone_name and timezone_name != current["region"]["timezone"]:
            region["timezone"] = timezone_name
        rate = shop_settings.suggested_vat_rate(region["country"])
        if "standard_rate" not in changes.get("taxes", {}) and rate != current["taxes"]["standard_rate"]:
            changes.setdefault("taxes", {})["standard_rate"] = rate
    if not changes and not keys:
        return None
    return start_operation(
        shop, user, ShopOperation.Kind.UPDATE_SETTINGS, shop_settings.with_placeholders(changes, keys), secrets=keys,
    )


def start_backup(shop, user):
    """Queues a backup the owner asked for."""
    if not backups.enabled():
        raise BackupsDisabled()
    # Checked before the lock: a second request at the same moment stops at the operation already running.
    if backups.manual_left(shop) <= 0:
        raise BackupLimitReached()
    return start_operation(shop, user, ShopOperation.Kind.CREATE_BACKUP)


def start_restore(shop, user, backup):
    """Queues bringing the shop back to `backup` (one of its restorable backups)."""
    if not backups.enabled():
        raise BackupsDisabled()
    return start_operation(shop, user, ShopOperation.Kind.RESTORE_BACKUP, backup=backup)


def start_operation(shop, user, kind, changes=None, secrets=None, backup=None):
    with transaction.atomic():
        # Locks the shop, so two requests can't both pass the checks below.
        shop = Shop.objects.select_for_update().get(pk=shop.pk)
        if shop.status != Shop.Status.ACTIVE:
            raise ShopNotActive()
        if current_operation(shop) is not None:
            raise OperationInProgress()
        # Keys of an operation that never finished (the worker died) don't stay around either.
        shop.operations.filter(created_at__lt=timezone.now() - OPERATION_TIMEOUT).exclude(secrets="").update(secrets="")
        operation = ShopOperation.objects.create(
            shop=shop, kind=kind, changes=changes or {}, secrets=json.dumps(secrets) if secrets else "",
            backup=backup, requested_by=user,
        )
        transaction.on_commit(lambda: run_shop_operation.delay(operation.pk))
    return operation
