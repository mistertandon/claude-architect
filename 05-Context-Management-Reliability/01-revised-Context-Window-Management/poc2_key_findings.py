"""
POC 2 - Key findings first
==========================
Dana Reyes (CUST-1042) asks for a $312.40 refund of order ORD-9024, and a reviewer gets the findings of 9
back-office checks. One finding blocks the refund: the card issuer has already opened chargeback CB-4471 for the
same $312.40, so a refund would pay her twice. It sits in source 5 of 9, Payments: the middle of the input.

The same 9 sources, combined two ways:

    aggregate_plain()   the 9 detailed results, one after the other    -> CB-4471 about halfway in
    aggregate()         ## Key Findings Summary: one bullet per source -> CB-4471 in the first 8%
                        ## Detailed Results: one ### header per source

A note telling the model to read everything moves nothing. Only the layout moves the finding (C17).

Besides model I/O, the log shows where CB-4471 sits in each layout (computed in Python, before any API call), and
per review its decision and whether its reason cites the chargeback.

Run:  python poc2_key_findings.py     (2 runs, 1 query() call each; 1 optional run)
"""

import asyncio
import sys

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKError, ResultError, ResultMessage, query

from common import Settings, load_settings, log, log_model_io, setup_logging

SOURCES = [  # 9 back-office checks: a one-line key finding, then the detailed result it was drawn from
    {"name": "Order system",
     "key_finding": "ORD-9024, Nimbus portable speaker, $312.40, delivered 2026-04-06; returnable until 2026-05-06.",
     "details": "order ORD-9024 placed 2026-04-02 10:14 on the web store by CUST-1042\n"
                "item NIM-SPK-PT-02 Nimbus portable speaker, qty 1, unit price $312.40\n"
                "subtotal $312.40, discount $0.00, shipping $0.00, total charged $312.40\n"
                "picked and packed 2026-04-03 at WH-PDX-2; shipped 2026-04-04 with Lumen Freight, LH-60218837\n"
                "delivered 2026-04-06 14:22, left with the building concierge at 12 Alder St\n"
                "return policy RP-30-STD: returnable until 2026-05-06\n"
                "order status delivered; fulfilment status fulfilled; no holds on the record"},
    {"name": "Customer request",
     "key_finding": "CUST-1042 asked on 2026-04-25 for a full refund of $312.40: the speaker stopped charging.",
     "details": "ticket TCK-30418 opened 2026-04-25 09:03 by CUST-1042 (Dana Reyes) by email\n"
                "subject: Nimbus speaker no longer charges\n"
                "message: \"The speaker from ORD-9024 stopped charging after about ten days. I posted it back last "
                "week. Please refund the full $312.40 to my card.\"\n"
                "requested outcome: full refund of $312.40 to the original card\n"
                "attachments: 2 photos of the charging port and the order confirmation\n"
                "return request RR-2216 created online on 2026-04-19, return label issued the same day\n"
                "ticket status: waiting for review"},
    {"name": "Carrier tracking",
     "key_finding": "Return parcel LR-7781 reached the returns desk on 2026-04-24.",
     "details": "return parcel LR-7781, Lumen Freight, linked to order ORD-9024 and return request RR-2216\n"
                "2026-04-20 16:05 label scanned at drop-off point PDX-114\n"
                "2026-04-21 03:40 arrived at sorting hub PDX-HUB-1\n"
                "2026-04-22 11:18 left the sorting hub for the returns centre\n"
                "2026-04-23 18:47 arrived at the returns centre, queued for the returns desk\n"
                "2026-04-24 09:52 delivered to the returns desk, received by J. Okafor\n"
                "proof of delivery: signature captured, photo POD-99187 on file\n"
                "parcel weight 1.4 kg; outer box intact"},
    {"name": "Returns inspection",
     "key_finding": "Speaker received complete; charging fault confirmed; not resellable.",
     "details": "inspection RI-5530 for parcel LR-7781, order ORD-9024, started 2026-04-24 13:10\n"
                "contents: Nimbus portable speaker, USB-C cable, quick-start guide, original box\n"
                "completeness: all listed parts present; serial NPS-88214 matches the order\n"
                "power test: the unit does not charge from 3 known-good chargers\n"
                "port check: no physical damage, no liquid indicator triggered\n"
                "diagnosis: charging fault confirmed in the internal charging circuit\n"
                "grade C: not resellable; routed to supplier returns. Inspector M. Alvarez"},
    {"name": "Payments",  # the finding that blocks the refund, in source 5 of 9
     "key_finding": "Chargeback CB-4471 for $312.40 opened by the card issuer on 2026-04-21; still open.",
     "details": "2026-04-02 10:14 authorization AUTH-55102 approved: $312.40, Visa ending 4417, order ORD-9024\n"
                "2026-04-02 10:15 capture CAP-55102 settled: $312.40\n"
                "2026-04-03 02:00 settlement batch SB-0402 closed: 418 transactions, no exceptions\n"
                "2026-04-21 16:37 chargeback CB-4471 opened by the card issuer: $312.40 on ORD-9024, reason 13.3 "
                "(not as described), status open\n"
                "2026-04-22 02:00 settlement batch SB-0422 closed: 391 transactions, no exceptions\n"
                "2026-04-23 09:12 issuer notice: merchant response due by 2026-05-05\n"
                "2026-04-25 08:00 daily reconciliation completed: balances match"},
    {"name": "Fraud and risk",
     "key_finding": "Risk score 0.03 (low); no linked accounts, no recent address change.",
     "details": "risk evaluation RE-20931 for order ORD-9024, run 2026-04-02 10:14\n"
                "model score 0.03 (low); manual review starts at 0.60\n"
                "device fingerprint seen in 14 earlier sessions of CUST-1042\n"
                "billing and shipping address match: 12 Alder St, Portland, OR 97205\n"
                "linked accounts: none found across email, phone and card\n"
                "address changes in the last 90 days: none\n"
                "card checks: CVV match; 3-D Secure passed at checkout\n"
                "velocity: 1 order in 24 hours, within limits; no rule hits\n"
                "decision: auto-approved, no manual review"},
    {"name": "Product quality",
     "key_finding": "4 other charging-fault reports for batch B-2207 since 2026-04-01; supplier notified.",
     "details": "quality case QC-0612: Nimbus portable speaker NIM-SPK-PT-02, batch B-2207\n"
                "2026-04-01 first report: the unit stops charging after 1-2 weeks of use\n"
                "since 2026-04-01: 4 other charging-fault reports for batch B-2207, plus ORD-9024\n"
                "all affected units carry charging board revision R3\n"
                "2026-04-19 supplier Nimbus Audio notified, reference SUP-7740\n"
                "supplier reply 2026-04-22: investigation open, no recall decided yet\n"
                "batches B-2206 and B-2208: no reports so far\n"
                "QC owner K. Lindqvist; next review of batch B-2207 on 2026-05-03"},
    {"name": "Inventory",
     "key_finding": "12 units in stock; a replacement could ship on 2026-04-27.",
     "details": "item NIM-SPK-PT-02 Nimbus portable speaker at warehouse WH-PDX-2\n"
                "on hand 14, reserved 2, available 12\n"
                "available units by batch: B-2208 (12); no B-2207 units left in stock\n"
                "next inbound purchase order PO-3391: 40 units, expected 2026-05-02\n"
                "a replacement for ORD-9024 could ship on 2026-04-27 if the customer chooses one\n"
                "last cycle count 2026-04-20: no variance\n"
                "reorder point 10 units; lead time 12 days\n"
                "bin location A-14-03; units stored in their original cartons\n"
                "safety stock 5 units; no open transfer between warehouses"},
    {"name": "Customer history",
     "key_finding": "Gold tier since 2023; 1 earlier return, refunded; no earlier disputes.",
     "details": "customer CUST-1042 Dana Reyes, account opened 2023-02-11\n"
                "loyalty tier: gold since 2023, 4,812 points, next tier review in January\n"
                "lifetime orders: 23; lifetime spend $4,812.55\n"
                "returns: 1 earlier return, order ORD-8891 (Aurora floor lamp), refunded as RF-0001\n"
                "support contacts: 6 tickets, all resolved, average rating 4.8\n"
                "payment method on file: Visa ending 4417\n"
                "account flags: none; marketing opt-in: no\n"
                "preferred contact: email, in English\n"
                "last orders: ORD-9024 on 2026-04-02, ORD-8891 on 2026-03-03"},
]

