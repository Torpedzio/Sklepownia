import logging
import uuid

from .base import BaseSender, Ticket

logger = logging.getLogger(__name__)


class LogSender(BaseSender):
    """Writes notifications to the log instead of sending them: for development without a phone."""

    def send(self, messages):
        for message in messages:
            logger.info("Push to %s…: %s | %s | %s", message.token[:24], message.title, message.body, message.url)
        return [Ticket(ok=True, id=f"log-{uuid.uuid4()}") for _ in messages]

    def receipts(self, ticket_ids):
        return {ticket_id: Ticket(ok=True) for ticket_id in ticket_ids}
