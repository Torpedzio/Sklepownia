"""Who issues invoices: the platform itself or an invoicing service. See settings.INVOICE_ISSUER."""


class InvoicingError(Exception):
    """The invoice could not be issued now; the message says why. Issuing is tried again later."""


class BaseIssuer:
    name = ""

    def issue(self, invoice):
        """
        Gives the invoice its number, document and, when it goes to KSeF, its first KSeF status. Changes the
        instance without saving it. Raises InvoicingError when it cannot be issued now.
        """
        raise NotImplementedError

    def check_ksef(self, invoice):
        """Follows an invoice sent to KSeF: updates its KSeF status, number and document. Raises InvoicingError."""
        raise NotImplementedError
