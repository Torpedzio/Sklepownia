"""Magento products through its REST API, mixed into MagentoProvisioner. Stock is kept by the inventory (MSI) source."""

from datetime import date

from ..products import Filter, Product, ProductDetail, ProductPage, gross, stock_count
from ..remote import NotInShop

# The single source of a shop the platform set up.
SOURCE = "default"
# Types whose own stock the app sets: configurable, bundle and grouped ones count it in their parts.
COUNTED_TYPES = {"simple", "virtual"}
NOT_VISIBLE_INDIVIDUALLY = 1
ENABLED = 1
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
        url_key = _attributes(row).get("url_key")
        return ProductDetail(
            **vars(product),
            categories=self._categories(api, row),
            # The default URL suffix of product pages.
            url=f"{shop.url}/{url_key}.html" if product.visible and url_key else "",
        )

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
        return tuple(names[id] for id in ids if names.get(id))


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
