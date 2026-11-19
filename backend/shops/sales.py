"""
Sales overview, counted from a local copy of recent orders (ShopOrder) so it opens at once even when the shop is slow.
The copy is refreshed every few minutes and when the overview is opened with stale data.
"""

import logging
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from push import messages
from push import services as push

from .models import SalesSync, Shop, ShopOrder
from .provisioning import get_provisioner

logger = logging.getLogger(__name__)

Status = ShopOrder.Status
# Placed (paid or not) and not cancelled.
SALE = (Status.NEW, Status.PROCESSING, Status.COMPLETED)
# Copy window: enough to compare 30 days with the 30 before.
KEPT_FOR = timedelta(days=90)
# Reads start this much before the cursor, for changes saved a moment late.
OVERLAP = timedelta(minutes=10)
BATCH = 500
MAX_BATCHES = 10
STALE_AFTER = timedelta(minutes=2)
# Older orders aren't pushed as new, even when they're new to the copy.
ANNOUNCED_FOR = timedelta(days=7)
REFRESH_AGAIN_AFTER = timedelta(seconds=30)
REFRESH_TIMEOUT = timedelta(minutes=2)
RECENT_ORDERS = 10
CHART_DAYS = 30
SYNC_FAILED = "Nie udało się odczytać zamówień ze sklepu. Spróbujemy ponownie za kilka minut."


def sync(shop_id):
    """Returns False when the shop isn't active, another read is under way, or reading failed (error kept)."""
    shop = Shop.objects.select_related("config").filter(pk=shop_id).first()
    if shop is None or shop.status != Shop.Status.ACTIVE:
        return False
    SalesSync.objects.get_or_create(shop=shop)
    now = timezone.now()
    oldest = now - KEPT_FOR
    with transaction.atomic():
        # Held while reading, so a concurrent read of the same shop skips instead of waiting.
        state = SalesSync.objects.select_for_update(skip_locked=True).filter(shop=shop).first()
        if state is None:
            return False
        since = max(state.cursor - OVERLAP, oldest) if state.cursor else oldest
        # The first read copies existing orders: nothing of it is news.
        announce = state.synced_at is not None
        provisioner = get_provisioner(shop.platform)
        new_sales = []
        try:
            for _ in range(MAX_BATCHES):
                orders = provisioner.read_orders(shop, since, BATCH)
                # Savepoint: a failed batch is undone alone, so the state below can still be saved.
                with transaction.atomic():
                    stored = _store(shop, [order for order in orders if order.placed_at >= oldest])
                new_sales += stored
                if orders:
                    state.cursor = max(order.changed_at for order in orders)
                    since = state.cursor
                if len(orders) < BATCH:
                    break
        except Exception:
            # Earlier batches and their cursor stay.
            logger.exception("Reading the orders of shop %s failed", shop.pk)
            state.attempted_at = timezone.now()
            state.error = SYNC_FAILED
        else:
            state.synced_at = state.attempted_at = timezone.now()
            state.error = ""
        state.save()
    if not state.error:
        ShopOrder.objects.filter(shop=shop, placed_at__lt=oldest).delete()
    recent = [order for order in new_sales if order.placed_at >= now - ANNOUNCED_FOR]
    if announce and recent:
        push.notify(shop.owner_id, messages.new_orders(shop, sorted(recent, key=lambda order: order.placed_at)))
    return not state.error


def sync_all():
    """Queues every active shop not attempted in the last half interval."""
    from .tasks import sync_shop_orders

    recent = timezone.now() - timedelta(minutes=settings.SHOP_ORDERS_SYNC_MINUTES) / 2
    shops = Shop.objects.filter(status=Shop.Status.ACTIVE).exclude(sales_sync__attempted_at__gt=recent)
    for shop_id in shops.values_list("pk", flat=True):
        sync_shop_orders.delay(shop_id)


