"""
Start checklist on the shop screen. Steps tick themselves off from what the platform knows, plus a product count the
worker makes when the shop screen is opened.
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


STALE_AFTER = timedelta(minutes=2)
COUNT_TIMEOUT = timedelta(minutes=2)


def overview(shop):
    """Also queues what's needed to tick off the open steps."""
    checklist, _ = ShopChecklist.objects.get_or_create(shop=shop)
    hidden = checklist.hidden_at is not None
    if shop.status != Shop.Status.ACTIVE or hidden:
        return _payload(checklist, available=False, steps={}, refreshing=False)
    request_count(shop, checklist)
    steps = _steps(shop, checklist)
    refreshing = is_counting(checklist) or services.current_operation(shop) is not None
    if not steps[Step.TEST_ORDER]:
        # Refresh the order copy so the test order shows up soon.
        refreshing = sales.is_refreshing(sales.request_refresh(shop)) or refreshing
    return _payload(checklist, available=True, steps=steps, refreshing=refreshing)


def hide(shop, hidden):
    checklist, _ = ShopChecklist.objects.get_or_create(shop=shop)
    checklist.hidden_at = timezone.now() if hidden else None
    checklist.save(update_fields=["hidden_at"])


def request_count(shop, checklist):
    """Only while a product step is open and the last attempt (failed too) is older than STALE_AFTER; never twice."""
    from .tasks import count_shop_products

    if not _needs_count(shop, checklist) or is_counting(checklist):
        return
    now = timezone.now()
    if checklist.attempted_at and checklist.attempted_at > now - STALE_AFTER:
        return
    # Compare-and-set on the old value: two requests at once queue one count.
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
    """Returns False when the shop isn't active or counting failed."""
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
    values = services.get_settings(shop).values
    sections = platform_info(shop.platform).settings_sections
    steps = {}
    # Sections the app doesn't manage are set in the shop's panel and can't be checked from here.
    if "payments" in sections:
        payments = values["payments"]
        steps[Step.PAYMENTS] = any(
            payments.get(field)
            for field in ("bank_transfer_enabled", "cash_on_delivery_enabled", "przelewy24_enabled", "payu_enabled")
        )
    if "shipping" in sections:
        shipping = values["shipping"]
        steps[Step.SHIPPING] = (
            shipping["courier_enabled"] or shipping["free_shipping_enabled"] or shipping["local_pickup_enabled"]
        )
    if "documents" in sections:
        steps[Step.DOCUMENTS] = bool(values["documents"]["managed"] and values["documents"]["terms_url"])
    steps[Step.PRODUCTS] = bool(checklist.products)
    if _has_samples(shop, checklist):
        steps[Step.SAMPLE_PRODUCTS] = checklist.sample_products == 0
    steps[Step.NOTIFICATIONS] = PushDevice.objects.filter(user_id=shop.owner_id).exists()
    steps[Step.TEST_ORDER] = shop.orders.exists()
    return steps


def _has_samples(shop, checklist):
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
