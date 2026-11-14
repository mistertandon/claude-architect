"""
POC 2 - auto, any and a forced tool (Messages API)
==================================================
The Agent SDK has no tool_choice: every SDK tool call is effectively "auto". So this script calls the Messages API
directly, with three extraction tools and 4 inbox documents (2 invoices, a receipt, a newsletter):

    auto     Claude MAY call a tool, or reply in text: no guaranteed structured output
    any      Claude MUST call a tool, but picks which one: right when the document type is unknown
    forced   Claude MUST call extract_metadata: a mandatory first step, even when another tool fits better

strict: True on every tool makes a guaranteed call schema-valid too. Each call is one response: no tool_result is
sent back.

Besides model I/O, the log shows one line per call (tool chosen, schema problems) and one summary line per mode.

Run:  python poc2_tool_choice.py     (3 runs, 4 API calls each)
"""

import asyncio
import sys

import anthropic

from common import load_settings, log, log_model_io, setup_logging
from extraction_setup import DOCUMENTS, INVOICE_SCHEMA

FORCED_MODEL = "claude-haiku-5-5"  # accepts any/tool; Opus 5.5, Sonnet 5.5 and Fable 5.1 answer them with a 400 (E1)
MAX_TOKENS = 2048
INBOX = ["D1", "D4", "R1", "N1"]
INBOX_SYSTEM = "You are the inbox assistant of the Fernway Outfitters accounts-payable team."

RECEIPT_SCHEMA = {"type": "object", "additionalProperties": False,
                  "properties": {"merchant": {"type": "string"}, "total_amount": {"type": "number"},
                                 "payment_method": {"type": "string", "enum": ["card", "cash", "unclear", "other"]},
                                 "purchase_date": {"type": ["string", "null"]}},
                  "required": ["merchant", "total_amount", "payment_method"]}
METADATA_SCHEMA = {"type": "object", "additionalProperties": False,
                   "properties": {"document_type": {"type": "string", "enum": ["invoice", "receipt", "unclear", "other"]},
                                  "document_type_detail": {"type": ["string", "null"]},
                                  "sender": {"type": ["string", "null"]}},
                   "required": ["document_type"]}
TOOLS = [  # strict: True on every tool: the input must match its schema (E2)
    {"name": "extract_invoice", "strict": True, "input_schema": INVOICE_SCHEMA,
     "description": "Records a supplier invoice: a bill Fernway Outfitters must pay. Use it for invoices and "
                    "statements that ask for payment."},
    {"name": "extract_receipt", "strict": True, "input_schema": RECEIPT_SCHEMA,
     "description": "Records a receipt for a purchase that was already paid at the point of sale."},
    {"name": "extract_metadata", "strict": True, "input_schema": METADATA_SCHEMA,
     "description": "Records a document's type and sender: the mandatory first step for every inbox document, before "
                    "any type-specific extraction."},
]
SCHEMAS = {t["name"]: t["input_schema"] for t in TOOLS}
MODES = {"auto": {"type": "auto"}, "any": {"type": "any"}, "forced": {"type": "tool", "name": "extract_metadata"}}

RUNS = ["auto", "any", "forced"]


def check_input(data: dict, schema: dict) -> list[str]:
    """Problems of a tool input against its schema: a missing or unknown key, a wrong type, a value outside an enum."""
    types = {"string": str, "number": (int, float), "null": type(None)}
    problems = [f"missing {k}" for k in schema["required"] if k not in data]
    problems += [f"unknown {k}" for k in data if k not in schema["properties"]]
    for key, value in data.items():
        spec = schema["properties"].get(key, {})
        allowed = spec.get("type", [])
        allowed = allowed if isinstance(allowed, list) else [allowed]
        if allowed and not isinstance(value, tuple(types[t] for t in allowed)):
            problems.append(f"{key}: {type(value).__name__} is not {allowed}")
        if "enum" in spec and value not in spec["enum"]:
            problems.append(f"{key}: {value!r} is not in the enum")
    return problems


async def send(client: anthropic.AsyncAnthropic, mode: str, doc_id: str):
    """One Messages API call: the same tools and document every time; only tool_choice changes."""
    text = f"New document in the accounts inbox:\n\n{DOCUMENTS[doc_id]}"
    log.info("MODEL INPUT   prompt       %s  (tool_choice=%s)", text, MODES[mode])
    response = await client.messages.create(
        model=FORCED_MODEL, max_tokens=MAX_TOKENS, system=INBOX_SYSTEM, tools=TOOLS, tool_choice=MODES[mode],
        messages=[{"role": "user", "content": text}])
    log_model_io(response)
    return response


async def main() -> int:
    try:
        load_settings()  # puts ANTHROPIC_API_KEY from .env into the environment, where the client reads it
        setup_logging("poc2_tool_choice")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    client = anthropic.AsyncAnthropic()
    for mode in RUNS:
        called, text_only, problems = [], [], 0
        for doc_id in INBOX:
            try:
                response = await send(client, mode, doc_id)
            except anthropic.APIError as exc:  # e.g. a 400 if FORCED_MODEL doesn't support forced tool use
                log.error("%s %s: API error: %s", mode, doc_id, exc)
                continue
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:  # auto allowed a conversational reply: nothing to store (C7)
                text_only.append(doc_id)
                continue
            found = check_input(tool_uses[0].input, SCHEMAS[tool_uses[0].name])
            problems += len(found)
            called.append(f"{doc_id}->{tool_uses[0].name}")
            log.info("%-6s %s: %s, first block %s, schema problems %s", mode, doc_id, tool_uses[0].name,
                     response.content[0].type, found or "none")
        log.info("%-6s %d/%d called a tool %s; text only: %s; schema problems: %d", mode, len(called), len(INBOX),
                 called, text_only or "none", problems)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
