import secrets

from django.conf import settings
from django.urls import reverse

from .base import BaseGateway, Checkout, PaymentResult, SavedCard

FAKE_CARD = SavedCard(token="", brand="Visa", tail="4242", expiry="1230")


class FakeGateway(BaseGateway):
    """
    Simulates a card gateway without any account: the payment page is served by the platform itself
    (billing.views.fake_gateway_page) with buttons to pay or decline. For local work and tests.
    """

    name = "fake"

    def start_payment(self, payment, payer, *, return_url, site_url):
        path = reverse("billing-fake-gateway", args=[payment.pk])
        return Checkout(
            gateway_id=f"fake-{secrets.token_hex(8)}",
            title=f"FAKE-{payment.pk:06d}",
            redirect_url=f"{site_url.rstrip('/')}{path}",
        )

    def charge_saved_card(self, payment, payer, card_token):
        if settings.FAKE_GATEWAY_DECLINE_RENEWALS:
            return PaymentResult(reference=payment.reference, paid=False, error="Karta odrzucona (symulacja).")
        return PaymentResult(
            reference=payment.reference,
            paid=True,
            amount=payment.amount,
            gateway_id=f"fake-{secrets.token_hex(8)}",
            title=f"FAKE-{payment.pk:06d}",
        )

    @staticmethod
    def saved_card():
        return SavedCard(token=f"fake-{secrets.token_hex(16)}", brand=FAKE_CARD.brand, tail=FAKE_CARD.tail,
                         expiry=FAKE_CARD.expiry)
