"""
Platform-neutral products, read from the shop's REST API each time (BaseProvisioner.read_products, read_product) and
never stored: the shop is the only place they live, and the owner may change them in the panel at any time.
"""

import html
import logging
import re
from dataclasses import dataclass
from decimal import Decimal

from django.utils.text import slugify

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
class Category:
    id: str
    name: str


@dataclass(frozen=True)
class ProductDetail(Product):
    categories: tuple[Category, ...]
    # The product's page in the shop, or "" when it has none yet (e.g. hidden).
    url: str
    # As plain text, paragraphs apart by a blank line.
    description: str = ""
    # The shop's description has formatting (lists, bold…) that saving it from the app drops.
    formatted_description: bool = False


@dataclass(frozen=True)
class ProductPage:
    products: tuple[Product, ...]
    has_more: bool


class StockNotEditable(Exception):
    pass


class PriceOfVariants(Exception):
    """Variants have their own prices."""


class SaleNotBelowPrice(Exception):
    pass


# What the app changes in a product, with the history's names for them; `stock` only when adding one.
FIELDS = {
    "name": "Nazwa",
    "price": "Cena",
    "sale_price": "Cena promocyjna",
    "sku": "SKU",
    "description": "Opis",
    "categories": "Kategorie",
    "visible": "Widoczność",
}
PRICE_FIELDS = ("price", "sale_price")


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


def categories(shop):
    """The shop's product categories (Category), in the shop's order, without the root ones every product is in."""
    from .provisioning import get_provisioner

    return _call("the categories", shop, get_provisioner(shop.platform).read_categories, shop)


def update(shop, external_id, changes, actor):
    """
    Saves `changes` ({field in FIELDS: value}; `sale_price` None ends the sale) and returns the product read again.
    Fields equal to what the shop has are left out, so a form sent whole changes only what was edited.
    """
    from .provisioning import get_provisioner

    product = read(shop, external_id)
    changes = {name: value for name, value in changes.items() if value != _current(product, name)}
    if not changes:
        return product
    if product.has_variants and any(name in changes for name in PRICE_FIELDS):
        raise PriceOfVariants()
    price = changes.get("price", _current(product, "price"))
    sale = changes.get("sale_price", _current(product, "sale_price"))
    if sale is not None and (price is None or sale >= price):
        raise SaleNotBelowPrice()
    edited = [label for name, label in FIELDS.items() if name in changes]
    if "sale_price" not in changes and "price" in changes and sale is not None:
        # The sale price stays as it was; PrestaShop keeps a sale as an amount off the price, so it's sent again.
        changes["sale_price"] = sale
    _call("a product change", shop, get_provisioner(shop.platform).update_product, shop, product, changes)
    changed = None
    try:
        changed = read(shop, external_id)
        return changed
    finally:
        history.record(
            shop, ShopEvent.Kind.PRODUCT_UPDATED, actor,
            name=changed.name if changed is not None else changes.get("name", product.name),
            fields=edited,
        )


def create(shop, fields, actor):
    """
    A simple product from `fields` (name and price required; sku, description, categories, visible, sale_price,
    stock optional) and returns it as read from the shop.
    """
    from .provisioning import get_provisioner

    if fields.get("sale_price") is not None and fields["sale_price"] >= fields["price"]:
        raise SaleNotBelowPrice()
    external_id = _call("a new product", shop, get_provisioner(shop.platform).create_product, shop, fields)
    history.record(shop, ShopEvent.Kind.PRODUCT_CREATED, actor, name=fields["name"])
    return read(shop, external_id)


def delete(shop, external_id, actor):
    from .provisioning import get_provisioner

    product = read(shop, external_id)
    _call("a product deletion", shop, get_provisioner(shop.platform).delete_product, shop, product)
    history.record(shop, ShopEvent.Kind.PRODUCT_DELETED, actor, name=product.name)


def _current(product, name):
    """The product's value of a FIELDS name, as it would come in changes."""
    if name == "price":
        return product.regular_price if product.regular_price is not None else product.price
    if name == "sale_price":
        return product.price if product.regular_price is not None else None
    if name == "categories":
        return [category.id for category in product.categories]
    return getattr(product, name)


# Tags that only make paragraphs and lines, which the plain text keeps.
PLAIN_TAGS = re.compile(r"</?(p|br|div|span)(\s[^>]*)?/?>", re.IGNORECASE)


def description_text(markup):
    """(plain text, whether the markup had more formatting than paragraphs)."""
    markup = markup or ""
    formatted = bool(re.search(r"<[a-zA-Z]", PLAIN_TAGS.sub("", markup)))
    text = re.sub(r"<br\s*/?>", "\n", markup, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|h\d|ul|ol|table)>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(li|tr)>", "\n", text, flags=re.IGNORECASE)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    lines = [line.strip() for line in text.replace("\r", "").split("\n")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text, formatted


def description_markup(text):
    """Paragraphs for the shop: a blank line starts a new one, a single line break stays a break."""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", (text or "").strip()) if part.strip()]
    return "".join(
        "<p>" + "<br>".join(html.escape(line.strip()) for line in paragraph.split("\n")) + "</p>"
        for paragraph in paragraphs
    )


def url_slug(text):
    """A product's address in the shop, from its name ("Łyżka drewniana" → "lyzka-drewniana")."""
    # Django's slugify drops "ł", which doesn't decompose into a letter and a mark.
    return slugify(text.replace("ł", "l").replace("Ł", "L"))


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
