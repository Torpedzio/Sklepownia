"""
A sender hands notifications to a push service, which passes them on to Apple's and Google's services. The answer
comes in two parts: a ticket at once (the service took the message) and a receipt later (the phone's service did).
"""

from dataclasses import dataclass

# The phone no longer takes notifications from the app (uninstalled, or notifications turned off for good).
DEVICE_NOT_REGISTERED = "DeviceNotRegistered"


class PushError(Exception):
    """The push service refused the request; sending it again won't help."""


class PushUnavailable(PushError):
    """The push service didn't answer or asked to slow down; try again later."""


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
        """Sends `messages`; returns one Ticket per message, in the same order. Raises PushUnavailable to retry."""
        raise NotImplementedError

    def receipts(self, ticket_ids):
        """Receipts of the tickets that have one by now, as {ticket id: Ticket}."""
        raise NotImplementedError
