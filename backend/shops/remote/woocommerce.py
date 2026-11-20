from . import ShopApi


class WooCommerceApi(ShopApi):
    """WooCommerce REST API v3, signed in as the shop's administrator with an application password."""

    def authenticate(self, session, credentials):
        session.auth = (credentials.admin_login, credentials.api_key)

    def address(self, path, params):
        return f"{self.shop.url}/wp-json/wc/v3/{path.lstrip('/')}", params

    def error_message(self, body):
        return body.get("message") or ""

    def ping(self):
        # Needs the manage_woocommerce capability, so it also checks whose key it is.
        self.get("data/currencies/current")
