"""Professional Spanish quote PDF.

WeasyPrint is used when it is installed. It needs system libraries that are
not available on every machine, so ReportLab renders the same document otherwise.
"""

import importlib
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from app.services.cost_engine import as_money


@dataclass(frozen=True)
class QuoteDocument:
    business_name: str
    rfc: str
    address: str
    client_name: str
    phone: str
    event_date: str
    slot_label: str
    venue: str
    guests: str
    waiters: str
    package_name: str
    options: tuple[tuple[str, str], ...]
    extras: tuple[tuple[str, str], ...]
    equipment: tuple[tuple[str, str], ...]
    package_price: str
    waiter_cost: str
    freight_name: str
    freight: str
    subtotal: str
    discount: str
    tax: str
    total: str
    special_requests: str
    token: str
    status_label: str


def render_quote_pdf(document: QuoteDocument) -> bytes:
    rendered = _weasyprint_pdf(document)
    if rendered is not None:
        return rendered
    return _reportlab_pdf(document)


def _weasyprint_pdf(document: QuoteDocument) -> bytes | None:
    try:
        module = importlib.import_module("weasyprint")
    except ImportError:
        return None
    html = getattr(module, "HTML", None)
    if html is None:
        return None
    try:
        payload = html(string=_html(document)).write_pdf()
    except OSError:
        return None
    if not isinstance(payload, bytes):
        return None
    return payload


def _html(document: QuoteDocument) -> str:
    from xml.sax.saxutils import escape

    rows = [
        ("Paquete " + document.package_name, document.package_price),
        ("Meseros (" + document.waiters + ")", document.waiter_cost),
        (document.freight_name or "Flete", document.freight),
        *list(document.extras),
        *list(document.equipment),
    ]
    body = "".join(
        f"<tr><td>{escape(label)}</td><td>{escape(amount)}</td></tr>"
        for label, amount in rows
    )
    options = "".join(
        f"<li>{escape(group)}: {escape(recipe)}</li>"
        for group, recipe in document.options
    )
    return (
        "<html><body>"
        "<h1>Cotización</h1>"
        f"<p>{escape(document.business_name)} · {escape(document.rfc)}</p>"
        f"<p>{escape(document.client_name)} · {escape(document.event_date)} "
        f"· {escape(document.slot_label)}</p>"
        f"<p>{escape(document.venue)} · {escape(document.guests)} invitados</p>"
        f"<ul>{options}</ul><table>{body}</table>"
        f"<p>Subtotal {escape(document.subtotal)}</p>"
        f"<p>Descuento {escape(document.discount)}</p>"
        f"<p>IVA {escape(document.tax)}</p>"
        f"<p>Total {escape(document.total)}</p>"
        f"<p>Folio {escape(document.token)}</p>"
        f"<p>{escape(document.special_requests)}</p>"
        f"<p>{escape(document.status_label)}</p>"
        "</body></html>"
    )


def _font_name() -> str:
    candidates = (
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    )
    for path in candidates:
        if not path.is_file():
            continue
        if "QuoteSans" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("QuoteSans", str(path)))
        return "QuoteSans"
    return "Helvetica"


def _reportlab_pdf(document: QuoteDocument) -> bytes:
    buffer = BytesIO()
    pdf = Canvas(buffer, pagesize=A4)
    font = _font_name()
    width, height = A4
    pdf.setFillColor(HexColor("#09090B"))
    pdf.rect(0, height - 78, width, 78, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#FFC72C"))
    _draw(pdf, font, 20, 40, height - 48, "Cotización")
    pdf.setFillColor(HexColor("#18181B"))
    y = height - 110
    lines = [
        document.business_name,
        f"RFC {document.rfc}" if document.rfc else "",
        document.address,
        f"Cliente: {document.client_name}",
        f"Teléfono: {document.phone}",
        f"Evento: {document.event_date} · {document.slot_label}",
        f"Lugar: {document.venue}",
        f"Invitados: {document.guests} · Meseros: {document.waiters}",
        f"Paquete: {document.package_name}",
        f"Estado: {document.status_label}",
        f"Folio: {document.token}",
    ]
    for group, recipe in document.options:
        lines.append(f"{group}: {recipe}")
    if document.special_requests:
        lines.append(f"Peticiones: {document.special_requests}")
    y = _block(pdf, font, 40, y, lines)
    y -= 12
    amounts = [
        (f"Paquete {document.package_name}", _pesos(document.package_price)),
        (f"Meseros ({document.waiters})", _pesos(document.waiter_cost)),
        (document.freight_name or "Flete", _pesos(document.freight)),
        *[(label, _pesos(amount)) for label, amount in document.extras],
        *[(label, _pesos(amount)) for label, amount in document.equipment],
        ("Subtotal", _pesos(document.subtotal)),
        ("Descuento", _pesos(document.discount)),
        ("IVA", _pesos(document.tax)),
        ("Total", _pesos(document.total)),
    ]
    for label, amount in amounts:
        if y < 72:
            pdf.showPage()
            y = height - 48
        _draw(pdf, font, 11, 40, y, label)
        _draw(pdf, font, 11, width - 140, y, amount)
        y -= 16
    pdf.setFillColor(HexColor("#FFC72C"))
    pdf.rect(0, 0, width, 28, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#09090B"))
    _draw(pdf, font, 9, 40, 10, "iBistro")
    pdf.save()
    return buffer.getvalue()


def _block(pdf: Canvas, font: str, x: float, y: float, lines: list[str]) -> float:
    for line in lines:
        if not line:
            continue
        if y < 72:
            pdf.showPage()
            y = 800
        _draw(pdf, font, 11, x, y, line)
        y -= 16
    return y


def _draw(pdf: Canvas, font: str, size: int, x: float, y: float, text: str) -> None:
    pdf.setFont(font, size)
    try:
        pdf.drawString(x, y, text)
    except UnicodeEncodeError:
        pdf.drawString(x, y, text.encode("latin-1", "replace").decode("latin-1"))


def _pesos(value: str) -> str:
    try:
        amount = as_money(Decimal(value))
    except InvalidOperation:
        return value
    return f"${amount:,.2f}"
