class InvoicingError(Exception):
    """Can't be issued now (the message says why); retried later."""


class BaseIssuer:
    name = ""

    def issue(self, invoice):
        """Sets the number, document and (for KSeF) first KSeF status without saving. Raises InvoicingError."""
        raise NotImplementedError

    def check_ksef(self, invoice):
        """Updates the KSeF status, number and document of an invoice sent to KSeF. Raises InvoicingError."""
        raise NotImplementedError
