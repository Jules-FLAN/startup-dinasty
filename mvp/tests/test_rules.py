import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from explain import demo_explanations  # noqa: E402
from invoices import (Invoice, InvoiceReadError, analyze, extract_text, parse_amount,  # noqa: E402
                      parse_invoice)

TODAY = date(2026, 10, 9)


def inv(name, supplier="Acme SAS", number="INV-1", d=date(2026, 9, 1), total="100.00", cur="EUR"):
    return Invoice(name, supplier, number, d, Decimal(total) if total else None, cur)


@pytest.mark.parametrize("text,expected", [
    ("1 240,00 EUR", (Decimal("1240.00"), "EUR")),
    ("1,240.00 USD", (Decimal("1240.00"), "USD")),
    ("1.240,50 €", (Decimal("1240.50"), "EUR")),
    ("389.50 EUR", (Decimal("389.50"), "EUR")),
    ("no number", (None, None)),
])
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


def test_parse_invoice_fields():
    text = "Supplier: Acme SAS\nInvoice No: INV-7\nInvoice date: 02/09/2026\nTotal due: 50,00 EUR"
    i = parse_invoice("a.pdf", text)
    assert (i.supplier, i.number, i.date, i.total, i.currency) == ("Acme SAS", "INV-7", date(2026, 9, 2), Decimal("50.00"), "EUR")


def test_missing_fields_are_unknown_not_guessed():
    i = parse_invoice("x.pdf", "Hello world")
    assert i.display("total") == "Unknown"
    kinds = [a.kind for a in analyze([i], TODAY)]
    assert kinds.count("missing") == 5


def test_duplicate_same_number_despite_formatting():
    a = inv("a", supplier="Acme Office SAS", number="INV-1042")
    b = inv("b", supplier="ACME office", number="INV-01042")
    alerts = [x for x in analyze([a, b], TODAY) if x.kind == "duplicate"]
    assert len(alerts) == 1 and alerts[0].severity == "high"


def test_duplicate_same_amount_close_dates():
    a = inv("a", number="NL-88", d=date(2026, 9, 10))
    b = inv("b", number="NL-91", d=date(2026, 9, 14))
    alerts = [x for x in analyze([a, b], TODAY) if x.kind == "duplicate"]
    assert len(alerts) == 1 and alerts[0].severity == "medium"


def test_no_duplicate_when_dates_far_apart():
    a = inv("a", number="1", d=date(2026, 6, 1))
    b = inv("b", number="2", d=date(2026, 9, 1))
    assert not [x for x in analyze([a, b], TODAY) if x.kind == "duplicate"]


def test_no_duplicate_across_suppliers():
    assert not [x for x in analyze([inv("a"), inv("b", supplier="Other Ltd")], TODAY) if x.kind == "duplicate"]


def test_inconsistencies():
    kinds = {a.message for a in analyze([inv("a", total="0", d=date(2027, 1, 1))], TODAY)}
    assert "Total is zero or negative." in kinds
    assert "Invoice date is in the future." in kinds


def test_rejects_non_pdf_and_oversize():
    with pytest.raises(InvoiceReadError):
        extract_text("a.pdf", b"not a pdf")
    with pytest.raises(InvoiceReadError):
        extract_text("a.pdf", b"%PDF" + b"0" * (6 * 1024 * 1024))
    with pytest.raises(InvoiceReadError):
        extract_text("a.pdf", b"%PDF-1.4 garbage")


def test_samples_end_to_end():
    samples = Path(__file__).parent.parent / "samples"
    invoices = [parse_invoice(p.name, extract_text(p.name, p.read_bytes())) for p in sorted(samples.glob("*.pdf"))]
    alerts = analyze(invoices, TODAY)
    dup = {tuple(sorted(a.files)): a.severity for a in alerts if a.kind == "duplicate"}
    assert dup == {("acme_inv-1042.pdf", "acme_inv-1042_copy.pdf"): "high",
                   ("nordlight_88.pdf", "nordlight_91.pdf"): "medium"}
    missing = {a.message for a in alerts if a.kind == "missing" and a.files == ["bluecab_missing.pdf"]}
    assert missing == {"Field 'number' could not be found.", "Field 'date' could not be found."}
    assert len(demo_explanations(alerts)) == len(alerts)
