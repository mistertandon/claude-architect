"""
extraction_setup.py - what both POCs share: the documents and their known values, the two invoice schemas (the
honest one and the naive one), the options, extract() and the scorer.
"""

from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultError, ResultMessage, query

from common import Settings

# ---------------------------------------------------------------- the documents and their known values

INVOICES = {
    "D1": ("RIDGEWAY SHELVING CO.\nInvoice RS-20417\nDate: 2026-09-14\nBill to: Fernway Outfitters\n"
           "4 x steel warehouse shelving unit @ $460.00 = $1,840.00\nSales tax (8%): $147.20\nTotal due: $1,987.20"),
    "D2": ("CLOUDNEST SOFTWARE\nInvoice CN-88213\nIssued 2026-10-01\n"
           "Inventory sync subscription, October 2026: $450.00\nTax: $36.00\nAmount due: $486.00"),
    "D3": ("HOLLIS PEST CONTROL\nInvoice HPC-5521\n2026-09-30\nQuarterly warehouse pest treatment: $280.00\n"
           "Tax: $22.40\nTotal: $302.40"),
    "D4": ("Marta's Taxi Service\nMonthly statement for the Fernway Outfitters sales team\n"
           "14 rides between your Bend store and the airport\nFares: $351.36\nGST: $35.14\nPlease pay: $386.50\n"
           "Thank you!"),  # no invoice number, no date
    "D5": ("KESTREL RIDGE HOLDINGS\nDate: 2026-10-05\nFor: as agreed\nAmount due: $2,400.00\n"
           "Payment within 30 days."),  # no invoice number, no tax, and nothing says what was bought
}
RECEIPTS = {"R1": ("TRAILSIDE CAFE\n2026-10-12 08:41\n2 x flat white $4.50\n1 x breakfast burrito $9.75\n"
                   "Total $18.75\nPaid: Visa ****4417")}
OTHER = {"N1": ("Kestrel Supply newsletter: our autumn catalogue is out! New insulated jackets, and 20% off tents "
                "until 31 October. Visit kestrelsupply.example to browse.")}
DOCUMENTS = {**INVOICES, **RECEIPTS, **OTHER}

TRUTH = {  # vendor, total, category, detail (a word it must contain), number, date, tax
    "D1": ("Ridgeway Shelving Co.", 1987.20, "equipment", None, "RS-20417", "2026-09-14", 147.20),
    "D2": ("Cloudnest Software", 486.00, "software", None, "CN-88213", "2026-10-01", 36.00),
    "D3": ("Hollis Pest Control", 302.40, "other", "pest", "HPC-5521", "2026-09-30", 22.40),
    "D4": ("Marta's Taxi Service", 386.50, "travel", None, None, None, 35.14),
    "D5": ("Kestrel Ridge Holdings", 2400.00, "unclear", None, None, "2026-10-05", None),
}
ABSENT = {"D4": ["invoice_number", "invoice_date"], "D5": ["invoice_number", "tax_amount"]}  # 4 absent fields

# ---------------------------------------------------------------- the two schemas

CATEGORIES = ["equipment", "software", "office_supplies", "travel"]

INVOICE_SCHEMA = {  # 3 required fields, 3 optional nullable fields, an enum with unclear and other, a detail (C1)
    "type": "object",
    "properties": {
        "vendor_name": {"type": "string", "description": "The company that issued the invoice, as written."},
        "total_amount": {"type": "number", "description": "The total amount due."},
        "category": {"type": "string", "enum": CATEGORIES + ["unclear", "other"],
                     "description": "What was bought. unclear: the document doesn't say. other: no listed category "
                                    "fits; describe it in category_detail."},
        "category_detail": {"type": ["string", "null"],
                            "description": "Only when category is other: what was bought. Otherwise null."},
        "invoice_number": {"type": ["string", "null"], "description": "Exactly as printed, or null if the document has none."},
        "invoice_date": {"type": ["string", "null"], "description": "YYYY-MM-DD, or null if the document has none."},
        "tax_amount": {"type": ["number", "null"], "description": "As printed, or null if the document shows no tax."},
    },
    "required": ["vendor_name", "total_amount", "category"],  # only the 3 fields every invoice has (C4)
    "additionalProperties": False,  # required by strict tool use in POC 2 (E2)
}

