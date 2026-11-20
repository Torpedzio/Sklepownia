"""PrestaShop products through its webservice, mixed into PrestaShopProvisioner."""

from decimal import Decimal

from ..products import (
    Category, Filter, Product, ProductDetail, ProductPage, description_markup, description_text, gross, page_of,
    stock_count, url_slug,
)
from ..remote import NotInShop
from ..remote.prestashop import Translated

# The webservice works the price out as the shop does: gross, and `final` after the sale.
PRICES = {"price[final][use_tax]": "1", "price[regular][use_tax]": "1", "price[regular][use_reduction]": "0"}
# The shop's settings the products need.
SETTINGS = ("PS_ROOT_CATEGORY", "PS_HOME_CATEGORY", "PS_LANG_DEFAULT", "PS_COUNTRY_DEFAULT")
# A specific price for everyone: any cart, customer, group, country and currency, from one piece.
GENERAL_PRICE = {
    "id_product_attribute": 0, "id_shop": 0, "id_shop_group": 0, "id_cart": 0, "id_currency": 0, "id_country": 0,
    "id_group": 0, "id_customer": 0, "from_quantity": 1,
}
ALWAYS = "0000-00-00 00:00:00"
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
        description, formatted = description_text(_text(row.get("description")))
        return ProductDetail(
            **vars(product),
            categories=self._categories(api, row),
            # The shop redirects it to the product's friendly address.
            url=f"{shop.url}/index.php?controller=product&id_product={int(row['id'])}" if product.visible else "",
            description=description,
            formatted_description=formatted,
        )

    def read_categories(self, shop):
        """The tree below the home category, depth first in the shop's order."""
        api = self.api(shop)
        settings = _settings(api)
        rows = _rows(api.get("categories", {"display": "[id,name,id_parent,position]"}), "categories")
        children = {}
        for row in sorted(rows, key=lambda row: int(row.get("position") or 0)):
            children.setdefault(str(row["id_parent"]), []).append(row)
        found = []

        def walk(parent):
            for row in children.get(parent, []):
                found.append(Category(str(row["id"]), _text(row.get("name"))))
                walk(str(row["id"]))

        walk(settings["PS_HOME_CATEGORY"])
        return tuple(found)

    def update_product(self, shop, product, changes):
        api = self.api(shop)
        settings = _settings(api)
        id = int(product.external_id)
        row = _first(api.get("products", {
            "display": "[id,id_tax_rules_group,visibility]", "filter[id]": f"[{id}]",
        }), "products")
        if not row:
            raise NotInShop("Nie ma tego produktu w sklepie.")
        fields = _fields(changes, settings, rate=self._tax_rate(api, row, settings))
        if changes.get("visible") and row.get("visibility") == "none":
            fields["visibility"] = "both"
        if fields:
            api.send_xml("PATCH", f"products/{id}", "product", {"id": id, **fields})
        if "sale_price" in changes:
            price = changes.get("price", product.regular_price if product.regular_price is not None else product.price)
            self._set_sale(api, id, price, changes["sale_price"])

    def create_product(self, shop, fields):
        api = self.api(shop)
        settings = _settings(api)
        language = settings["PS_LANG_DEFAULT"]
        body = {
            # Without a tax group, so the price entered is what the customer pays.
            "id_tax_rules_group": 0, "active": 1, "visibility": "both", "state": 1, "product_type": "standard",
            "link_rewrite": Translated({language: url_slug(fields["name"])[:120] or "produkt"}),
            **_fields({**fields, "categories": fields.get("categories") or []}, settings, rate=Decimal(0)),
        }
        id = int(api.send_xml("POST", "products", "product", body)["product"]["id"])
        if fields.get("stock") is not None:
            self.set_product_stock(shop, _id_only(id), fields["stock"])
        if fields.get("sale_price") is not None:
            self._set_sale(api, id, fields["price"], fields["sale_price"])
        return str(id)

    def delete_product(self, shop, product):
        self.api(shop).delete(f"products/{int(product.external_id)}")

    @staticmethod
    def _tax_rate(api, row, settings):
        """The product's tax in the shop's country, in percent; 0 without a tax group."""
        group = int(row.get("id_tax_rules_group") or 0)
        if not group:
            return Decimal(0)
        rule = _first(api.get("tax_rules", {
            "filter[id_tax_rules_group]": f"[{group}]", "filter[id_country]": f"[{int(settings['PS_COUNTRY_DEFAULT'])}]",
            "display": "[id_tax]",
        }), "tax_rules")
        if not rule or not int(rule.get("id_tax") or 0):
            return Decimal(0)
        tax = _first(api.get("taxes", {"filter[id]": f"[{int(rule['id_tax'])}]", "display": "[rate]"}), "taxes")
        return Decimal(str(tax.get("rate") or 0))

    @staticmethod
    def _set_sale(api, id, price, sale_price):
        """
        The sale as the one specific price for everyone, an amount off the gross price; others (for a group, a
        customer, from more pieces) stay as the owner set them in the panel.
        """
        for row in _rows(api.get("specific_prices", {"filter[id_product]": f"[{id}]", "display": "full"}),
                         "specific_prices"):
            if all(int(row.get(name) or 0) == value for name, value in GENERAL_PRICE.items() if name != "id_shop"):
                api.delete(f"specific_prices/{int(row['id'])}")
        if sale_price is not None:
            api.send_xml("POST", "specific_prices", "specific_price", {
                **GENERAL_PRICE, "id_product": id, "price": -1, "reduction": f"{price - sale_price:.2f}",
                "reduction_tax": 1, "reduction_type": "amount", "from": ALWAYS, "to": ALWAYS,
            })

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
        """The product's categories, without the root and home ones every product is in."""
        settings = _settings(api)
        hidden = {settings["PS_ROOT_CATEGORY"], settings["PS_HOME_CATEGORY"]}
        ids = [
            str(item["id"]) for item in (row.get("associations") or {}).get("categories") or []
            if str(item["id"]) not in hidden
        ]
        # The main one first, as the app's form takes the first chosen as the main one.
        ids.sort(key=lambda id: id != str(row.get("id_category_default")))
        if not ids:
            return ()
        names = {
            str(item["id"]): _text(item.get("name"))
            for item in _rows(api.get("categories", {"filter[id]": _ids(ids), "display": "[id,name]"}), "categories")
        }
        return tuple(Category(id, names[id]) for id in ids if names.get(id))


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


