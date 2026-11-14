"""
POC 1 - Validate, then retry with the error
===========================================
A Python-controlled loop around output_format:

    extract ──► validate() ──► no errors ─────────────────────────────► accepted
                    │
                    ├── an error a retry can't fix (absent information) ──► human review, NO retry
                    └── fixable errors ──► retry with document + failed JSON + the errors (at most 2 retries)

F1 and F2 start from a recorded bad extraction (seeded), so the retry path runs every time. U1-U3 lack a due date,
an invoice number and a printed total: a live extraction, then human review. The last run retries U1 anyway, to show
that a retry can't create information the document doesn't have.

Run:  python poc1_retry_loop.py     (3 runs: 2 + 3 + 1 query() calls when each retry succeeds)
"""

import asyncio
import json
import sys
from copy import deepcopy

from claude_agent_sdk import ClaudeSDKError

from common import Settings, load_settings
from validation_setup import DOCUMENTS, TRUTH, extract, validate

MAX_RETRIES = 2  # a cap, then human review (C9)

SEEDED = {  # recorded bad first attempts (E1): live first attempts on these clean documents are usually right
    "F1": {**TRUTH["F1"], "invoice_date": "2026-11-13", "due_date": "2026-10-14"},  # misplaced values: swapped dates
    "F2": {**deepcopy(TRUTH["F2"]), "calculated_total": 295.0, "total_discrepancy": True},  # a wrong total
}
SEEDED["F2"]["line_items"][0]["amount"] = 145.0  # 3 x 45.00 recorded as 145.00

RETRY_TEMPLATE = ("Your extraction of this document failed validation. Correct it.\n\n"
                  "<document>\n{document}\n</document>\n\n"
                  "<failed_extraction>\n{failed}\n</failed_extraction>\n\n"
                  "<validation_errors>\n{errors}\n</validation_errors>\n\n"
                  "Fix what the errors name, using the document as the only source.")
NAIVE_RETRY = ("Your extraction of this document failed validation. Extract it again.\n\n"
               "<document>\n{document}\n</document>")

RUNS = ["fixable", "unfixable", "retry-anyway"]
GROUPS = {"fixable": ["F1", "F2"], "unfixable": ["U1", "U2", "U3"]}


def first_prompt(doc_id: str) -> str:
    return f"Extract this invoice.\n\n<document>\n{DOCUMENTS[doc_id]}\n</document>"


def retry_message(doc_id: str, failed: dict, errors: list[dict]) -> str:
    """The three parts of a useful retry: the document, the failed extraction and the specific errors (C7)."""
    return RETRY_TEMPLATE.format(document=DOCUMENTS[doc_id], failed=json.dumps(failed, indent=2),
                                 errors="\n".join(e["message"] for e in errors))


def changed_fields(before: dict, after: dict) -> list[str]:
    """What the retry changed: top-level fields and line amounts."""
    changes = [f"{k}: {before.get(k)} -> {after.get(k)}" for k in before if k != "line_items" and before.get(k) != after.get(k)]
    for n, (b, a) in enumerate(zip(before["line_items"], after.get("line_items", [])), 1):
        if b["amount"] != a["amount"]:
            changes.append(f"line {n} amount: {b['amount']} -> {a['amount']}")
    return changes


async def process(settings: Settings, doc_id: str) -> dict:
    """Validate, then accept, retry with feedback, or send to human review."""
    attempt = SEEDED.get(doc_id) or await extract(settings, first_prompt(doc_id))
    first = attempt
    for retry in range(MAX_RETRIES + 1):
        if attempt is None:
            return {"doc": doc_id, "status": "human_review", "attempts": retry + 1,
                    "errors": [{"check": "no_extraction", "message": "no_extraction: no structured output", "fixable": False}]}
        errors = validate(attempt)
        if not errors:
            if doc_id in SEEDED:
                changed = changed_fields(first, attempt)  # what the feedback retry changed
            return {"doc": doc_id, "status": "accepted", "attempts": retry + 1, "errors": [], "data": attempt}
        if any(not e["fixable"] for e in errors):  # the boundary: a retry can't create absent information (C10)
            return {"doc": doc_id, "status": "human_review", "attempts": retry + 1, "errors": errors, "data": attempt}
        if retry == MAX_RETRIES:
            return {"doc": doc_id, "status": "human_review", "attempts": retry + 1, "errors": errors, "data": attempt}
        attempt = await extract(settings, retry_message(doc_id, attempt, errors))
    return {}


async def main() -> int:
    try:
        settings = load_settings()
    except (OSError, RuntimeError):
        return 1

    feedback = retry_message("F2", SEEDED["F2"], validate(SEEDED["F2"]))
    naive = NAIVE_RETRY.format(document=DOCUMENTS["F2"])
    # (C8) the feedback retry includes the failed JSON and the errors; the naive retry includes neither
    feedback_has = ("<failed_extraction>" in feedback, "numeric:" in feedback)
    naive_has = ("<failed_extraction>" in naive, "numeric:" in naive)

    results = {}
    for run in RUNS:
        try:
            if run == "retry-anyway":  # the control: retry U1 although its only error can't be fixed (C10)
                u1 = results.get("U1", {}).get("data")
                if u1 is None:
                    continue
                retried = await extract(settings, retry_message("U1", u1, validate(u1)))
                value = (retried or {}).get("due_date")
                in_document = value is not None and value in DOCUMENTS["U1"]  # no real information appeared
                continue
            for doc_id in GROUPS[run]:
                results[doc_id] = await process(settings, doc_id)
        except ClaudeSDKError:  # Claude Code not found, its process crashed, ...
            return 1
    queue = [f"{r['doc']} ({', '.join(e['message'].split()[1] if e['check'] == 'completeness' else e['check'] for e in r['errors'])})"
             for r in results.values() if r.get("status") == "human_review"]  # what each document lacks
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
