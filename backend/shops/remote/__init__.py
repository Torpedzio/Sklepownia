"""The shop's own REST API, called at the shop's public address: what the app does in a shop right away."""

import requests

from ..models import ShopCredentials
from ..unavailable import UNAVAILABLE_HEADER

CONNECT_TIMEOUT = 5
READ_TIMEOUT = 30
# The name of the key in the shop's panel, so the owner knows what it's for.
KEY_NAME = "Sklepownia"


class ShopApiError(Exception):
    """The message is for the shop's owner."""


class ShopUnavailable(ShopApiError):
    pass


class ShopNotConnected(ShopApiError):
    pass


class ShopRejected(ShopApiError):
    """The shop refused the key, e.g. the owner deleted it in the panel."""


class NotInShop(ShopApiError):
    pass


class ShopApi:
    def __init__(self, shop):
        self.shop = shop
        credentials = ShopCredentials.objects.filter(shop=shop).first()
        if credentials is None or not credentials.api_key:
            raise ShopNotConnected("Sklep nie jest jeszcze połączony z aplikacją.")
        self.session = requests.Session()
        self.session.headers["Accept"] = "application/json"
        self.authenticate(self.session, credentials)

    def authenticate(self, session, credentials):
        raise NotImplementedError

    def address(self, path, params):
        """(URL, query parameters) of `path` in the platform's API."""
        raise NotImplementedError

    def error_message(self, body):
        """The platform's own error text from a JSON error body, or ""."""
        return ""

    def ping(self):
        """Succeeds when the shop answers and accepts the key."""
        raise NotImplementedError

    def get(self, path, params=None):
        return self.request("GET", path, params=params)

    def post(self, path, json=None, params=None):
        return self.request("POST", path, params=params, json=json)

    def put(self, path, json=None, params=None):
        return self.request("PUT", path, params=params, json=json)

    def delete(self, path, params=None):
        return self.request("DELETE", path, params=params)

    def request(self, method, path, params=None, json=None, data=None, headers=None):
        url, params = self.address(path, dict(params or {}))
        try:
            # A redirect would turn a POST into a GET and drop the key on another host.
            response = self.session.request(
                method, url, params=params, json=json, data=data, headers=headers,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), allow_redirects=False,
            )
        except requests.Timeout:
            raise ShopUnavailable("Sklep nie odpowiedział na czas.") from None
        except requests.RequestException:
            raise ShopUnavailable("Nie da się połączyć ze sklepem.") from None
        return self._result(response)

    def _result(self, response):
        status = response.status_code
        # The proxy's own page: no healthy container to send the request to.
        if response.headers.get(UNAVAILABLE_HEADER) or status in (502, 504):
            raise ShopUnavailable("Sklep jest chwilowo niedostępny.")
        if status in (401, 403):
            raise ShopRejected("Sklep nie przyjął klucza aplikacji.")
        if 300 <= status < 400:
            raise ShopApiError("Sklep przekierował zapytanie pod inny adres.")
        try:
            body = response.json() if response.content else None
        except ValueError:
            body = None
            if status < 300:
                raise ShopApiError("Sklep odpowiedział w nieoczekiwany sposób.") from None
        if status == 404:
            raise NotInShop(self._message(body) or "Nie ma tego w sklepie.")
        if status >= 400:
            message = self._message(body)
            raise ShopApiError(f"Sklep zwrócił błąd: {message}" if message else f"Sklep zwrócił błąd {status}.")
        return body

    def _message(self, body):
        try:
            return self.error_message(body).strip() if body else ""
        except (AttributeError, KeyError, IndexError, TypeError):
            return ""


def connect(shop):
    """The client for the shop's platform (a simulated one with the fake provisioner)."""
    from ..provisioning import get_provisioner

    return get_provisioner(shop.platform).api(shop)