def _fields(changes, settings, *, rate):
    """The product's fields in the webservice for the app's, the price net of `rate` (the sale is apart)."""
    language = settings["PS_LANG_DEFAULT"]
    fields = {}
    if "name" in changes:
        fields["name"] = Translated({language: changes["name"]})
    if "price" in changes:
        fields["price"] = f"{changes['price'] / (1 + rate / 100):.6f}"
    if "sku" in changes:
        fields["reference"] = changes["sku"]
    if "description" in changes:
        fields["description"] = Translated({language: description_markup(changes["description"])})
    if "categories" in changes:
        # The home category stays: the shop lists products by it, and the first chosen one is the main one.
        home = settings["PS_HOME_CATEGORY"]
        ids = list(dict.fromkeys([home, *(str(int(id)) for id in changes["categories"])]))
        fields["id_category_default"] = ids[1] if len(ids) > 1 else home
        fields["associations"] = {"categories": [("category", {"id": id}) for id in ids]}
    if "visible" in changes:
        fields["active"] = 1 if changes["visible"] else 0
    return fields


def _settings(api):
    rows = _rows(api.get("configurations", {
        "filter[name]": f"[{'|'.join(SETTINGS)}]", "display": "[name,value]",
    }), "configurations")
    return {row["name"]: str(row["value"]) for row in rows}


class _id_only:
    """What set_product_stock needs of a product just made."""

    def __init__(self, id):
        self.external_id = str(id)


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
