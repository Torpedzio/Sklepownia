from pathlib import Path

from django.conf import settings
from django.utils import timezone
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace

from shops.choices import Country

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
FONT = "DejaVu"
INK = (32, 33, 36)
MUTED = (95, 99, 104)
RULE = (210, 212, 216)
LEFT_COLUMN = 95


def render(invoice, *, notes=()):
    """PDF bytes; `notes` are extra lines under the totals, e.g. why VAT is not charged."""
    pdf = FPDF(format="A4")
    pdf.set_title(f"Faktura {invoice.number}")
    pdf.set_author(invoice.seller.get("name", ""))
    pdf.set_creator(settings.PLATFORM_NAME)
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_font(FONT, "", FONT_DIR / "DejaVuSans.ttf")
    pdf.add_font(FONT, "B", FONT_DIR / "DejaVuSans-Bold.ttf")
    pdf.add_page()
    pdf.set_text_color(*INK)

    _header(pdf, invoice)
    if invoice.seller.get("test"):
        pdf.set_font(FONT, "B", 9)
        pdf.set_text_color(180, 35, 24)
        pdf.cell(text="Dokument testowy: dane sprzedawcy nie są prawdziwe, to nie jest faktura.",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(*INK)
        pdf.ln(4)
    _parties(pdf, invoice)
    _items(pdf, invoice)
    _totals(pdf, invoice, notes)
    return bytes(pdf.output())


def _header(pdf, invoice):
    pdf.set_font(FONT, "B", 18)
    pdf.cell(LEFT_COLUMN, 9, "Faktura VAT")
    top = pdf.get_y()
    for label, value in [
        ("Numer", invoice.number),
        ("Data wystawienia", _date(invoice.issue_date)),
        ("Data sprzedaży", _date(invoice.sale_date)),
    ]:
        pdf.set_xy(pdf.l_margin + LEFT_COLUMN, top)
        pdf.set_font(FONT, "", 9)
        pdf.set_text_color(*MUTED)
        pdf.cell(35, 5.5, label)
        pdf.set_font(FONT, "B", 9)
        pdf.set_text_color(*INK)
        pdf.cell(0, 5.5, value, align="R")
        top += 5.5
    pdf.set_y(top + 8)


def _parties(pdf, invoice):
    top = pdf.get_y()
    _party(pdf, "Sprzedawca", _seller_lines(invoice.seller), pdf.l_margin, top)
    seller_bottom = pdf.get_y()
    _party(pdf, "Nabywca", _buyer_lines(invoice.buyer), pdf.l_margin + LEFT_COLUMN, top)
    pdf.set_y(max(seller_bottom, pdf.get_y()) + 8)


def _party(pdf, title, lines, x, y):
    pdf.set_xy(x, y)
    pdf.set_font(FONT, "", 9)
    pdf.set_text_color(*MUTED)
    pdf.cell(text=title, new_x=XPos.LEFT, new_y=YPos.NEXT)
    pdf.set_text_color(*INK)
    for index, line in enumerate(lines):
        pdf.set_x(x)
        pdf.set_font(FONT, "B" if index == 0 else "", 10)
        pdf.multi_cell(LEFT_COLUMN - 6, 5, line, new_x=XPos.LEFT, new_y=YPos.NEXT)


def _seller_lines(seller):
    lines = [seller.get("name", ""), seller.get("street", ""), f"{seller.get('postal_code', '')} {seller.get('city', '')}"]
    if seller.get("tax_id"):
        lines.append(f"NIP {seller['tax_id']}")
    if seller.get("bank_account"):
        lines.append(f"Konto {seller['bank_account']}")
    return [line.strip() for line in lines if line.strip()]


def _buyer_lines(buyer):
    company = buyer.get("kind") == "company"
    place = f"{buyer.get('postal_code', '')} {buyer.get('city', '')}".strip()
    country = buyer.get("country", Country.PL)
    if country != Country.PL:
        place += f", {Country(country).label if country in Country.values else country}"
    lines = [buyer.get("company_name") if company else buyer.get("full_name"), buyer.get("street", ""), place]
    if company and buyer.get("tax_id"):
        lines.append(f"{'NIP' if country == Country.PL else 'Numer VAT'} {buyer['tax_id']}")
    return [line.strip() for line in lines if line and line.strip()]


def _items(pdf, invoice):
    rate = _rate(invoice.vat_rate)
    heading = FontFace(emphasis="BOLD", color=MUTED, fill_color=(244, 245, 247), size_pt=7.5)
    pdf.set_font(FONT, "", 9)
    pdf.set_draw_color(*RULE)
    with pdf.table(
        col_widths=(8, 52, 12, 11, 19, 21, 11, 19, 21),
        text_align=("CENTER", "LEFT", "RIGHT", "CENTER", "RIGHT", "RIGHT", "CENTER", "RIGHT", "RIGHT"),
        headings_style=heading,
        line_height=5,
        padding=1.6,
        borders_layout="HORIZONTAL_LINES",
    ) as table:
        table.row(["Lp.", "Nazwa usługi", "Ilość", "J.m.", "Cena netto", "Wartość netto", "VAT", "Kwota VAT",
                   "Wartość brutto"])
        table.row(["1", invoice.item, "1", "usł.", _amount(invoice.net), _amount(invoice.net), rate,
                   _amount(invoice.vat), _amount(invoice.gross)])
    pdf.ln(6)


def _totals(pdf, invoice, notes):
    width = 80
    x = pdf.w - pdf.r_margin - width
    rows = [
        ("Razem netto", _money(invoice.net, invoice.currency)),
        (f"VAT {_rate(invoice.vat_rate)}", _money(invoice.vat, invoice.currency)),
        ("Razem brutto", _money(invoice.gross, invoice.currency)),
    ]
    for label, value in rows:
        pdf.set_x(x)
        pdf.set_font(FONT, "", 9)
        pdf.set_text_color(*MUTED)
        pdf.cell(width / 2, 6, label)
        pdf.set_font(FONT, "B", 10)
        pdf.set_text_color(*INK)
        pdf.cell(width / 2, 6, value, align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(6)

    paid = invoice.payment.paid_at
    pdf.set_font(FONT, "", 9)
    for line in [
        f"Zapłacono: {_money(invoice.gross, invoice.currency)}, kartą płatniczą"
        + (f", {_date(paid)}" if paid else "") + ".",
        f"Pozostało do zapłaty: {_money(0, invoice.currency)}.",
        *notes,
    ]:
        pdf.multi_cell(0, 5, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if invoice.ksef_number:
        pdf.multi_cell(0, 5, f"Numer KSeF: {invoice.ksef_number}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(10)
    pdf.set_font(FONT, "", 8)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 4, f"Faktura wystawiona elektronicznie w serwisie {settings.PLATFORM_NAME}. "
                         "Nie wymaga podpisu.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _rate(rate):
    return "np." if rate == "np" else f"{rate}%"


def _amount(value):
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def _money(value, currency):
    return f"{_amount(value)} {currency}"


def _date(value):
    if value is None:
        return ""
    if hasattr(value, "tzinfo") and value.tzinfo is not None:
        value = timezone.localtime(value)
    return value.strftime("%d.%m.%Y")
