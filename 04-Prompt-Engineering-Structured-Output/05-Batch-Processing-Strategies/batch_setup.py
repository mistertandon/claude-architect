"""
batch_setup.py - the 20 generated invoices and their known values, the JSON schema, the 3 prompt versions, the one
function that builds every request, and the checks of a result.
"""

import json
from typing import Any

# The spec says 1024 / 80 line items / 8192. Opus 5.5 and Sonnet 5.5 always think, and thinking counts toward
# max_tokens, so these limits are doubled: a 2-3 item invoice keeps room to think, an outlier still overflows.
FIRST_MAX_TOKENS = 2048  # enough for a 2-3 item invoice plus thinking; the 2 outliers overflow it (E2)
RETRY_MAX_TOKENS = 16000  # the targeted change for the retry batch (C6)
OUTLIER_ITEMS = 120  # about 120 x 25 = 3,000 output tokens of JSON alone

BATCH_SCHEMA = {  # JSON outputs: every object needs additionalProperties: false
    "type": "object", "additionalProperties": False,
    "required": ["vendor_name", "invoice_date", "total_amount", "line_items"],
    "properties": {
        "vendor_name": {"type": "string"}, "invoice_date": {"type": "string"}, "total_amount": {"type": "number"},
        "line_items": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["description", "quantity", "unit_price"],
            "properties": {"description": {"type": "string"}, "quantity": {"type": "number"},
                           "unit_price": {"type": "number"}}}},
    },
}


def build_params(model: str, doc: dict, system_prompt: str, max_tokens: int = FIRST_MAX_TOKENS) -> dict[str, Any]:
    """One Messages API request body: the SAME dict for a synchronous sample call and for a batch entry (E1)."""
    return {
        "model": model,
        "max_tokens": max_tokens,  # includes thinking tokens (E2)
        "system": system_prompt,
        "messages": [{"role": "user", "content": doc["text"]}],
        "output_config": {"format": {"type": "json_schema", "schema": BATCH_SCHEMA}},  # the JSON is the text block
    }


# ---------------------------------------------------------------- 20 invoices, generated so the truth is known

VENDORS = ["Ridgeway Shelving Co.", "Cloudnest Software", "Hollis Pest Control", "Summit Tentworks",
           "Juniper Lantern Co.", "Cascade Filters Ltd"]
CATALOG = [("Steel shelving unit", 310.0), ("Corner bracket kit", 22.5), ("Inventory sync licence", 120.0),
           ("Priority support add-on", 85.0), ("Warehouse pest treatment", 260.0), ("Bait station", 14.0),
           ("Alpine two-person tent", 189.0), ("Aluminium stake pack", 7.5), ("Brass camp lantern", 25.0),
           ("Replacement glass globe", 6.5), ("Water filter cartridge", 18.0), ("Spare O-ring kit", 3.0)]
WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]


def make_documents() -> list[dict[str, Any]]:
    """doc-01..doc-18 cycle table -> narrative -> mixed; doc-19 and doc-20 are long outliers."""
    docs = []
    for n in range(1, 21):
        vendor, date = VENDORS[(n - 1) % len(VENDORS)], f"2026-10-{n:02d}"
        if n <= 18:
            structure = ["table", "narrative", "mixed"][(n - 1) % 3]
            (d1, p1), (d2, p2) = CATALOG[(2 * n) % 12], CATALOG[(2 * n + 1) % 12]
            q1, q2 = 2 + n % 11, 2 + (3 * n) % 11  # quantities 2-12
            items = [(d1, q1, p1), (d2, q2, p2)]
        else:
            structure = "outlier"
            items = [(f"{CATALOG[i % 12][0]} (lot {i + 1})", 1 + i % 5, CATALOG[i % 12][1]) for i in range(OUTLIER_ITEMS)]
        total = round(sum(q * p for _, q, p in items), 2)
        rows = "\n".join(f"| {d} | {q} | {p:.2f} | {q * p:.2f} |" for d, q, p in items)
        if structure in ("table", "outlier"):
            text = (f"{vendor.upper()}: INVOICE\nInvoice date: {date}\n| Item | Qty | Unit price | Amount |\n{rows}\n"
                    f"Total due: {total:.2f}")
        elif structure == "narrative":
            text = (f"{vendor}\n\nDear Fernway team, this letter is our invoice dated {date}. We delivered "
                    f'{WORDS[q1]} of item "{d1}" at ${p1:.2f} each and {WORDS[q2]} of item "{d2}" at ${p2:.2f} each. '
                    f"We also included a carry bag free of charge. The amount due is ${total:.2f}.")
        else:  # mixed: one item in the table, one in a note
            text = (f"{vendor.upper()}: INVOICE\nInvoice date: {date}\n| Item | Qty | Unit price | Amount |\n"
                    f"| {d1} | {q1} | {p1:.2f} | {q1 * p1:.2f} |\nNotes: we also sent {q2} x {d2} at ${p2:.2f} each, "
                    f"added to this invoice.\nTotal due: ${total:.2f}")
        docs.append({"id": f"doc-{n:02d}", "structure": structure, "text": text,
                     "truth": {"invoice_date": date, "total": total, "pairs": sorted((q, p) for _, q, p in items)}})
    return docs


SAMPLE = ["doc-01", "doc-02", "doc-03", "doc-04", "doc-05"]  # 2 tables, 2 letters, 1 mixed; no outlier

PROMPTS = [  # each version extends the last (C10)
    "Extract this supplier invoice: the vendor, the issue date as YYYY-MM-DD, the total amount due, and the line items.",
]
PROMPTS.append(PROMPTS[0] + " Include every billed item wherever it appears: table rows, sentences and notes.")
PROMPTS.append(PROMPTS[1] + " Items given free of charge are not billed: leave them out. Write every quantity in digits.")


def parse_output(message: Any) -> dict | None:
    """The JSON of a result, or None when it was cut off at max_tokens or isn't valid JSON."""
    if message.stop_reason == "max_tokens":
        return None
    text = next((b.text for b in message.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def is_correct(doc: dict, data: dict) -> bool:
    truth = doc["truth"]
    pairs = sorted((round(i["quantity"], 2), round(i["unit_price"], 2)) for i in data.get("line_items", []))
    return (data.get("invoice_date") == truth["invoice_date"] and abs(data.get("total_amount", 0) - truth["total"]) < 0.01
            and pairs == truth["pairs"])
