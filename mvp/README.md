# Dinasty Invoice — MVP

Early prototype that flags supplier invoice problems before payment. It runs locally.

**Status:** prototype tested on fictitious invoices only. Not used by any customer.

## What works today

1. Upload one or more text-based PDF invoices, or use the fictitious samples.
2. Extract supplier, invoice number, date, total and currency with deterministic rules.
3. Normalize the fields (supplier legal suffixes, separators and leading zeros in numbers, FR/EN amounts).
4. Flag alerts with deterministic rules:
   - **Duplicate, high:** same supplier and same invoice number.
   - **Duplicate, medium:** same supplier and amount, dates within 7 days, different numbers.
   - **Missing:** a field could not be found. It shows as `Unknown`, never guessed.
   - **Inconsistent:** total zero or negative, or a date in the future.
5. Explain each alert in plain language, either with canned demo text (no API call) or with Claude.
6. Show a report with the evidence for each alert. A human makes every decision.

## What is not built yet

- OCR for scanned PDFs. Scanned files are rejected with a clear message.
- Line-item checks, VAT checks, purchase-order matching.
- Accounts, storage, hosted version.

## How Claude is used, and its limits

- Claude **only explains** alerts that the rules already found. It does not create alerts.
- Claude receives the extracted fields and the alerts. It **does not** receive the raw invoice text.
- Claude cannot pay, contact suppliers or change data. The app has no such function.
- Claude mode requires an explicit consent checkbox before anything is sent.
- One API call per analysis, at most 20 alerts, `max_tokens=2000`.

## Install

Requires Python 3.11 or newer.

```bash
cd mvp
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python make_samples.py
```

## Run

```bash
streamlit run app.py
```

Demo mode works without any key. For Claude mode, copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`. Never commit `.env`.

## Test

```bash
python -m pytest -q
```

The tests cover amount parsing, field extraction, duplicate rules, missing and inconsistent fields, file rejection, and an end-to-end run on the samples.

## Cost

Measured on one analysis of the 5 samples with `claude-haiku-4-5` (default): 889 input tokens, 394 output tokens, about $0.003 at $1 / $5 per million tokens.

Set `DINASTY_MODEL` to use another model, for example `claude-opus-5-5` for stronger reasoning at a higher price.

## Data handling

Uploaded files stay in memory during the session. Nothing is written to disk and nothing is kept after the page closes.

## Samples

All companies, numbers and amounts in `samples/` are fictitious.