ATTENTION_NOTE = "Read every finding carefully, including the ones in the middle, and don't miss anything."
QUESTION = "Question: Should Lumen Home approve the $312.40 refund for order ORD-9024 now?"

REVIEWER_PROMPT = (
    "You review refund requests for Lumen Home. Decide from the findings in the message whether to approve the "
    "refund now or hold it. Hold it if any finding shows that the money is already coming back to the customer "
    "another way, because a refund would then pay them twice; otherwise approve a refund the findings support. "
    "In reason, name every finding that drives your decision."
)
DECISION_SCHEMA = {"type": "object", "required": ["decision", "reason"],
                   "properties": {"decision": {"type": "string", "enum": ["approve", "hold"]},
                                  "reason": {"type": "string"}}}


def aggregate(sources: list[dict]) -> str:
    """Key Findings Summary first, one bullet per source, then the detailed results under explicit headers (C16).
    The bullets are the sources' own key findings: the aggregator only places text, it never rewrites it."""
    lines = ["## Key Findings Summary"]
    lines += [f"- {source['name']}: {source['key_finding']}" for source in sources]
    lines += ["", "## Detailed Results"]
    for n, source in enumerate(sources, 1):
        lines += ["", f"### {n}. {source['name']}", source["details"]]
    return "\n".join(lines)


