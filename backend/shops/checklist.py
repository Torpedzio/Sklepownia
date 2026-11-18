"""
The start checklist on the shop screen: what a new shop still needs before it sells. Every step ticks itself off,
from what the platform already knows (the settings, the copy of the orders, the owner's phones) and from a count of
the shop's products, which the worker makes when the owner opens the shop screen.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from push.models import PushDevice

from . import sales, services
from .models import Shop, ShopChecklist
from .platforms import platform_info
from .provisioning import get_provisioner

logger = logging.getLogger(__name__)

Step = ShopChecklist.Step


# Opening the shop screen counts the products again when the last count is older than this.
STALE_AFTER = timedelta(minutes=2)
# A queued count that hasn't finished by then is not waited for any more.
COUNT_TIMEOUT = timedelta(minutes=2)


def overview(shop):
    """What the app shows. Opening it queues what's needed to tick off the steps that aren't done yet."""
    checklist, _ = ShopChecklist.objects.get_or_create(shop=shop)
    hidden = checklist.hidden_at is not None
    if shop.status != Shop.Status.ACTIVE or hidden:
        return _payload(checklist, available=False, steps={}, refreshing=False)
    request_count(shop, checklist)
    steps = _steps(shop, checklist)
    refreshing = is_counting(checklist) or services.current_operation(shop) is not None
    if not steps[Step.TEST_ORDER]:
        # The copy of the orders is read like for the sales overview, so the test order shows up soon after.
        refreshing = sales.is_refreshing(sales.request_refresh(shop)) or refreshing
    return _payload(checklist, available=True, steps=steps, refreshing=refreshing)


def hide(shop, hidden):
    checklist, _ = ShopChecklist.objects.get_or_create(shop=shop)
    checklist.hidden_at = timezone.now() if hidden else None
    checklist.save(update_fields=["hidden_at"])


def request_count(shop, checklist):
    """
    Queues counting the shop's products while a product step is still open and the last count was a while ago
    (a failed one too, so a broken shop isn't asked on every visit). Nothing is queued twice.
    """
    from .tasks import count_shop_products

    if not _needs_count(shop, checklist) or is_counting(checklist):
        return
    now = timezone.now()
    if checklist.attempted_at and checklist.attempted_at > now - STALE_AFTER:
        return
    # Claimed with the old value: two requests at once queue one count.
    if ShopChecklist.objects.filter(pk=checklist.pk, requested_at=checklist.requested_at).update(requested_at=now):
        checklist.requested_at = now
        transaction.on_commit(lambda: count_shop_products.delay(shop.pk))


def is_counting(checklist, now=None):
    now = now or timezone.now()
    return bool(
        checklist.requested_at
        and checklist.requested_at > now - COUNT_TIMEOUT
        and (checklist.attempted_at is None or checklist.attempted_at < checklist.requested_at)
    )


def count(shop_id):
    """Counts the shop's products (in the worker). Returns False when the shop isn't running or counting failed."""
    shop = Shop.objects.select_related("config").filter(pk=shop_id).first()
    if shop is None or shop.status != Shop.Status.ACTIVE:
        return False
    checklist, _ = ShopChecklist.objects.get_or_create(shop=shop)
    try:
        counted = get_provisioner(shop.platform).count_products(shop)
    except Exception:
        logger.exception("Counting the products of shop %s failed", shop.pk)
        ShopChecklist.objects.filter(pk=checklist.pk).update(attempted_at=timezone.now())
        return False
    now = timezone.now()
    ShopChecklist.objects.filter(pk=checklist.pk).update(
        products=counted.products, sample_products=counted.samples, counted_at=now, attempted_at=now,
    )
    return True


def _steps(shop, checklist):
    """{step: done} of the steps that apply to the shop, in order."""
    values = services.get_settings(shop).values
    sections = platform_info(shop.platform).settings_sections
    steps = {}
    # Where the app can't change a setting, it's set in the shop's panel and can't be checked from here.
    if "payments" in sections:
        payments = values["payments"]
        steps[Step.PAYMENTS] = payments["bank_transfer_enabled"] or payments["cash_on_delivery_enabled"]
    if "shipping" in sections:
        shipping = values["shipping"]
        steps[Step.SHIPPING] = (
            shipping["courier_enabled"] or shipping["free_shipping_enabled"] or shipping["local_pickup_enabled"]
        )
    steps[Step.PRODUCTS] = bool(checklist.products)
    if _has_samples(shop, checklist):
        steps[Step.SAMPLE_PRODUCTS] = checklist.sample_products == 0
    steps[Step.NOTIFICATIONS] = PushDevice.objects.filter(user_id=shop.owner_id).exists()
    steps[Step.TEST_ORDER] = shop.orders.exists()
    return steps


def _has_samples(shop, checklist):
    """The shop got sample products at setup, or some were counted in it."""
    return shop.config.include_sample_products or bool(checklist.sample_products)


def _needs_count(shop, checklist):
    samples_left = _has_samples(shop, checklist) and checklist.sample_products != 0
    return not checklist.products or samples_left


def _payload(checklist, *, available, steps, refreshing):
    return {
        "available": available,
        "hidden": checklist.hidden_at is not None,
        "steps": [{"key": key, "done": bool(done)} for key, done in steps.items()],
        "products": checklist.products,
        "sample_products": checklist.sample_products,
        "counted_at": checklist.counted_at,
        "refreshing": refreshing,
    }
