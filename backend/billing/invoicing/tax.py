"""VAT on invoices. Plan prices are gross; the invoice splits what was paid into net and VAT."""

from decimal import ROUND_HALF_UP, Decimal

EU = {"AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU", "IE", "IT", "LT", "LU",
      "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK"}
NOT_SUBJECT = "np"
CENT = Decimal("0.01")


def rate_for(buyer, plan_rate):
    """
    A company from abroad buys a service taxed where it is (art. 28b of the VAT act): no Polish VAT. People
    and Polish companies pay the plan's rate.
    """
    if buyer.get("kind") == "company" and buyer.get("country", "PL") != "PL":
        return NOT_SUBJECT
    return format(Decimal(plan_rate).normalize(), "f")


def split(gross, rate):
    """(net, VAT) of a gross amount."""
    if rate == NOT_SUBJECT:
        return gross, Decimal("0.00")
    vat = (gross * Decimal(rate) / (100 + Decimal(rate))).quantize(CENT, rounding=ROUND_HALF_UP)
    return gross - vat, vat


def notes(invoice):
    """What the invoice has to say about VAT it does not charge."""
    if invoice.vat_rate != NOT_SUBJECT:
        return []
    if invoice.buyer.get("country") in EU:
        return ["Odwrotne obciążenie: VAT rozlicza nabywca."]
    return ["Usługa nie podlega opodatkowaniu VAT w Polsce (art. 28b ustawy o VAT)."]
