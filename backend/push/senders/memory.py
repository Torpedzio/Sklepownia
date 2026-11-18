from .base import DEVICE_NOT_REGISTERED, BaseSender, Ticket


class MemorySender(BaseSender):
    """
    For tests: what was sent lands in `outbox`. Tokens in `unregistered` are refused at once, tokens in
    `unregistered_later` get the same news in their receipt. `reset()` empties it all.
    """

    outbox = []
    unregistered = set()
    unregistered_later = set()
    _tokens = {}

    @classmethod
    def reset(cls):
        cls.outbox.clear()
        cls.unregistered.clear()
        cls.unregistered_later.clear()
        cls._tokens.clear()

    def send(self, messages):
        tickets = []
        for message in messages:
            if message.token in self.unregistered:
                tickets.append(Ticket(ok=False, error=DEVICE_NOT_REGISTERED, message="Not a registered device"))
                continue
            self.outbox.append(message)
            ticket_id = f"ticket-{len(self._tokens) + 1}"
            self._tokens[ticket_id] = message.token
            tickets.append(Ticket(ok=True, id=ticket_id))
        return tickets

    def receipts(self, ticket_ids):
        return {
            ticket_id: Ticket(ok=False, error=DEVICE_NOT_REGISTERED)
            if self._tokens[ticket_id] in self.unregistered_later else Ticket(ok=True)
            for ticket_id in ticket_ids if ticket_id in self._tokens
        }
