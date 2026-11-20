"""WooCommerce products through its REST API (wc/v3), mixed into WooCommerceProvisioner."""

from ..products import Filter, Product, ProductDetail, ProductPage, gross, page_of, stock_count

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
        product = _product(row)
        return ProductDetail(
            **vars(product),
            categories=tuple(category["name"] for category in row.get("categories") or [] if category.get("name")),
            # A draft's permalink is a preview link that needs the panel's login.
            url=(row.get("permalink") or "") if row.get("status") == "publish" else "",
        )

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
