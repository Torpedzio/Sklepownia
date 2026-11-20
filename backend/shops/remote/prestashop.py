from . import ShopApi


class PrestaShopApi(ShopApi):
    """PrestaShop's webservice: JSON answers, but data to save goes as XML."""

    def authenticate(self, session, credentials):
        session.auth = (credentials.api_key, "")

    def address(self, path, params):
        # The dispatcher works without friendly URLs, which /api/ needs.
        return f"{self.shop.url}/webservice/dispatcher.php", {**params, "url": path.strip("/"), "output_format": "JSON"}

    def error_message(self, body):
        return "; ".join(error["message"] for error in body["errors"])

    def ping(self):
        # Not the list of resources: PrestaShop 9.2 fails to give it as JSON.
        self.get("shops")
