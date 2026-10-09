"""Generate fictitious invoices in samples/. All companies and numbers are invented."""
from pathlib import Path

from fpdf import FPDF

SAMPLES = {
    "acme_inv-1042.pdf": ["Supplier: Acme Office Supplies SAS", "Invoice No: INV-1042", "Invoice date: 2026-09-02",
                          "Item: Printer paper x 40", "Total due: 1 240,00 EUR"],
    "acme_inv-1042_copy.pdf": ["Supplier: ACME Office Supplies", "Invoice No: INV-01042", "Invoice date: 2026-09-03",
                               "Item: Printer paper x 40", "Total due: 1 240,00 EUR"],
    "nordlight_88.pdf": ["Supplier: Nordlight Energy Ltd", "Invoice No: NL-88", "Invoice date: 2026-09-10",
                         "Electricity, August", "Total due: 389.50 EUR"],
    "nordlight_91.pdf": ["Supplier: Nordlight Energy Ltd", "Invoice No: NL-91", "Invoice date: 2026-09-14",
                         "Electricity, August", "Total due: 389.50 EUR"],
    "bluecab_missing.pdf": ["Supplier: BlueCab Transport", "Taxi rides, September", "Total due: 72,40 EUR"],
}


def main() -> None:
    out = Path(__file__).parent / "samples"
    out.mkdir(exist_ok=True)
    for name, lines in SAMPLES.items():
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(0, 10, "INVOICE (fictitious sample)", new_x="LMARGIN", new_y="NEXT")
        for line in lines:
            pdf.cell(0, 8, line, new_x="LMARGIN", new_y="NEXT")
        pdf.output(str(out / name))
    print(f"Wrote {len(SAMPLES)} samples to {out}")


if __name__ == "__main__":
    main()
