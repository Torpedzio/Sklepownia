from . import ShopNotConnected
from ..models import ShopCredentials


class FakeApi:
    """The API of a simulated shop. Tests set `unreachable` to {shop id: ShopApiError raised by every call}."""

    unreachable = {}

    def __init__(self, shop):
        self.shop = shop
        if not ShopCredentials.objects.filter(shop=shop).exclude(api_key="").exists():
            raise ShopNotConnected("Sklep nie jest jeszcze połączony z aplikacją.")

    def ping(self):
        error = self.unreachable.get(self.shop.pk)
        if error is not None:
            raise error
