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

Besides model I/O, the log shows each attempt's checks and errors, the loop's decision, and the review queue.

Run:  python poc1_retry_loop.py     (3 runs: 2 + 3 + 1 query() calls when each retry succeeds)
"""

import asyncio
import json
import sys
from copy import deepcopy

from claude_agent_sdk import ClaudeSDKError

from common import Settings, load_settings, log, setup_logging
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
    log.info("%s attempt 1: %s", doc_id, "seeded (a recorded bad extraction)" if doc_id in SEEDED else "live")
    attempt = SEEDED.get(doc_id) or await extract(settings, first_prompt(doc_id))
    first = attempt
    for retry in range(MAX_RETRIES + 1):
        if attempt is None:
            log.info("%s -> human review: no extraction", doc_id)
            return {"doc": doc_id, "status": "human_review", "attempts": retry + 1,
                    "errors": [{"check": "no_extraction", "message": "no_extraction: no structured output", "fixable": False}]}
        errors = validate(attempt)
        log.info("%s: schema valid; stated_total %s, calculated_total %s, total_discrepancy %s; %d semantic error(s)",
                 doc_id, attempt.get("stated_total"), attempt["calculated_total"], attempt["total_discrepancy"], len(errors))
        for e in errors:
            log.info("%s   %s", doc_id, e["message"])
        if not errors:
            log.info("%s -> accepted; line items: %s; conflict_detected=%s", doc_id, "; ".join(
                f"{i['description']} -> {i['detected_pattern']}" for i in attempt["line_items"]), attempt["conflict_detected"])
            if doc_id in SEEDED:
                log.info("%s fields the feedback retry changed: %s", doc_id, changed_fields(first, attempt))
            return {"doc": doc_id, "status": "accepted", "attempts": retry + 1, "errors": [], "data": attempt}
        if any(not e["fixable"] for e in errors):  # the boundary: a retry can't create absent information (C10)
            log.info("%s -> human review: information the document doesn't have; no retry", doc_id)
            return {"doc": doc_id, "status": "human_review", "attempts": retry + 1, "errors": errors, "data": attempt}
        if retry == MAX_RETRIES:
            log.warning("%s -> human review: still failing after %d retries", doc_id, MAX_RETRIES)
            return {"doc": doc_id, "status": "human_review", "attempts": retry + 1, "errors": errors, "data": attempt}
        log.info("%s -> retry %d with the document, the failed JSON and %d error(s)", doc_id, retry + 1, len(errors))
        attempt = await extract(settings, retry_message(doc_id, attempt, errors))
    return {}


async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc1_retry_loop")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    feedback = retry_message("F2", SEEDED["F2"], validate(SEEDED["F2"]))
    naive = NAIVE_RETRY.format(document=DOCUMENTS["F2"])
    log.info("F2 feedback retry: %d chars, failed JSON included: %s, errors included: %s | naive retry: %d chars, "
             "failed JSON included: %s, errors included: %s", len(feedback), "<failed_extraction>" in feedback,
             "numeric:" in feedback, len(naive), "<failed_extraction>" in naive, "numeric:" in naive)  # (C8)

    results = {}
    for run in RUNS:
        try:
            if run == "retry-anyway":  # the control: retry U1 although its only error can't be fixed (C10)
                u1 = results.get("U1", {}).get("data")
                if u1 is None:
                    continue
                retried = await extract(settings, retry_message("U1", u1, validate(u1)))
                value = (retried or {}).get("due_date")
                log.info("U1 retry anyway: due_date = %r (in the document: %s): no real information appeared", value,
                         value is not None and value in DOCUMENTS["U1"])
                continue
            for doc_id in GROUPS[run]:
                results[doc_id] = await process(settings, doc_id)
        except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
            log.error("SDK error: %s", exc)
            return 1
    queue = [f"{r['doc']} ({', '.join(e['message'].split()[1] if e['check'] == 'completeness' else e['check'] for e in r['errors'])})"
             for r in results.values() if r.get("status") == "human_review"]  # what each document lacks
    log.info("review queue: %s", queue or "empty")  # (C11)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
