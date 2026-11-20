"""
Platform-neutral orders: Order from BaseProvisioner.read_orders, before it's stored as ShopOrder, and OrderDetail from
BaseProvisioner.read_order, read from the shop each time and never stored.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from django.db.models import Q

from .choices import Country
from .models import ShopOrder

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
    from .remote import ShopApiError

    try:
        order = get_provisioner(shop.platform).read_order(shop, external_id)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        # A plugin or a newer platform version changed the answer's shape.
        logger.warning("Unexpected order from shop %s: %r", shop.pk, exc)
        raise ShopApiError("Sklep odpowiedział w nieoczekiwany sposób.") from exc
    ShopOrder.objects.filter(shop=shop, external_id=order.external_id).exclude(status=order.status).update(
        status=order.status,
    )
    return order


def amount(value):
    """A number from the platform's API as money; not a number counts as 0."""
    try:
        return Decimal(str(value if value not in (None, "") else 0)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return Decimal("0.00")


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
