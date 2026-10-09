"""Deterministic invoice extraction and checks. No AI here: every alert is reproducible."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_PAGES = 20
UNKNOWN = "Unknown"


class InvoiceReadError(Exception):
    """Raised when a file cannot be turned into usable text."""


@dataclass
class Invoice:
    filename: str
    supplier: str | None = None
    number: str | None = None
    date: date | None = None
    total: Decimal | None = None
    currency: str | None = None
    raw_text: str = field(default="", repr=False)

    def display(self, name: str) -> str:
        value = getattr(self, name)
        return UNKNOWN if value is None else str(value)


@dataclass
class Alert:
    kind: str          # "duplicate" | "missing" | "inconsistent"
    severity: str      # "high" | "medium" | "low"
    files: list[str]
    message: str
    evidence: str


def extract_text(filename: str, data: bytes) -> str:
    if len(data) > MAX_FILE_BYTES:
        raise InvoiceReadError(f"{filename}: file larger than {MAX_FILE_BYTES // (1024 * 1024)} MB")
    if not data.startswith(b"%PDF"):
        raise InvoiceReadError(f"{filename}: not a PDF file")
    try:
        reader = PdfReader(io.BytesIO(data))
        if len(reader.pages) > MAX_PAGES:
            raise InvoiceReadError(f"{filename}: more than {MAX_PAGES} pages")
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except (PdfReadError, ValueError, KeyError) as exc:
        raise InvoiceReadError(f"{filename}: unreadable PDF ({exc})") from exc
    if not text.strip():
        # ponytail: no OCR, scanned PDFs are rejected; add OCR if real users send scans
        raise InvoiceReadError(f"{filename}: no text layer (scanned image?)")
    return text


_LABEL = r"[ \t]*[:#]?[ \t]*"
_PATTERNS = {
    "supplier": re.compile(r"(?:supplier|vendor|from|fournisseur)" + _LABEL + r"(.+)", re.I),
    "number": re.compile(r"(?:invoice\s*(?:no|number|n°|#)|facture\s*n°?)" + _LABEL + r"([A-Z0-9][A-Z0-9\-/]*)", re.I),
    "date": re.compile(r"(?:invoice\s*date|date)" + _LABEL + r"(\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4})", re.I),
    "total": re.compile(r"(?:total\s*(?:due|ttc|amount)?|amount\s*due)" + _LABEL + r"([^\n]+)", re.I),
}
_CURRENCIES = {"€": "EUR", "EUR": "EUR", "$": "USD", "USD": "USD", "£": "GBP", "GBP": "GBP"}


def parse_amount(text: str) -> tuple[Decimal | None, str | None]:
    currency = next((code for sym, code in _CURRENCIES.items() if sym in text.upper() or sym in text), None)
    m = re.search(r"\d[\d\s.,]*", text)
    if not m:
        return None, currency
    num = m.group().strip().replace(" ", "")
    # "1.234,56" (FR) vs "1,234.56" (EN): last separator is the decimal one
    if "," in num and "." in num:
        num = num.replace(".", "").replace(",", ".") if num.rfind(",") > num.rfind(".") else num.replace(",", "")
    elif "," in num:
        num = num.replace(",", ".") if len(num.split(",")[-1]) == 2 else num.replace(",", "")
    try:
        return Decimal(num).quantize(Decimal("0.01")), currency
    except InvalidOperation:
        return None, currency


def parse_date(text: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def normalize_supplier(name: str | None) -> str:
    if not name:
        return ""
    name = re.sub(r"\b(sas|sarl|sa|ltd|inc|llc|gmbh)\b\.?", "", name.lower())
    return re.sub(r"[^a-z0-9]", "", name)


def normalize_number(number: str | None) -> str:
    # "INV-01042" and "INV-1042" match: drop separators and leading zeros of digit runs
    cleaned = re.sub(r"[^A-Z0-9]", "", (number or "").upper())
    return re.sub(r"(?<![0-9])0+(?=[0-9])", "", cleaned)


def parse_invoice(filename: str, text: str) -> Invoice:
    inv = Invoice(filename=filename, raw_text=text)
    if m := _PATTERNS["supplier"].search(text):
        inv.supplier = m.group(1).strip()
    if m := _PATTERNS["number"].search(text):
        inv.number = m.group(1).strip()
    if m := _PATTERNS["date"].search(text):
        inv.date = parse_date(m.group(1))
    if m := _PATTERNS["total"].search(text):
        inv.total, inv.currency = parse_amount(m.group(1))
    return inv


def find_duplicates(invoices: list[Invoice]) -> list[Alert]:
    alerts = []
    # ponytail: O(n²) pair scan, fine for a few hundred invoices; index by supplier if volume grows
    for i, a in enumerate(invoices):
        for b in invoices[i + 1:]:
            same_supplier = normalize_supplier(a.supplier) and normalize_supplier(a.supplier) == normalize_supplier(b.supplier)
            same_number = normalize_number(a.number) and normalize_number(a.number) == normalize_number(b.number)
            same_total = a.total is not None and a.total == b.total and a.currency == b.currency
            close_dates = a.date and b.date and abs((a.date - b.date).days) <= 7
            files = [a.filename, b.filename]
            if same_supplier and same_number:
                alerts.append(Alert("duplicate", "high", files,
                                    "Same supplier and same invoice number.",
                                    f"{a.supplier} / {a.number} vs {b.supplier} / {b.number}"))
            elif same_supplier and same_total and close_dates:
                alerts.append(Alert("duplicate", "medium", files,
                                    "Same supplier, same amount, dates within 7 days, different numbers.",
                                    f"{a.total} {a.currency} on {a.date} and {b.date}; numbers {a.number} / {b.number}"))
    return alerts


def check_invoice(inv: Invoice, today: date | None = None) -> list[Alert]:
    today = today or date.today()
    alerts = []
    for name in ("supplier", "number", "date", "total", "currency"):
        if getattr(inv, name) is None:
            alerts.append(Alert("missing", "medium", [inv.filename], f"Field '{name}' could not be found.", "Not detected in text"))
    if inv.total is not None and inv.total <= 0:
        alerts.append(Alert("inconsistent", "high", [inv.filename], "Total is zero or negative.", f"total = {inv.total}"))
    if inv.date and inv.date > today:
        alerts.append(Alert("inconsistent", "medium", [inv.filename], "Invoice date is in the future.", f"date = {inv.date}"))
    return alerts


def analyze(invoices: list[Invoice], today: date | None = None) -> list[Alert]:
    alerts = find_duplicates(invoices)
    for inv in invoices:
        alerts.extend(check_invoice(inv, today))
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(alerts, key=lambda a: order[a.severity])
