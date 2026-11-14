"""
POC 1 - A schema that lets Claude say "not there"
=================================================
The same 5 invoices are extracted twice through output_format (the SDK's structured output: Claude hands in its
JSON through the built-in StructuredOutput tool, and the SDK validates it against your schema):

    naive      every field required, no null allowed, and no way out of the category list
    nullable   3 required fields, 3 optional nullable ones, a category enum with unclear and other, a detail field

D1-D3 are complete. D4 has no invoice number and no date; D5 has no invoice number, no tax, and doesn't say what
was bought. With the naive schema, the SDK's validator rejects every honest "nothing here", so Claude MUST invent.

Besides model I/O, the log shows one score line per document and schema, then the totals per schema.

Run:  python poc1_schema_design.py     (2 runs, 5 query() calls each)
"""

import asyncio
import sys

from claude_agent_sdk import ClaudeSDKError

from common import load_settings, log, setup_logging
from extraction_setup import ABSENT, INVOICE_SCHEMA, INVOICES, NAIVE_SCHEMA, TRUTH, extract, score

RUNS = [
    ("naive", NAIVE_SCHEMA),  # required fields pressure Claude to invent (C3)
    ("nullable", INVOICE_SCHEMA),  # null is an allowed, honest answer (C4, C5)
]


async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc1_schema_design")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    for label, schema in RUNS:
        invented, wrong_category = 0, 0
        for doc_id in INVOICES:
            try:
                data, subtype = await extract(settings, doc_id, schema)
            except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
                log.error("SDK error: %s", exc)
                return 1
            if data is None:  # e.g. the validator never got a value it accepts
                log.error("%s %s: no structured output (%s)", label, doc_id, subtype)
                continue
            verdicts = score(doc_id, data, schema)
            invented += sum(v.startswith("invented") for v in verdicts.values())
            wrong_category += data.get("category") != TRUTH[doc_id][2]
            log.info("%-8s %s: %s", label, doc_id, " ".join(f"{f}={v}" for f, v in verdicts.items()))
        log.info("%-8s totals: %d of %d absent fields invented, %d of %d categories wrong", label, invented,
                 sum(len(fields) for fields in ABSENT.values()), wrong_category, len(INVOICES))
    log.info("Same documents, prompt, model and options: only the schema changed")  # schema design is the fix (C2)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
