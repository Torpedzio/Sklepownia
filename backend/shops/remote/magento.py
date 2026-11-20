from . import ShopApi


class MagentoApi(ShopApi):
    """Magento REST API with the token of the platform's integration, in the global scope like the panel's default."""

    def authenticate(self, session, credentials):
        session.headers["Authorization"] = f"Bearer {credentials.api_key}"

    def address(self, path, params):
        return f"{self.shop.url}/rest/all/V1/{path.lstrip('/')}", params

    def error_message(self, body):
        # "Brak produktu %1" with the values in `parameters`, a list or a {name: value} dict.
        message, parameters = body["message"], body.get("parameters") or []
        names = parameters.items() if isinstance(parameters, dict) else enumerate(parameters, start=1)
        for name, value in names:
            message = message.replace(f"%{name}", str(value))
        return message

    def ping(self):
        self.get("store/storeViews")
