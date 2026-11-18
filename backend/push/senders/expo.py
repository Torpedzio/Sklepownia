"""Expo's push service: one API for iOS and Android, used with tokens from expo-notifications."""

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

from .base import BaseSender, PushError, PushUnavailable, Ticket

logger = logging.getLogger(__name__)

SEND_URL = "https://exp.host/--/api/v2/push/send"
RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"
# The service's limits per request.
SEND_BATCH = 100
RECEIPTS_BATCH = 1000
TIMEOUT = 15


class ExpoSender(BaseSender):
    def send(self, messages):
        tickets = []
        for start in range(0, len(messages), SEND_BATCH):
            batch = messages[start:start + SEND_BATCH]
            data = self._post(SEND_URL, [self._payload(message) for message in batch]).get("data")
            if not isinstance(data, list) or len(data) != len(batch):
                raise PushError(f"Expo answered {data!r:.200} for {len(batch)} messages")
            tickets += [_ticket(item) for item in data]
        return tickets

    def receipts(self, ticket_ids):
        receipts = {}
        for start in range(0, len(ticket_ids), RECEIPTS_BATCH):
            data = self._post(RECEIPTS_URL, {"ids": ticket_ids[start:start + RECEIPTS_BATCH]}).get("data") or {}
            receipts.update({ticket_id: _ticket(item) for ticket_id, item in data.items()})
        return receipts

    @staticmethod
    def _payload(message):
        return {
            "to": message.token,
            "title": message.title,
            "body": message.body,
            "data": {"url": message.url},
            "sound": "default",
            "priority": "high",
            "channelId": message.topic,
        }

    @staticmethod
    def _post(url, body):
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if settings.EXPO_ACCESS_TOKEN:
            # Required when the Expo project has "enhanced security for push notifications" on.
            headers["Authorization"] = f"Bearer {settings.EXPO_ACCESS_TOKEN}"
        request = urllib.request.Request(url, method="POST", data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            details = error.read().decode(errors="replace")[:500]
            if error.code == 429 or error.code >= 500:
                raise PushUnavailable(f"Expo push {error.code}: {details}") from error
            raise PushError(f"Expo push {error.code}: {details}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise PushUnavailable(f"Expo push doesn't answer: {error}") from error
        except ValueError as error:
            raise PushUnavailable("Expo push answered with something other than JSON") from error


def _ticket(item):
    if item.get("status") == "ok":
        return Ticket(ok=True, id=item.get("id", ""))
    return Ticket(ok=False, error=(item.get("details") or {}).get("error", ""), message=item.get("message", ""))