def request_refresh(shop, *, force=False):
    """
    Queues a read if the last attempt is older than STALE_AFTER (REFRESH_AGAIN_AFTER with `force`). Failed reads
    count too, so a broken shop isn't asked on every visit. Never queues twice. Returns the SalesSync.
    """
    from .tasks import sync_shop_orders

    state, _ = SalesSync.objects.get_or_create(shop=shop)
    if shop.status != Shop.Status.ACTIVE or is_refreshing(state):
        return state
    now = timezone.now()
    if state.attempted_at and state.attempted_at > now - (REFRESH_AGAIN_AFTER if force else STALE_AFTER):
        return state
    # Compare-and-set on the old value: two requests at once queue one read.
    if SalesSync.objects.filter(pk=state.pk, requested_at=state.requested_at).update(requested_at=now):
        state.requested_at = now
        transaction.on_commit(lambda: sync_shop_orders.delay(shop.pk))
    return state


def is_refreshing(state, now=None):
    now = now or timezone.now()
    return bool(
        state.requested_at
        and state.requested_at > now - REFRESH_TIMEOUT
        and (state.attempted_at is None or state.attempted_at < state.requested_at)
    )


def overview(shop, now=None):
    """Only orders in the shop's currency count."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    first_day = today - timedelta(days=2 * CHART_DAYS - 1)
    currency = shop.config.currency
    sales = shop.orders.filter(
        placed_at__gte=timezone.make_aware(datetime.combine(first_day, time.min)), status__in=SALE, currency=currency,
    ).values_list("placed_at", "total")
    orders_by_day = defaultdict(int)
    revenue_by_day = defaultdict(lambda: Decimal("0.00"))
    for placed_at, total in sales:
        day = timezone.localdate(placed_at)
        orders_by_day[day] += 1
        revenue_by_day[day] += total

    def period(first, last):
        days = [first + timedelta(days=offset) for offset in range((last - first).days + 1)]
        orders = sum(orders_by_day.get(day, 0) for day in days)
        revenue = sum((revenue_by_day.get(day, Decimal("0.00")) for day in days), Decimal("0.00"))
        return {"orders": orders, "revenue": revenue,
                "average": (revenue / orders).quantize(Decimal("0.01"), ROUND_HALF_UP) if orders else Decimal("0.00")}

    chart_start = today - timedelta(days=CHART_DAYS - 1)
    to_handle = {status: 0 for status in (Status.NEW, Status.PROCESSING)}
    for status in shop.orders.filter(status__in=to_handle).values_list("status", flat=True):
        to_handle[status] += 1
    return {
        "currency": currency,
        "today": period(today, today),
        "last_7_days": period(today - timedelta(days=6), today),
        "last_30_days": period(chart_start, today),
        "previous_30_days": period(first_day, chart_start - timedelta(days=1)),
        "daily": [
            {"date": day, "orders": orders_by_day.get(day, 0), "revenue": revenue_by_day.get(day, Decimal("0.00"))}
            for day in (chart_start + timedelta(days=offset) for offset in range(CHART_DAYS))
        ],
        "to_handle": {"new": to_handle[Status.NEW], "processing": to_handle[Status.PROCESSING]},
        "recent": list(shop.orders.exclude(status=Status.UNFINISHED)[:RECENT_ORDERS]),
    }


def _store(shop, orders):
    """Upserts; returns orders that just became sales (unseen before, or unpaid until now)."""
    # An upsert may not touch the same row twice.
    orders = list({order.external_id: order for order in orders}.values())
    if not orders:
        return []
    known = dict(
        shop.orders.filter(external_id__in=[order.external_id[:40] for order in orders])
        .values_list("external_id", "status")
    )
    ShopOrder.objects.bulk_create(
        [
            ShopOrder(
                shop=shop, external_id=order.external_id[:40], number=order.number[:40], status=order.status,
                total=order.total, currency=order.currency[:3], items=order.items, customer=order.customer[:80],
                placed_at=order.placed_at, changed_at=order.changed_at,
            )
            for order in orders
        ],
        update_conflicts=True,
        unique_fields=["shop", "external_id"],
        update_fields=["number", "status", "total", "currency", "items", "customer", "placed_at", "changed_at"],
    )
    return [
        order for order in orders
        if order.status in SALE and known.get(order.external_id[:40], Status.UNFINISHED) == Status.UNFINISHED
    ]
