"""
validation_setup.py - the extraction schema with its self-check fields, the 5 test documents, the options, extract()
and validate(): the semantic checks that output_format can't do.
"""

from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultError, ResultMessage, query

from common import Settings, log, log_model_io

CURRENCIES = ["USD", "EUR", "GBP", "CAD"]  # checked in Python (enum validity), not in the schema
PATTERNS = ["table_row", "prose_sentence", "summary_row", "adjustment_row", "other"]

LINE_ITEM = {"type": "object", "additionalProperties": False,
             "required": ["description", "quantity", "unit_price", "amount", "detected_pattern"],
             "properties": {
                 "description": {"type": "string"}, "quantity": {"type": "number"},
                 "unit_price": {"type": "number"}, "amount": {"type": "number"},
                 "detected_pattern": {"type": "string", "enum": PATTERNS,  # which construct produced this finding (C1)
                                      "description": "Where this item was read from: a table row, a sentence, a "
                                                     "subtotal/tax/shipping row, a discount or credit row, or other."}}}

EXTRACTION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["vendor_name", "currency", "line_items", "calculated_total", "total_discrepancy", "conflict_detected"],
    "properties": {
        "vendor_name": {"type": "string"},
        "invoice_number": {"type": ["string", "null"]},  # nullable: absent stays null (topic 03)
        "invoice_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
        "due_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
        "currency": {"type": "string", "description": "ISO 4217 code, such as USD."},
        "line_items": {"type": "array", "items": LINE_ITEM},
        "stated_total": {"type": ["number", "null"], "description": "The total printed on the document."},
        # the self-check fields: Claude compares its own sum with the printed total (C2)
        "calculated_total": {"type": "number", "description": "Your own sum of the line item amounts."},
        "total_discrepancy": {"type": "boolean", "description": "True when calculated_total differs from stated_total."},
        "conflict_detected": {"type": "boolean", "description": "True when the document itself states conflicting values."},
    },
}

EXTRACT_PROMPT = ("You extract supplier invoices for the accounts-payable team of Fernway Outfitters. Use only the "
                  "document. Use null for a field the document doesn't contain. Compute calculated_total yourself and "
                  "compare it with the printed total.")

DOCUMENTS = {
    "F1": ("RIDGEWAY SHELVING CO.\nInvoice RS-20502\nInvoice date: 2026-10-14\nDue date: 2026-11-13\nCurrency: USD\n"
           "| Item | Qty | Unit price | Amount |\n| Steel shelving unit, 5-tier | 2 | 310.00 | 620.00 |\n"
           "| Shelf divider | 6 | 12.50 | 75.00 |\nTotal due: 695.00"),
    "F2": ("CLOUDNEST SOFTWARE\nInvoice CN-88407\nIssued: 2026-10-01\nDue: 2026-10-31\nCurrency: USD\n"
           "| Item | Qty | Unit price | Amount |\n| Inventory sync licence | 3 | 45.00 | 135.00 |\n"
           "| Onboarding session | 1 | 150.00 | 150.00 |\nTotal due: 285.00"),
    "U1": ("HOLLIS PEST CONTROL\nInvoice HPC-5590\nIssued: 2026-10-02\nCurrency: USD\n"
           "| Service | Qty | Rate | Amount |\n| Quarterly warehouse treatment | 1 | 280.00 | 280.00 |\nTotal: 280.00"),
    "U2": ("Marta's Taxi Service\nStatement date: 2026-10-01\nPay by: 2026-10-15\nCurrency: USD\n"
           "| Rides, Bend store to airport | 14 | 25.00 | 350.00 |\nTotal: 350.00"),
    "U3": ("KESTREL RIDGE HOLDINGS\nInvoice KRH-118\nDate: 2026-10-05\nDue: 2026-11-04\nCurrency: USD\n"
           "| Storage bay rental, October | 1 | 1,800.00 | 1,800.00 |\n| Forklift hire, 3 days | 3 | 200.00 | 600.00 |\n"
           "Total: see the attached statement."),
}


def _items(*rows: tuple[str, float, float]) -> list[dict]:
    return [{"description": d, "quantity": q, "unit_price": p, "amount": round(q * p, 2), "detected_pattern": "table_row"}
            for d, q, p in rows]


