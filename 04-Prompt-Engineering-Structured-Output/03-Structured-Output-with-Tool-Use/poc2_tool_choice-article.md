# POC 2: Auto, Any and a Forced Tool

> **File:** `poc2_tool_choice.py` (with `extraction_setup.py` and `common.py`)
> **Domain:** 04 Prompt Engineering & Structured Output → 03 Structured Output with Tool Use
> **SDK:** Anthropic Python SDK, Messages API (`anthropic>=2.0`; 2.8.0 in the folder's `.venv`), model `claude-haiku-5-5`
> **Page:** https://claude.ai/artifact/AZvPEjXkDisjN5DWvnsJBH

---

## 1. What this POC proves

This POC sends the same 4 inbox documents (2 invoices, a receipt, a newsletter) to the Messages API three times, with the same three extraction tools. Only `tool_choice` changes: `auto`, `any`, then a forced `extract_metadata`. Each call is one response; no `tool_result` is ever sent back. Every claim below is checked against one real run: `logs/poc2_tool_choice_20261114_023531.log`.

| # | Idea | Where it shows up in the code |
|---|------|------------------------------|
| 1 | **`tool_choice` decides whether a tool call is guaranteed.** `auto`: Claude may call a tool or reply in text. `any`: Claude must call a tool, and picks which. `tool`: Claude must call the named tool. | `MODES`, `send()` |
| 2 | **The Agent SDK has no `tool_choice`,** so this POC uses the Messages API directly. Opus 5.5, Sonnet 5.5 and Fable 5.1 answer `any` and `tool` with a 400 error, so it runs on `claude-haiku-5-5`. | `FORCED_MODEL`, `anthropic.AsyncAnthropic()` |
| 3 | **`strict: True` makes a guaranteed call schema-valid too.** `any` guarantees a call, not a valid input; `strict` constrains the input to the tool's schema. | `"strict": True` on every tool in `TOOLS` |
| 4 | **Tool descriptions steer selection.** `extract_metadata` says it is "the mandatory first step for every inbox document". | `TOOLS` descriptions |
| 5 | **Check, don't trust.** The script verifies every first tool call against its schema in plain Python, and reports which block came first. | `check_input()`; the per-call and summary lines in `main()` |
| 6 | **The honest schemas from POC 1 are reused.** `INVOICE_SCHEMA` (nullable optional fields, `unclear`/`other`) is the input schema of `extract_invoice`. | `from extraction_setup import DOCUMENTS, INVOICE_SCHEMA` |

The pattern in one line:

```
document + 3 tools + tool_choice ──messages.create()──▶ one response ──▶ tool_use block(s) or text ──▶ check_input(first call)
```

**What the real run showed, in one line:** all 12 responses called a tool, `auto` included. In every mode the first call was `extract_metadata`; under `any` and `forced`, Claude also called `extract_invoice` or `extract_receipt` in the same response, which the script's summary lines don't show. Section 5 has the details.

---

## 2. The files involved

```
03-Structured-Output-with-Tool-Use/
├── .env                      ← ANTHROPIC_API_KEY (POC 2 reads only the key), MODEL_ID, MAX_TURNS, MAX_BUDGET_USD
├── .env.example              ← the same keys, with placeholder values
├── requirements.txt          ← claude-agent-sdk, python-dotenv, anthropic>=2.0 (for this script)
├── common.py                 ← load_settings(), setup_logging(), log_model_io() (with a Messages API branch)
├── extraction_setup.py       ← DOCUMENTS (5 invoices, a receipt, a newsletter), INVOICE_SCHEMA (shared with POC 1)
├── poc1_schema_design.py     ← POC 1: naive vs nullable schema through the Agent SDK (not covered here)
├── poc2_tool_choice.py       ← entry point: 3 modes × 4 documents = 12 Messages API calls
├── README.md
└── logs/
    └── poc2_tool_choice_20261114_023531.log   ← the real run used in sections 3.2 and 5
```

Every snippet in this article is copied from these files, logging statements included. Each logging statement is named with the log line tag it writes, so you can find its output in the log file.

`poc2_tool_choice.py` holds almost everything itself:
- `common.py` covers **configuration and observability**: `load_settings()` puts the API key into the environment, and `log_model_io()` logs a Messages API response with the same tags POC 1 uses for SDK messages.
- `extraction_setup.py` covers **shared test material**: the documents and `INVOICE_SCHEMA`.
- `poc2_tool_choice.py` covers **capabilities and the experiment**: the receipt and metadata schemas, the three tools, the three `tool_choice` modes, `check_input()`, `send()` and the loop.

---

## 3. End-to-end execution flow

### 3.1 The big picture

```
python poc2_tool_choice.py
        │
        ▼
asyncio.run(main())                                                     [poc2_tool_choice.py]
        │
        ├─▶ load_settings()                                             [common.py]
        │      └─ .env → os.environ (ANTHROPIC_API_KEY); the returned Settings is not used
        ├─▶ setup_logging("poc2_tool_choice")                           [common.py]
        │      └─ console + logs/poc2_tool_choice_<date>_<time>.log, lines "HH:MM:SS  message"
        ├─▶ client = anthropic.AsyncAnthropic()                          reads ANTHROPIC_API_KEY
        │
        └─▶ for mode in RUNS:                      auto → any → forced
               ├─ for doc_id in INBOX:            D1, D4, R1, N1
               │     ├─ response = send(client, mode, doc_id)
               │     │     ├─ log.info("MODEL INPUT   prompt ... (tool_choice=...)")      → log: prompt
               │     │     ├─ client.messages.create(..., tools=TOOLS, tool_choice=MODES[mode])
               │     │     └─ log_model_io(response)                                    → log: tool_use / text / stop_reason
               │     ├─ APIError → log.error("<mode> <doc>: API error: ..."); continue
               │     ├─ no tool_use block → text_only.append(doc_id); continue
               │     ├─ found = check_input(tool_uses[0].input, SCHEMAS[tool_uses[0].name])
               │     └─ log.info("%-6s %s: %s, first block %s, schema problems %s")      → log: "<mode> <doc>: ..."
               └─ log.info("%-6s %d/%d called a tool ...")                              → log: "<mode> 4/4 called a tool ..."
```

There is no agent loop here. Each document is one request and one response, and this is what happens inside it; the right-hand column names the log line each step writes.

```
send(client, mode, doc_id)                                                            [poc2_tool_choice.py]
   │
   ├─ text = "New document in the accounts inbox:\n\n" + DOCUMENTS[doc_id]
   ├─ log.info("MODEL INPUT   prompt ... (tool_choice=...)")                       → log: prompt
   │
   ├─▶ await client.messages.create(model=FORCED_MODEL, system=INBOX_SYSTEM, tools=TOOLS,
   │                                tool_choice=MODES[mode], messages=[user: text])
   │      ┌──────────────── API-owned: one model response ─────────────────────────────┐
   │      │ auto   → Claude may think, then call 0, 1 or more tools, or answer in text  │
   │      │ any    → the response must contain a tool call; Claude picks the tool       │
   │      │ tool   → the response must call extract_metadata                            │
   │      │ strict → each tool input is constrained to that tool's input_schema         │
   │      │ returns Message(content=[thinking? text? tool_use...], stop_reason)         │
   │      └────────────────────────────────────────────────────────────────────────────┘
   │
   └─ log_model_io(response)                     one line per block, then stop_reason  → log: tool_use / stop_reason
   return response   (main() reads tool_use blocks; no tool is executed, no tool_result is sent)
```

### 3.2 One document across the three modes (D1, real output)

The values below come from the real run on 2026-11-14, recorded in `logs/poc2_tool_choice_20261114_023531.log`. The log holds model input, model output and the POC's own check lines. Each log line comes from one statement in the code:

| Log line tag | Source | Field logged | Written by |
|--------------|--------|--------------|------------|
| `MODEL INPUT   prompt` | *(none: the user message built in `send()`)* | `text` and `MODES[mode]` | `log.info("MODEL INPUT   prompt ... (tool_choice=%s)")` in `send()` |
| `MODEL OUTPUT  thinking` | `response.content` → block with `type == "thinking"` | `block.thinking`, only when non-empty | `log_model_io()`, Messages API branch (`common.py`). None in this log |
| `MODEL OUTPUT  text` | block with `type == "text"` | `block.text` | `log_model_io()`. None in this log |
| `MODEL OUTPUT  tool_use` | block with `type == "tool_use"` | `block.name`, `block.input`, `block.id` | `log_model_io()`: one line per `tool_use` block |
| `MODEL OUTPUT  stop_reason ... (Messages API)` | the response itself | `response.stop_reason` | `log_model_io()` |
| `<mode> <doc>: <tool>, first block <type>, schema problems <...>` | *(none: Python checks)* | `tool_uses[0].name`, `response.content[0].type`, `check_input()` | `log.info(...)` in `main()` |
| `<mode> N/4 called a tool [...]; text only: ...; schema problems: N` | *(none: Python counters)* | `called`, `text_only`, `problems` | `log.info(...)` in `main()` |
| `<mode> <doc>: API error: ...` | *(none)* | the `anthropic.APIError` | `main()`. None in this log |
| `HH:MM:SS` at the start of each line | *(none)* | the time the line was logged | the formatter in `setup_logging()` |

D1 is plainly an invoice. The same request three times, only `tool_choice` different:

```
── auto ─────────────────────────────────────────────────────────────────────────
02:35:31  (input)  prompt = New document in the accounts inbox:\n\nRIDGEWAY SHELVING CO. ... Total due: $1,987.20
                   tool_choice = {'type': 'auto'}                                      log: prompt
02:35:40  response.content[0]  type = "thinking"   (block.thinking empty → no log line)
          response.content[1]  tool_use                                                 log: tool_use
            name  = "extract_metadata"
            input = {'document_type': 'invoice', 'sender': 'Ridgeway Shelving Co.'}
            id    = "toolu_01V2GxsUDbK2jzoyA5MxsnYo"
          response.stop_reason = "tool_use"                                             log: stop_reason
02:35:40  (check)  auto   D1: extract_metadata, first block thinking, schema problems none

── any ──────────────────────────────────────────────────────────────────────────
02:35:48  (input)  tool_choice = {'type': 'any'}
02:35:56  response.content[0]  tool_use                                                 log: tool_use
            name  = "extract_metadata"
            input = {'document_type': 'invoice', 'sender': 'RIDGEWAY SHELVING CO.'}
            id    = "toolu_01L1ApmJ4sVbd2s2ktBPRkcS"
          response.content[1]  tool_use                                                 log: tool_use
            name  = "extract_invoice"                                                   ← a second call, same response
            input = {'vendor_name': 'RIDGEWAY SHELVING CO.', 'total_amount': 1987.2,
                     'category': 'equipment', 'invoice_date': '2026-09-14', 'tax_amount': 147.2}
            id    = "toolu_01MPWpTZq45csGPR75FbtiWX"
          response.stop_reason = "tool_use"
02:35:56  (check)  any    D1: extract_metadata, first block tool_use, schema problems none

── forced: {'type': 'tool', 'name': 'extract_metadata'} ─────────────────────────
02:36:03  (input)  tool_choice = {'type': 'tool', 'name': 'extract_metadata'}
02:36:04  response.content[0]  tool_use  extract_metadata {'document_type': 'invoice',
                                         'sender': 'RIDGEWAY SHELVING CO.'}  (id=toolu_01NVGLrtckmYgNgLEiVkPpsu)
          response.content[1]  tool_use  extract_invoice {'vendor_name': 'RIDGEWAY SHELVING CO.',
                                         'total_amount': 1987.2, 'category': 'equipment',
                                         'invoice_date': '2026-09-14', 'tax_amount': 147.2}
                                         (id=toolu_01GfVLECHBQHZBrhqAa1M15a)
          response.stop_reason = "tool_use"
02:36:04  (check)  forced D1: extract_metadata, first block tool_use, schema problems none
```

What to notice in the real data:
- **`auto` didn't reply in text here.** Claude called `extract_metadata` for D1, and for every other document too. The description says it's "the mandatory first step for every inbox document", and Claude followed it.
- **`auto` thinks first; `any` and `forced` don't.** Under `auto` the first block was a `thinking` block on all 4 documents; under `any` and `forced` it was `tool_use` on all 8. The `first block ...` part of each check line comes from `response.content[0].type`. The thinking text itself was empty, so `log_model_io()` (which logs only non-empty thinking) wrote no `thinking` line.
- **Two tool calls in one response.** Under `any` and `forced`, D1 got `extract_metadata` *and* `extract_invoice`. `log_model_io()` logs every `tool_use` block, so both appear; `main()` looks only at `tool_uses[0]`, so its check line names only `extract_metadata`.
- **Forcing a tool doesn't make it the only one.** `forced` guaranteed `extract_metadata` as the first call, and Claude still added `extract_invoice`, the tool that fits better, right after it.
- **`stop_reason = "tool_use"` every time.** With a tool call in the response, the API stops and waits for a `tool_result`. This script never sends one, so each document ends there.
- **Sender casing differs between modes:** `Ridgeway Shelving Co.` under `auto`, `RIDGEWAY SHELVING CO.` under `any` and `forced`. `METADATA_SCHEMA` gives `sender` no description, so nothing asks for one form.
- **Not shown:** the model name, token usage and the response `id` are on the response object, but `log_model_io()` doesn't log them. Tool results don't exist in this POC, so there is no `tool_result` line.

---

## 4. Code walkthrough

The snippets follow the order in which the code runs. Each one ends with the log lines it writes, copied from the real log (long values trimmed with `...`).

### 4.1 Module docstring: why the Messages API

```python
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
```

**Why it matters:**
- **Why not the Agent SDK:** `ClaudeAgentOptions` has no `tool_choice`, so every SDK tool call is effectively `auto`. To see the three modes side by side, the script talks to the API directly. (POC 1's guarantee in the SDK is `output_format`.)
- **The three modes in one table:** MAY / MUST, any tool / MUST, this tool. That's the exam distinction.
- **"Each call is one response":** no agent loop, no tool execution. The test is only *what Claude asks to call*.

---

### 4.2 Imports and constants

```python
import asyncio
import sys

import anthropic

from common import load_settings, log, log_model_io, setup_logging
from extraction_setup import DOCUMENTS, INVOICE_SCHEMA

FORCED_MODEL = "claude-haiku-5-5"  # accepts any/tool; Opus 5.5, Sonnet 5.5 and Fable 5.1 answer them with a 400 (E1)
MAX_TOKENS = 2048
INBOX = ["D1", "D4", "R1", "N1"]
INBOX_SYSTEM = "You are the inbox assistant of the Fernway Outfitters accounts-payable team."
```

| Name | Value | Why |
|------|-------|-----|
| `anthropic` | the Anthropic Python SDK | Direct Messages API access, where `tool_choice` exists |
| `DOCUMENTS`, `INVOICE_SCHEMA` | from `extraction_setup.py` | Same documents and honest invoice schema as POC 1 |
| `FORCED_MODEL` | `claude-haiku-5-5` | Accepts `any` and `tool`; the code comment says the 5.5 Opus/Sonnet and Fable 5.1 models return a 400 for them |
| `MAX_TOKENS` | `2048` | Enough for thinking plus one or two tool calls |
| `INBOX` | `D1`, `D4`, `R1`, `N1` | A complete invoice, a statement with missing fields, a receipt, a newsletter: one per kind of decision |
| `INBOX_SYSTEM` | a one-line role | Deliberately says nothing about which tool to use; the descriptions do that |

**Agentic concept:** model capabilities differ. A feature you rely on (here, forced tool use) must be checked against the model you deploy. `MODEL_ID` from `.env` is ignored by this script on purpose.

---

### 4.3 The three schemas and the three tools

```python
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
```

| Tool | When its description says to use it | Schema highlights |
|------|--------------------------------------|-------------------|
| `extract_invoice` | invoices and statements that ask for payment | POC 1's honest schema: 3 required, nullable optional fields, `unclear`/`other` |
| `extract_receipt` | purchases already paid at the point of sale | `payment_method` enum with `unclear`/`other`; nullable `purchase_date` |
| `extract_metadata` | **every** inbox document, **first**, before any type-specific extraction | only `document_type` required; `other` + `document_type_detail` |

**Why it matters:**
- **The description is the prompt.** Nothing in `INBOX_SYSTEM` or the user message says which tool to call. Claude picks from the descriptions, and `extract_metadata`'s "mandatory first step" wording shaped every response in the log.
- **`strict: True` on every tool.** Under `any`, Claude must call a tool, but without `strict` the input could still miss a required key or break an enum. `strict` constrains the input to the schema, which needs `additionalProperties: False` on every object (hence that key in all three schemas and in `INVOICE_SCHEMA`).
- **Honest escape values everywhere:** `unclear` and `other` in both enums, `null` for optional fields. A newsletter can be `document_type: "other"` with a detail instead of being forced into `invoice` or `receipt`.
- **`SCHEMAS`** maps a tool name back to its schema, so `check_input()` can verify whichever tool Claude chose.

**Anti-pattern avoided:** a newsletter has no matching extraction tool. Without `extract_metadata` and its `other` value, `any` would force Claude to file it as an invoice or a receipt.

---

### 4.4 The modes

```python
MODES = {"auto": {"type": "auto"}, "any": {"type": "any"}, "forced": {"type": "tool", "name": "extract_metadata"}}

RUNS = ["auto", "any", "forced"]
```

| Mode | `tool_choice` | Guarantee | Use it when |
|------|---------------|-----------|-------------|
| `auto` | `{"type": "auto"}` | none: a tool call or a text reply | a conversation where text is a valid answer |
| `any` | `{"type": "any"}` | at least one tool call; Claude picks the tool | you need structured output and the document type is unknown |
| `forced` | `{"type": "tool", "name": "extract_metadata"}` | that tool is called | a mandatory step must run (metadata before enrichment) |

---

### 4.5 `check_input()`: a schema check you can read

```python
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
```

**Why it matters:**
- **Four checks, flat schemas only:** a required key is missing, a key is unknown (`additionalProperties: False`), a value has the wrong type (`null` allowed only where the type list has it), or a value is outside its `enum`.
- **An empty list means valid.** `main()` adds `len(found)` to `problems` and logs `schema problems none` when the list is empty.
- **Independent of `strict`.** The point is to verify the guarantee, not assume it. All 12 checked calls had no problems.
- **Limit to know:** it doesn't check that optional fields are *present*. A present-but-omitted invoice number passes (section 5.2).

---

### 4.6 `send()`: one request, one response

```python
async def send(client: anthropic.AsyncAnthropic, mode: str, doc_id: str):
    """One Messages API call: the same tools and document every time; only tool_choice changes."""
    text = f"New document in the accounts inbox:\n\n{DOCUMENTS[doc_id]}"
    log.info("MODEL INPUT   prompt       %s  (tool_choice=%s)", text, MODES[mode])
    response = await client.messages.create(
        model=FORCED_MODEL, max_tokens=MAX_TOKENS, system=INBOX_SYSTEM, tools=TOOLS, tool_choice=MODES[mode],
        messages=[{"role": "user", "content": text}])
    log_model_io(response)
    return response
```

**Why it matters:**
- **Everything is fixed except `tool_choice=MODES[mode]`:** model, system prompt, tools, document, `max_tokens`.
- **The user message doesn't say "extract".** "New document in the accounts inbox" leaves room for a conversational reply under `auto`, which is the failure mode the POC wants to expose.
- **A single-turn `messages` list.** Each call starts fresh; no earlier document is in the context.
- **The prompt log line carries the mode,** so each block of the log names its `tool_choice`.

Log line it wrote:

```
02:35:46  MODEL INPUT   prompt       New document in the accounts inbox:

Kestrel Supply newsletter: our autumn catalogue is out! New insulated jackets, and 20% off tents until 31 October. Visit kestrelsupply.example to browse.  (tool_choice={'type': 'auto'})
```

---

### 4.7 `main()`: three modes, four documents, three counters

#### a) Setup

```python
async def main() -> int:
    try:
        load_settings()  # puts ANTHROPIC_API_KEY from .env into the environment, where the client reads it
        setup_logging("poc2_tool_choice")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    client = anthropic.AsyncAnthropic()
```

`load_settings()` is called only for its side effect: `load_dotenv()` puts the key into `os.environ`, and `AsyncAnthropic()` reads `ANTHROPIC_API_KEY` from there. The returned `Settings` (model, turns, budget) isn't used: this script has no agent loop to cap.

#### b) The loop and its checks

```python
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
```

**Why it matters:**
- **An API error doesn't stop the run.** If the model rejects a mode (the 400 the comment mentions), the document is logged and skipped. None in this log.
- **"Text only" is the `auto` failure.** A response without a `tool_use` block gives the pipeline nothing to store. The code counts it instead of crashing.
- **`response.content[0].type`** shows whether the API put the tool call first. Under `any` and `tool`, the call came first; under `auto`, thinking came first.
- **Only the first tool call is checked and reported.** `tool_uses[0]` is what `check_input()`, `called` and the per-call line see. Any further `tool_use` blocks in the same response are logged by `log_model_io()` but not checked or counted. In the real run, that hid 6 of the 18 tool calls (section 5).

Log lines it wrote (`any` mode):

```
02:35:56  any    D1: extract_metadata, first block tool_use, schema problems none
02:36:03  any    4/4 called a tool ['D1->extract_metadata', 'D4->extract_metadata', 'R1->extract_metadata', 'N1->extract_metadata']; text only: none; schema problems: 0
```

---

### 4.8 `__main__`

```python
if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

`asyncio.run()` runs the async `main()` (the client is `AsyncAnthropic`, so every call is awaited); `sys.exit()` passes `0` or `1` to the shell.

---

### 4.9 `log_model_io()` for a Messages API response (from `common.py`)

```python
def log_model_io(message: Any) -> None:
    """Log the model input or output carried by one message from the query() stream, or by one Messages API
    response."""
    if isinstance(message, AssistantMessage):  # Claude's response = model OUTPUT
        ...
    elif getattr(message, "type", None) == "message":  # a Messages API response (POC 2): no SDK loop around it
        for block in message.content:
            if block.type == "thinking" and block.thinking:
                log.info("MODEL OUTPUT  thinking     %s", block.thinking)
            elif block.type == "text":
                log.info("MODEL OUTPUT  text         %s", block.text)
            elif block.type == "tool_use":
                log.info("MODEL OUTPUT  tool_use     %s %s  (id=%s)", block.name, block.input, block.id)
        log.info("MODEL OUTPUT  stop_reason  %s  (Messages API)", message.stop_reason)
```

**Why it matters:**
- **Same tags as the SDK branches,** so POC 1's and POC 2's logs read the same way. The `(Messages API)` suffix replaces `(loop result: ...)`, because there is no loop and no `subtype`.
- **Every `tool_use` block gets its own line.** That's why the log shows the second calls that `main()` doesn't report.
- **Thinking only when non-empty.** The `auto` responses started with a `thinking` block (per the check lines) whose text was empty, so no `thinking` line appears.

---

### 4.10 `load_settings()` and `setup_logging()` (from `common.py`)

```python
def load_settings() -> Settings:
    """Read .env. The SDK's Claude Code process takes ANTHROPIC_API_KEY from the environment."""
    env_file = POC_DIR / ".env"
    if not env_file.is_file():
        raise RuntimeError(f"{env_file} not found: copy .env.example to .env and add your API key")
    load_dotenv(env_file, override=True)  # .env wins over variables already set in your shell
    if os.getenv("ANTHROPIC_API_KEY", "") in ("", "your-api-key-here"):
        raise RuntimeError(f"set ANTHROPIC_API_KEY in {env_file}")
    ...


def setup_logging(script_name: str) -> None:
    """Log to the console and to logs/<script>_<time>.log, so a paid run can be re-read later."""
    log_dir = POC_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"{script_name}_{datetime.now():%Y%m%d_%H%M%S}.log"
    ...
```

**Why it matters:** the key never appears in code; `load_dotenv(..., override=True)` makes `.env` win over the shell. The log file name `poc2_tool_choice_20261114_023531.log` is the start time, 02:35:31, the time of the first log line.

---

### 4.11 The documents (from `extraction_setup.py`)

```python
INVOICES = {
    "D1": ("RIDGEWAY SHELVING CO.\nInvoice RS-20417\nDate: 2026-09-14\nBill to: Fernway Outfitters\n"
           "4 x steel warehouse shelving unit @ $460.00 = $1,840.00\nSales tax (8%): $147.20\nTotal due: $1,987.20"),
    ...
    "D4": ("Marta's Taxi Service\nMonthly statement for the Fernway Outfitters sales team\n"
           "14 rides between your Bend store and the airport\nFares: $351.36\nGST: $35.14\nPlease pay: $386.50\n"
           "Thank you!"),  # no invoice number, no date
    ...
}
RECEIPTS = {"R1": ("TRAILSIDE CAFE\n2026-10-12 08:41\n2 x flat white $4.50\n1 x breakfast burrito $9.75\n"
                   "Total $18.75\nPaid: Visa ****4417")}
OTHER = {"N1": ("Kestrel Supply newsletter: our autumn catalogue is out! New insulated jackets, and 20% off tents "
                "until 31 October. Visit kestrelsupply.example to browse.")}
DOCUMENTS = {**INVOICES, **RECEIPTS, **OTHER}
```

| Id | Kind | Best-fitting tool | Why it's in the inbox |
|----|------|-------------------|-----------------------|
| D1 | complete invoice | `extract_invoice` | Under `forced`, it shows the named tool winning over the obvious one |
| D4 | statement, no number, no date | `extract_invoice` ("statements that ask for payment") | Tests the description's edge and the nullable fields |
| R1 | paid receipt | `extract_receipt` | A second type-specific tool to choose |
| N1 | newsletter | none of the type-specific tools | Under `auto`, the expected text reply; under `any`, the test of `other` |

---

## 5. Turn-by-turn trace of each run (real output)

Each run is 4 Messages API calls, one response each. Times are from `logs/poc2_tool_choice_20261114_023531.log`.

### 5.1 Run 1: `auto`

```
02:35:40  MODEL OUTPUT  tool_use     extract_metadata {'document_type': 'invoice', 'sender': 'Ridgeway Shelving Co.'}  (id=toolu_01V2GxsUDbK2jzoyA5MxsnYo)
02:35:40  MODEL OUTPUT  stop_reason  tool_use  (Messages API)
02:35:40  auto   D1: extract_metadata, first block thinking, schema problems none
02:35:44  MODEL OUTPUT  tool_use     extract_metadata {'document_type': 'invoice', 'document_type_detail': 'Monthly statement requesting payment for 14 taxi rides', 'sender': "Marta's Taxi Service"}  (id=toolu_01SAPJvdR9tnxd198Z1MBM4d)
02:35:44  auto   D4: extract_metadata, first block thinking, schema problems none
02:35:46  MODEL OUTPUT  tool_use     extract_metadata {'document_type': 'receipt', 'sender': 'TRAILSIDE CAFE'}  (id=toolu_01LSaAqBcF7GcvCW29XTjvgu)
02:35:46  auto   R1: extract_metadata, first block thinking, schema problems none
02:35:48  MODEL OUTPUT  tool_use     extract_metadata {'document_type': 'other', 'document_type_detail': 'Marketing newsletter (autumn catalogue announcement with promotional offer). No payment requested.', 'sender': 'Kestrel Supply'}  (id=toolu_01UtrYbnYm9xCBBC9RVaiiKs)
02:35:48  MODEL OUTPUT  stop_reason  tool_use  (Messages API)
02:35:48  auto   N1: extract_metadata, first block thinking, schema problems none
02:35:48  auto   4/4 called a tool ['D1->extract_metadata', 'D4->extract_metadata', 'R1->extract_metadata', 'N1->extract_metadata']; text only: none; schema problems: 0
```

| Document | `tool_use` blocks (all logged) | `content[0].type` | `stop_reason` | `check_input()` |
|----------|-------------------------------|-------------------|---------------|-----------------|
| D1 | `extract_metadata` (invoice) | `thinking` | `tool_use` | `[]` |
| D4 | `extract_metadata` (invoice, detail "Monthly statement ...") | `thinking` | `tool_use` | `[]` |
| R1 | `extract_metadata` (receipt) | `thinking` | `tool_use` | `[]` |
| N1 | `extract_metadata` (other, "Marketing newsletter ... No payment requested.") | `thinking` | `tool_use` | `[]` |

| Variable (code) | Value |
|-----------------|-------|
| `called` | `['D1->extract_metadata', 'D4->extract_metadata', 'R1->extract_metadata', 'N1->extract_metadata']` |
| `text_only` | `[]` → logged as `none` |
| `problems` | `0` |
| `anthropic.APIError` | not raised |
| Wall time | 02:35:31 → 02:35:48, about 17 s (D1 alone 9 s) |

Lessons from the real data:
- **No text reply this time.** The curriculum expects `auto` to answer at least one document (typically N1) in text. In this run all 4 got a tool call. `auto` *allows* a text reply; it didn't *produce* one here, most likely because `extract_metadata` describes itself as mandatory for every document. One clean run doesn't make `auto` a guarantee: nothing in the request requires a call.
- **One call per response, and it was the first step only.** Under `auto`, Claude called `extract_metadata` and stopped (`stop_reason` `tool_use`), apparently waiting for its result before any type-specific extraction, as the description says ("before any type-specific extraction"). The pipeline got metadata, but no invoice or receipt fields.
- **The metadata was right.** D1 and D4 `invoice`, R1 `receipt`, N1 `other` with a detail that says why.

### 5.2 Run 2: `any`

```
02:35:56  MODEL OUTPUT  tool_use     extract_metadata {'document_type': 'invoice', 'sender': 'RIDGEWAY SHELVING CO.'}  (id=toolu_01L1ApmJ4sVbd2s2ktBPRkcS)
02:35:56  MODEL OUTPUT  tool_use     extract_invoice {'vendor_name': 'RIDGEWAY SHELVING CO.', 'total_amount': 1987.2, 'category': 'equipment', 'invoice_date': '2026-09-14', 'tax_amount': 147.2}  (id=toolu_01MPWpTZq45csGPR75FbtiWX)
02:35:56  any    D1: extract_metadata, first block tool_use, schema problems none
02:35:59  MODEL OUTPUT  tool_use     extract_metadata {'document_type': 'invoice', 'document_type_detail': 'Monthly statement requesting payment for 14 taxi rides between Bend store and airport', 'sender': "Marta's Taxi Service"}  (id=toolu_01L9VvpyLgjxiU6U1EbzWiBx)
02:35:59  MODEL OUTPUT  tool_use     extract_invoice {'vendor_name': "Marta's Taxi Service", 'total_amount': 386.5, 'category': 'travel', 'tax_amount': 35.14}  (id=toolu_01G4cRvh8dGe2vJKj3tcVMao)
02:35:59  any    D4: extract_metadata, first block tool_use, schema problems none
02:36:01  MODEL OUTPUT  tool_use     extract_metadata {'document_type': 'receipt', 'document_type_detail': 'Point-of-sale receipt from Trailside Cafe, already paid by Visa ****4417', 'sender': 'TRAILSIDE CAFE'}  (id=toolu_01SM4PSnhPvjqoXBzTK5tmto)
02:36:01  MODEL OUTPUT  tool_use     extract_receipt {'merchant': 'TRAILSIDE CAFE', 'total_amount': 18.75, 'payment_method': 'card', 'purchase_date': '2026-10-12'}  (id=toolu_016ojo87eVsTXzve5sZUoJEQ)
02:36:01  any    R1: extract_metadata, first block tool_use, schema problems none
02:36:03  MODEL OUTPUT  tool_use     extract_metadata {'document_type': 'other', 'document_type_detail': 'Marketing newsletter from Kestrel Supply promoting an autumn catalogue and a 20% tent discount until 31 October. No payment request.', 'sender': 'Kestrel Supply'}  (id=toolu_01J3HNSTub9XgvbKfq2Kbbna)
02:36:03  any    N1: extract_metadata, first block tool_use, schema problems none
02:36:03  any    4/4 called a tool ['D1->extract_metadata', 'D4->extract_metadata', 'R1->extract_metadata', 'N1->extract_metadata']; text only: none; schema problems: 0
```

| Document | 1st `tool_use` (checked) | 2nd `tool_use` (logged, not checked by the code) | `content[0].type` |
|----------|--------------------------|--------------------------------------------------|-------------------|
| D1 | `extract_metadata` invoice | `extract_invoice`: vendor, 1987.2, `equipment`, 2026-09-14, tax 147.2 | `tool_use` |
| D4 | `extract_metadata` invoice | `extract_invoice`: vendor, 386.5, `travel`, tax 35.14 (no number, no date) | `tool_use` |
| R1 | `extract_metadata` receipt | `extract_receipt`: `TRAILSIDE CAFE`, 18.75, `card`, 2026-10-12 | `tool_use` |
| N1 | `extract_metadata` other | none | `tool_use` |

| Variable (code) | Value |
|-----------------|-------|
| `called` | 4 × `->extract_metadata` (only `tool_uses[0]`) |
| `text_only` / `problems` | `none` / `0` |
| `response.stop_reason` | `tool_use` × 4 |
| Wall time | 02:35:48 → 02:36:03, about 15 s (D1 alone 8 s) |

Lessons from the real data:
- **`any` guaranteed a tool call: 4 of 4, the call first, no text before it.** That's the curriculum's acceptance for `any`: `stop_reason` `tool_use`, first block `tool_use`, no text-only responses, valid input.
- **The type-specific extraction happened, in the same response.** D1 and D4 got `extract_invoice`, R1 got `extract_receipt`, N1 got only metadata (no tool fits a newsletter). That's exactly the routing the curriculum expects from `any`, but as a *second* call after `extract_metadata`, not instead of it. The summary line reads `D1->extract_metadata` for all four, so you only see the routing in the `tool_use` lines.
- **The second calls are valid.** Checked by hand against the schemas (the code doesn't): every key is known, every required key is present, `equipment`, `travel` and `card` are in their enums, the numbers are numbers.
- **Optional fields can be dropped even when present.** D1's `extract_invoice` has no `invoice_number`, though the document prints `RS-20417`. Optional means *may be omitted*, and `check_input()` doesn't flag a missing optional key. D4's call also omits `invoice_number` and `invoice_date`, which *is* right: the statement has neither. Omission is valid for both, so absence of a key doesn't tell you which case you're in.

### 5.3 Run 3: `forced` (`extract_metadata`)

```
02:36:04  MODEL OUTPUT  tool_use     extract_metadata {'document_type': 'invoice', 'sender': 'RIDGEWAY SHELVING CO.'}  (id=toolu_01NVGLrtckmYgNgLEiVkPpsu)
02:36:04  MODEL OUTPUT  tool_use     extract_invoice {'vendor_name': 'RIDGEWAY SHELVING CO.', 'total_amount': 1987.2, 'category': 'equipment', 'invoice_date': '2026-09-14', 'tax_amount': 147.2}  (id=toolu_01GfVLECHBQHZBrhqAa1M15a)
02:36:04  forced D1: extract_metadata, first block tool_use, schema problems none
02:36:06  MODEL OUTPUT  tool_use     extract_metadata {'document_type': 'invoice', 'document_type_detail': 'Monthly statement requesting payment for 14 taxi rides between Bend store and airport', 'sender': "Marta's Taxi Service"}  (id=toolu_01BUBQdXCccfCbVvshKNZ4tR)
02:36:06  MODEL OUTPUT  tool_use     extract_invoice {'vendor_name': "Marta's Taxi Service", 'total_amount': 386.5, 'category': 'travel', 'tax_amount': 35.14}  (id=toolu_011UiAHrPKtftjSFitwkeV9R)
02:36:08  MODEL OUTPUT  tool_use     extract_metadata {'document_type': 'receipt', 'document_type_detail': 'Point-of-sale receipt from Trailside Cafe, already paid by Visa ****4417', 'sender': 'TRAILSIDE CAFE'}  (id=toolu_01XFcYMgY3RjXtMQAw2u3NP5)
02:36:08  MODEL OUTPUT  tool_use     extract_receipt {'merchant': 'TRAILSIDE CAFE', 'total_amount': 18.75, 'payment_method': 'card', 'purchase_date': '2026-10-12'}  (id=toolu_0161HVhqYLuUMjcjfEA3RtEt)
02:36:10  MODEL OUTPUT  tool_use     extract_metadata {'document_type': 'other', 'document_type_detail': 'Marketing newsletter from Kestrel Supply promoting an autumn catalogue and a tent discount; no payment requested.', 'sender': 'Kestrel Supply'}  (id=toolu_01XDNWve1JedBEJWrvAvRoYK)
02:36:10  forced 4/4 called a tool ['D1->extract_metadata', 'D4->extract_metadata', 'R1->extract_metadata', 'N1->extract_metadata']; text only: none; schema problems: 0
```

| Variable (code) | Value |
|-----------------|-------|
| `MODES["forced"]` | `{'type': 'tool', 'name': 'extract_metadata'}` |
| First `tool_use` | `extract_metadata` × 4, `content[0].type` `tool_use` × 4 |
| Second `tool_use` | D1, D4 `extract_invoice`; R1 `extract_receipt`; N1 none (same pattern and same values as `any`) |
| `text_only` / `problems` | `none` / `0` |
| Wall time | 02:36:03 → 02:36:10, about 7 s (D1 1 s) |

Lessons from the real data:
- **The forced tool ran every time, first.** D1 (plainly an invoice) and R1 (plainly a receipt) both got `extract_metadata` first. The mandatory step can't be skipped.
- **Forced is not exclusive.** After the forced call, Claude added the better-fitting tool in the same response, as under `any`. "The model has no flexibility in tool selection" holds for the *first* call; it didn't stop a second one. If a step must be the *only* call, the request has to say so too (the Messages API's `disable_parallel_tool_use` option in `tool_choice`; not used in this POC).
- **`forced` and `any` produced the same tool sequence here.** Because `extract_metadata` already presents itself as the mandatory first step, `any` chose it first anyway. The difference is the guarantee: under `any` that order is Claude's choice; under `forced` it's enforced.
- **The fastest run.** D1 took about 1 s under `forced`, 8 s under `any` and 9 s under `auto`.

### 5.4 The three runs side by side

| | `auto` | `any` | `forced` |
|-|--------|-------|----------|
| `tool_choice` | `{'type': 'auto'}` | `{'type': 'any'}` | `{'type': 'tool', 'name': 'extract_metadata'}` |
| Calls | 4 | 4 | 4 |
| Responses with a tool call | 4/4 | 4/4 | 4/4 |
| Text-only responses | 0 | 0 | 0 |
| `tool_use` blocks in total | 4 | 7 | 7 |
| First block | `thinking` × 4 | `tool_use` × 4 | `tool_use` × 4 |
| First tool | `extract_metadata` × 4 | `extract_metadata` × 4 | `extract_metadata` × 4 |
| Type-specific call | none | D1, D4 invoice; R1 receipt | D1, D4 invoice; R1 receipt |
| `stop_reason` | `tool_use` × 4 | `tool_use` × 4 | `tool_use` × 4 |
| `check_input()` problems (first call) | 0 | 0 | 0 |
| `APIError` | no | no | no |
| Wall time (from log) | about 17 s | about 15 s | about 7 s |

The whole run took 39 s (02:35:31 → 02:36:10). The log has no `API error:` line, so the script exited with `0`.

**The corrections the log makes:**
- **`auto` produced no text reply** (the curriculum and the README expect one, typically for N1). The guarantee difference is still real: `auto` *may* answer in text, `any` and `tool` may not.
- **`any` didn't pick one tool per document type.** It always called `extract_metadata` first and then, in the same response, the type-specific tool. The summary lines (`D1->extract_metadata`, ...) report only the first call, so the routing the curriculum expects is visible only in the `tool_use` lines.
- **`forced` didn't stop Claude from calling a second tool.** It made `extract_metadata` the guaranteed first call; `extract_invoice` and `extract_receipt` still followed where they fit.

---

## 6. Agentic AI concepts recap

| Concept | How this POC shows it |
|---------|-----------------------|
| **`tool_choice: auto`** | No guarantee: Claude may call a tool or answer in text. Here it called one tool per document and thought first. |
| **`tool_choice: any`** | A guaranteed tool call; Claude picks which. The call came first, with no text before it, on all 4 documents. |
| **Forced `tool_choice`** | The named tool is guaranteed, as the first call, even for documents another tool fits better. |
| **Parallel tool calls** | Under `any` and `forced`, one response held two `tool_use` blocks: metadata, then the type-specific extraction. |
| **Tool descriptions as prompts** | "the mandatory first step for every inbox document" made `extract_metadata` the first call in every mode. |
| **Strict tool use** | `"strict": True` + `additionalProperties: False`: every input matched its schema. |
| **Verify the guarantee** | `check_input()` checks required keys, unknown keys, types and enums in plain Python. |
| **Escape values** | `other` + `document_type_detail` let the newsletter be filed honestly; `unclear` is available in both enums. |
| **Model capability limits** | `FORCED_MODEL = "claude-haiku-5-5"`: the code comment says Opus/Sonnet 5.5 and Fable 5.1 reject `any`/`tool` with a 400. |
| **No loop, no tool execution** | Every response ends with `stop_reason` `tool_use`; the script reads the requested calls and never sends a `tool_result`. |
| **Observability** | `log_model_io()` logs every block; the per-call check line adds `content[0].type` and the schema problems. |

---

## 7. Common mistakes this POC helps you avoid

1. **Using `auto` when you need structured output.** It allowed a text reply in every call; that none came this time is luck plus a strong description, not a guarantee.
2. **Using a forced tool when the document type is unknown.** `forced` would always call the one tool; `any` lets Claude pick the one that fits.
3. **Assuming `any` or `tool` means exactly one call.** Under both modes, Claude made two calls in one response. If you need exactly one, ask for it explicitly (`disable_parallel_tool_use`) or handle every `tool_use` block.
4. **Reading only `tool_uses[0]`.** The script's own summary hid 6 type-specific extractions. Loop over all `tool_use` blocks.
5. **Assuming a guaranteed call has a valid input.** That's `strict`'s job, and still worth a check like `check_input()`.
6. **Forgetting `additionalProperties: False` with `strict`.** Strict tool use needs it on every object.
7. **Assuming every model supports forced tool use.** The script pins `claude-haiku-5-5` because the code comment says the 5.5 Opus/Sonnet models return a 400 for `any` and `tool`.
8. **Trying to set `tool_choice` in the Agent SDK.** `ClaudeAgentOptions` has no such field; use `output_format` (POC 1) or call the Messages API.
9. **Leaving no tool for "none of these".** Without `extract_metadata` and `other`, `any` would force the newsletter into an invoice or a receipt.
10. **Treating an omitted optional key as "absent in the document".** D1's invoice number was printed but omitted. If a field matters, make it required and nullable, so Claude must state `null` explicitly.
11. **Expecting the tool to run.** A `tool_use` block is a request. Nothing is executed or stored until your code does it.

---

## 8. Claude Architect exam lens

### 8.1 What the exam tests on this topic

The objectives come from `curriculum/04-Prompt-Engineering-Structured-Output/03-raw-Structured-Output-with-Tool-Use.md`. POC 2 covers objectives 2–4; POC 1 covers 1 and 5 (schema design), and its `INVOICE_SCHEMA` is `extract_invoice`'s input schema here.

| Exam objective | What a correct answer looks like | Where this POC shows it |
|----------------|----------------------------------|-------------------------|
| 1. Extraction tool schema: 3 required, 3 nullable, `unclear`/`other`, a detail field | Optional fields nullable, `required` limited to always-present fields, escape values in the enum. | `extract_invoice` uses POC 1's `INVOICE_SCHEMA`; `METADATA_SCHEMA` and `RECEIPT_SCHEMA` follow the same rules |
| 2. `tool_choice: auto` can return text instead of a tool call | `auto` gives no guaranteed structured output, so it's unsuitable when every document needs a record. | Run `auto`: the `text_only` branch in `main()`. Real run: 0 text replies, which shows the guarantee is about what's *allowed*, not what happens on one run |
| 3. `tool_choice: any` always returns a tool call | Every response has `stop_reason` `tool_use`, a schema-valid tool call, no text-only responses. Right when the document type is unknown: Claude picks the tool. | Run `any`: 4/4, `first block tool_use`, `schema problems: 0`; the type-specific second calls |
| 4. Force `{type: tool, name: extract_metadata}` | The named tool always runs, even when another fits better: a mandatory first step before enrichment. | Run `forced`: `extract_metadata` first on all 4, including D1 and R1 |
| 5. 5 documents, 2 with missing fields → `null`, not invented values | Nullable fields come back `null`; no invented dates, amounts or identifiers. | POC 1. Here: D4's `extract_invoice` omits number and date instead of inventing them |

> **Exam tip:** exam questions on `tool_choice` are about the Messages API. The Agent SDK has no `tool_choice`; its tool calls are effectively `auto`, and its guarantee of structured output is `output_format` (POC 1). If a question asks how to guarantee structured output "when the document type is unknown", the answer is `any`; "a step that must always run first" is a forced tool; "a chat that may or may not need a tool" is `auto`.

### 8.2 The same guarantees with the Agent SDK

The objectives describe the Messages API, which is what this POC uses. In the Agent SDK you can't set `tool_choice`, so each guarantee is built differently: `output_format` guarantees structured output, and your own code makes a step mandatory by running it first.

```python
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

# INBOX_SYSTEM, DOCUMENTS, METADATA_SCHEMA, INVOICE_SCHEMA and RECEIPT_SCHEMA are as in the POC.


async def structured(settings, text: str, schema: dict) -> dict | None:
    """One query() whose only way to finish is the StructuredOutput tool: guaranteed JSON, like any/tool."""
    options = ClaudeAgentOptions(
        model=settings.model_id, system_prompt=INBOX_SYSTEM, tools=[], setting_sources=[],
        output_format={"type": "json_schema", "schema": schema}, max_turns=settings.max_turns,
    )
    async for message in query(prompt=text, options=options):  # raises ResultError after an error result
        if isinstance(message, ResultMessage) and message.subtype == "success":
            return message.structured_output
    return None


async def process(settings, doc_id: str) -> tuple[dict | None, dict | None]:
    text = f"New document in the accounts inbox:\n\n{DOCUMENTS[doc_id]}"
    meta = await structured(settings, text, METADATA_SCHEMA)  # the mandatory first step: your code runs it
    schema = {"invoice": INVOICE_SCHEMA, "receipt": RECEIPT_SCHEMA}.get(meta["document_type"]) if meta else None
    return meta, (await structured(settings, text, schema) if schema else None)  # then the type-specific step
```

| Messages API (`poc2_tool_choice.py`) | Agent SDK equivalent |
|--------------------------------------|----------------------|
| `tool_choice={"type": "auto"}` | The SDK default: every tool call is Claude's choice |
| `tool_choice={"type": "any"}` + 3 tools | One `output_format` call per schema; or one schema that covers all types |
| `tool_choice={"type": "tool", "name": "extract_metadata"}` | Your code runs the metadata `query()` first, then the type-specific one |
| `"strict": True` on each tool | `output_format`: the SDK validates and re-prompts; `error_max_structured_output_retries` if it never fits |
| `block.input` of each `tool_use` block | `ResultMessage.structured_output` |
| Two `tool_use` blocks may come back in one response | One structured result per `query()`; the order is your code's |
| Model must accept `any`/`tool` (`claude-haiku-5-5`) | Any model; no `tool_choice` to reject |
| `stop_reason == "tool_use"`, no loop | Final `stop_reason == "tool_use"`, `subtype == "success"` |

Two things the comparison makes obvious:
- **A forced tool is a sequencing tool.** In the SDK you get the same "this step always runs first" by writing the sequence in code, which also guarantees it's the *only* thing that runs in that step.
- **Guaranteed structure has two layers:** a call must happen (`any`/`tool`, or `output_format`), and its input must fit (`strict`, or SDK validation). The exam tests both.

### 8.3 Scenario questions

Try each one before reading the answer. These questions were written for this article to match the curriculum objectives above. They are not official exam questions.

---

**Scenario 1: The missing records**

An inbox pipeline sends each document with three extraction tools and `tool_choice` left at the default `auto`. About 1 in 30 documents produces no database row; the logs show a friendly text summary instead of a tool call. What is the fix?

- A. Add "always call a tool" to the system prompt.
- B. Set `tool_choice` to `{"type": "any"}`, so every response must call one of the tools while Claude still picks which.
- C. Force `extract_invoice` for every document.
- D. Retry the document until a tool is called.

**Answer: B.** `auto` lets Claude answer conversationally, so it can't guarantee structured output. `any` guarantees a tool call and keeps the choice of tool, which is right when the type is unknown. A reduces the rate but guarantees nothing. C files receipts and newsletters as invoices. D wastes calls and still guarantees nothing. *POC link:* `MODES` and the `text_only` branch in `main()`. In the real run `auto` happened to call a tool 4/4 times; nothing in the request required it.

---

**Scenario 2: Unknown document types**

Documents arrive as invoices, receipts or anything else. Every document must produce a structured record, and the right extraction depends on the type. Which `tool_choice` fits?

- A. `auto`
- B. `any`, with one tool per type plus a metadata tool whose type enum includes `other`
- C. `{"type": "tool", "name": "extract_invoice"}`
- D. No tools; parse the text answer.

**Answer: B.** `any` guarantees a call and lets Claude route by type; the metadata tool with `other` gives a valid record for documents no type-specific tool fits. *POC link:* the `any` run: D1 and D4 got `extract_invoice`, R1 `extract_receipt`, N1 only `extract_metadata` with `document_type: 'other'`.

---

**Scenario 3: The mandatory first step**

Compliance requires that every incoming document's type and sender are recorded before any enrichment step runs. How do you guarantee it?

- A. Describe the metadata tool as "mandatory" and use `auto`.
- B. Force it: `tool_choice={"type": "tool", "name": "extract_metadata"}`.
- C. Use `any` and hope Claude picks it.
- D. Put the metadata fields into every type-specific tool.

**Answer: B.** Forced selection makes the step run regardless of Claude's judgement. A and C rely on Claude's choice; they worked in this run, but they aren't guarantees. D spreads the step across tools and still doesn't force one. *POC link:* the `forced` run: `extract_metadata` was the first call on all 4 documents, including D1 (plainly an invoice) and R1 (plainly a receipt).

---

**Scenario 4: Forced, but not alone**

A team forces `extract_metadata` and is surprised to see `extract_invoice` in the same response, after it. Their enrichment code assumed exactly one call. What explains it, and what should they do?

- A. A bug: forced `tool_choice` should prevent other tools.
- B. Forcing guarantees the named tool is called, not that it's the only call; Claude may add parallel calls. Process every `tool_use` block, or ask for a single call with `disable_parallel_tool_use`.
- C. Remove the other tools from the request permanently.
- D. Switch to `auto`.

**Answer: B.** A forced choice fixes the first call, not the number of calls. Code that reads only the first block silently drops the rest. C works only if the other tools are never needed in that step. D removes the guarantee. *POC link:* the real `forced` run: D1, D4 and R1 each got a second call (`extract_invoice` or `extract_receipt`); `main()` reads only `tool_uses[0]`, so its summary shows none of them.

---

**Scenario 5: Guaranteed call, broken input**

With `tool_choice: any`, a tool call always comes back, but now and then `category` holds a value outside its enum, or a required key is missing. What fixes this?

- A. Switch to `auto`.
- B. Set `"strict": true` on the tool (with `additionalProperties: false` on every object) so the input is constrained to the schema, and keep a schema check in code.
- C. Add more examples to the description.
- D. Lower `max_tokens`.

**Answer: B.** `any` guarantees *a call*; `strict` makes its input schema-valid. A check like `check_input()` verifies it. *POC link:* `"strict": True` on every tool in `TOOLS`, `additionalProperties: False` in every schema, and `schema problems: 0` in all three summary lines.

---

**Scenario 6: A 400 on forced tool use**

A team moves an extraction pipeline that forces a tool to a newer, larger model, and every request now fails with HTTP 400. Nothing else changed. What is the most likely cause?

- A. The tool schema is too large.
- B. The new model doesn't accept `tool_choice` `any`/`tool`; keep a model that does for that step, or use structured output without forcing (e.g. the Agent SDK's `output_format`).
- C. The API key lacks permissions.
- D. `strict` is not allowed with forced tools.

**Answer: B.** Forced tool use isn't supported on every model. *POC link:* `FORCED_MODEL = "claude-haiku-5-5"  # accepts any/tool; Opus 5.5, Sonnet 5.5 and Fable 5.1 answer them with a 400`, and the `except anthropic.APIError` branch in `main()` that logs it per document.

---

**Scenario 7: `tool_choice` in the Agent SDK**

A developer looks for `tool_choice` in `ClaudeAgentOptions` to force structured output from an agent. They can't find it. What should they use?

- A. `allowed_tools=["StructuredOutput"]`.
- B. `output_format={"type": "json_schema", "schema": ...}`: Claude must hand in its answer through the `StructuredOutput` tool, and the SDK validates it.
- C. `permission_mode="bypassPermissions"`.
- D. A hook that blocks text replies.

**Answer: B.** The Agent SDK has no `tool_choice`; every tool call is effectively `auto`. Its guarantee of structured output is `output_format`, and a mandatory step is a separate `query()` your code runs first. *POC link:* the docstring of `poc2_tool_choice.py` ("The Agent SDK has no tool_choice"); POC 1's `build_extract_options()`.

---

**Scenario 8: A newsletter under `any`**

Under `tool_choice: any`, the only tools are `extract_invoice` and `extract_receipt`. A marketing newsletter arrives. What happens, and what's the better design?

- A. Claude replies in text; nothing to fix.
- B. Claude must call one of the two tools, so the newsletter is recorded as an invoice or receipt with made-up fields. Add a tool (or an enum value) that can say "other".
- C. The API returns an error.
- D. Claude calls no tool and `stop_reason` is `end_turn`.

**Answer: B.** `any` forbids a text-only answer, so with no fitting tool, Claude has to misuse one. Give it an honest option. *POC link:* `extract_metadata` with `document_type` enum `["invoice", "receipt", "unclear", "other"]`; under `any` and `forced`, N1 got only `extract_metadata` with `'other'` and the detail "Marketing newsletter ... No payment request."

---

**Scenario 9: Reading the response**

After a call with `tool_choice: any`, the response's `stop_reason` is `tool_use` and `content` holds two `tool_use` blocks. The pipeline stores `content[0].input` only. What's the risk?

- A. None; the first block is always the important one.
- B. The second extraction is lost. Iterate over all `tool_use` blocks and handle each by name.
- C. `stop_reason` should be `end_turn`; the call failed.
- D. The second block is a duplicate.

**Answer: B.** A response can carry several tool calls. *POC link:* in the `any` run, `content[0]` was `extract_metadata` and `content[1]` the real extraction (`extract_invoice` with vendor, total, category, date and tax); `main()`'s `tool_uses[0]` reported only the first.

---

**Scenario 10: An optional field left out**

An `extract_invoice` call returns no `invoice_number` key for an invoice that prints one, and passes schema validation. How do you make the extractor commit to an answer for that field?

- A. Make `invoice_number` required with type `["string", "null"]`: Claude must state it, as a value or as `null`.
- B. Make it required and non-nullable.
- C. Remove it from the schema.
- D. Lower `max_tokens`.

**Answer: A.** Optional keys may be omitted, so "omitted" can mean "absent" or "skipped". Required + nullable forces an explicit answer while keeping `null` honest. B brings back the fabrication pressure from POC 1. *POC link:* the real `any` and `forced` runs: D1's `extract_invoice` omitted `invoice_number` (`RS-20417` is printed), and `check_input()` reported no problem because the key is optional.

---

### 8.4 Quick-recall cheat sheet

```
auto                  → Claude MAY call a tool or reply in text: no guaranteed structured output
any                   → Claude MUST call a tool, picks which: document type unknown
{type: tool, name}    → Claude MUST call that tool: mandatory first step (metadata before enrichment)
forced ≠ only         → other tool calls may follow in the same response (disable_parallel_tool_use)
read every block      → a response can hold several tool_use blocks; don't stop at content[0]
strict: true          → guaranteed call ALSO schema-valid; needs additionalProperties: false
honest options        → an "other"/"unclear" path so any/forced never forces a wrong record
model support         → claude-haiku-5-5 accepts any/tool; the POC notes Opus/Sonnet 5.5, Fable 5.1 return 400
Agent SDK             → no tool_choice (calls are auto); guarantee = output_format; sequence in code
stop_reason tool_use  → a request, not an execution: your code runs the tool and sends tool_result
optional vs required  → optional keys may vanish; required + nullable forces value-or-null
```

---

## 9. How to run it

```bash
cd 04-Prompt-Engineering-Structured-Output/03-Structured-Output-with-Tool-Use
source .venv/bin/activate        # the folder's venv (anthropic 2.8.0, claude-agent-sdk 0.2.181)
python poc2_tool_choice.py       # paid: 3 modes × 4 documents = 12 Messages API calls on claude-haiku-5-5
python poc1_schema_design.py     # paid: POC 1, naive vs nullable schema through the Agent SDK
```

- Without the venv: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`, then `cp .env.example .env` and add your key.
- Both scripts call the API. This folder has no free offline demo.
- `.env` needs only `ANTHROPIC_API_KEY` for this script. `MODEL_ID`, `MAX_TURNS` and `MAX_BUDGET_USD` are read by `load_settings()` but not used: the model is fixed in `FORCED_MODEL`, and there is no agent loop to cap.
- Every model input and output, the per-call checks and the summaries are printed to the console and written to `logs/poc2_tool_choice_<date>_<time>.log`. Expect `auto` to vary between runs (a text reply on N1 is possible), and the number of `tool_use` blocks per response to vary too.
- The exit code is `0` when all modes finish; an `anthropic.APIError` on one call is logged and skipped, not fatal. It's `1` only on a setup failure (`OSError`, `RuntimeError`).
