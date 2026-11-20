"""Magento products through its REST API, mixed into MagentoProvisioner. Stock is kept by the inventory (MSI) source."""

import secrets
from datetime import date
from urllib.parse import quote

from ..products import (
    Category, Filter, Product, ProductDetail, ProductPage, description_markup, description_text, gross, stock_count,
    url_slug,
)
from ..remote import NotInShop

# The single source of a shop the platform set up.
SOURCE = "default"
# Types whose own stock the app sets: configurable, bundle and grouped ones count it in their parts.
COUNTED_TYPES = {"simple", "virtual"}
NOT_VISIBLE_INDIVIDUALLY = 1
ENABLED = 1
DISABLED = 2
CATALOG_AND_SEARCH = 4
# Magento's default attribute set for products, and the main website.
DEFAULT_ATTRIBUTE_SET = 4
MAIN_WEBSITE = 1
# The tree's root and the store's root category, which every category is under.
ROOT_LEVELS = 1
# The most sold-out products the filter looks through.
MAX_SOLD_OUT = 1000


class MagentoProducts:
    def read_products(self, shop, *, query, stock_filter, offset, limit):
        api = self.api(shop)
        criteria = Criteria()
        criteria.sort("entity_id", "DESC")
        if query:
            criteria.any([("name", f"%{query}%", "like"), ("sku", f"%{query}%", "like")])
        if stock_filter == Filter.OUT_OF_STOCK:
            sold_out = api.get("inventory/source-items", Criteria().where("source_code", SOURCE).where(
                "quantity", 0, "lteq").page(MAX_SOLD_OUT, 1).params).get("items") or []
            if not sold_out:
                return ProductPage(products=(), has_more=False)
            criteria.where("sku", ",".join(item["sku"] for item in sold_out), "in")
        # Pages of the list are whole pages of Magento's.
        body = api.get("products", criteria.page(limit, offset // limit + 1).params)
        rows = body.get("items") or []
        stock = self._stock(api, [row["sku"] for row in rows])
        return ProductPage(
            products=tuple(_product(shop, row, stock) for row in rows),
            has_more=int(body.get("total_count") or 0) > offset + len(rows),
        )

    def read_product(self, shop, external_id):
        api = self.api(shop)
        # By id: the API's own product address takes the SKU, which the owner may change.
        rows = api.get("products", Criteria().where("entity_id", int(external_id)).page(1, 1).params).get("items")
        if not rows:
            raise NotInShop("Nie ma tego produktu w sklepie.")
        row = rows[0]
        product = _product(shop, row, self._stock(api, [row["sku"]]))
        attributes = _attributes(row)
        description, formatted = description_text(attributes.get("description"))
        return ProductDetail(
            **vars(product),
            categories=self._categories(api, row),
            # The default URL suffix of product pages.
            url=f"{shop.url}/{attributes['url_key']}.html" if product.visible and attributes.get("url_key") else "",
            description=description,
            formatted_description=formatted,
        )

    def read_categories(self, shop):
        """The tree, depth first, below the store's root category."""
        found = []

        def walk(node):
            if int(node.get("level") or 0) > ROOT_LEVELS:
                found.append(Category(str(node["id"]), node.get("name") or ""))
            for child in node.get("children_data") or []:
                walk(child)

        walk(self.api(shop).get("categories"))
        return tuple(found)

    def update_product(self, shop, product, changes):
        api = self.api(shop)
        body = {**_body(changes), "id": int(product.external_id)}
        body.setdefault("sku", product.sku)
        # Saved by id, not PUT products/{sku}: the API puts the address's SKU over the one sent, so a new SKU
        # wouldn't be saved, and it refuses SKUs with a slash in the address.
        api.post("products", json={"product": body})
        if "sale_price" in changes and changes["sale_price"] is None:
            # An empty special price isn't saved through the product; the price API removes it.
            self._end_sale(api, body["sku"])

    def create_product(self, shop, fields):
        api = self.api(shop)
        name = url_slug(fields["name"])[:40] or "produkt"
        sku = fields.get("sku") or f"{name}-{secrets.token_hex(3)}"
        body = {
            "sku": sku, "attribute_set_id": DEFAULT_ATTRIBUTE_SET, "type_id": "simple", "visibility": CATALOG_AND_SEARCH,
            "status": ENABLED, **_body(fields),
        }
        body["extension_attributes"] = {**body.get("extension_attributes", {}), "website_ids": [MAIN_WEBSITE]}
        # A unique page address: the name's with the SKU, so two products may share a name.
        body.setdefault("custom_attributes", []).append(
            {"attribute_code": "url_key", "value": url_slug(sku) if not fields.get("sku") else f"{name}-{url_slug(sku)}"},
        )
        created = api.post("products", json={"product": body})
        # Always: without the source's row the product has no stock to sell from.
        self.set_product_stock(shop, _sku_only(sku), fields.get("stock") or 0)
        return str(created["id"])

    def delete_product(self, shop, product):
        api = self.api(shop)
        sku = product.sku
        if "/" in sku:
            # Deleted only by SKU, and the address refuses a slash in it: it is renamed first.
            sku = f"usuwany-{int(product.external_id)}"
            api.post("products", json={"product": {"id": int(product.external_id), "sku": sku}})
        api.delete(f"products/{quote(sku, safe='')}")

    @staticmethod
    def _end_sale(api, sku):
        rows = api.post("products/special-price-information", json={"skus": [sku]}) or []
        if rows:
            api.post("products/special-price-delete", json={"prices": rows})

    def set_product_stock(self, shop, product, quantity):
        self.api(shop).post("inventory/source-items", json={"sourceItems": [{
            "sku": product.sku, "source_code": SOURCE, "quantity": quantity, "status": 1 if quantity > 0 else 0,
        }]})

    @staticmethod
    def _stock(api, skus):
        """{sku: (pieces, sells)} from the shop's source."""
        if not skus:
            return {}
        items = api.get("inventory/source-items", Criteria().where("source_code", SOURCE).where(
            "sku", ",".join(skus), "in").page(len(skus), 1).params).get("items") or []
        return {item["sku"]: (stock_count(item.get("quantity")), item.get("status") == 1) for item in items}

    @staticmethod
    def _categories(api, row):
        ids = [str(id) for id in _attributes(row).get("category_ids") or []]
        if not ids:
            return ()
        items = api.get("categories/list", Criteria().where("entity_id", ",".join(ids), "in").page(
            len(ids), 1).params).get("items") or []
        names = {str(item["id"]): item.get("name") or "" for item in items}
        return tuple(Category(id, names[id]) for id in ids if names.get(id))


class Criteria:
    """Magento's searchCriteria as query parameters: each `where` is ANDed, the filters of one `any` are ORed."""

    def __init__(self):
        self.params = {}
        self.groups = 0

    def where(self, field, value, condition="eq"):
        return self.any([(field, value, condition)])

    def any(self, filters):
        for index, (field, value, condition) in enumerate(filters):
            prefix = f"searchCriteria[filterGroups][{self.groups}][filters][{index}]"
            self.params.update({
                f"{prefix}[field]": field, f"{prefix}[value]": value, f"{prefix}[condition_type]": condition,
            })
        self.groups += 1
        return self

    def sort(self, field, direction):
        self.params.update({
            "searchCriteria[sortOrders][0][field]": field, "searchCriteria[sortOrders][0][direction]": direction,
        })
        return self

    def page(self, size, number):
        self.params.update({"searchCriteria[pageSize]": size, "searchCriteria[currentPage]": number})
        return self


def _attributes(row):
    return {item["attribute_code"]: item.get("value") for item in row.get("custom_attributes") or []}


def _product(shop, row, stock):
    attributes = _attributes(row)
    price = gross(row.get("price"))
    special = gross(attributes.get("special_price"))
    on_sale = special is not None and price is not None and special < price and _in_dates(attributes)
    count, sells = stock.get(row["sku"], (None, False))
    image = next(
        (attributes[name] for name in ("thumbnail", "small_image", "image")
         if attributes.get(name) and attributes[name] != "no_selection"),
        "",
    )
    return Product(
        external_id=str(row["id"]),
        name=row.get("name") or "",
        sku=row["sku"],
        # As entered in the shop: gross when the shop enters prices with tax, as set up by the platform.
        price=special if on_sale else price,
        regular_price=price if on_sale else None,
        stock=count,
        in_stock=sells,
        visible=row.get("status") == ENABLED and row.get("visibility") != NOT_VISIBLE_INDIVIDUALLY,
        image=f"{shop.url}/media/catalog/product{image}" if image else "",
        has_variants=row.get("type_id") not in COUNTED_TYPES,
    )


def _in_dates(attributes):
    """A special price counts between its dates, when they are set ("2026-11-20 00:00:00")."""
    today = date.today().isoformat()
    start = (attributes.get("special_from_date") or "")[:10]
    end = (attributes.get("special_to_date") or "")[:10]
    return (not start or start <= today) and (not end or today <= end)


def _body(fields):
    """The product's fields in the REST API for the app's; prices as entered, gross as the platform sets it."""
    body, attributes = {}, []
    if "name" in fields:
        body["name"] = fields["name"]
    if "price" in fields:
        body["price"] = float(fields["price"])
    if fields.get("sale_price") is not None:
        attributes.append({"attribute_code": "special_price", "value": str(fields["sale_price"])})
    if "sku" in fields and fields["sku"]:
        body["sku"] = fields["sku"]
    if "description" in fields:
        attributes.append({"attribute_code": "description", "value": description_markup(fields["description"])})
    if "categories" in fields:
        body["extension_attributes"] = {"category_links": [
            {"position": index, "category_id": str(id)} for index, id in enumerate(fields["categories"])
        ]}
    if "visible" in fields:
        body["status"] = ENABLED if fields["visible"] else DISABLED
    if attributes:
        body["custom_attributes"] = attributes
    return body




class _sku_only:
    """What set_product_stock needs of a product just made."""

    def __init__(self, sku):
        self.sku = sku
