"""Senders pass notifications to a push service (then APNs/FCM): a ticket comes at once, a receipt later."""

from dataclasses import dataclass

# The app was uninstalled or its notifications turned off for good.
DEVICE_NOT_REGISTERED = "DeviceNotRegistered"


class PushError(Exception):
    """Refused; sending it again won't help."""


class PushUnavailable(PushError):
    """No answer or asked to slow down; try again later."""


@dataclass(frozen=True)
class Message:
    token: str
    title: str
    body: str
    # The app screen the notification opens, e.g. "/shops/7/sales".
    url: str
    # Also the Android channel the notification shows in.
    topic: str


@dataclass(frozen=True)
class Ticket:
    ok: bool
    id: str = ""
    # The service's error code, e.g. DEVICE_NOT_REGISTERED.
    error: str = ""
    message: str = ""


class BaseSender:
    def send(self, messages):
        """Returns one Ticket per message, in the same order. Raises PushUnavailable to retry."""
        raise NotImplementedError

    def receipts(self, ticket_ids):
        """{ticket id: Ticket} for the tickets whose receipt is ready."""
        raise NotImplementedError
