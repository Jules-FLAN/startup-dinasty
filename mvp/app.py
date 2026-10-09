"""Dinasty Invoice MVP. Run: streamlit run app.py"""
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from explain import ExplainError, claude_explanations, demo_explanations
from invoices import InvoiceReadError, analyze, extract_text, parse_invoice

load_dotenv()
st.set_page_config(page_title="Dinasty Invoice (MVP)", layout="wide")
st.title("Dinasty Invoice — MVP")
st.caption("Early prototype. Every alert must be reviewed by a human. Nothing is paid, sent or modified.")

SAMPLES_DIR = Path(__file__).parent / "samples"

source = st.radio("Invoices", ["Use fictitious samples", "Upload my PDFs"], horizontal=True)
files: list[tuple[str, bytes]] = []
if source == "Use fictitious samples":
    files = [(p.name, p.read_bytes()) for p in sorted(SAMPLES_DIR.glob("*.pdf"))]
    if not files:
        st.warning("No samples found. Run: python make_samples.py")
else:
    uploads = st.file_uploader("PDF invoices (max 5 MB each)", type="pdf", accept_multiple_files=True)
    files = [(u.name, u.getvalue()) for u in uploads or []]  # kept in memory only, never written to disk

mode = st.radio("Explanations", ["Demo mode (no API call)", "Claude API"], horizontal=True)
consent = True
if mode == "Claude API":
    consent = st.checkbox(
        "I understand that extracted fields (supplier, number, date, amount) and alerts will be sent to "
        "Anthropic's API. Raw invoice text is not sent."
    )

if files and st.button("Analyze", type="primary", disabled=not consent):
    invoices, errors = [], []
    for name, data in files:
        try:
            invoices.append(parse_invoice(name, extract_text(name, data)))
        except InvoiceReadError as exc:
            errors.append(str(exc))
    for err in errors:
        st.error(err)

    if invoices:
        st.subheader("Extracted data")
        st.dataframe([{f: inv.display(f) for f in ("supplier", "number", "date", "total", "currency")}
                      | {"file": inv.filename} for inv in invoices], use_container_width=True)

        alerts = analyze(invoices)
        st.subheader(f"Alerts ({len(alerts)})")
        if not alerts:
            st.success("No rule triggered. A human should still review before payment.")
        else:
            try:
                explanations = (claude_explanations(invoices, alerts) if mode == "Claude API"
                                else demo_explanations(alerts))
            except ExplainError as exc:
                st.warning(str(exc))
                explanations = []
            by_index = {e.alert_index: e for e in explanations}
            for i, a in enumerate(alerts):
                with st.container(border=True):
                    st.markdown(f"**{a.severity.upper()} · {a.kind}** — {', '.join(a.files)}")
                    st.write(a.message)
                    st.caption(f"Evidence: {a.evidence}")
                    if e := by_index.get(i):
                        st.write(e.explanation)
                        st.info(f"Human check: {e.human_check}")
