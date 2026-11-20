import json
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import User

from . import backups, history, shop_settings
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

    def __init__(self, plan, platform, limit):
        super().__init__(platform, limit)
        self.plan = plan
        self.platform = platform
        self.limit = limit


class PlanRequired(Exception):
    pass


class ShopBeingSetUp(Exception):

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
    """SHOPS_BACKUP_PASSWORD is not set."""


class BackupLimitReached(Exception):
    """SHOPS_BACKUP_MANUAL_PER_DAY reached."""


def create_shop(owner, *, name, slug, platform=None, **config):
    """`platform` defaults to the template's; the serializer ensures they match."""
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
            history.record(shop, history.Kind.SHOP_CREATED, owner)
            _enqueue_provisioning(shop)
    except IntegrityError as exc:
        if "unique_slug_for_live_shops" in str(exc):
            raise SlugTaken() from exc
        raise
    return shop


def active_plan(user):
    from billing.models import Subscription

    subscription = Subscription.objects.select_related("plan").filter(user=user).first()
    return subscription.plan if subscription and subscription.allows_new_shops else None


def counted_shops(user):
    """Shops that count against the plan: not deleted, suspended or test shops (from before paid plans)."""
    return (
        user.shops.exclude(status__in=[Shop.Status.DELETED, Shop.Status.SUSPENDED])
        .filter(is_test=False)
        .order_by("created_at", "pk")
    )


def paid_shop_count(user):
    return counted_shops(user).count()


# Platforms with their own per-plan limit, and the plan field holding it.
PLATFORM_LIMIT_FIELDS = {Platform.MAGENTO: "max_magento_shops"}


def platform_limit(plan, platform):
    """None when only the plan's total limit applies."""
    field = PLATFORM_LIMIT_FIELDS.get(platform)
    return getattr(plan, field) if field else None


def platform_usage(user, plan, platform):
    """(counted shops on `platform`, limit), or None when the platform has no own limit."""
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
    `shops` (in order) that fit in the plan next to `kept`, within the total and per-platform limits.
    A shop that doesn't fit is skipped, so a later one may still fit.
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
    """Files and data stay; resume_shop brings them back."""
    for shop in shops:
        with transaction.atomic():
            shop = Shop.objects.select_for_update().get(pk=shop.pk)
            if shop.status == Shop.Status.SUSPENDED:
                continue
            shop.transition_to(Shop.Status.SUSPENDED)
            history.record(shop, history.Kind.SUSPENDED)
            transaction.on_commit(lambda shop_id=shop.pk: suspend_shop.delay(shop_id))


def resume_shop(shop, actor=None):
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
        history.record(shop, history.Kind.RESUMED, actor)
    return shop


def suspended_shops(user):
    return user.shops.filter(status=Shop.Status.SUSPENDED, is_test=False).order_by("created_at", "pk")


def resume_up_to_limit(user, plan):
    """Oldest first, as far as the plan allows."""
    resumed = []
    for shop in shops_that_fit(plan, suspended_shops(user), kept=list(counted_shops(user))):
        with transaction.atomic():
            shop = Shop.objects.select_for_update().get(pk=shop.pk)
            if shop.status == Shop.Status.SUSPENDED:
                _bring_back(shop)
                history.record(shop, history.Kind.RESUMED)
                resumed.append(shop)
    return resumed


def _bring_back(shop):
    # A shop whose setup never finished comes back as failed, so it can be retried.
    job = shop.provisioning_jobs.first()
    finished = job is not None and job.status == ProvisioningJob.Status.SUCCEEDED
    shop.transition_to(Shop.Status.ACTIVE if finished else Shop.Status.FAILED)
    if finished:
        transaction.on_commit(lambda: resume_shop_container.delay(shop.pk))


def retry_shop(shop, actor=None):
    if not shop.is_test and active_plan(shop.owner) is None:
        raise PlanRequired()
    with transaction.atomic():
        shop = Shop.objects.select_for_update().get(pk=shop.pk)
        shop.transition_to(Shop.Status.PENDING)
        _enqueue_provisioning(shop)
        history.record(shop, history.Kind.SETUP_RETRIED, actor)
    return shop


def delete_shop(shop):
    with transaction.atomic():
        shop = Shop.objects.select_for_update().get(pk=shop.pk)
        shop.transition_to(Shop.Status.DELETED)
        transaction.on_commit(lambda: teardown_shop.delay(shop.pk))


def delete_all_shops(user):
    """
    For a deleted account, inside the caller's transaction; teardown_shop then also deletes the rows.
    Returns the names of shops still live.
    Already-deleted shops are torn down again (harmless), in case that failed before.
    """
    shops = list(Shop.objects.select_for_update().filter(owner=user).order_by("created_at", "pk"))
    # A queued shop would be picked up by the worker after its row is gone, so it has to finish first.
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
    """Fills in missing sections/fields and saves them."""
    stored, _ = ShopSettings.objects.get_or_create(shop=shop)
    defaults = shop_settings.default_settings(shop)
    complete = shop_settings.complete(stored.values, defaults)
    if complete != stored.values:
        stored.values = complete
        stored.save(update_fields=["values", "updated_at"])
    return stored


def current_operation(shop):
    return (
        shop.operations.filter(
            status__in=[ShopOperation.Status.QUEUED, ShopOperation.Status.RUNNING],
            created_at__gte=timezone.now() - OPERATION_TIMEOUT,
        )
        .order_by("-created_at")
        .first()
    )


def update_settings(shop, user, changes):
    """`changes` is SettingsUpdateSerializer's validated data. Returns None when nothing would change."""
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
    if not backups.enabled():
        raise BackupsDisabled()
    # Racy before the lock, but a concurrent request stops at OperationInProgress.
    if backups.manual_left(shop) <= 0:
        raise BackupLimitReached()
    return start_operation(shop, user, ShopOperation.Kind.CREATE_BACKUP)


def start_restore(shop, user, backup):
    if not backups.enabled():
        raise BackupsDisabled()
    return start_operation(shop, user, ShopOperation.Kind.RESTORE_BACKUP, backup=backup)


def start_operation(shop, user, kind, changes=None, secrets=None, backup=None):
    with transaction.atomic():
        shop = Shop.objects.select_for_update().get(pk=shop.pk)
        if shop.status != Shop.Status.ACTIVE:
            raise ShopNotActive()
        if current_operation(shop) is not None:
            raise OperationInProgress()
        # Drop keys left by operations that never finished (the worker died).
        shop.operations.filter(created_at__lt=timezone.now() - OPERATION_TIMEOUT).exclude(secrets="").update(secrets="")
        operation = ShopOperation.objects.create(
            shop=shop, kind=kind, changes=changes or {}, secrets=json.dumps(secrets) if secrets else "",
            backup=backup, requested_by=user,
        )
        history.record_operation(operation)
        transaction.on_commit(lambda: run_shop_operation.delay(operation.pk))
    return operation
