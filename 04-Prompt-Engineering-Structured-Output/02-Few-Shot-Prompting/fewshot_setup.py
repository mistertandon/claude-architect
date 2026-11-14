"""
fewshot_setup.py - the 5 test documents and their known values, ONE extraction schema, the 3 prompts under test
(no examples, examples as input/output pairs, examples with reasoning), the options, extract() and the scorer.

Model, schema, documents and options never change between arms: only the examples in the system prompt do (C11).
"""

import json
import re
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultError, ResultMessage, query

from common import Settings, log, log_model_io

# ---------------------------------------------------------------- the test set: 3 structures, known values (C2)

DOCUMENTS = {
    "T1": ("RIDGEWAY SHELVING CO.: INVOICE\n"
           "Invoice date: 2026-09-14 | Due date: 2026-10-14 | Bill to: Fernway Outfitters\n"
           "| Item                        | Qty | Unit price | Amount   |\n"
           "| Steel shelving unit, 5-tier | 4   | 310.00     | 1,240.00 |\n"
           "| Corner bracket kit          | 4   | 22.50      | 90.00    |\n"
           "| Total due                   |     |            | 1,330.00 |"),
    "T2": ("CLOUDNEST SOFTWARE: INVOICE\n"
           "Date: 2026-10-01 | Payment due: 2026-10-31 | Customer: Fernway Outfitters\n"
           "| Item                             | Qty | Unit price | Amount |\n"
           "| Inventory sync licence (monthly) | 3   | 120.00     | 360.00 |\n"
           "| Priority support add-on          | 1   | 85.00      | 85.00  |\n"
           "| Total due                        |     |            | 455.00 |"),  # the supplier's sum is 10.00 too high
    "N1": ("Summit Tentworks\n\nDear Fernway team,\n\nthis letter is our invoice, dated the third of September 2026. "
           "We delivered six Alpine two-person tents at one hundred eighty-nine dollars each, together with twelve "
           "packs of aluminium stakes at $7.50 a pack. As agreed, the replacement poles we sent last month remain free "
           "of charge. The total for this delivery is one thousand two hundred twenty-four dollars, payable within "
           "thirty days of the invoice date.\n\nKind regards,\nMarta Ruiz"),
    "N2": ("Okafor Sign Works, note dated 18 September 2026\n\nHi Fernway, a quick note to bill you for the "
           "trail-signage job at your Bend store: our crew installed fourteen trail signs at $45 each and used two "
           "bags of mounting hardware at twenty-two dollars a bag. That makes $674 in total.\n\nThanks,\nDev Okafor"),
    "M1": ("HOLLIS PEST CONTROL: Invoice HPC-5521\n"
           "Issued: 30/09/2026 (dates on this invoice are DD/MM/YYYY)\n"
           "| Service                       | Qty | Rate   | Amount |\n"
           "| Quarterly warehouse treatment | 1   | 260.00 | 260.00 |\n"
           "Notes: we also replaced 3 bait stations at $14.00 each; they are added to this invoice.\n"
           "Terms: payment due 15 days after the issue date.\n"
           "Total due: $302.00"),
}
DOC_TYPES = {"T1": "table", "T2": "table", "N1": "narrative", "N2": "narrative", "M1": "mixed"}

TRUTH = {  # line_items as (quantity, unit_price) pairs
    "T1": {"vendor_name": "Ridgeway Shelving Co.", "invoice_date": "2026-09-14", "due_date": "2026-10-14",
           "total_amount": 1330.00, "line_items": [(4, 310.00), (4, 22.50)]},
    "T2": {"vendor_name": "Cloudnest Software", "invoice_date": "2026-10-01", "due_date": "2026-10-31",
           "total_amount": 455.00, "line_items": [(3, 120.00), (1, 85.00)]},  # items sum to 445.00
    "N1": {"vendor_name": "Summit Tentworks", "invoice_date": "2026-09-03", "due_date": "2026-10-03",
           "total_amount": 1224.00, "line_items": [(6, 189.00), (12, 7.50)]},  # the free poles are not billed
    "N2": {"vendor_name": "Okafor Sign Works", "invoice_date": "2026-09-18", "due_date": None,  # no due date at all
           "total_amount": 674.00, "line_items": [(14, 45.00), (2, 22.00)]},
    "M1": {"vendor_name": "Hollis Pest Control", "invoice_date": "2026-09-30", "due_date": "2026-10-15",
           "total_amount": 302.00, "line_items": [(1, 260.00), (3, 14.00)]},
}
FIELDS = ["vendor_name", "invoice_date", "due_date", "total_amount", "line_items"]

