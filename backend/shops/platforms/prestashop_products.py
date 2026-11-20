"""PrestaShop products through its webservice, mixed into PrestaShopProvisioner."""

from ..products import Filter, Product, ProductDetail, ProductPage, gross, page_of, stock_count
from ..remote import NotInShop

# The webservice works the price out as the shop does: gross, and `final` after the sale.
PRICES = {"price[final][use_tax]": "1", "price[regular][use_tax]": "1", "price[regular][use_reduc]": "0"}
# The product's own stock; its combinations (variants) have rows of their own.
OWN_STOCK = {"filter[id_product_attribute]": "[0]"}
# Every field of a stock row, as PUT replaces the whole row.
STOCK_FIELDS = (
    "id", "id_product", "id_product_attribute", "id_shop", "id_shop_group", "quantity", "depends_on_stock",
    "out_of_stock", "location",
)
# Types whose own stock the app sets: combinations and packs count it in their parts.
COUNTED_TYPES = {"standard", "virtual"}
OUT_OF_STOCK_RANGE = "[-999999999,0]"


class PrestaShopProducts:
    def read_products(self, shop, *, query, stock_filter, offset, limit):
        api = self.api(shop)
        page = f"{offset},{limit + 1}"
        params = {"display": "full", "sort": "[id_DESC]", **PRICES}
        if stock_filter == Filter.OUT_OF_STOCK:
            # Stock is kept apart from the product: the sold out ones first, then those products.
            sold_out = _rows(api.get("stock_availables", {
                **OWN_STOCK, "filter[quantity]": OUT_OF_STOCK_RANGE, "display": "[id_product]",
                "sort": "[id_product_DESC]", "limit": page,
            }), "stock_availables")
            ids, has_more = page_of((row["id_product"] for row in sold_out), limit)
            if not ids:
                return ProductPage(products=(), has_more=False)
            params["filter[id]"] = _ids(ids)
            if query:
                params["filter[name]"] = f"%[{query}]%"
            rows = _rows(api.get("products", params), "products")
        else:
            if query:
                params["filter[name]"] = f"%[{query}]%"
            rows, has_more = page_of(_rows(api.get("products", {**params, "limit": page}), "products"), limit)
        stock = self._stock(api, [row["id"] for row in rows])
        return ProductPage(products=tuple(_product(shop, row, stock) for row in rows), has_more=has_more)

    def read_product(self, shop, external_id):
        api = self.api(shop)
        # A list, not products/{id}: only lists keep the fields that are 0.
        rows = _rows(api.get("products", {"display": "full", "filter[id]": f"[{int(external_id)}]", **PRICES}),
                     "products")
        if not rows:
            raise NotInShop("Nie ma tego produktu w sklepie.")
        row = rows[0]
        product = _product(shop, row, self._stock(api, [row["id"]]))
        return ProductDetail(
            **vars(product),
            categories=self._categories(api, row),
            # The shop redirects it to the product's friendly address.
            url=f"{shop.url}/index.php?controller=product&id_product={int(row['id'])}" if product.visible else "",
        )

    def set_product_stock(self, shop, product, quantity):
        api = self.api(shop)
        row = _first(api.get("stock_availables", {
            **OWN_STOCK, "filter[id_product]": f"[{int(product.external_id)}]", "display": "full",
        }), "stock_availables")
        if not row:
            raise NotInShop("Nie ma tego produktu w sklepie.")
        fields = {name: row.get(name, "" if name == "location" else 0) for name in STOCK_FIELDS}
        api.send_xml("PUT", f"stock_availables/{int(row['id'])}", "stock_available", {**fields, "quantity": quantity})

    @staticmethod
    def _stock(api, product_ids):
        """{product id: pieces}."""
        if not product_ids:
            return {}
        rows = _rows(api.get("stock_availables", {
            **OWN_STOCK, "filter[id_product]": _ids(product_ids), "display": "[id_product,quantity]",
        }), "stock_availables")
        return {str(row["id_product"]): stock_count(row.get("quantity")) for row in rows}

    @staticmethod
    def _categories(api, row):
        """Names of the product's categories, without the root and home ones every product is in."""
        hidden = {
            str(item["value"]) for item in _rows(api.get("configurations", {
                "filter[name]": "[PS_ROOT_CATEGORY|PS_HOME_CATEGORY]", "display": "[name,value]",
            }), "configurations")
        }
        ids = [
            str(item["id"]) for item in (row.get("associations") or {}).get("categories") or []
            if str(item["id"]) not in hidden
        ]
        if not ids:
            return ()
        names = {
            str(item["id"]): _text(item.get("name"))
            for item in _rows(api.get("categories", {"filter[id]": _ids(ids), "display": "[id,name]"}), "categories")
        }
        return tuple(names[id] for id in ids if names.get(id))


def _product(shop, row, stock):
    combinations = (row.get("associations") or {}).get("combinations") or []
    has_variants = bool(combinations) or (row.get("product_type") or "standard") not in COUNTED_TYPES
    final, regular = gross(row.get("final")), gross(row.get("regular"))
    count = stock.get(str(row["id"]))
    image = str(row.get("id_default_image") or "")
    return Product(
        external_id=str(row["id"]),
        name=_text(row.get("name")),
        sku=row.get("reference") or "",
        price=final,
        regular_price=regular if regular is not None and final is not None and regular > final else None,
        stock=count,
        in_stock=bool(count and count > 0),
        visible=str(row.get("active")) == "1" and row.get("visibility") != "none",
        # The theme's product-list size, public like the shop's pages.
        image=f"{shop.url}/img/p/{'/'.join(image)}/{image}-home_default.jpg" if image.isdigit() else "",
        has_variants=has_variants,
    )


def _text(value):
    """A translated field: a string with one language, else [{id, value}] (the first is the default language)."""
    if isinstance(value, list):
        return str(value[0].get("value") or "") if value else ""
    return str(value or "")


def _ids(ids):
    return f"[{'|'.join(str(int(id)) for id in ids)}]"


def _rows(body, resource):
    """A webservice list; it comes as [] instead of {resource: []} when nothing matches."""
    return (body.get(resource) or []) if isinstance(body, dict) else []


def _first(body, resource):
    rows = _rows(body, resource)
    return rows[0] if rows else {}
