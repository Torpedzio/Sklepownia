"""WooCommerce products through its REST API (wc/v3), mixed into WooCommerceProvisioner."""

from ..products import (
    Category, Filter, Product, ProductDetail, ProductPage, description_markup, description_text, gross, page_of,
    stock_count,
)
from ..remote import NotInShop

# Product types whose own stock the app sets; variable and grouped ones keep it in their parts, external ones have none.
COUNTED_TYPES = {"simple"}
SELLING = {"instock", "onbackorder"}


class WooCommerceProducts:
    def read_products(self, shop, *, query, stock_filter, offset, limit):
        params = {
            # Drafts and private ones too: the owner looks for every product, not only what customers see.
            "status": "any", "orderby": "date", "order": "desc", "offset": offset, "per_page": limit + 1,
        }
        if query:
            params["search"] = query
        if stock_filter == Filter.OUT_OF_STOCK:
            params["stock_status"] = "outofstock"
        rows, has_more = page_of(self.api(shop).get("products", params), limit)
        return ProductPage(products=tuple(_product(row) for row in rows), has_more=has_more)

    def read_product(self, shop, external_id):
        row = self.api(shop).get(f"products/{int(external_id)}")
        if row.get("status") == "trash":
            # Deleted from the app or the panel: in the trash only the panel can bring it back.
            raise NotInShop("Nie ma tego produktu w sklepie.")
        product = _product(row)
        description, formatted = description_text(row.get("description"))
        return ProductDetail(
            **vars(product),
            categories=tuple(
                Category(str(category["id"]), category.get("name") or "") for category in row.get("categories") or []
            ),
            # A draft's permalink is a preview link that needs the panel's login.
            url=(row.get("permalink") or "") if row.get("status") == "publish" else "",
            description=description,
            formatted_description=formatted,
        )

    def read_categories(self, shop):
        rows = self.api(shop).get("products/categories", {"per_page": 100, "orderby": "name", "hide_empty": False})
        return tuple(Category(str(row["id"]), row.get("name") or "") for row in rows)

    def update_product(self, shop, product, changes):
        self.api(shop).put(f"products/{int(product.external_id)}", json=_body(changes))

    def create_product(self, shop, fields):
        body = {"type": "simple", "status": "publish", **_body(fields)}
        if fields.get("stock") is not None:
            body.update(manage_stock=True, stock_quantity=fields["stock"])
        return str(self.api(shop).post("products", json=body)["id"])

    def delete_product(self, shop, product):
        # To the bin, from which the panel can bring it back for 30 days.
        self.api(shop).delete(f"products/{int(product.external_id)}")

    def set_product_stock(self, shop, product, quantity):
        # WooCommerce sets "in stock" or "out of stock" from the count.
        self.api(shop).put(
            f"products/{int(product.external_id)}", json={"manage_stock": True, "stock_quantity": quantity},
        )


def _product(row):
    on_sale = bool(row.get("on_sale")) and row.get("type") in COUNTED_TYPES
    images = row.get("images") or []
    return Product(
        external_id=str(row["id"]),
        name=row.get("name") or "",
        sku=row.get("sku") or "",
        # As entered in the shop: gross when the shop enters prices with tax, as set up by the platform.
        price=gross(row.get("price")),
        regular_price=gross(row.get("regular_price")) if on_sale else None,
        stock=stock_count(row.get("stock_quantity")) if row.get("manage_stock") is True else None,
        in_stock=row.get("stock_status") in SELLING,
        visible=row.get("status") == "publish" and row.get("catalog_visibility") != "hidden",
        image=(images[0].get("src") or "") if images else "",
        has_variants=row.get("type") not in COUNTED_TYPES,
    )


def _body(fields):
    """The REST API's fields for the app's (prices as entered in the shop, which the platform sets gross)."""
    body = {}
    if "name" in fields:
        body["name"] = fields["name"]
    if "price" in fields:
        body["regular_price"] = _price(fields["price"])
    if "sale_price" in fields:
        # Empty ends the sale.
        body["sale_price"] = _price(fields["sale_price"])
    if "sku" in fields:
        body["sku"] = fields["sku"]
    if "description" in fields:
        body["description"] = description_markup(fields["description"])
    if "categories" in fields:
        body["categories"] = [{"id": int(id)} for id in fields["categories"]]
    if "visible" in fields:
        # A draft is hidden from customers; a product hidden only from the catalogue comes back with it.
        body["status"] = "publish" if fields["visible"] else "draft"
        if fields["visible"]:
            body["catalog_visibility"] = "visible"
    return body


def _price(value):
    return "" if value is None else f"{value:.2f}"
