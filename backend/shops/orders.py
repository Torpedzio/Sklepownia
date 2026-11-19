"""Platform-neutral orders from BaseProvisioner.read_orders, before they're stored as ShopOrder."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from .models import ShopOrder

Status = ShopOrder.Status


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


def customer_label(first_name, last_name):
    """"Anna N.": the customer's full name is never copied."""
    first = (first_name or "").strip()
    last = (last_name or "").strip()
    return f"{first} {last[0]}.".strip() if last else first


def from_timestamp(value):
    return datetime.fromtimestamp(int(value), tz=UTC)