# ---------------------------------------------------------------- one schema and the prompts under test

EXTRACTION_SCHEMA = {  # every field required and none nullable: the design before topic 03 (E2)
    "type": "object",
    "properties": {
        "vendor_name": {"type": "string"},
        "invoice_date": {"type": "string"},
        "due_date": {"type": "string"},
        "total_amount": {"type": "number"},
        "line_items": {"type": "array", "items": {
            "type": "object",
            "properties": {"description": {"type": "string"}, "quantity": {"type": "number"},
                           "unit_price": {"type": "number"}},
            "required": ["description", "quantity", "unit_price"]}},
    },
    "required": ["vendor_name", "invoice_date", "due_date", "total_amount", "line_items"],
}

BASE_PROMPT = (  # detailed instructions, no examples (C1)
    "You extract invoice data for the accounts-payable team of Fernway Outfitters, an outdoor-gear store. Fill every "
    "field from the document: vendor_name is the company that issued the invoice, as written; invoice_date is the "
    "date the invoice was issued and due_date the date payment is due, both as YYYY-MM-DD; total_amount is the total "
    "amount due, as a number without a currency symbol; line_items has one entry per billed product or service, with "
    "its description, quantity and unit_price as numbers. Use only information in the document.")


def _items(*rows: tuple[str, float, float]) -> list[dict]:
    return [{"description": d, "quantity": q, "unit_price": p} for d, q, p in rows]


EXAMPLES = [  # 3 invoices that are NOT in the test set, one per structure (C7), each with its reasoning (C8)
    {"structure": "table",
     "document": ("BRIGHTLINE PACKAGING: INVOICE\nInvoice date: 2026-08-02 | Due date: 2026-09-01\n"
                  "| Item                  | Qty | Unit price | Amount |\n"
                  "| Shipping boxes, large | 200 | 1.15       | 230.00 |\n"
                  "| Packing tape, 6-pack  | 10  | 8.40       | 84.00  |\n"
                  "| Total due             |     |            | 314.00 |"),
     "reasoning": ("Each product row is a line item with its Qty and Unit price. The Total due row is the invoice "
                   "total, not a line item. Both dates are already YYYY-MM-DD."),
     "extraction": {"vendor_name": "Brightline Packaging", "invoice_date": "2026-08-02", "due_date": "2026-09-01",
                    "total_amount": 314.00,
                    "line_items": _items(("Shipping boxes, large", 200, 1.15), ("Packing tape, 6-pack", 10, 8.40))}},
    {"structure": "narrative",
     "document": ("Juniper Lantern Co.\n\nHello Fernway, please treat this letter as our invoice, dated the fifth of "
                  "August 2026. We shipped eight brass camp lanterns at twenty-five dollars each and four replacement "
                  "glass globes at $6.50 apiece. The carry bags we included are complimentary. The amount due is two "
                  "hundred twenty-six dollars, payable within fourteen days of the invoice date."),
     "reasoning": ('This is a letter, so the facts are in sentences. "Dated the fifth of August 2026" is the invoice '
                   "date, 2026-08-05. Numbers written as words become digits: eight lanterns at 25.00, four globes at "
                   "6.50. The carry bags are complimentary, so nothing is billed and they are not a line item. "
                   '"Payable within fourteen days of the invoice date" gives the due date: 2026-08-05 plus 14 days is '
                   "2026-08-19. The total, 226.00, matches 8 x 25.00 + 4 x 6.50."),
     "extraction": {"vendor_name": "Juniper Lantern Co.", "invoice_date": "2026-08-05", "due_date": "2026-08-19",
                    "total_amount": 226.00,
                    "line_items": _items(("Brass camp lantern", 8, 25.00), ("Replacement glass globe", 4, 6.50))}},
    {"structure": "mixed",
     "document": ("CASCADE FILTERS LTD: Invoice CF-3307\nIssued: 12/08/2026 (dates on this invoice are DD/MM/YYYY)\n"
                  "| Product                | Qty | Rate  | Amount |\n"
                  "| Water filter cartridge | 20  | 18.00 | 360.00 |\n"
                  "Notes: we also sent 5 spare O-ring kits at $3.00 each, added to this invoice.\n"
                  "Terms: payment due 21 days after the issue date.\nTotal due: $375.00"),
     "reasoning": ("The header says the dates are DD/MM/YYYY, so 12/08/2026 is 12 August 2026: 2026-08-12. The table "
                   "has one product, and the note adds a second billed item, 5 O-ring kits at 3.00. The terms give the "
                   "due date: 2026-08-12 plus 21 days is 2026-09-02. The total, 375.00, matches 360.00 + 15.00."),
     "extraction": {"vendor_name": "Cascade Filters Ltd", "invoice_date": "2026-08-12", "due_date": "2026-09-02",
                    "total_amount": 375.00,
                    "line_items": _items(("Water filter cartridge", 20, 18.00), ("Spare O-ring kit", 5, 3.00))}},
]


