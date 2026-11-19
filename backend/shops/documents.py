"""
Terms of sale and privacy policy rendered from templates/shops/documents/ and published in the shop.

The templates follow Polish law (consumer rights, electronic services, GDPR): a lawyer-checked starting point, not
legal advice. After changing them, raise VERSION and run `publish_shop_documents`.
"""

from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser

from django.conf import settings
from django.template.loader import render_to_string

from .shop_settings import OPERATORS

VERSION = "2026-11-18"

# A change in any of these republishes the documents.
INPUT_SECTIONS = ("general", "shopping", "payments", "shipping", "region", "documents")

MONTHS = (
    "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
    "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
)

CURRENCY_NAMES = {"PLN": "złotych polskich", "EUR": "euro", "USD": "dolarach amerykańskich",
                  "GBP": "funtach brytyjskich"}

# Named in the terms and among the data recipients in the privacy policy.
OPERATOR_COMPANIES = {
    "przelewy24": "PayPro S.A. z siedzibą w Poznaniu",
    "payu": "PayU S.A. z siedzibą w Poznaniu",
}


@dataclass
class Document:
    key: str
    title: str
    # Used where the platform lets us choose the page address.
    slug: str
    html: str
    blocks: list = field(default_factory=list)


def should_publish(changes, values):
    return values["documents"]["managed"] and any(section in changes for section in INPUT_SECTIONS)


def render(values, url, today=None):
    """Returns [terms, privacy policy]; `url` is the shop's address."""
    context = {**_context(values, today or date.today()), "url": url}
    documents = []
    for key, title, slug in (
        ("terms", "Regulamin sklepu", "regulamin"),
        ("privacy", "Polityka prywatności", "polityka-prywatnosci"),
    ):
        html = _compact(render_to_string(f"shops/documents/{key}.html", context))
        documents.append(Document(key=key, title=title, slug=slug, html=html, blocks=blocks(html)))
    return documents


def _context(values, today):
    documents = values["documents"]
    payments = values["payments"]
    shipping = values["shipping"]
    region = values["region"]
    currency = region["currency"]
    operators = [
        {"name": operator.name, "company": OPERATOR_COMPANIES[key]}
        for key, operator in OPERATORS.items()
        if payments.get(f"{key}_enabled")
    ]
    free_from = shipping["free_shipping_min_amount"]
    reviews = values["shopping"]["reviews"]
    # Paragraph numbers shift as optional ones come and go.
    paragraphs = ["general", "definitions", "services", "orders", "payments", "delivery", "withdrawal", "complaints"]
    paragraphs += ["reviews"] if reviews else []
    paragraphs += ["disputes", "data", "final"]
    return {
        "number": {name: index for index, name in enumerate(paragraphs, start=1)},
        "shop": values["general"],
        "seller": documents,
        "address": f"{documents['street']}, {documents['postal_code']} {documents['city']}",
        "bank_transfer": payments["bank_transfer_enabled"],
        "cash_on_delivery": payments["cash_on_delivery_enabled"],
        "operators": operators,
        "courier": shipping["courier_enabled"],
        "free_shipping": shipping["free_shipping_enabled"],
        "free_shipping_from": _money(free_from, currency) if free_from and float(free_from) > 0 else "",
        "local_pickup": shipping["local_pickup_enabled"],
        "currency_name": CURRENCY_NAMES.get(currency, currency),
        "reviews": reviews,
        "dispatch": _working_days(documents["dispatch_days"]),
        "hosting": _hosting(),
        "date": f"{today.day} {MONTHS[today.month - 1]} {today.year}",
    }


def _money(amount, currency):
    whole, _, cents = amount.partition(".")
    return f"{whole},{cents or '00'} {currency}" if cents != "00" else f"{whole} {currency}"


def _working_days(days):
    return "1 dnia roboczego" if days == 1 else f"{days} dni roboczych"


def _hosting():
    """We host the shop, so we're a processor of the customers' data (GDPR)."""
    seller = settings.INVOICE_SELLER
    if not seller["name"]:
        return None
    address = ", ".join(part for part in (seller["street"], f"{seller['postal_code']} {seller['city']}".strip()) if part)
    return {"name": seller["name"], "address": address}


def _compact(html):
    return "\n".join(line.strip() for line in html.splitlines() if line.strip())


class _Blocks(HTMLParser):
    """Documents' HTML as plain-text blocks for the app: headings, paragraphs, lists (one level of nesting)."""

    def __init__(self):
        super().__init__()
        self.blocks = []
        self.lists = []
        self.text = None

    def handle_starttag(self, tag, attrs):
        if tag in ("h2", "h3", "p"):
            self.text = []
        elif tag in ("ol", "ul"):
            items = []
            if self.lists:
                self._flush_item()
                self.lists[-1][-1]["items"] = items
            else:
                self.blocks.append({"type": "list", "ordered": tag == "ol", "items": items})
            self.lists.append(items)
        elif tag == "li":
            self.lists[-1].append({"text": ""})
            self.text = []
        elif tag == "br" and self.text is not None:
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in ("h2", "h3"):
            self.blocks.append({"type": "heading", "level": int(tag[1]), "text": self._take()})
        elif tag == "p":
            self.blocks.append({"type": "paragraph", "text": self._take()})
        elif tag == "li":
            self._flush_item()
        elif tag in ("ol", "ul"):
            self.lists.pop()

    def handle_data(self, data):
        if self.text is not None:
            self.text.append(data)

    def _flush_item(self):
        if self.text is not None:
            item = self.lists[-1][-1]
            item["text"] = (item["text"] + " " + self._take()).strip()

    def _take(self):
        text = "".join(self.text or [])
        self.text = None
        return "\n".join(" ".join(line.split()) for line in text.split("\n")).strip()


def blocks(html):
    parser = _Blocks()
    parser.feed(html)
    parser.close()
    return parser.blocks