TRUTH = {  # the correct extractions of the two fixable documents
    "F1": {"vendor_name": "Ridgeway Shelving Co.", "invoice_number": "RS-20502", "invoice_date": "2026-10-14",
           "due_date": "2026-11-13", "currency": "USD",
           "line_items": _items(("Steel shelving unit, 5-tier", 2, 310.0), ("Shelf divider", 6, 12.5)),
           "stated_total": 695.0, "calculated_total": 695.0, "total_discrepancy": False, "conflict_detected": False},
    "F2": {"vendor_name": "Cloudnest Software", "invoice_number": "CN-88407", "invoice_date": "2026-10-01",
           "due_date": "2026-10-31", "currency": "USD",
           "line_items": _items(("Inventory sync licence", 3, 45.0), ("Onboarding session", 1, 150.0)),
           "stated_total": 285.0, "calculated_total": 285.0, "total_discrepancy": False, "conflict_detected": False},
}


def build_extract_options(settings: Settings) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=settings.model_id,
        system_prompt=EXTRACT_PROMPT,
        output_format={"type": "json_schema", "schema": EXTRACTION_SCHEMA},  # syntax is guaranteed here (C5)
        tools=[],  # no built-in tools: the document is in the prompt
        setting_sources=[],  # ignore ~/.claude settings, CLAUDE.md and hooks: the same run on any machine
        env={"ENABLE_TOOL_SEARCH": "false"},  # no ToolSearch calls
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=settings.max_turns,  # safety cap (01 C16)
        max_budget_usd=settings.max_budget_usd,  # cost guard per extraction call
    )


async def extract(settings: Settings, prompt: str) -> dict | None:
    """One query() = one NEW session: a retry prompt must carry everything Claude needs."""
    log.info("MODEL INPUT   prompt       %s", prompt)
    data = None
    try:
        async for message in query(prompt=prompt, options=build_extract_options(settings)):
            log_model_io(message)
            if isinstance(message, ResultMessage) and message.subtype == "success":
                data = message.structured_output  # already schema-valid: only semantic errors can remain
            # No `break`: a few system events can still arrive after the ResultMessage.
    except ResultError as exc:  # raised AFTER the error ResultMessage, e.g. error_max_structured_output_retries
        log.error("The extraction failed: %s", exc)
    return data


EXPECTED = {"invoice_number": "the invoice number as printed", "invoice_date": "the issue date (YYYY-MM-DD)",
            "due_date": "the payment due date (YYYY-MM-DD)", "stated_total": "the total printed on the document"}


def validate(data: dict) -> list[dict[str, Any]]:
    """Semantic checks (C4). Each error says what was expected and what was found (C6), and whether a retry can
    fix it: absent information and conflicts in the source can't be fixed by asking again (C10)."""
    errors = []

    def add(check: str, message: str, fixable: bool) -> None:
        errors.append({"check": check, "message": f"{check}: {message}", "fixable": fixable})

    for field, expected in EXPECTED.items():  # completeness
        if data.get(field) is None:
            add("completeness", f"{field} is null. Expected {expected}; found none.", False)
    if data.get("conflict_detected"):
        add("conflict", "the extraction reports conflicting values in the document itself.", False)
    items = data.get("line_items", [])
    for n, item in enumerate(items, 1):  # numeric consistency
        expected_amount = round(item["quantity"] * item["unit_price"], 2)
        if abs(item["amount"] - expected_amount) > 0.01:
            add("numeric", f"line {n} '{item['description']}' amount {item['amount']:.2f} != quantity "
                           f"{item['quantity']:g} x unit_price {item['unit_price']:.2f} = {expected_amount:.2f}.", True)
    total = round(sum(item["amount"] for item in items), 2)
    if abs(data["calculated_total"] - total) > 0.01:
        add("numeric", f"calculated_total {data['calculated_total']:.2f} != sum of line amounts {total:.2f}.", True)
    if data.get("stated_total") is not None and abs(data["calculated_total"] - data["stated_total"]) > 0.01:
        add("numeric", f"calculated_total {data['calculated_total']:.2f} != stated_total {data['stated_total']:.2f} "
                       f"(difference {abs(data['calculated_total'] - data['stated_total']):.2f}).", True)
    if data.get("currency") not in CURRENCIES:  # enum validity
        add("enum", f"currency {data.get('currency')!r} is not one of {', '.join(CURRENCIES)}.", True)
    if data.get("invoice_date") and data.get("due_date") and data["due_date"] < data["invoice_date"]:  # date order
        add("date_order", f"due_date {data['due_date']} is before invoice_date {data['invoice_date']}. Expected "
                          "due_date on or after invoice_date.", True)
    return errors
