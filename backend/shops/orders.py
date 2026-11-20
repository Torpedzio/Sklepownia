"""
Platform-neutral orders: Order from BaseProvisioner.read_orders, before it's stored as ShopOrder, and OrderDetail from
BaseProvisioner.read_order, read from the shop each time and never stored.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from django.db.models import Q

from . import history
from .choices import Country
from .models import ShopEvent, ShopOrder

logger = logging.getLogger(__name__)

Status = ShopOrder.Status
# Orders per page of the list.
PAGE = 30


@dataclass(frozen=True)
class Order:
    external_id: str
    number: str
    status: str
    total: Decimal
    currency: str
    items: int
    customer: str
    placed_at: datetime
    changed_at: datetime


@dataclass(frozen=True)
class Address:
    name: str
    company: str
    # Street, building and flat, as typed.
    lines: tuple[str, ...]
    postcode: str
    city: str
    # The country's name, or its ISO code when the app doesn't know it.
    country: str
    phone: str


@dataclass(frozen=True)
class OrderLine:
    name: str
    sku: str
    quantity: int
    # Gross, before the order's discount.
    price: Decimal
    total: Decimal


@dataclass(frozen=True)
class OrderDetail:
    external_id: str
    number: str
    status: str
    currency: str
    # Gross amounts; products and shipping before the discount, the total as the customer pays it.
    products_total: Decimal
    shipping_total: Decimal
    discount_total: Decimal
    total: Decimal
    payment_method: str
    shipping_method: str
    customer_name: str
    email: str
    phone: str
    billing: Address | None
    shipping: Address | None
    lines: tuple[OrderLine, ...]
    # What the customer wrote when ordering.
    customer_note: str
    placed_at: datetime
    # The parcel's number for the customer, when the shop has one.
    tracking_number: str = ""
    carrier: str = ""
    # What can be done with the order now (Action values), in this order.
    actions: tuple[str, ...] = ()


class Action:
    MARK_PAID = "mark_paid"
    MARK_SHIPPED = "mark_shipped"
    CANCEL = "cancel"

    # Done once: the history's kind and, as the order's new status, what the app shows.
    KINDS = {
        MARK_PAID: ShopEvent.Kind.ORDER_PAID,
        MARK_SHIPPED: ShopEvent.Kind.ORDER_SHIPPED,
        CANCEL: ShopEvent.Kind.ORDER_CANCELLED,
    }
    ALL = (MARK_PAID, MARK_SHIPPED, CANCEL)


class ActionNotAllowed(Exception):
    pass


def actions_for(status, *, can_cancel=True):
    """What an order in `status` can go through; a platform may refuse to cancel (e.g. Magento once invoiced)."""
    actions = {
        Status.NEW: (Action.MARK_PAID, Action.MARK_SHIPPED, Action.CANCEL),
        Status.PROCESSING: (Action.MARK_SHIPPED, Action.CANCEL),
        Status.UNFINISHED: (Action.CANCEL,),
    }.get(status, ())
    return tuple(action for action in actions if can_cancel or action != Action.CANCEL)


def listing(shop, *, status="", query="", before=None):
    """(Orders from the local copy, newest first, more_after_these) for one page; `before`: the last order shown."""
    orders = shop.orders.all()
    if status:
        orders = orders.filter(status=status)
    query = query.strip().lstrip("#")
    if query:
        orders = orders.filter(Q(number__icontains=query) | Q(customer__icontains=query))
    if before is not None:
        orders = orders.filter(Q(placed_at__lt=before.placed_at) | Q(placed_at=before.placed_at, id__lt=before.id))
    page = list(orders[:PAGE + 1])
    return page[:PAGE], len(page) > PAGE


def read(shop, external_id):
    """The order as it is in the shop now (raises shops.remote.ShopApiError); the local copy takes its status."""
    from .provisioning import get_provisioner

    try:
        order = get_provisioner(shop.platform).read_order(shop, external_id)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        # A plugin or a newer platform version changed the answer's shape.
        logger.warning("Unexpected order from shop %s: %r", shop.pk, exc)
        raise _unexpected() from exc
    ShopOrder.objects.filter(shop=shop, external_id=order.external_id).exclude(status=order.status).update(
        status=order.status,
    )
    return order


def change(shop, external_id, action, actor, *, tracking_number="", carrier=""):
    """
    Does `action` in the shop and returns the order as it is afterwards. Raises ActionNotAllowed when the order (read
    just before) doesn't offer it, shops.remote.ShopApiError when the shop fails.
    """
    from .provisioning import get_provisioner

    order = read(shop, external_id)
    if action not in order.actions:
        raise ActionNotAllowed(action)
    provisioner = get_provisioner(shop.platform)
    try:
        provisioner.change_order(shop, order, action, tracking_number=tracking_number, carrier=carrier)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        logger.warning("Unexpected answer to %s of order %s in shop %s: %r", action, external_id, shop.pk, exc)
        raise _unexpected() from exc
    changed = None
    try:
        changed = read(shop, external_id)
        return changed
    finally:
        # Done in the shop even when reading it again fails. The parcel as the shop keeps it: PrestaShop, e.g., ships
        # with the order's own carrier, not the one typed in.
        data = {"number": order.number}
        if action == Action.MARK_SHIPPED and tracking_number:
            kept = changed if changed is not None and changed.tracking_number else None
            data.update(
                tracking_number=kept.tracking_number if kept else tracking_number,
                carrier=kept.carrier if kept else carrier,
            )
        history.record(shop, Action.KINDS[action], actor, **data)


# What the customer reads about the parcel, in the shop's language.
SHIPPED_NOTE = {
    "pl_PL": "Zamówienie zostało wysłane. Numer przesyłki: {tracking}.",
    "en_US": "Your order has been shipped. Tracking number: {tracking}.",
    "de_DE": "Ihre Bestellung wurde versandt. Sendungsnummer: {tracking}.",
}


def shipped_note(shop, tracking_number, carrier=""):
    tracking = f"{tracking_number} ({carrier})" if carrier else tracking_number
    language = getattr(getattr(shop, "config", None), "language", "pl_PL")
    return SHIPPED_NOTE.get(language, SHIPPED_NOTE["pl_PL"]).format(tracking=tracking)


def notes(shop, external_id):
    return shop.order_notes.filter(external_id=str(external_id)).select_related("author")


def amount(value):
    """A number from the platform's API as money; not a number counts as 0."""
    try:
        return Decimal(str(value if value not in (None, "") else 0)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return Decimal("0.00")


def _unexpected():
    from .remote import ShopApiError

    return ShopApiError("Sklep odpowiedział w nieoczekiwany sposób.")


def quantity(value):
    try:
        return int(Decimal(str(value or 0)))
    except (InvalidOperation, ValueError):
        return 0


def country_name(code):
    code = (code or "").upper()
    return Country(code).label if code in Country.values else code


def full_name(first_name, last_name):
    return " ".join(part.strip() for part in (first_name or "", last_name or "") if part and part.strip())


def customer_label(first_name, last_name):
    """"Anna N.": the customer's full name is never copied."""
    first = (first_name or "").strip()
    last = (last_name or "").strip()
    return f"{first} {last[0]}.".strip() if last else first


def from_timestamp(value):
    return datetime.fromtimestamp(int(value), tz=UTC)
