"""
Platform-neutral products, read from the shop's REST API each time (BaseProvisioner.read_products, read_product) and
never stored: the shop is the only place they live, and the owner may change them in the panel at any time.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

from . import history
from .models import ShopEvent
from .remote import ShopApiError

logger = logging.getLogger(__name__)

# Products per page of the list.
PAGE = 30
# The most a stock can be set to from the app; more is surely a typo.
MAX_STOCK = 999_999


class Filter:
    ALL = ""
    OUT_OF_STOCK = "out_of_stock"
    VALUES = (ALL, OUT_OF_STOCK)


@dataclass(frozen=True)
class Product:
    external_id: str
    name: str
    sku: str
    # Gross, as the customer pays it. With variants: the lowest. None when the shop has no price for it.
    price: Decimal | None
    # The price before the sale, while there is one; else None.
    regular_price: Decimal | None
    # Pieces in stock; None when the shop doesn't count them (then `in_stock` says if it sells).
    stock: int | None
    in_stock: bool
    # Customers can find and buy it.
    visible: bool
    # The main picture's address, or "".
    image: str
    # Variants (sizes, colours…) have their own prices and stock, changed in the panel for now.
    has_variants: bool


@dataclass(frozen=True)
class ProductDetail(Product):
    categories: tuple[str, ...]
    # The product's page in the shop, or "" when it has none yet (e.g. hidden).
    url: str


@dataclass(frozen=True)
class ProductPage:
    products: tuple[Product, ...]
    has_more: bool


class StockNotEditable(Exception):
    pass


def unexpected():
    return ShopApiError("Sklep odpowiedział w nieoczekiwany sposób.")


def _call(what, shop, function, *args, **kwargs):
    """Raises ShopApiError also when the answer's shape is unexpected, e.g. changed by a plugin or a newer version."""
    try:
        return function(*args, **kwargs)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        logger.warning("Unexpected answer to %s in shop %s: %r", what, shop.pk, exc)
        raise unexpected() from exc


def listing(shop, *, query="", stock_filter=Filter.ALL, page=1):
    """ProductPage, newest first; `query` looks in the names (and SKUs where the shop can)."""
    from .provisioning import get_provisioner

    provisioner = get_provisioner(shop.platform)
    return _call(
        "the product list", shop, provisioner.read_products, shop,
        query=query.strip(), stock_filter=stock_filter, offset=(page - 1) * PAGE, limit=PAGE,
    )


def read(shop, external_id):
    """ProductDetail as it is in the shop now; raises shops.remote.ShopApiError (NotInShop when it's gone)."""
    from .provisioning import get_provisioner

    return _call("a product", shop, get_provisioner(shop.platform).read_product, shop, external_id)


def set_stock(shop, external_id, quantity, actor):
    """Sets the pieces in stock (and so whether it sells) and returns the product read again."""
    from .provisioning import get_provisioner

    product = read(shop, external_id)
    if product.has_variants:
        raise StockNotEditable()
    _call("a stock change", shop, get_provisioner(shop.platform).set_product_stock, shop, product, quantity)
    changed = None
    try:
        changed = read(shop, external_id)
        return changed
    finally:
        # Done in the shop even when reading it again fails.
        history.record(
            shop, ShopEvent.Kind.PRODUCT_STOCK, actor,
            name=product.name, before=product.stock, after=changed.stock if changed is not None else quantity,
        )


def page_of(rows, limit):
    """(the first `limit` rows, whether there were more): lists are read one row past the page."""
    rows = list(rows)
    return tuple(rows[:limit]), len(rows) > limit


def gross(value):
    """A price from the shop; blank means none."""
    if value in (None, ""):
        return None
    return Decimal(str(value)).quantize(Decimal("0.01"))


def stock_count(value):
    return int(Decimal(str(value))) if value not in (None, "") else None
