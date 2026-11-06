"""
A payment gateway takes the first payment on its own page (saving the card) and charges the saved card later.
Card numbers never reach the platform: it only keeps the gateway's token.
"""

from dataclasses import dataclass
from decimal import Decimal


class GatewayError(Exception):
    """The gateway refused or failed a request. The message is for logs; customers get a plain one."""


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
    """A payment started on the gateway; the payer goes to `redirect_url`."""

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
    """What the gateway says about a payment: paid, failed, or not decided yet (status None)."""

    reference: str
    paid: bool | None
    amount: Decimal | None = None
    gateway_id: str = ""
    title: str = ""
    card: SavedCard | None = None
    error: str = ""


class BaseGateway:
    name = ""
    # The body the gateway expects back after a notification it may stop resending.
    notification_ack = "TRUE"

    def start_payment(self, payment, payer: Payer, *, return_url: str, site_url: str) -> Checkout:
        """Starts the first payment, which also saves the card for renewals."""
        raise NotImplementedError

    def charge_saved_card(self, payment, payer: Payer, card_token: str) -> PaymentResult:
        """Charges a saved card without the payer. The result may still be pending."""
        raise NotImplementedError

    def parse_notification(self, request) -> PaymentResult:
        """Verifies a notification from the gateway and reads it. Raises InvalidNotification."""
        raise InvalidNotification("This gateway sends no notifications.")

    def fetch_result(self, payment) -> PaymentResult | None:
        """Asks the gateway about a payment, for when notifications can't reach the platform."""
        return None