NAIVE_SCHEMA = {  # the anti-pattern: every field required, no null, and no way out of the category list (C3)
    "type": "object",
    "properties": {
        "vendor_name": {"type": "string"}, "total_amount": {"type": "number"},
        "category": {"type": "string", "enum": CATEGORIES},
        "invoice_number": {"type": "string"}, "invoice_date": {"type": "string"}, "tax_amount": {"type": "number"},
    },
    "required": ["vendor_name", "total_amount", "category", "invoice_number", "invoice_date", "tax_amount"],
    "additionalProperties": False,
}

EXTRACT_PROMPT = ("You extract supplier invoices for the accounts-payable team of Fernway Outfitters. "
                  "Fill the fields from the document only.")


def build_extract_options(settings: Settings, schema: dict) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=settings.model_id,
        system_prompt=EXTRACT_PROMPT,  # the same prompt for both schemas: only the schema changes
        output_format={"type": "json_schema", "schema": schema},  # structured output through the StructuredOutput tool
        tools=[],  # no built-in tools: the document is in the prompt
        setting_sources=[],  # ignore ~/.claude settings, CLAUDE.md and hooks: the same run on any machine
        env={"ENABLE_TOOL_SEARCH": "false"},  # no ToolSearch calls
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=settings.max_turns,  # safety cap (01 C16), with room for schema retries
        max_budget_usd=settings.max_budget_usd,  # cost guard per extraction call
    )


async def extract(settings: Settings, doc_id: str, schema: dict) -> tuple[dict | None, str]:
    """One query(). Returns (structured_output or None, the result subtype)."""
    prompt = f"Extract this invoice.\n\n<document>\n{DOCUMENTS[doc_id]}\n</document>"
    data, subtype = None, "no result"
    try:
        async for message in query(prompt=prompt, options=build_extract_options(settings, schema)):
            if isinstance(message, ResultMessage):
                subtype = message.subtype
                if message.subtype == "success":
                    data = message.structured_output  # validated against the schema by the SDK
            # No `break`: a few system events can still arrive after the ResultMessage.
    except ResultError:  # e.g. error_max_structured_output_retries: no valid answer fit the schema
        pass
    return data, subtype


def score(doc_id: str, data: dict, schema: dict) -> dict[str, str]:
    """Per field: correct, null (right for an absent field), invented (a value the document doesn't have) or wrong."""
    vendor, total, category, detail, number, date, tax = TRUTH[doc_id]
    truth = {"vendor_name": vendor, "total_amount": total, "category": category, "invoice_number": number,
             "invoice_date": date, "tax_amount": tax}
    verdicts = {}
    for field, expected in truth.items():
        value = data.get(field)  # a missing key counts as null
        if field in ABSENT.get(doc_id, []):
            verdicts[field] = "null" if value is None else f"invented({value!r})"
        elif isinstance(expected, float):
            verdicts[field] = "correct" if isinstance(value, (int, float)) and abs(value - expected) < 0.01 else f"wrong({value!r})"
        elif field == "vendor_name":
            verdicts[field] = "correct" if value and expected.lower().rstrip(".") in value.lower() else f"wrong({value!r})"
        else:
            verdicts[field] = "correct" if value == expected else f"wrong({value!r})"
    if "category_detail" in schema["properties"]:  # only the honest schema has the detail field
        value = data.get("category_detail")
        verdicts["category_detail"] = ("correct" if (detail is None and value is None)
                                       or (detail and value and detail in value.lower()) else f"wrong({value!r})")
    return verdicts
