"""Gateways take the first payment on their page, then charge the saved card; card numbers never reach us."""

from dataclasses import dataclass
from decimal import Decimal


class GatewayError(Exception):
    """The message is for logs; customers get a plain one."""


class InvalidNotification(Exception):
    """A notification that is not provably from the gateway."""


@dataclass(frozen=True)
class Payer:
    email: str
    name: str
    street: str = ""
    postal_code: str = ""
    city: str = ""
    country: str = "PL"
    tax_id: str = ""


@dataclass(frozen=True)
class Checkout:
    gateway_id: str
    title: str
    redirect_url: str


@dataclass(frozen=True)
class SavedCard:
    token: str
    brand: str = ""
    tail: str = ""
    expiry: str = ""


@dataclass(frozen=True)
class PaymentResult:
    """`paid` is None while the gateway hasn't decided yet."""

    reference: str
    paid: bool | None
    amount: Decimal | None = None
    gateway_id: str = ""
    title: str = ""
    card: SavedCard | None = None
    error: str = ""


class BaseGateway:
    name = ""
    # Response body that stops the gateway resending a notification.
    notification_ack = "TRUE"

    def start_payment(self, payment, payer: Payer, *, return_url: str, site_url: str) -> Checkout:
        """Starts the first payment, which also saves the card for renewals."""
        raise NotImplementedError

    def charge_saved_card(self, payment, payer: Payer, card_token: str) -> PaymentResult:
        """Charges without the payer; the result may still be pending."""
        raise NotImplementedError

    def parse_notification(self, request) -> PaymentResult:
        """Verifies and reads a notification; raises InvalidNotification."""
        raise InvalidNotification("This gateway sends no notifications.")

    def fetch_result(self, payment) -> PaymentResult | None:
        """Polls the gateway, for when notifications can't reach the platform."""
        return None