def aggregate_plain(sources: list[dict]) -> str:
    """The naive aggregation: the details one after the other, with no summary and no headers."""
    return "\n\n".join(source["details"] for source in sources)


def position(text: str, needle: str = "CB-4471") -> float:
    """How far into the text the finding first appears: 0.0 = the very start, 1.0 = the end."""
    return text.index(needle) / len(text)


# The same findings in 3 layouts. Only "plain" and "structured" are reviewed; the note only adds words on top
LAYOUTS = {"plain": aggregate_plain(SOURCES),
           "note": f"{ATTENTION_NOTE}\n\n{aggregate_plain(SOURCES)}",  # the prompt-based "fix" (C17)
           "structured": aggregate(SOURCES)}

RUNS = [
    "plain",  # CB-4471 in the middle: a miss here is the lost-in-the-middle effect (C15)
    "structured",  # CB-4471 in the first 8%: the part of a long input that models read reliably
    # "note",  # optional: the plain layout with ATTENTION_NOTE on top
]


def build_review_options(settings: Settings) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=settings.model_id,
        system_prompt=REVIEWER_PROMPT,  # the same reviewer for every layout
        output_format={"type": "json_schema", "schema": DECISION_SCHEMA},  # the decision as validated JSON
        tools=[],  # no built-in tools: the findings are all in the prompt
        setting_sources=[],  # ignore ~/.claude settings, CLAUDE.md and hooks: the same run on any machine
        env={"ENABLE_TOOL_SEARCH": "false"},  # no ToolSearch calls
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=5,  # safety cap (01 C16)
        max_budget_usd=settings.max_budget_usd,  # cost guard per review
    )


async def review(settings: Settings, text: str) -> dict | None:
    """One query(): the aggregated findings, then the question. Returns {"decision", "reason"}, or None."""
    prompt = f"{text}\n\n{QUESTION}"
    log.info("MODEL INPUT   prompt       %s", prompt)
    decision = None
    try:
        async for message in query(prompt=prompt, options=build_review_options(settings)):
            log_model_io(message)
            if isinstance(message, ResultMessage) and message.subtype == "success":
                decision = message.structured_output  # None on a success result still counts as a failure
            # No `break`: a few system events can still arrive after the ResultMessage.
    except ResultError as exc:  # raised AFTER the error ResultMessage, e.g. error_max_structured_output_retries
        log.error("The review failed: %s", exc)
    return decision


async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc2_key_findings")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    for name, text in LAYOUTS.items():  # where the finding sits: decided by the layout, before any model reads it
        log.info("Layout %-10s CB-4471 at character %d of %d: %.1f%% of the way in",
                 name, text.index("CB-4471"), len(text), 100 * position(text))

    for name in RUNS:
        try:
            decision = await review(settings, LAYOUTS[name])
        except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
            log.error("SDK error: %s", exc)
            return 1
        if decision is None:
            log.error("Review of the %s layout: no decision", name)
            continue
        reason = str(decision.get("reason", ""))
        log.info("Review of the %s layout: %s; its reason cites the chargeback: %s", name, decision.get("decision"),
                 "CB-4471" in reason or "chargeback" in reason.lower())
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