def examples_block(with_reasoning: bool) -> str:
    """Each example: the document, (the reasoning,) and the extraction. Pairs leave the reasoning out (C9)."""
    return "Worked examples:\n" + "\n".join(
        f"<example>\n<document>\n{e['document']}\n</document>\n"
        + (f"<reasoning>{e['reasoning']}</reasoning>\n" if with_reasoning else "")
        + f"<extraction>{json.dumps(e['extraction'])}</extraction>\n</example>" for e in EXAMPLES)


PAIRS_PROMPT = BASE_PROMPT + "\n\n" + examples_block(False)  # input/output pairs only
FEWSHOT_PROMPT = BASE_PROMPT + "\n\n" + examples_block(True)  # the same examples, with their reasoning


def build_extract_options(settings: Settings, system_prompt: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=settings.model_id,  # one model for every arm
        system_prompt=system_prompt,  # the ONLY thing that changes between arms: the examples live here
        output_format={"type": "json_schema", "schema": EXTRACTION_SCHEMA},  # validated JSON: syntax never varies (E1)
        tools=[],  # no built-in tools: the document is in the prompt
        setting_sources=[],  # ignore ~/.claude settings, CLAUDE.md and hooks: the same run on any machine
        env={"ENABLE_TOOL_SEARCH": "false"},  # no ToolSearch calls
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=settings.max_turns,  # safety cap (01 C16)
        max_budget_usd=settings.max_budget_usd,  # cost guard per extraction call
    )


async def extract(settings: Settings, system_prompt: str, doc_id: str) -> dict | None:
    """One document = one query() = one NEW session: no other document, and no example but the prompt's."""
    prompt = f"Extract the invoice below.\n\n<document>\n{DOCUMENTS[doc_id]}\n</document>"
    log.info("MODEL INPUT   prompt       %s", prompt)
    data = None
    try:
        async for message in query(prompt=prompt, options=build_extract_options(settings, system_prompt)):
            log_model_io(message)
            if isinstance(message, ResultMessage) and message.subtype == "success":
                data = message.structured_output  # None here means no structured output: treat it as a failure
            # No `break`: a few system events can still arrive after the ResultMessage.
    except ResultError as exc:  # raised AFTER the error ResultMessage, e.g. error_max_structured_output_retries
        log.error("The extraction failed: %s", exc)
    return data


# ---------------------------------------------------------------- scoring against the known values

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", name.lower())


def score(doc_id: str, data: dict) -> dict[str, Any]:
    """Per field: correct, empty or wrong. N2's due_date has no true value: it keeps its raw value (the probe)."""
    truth, verdicts = TRUTH[doc_id], {}
    for field in FIELDS:
        value = data.get(field)
        if field == "due_date" and truth[field] is None:
            verdicts[field] = f"probe:{value!r}"  # fabrication probe (C15)
        elif value in ("", [], 0, None) or (isinstance(value, str) and not value.strip()):
            verdicts[field] = "empty"
        elif field == "vendor_name":
            verdicts[field] = "correct" if _norm(truth[field]) in _norm(value) else "wrong"
        elif field == "total_amount":
            verdicts[field] = "correct" if abs(value - truth[field]) < 0.01 else "wrong"
        elif field == "line_items":
            pairs = sorted((round(i["quantity"], 2), round(i["unit_price"], 2)) for i in value)
            verdicts[field] = "correct" if pairs == sorted(truth[field]) else "wrong"
        else:
            verdicts[field] = "correct" if value == truth[field] else "wrong"
    dates = [data.get(f) for f in ("invoice_date", "due_date") if data.get(f)]
    return {"verdicts": verdicts, "iso": [bool(ISO_DATE.match(d)) for d in dates], "data": data}
