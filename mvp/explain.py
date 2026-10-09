"""Claude turns deterministic alerts into plain-language explanations.

Claude never sees raw invoice text, never creates alerts, and cannot act on anything:
it only receives the extracted fields and the alerts the rules already produced.
"""
from __future__ import annotations

import os

import anthropic
from pydantic import BaseModel, ValidationError

from invoices import Alert, Invoice

DEFAULT_MODEL = "claude-haiku-5-5"
MAX_ALERTS_PER_CALL = 20

SYSTEM = (
    "You help an accounts-payable clerk review supplier invoice alerts before payment. "
    "You receive extracted invoice fields and alerts produced by deterministic rules. "
    "For each alert, explain in one or two plain sentences why it matters and what a human should check. "
    "Use only the data provided. Never invent amounts, dates, suppliers or new anomalies. "
    "If a field is 'Unknown', say it must be verified. You cannot pay, contact suppliers or edit records; "
    "never suggest that you did."
)


class Explanation(BaseModel):
    alert_index: int
    explanation: str
    human_check: str


class Report(BaseModel):
    explanations: list[Explanation]


class ExplainError(Exception):
    pass


def demo_explanations(alerts: list[Alert]) -> list[Explanation]:
    """Offline mode: canned wording, zero API calls."""
    checks = {
        "duplicate": "Compare both PDFs and confirm with the supplier before paying either.",
        "missing": "Open the PDF and fill in the field by hand, or ask the supplier for a corrected invoice.",
        "inconsistent": "Check the original document and the purchase order.",
    }
    return [Explanation(alert_index=i, explanation=f"[Demo] {a.message}", human_check=checks[a.kind])
            for i, a in enumerate(alerts)]


def _payload(invoices: list[Invoice], alerts: list[Alert]) -> str:
    lines = ["INVOICES:"]
    for inv in invoices:
        lines.append(f"- {inv.filename}: supplier={inv.display('supplier')}, number={inv.display('number')}, "
                     f"date={inv.display('date')}, total={inv.display('total')} {inv.display('currency')}")
    lines.append("ALERTS:")
    for i, a in enumerate(alerts):
        lines.append(f"[{i}] {a.kind}/{a.severity} files={a.files}: {a.message} Evidence: {a.evidence}")
    return "\n".join(lines)


def claude_explanations(invoices: list[Invoice], alerts: list[Alert]) -> list[Explanation]:
    if not alerts:
        return []
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ExplainError("ANTHROPIC_API_KEY is not set. Use demo mode or add the key to .env.")
    alerts = alerts[:MAX_ALERTS_PER_CALL]  # cost cap: one call, bounded input
    client = anthropic.Anthropic(max_retries=2, timeout=60)
    try:
        response = client.messages.parse(
            model=os.environ.get("DINASTY_MODEL", DEFAULT_MODEL),
            max_tokens=2000,
            output_config={"effort": "low"},
            system=SYSTEM,
            messages=[{"role": "user", "content": _payload(invoices, alerts)}],
            output_format=Report,
        )
    except anthropic.AuthenticationError as exc:
        raise ExplainError("Invalid API key.") from exc
    except anthropic.RateLimitError as exc:
        raise ExplainError("Rate limited by the API. Try again in a minute.") from exc
    except anthropic.APIStatusError as exc:
        raise ExplainError(f"API error {exc.status_code}.") from exc
    except anthropic.APIConnectionError as exc:
        raise ExplainError("Could not reach the API.") from exc
    except ValidationError as exc:
        raise ExplainError("Malformed answer from Claude. Showing rule results only.") from exc

    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise ExplainError("Claude returned no usable answer. Showing rule results only.")
    valid = [e for e in response.parsed_output.explanations if 0 <= e.alert_index < len(alerts)]
    return valid
