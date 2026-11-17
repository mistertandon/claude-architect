# POC 1: A Schema That Lets Claude Say "Not There"

> **File:** `poc1_schema_design.py` (with `extraction_setup.py` and `common.py`)
> **Domain:** 04 Prompt Engineering & Structured Output → 03 Structured Output with Tool Use
> **SDK:** Claude Agent SDK for Python (`claude-agent-sdk >=0.2.174,<0.3`; 0.2.181 in the folder's `.venv`)
> **Page:** https://claude.ai/artifact/Nojs4b6sPoeN1gHHaqrMgZ

---

## 1. What this POC proves

This POC extracts the same 5 invoices twice through the Agent SDK's structured output. Only the JSON schema changes between the two runs: a naive one (every field required, no `null`, a closed category list) and an honest one (3 required fields, 3 nullable ones, a category enum with `unclear` and `other`, and a detail field). A scorer checks each field against known values. Every claim below is checked against one real run: `logs/poc1_schema_design_20261114_023403.log`.

| # | Idea | Where it shows up in the code |
|---|------|------------------------------|
| 1 | **Structured output is a tool call.** With `output_format`, Claude hands in its JSON by calling the built-in `StructuredOutput` tool; the SDK validates it against your schema and puts it in `ResultMessage.structured_output`. | `build_extract_options()`, `extract()` in `extraction_setup.py` |
| 2 | **Required fields pressure the model to invent.** When a document is silent, a required non-nullable field leaves Claude no honest answer: it must write *something*. | `NAIVE_SCHEMA`; the `naive` run |
| 3 | **Nullable optional fields allow an honest `null`.** `required` lists only the fields every invoice has; the others are `["string", "null"]`. | `INVOICE_SCHEMA`; the `nullable` run |
| 4 | **`unclear` and `other` stop a closed list from forcing a wrong category.** `other` comes with a `category_detail` string that says what it was. | `category` and `category_detail` in `INVOICE_SCHEMA` |
| 5 | **Schema design is the root-cause fix for fabrication.** Same documents, prompt, model and options; only the schema changed, and invented values went from 4 of 4 to 0 of 4. | `RUNS` in `poc1_schema_design.py`; the two `totals` lines |
| 6 | **Field descriptions are instructions.** The honest schema describes each field ("as written", "or null if the document has none"); the naive one has no descriptions. | `"description"` keys in `INVOICE_SCHEMA` |

The pattern in one line:

```
document ──query(output_format = schema)──▶ Claude ──StructuredOutput{json}──▶ SDK validates against schema ──▶ ResultMessage.structured_output ──▶ score()
```

---

## 2. The files involved

```
03-Structured-Output-with-Tool-Use/
├── .env                      ← ANTHROPIC_API_KEY, MODEL_ID, MAX_TURNS, MAX_BUDGET_USD
├── .env.example              ← the same keys, with placeholder values
├── requirements.txt          ← claude-agent-sdk >=0.2.174,<0.3, python-dotenv, anthropic (POC 2 only)
├── common.py                 ← Settings, load_settings(), setup_logging(), log_model_io()
├── extraction_setup.py       ← documents + TRUTH + ABSENT, INVOICE_SCHEMA, NAIVE_SCHEMA, EXTRACT_PROMPT,
│                               build_extract_options(), extract(), score()
├── poc1_schema_design.py     ← entry point: 2 runs × 5 invoices = 10 query() calls
├── poc2_tool_choice.py       ← POC 2: auto, any and a forced tool on the Messages API (not covered here)
├── README.md
└── logs/
    └── poc1_schema_design_20261114_023403.log   ← the real run used in sections 3.2 and 5
```

Every snippet in this article is copied from these files, logging statements included. Each logging statement is named with the log line tag it writes, so you can find its output in the log file.

`poc1_schema_design.py` is 62 lines because everything it compares lives in `extraction_setup.py`:
- `common.py` covers **configuration and observability**: which model, the turn and budget caps, and one log line per model input or output.
- `extraction_setup.py` covers **the test material and the one call**: the documents and their known values, the two schemas, the options, `extract()` and the scorer. POC 2 imports the same documents and `INVOICE_SCHEMA`.
- `poc1_schema_design.py` covers **the experiment**: run each schema over the 5 invoices, score, and total.

---

## 3. End-to-end execution flow

### 3.1 The big picture

```
python poc1_schema_design.py
        │
        ▼
asyncio.run(main())                                                     [poc1_schema_design.py]
        │
        ├─▶ load_settings()                                             [common.py]
        │      └─ .env → Settings(model_id, max_turns, max_budget_usd), frozen
        ├─▶ setup_logging("poc1_schema_design")                         [common.py]
        │      └─ console + logs/poc1_schema_design_<date>_<time>.log, lines "HH:MM:SS  message"
        │
        ├─▶ for label, schema in RUNS:              naive → nullable
        │      ├─ for doc_id in INVOICES:           D1, D2, D3, D4, D5
        │      │     ├─ data, subtype = extract(settings, doc_id, schema)   [extraction_setup.py] → one query()
        │      │     ├─ data is None → log.error("... no structured output (subtype)"); continue
        │      │     ├─ verdicts = score(doc_id, data, schema)              [extraction_setup.py]
        │      │     ├─ invented += ...; wrong_category += ...
        │      │     └─ log.info("%-8s %s: %s", ...)                         → log: "<schema> <doc>: field=verdict ..."
        │      └─ log.info("%-8s totals: ...")                              → log: "<schema> totals: ..."
        │
        └─▶ log.info("Same documents, prompt, model and options: only the schema changed")
```

All 10 extractions go through the same function. This is what happens inside it; the right-hand column names the log line each step writes.

```
extract(settings, doc_id, schema)                                                     [extraction_setup.py]
   │
   ├─ prompt = "Extract this invoice.\n\n<document>\n...\n</document>"
   ├─ log.info("MODEL INPUT   prompt ...")                                         → log: prompt
   │
   └─▶ async for message in query(prompt=prompt, options=build_extract_options(settings, schema)):
          │
          │   ┌──────────────── SDK-owned: one NEW session per call ──────────────────────┐
          │   │ starts the bundled Claude Code with system_prompt = EXTRACT_PROMPT         │
          │   │ and a StructuredOutput tool whose input schema is `schema`                 │
          │   │ Claude reads the document (may think: adaptive thinking, summarized)       │  → log: thinking
          │   │ Claude calls StructuredOutput with its JSON                                │  → log: structured
          │   │ the SDK validates the JSON against `schema`                                │
          │   │   valid   → tool_result "Structured output provided successfully"          │  → log: tool_result
          │   │   invalid → Claude is re-prompted (up to max_turns), then                  │
          │   │             error_max_structured_output_retries                            │
          │   │ yields ResultMessage(subtype, structured_output)                           │  → log: stop_reason
          │   └───────────────────────────────────────────────────────────────────────────┘
          │
          ├─ log_model_io(message)   writes the log lines marked above
          ├─ ResultMessage → subtype = message.subtype; if "success": data = message.structured_output
          └─ ResultError   → log.error("The extraction failed: %s")                    → log: (none in this run)
   return (data, subtype)
```

### 3.2 Messages your `async for` receives (the `naive` run on D5, real output)

The values below come from the real run on 2026-11-14, recorded in `logs/poc1_schema_design_20261114_023403.log`. The log holds model input, model output and the POC's own score lines. Each log line comes from one statement in the code:

| Log line tag | Message class yielded by `query()` | Field logged | Written by |
|--------------|------------------------------------|--------------|------------|
| `MODEL INPUT   prompt` | *(none: it's the `prompt` built in `extract()`)* | `prompt` | `log.info("MODEL INPUT   prompt ...")` in `extract()` (`extraction_setup.py`) |
| `MODEL OUTPUT  thinking` | `AssistantMessage` → `ThinkingBlock` | `block.thinking`, only when non-empty | `log_model_io()` (`common.py`) |
| `MODEL OUTPUT  text` | `AssistantMessage` → `TextBlock` | `block.text` | `log_model_io()`. None in this log |
| `MODEL OUTPUT  structured` | `AssistantMessage` → `ToolUseBlock` named `StructuredOutput` | `block.input`, `block.id` | `log_model_io()` |
| `MODEL OUTPUT  tool_use` | `AssistantMessage` → any other `ToolUseBlock` | `block.name`, `block.input`, `block.id` | `log_model_io()`. None in this log (`tools=[]`) |
| `MODEL INPUT   tool_result` | `UserMessage` → `ToolResultBlock` | `block.content`, `block.tool_use_id`, `block.is_error` | `log_model_io()` |
| `MODEL OUTPUT  stop_reason` | `ResultMessage` | `message.stop_reason`, `message.subtype` | `log_model_io()` |
| `<schema> <doc>: field=verdict ...` | *(none: the scorer)* | `verdicts` | `log.info("%-8s %s: %s", ...)` in `main()` (`poc1_schema_design.py`) |
| `<schema> totals: ...`, `Same documents, ...` | *(none: Python counters)* | `invented`, `wrong_category` | `log.info(...)` in `main()` |
| `... no structured output (...)`, `The extraction failed: ...`, `SDK error: ...` | *(none)* | the failure | `main()`, `extract()`. None in this log |
| `HH:MM:SS` at the start of each line | *(none)* | the time the line was logged | the formatter in `setup_logging()` |

D5 is the hardest document: no invoice number, no tax, and "For: as agreed" says nothing about what was bought. With the naive schema, it streamed like this inside the one `async for` loop:

```
02:34:23  (input)                                                             log: prompt
            prompt = Extract this invoice.\n\n<document>\nKESTREL RIDGE HOLDINGS\nDate: 2026-10-05\n
                     For: as agreed\nAmount due: $2,400.00\nPayment within 30 days.\n</document>

02:34:32  AssistantMessage › ThinkingBlock                                    log: thinking
            thinking = I'm checking the document for the invoice number, tax amount, and category, and
                       none of them are actually stated. I'm leaning toward leaving the invoice number
                       empty and not inventing a tax figure, but the category field has to hold one of
                       the listed values, so I'm weighing which option fits best.

                       I'm going with 0 for the tax and flagging that it wasn't stated in the document.
                       The category has to be one of the listed values, so I'll pick the closest fit
                       and note that it's a guess.

02:34:32  AssistantMessage › ToolUseBlock                                     log: structured
            name  = "StructuredOutput"                                        ← not logged: implied by the tag
            input = {'vendor_name': 'Kestrel Ridge Holdings', 'total_amount': 2400,
                     'category': 'equipment',                                 ← a guess the schema forced
                     'invoice_number': '',                                    ← a placeholder, not null
                     'invoice_date': '2026-10-05',
                     'tax_amount': 0}                                         ← "no tax shown" became 0
            id    = "toolu_01XHn2q4LvoEN4EudKQ4KCM2"

02:34:32  UserMessage › ToolResultBlock                                       log: tool_result
            content     = Structured output provided successfully             ← a plain string, not a list
            tool_use_id = "toolu_01XHn2q4LvoEN4EudKQ4KCM2"                    ← same id as the request
            is_error    = None

02:34:32  ResultMessage                                                       log: stop_reason
            stop_reason = "tool_use", subtype = "success"

02:34:33  (scorer)  naive    D5: vendor_name=correct total_amount=correct category=wrong('equipment')
                    invoice_number=invented('') invoice_date=correct tax_amount=invented(0)
```

The same document with the honest schema, 22 seconds later:

```
02:34:54  AssistantMessage › ToolUseBlock                                     log: structured
            input = {'vendor_name': 'KESTREL RIDGE HOLDINGS', 'total_amount': 2400, 'category': 'unclear',
                     'invoice_date': '2026-10-05', 'invoice_number': None, 'tax_amount': None,
                     'category_detail': None}
            id    = "toolu_01WrEYLZjcVKCYCo7gVqjvUo"
02:34:55  UserMessage › ToolResultBlock   (tool_use_id = toolu_01WrEYLZjcVKCYCo7gVqjvUo, is_error = None)
02:34:55  ResultMessage                   stop_reason = "tool_use", subtype = "success"
02:34:56  (scorer)  nullable D5: ... category=correct invoice_number=null invoice_date=correct tax_amount=null ...
```

What to notice in the real data:
- **The thinking named the problem, and the schema won anyway.** Claude saw that none of the three values was stated and leaned toward "not inventing a tax figure". The schema requires a number, so it wrote `0`. It planned to "flag" the guesses, but with `output_format` the answer is the `StructuredOutput` call: no `text` line follows, and the flag never reached the output.
- **"Invented" here means placeholders.** The naive run never made up a plausible invoice number or date. It wrote `''` and `0`. Those still look like data downstream: an empty string passes a "required string" check, and `0` is a valid tax amount. `score()` counts any non-null value for an absent field as `invented`.
- **No validator rejection in the log.** Each call has exactly one `structured` line and one `Structured output provided successfully` result, so the SDK accepted the first JSON every time. Claude didn't try `null` and get refused; it chose a schema-valid value up front, as its D4 thinking says ("empty strings rather than null, since the required fields have to be strings").
- **`success` with `stop_reason = "tool_use"`, 10 times out of 10.** The run ends right after the `StructuredOutput` call is accepted. `extract()` checks `subtype`, not `stop_reason`.
- **`tool_use_id` pairing.** Each `structured` line's `id` comes back as the next `tool_result` line's `tool_use_id`.
- **With the honest schema, no thinking lines at all.** The naive run thought on D3, D4 and D5, the three documents where the schema forced a hard choice. The nullable run has no `thinking` line on any document. The log can't tell whether no `ThinkingBlock` arrived or its text was empty.
- **Not shown:** `SystemMessage`s and other events also arrive in the stream (see the "No `break`" comment in `extract()`), but `log_model_io()` has no branch for them. Cost, session ids and turn counts are on the `ResultMessage` too, but the log records only `stop_reason` and `subtype`. The model name isn't logged.

> The `UserMessage` items are **not** typed by a human. Here they carry only the SDK's acknowledgement of the `StructuredOutput` call.

---

## 4. Code walkthrough

The snippets follow the order in which the code runs: the script first, then the module functions it calls. Each one ends with the log lines it writes, copied from the real log (long values trimmed with `...`).

### 4.1 Module docstring: the claim under test

```python
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
```

**Why it matters:** the docstring states the mechanism and the test data before any code.
- **`output_format` is tool use.** The SDK's structured output isn't free text parsed afterwards: Claude calls a tool whose input schema *is* your schema.
- **Two schemas, one variable.** Everything else is held constant, so a difference in the output comes from the schema.
- **4 absent fields:** D4's number and date, D5's number and tax. Plus D5's category, which the document doesn't give.
- **"the validator rejects every honest 'nothing here'"** is true of the schema: `null` isn't a valid value for a `string` field. In the real run the validator never had to reject anything, because Claude never sent `null` (section 5.1).

---

### 4.2 Imports

```python
import asyncio
import sys

from claude_agent_sdk import ClaudeSDKError

from common import load_settings, log, setup_logging
from extraction_setup import ABSENT, INVOICE_SCHEMA, INVOICES, NAIVE_SCHEMA, TRUTH, extract, score
```

| Import | What it brings in | Why this file needs it |
| --- | --- | --- |
| `asyncio` | The event loop | `query()` is an async generator, so every extraction is awaited |
| `sys` | `sys.exit()` | Passes `0` or `1` from `main()` to the shell |
| `ClaudeSDKError` | The SDK's base error | Catches SDK runtime failures (Claude Code not found, its process crashed) |
| `load_settings`, `log`, `setup_logging` | From `common` | `.env` → `Settings`; the `poc` logger and its handlers |
| `INVOICE_SCHEMA`, `NAIVE_SCHEMA` | From `extraction_setup` | The two schemas under test |
| `INVOICES` | From `extraction_setup` | D1–D5 (POC 2 also uses a receipt and a newsletter, not used here) |
| `TRUTH`, `ABSENT` | From `extraction_setup` | Known values; which fields each document lacks |
| `extract`, `score` | From `extraction_setup` | One `query()` per document; the field-by-field scorer |

The script never imports `query` or `ClaudeAgentOptions`: `extract()` owns the SDK call, so both runs are guaranteed to use the same options.

---

### 4.3 The run table

```python
RUNS = [
    ("naive", NAIVE_SCHEMA),  # required fields pressure Claude to invent (C3)
    ("nullable", INVOICE_SCHEMA),  # null is an allowed, honest answer (C4, C5)
]
```

**Why it matters:** each entry is `(label, schema)`. The label prefixes every score line (`naive    D4: ...`, `nullable D4: ...`), so the two runs can be read side by side. The order is deliberate: see the failure first, then the fix.

---

### 4.4 `main()`: two schemas, five invoices, two counters

#### a) Setup

```python
async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc1_schema_design")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1
```

Setup failures use `print()`, because the logger may not exist yet (a missing `.env` fails before `setup_logging()`).

#### b) The extraction loop

```python
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
```

**Why it matters:**
- **Two failure boundaries.** A `ClaudeSDKError` (the runtime failed) stops the script with `1`. A `None` result (the validator never accepted a value, e.g. `error_max_structured_output_retries`) is logged with its `subtype` and skipped. The second is the failure the naive schema *could* cause; the real run has neither.
- **Two counters per schema.** `invented` counts absent fields that got a value; `wrong_category` counts categories that differ from `TRUTH` (`True` adds 1).
- **One score line per document** (`%-8s` pads the label to 8 characters).

Log lines it wrote:

```
02:34:23  naive    D4: vendor_name=correct total_amount=correct category=correct invoice_number=invented('') invoice_date=invented('') tax_amount=correct
02:34:51  nullable D4: vendor_name=correct total_amount=correct category=correct invoice_number=null invoice_date=null tax_amount=correct category_detail=correct
```

#### c) The totals and the conclusion

```python
        log.info("%-8s totals: %d of %d absent fields invented, %d of %d categories wrong", label, invented,
                 sum(len(fields) for fields in ABSENT.values()), wrong_category, len(INVOICES))
    log.info("Same documents, prompt, model and options: only the schema changed")  # schema design is the fix (C2)
    return 0
```

**Why it matters:** the totals turn ten score lines into two numbers per schema. The last line is fixed text, not a check; it's true by construction, because `build_extract_options()` takes only the schema as a variable (4.9).

Log lines it wrote:

```
02:34:33  naive    totals: 4 of 4 absent fields invented, 2 of 5 categories wrong
02:34:56  nullable totals: 0 of 4 absent fields invented, 0 of 5 categories wrong
02:34:56  Same documents, prompt, model and options: only the schema changed
```

---

### 4.5 `__main__`

```python
if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

`asyncio.run()` runs the async `main()`; `sys.exit()` passes its `0` or `1` to the shell.

---

### 4.6 `Settings` and `load_settings()` (from `common.py`)

```python
@dataclass(frozen=True)
class Settings:
    model_id: str  # MODEL_ID: the Claude model of POC 1's extractions (POC 2 uses FORCED_MODEL)
    max_turns: int  # MAX_TURNS: safety cap on turns per extraction call
    max_budget_usd: float  # MAX_BUDGET_USD: cost guard for a single run


def load_settings() -> Settings:
    """Read .env. The SDK's Claude Code process takes ANTHROPIC_API_KEY from the environment."""
    env_file = POC_DIR / ".env"
    if not env_file.is_file():
        raise RuntimeError(f"{env_file} not found: copy .env.example to .env and add your API key")
    load_dotenv(env_file, override=True)  # .env wins over variables already set in your shell
    if os.getenv("ANTHROPIC_API_KEY", "") in ("", "your-api-key-here"):
        raise RuntimeError(f"set ANTHROPIC_API_KEY in {env_file}")
    try:
        return Settings(
            model_id=os.getenv("MODEL_ID") or "claude-sonnet-5-5",
            max_turns=int(os.getenv("MAX_TURNS") or 10),
            max_budget_usd=float(os.getenv("MAX_BUDGET_USD") or 0.50),
        )
    except ValueError as exc:
        raise RuntimeError(f"MAX_TURNS and MAX_BUDGET_USD in .env must be numbers ({exc})") from exc
```

**Why it matters:**
- **One model for both schemas.** `frozen=True` means no code can change a setting mid-run.
- **`max_turns` defaults to 10 here, not 5.** A schema mismatch makes the SDK re-prompt Claude, and each retry is a turn; the extra room lets a retry happen before the cap. In the real run no call needed one.
- **The key never appears in code.** The SDK's Claude Code process reads `ANTHROPIC_API_KEY` from the environment that `load_dotenv()` filled.

---

### 4.7 `setup_logging()` and `log_model_io()` (from `common.py`)

```python
def setup_logging(script_name: str) -> None:
    """Log to the console and to logs/<script>_<time>.log, so a paid run can be re-read later."""
    log_dir = POC_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"{script_name}_{datetime.now():%Y%m%d_%H%M%S}.log"
    formatter = logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(log_file, encoding="utf-8")):
        handler.setFormatter(formatter)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def log_model_io(message: Any) -> None:
    """Log the model input or output carried by one message from the query() stream, or by one Messages API
    response."""
    if isinstance(message, AssistantMessage):  # Claude's response = model OUTPUT
        for block in message.content:
            if isinstance(block, ThinkingBlock) and block.thinking:
                log.info("MODEL OUTPUT  thinking     %s", block.thinking)
            elif isinstance(block, TextBlock):
                log.info("MODEL OUTPUT  text         %s", block.text)
            elif isinstance(block, ToolUseBlock) and block.name == "StructuredOutput":
                # output_format at work: Claude hands in its JSON through this built-in tool
                log.info("MODEL OUTPUT  structured   %s  (id=%s)", block.input, block.id)
            elif isinstance(block, ToolUseBlock):
                log.info("MODEL OUTPUT  tool_use     %s %s  (id=%s)", block.name, block.input, block.id)

    elif isinstance(message, UserMessage) and isinstance(message.content, list):  # tool results = model INPUT
        for block in message.content:
            if isinstance(block, ToolResultBlock):
                log.info(
                    "MODEL INPUT   tool_result  %s  (tool_use_id=%s, is_error=%s)",
                    block.content, block.tool_use_id, block.is_error,
                )

    elif isinstance(message, ResultMessage):  # the loop has ended
        log.info("MODEL OUTPUT  stop_reason  %s  (loop result: %s)", message.stop_reason, message.subtype)

    elif getattr(message, "type", None) == "message":  # a Messages API response (POC 2): no SDK loop around it
        ...
```

**Why it matters:**
- **The file name** `poc1_schema_design_20261114_023403.log` comes from `datetime.now()` at setup: the run started at 02:34:03, the time of the first log line.
- **`structured` is a `ToolUseBlock` named `StructuredOutput`.** Its `input` is the JSON Claude proposes. If the SDK rejected it, you'd see a second `structured` line for the same document; the real log has exactly one per document.
- **`thinking` only when non-empty**, so a missing `thinking` line doesn't prove no block arrived.
- **The last branch** handles POC 2's raw Messages API responses with the same tags; POC 1 never reaches it.

Log lines it wrote for one call (naive, D1):

```
02:34:07  MODEL OUTPUT  structured   {'vendor_name': 'Ridgeway Shelving Co.', 'total_amount': 1987.2, 'category': 'equipment', 'invoice_number': 'RS-20417', 'invoice_date': '2026-09-14', 'tax_amount': 147.2}  (id=toolu_018d3sKGV6DmF8Vxct7EXkVR)
02:34:07  MODEL INPUT   tool_result  Structured output provided successfully  (tool_use_id=toolu_018d3sKGV6DmF8Vxct7EXkVR, is_error=None)
02:34:07  MODEL OUTPUT  stop_reason  tool_use  (loop result: success)
```

---

### 4.8 The documents and their known values (from `extraction_setup.py`)

```python
INVOICES = {
    "D1": ("RIDGEWAY SHELVING CO.\nInvoice RS-20417\nDate: 2026-09-14\nBill to: Fernway Outfitters\n"
           "4 x steel warehouse shelving unit @ $460.00 = $1,840.00\nSales tax (8%): $147.20\nTotal due: $1,987.20"),
    ...
    "D4": ("Marta's Taxi Service\nMonthly statement for the Fernway Outfitters sales team\n"
           "14 rides between your Bend store and the airport\nFares: $351.36\nGST: $35.14\nPlease pay: $386.50\n"
           "Thank you!"),  # no invoice number, no date
    "D5": ("KESTREL RIDGE HOLDINGS\nDate: 2026-10-05\nFor: as agreed\nAmount due: $2,400.00\n"
           "Payment within 30 days."),  # no invoice number, no tax, and nothing says what was bought
}
...
TRUTH = {  # vendor, total, category, detail (a word it must contain), number, date, tax
    "D1": ("Ridgeway Shelving Co.", 1987.20, "equipment", None, "RS-20417", "2026-09-14", 147.20),
    "D2": ("Cloudnest Software", 486.00, "software", None, "CN-88213", "2026-10-01", 36.00),
    "D3": ("Hollis Pest Control", 302.40, "other", "pest", "HPC-5521", "2026-09-30", 22.40),
    "D4": ("Marta's Taxi Service", 386.50, "travel", None, None, None, 35.14),
    "D5": ("Kestrel Ridge Holdings", 2400.00, "unclear", None, None, "2026-10-05", None),
}
ABSENT = {"D4": ["invoice_number", "invoice_date"], "D5": ["invoice_number", "tax_amount"]}  # 4 absent fields
```

| Id | What it tests | Right answer for the hard fields |
|----|---------------|----------------------------------|
| D1 | complete; equipment | everything present |
| D2 | complete; software | everything present |
| D3 | complete, but **pest control fits no listed category** | `other`, with a detail containing "pest" |
| D4 | **no invoice number, no date** | `invoice_number: null`, `invoice_date: null` |
| D5 | **no invoice number, no tax, nothing says what was bought** | `null`, `null`, `category: unclear` |

**Why it matters:** "3 complete, 2 with missing fields" is the curriculum's test set, plus D3 to test the closed category list. `ABSENT` makes "what should be null" explicit, so the scorer can tell an honest `null` from a made-up value.

---

### 4.9 The two schemas (from `extraction_setup.py`)

#### a) `INVOICE_SCHEMA`: the honest design

```python
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
```

| Design choice | What it allows | Seen in the real run |
|---------------|----------------|----------------------|
| `required` = the 3 fields every invoice has | An absent field isn't forced | — |
| `["string", "null"]` / `["number", "null"]` | `null` is a valid value, so "not there" has a way to be said | D4 number and date `None`; D5 number and tax `None` |
| `unclear` in the enum | "the document doesn't say" is a valid category | D5 `category: 'unclear'` |
| `other` + `category_detail` | "none of the listed ones" without losing what it was | D3 `'other'`, `'Quarterly warehouse pest control treatment (service)'` |
| `"description"` on each field | Tells Claude when to use `null`, `unclear` and `other` | the `nullable` arm used each exactly where the descriptions say |
| `additionalProperties: False` | No extra keys; needed for `strict: true` tools in POC 2 | — |

**Why it matters:** this is the curriculum's root-cause fix for hallucinated extraction data. You don't stop invention with "don't invent" in the prompt; you give the honest answer a valid shape. Note that even `category_detail` and the 3 optional fields came back as explicit `None` keys in the real run, so downstream code sees a `null`, not a missing key (`score()` treats both the same).

**Agentic concept:** the schema is part of the prompt. The tool's input schema, including its descriptions, tells Claude what answers are possible.

#### b) `NAIVE_SCHEMA`: the anti-pattern

```python
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
```

**Why it matters:** three design flaws, each with a real consequence in the log:

| Flaw | What Claude had to do | Real output |
|------|-----------------------|-------------|
| every field `required`, no `null` | write a string for a missing number or date | D4 `invoice_number: ''`, `invoice_date: ''`; D5 `invoice_number: ''` |
| `tax_amount` a required `number` | write a number for a missing tax | D5 `tax_amount: 0` |
| `enum` without `unclear` or `other` | pick a listed category that doesn't fit | D3 `office_supplies` (pest control); D5 `equipment` (unknown) |
| no `description`s | rely on the short system prompt alone | vendors title-cased (`Ridgeway Shelving Co.`), not "as written" |

**Anti-pattern:** "every field required" feels safe because downstream code never sees a missing key. The price is that it never sees an honest "unknown" either: `''`, `0` and a wrong category all pass validation and look like data.

---

### 4.10 `EXTRACT_PROMPT` and `build_extract_options()`

```python
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
```

| Option | Effect | Agentic concept |
|--------|--------|-----------------|
| `model=settings.model_id` | Same model for both schemas | Controlled experiment |
| `system_prompt=EXTRACT_PROMPT` | A short, fixed prompt: "Fill the fields from the document only." | The prompt isn't the variable; the schema is |
| `output_format={"type": "json_schema", "schema": schema}` | Claude must call `StructuredOutput`; the SDK validates against `schema`, re-prompts on a mismatch, and returns the JSON in `structured_output` | Structured output through tool use |
| `tools=[]` | No built-in tools | Least privilege; the document is in the prompt |
| `setting_sources=[]` | No user/project settings, `CLAUDE.md` or hooks | Reproducibility |
| `env={"ENABLE_TOOL_SEARCH": "false"}` | No ToolSearch calls | A clean stream |
| `thinking={"type": "adaptive", "display": "summarized"}` | Claude decides when to think; summaries come back as `ThinkingBlock` | Observability: the D3–D5 thinking shows the schema's pressure |
| `max_turns=settings.max_turns` | Caps turns, leaving room for schema retries | Safety cap |
| `max_budget_usd=settings.max_budget_usd` | Stops a call whose estimated spend passes the cap | Cost guard |

**Why it matters:** `schema` is the only parameter that differs between the runs. Note that the prompt says "from the document only" in both runs. That instruction didn't stop the naive run from writing `0` and `equipment`: when instructions and schema disagree, the schema decides what can be returned.

---

### 4.11 `extract()`: one document, one session, one `(data, subtype)`

```python
async def extract(settings: Settings, doc_id: str, schema: dict) -> tuple[dict | None, str]:
    """One query(). Returns (structured_output or None, the result subtype)."""
    prompt = f"Extract this invoice.\n\n<document>\n{DOCUMENTS[doc_id]}\n</document>"
    log.info("MODEL INPUT   prompt       %s", prompt)
    data, subtype = None, "no result"
    try:
        async for message in query(prompt=prompt, options=build_extract_options(settings, schema)):
            log_model_io(message)
            if isinstance(message, ResultMessage):
                subtype = message.subtype
                if message.subtype == "success":
                    data = message.structured_output  # validated against the schema by the SDK
            # No `break`: a few system events can still arrive after the ResultMessage.
    except ResultError as exc:  # e.g. error_max_structured_output_retries: no valid answer fit the schema
        log.error("The extraction failed: %s", exc)
    return data, subtype
```

**Why it matters:**
- **A new session per document.** Each `query()` starts with an empty history; no extraction influences the next.
- **`subtype` is returned too,** so `main()` can say *why* a call produced nothing. It starts as `"no result"` in case the stream ends without a `ResultMessage`.
- **`subtype == "success"` is the completion check,** not `stop_reason`. With `output_format`, success ends with `stop_reason == "tool_use"`.
- **`structured_output` is already validated.** No `json.loads()`, no try/except around parsing: if the SDK hands it over, it matches the schema.
- **`ResultError` after an error result.** If no answer Claude gives fits the schema before the cap, the SDK yields an error `ResultMessage` (e.g. `error_max_structured_output_retries`) and then raises. That's the other honest outcome a strict schema can produce: no data instead of fake data.

Log line it wrote (`MODEL INPUT   prompt`):

```
02:34:19  MODEL INPUT   prompt       Extract this invoice.

<document>
Marta's Taxi Service
Monthly statement for the Fernway Outfitters sales team
...
</document>
```

---

### 4.12 `score()`: correct, null, invented or wrong

```python
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
```

| Field | Rule |
|-------|------|
| an `ABSENT` field | `null` if the value is `None` (or the key is missing), otherwise `invented(<value>)`: `''` and `0` count as invented |
| `total_amount`, `tax_amount` | a number within 0.01 (`486` = `486.00`) |
| `vendor_name` | the true name, lowercased and without a trailing dot, is contained in the value (case-insensitive) |
| `category`, number, date | exact match |
| `category_detail` (honest schema only) | `null` when no detail is expected; otherwise it must contain the expected word (`pest`) |

**Why it matters:**
- **`invented` is strict on purpose.** An empty string and a zero are not "no value": they're values that downstream code will store and use. That's why `invented('')` and `invented(0)` both count.
- **Wrong values keep their raw value** (`wrong('office_supplies')`), so the score line shows what Claude chose.
- **The case-insensitive vendor rule** hides the casing difference between the runs (section 5).

---

## 5. Turn-by-turn trace of each run (real output)

Each run is 5 `query()` calls. Every call is one turn: Claude calls `StructuredOutput`, the SDK accepts it, and the session ends. Times are from `logs/poc1_schema_design_20261114_023403.log`.

### 5.1 Run 1: `naive` (every field required, no `null`)

```
02:34:07  MODEL OUTPUT  structured   {'vendor_name': 'Ridgeway Shelving Co.', 'total_amount': 1987.2, 'category': 'equipment', 'invoice_number': 'RS-20417', 'invoice_date': '2026-09-14', 'tax_amount': 147.2}  (id=toolu_018d3sKGV6DmF8Vxct7EXkVR)
02:34:08  naive    D1: vendor_name=correct total_amount=correct category=correct invoice_number=correct invoice_date=correct tax_amount=correct
02:34:11  MODEL OUTPUT  structured   {'vendor_name': 'CloudNest Software', 'total_amount': 486, 'category': 'software', 'invoice_number': 'CN-88213', 'invoice_date': '2026-10-01', 'tax_amount': 36}  (id=toolu_01QGBzeVcUGjDUxnF2wPtKfC)
02:34:13  naive    D2: vendor_name=correct ... tax_amount=correct
02:34:17  MODEL OUTPUT  thinking     The category list offers equipment, software, office_supplies, and travel, and none of them fits a pest control service. I have to pick one anyway, so office_supplies looks like the least bad fallback. I'll note that mismatch in my reply and then make the tool call.
02:34:17  MODEL OUTPUT  structured   {'vendor_name': 'Hollis Pest Control', 'total_amount': 302.4, 'category': 'office_supplies', 'invoice_number': 'HPC-5521', 'invoice_date': '2026-09-30', 'tax_amount': 22.4}  (id=toolu_01HEwfnciTYhMtsTJ7i8cyGL)
02:34:19  naive    D3: vendor_name=correct total_amount=correct category=wrong('office_supplies') invoice_number=correct invoice_date=correct tax_amount=correct
02:34:22  MODEL OUTPUT  thinking     I'm noticing the document doesn't have an invoice number or date, so I'll leave those as empty strings rather than null, since the required fields have to be strings.
02:34:22  MODEL OUTPUT  structured   {'vendor_name': "Marta's Taxi Service", 'total_amount': 386.5, 'category': 'travel', 'invoice_number': '', 'invoice_date': '', 'tax_amount': 35.14}  (id=toolu_01PazHTJegHwctFBTBTNkeTx)
02:34:23  naive    D4: vendor_name=correct total_amount=correct category=correct invoice_number=invented('') invoice_date=invented('') tax_amount=correct
02:34:32  MODEL OUTPUT  thinking     I'm checking the document for the invoice number, tax amount, and category, ... I'll pick the closest fit and note that it's a guess.
02:34:32  MODEL OUTPUT  structured   {'vendor_name': 'Kestrel Ridge Holdings', 'total_amount': 2400, 'category': 'equipment', 'invoice_number': '', 'invoice_date': '2026-10-05', 'tax_amount': 0}  (id=toolu_01XHn2q4LvoEN4EudKQ4KCM2)
02:34:33  naive    D5: vendor_name=correct total_amount=correct category=wrong('equipment') invoice_number=invented('') invoice_date=correct tax_amount=invented(0)
02:34:33  naive    totals: 4 of 4 absent fields invented, 2 of 5 categories wrong
```

(The `prompt`, `tool_result` and `stop_reason` lines are left out; each call has one of each, with `is_error=None` and `tool_use  (loop result: success)`.)

| Variable / field (code) | Value in the real run |
|-------------------------|-----------------------|
| `schema` (`main()`) | `NAIVE_SCHEMA` |
| `message.subtype` / `stop_reason` | `success` / `tool_use` × 5 |
| `data` (from `structured_output`) | 5 dicts, never `None` |
| `subtype` returned by `extract()` | `"success"` × 5 |
| D4 `invoice_number`, `invoice_date` | `''`, `''` → `invented('')` × 2 |
| D5 `invoice_number`, `tax_amount` | `''`, `0` → `invented('')`, `invented(0)` |
| D3, D5 `category` | `office_supplies`, `equipment` → `wrong(...)` |
| `invented` / `wrong_category` | `4` / `2` |
| `ResultError` / `ClaudeSDKError` | not raised |
| Wall time | 02:34:03 → 02:34:33, about 30 s (D5 alone about 9 s) |

Lessons from the real data:
- **Every absent field got a value: 4 of 4.** Not a single plausible fake number or date, but `''` and `0`, which pass the schema and look like data. A database column `invoice_number = ''` can't be told apart from "a blank was printed".
- **The closed enum forced 2 wrong categories out of 5.** The D3 thinking says it outright: "none of them fits a pest control service. I have to pick one anyway, so office_supplies looks like the least bad fallback."
- **Claude knew, and said so only in its thinking.** D3: "I'll note that mismatch in my reply". D5: "flagging that it wasn't stated ... note that it's a guess". No `text` line appears in the run: with `output_format`, the only answer is the JSON, and the JSON has no field for a caveat.
- **The validator never rejected anything.** One `structured` line per document, each accepted at once. The pressure worked before validation: Claude picked a schema-valid value instead of trying `null`.
- **The harder the choice, the longer the call.** D5, with three forced choices, took about 9 s from prompt to answer; D1 and D2 about 3–4 s, with no thinking line.

### 5.2 Run 2: `nullable` (3 required, 3 nullable, `unclear`/`other`)

```
02:34:37  MODEL OUTPUT  structured   {'vendor_name': 'RIDGEWAY SHELVING CO.', 'total_amount': 1987.2, 'category': 'equipment', 'invoice_number': 'RS-20417', 'invoice_date': '2026-09-14', 'tax_amount': 147.2, 'category_detail': None}  (id=toolu_01BYq2JqjYLLxSLgp4mCne3S)
02:34:38  nullable D1: vendor_name=correct total_amount=correct category=correct invoice_number=correct invoice_date=correct tax_amount=correct category_detail=correct
02:34:41  MODEL OUTPUT  structured   {'vendor_name': 'CLOUDNEST SOFTWARE', 'total_amount': 486, 'category': 'software', 'invoice_date': '2026-10-01', 'invoice_number': 'CN-88213', 'tax_amount': 36, 'category_detail': None}  (id=toolu_01W6jjFZbP8zDj9pskncHfiN)
02:34:46  MODEL OUTPUT  structured   {'vendor_name': 'HOLLIS PEST CONTROL', 'total_amount': 302.4, 'category': 'other', 'category_detail': 'Quarterly warehouse pest control treatment (service)', 'invoice_date': '2026-09-30', 'invoice_number': 'HPC-5521', 'tax_amount': 22.4}  (id=toolu_01QReLAnYkR3KK9cJpdoCjsD)
02:34:47  nullable D3: vendor_name=correct total_amount=correct category=correct invoice_number=correct invoice_date=correct tax_amount=correct category_detail=correct
02:34:50  MODEL OUTPUT  structured   {'vendor_name': "Marta's Taxi Service", 'total_amount': 386.5, 'tax_amount': 35.14, 'category': 'travel', 'invoice_date': None, 'invoice_number': None, 'category_detail': None}  (id=toolu_016GBue6iKMd2eZdiX75PoTV)
02:34:51  nullable D4: vendor_name=correct total_amount=correct category=correct invoice_number=null invoice_date=null tax_amount=correct category_detail=correct
02:34:54  MODEL OUTPUT  structured   {'vendor_name': 'KESTREL RIDGE HOLDINGS', 'total_amount': 2400, 'category': 'unclear', 'invoice_date': '2026-10-05', 'invoice_number': None, 'tax_amount': None, 'category_detail': None}  (id=toolu_01WrEYLZjcVKCYCo7gVqjvUo)
02:34:56  nullable D5: vendor_name=correct total_amount=correct category=correct invoice_number=null invoice_date=correct tax_amount=null category_detail=correct
02:34:56  nullable totals: 0 of 4 absent fields invented, 0 of 5 categories wrong
02:34:56  Same documents, prompt, model and options: only the schema changed
```

| Variable / field (code) | Value in the real run |
|-------------------------|-----------------------|
| `schema` | `INVOICE_SCHEMA` |
| `message.subtype` / `stop_reason` | `success` / `tool_use` × 5 |
| D4 `invoice_number`, `invoice_date` | `None`, `None` → `null` × 2 |
| D5 `invoice_number`, `tax_amount` | `None`, `None` → `null` × 2 |
| D3 `category`, `category_detail` | `'other'`, `'Quarterly warehouse pest control treatment (service)'` |
| D5 `category` | `'unclear'` |
| `category_detail` for D1, D2, D4, D5 | `None` (sent as an explicit key) |
| `invented` / `wrong_category` | `0` / `0` |
| `thinking` lines | none |
| Wall time | 02:34:33 → 02:34:56, about 23 s |

Lessons from the real data:
- **Every absent field came back `null`: 0 of 4 invented.** Same documents, same prompt, same model. The only change was the schema.
- **`other` and `unclear` were used exactly where they belong.** D3 got `other` with a detail that contains "pest"; D5 got `unclear`. Every category was right (0 of 5 wrong, against 2 of 5).
- **Complete documents stayed complete.** D1–D3 scored `correct` on every field: the nullable types didn't make Claude lazy on fields that are present.
- **The field descriptions changed the vendor names.** The honest schema says `vendor_name` is "The company that issued the invoice, as written". This run returned `RIDGEWAY SHELVING CO.`, `CLOUDNEST SOFTWARE`, `HOLLIS PEST CONTROL` and `KESTREL RIDGE HOLDINGS`, as printed. The naive schema has no descriptions, and that run title-cased them. `score()` is case-insensitive, so neither run lost points for it.
- **No thinking needed.** With an honest answer available for every field, no call logged a `thinking` line, and the run was about 7 s faster.
- **Key order varies** (`tax_amount` before `category` on D4). JSON objects are unordered; `structured_output` is a dict, so it doesn't matter.

### 5.3 The two runs side by side

| | `naive` | `nullable` |
|-|---------|------------|
| Schema | 6 required, no `null`, 4-value enum, no descriptions | 3 required, 3 nullable, 6-value enum + `category_detail`, descriptions |
| `query()` calls | 5 | 5 |
| `StructuredOutput` calls | 5 (no retries) | 5 (no retries) |
| Final `subtype` / `stop_reason` | `success` / `tool_use` × 5 | `success` / `tool_use` × 5 |
| `thinking` lines | D3, D4, D5 | none |
| Absent fields invented | 4 of 4 (`''`, `''`, `''`, `0`) | 0 of 4 (all `None`) |
| Categories wrong | 2 of 5 (D3 `office_supplies`, D5 `equipment`) | 0 of 5 (D3 `other`, D5 `unclear`) |
| Vendor casing | title case (`Ridgeway Shelving Co.`) | as printed (`RIDGEWAY SHELVING CO.`) |
| `ResultError` / `ClaudeSDKError` | no | no |
| Wall time (from log) | about 30 s | about 23 s |

The log has no `no structured output`, `The extraction failed:` or `SDK error:` line, so the script exited with `0`.

**The correction the log makes:** the docstring says the naive schema's validator "rejects every honest 'nothing here', so Claude MUST invent", and the README's illustrative lines show invented values like `'N/A'` and `'2026-09-30'`. In the real run nothing was rejected, because Claude never offered `null`. It filled the gaps with `''` and `0` on its first try, after reasoning in its thinking that the schema left no other choice. The outcome is the one the POC predicts (4 of 4 absent fields filled), reached by anticipation rather than by validator retries.

---

## 6. Agentic AI concepts recap

| Concept | How this POC shows it |
|---------|-----------------------|
| **Structured output through tool use** | `output_format` → Claude calls `StructuredOutput` → the SDK validates → `ResultMessage.structured_output`. |
| **Schema design prevents fabrication** | Same everything, only the schema changed: invented absent fields 4 → 0, wrong categories 2 → 0. |
| **Required fields pressure invention** | `NAIVE_SCHEMA`: D4 and D5 got `''` and `0` for fields the documents don't have. |
| **Nullable optional fields** | `["string", "null"]`, `["number", "null"]`, and `required` limited to the 3 always-present fields. |
| **Escape values in enums** | `unclear` for "the document doesn't say", `other` + `category_detail` for "none of these". |
| **Schema descriptions are instructions** | "as written" and "or null if the document has none" steered the honest run; the naive run had neither. |
| **Instructions lose to the schema** | "Fill the fields from the document only" didn't stop `tax_amount: 0`: the schema had no other valid answer. |
| **Validated output, no parsing** | `extract()` reads a dict; no `json.loads()`, no repair code. |
| **Completion signal** | `subtype == "success"` with `stop_reason == "tool_use"` on every call. |
| **Honest failure** | A strict schema with no valid answer ends in `error_max_structured_output_retries` and `None`, not fake data (not triggered here). |
| **Observability** | Adaptive thinking exposed the forced choices ("I have to pick one anyway") that the JSON alone hides. |

---

## 7. Common mistakes this POC helps you avoid

1. **Marking every field `required` "to be safe".** It removes the honest answer for absent data; you get `''`, `0` or a guess instead.
2. **Treating an empty string as "missing".** `''` is a value. It passes a `string` check and lands in your database. Use `null`.
3. **Using `0` for an unknown amount.** "No tax shown" and "tax is 0" are different facts. Make the field `["number", "null"]`.
4. **A closed enum with no way out.** Without `unclear` and `other`, every misfit becomes a wrong category (D3, D5).
5. **`other` without a detail field.** You'd know it didn't fit, but not what it was. `category_detail` keeps the information.
6. **Fixing fabrication with "don't invent" in the prompt.** The prompt already said "from the document only". The schema is the root-cause fix.
7. **Leaving fields undescribed.** Descriptions tell Claude when `null`, `unclear` and `other` apply, and how to format values ("as written").
8. **Parsing JSON out of text.** Use `output_format` (or a tool) and read `structured_output`.
9. **Checking `stop_reason == "end_turn"` for structured output.** All 10 successful calls ended with `tool_use`.
10. **Expecting Claude's caveats to reach your code.** "I'll note that it's a guess" stayed in the thinking. If you need a confidence flag, put it in the schema.
11. **A scorer that counts `''` as "missing".** Then the naive run would look honest. Count any non-null value for an absent field as invented.

---

## 8. Claude Architect exam lens

### 8.1 What the exam tests on this topic

The objectives come from `curriculum/04-Prompt-Engineering-Structured-Output/03-raw-Structured-Output-with-Tool-Use.md`. POC 1 covers objectives 1 and 5; POC 2 covers 2–4 (`tool_choice` `auto`, `any` and forced).

| Exam objective | What a correct answer looks like | Where this POC shows it |
|----------------|----------------------------------|-------------------------|
| 1. An extraction tool with a JSON schema: 3 required, 3 optional/nullable, an enum with `unclear` and `other`, a detail field for `other` | `required` lists only the always-present fields; optional fields are typed `["string", "null"]`; the enum includes `unclear` and `other`; `other` comes with a free-text detail. Schema design is the root-cause fix for hallucinated data. | `INVOICE_SCHEMA` in `extraction_setup.py` |
| 2. `tool_choice: auto` returns text sometimes | `auto` doesn't guarantee structured output. | Not in POC 1 (see POC 2). In the SDK, `output_format` is the guarantee |
| 3. `tool_choice: any` always returns a tool call | Guaranteed call, Claude picks the tool: right when the document type is unknown. | Not in POC 1 (see POC 2) |
| 4. Forced `tool_choice` | A mandatory first step always runs. | Not in POC 1 (see POC 2) |
| 5. 5 documents, 3 complete and 2 with missing fields: nullable fields return `null` | Complete documents fully correct; missing data comes back `null`, with no invented dates, amounts or identifiers. Required fields are what pressure the model to invent. | The two runs: `naive totals: 4 of 4 absent fields invented`, `nullable totals: 0 of 4` |

> **Exam tip:** the exam describes structured output as a Messages API tool with an `input_schema`, called with `tool_choice` set to `any` or to the tool. The Agent SDK has no `tool_choice`; its guarantee is `output_format`, which works the same way underneath: a tool (`StructuredOutput`) whose input schema is your schema. The schema rules are identical in both forms.

### 8.2 The same extraction with the raw Messages API

On the Messages API, the honest schema becomes a tool's `input_schema`, and `tool_choice` makes the call mandatory. The README notes that Opus 5.5, Sonnet 5.5 and Fable 5.1 reject `any` and forced `tool_choice` with a 400 error, so POC 2 uses `claude-haiku-5-5`; the same constraint applies here.

```python
import anthropic

client = anthropic.Anthropic()
# INVOICE_SCHEMA, EXTRACT_PROMPT and DOCUMENTS are as in extraction_setup.py.

EXTRACT_INVOICE = {
    "name": "extract_invoice",
    "description": "Records a supplier invoice. Use null for any optional field the document doesn't show.",
    "input_schema": INVOICE_SCHEMA,  # the same honest schema: 3 required, 3 nullable, unclear/other
    "strict": True,  # the input must match the schema (needs additionalProperties: False)
}


def extract(doc_id: str) -> dict | None:
    response = client.messages.create(
        model="claude-haiku-5-5",  # accepts a forced tool_choice (see the README)
        max_tokens=2048,
        system=EXTRACT_PROMPT,
        tools=[EXTRACT_INVOICE],
        tool_choice={"type": "tool", "name": "extract_invoice"},  # always this tool: guaranteed structured output
        messages=[{"role": "user", "content": f"Extract this invoice.\n\n<document>\n{DOCUMENTS[doc_id]}\n</document>"}],
    )
    for block in response.content:  # stop_reason is "tool_use"
        if block.type == "tool_use":
            return block.input  # a dict shaped by INVOICE_SCHEMA; None for absent optional fields
    return None
```

| Raw Messages API (you write it) | Agent SDK (`poc1_schema_design.py` + `extraction_setup.py`) |
|---------------------------------|-------------------------------------------------------------|
| A tool with `input_schema=INVOICE_SCHEMA` | `output_format={"type": "json_schema", "schema": schema}` → the built-in `StructuredOutput` tool |
| `tool_choice={"type": "tool", ...}` or `{"type": "any"}` forces the call | No `tool_choice` in `ClaudeAgentOptions`; `output_format` makes the `StructuredOutput` call the way to finish |
| `"strict": True` makes the input schema-valid | The SDK validates and re-prompts on a mismatch; gives up with `error_max_structured_output_retries` |
| `block.input` of the `tool_use` block | `ResultMessage.structured_output` |
| `response.stop_reason == "tool_use"` | Final `stop_reason == "tool_use"`, `subtype == "success"` |
| Model must accept forced tool use (`claude-haiku-5-5` here) | Any model `MODEL_ID` names |
| One request, nothing to cap | `max_turns` (room for retries) and `max_budget_usd` per call |
| Field `description`s in the schema guide Claude | The same: the descriptions travel with the `StructuredOutput` tool's schema |

Two things the raw version makes obvious:
- **Structured output *is* tool use.** The SDK's `StructuredOutput` tool is what you'd write by hand: a tool whose only job is to receive the JSON.
- **Forcing the call doesn't make the content honest.** `tool_choice` guarantees *a* call; only the schema decides whether "not there" can be said inside it.

### 8.3 Scenario questions

Try each one before reading the answer. These questions were written for this article to match the curriculum objectives above. They are not official exam questions.

---

**Scenario 1: Invoice numbers that don't exist**

An extraction pipeline marks every field required. Audits find invoice numbers like `''` and `INV-0000` on statements that never had one. The prompt already says "use only information in the document". What is the root-cause fix?

- A. Add "NEVER invent invoice numbers" to the system prompt in capitals.
- B. Make `invoice_number` optional and nullable (`["string", "null"]`), keep `required` to the always-present fields, and describe when to use `null`.
- C. Post-process: replace `''` with `null`.
- D. Add few-shot examples with real invoice numbers.

**Answer: B.** A required non-nullable field leaves the model no honest answer, so it fills the gap. Schema design is the root-cause fix. A was already there in spirit and didn't help. C catches `''` but not `INV-0000`. D shows more invoice numbers, which doesn't help when there isn't one. *POC link:* `NAIVE_SCHEMA` vs `INVOICE_SCHEMA`; the real run's `naive D4: ... invoice_number=invented('') invoice_date=invented('')` vs `nullable D4: ... invoice_number=null invoice_date=null`.

---

**Scenario 2: Which schema is right?**

An invoice always has a vendor, a total and a category; it sometimes has an invoice number, a date and a tax line. Which `required` list and types are correct?

- A. `required`: all six fields, all typed `string`/`number`.
- B. `required`: `vendor_name`, `total_amount`, `category`; the other three typed `["string", "null"]` / `["number", "null"]`.
- C. `required`: none; every field typed with `null`.
- D. `required`: all six, each typed with `null` allowed.

**Answer: B.** `required` lists only what's always present; the rest are optional and nullable. A forces invention. C lets the model skip fields every invoice has. D is workable but keeps a key the model must fill for every field; the curriculum's design is B. *POC link:* `INVOICE_SCHEMA["required"]` and its nullable types.

---

**Scenario 3: The pest-control invoice**

The category enum is `equipment`, `software`, `office_supplies`, `travel`. A pest-control invoice keeps landing in `office_supplies`. What schema change fixes it?

- A. Add `pest_control` to the enum.
- B. Add `other` to the enum plus a `category_detail` string used only with `other`, and `unclear` for documents that don't say.
- C. Remove the enum and accept any string.
- D. Tell the model to pick the closest category.

**Answer: B.** `other` + detail handles every future misfit without growing the enum for each one; `unclear` handles documents that say nothing. A fixes one case only. C loses the closed list that downstream code depends on. D is what produced the wrong answer. *POC link:* the real run: `naive D3: ... category=wrong('office_supplies')`, whose thinking says "none of them fits ... I have to pick one anyway"; `nullable D3` returned `'other'` with `'Quarterly warehouse pest control treatment (service)'`.

---

**Scenario 4: A bill that doesn't say what it's for**

A document reads "For: as agreed. Amount due: $2,400.00". Which output is correct with a well-designed schema?

- A. `category: "equipment"`, the most common category.
- B. `category: "other"`, `category_detail: "as agreed"`.
- C. `category: "unclear"`, `category_detail: null`.
- D. Skip the document.

**Answer: C.** `unclear` means "the document doesn't say"; `other` means "it says, and it's none of the listed ones". "As agreed" says nothing about what was bought. *POC link:* D5 in `TRUTH` (`"unclear"`); the real run: `naive` returned `equipment` ("I'll pick the closest fit and note that it's a guess"), `nullable` returned `unclear`.

---

**Scenario 5: Zero tax**

With a schema where `tax_amount` is a required number, an invoice with no tax line comes back with `tax_amount: 0`. Why is this a problem, and what's the fix?

- A. No problem: no tax line means zero tax.
- B. `0` asserts a fact the document doesn't state; make `tax_amount` `["number", "null"]` with the description "null if the document shows no tax".
- C. Use `-1` as a sentinel for "unknown".
- D. Make `tax_amount` a string so the model can write "none".

**Answer: B.** "Not shown" and "zero" are different facts, and only `null` says the first. C invents a magic number downstream code must know about. D breaks the type for every invoice that has tax. *POC link:* the real run: `naive D5: ... tax_amount=invented(0)`, after thinking "I'm going with 0 for the tax and flagging that it wasn't stated"; `nullable D5: ... tax_amount=null`.

---

**Scenario 6: The model knew it was guessing**

Claude's thinking on a document says "I'll pick the closest fit and note that it's a guess", but the structured output contains only the guessed value with no note. The team wants to know when values are guesses. What should they do?

- A. Parse the thinking text for the word "guess".
- B. Give the schema an honest way to express it: `unclear` / `null` for unknowns, or an explicit confidence or `notes` field if needed.
- C. Ask for the answer in free text instead.
- D. Raise `max_turns`.

**Answer: B.** With structured output, the JSON is the whole answer; anything the schema has no field for doesn't reach your code. A depends on thinking text that may be summarized or absent. C gives up guaranteed structure. D changes nothing. *POC link:* the real run's D3 and D5 thinking lines in the `naive` run, and the absence of any `text` line.

---

**Scenario 7: Reading the result**

A developer reads `ResultMessage` after an `output_format` call and sees `subtype == "success"` and `stop_reason == "tool_use"`. They think the run is unfinished. Where is the JSON?

- A. In the last `TextBlock`; parse it with `json.loads()`.
- B. In `ResultMessage.structured_output`, already validated against the schema. `tool_use` is expected: Claude finished by calling `StructuredOutput`.
- C. Nowhere; `tool_use` means a tool is still pending.
- D. In `ResultMessage.result`, as a string.

**Answer: B.** With `output_format`, Claude hands in the JSON through the `StructuredOutput` tool, so a successful run ends with `stop_reason == "tool_use"`, and `subtype` is the completion signal. *POC link:* `extract()` reads `message.structured_output` when `subtype == "success"`; all 10 calls in the log end `stop_reason  tool_use  (loop result: success)`.

---

**Scenario 8: No valid answer**

A strict schema requires a field the document doesn't have, and the model keeps returning `null`, which the schema rejects. What does the Agent SDK do, and how should the code handle it?

- A. It returns the last invalid JSON in `structured_output`.
- B. It re-prompts within the turn cap, then ends with an error result such as `error_max_structured_output_retries` and raises `ResultError`; the code should catch it and treat the document as not extracted.
- C. It silently drops the field.
- D. It switches to free text.

**Answer: B.** The SDK validates each `StructuredOutput` call and re-prompts on a mismatch; when retries run out, the run ends with an error subtype and a `ResultError`. That's an honest failure (no data), better than fake data, but the real fix is a schema that allows `null`. *POC link:* the `except ResultError` in `extract()` and the `data is None` branch in `main()`, which logs `no structured output (<subtype>)`. Not triggered in the real run: Claude never sent `null` to the naive schema.

---

**Scenario 9: Complete documents with the new schema**

After switching to nullable optional fields, a reviewer worries the model will return `null` even when data is present. How do you check?

- A. Trust the model.
- B. Include complete documents in the test set with known values and confirm every present field is extracted correctly, while absent fields come back `null`.
- C. Make all fields required again.
- D. Only test documents with missing fields.

**Answer: B.** The curriculum's test is both halves: complete documents fully correct, and missing data `null`. *POC link:* `nullable D1`–`D3` all `correct` in the real run, and `nullable totals: 0 of 4 absent fields invented, 0 of 5 categories wrong`.

---

**Scenario 10: Forced tool, dishonest content**

A team forces the extraction tool with `tool_choice` and is surprised that fabricated dates still appear. Why?

- A. `tool_choice` is ignored by the API.
- B. Forcing guarantees that the tool is called, not what goes in it. With required non-nullable fields, the model still has to fill them; the schema decides whether "not there" can be said.
- C. Forced tools disable schema validation.
- D. The model needs `temperature=0`.

**Answer: B.** `tool_choice` (`any` or forced) solves "did we get structured output"; schema design solves "is the content honest". You need both. *POC link:* in POC 1 every call was guaranteed structured output (`output_format`), yet the naive schema still produced `invented` values; only the schema change removed them.

---

### 8.4 Quick-recall cheat sheet

```
structured output       → a tool whose input schema IS your schema (SDK: output_format → StructuredOutput)
read the result         → ResultMessage.structured_output; subtype "success", stop_reason "tool_use"
required                → ONLY the fields every document has
optional fields         → ["string", "null"] / ["number", "null"] + description "null if the document has none"
closed list             → add "unclear" (doesn't say) and "other" (+ a detail field) to the enum
fabrication             → root cause = schema design, not the prompt ("from the document only" didn't stop it)
'' and 0                → values, not "missing": they pass validation and look like data
descriptions            → instructions: "as written", "or null if ..." change what comes back
caveats in thinking     → never reach your code; put flags in the schema if you need them
no valid answer         → SDK retries, then error_max_structured_output_retries + ResultError (no fake data)
tool_choice (POC 2)     → auto: may answer in text; any: a call, model picks; tool: that call, always
forcing a call          → guarantees structure, NOT honesty; that's the schema's job
```

---

## 9. How to run it

```bash
cd 04-Prompt-Engineering-Structured-Output/03-Structured-Output-with-Tool-Use
source .venv/bin/activate        # the folder's venv (claude-agent-sdk 0.2.181, anthropic 2.8.0)
python poc1_schema_design.py     # paid: 2 runs × 5 invoices = 10 query() calls
python poc2_tool_choice.py       # paid: POC 2, auto/any/forced on the Messages API
```

- Without the venv: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`, then `cp .env.example .env` and add your key.
- Both scripts call the API. This folder has no free offline demo.
- `.env` needs `ANTHROPIC_API_KEY`. `MODEL_ID`, `MAX_TURNS` and `MAX_BUDGET_USD` fall back to `claude-sonnet-5-5`, `10` and `0.50`.
- Every model input and output, the score lines and the totals are printed to the console and written to `logs/poc1_schema_design_<date>_<time>.log`. Expect different placeholders under the naive schema on each run (`''`, `'N/A'`, a guessed date); the totals pattern stays the same.
- The exit code is `0` when both runs finish (a document with no structured output is logged and skipped). It's `1` on a setup failure (`OSError`, `RuntimeError`) or an SDK runtime failure (`ClaudeSDKError`).
