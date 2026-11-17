# POC 1: Fix the Data Before Claude Reads It

> **File:** `poc1_normalize_test.py` (with `hooks_setup.py` and `common.py`)
> **Domain:** 01 Agentic Architecture & Orchestration → 05 Agent SDK Hooks
> **SDK:** Claude Agent SDK for Python (`claude-agent-sdk >=0.2.174,<0.3`; 0.2.181 in the folder's `.venv`)
> **Page:** https://claude.ai/artifact/KSbmyK2c3ZCkzgjaCeYjNx

---

## 1. What this POC proves

Three order systems answer the same question in three formats. Without help, Claude has to decode each format itself, and it can guess wrong. A `PostToolUse` hook rewrites every result into one format before Claude sees it. Every claim below is checked against one real run: `logs/poc1_normalize_test_20261113_205318.log`.

| # | Idea | Where it shows up in the code |
|---|------|------------------------------|
| 1 | **Format chaos causes real misreads.** System C's `04/05/2026` is 4 May; read month-first it's 5 April, and the order of the orders changes. | `ORDERS` in `hooks_setup.py`; run `baseline`: `WRONG` |
| 2 | **A `PostToolUse` hook runs after the handler and before Claude.** It sees the result and can replace it. | `normalize_output()`, registered under `"PostToolUse"` |
| 3 | **The replacement goes back as `updatedToolOutput` inside `hookSpecificOutput`,** in the same shape as the tool's output. | the return value of `normalize_output()`; `same_shape()` |
| 4 | **One set of rules for every tool.** ISO 8601 dates and English statuses, whichever system answered. | `to_iso()`, `to_status()`, `normalize_record()`; the matcher `"mcp__orders__.*"` |
| 5 | **`PostToolUse`, not `PreToolUse`, is the direction for data.** Before the handler runs there is no result to rewrite. | the comment above `NORMALIZE_HOOKS` |
| 6 | **Consistent input, correct answer.** The same prompt and tools, with the hook on, gave the right order and the right pending list. | run `normalized`: `matches the truth` |

The pattern in one line:

```
Claude ──tool_use──▶ handler (raw format) ──▶ PostToolUse hook: updatedToolOutput (ISO dates, English statuses) ──▶ Claude
```

---

## 2. The files involved

```
05-Agent-SDK-Hooks/
├── .env / .env.example       ← ANTHROPIC_API_KEY, MODEL_ID, MAX_TURNS, MAX_BUDGET_USD
├── requirements.txt          ← claude-agent-sdk >=0.2.174,<0.3 and python-dotenv
├── common.py                 ← Settings, load_settings(), setup_logging(), log_model_io()
├── hooks_setup.py            ← 3 order systems, 3 payment tools, HookState, build_hook_options(), run_agent()
├── poc1_normalize_test.py    ← entry point: the PostToolUse normalization hook, 2 runs
├── poc2_policy_test.py       ← POC 2: PreToolUse policy hooks (not covered here)
└── logs/
    └── poc1_normalize_test_20261113_205318.log   ← the real run used in sections 3.2 and 5
```

Every snippet in this article is copied from these files, logging statements included. Each logging statement is named with the log line it writes.

The responsibilities split like this:
- `common.py` covers **configuration and observability** (single-agent log lines).
- `hooks_setup.py` covers **capabilities** (the order tools, which return raw formats on purpose), **state** (`HookState`), the **options** (where hooks are plugged in) and the agent loop (`run_agent()`).
- `poc1_normalize_test.py` covers **the hook itself** (the normalization rules and `normalize_output()`) and **the experiment** (with and without the hook, checked against the truth).

---

## 3. End-to-end execution flow

### 3.1 The big picture

```
python poc1_normalize_test.py
        │
        ▼
asyncio.run(main())                                                      [poc1_normalize_test.py]
        │
        ├─▶ load_settings(), setup_logging("poc1_normalize_test")        [common.py]
        │
        └─▶ for name, hooks in RUNS:                ("baseline", None), ("normalized", NORMALIZE_HOOKS)
               │
               ├─▶ options = build_hook_options(settings, HookState(), "orders", hooks)   [hooks_setup.py]
               │       mcp_servers = {"orders": 3 tools}, hooks = None or {"PostToolUse": [HookMatcher(...)]}
               ├─▶ run = run_agent(TEST_PROMPT, options)                  → one query() call
               ├─▶ summary = parse_summary(run["answer"])                 the ORDERS | PENDING line
               └─▶ log.info("Run '%s': summary %s -> %s")                 compared with TRUTH
```

Inside `run_agent()`, for the `normalized` run. The right-hand column names the log line each step writes.

```
run_agent(user_prompt, options)                                                        [hooks_setup.py]
   │
   ├─ log.info("MODEL INPUT   prompt ...")                                           → log: prompt
   └─▶ async for message in query(prompt=user_prompt, options=options):
          │
          │   ┌──────────────────────── SDK-owned: the agent loop ─────────────────────────┐
          │   │ Claude: tool_use mcp__orders__system_X {customer_id}                        │  → log: tool_use
          │   │    └─▶ your handler → {"orders": [{... "order_date": raw, "status": raw}]}  │  (not logged)
          │   │    └─▶ PostToolUse hooks whose matcher fits "mcp__orders__system_X"         │
          │   │          normalize_output(input_data, tool_use_id, context)                 │  (not logged)
          │   │          → {"hookSpecificOutput": {"updatedToolOutput": normalized}}        │
          │   │    └─▶ Claude receives the NORMALIZED result as the tool_result             │  → log: tool_result
          │   │ ... final text, stop_reason = end_turn                                      │  → log: text, stop_reason
          │   └─────────────────────────────────────────────────────────────────────────────┘
          │
          ├─ log_model_io(message)
          ├─ tool_use / tool_result → run["tool_calls"], run["tool_results"]
          └─ ResultMessage success + end_turn → run["answer"] = message.result
```

In the `baseline` run, `hooks=None`, so the hook step is absent and Claude receives the handler's raw output.

### 3.2 Messages your `async for` receives (run `normalized`, real output)

The values below come from the real run on 2026-11-13, recorded in `logs/poc1_normalize_test_20261113_205318.log`. Each log line comes from one statement in the code:

| Log line tag | Message class yielded by `query()` | Field logged | Written by |
|--------------|------------------------------------|--------------|------------|
| `MODEL INPUT   prompt` | *(none: the `user_prompt` passed to `run_agent()`)* | `user_prompt` | `log.info("MODEL INPUT   prompt ...")` in `run_agent()` (`hooks_setup.py`) |
| `MODEL OUTPUT  thinking` | `AssistantMessage` → `ThinkingBlock` | `block.thinking`, only when non-empty | `log_model_io()` (`common.py`) |
| `MODEL OUTPUT  text` | `AssistantMessage` → `TextBlock` | `block.text` | `log_model_io()` |
| `MODEL OUTPUT  tool_use` | `AssistantMessage` → `ToolUseBlock` | `block.name`, `block.input`, `block.id` | `log_model_io()` |
| `MODEL INPUT   tool_result` | `UserMessage` → `ToolResultBlock` | `block.content`, `block.tool_use_id`, `block.is_error`: **after** any `PostToolUse` rewrite | `log_model_io()` |
| `MODEL OUTPUT  stop_reason` | `ResultMessage` | `message.stop_reason`, `message.subtype` | `log_model_io()` |
| `Run '...': summary {...} -> ...` | *(none: Python checks the answer)* | `parse_summary(run["answer"])` vs `TRUTH` | `log.info(...)` in `main()` (`poc1_normalize_test.py`) |
| `Safety cap hit: ...`, `The run failed: ...`, `SDK error: ...` | *(none)* | the exception | `run_agent()` and `main()`. None in this log |

Hooks write no log line. A `tool_result` line is what Claude received, so in the `normalized` run it shows the hook's output, never the handler's.

The `normalized` run as it really streamed:

```
20:53:31  (input)                                                              log: prompt
            prompt = Customer CUST-3318 has one order in each of our order systems A, B and C. List the
                       three orders oldest first, quoting each order's date and status exactly as the
                       tools give them. End with one line in exactly this form: ORDERS: <order ids,
                       oldest first> | PENDING: <ids of pending orders, or none>

20:53:34  AssistantMessage › ToolUseBlock                                      log: tool_use
            name = "mcp__orders__system_a", input = {'customer_id': 'CUST-3318'}
            id   = "toolu_01Qx5EMwWRREYucms41Xj68Q"
          (handler returned order_date 1776686400, status 2 → hook rewrote them)
20:53:34  UserMessage › ToolResultBlock                                        log: tool_result
            content = [{'type': 'text', 'text': '{"system": "A", "orders": [{"order_id": "LS-1042",
                        "item": "Cedar desk organizer", "order_date": "2026-04-20", "status": "shipped"}]}'}]
            tool_use_id = "toolu_01Qx5EMwWRREYucms41Xj68Q", is_error = None

20:53:34  AssistantMessage › ToolUseBlock                                      log: tool_use
            name = "mcp__orders__system_b", input = {'customer_id': 'CUST-3318'}
            id   = "toolu_01USSoLpEERbiigdJPgK73iG"
20:53:34  AssistantMessage › ToolUseBlock                                      log: tool_use
            name = "mcp__orders__system_c", input = {'customer_id': 'CUST-3318'}
            id   = "toolu_0191vEKZ4avNAWdgxNhBLVU2"                           ← B and C sent together
20:53:34  UserMessage › ToolResultBlock                                        log: tool_result
            content = [{'type': 'text', 'text': '{"system": "B", "orders": [{"order_id": "LS-2087", ...,
                        "order_date": "2026-04-28", "status": "delivered"}]}'}]  ← already ISO: unchanged values
20:53:34  UserMessage › ToolResultBlock                                        log: tool_result
            content = [{'type': 'text', 'text': '{"system": "C", "orders": [{"order_id": "LS-3150", ...,
                        "order_date": "2026-05-04", "status": "pending"}]}'}]  ← was "04/05/2026", "P"

20:53:37  AssistantMessage › TextBlock                                         log: text
            text = Here are the three orders for CUST-3318, oldest first: 1. LS-1042 ... 2026-04-20 ...
                   "shipped" ... 2. LS-2087 ... 2026-04-28 ... "delivered" ... 3. LS-3150 ... 2026-05-04
                   ... "pending" ... ORDERS: LS-1042, LS-2087, LS-3150 | PENDING: LS-3150
20:53:37  ResultMessage                                                        log: stop_reason
            stop_reason = "end_turn", subtype = "success"

20:53:38  Run 'normalized': summary {...} -> matches the truth                  ← main()
```

What to notice in the real data:
- **The log shows what Claude received.** System A's `tool_result` says `"2026-04-20"` and `"shipped"`, although the handler returns `1776686400` and `2` (compare the `baseline` run). The rewrite happened between the handler and Claude, and left no line of its own.
- **Every system came out in one format.** All three dates are ISO 8601; all three statuses are English words. System B's values were already in that form and passed through unchanged.
- **`tool_use_id` pairing.** Each result's `tool_use_id` matches its call's `id`. The hook replaced the content, not the pairing.
- **Two calls in one response.** `system_b` and `system_c` were both logged before either result, so Claude sent them together. `system_a` went first, on its own.
- **No reasoning needed.** This run has no `thinking` line and a short answer; the `baseline` run spent a thinking block on decoding the epoch and the ambiguous date.
- **Not shown:** the `SystemMessage`, cost and `num_turns` are in the stream; `run_agent()` keeps `num_turns` in its result, but nothing logs it.

> The `UserMessage` items are **not** typed by a human. They carry the tool results, here as rewritten by your hook.

---

## 4. Code walkthrough

The snippets follow the order in which the code runs: the script first, then the module functions it calls. Where a snippet writes log lines, they're shown under it, copied from the real log (long values trimmed with `...`).

### 4.1 Module docstring: three formats, one hook

```python
"""
POC 1 - Normalizing tool results with a PostToolUse hook
=========================================================
Three order systems answer the same question in three formats:

    A: 1776686400, status 2      B: "2026-04-28", "delivered"      C: "04/05/2026", "P"

A PostToolUse hook runs AFTER a handler returns and BEFORE Claude sees the result, and replaces the result
(updatedToolOutput) with ISO 8601 dates and English statuses. Compare the two runs' tool_result lines:

    baseline:    MODEL INPUT   tool_result  ... "order_date": "04/05/2026", "status": "P" ...
    normalized:  MODEL INPUT   tool_result  ... "order_date": "2026-05-04", "status": "pending" ...

Besides model I/O, the log shows one line per run: Claude's ORDERS summary checked against the truth.

Run:  python poc1_normalize_test.py     (2 short API runs)
"""
```

**Why it matters:** the docstring names the hook's position (after the handler, before Claude) and tells you exactly which two log lines to compare. The real log has both: `"04/05/2026", "status": "P"` at 20:53:22 and `"2026-05-04", "status": "pending"` at 20:53:34.

---

### 4.2 Imports

```python
import asyncio
import json
import re
import sys
from datetime import date, datetime, timezone
from typing import Any

from claude_agent_sdk import ClaudeSDKError, HookMatcher

from common import load_settings, log, setup_logging
from hooks_setup import HookState, build_hook_options, response_text, run_agent
```

| Import | What it brings in | Why this file needs it |
| --- | --- | --- |
| `json`, `re` | JSON and regular expressions | Parse and rebuild the tool's JSON; spot `DD/MM/YYYY`; read the summary line |
| `date`, `datetime`, `timezone` | Date handling | Convert epochs (in UTC) and day-first dates to ISO 8601 |
| `ClaudeSDKError` | The SDK's base error | Stops the script on an SDK runtime failure |
| `HookMatcher` | From the SDK | Registers a hook callback for the tools whose names match a pattern |
| `HookState` | From `hooks_setup` | The per-run state (here only the call counter is used) |
| `build_hook_options` | From `hooks_setup` | Options with or without hooks |
| `response_text` | From `hooks_setup` | Gets the text out of a `tool_response` of any shape |
| `run_agent` | From `hooks_setup` | Streams one request and returns the answer |

---

### 4.3 The normalization rules

```python
NUMERIC_STATUS = {0: "pending", 1: "processed", 2: "shipped", 3: "delivered", 9: "cancelled"}  # system A's codes
LETTER_STATUS = {"P": "pending", "R": "processed", "S": "shipped", "D": "delivered", "C": "cancelled"}  # system C's


def to_iso(value: int | str) -> str:
    if isinstance(value, int):  # A: Unix seconds. Pin UTC: in local time the same instant can be another day
        return datetime.fromtimestamp(value, tz=timezone.utc).date().isoformat()
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):  # C: DAY first. Read month-first, 04/05 would become April 5
        return datetime.strptime(value, "%d/%m/%Y").date().isoformat()
    return date.fromisoformat(value).isoformat()  # B: already ISO 8601 (raises on anything else)


def to_status(value: int | str) -> str:
    if isinstance(value, int):
        return NUMERIC_STATUS[value]
    return LETTER_STATUS[value] if len(value) == 1 else value.lower()  # "P" is pending, not processed (that's "R")


def normalize_record(record: dict) -> dict:
    return {**record, "order_date": to_iso(record["order_date"]), "status": to_status(record["status"])}
```

| System | Raw date → ISO | Raw status → English | Rule |
|--------|----------------|----------------------|------|
| A | `1776686400` → `2026-04-20` | `2` → `shipped` | epoch seconds in **UTC**; `NUMERIC_STATUS` |
| B | `2026-04-28` → `2026-04-28` | `delivered` → `delivered` | already ISO; lower-cased word |
| C | `04/05/2026` → `2026-05-04` | `P` → `pending` | **day first** (`%d/%m/%Y`); `LETTER_STATUS` |

**Why it matters:**
- **The knowledge lives in code, once.** The meaning of `2`, `P` and `04/05` is a fact about each source system. Code that knows it is right every time; a model guessing it is right only sometimes.
- **The comments name the traps.** Local time can shift an epoch by a day; month-first reading turns 4 May into 5 April; `P` is pending, not processed (`R`).
- **Unknown input fails loudly.** `date.fromisoformat()` raises on an unexpected format, and a missing code raises `KeyError`. `normalize_output()` catches both and leaves the result untouched rather than half-rewritten.

**Agentic concept:** deterministic data normalization at the boundary between tools and the model.

---

### 4.4 `same_shape()` and `normalize_output()`: the hook

```python
def same_shape(tool_response: Any, text: str) -> Any:
    """updatedToolOutput must have the shape of the tool's output, and MCP output isn't validated (E3)."""
    if isinstance(tool_response, dict):
        return {**tool_response, "content": [{"type": "text", "text": text}]}
    if isinstance(tool_response, list):
        return [{"type": "text", "text": text}]
    return text


async def normalize_output(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
    """PostToolUse: the handler has run (tool_response exists) and Claude hasn't seen the result yet (C3, C4)."""
    tool_response = input_data["tool_response"]
    try:
        data = json.loads(response_text(tool_response))
        data["orders"] = [normalize_record(record) for record in data["orders"]]
    except (ValueError, KeyError, TypeError):  # not an order list: leave the result alone
        return {}
    # updatedToolOutput goes INSIDE hookSpecificOutput, never at the top level (C6)
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                   "updatedToolOutput": same_shape(tool_response, json.dumps(data))}}
```

| Part | What it does | Agentic concept |
|------|--------------|-----------------|
| Signature `(input_data, tool_use_id, context)` | The SDK's hook callback signature; `async` | A hook is your code, called by the SDK at a fixed point |
| `input_data["tool_response"]` | The handler's result: exists only in `PostToolUse` | Post-execution interception |
| `response_text(tool_response)` | Text out of a string, a block list, or a dict with `content` | `tool_response` has no fixed shape (E3) |
| `return {}` on any parse error | Change nothing | A hook must never break a result it doesn't understand |
| `hookSpecificOutput` → `updatedToolOutput` | The replacement result | The code's comment: it goes inside `hookSpecificOutput`, never at the top level |
| `hookEventName: "PostToolUse"` | Names the event the output is for | Part of the hook output contract |
| `same_shape(...)` | Keeps the tool's output shape, swaps only the text | The SDK doesn't validate an MCP tool's replacement output, so you must |

**Why it matters:**
- **It runs for every matched call, and Claude can't skip it.** It isn't an instruction; it's code on the path between the handler and the model.
- **It doesn't touch the handler.** The order systems still return raw formats. The fix sits in one place, for all tools, without changing any source system.
- **Safe failure.** A result that isn't an order list comes back unchanged.

---

### 4.5 `NORMALIZE_HOOKS`: registering the hook

```python
# PostToolUse, not PreToolUse: a PreToolUse hook runs before the handler, so there is no result yet to rewrite;
# it only sees tool_input (C7). "mcp__orders__.*" is a regex: every tool of the orders server.
NORMALIZE_HOOKS = {"PostToolUse": [HookMatcher(matcher="mcp__orders__.*", hooks=[normalize_output])]}
```

**Why it matters:**
- **The event decides what the hook can see.** `PreToolUse` gets `tool_input` before the handler runs; `PostToolUse` gets `tool_response` after. Normalizing a result can only happen in `PostToolUse`.
- **The matcher names the full MCP tool names.** `mcp__orders__.*` matches `mcp__orders__system_a`, `_b` and `_c`. A bare `system_a` would match nothing, because MCP tools are named `mcp__<server>__<tool>`.
- **One matcher, every tool.** Adding a system D to the server would be normalized too, as long as its result has an `orders` list.

**Agentic concept:** the hook direction rule: `PostToolUse` transforms data after execution; `PreToolUse` decides before execution.

---

### 4.6 The test prompt, the truth and the run table

```python
TEST_PROMPT = (
    "Customer CUST-3318 has one order in each of our order systems A, B and C. List the three orders oldest first, "
    "quoting each order's date and status exactly as the tools give them. End with one line in exactly this form: "
    "ORDERS: <order ids, oldest first> | PENDING: <ids of pending orders, or none>"
)
TRUTH = {"orders": ["LS-1042", "LS-2087", "LS-3150"], "pending": ["LS-3150"]}

RUNS = [  # (name, hooks)
    ("baseline", None),  # Claude decodes 3 date formats and 3 status forms itself (C2)
    ("normalized", NORMALIZE_HOOKS),  # Claude only ever sees ISO dates and English statuses (C10)
]
```

**Why it matters:**
- **The question needs all three tools** and depends on exactly the two things the formats disagree on: dates (for the order) and statuses (for the pending list).
- **"quoting ... exactly as the tools give them"** makes the answer show what Claude received: raw values in the baseline, normalized ones with the hook.
- **`TRUTH`** is the correct answer: 20 April (A), 28 April (B), 4 May (C); only C is pending.
- **The machine-readable last line** lets Python check the answer instead of a person.

---

### 4.7 `parse_summary()` and `main()`

```python
def parse_summary(answer: str) -> dict | None:
    """The ORDERS line Claude was asked to end with, as {"orders": [...], "pending": [...]} (C9)."""
    lines = [line for line in answer.splitlines() if "ORDERS:" in line and "PENDING:" in line]
    if not lines:
        return None
    orders_part, pending_part = lines[-1].split("PENDING:", 1)
    return {"orders": re.findall(r"LS-\d{4}", orders_part), "pending": re.findall(r"LS-\d{4}", pending_part)}


async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc1_normalize_test")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    for name, hooks in RUNS:
        try:
            run = await run_agent(TEST_PROMPT, build_hook_options(settings, HookState(), "orders", hooks))
        except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
            log.error("SDK error: %s", exc)
            return 1
        summary = parse_summary(run["answer"] or "")
        log.info("Run '%s': summary %s -> %s", name, summary, "matches the truth" if summary == TRUTH else f"WRONG, truth is {TRUTH}")
    return 0
```

**Why it matters:**
- `parse_summary()` takes the **last** line with both markers, and pulls order IDs with a regex. Extra prose in the answer doesn't matter.
- `main()` builds fresh options per run (`HookState()` and a new tool server), so the runs share nothing but the prompt.
- The result line compares the parsed summary with `TRUTH` and prints `matches the truth` or `WRONG, truth is ...`.

The two lines it wrote:

```
20:53:31  Run 'baseline': summary {'orders': ['LS-3150', 'LS-1042', 'LS-2087'], 'pending': ['LS-3150']} -> WRONG, truth is {'orders': ['LS-1042', 'LS-2087', 'LS-3150'], 'pending': ['LS-3150']}
20:53:38  Run 'normalized': summary {'orders': ['LS-1042', 'LS-2087', 'LS-3150'], 'pending': ['LS-3150']} -> matches the truth
```

The baseline's order is exactly the month-first misread the README predicts: `LS-3150, LS-1042, LS-2087`. Its pending list happened to be right. No `SDK error:` line, so `main()` returned `0`.

---

### 4.8 `__main__`

```python
if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

---

### 4.9 The three order systems (from `hooks_setup.py`)

```python
ORDERS = {  # customer CUST-3318 has one order in each system. Same keys everywhere; only the VALUE FORMATS differ
    "a": {"name": "A (the legacy warehouse system)",  # Unix seconds, numeric status codes
          "orders": [{"order_id": "LS-1042", "item": "Cedar desk organizer", "order_date": 1776686400, "status": 2}]},
    "b": {"name": "B (the web store)",  # ISO 8601 dates, status words
          "orders": [{"order_id": "LS-2087", "item": "Linen throw blanket", "order_date": "2026-04-28", "status": "delivered"}]},
    "c": {"name": "C (the partner marketplace)",  # DD/MM/YYYY dates, one-letter status codes
          "orders": [{"order_id": "LS-3150", "item": "Copper pour-over kettle", "order_date": "04/05/2026", "status": "P"}]},
}


def build_orders_server(state: HookState) -> Any:
    def order_system(system: str) -> Any:  # the description names the system but not its formats, like many legacy APIs
        @tool(f"system_{system}", f"Order system {ORDERS[system]['name']}: returns a customer's orders as JSON.",
              CUSTOMER_SCHEMA, annotations=ToolAnnotations(readOnlyHint=True))
        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            state.calls[f"system_{system}"] += 1
            orders = ORDERS[system]["orders"] if args.get("customer_id") == "CUST-3318" else []
            return text_result(json.dumps({"system": system.upper(), "orders": orders}))
        return handler

    return create_sdk_mcp_server(name="orders", version="1.0.0", tools=[order_system(s) for s in ORDERS])
```

**Why it matters:**
- **Same keys, different value formats.** That isolates the problem to interpretation: Claude always finds `order_date` and `status`, but must decode them.
- **The descriptions don't explain the formats,** "like many legacy APIs". The model has no documentation to lean on.
- **A factory makes three tools from one handler,** each named `system_a`, `system_b`, `system_c` on the `orders` server, so their full names are `mcp__orders__system_a` and so on.
- `readOnlyHint=True`: lookups only. `state.calls` counts handler runs (used by POC 2's checks; POC 1 doesn't log it).

**Agentic concept:** heterogeneous tool outputs; the exam's "data format chaos".

---

### 4.10 `build_hook_options()`: where hooks plug in (from `hooks_setup.py`)

```python
def build_hook_options(settings: Settings, state: HookState, server: str, hooks: dict | None = None) -> ClaudeAgentOptions:
    build_server, tool_names = {"orders": (build_orders_server, ORDER_TOOLS),
                                "payments": (build_payments_server, PAYMENT_TOOLS)}[server]
    return ClaudeAgentOptions(
        model=settings.model_id,
        system_prompt=SYSTEM_PROMPTS[server],  # without one, the SDK sends an empty system prompt
        mcp_servers={server: build_server(state)},  # fresh tools bound to this run's state
        tools=[],  # remove ALL built-in tools: Claude can use only ours
        allowed_tools=tool_names,  # pre-approve every tool, so only a hook can block one (E1)
        hooks=hooks,  # {"PreToolUse": [...], "PostToolUse": [...]}; None = no hooks (the baseline)
        setting_sources=[],  # ignore settings files and their shell hooks; our callback hooks still run
        env={"ENABLE_TOOL_SEARCH": "false"},  # send all tool schemas up front: no ToolSearch calls
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=settings.max_turns,  # safety cap (01 C16); a normal run needs far fewer
        max_budget_usd=settings.max_budget_usd,  # cost guard per run
    )
```

| Option | What it does here | Agentic concept |
|--------|-------------------|-----------------|
| `hooks=hooks` | `None` for the baseline; `NORMALIZE_HOOKS` for the normalized run | Hooks are configuration: the same agent with or without them |
| `setting_sources=[]` | Ignores settings files and their shell hooks; callback hooks in `hooks=` still run | Only the hooks you pass in code apply |
| `system_prompt` | `SYSTEM_PROMPTS["orders"]`: "never guess an order, a date or a status" | No format hints in the prompt either |
| `mcp_servers`, `tools=[]`, `allowed_tools` | Only the three order tools, pre-approved | Least privilege; no permission prompts |
| `thinking` | Summarized reasoning | The baseline's decoding shows up as a `thinking` line |
| `max_turns`, `max_budget_usd` | Defaults `15` and `0.50` | Runaway and cost guards |

**Why it matters:** the only difference between the two runs is the `hooks` argument. Everything Claude can see except the tool results is identical.

---

### 4.11 `run_agent()` and `response_text()` (from `hooks_setup.py`)

```python
async def run_agent(user_prompt: str, options: ClaudeAgentOptions) -> dict[str, Any]:
    """01's run_agent(), extended with options= and tool_results: what Claude actually received for each call.

    Returns {"answer", "subtype", "stop_reason", "num_turns", "tool_calls", "tool_results"}; each tool_results item
    is {"tool_use_id", "name", "input", "is_error", "text"}.
    """
    log.info("MODEL INPUT   prompt       %s", user_prompt)
    ...
            elif isinstance(message, UserMessage) and isinstance(message.content, list):
                for block in message.content:
                    if isinstance(block, ToolResultBlock):
                        name, tool_input = uses.get(block.tool_use_id, (None, None))
                        run["tool_results"].append({"tool_use_id": block.tool_use_id, "name": name, "input": tool_input,
                                                    "is_error": block.is_error, "text": response_text(block.content)})
            elif isinstance(message, ResultMessage):
                run.update(subtype=message.subtype, stop_reason=message.stop_reason, num_turns=message.num_turns)
                if message.subtype == "success" and message.stop_reason == "end_turn":
                    run["answer"] = message.result
            # No `break`: a few system events can still arrive after the ResultMessage.
    except ResultError as exc:  # raised AFTER the error ResultMessage (already logged)
        if exc.subtype == "error_max_turns":
            log.warning("Safety cap hit: max_turns=%s was used up before Claude finished. No answer.", options.max_turns)
        else:  # e.g. error_max_budget_usd, error_during_execution, an invalid API key
            log.error("The run failed: %s", exc)
    return run
```

**Why it matters:**
- **`tool_results` records what Claude actually received,** taken from the `ToolResultBlock`, so after any `PostToolUse` rewrite. That's the evidence that the hook worked; the handler's raw output is never in it.
- **`answer` is set only on `success` + `end_turn`,** so `parse_summary()` gets `""` for a run that didn't finish.
- **Two failure lines:** a turn-cap warning (`Safety cap hit: ...`) or `The run failed: ...`. Neither appears in this log.

`response_text()` is the shape-tolerant reader both `run_agent()` and the hook use:

```python
def response_text(tool_response: Any) -> str:
    """A tool result's text. Its shape depends on the tool (E3): a string, a list of {"type": "text", ...}
    blocks, or a dict that holds that list under "content"."""
    if isinstance(tool_response, dict):
        tool_response = tool_response.get("content", [])
    if isinstance(tool_response, list):
        return "".join(block.get("text", "") for block in tool_response if isinstance(block, dict))
    return str(tool_response or "")
```

---

### 4.12 `common.py`: settings and a single-agent log

The same file as topic 04: defaults `claude-sonnet-5-5`, `max_turns` `15`, `max_budget_usd` `0.50`; `HH:MM:SS  message` lines on the console and in the file; `log_model_io(message)` without agent tags.

| `log_model_io()` branch | Log line tag | Lines in this log |
|-------------------------|--------------|-------------------|
| `ThinkingBlock` with text | `MODEL OUTPUT  thinking` | 1 (baseline) |
| `TextBlock` | `MODEL OUTPUT  text` | 2, the final answer of each run |
| `ToolUseBlock` | `MODEL OUTPUT  tool_use` | 6: `system_a`, `system_b`, `system_c` per run |
| `ToolResultBlock` | `MODEL INPUT   tool_result` | 6, all `is_error=None` |
| `ResultMessage` | `MODEL OUTPUT  stop_reason` | 2 |

Hooks have no branch here and no logging of their own in POC 1.

---

## 5. Turn-by-turn trace of each run (real output)

Each trace below is the real run from `logs/poc1_normalize_test_20261113_205318.log` (2026-11-13, 20:53:18 to 20:53:38: 20 seconds for both `query()` calls). Each log line points back to the statement that wrote it (section 3.2's table).

How to read the log blocks:
- In the log file, every entry is one line. Here, each entry's header (time, `MODEL INPUT` or `MODEL OUTPUT`, kind) stays on its first line, and its payload is pretty-printed underneath.
- Long text wraps onto a deeper-indented line.
- `...` marks text that was cut.

### 5.1 Run `baseline`: Claude decodes the formats itself

**Real log:**

```
20:53:18  MODEL INPUT   prompt
          Customer CUST-3318 has one order in each of our order systems A, B and C. List the three
            orders oldest first, quoting each order's date and status exactly as the tools give
            them. End with one line in exactly this form: ORDERS: <order ids, oldest first> |
            PENDING: <ids of pending orders, or none>

20:53:22  MODEL OUTPUT  tool_use
          mcp__orders__system_a {'customer_id': 'CUST-3318'}
          (id=toolu_012TBnTVtHK3Mr49z6s2ekPV)
20:53:22  MODEL INPUT   tool_result
          [{'type': 'text', 'text': '{"system": "A", "orders": [{"order_id": "LS-1042",
              "item": "Cedar desk organizer", "order_date": 1776686400, "status": 2}]}'}]
          (tool_use_id=toolu_012TBnTVtHK3Mr49z6s2ekPV, is_error=None)
20:53:22  MODEL OUTPUT  tool_use
          mcp__orders__system_b {'customer_id': 'CUST-3318'}
          (id=toolu_01RHFBqvZrhzJqnU84oqhNti)
20:53:22  MODEL OUTPUT  tool_use
          mcp__orders__system_c {'customer_id': 'CUST-3318'}
          (id=toolu_018hsdtZSFC7z2qb5cfMaDGS)
20:53:22  MODEL INPUT   tool_result
          [{'type': 'text', 'text': '{"system": "B", "orders": [{"order_id": "LS-2087",
              "item": "Linen throw blanket", "order_date": "2026-04-28", "status": "delivered"}]}'}]
          (tool_use_id=toolu_01RHFBqvZrhzJqnU84oqhNti, is_error=None)
20:53:22  MODEL INPUT   tool_result
          [{'type': 'text', 'text': '{"system": "C", "orders": [{"order_id": "LS-3150",
              "item": "Copper pour-over kettle", "order_date": "04/05/2026", "status": "P"}]}'}]
          (tool_use_id=toolu_018hsdtZSFC7z2qb5cfMaDGS, is_error=None)

20:53:30  MODEL OUTPUT  thinking
          I'm converting the epoch timestamp 1776686400 to a readable date: it works out to 109.5
            days after January 1, 2026, which lands on April 20 at 12:00 UTC.

          I'm checking the second date, April 28, 2026. The third one, 04/05/2026, could mean
            April 5 or May 4 depending on whether it's month-first or day-first. I'll need to pick
            one reading and flag the ambiguity.

20:53:30  MODEL OUTPUT  text
          I looked up all three systems. Two things are ambiguous, so the ordering and the PENDING
            list are provisional.

          Oldest first, with dates and statuses as the tools gave them:

          1. **LS-3150** (system C), Copper pour-over kettle: order_date `04/05/2026`, status `P`
          2. **LS-1042** (system A), Cedar desk organizer: order_date `1776686400`, status `2`
             - The date is a Unix timestamp that works out to 2026-04-20 12:00 UTC.
          3. **LS-2087** (system B), Linen throw blanket: order_date `2026-04-28`, status
             `delivered`

          **Caveats**
          - **System C date:** `04/05/2026` could be April 5 (MM/DD) or 4 May (DD/MM). I read it
            as April 5, which puts it first. If it is 4 May, the order becomes LS-1042, LS-2087,
            LS-3150.
          - **Status codes:** The tools don't define A's `2` or C's `P`. I treated `P` as
            "pending", but that's an assumption. I can't tell from the data whether `2` means
            pending.
          - **System B:** `delivered` is clear, so LS-2087 is not pending.

          ORDERS: LS-3150, LS-1042, LS-2087 | PENDING: LS-3150
20:53:30  MODEL OUTPUT  stop_reason  end_turn  (loop result: success)

20:53:31  Run 'baseline': summary {'orders': ['LS-3150', 'LS-1042', 'LS-2087'], 'pending':
            ['LS-3150']} -> WRONG, truth is {'orders': ['LS-1042', 'LS-2087', 'LS-3150'],
            'pending': ['LS-3150']}
```

**What Claude did with each raw value:**

| System | Raw value it received | Claude's reading | Correct reading | Result |
|--------|-----------------------|------------------|-----------------|--------|
| A | `1776686400` | 2026-04-20 12:00 UTC | 2026-04-20 | right (by arithmetic in its thinking) |
| A | `2` | "I can't tell ... whether `2` means pending" | shipped | unknown, left out of PENDING |
| B | `2026-04-28`, `delivered` | as given | as given | right |
| C | `04/05/2026` | April 5 (month first) | 4 May (day first) | **wrong**: LS-3150 moved to first |
| C | `P` | "pending, but that's an assumption" | pending | right, by a guess |

**Variable values:**

| Variable / field | Value |
|------------------|-------|
| `hooks` | `None`: no `PostToolUse` step |
| `run["tool_results"]` | the three raw results, as the handlers returned them |
| `run["answer"]` | the text above (`success` + `end_turn`) |
| `summary` | `{'orders': ['LS-3150', 'LS-1042', 'LS-2087'], 'pending': ['LS-3150']}` |
| `summary == TRUTH` | `False` → `WRONG, truth is ...` |

**Lessons from the real data:**
- **The misread is the exam's example, word for word.** Day-first `04/05/2026` read month-first became April 5, 29 days early, and moved LS-3150 from last to first.
- **Claude saw the ambiguity and still had to choose.** Its thinking says "pick one reading and flag the ambiguity", and its answer carries caveats. A careful model can't resolve an ambiguity the data doesn't resolve.
- **One right answer was a lucky guess.** `P` → pending was correct, but Claude called it "an assumption". It couldn't decode `2` at all.
- **Decoding cost effort:** a thinking block with date arithmetic, and a 12-second run (vs 6 s with the hook).

### 5.2 Run `normalized`: the hook rewrites, Claude just reads

**Real log:**

```
20:53:31  MODEL INPUT   prompt
          Customer CUST-3318 has one order in each of our order systems A, B and C. List the three
            orders oldest first, ... ORDERS: <order ids, oldest first> | PENDING: <ids of pending
            orders, or none>

20:53:34  MODEL OUTPUT  tool_use
          mcp__orders__system_a {'customer_id': 'CUST-3318'}
          (id=toolu_01Qx5EMwWRREYucms41Xj68Q)
20:53:34  MODEL INPUT   tool_result
          [{'type': 'text', 'text': '{"system": "A", "orders": [{"order_id": "LS-1042",
              "item": "Cedar desk organizer", "order_date": "2026-04-20", "status": "shipped"}]}'}]
          (tool_use_id=toolu_01Qx5EMwWRREYucms41Xj68Q, is_error=None)
20:53:34  MODEL OUTPUT  tool_use
          mcp__orders__system_b {'customer_id': 'CUST-3318'}
          (id=toolu_01USSoLpEERbiigdJPgK73iG)
20:53:34  MODEL OUTPUT  tool_use
          mcp__orders__system_c {'customer_id': 'CUST-3318'}
          (id=toolu_0191vEKZ4avNAWdgxNhBLVU2)
20:53:34  MODEL INPUT   tool_result
          [{'type': 'text', 'text': '{"system": "B", "orders": [{"order_id": "LS-2087",
              "item": "Linen throw blanket", "order_date": "2026-04-28", "status": "delivered"}]}'}]
          (tool_use_id=toolu_01USSoLpEERbiigdJPgK73iG, is_error=None)
20:53:34  MODEL INPUT   tool_result
          [{'type': 'text', 'text': '{"system": "C", "orders": [{"order_id": "LS-3150",
              "item": "Copper pour-over kettle", "order_date": "2026-05-04", "status": "pending"}]}'}]
          (tool_use_id=toolu_0191vEKZ4avNAWdgxNhBLVU2, is_error=None)

20:53:37  MODEL OUTPUT  text
          Here are the three orders for CUST-3318, oldest first:

          1. **LS-1042** (system A), Cedar desk organizer. The order date is 2026-04-20 and the
             status is "shipped".
          2. **LS-2087** (system B), Linen throw blanket. The order date is 2026-04-28 and the
             status is "delivered".
          3. **LS-3150** (system C), Copper pour-over kettle. The order date is 2026-05-04 and the
             status is "pending".

          ORDERS: LS-1042, LS-2087, LS-3150 | PENDING: LS-3150
20:53:37  MODEL OUTPUT  stop_reason  end_turn  (loop result: success)

20:53:38  Run 'normalized': summary {'orders': ['LS-1042', 'LS-2087', 'LS-3150'], 'pending':
            ['LS-3150']} -> matches the truth
```

**What each step did and which code ran:**

| Step | Claude asked for | Handler returned (not logged) | `normalize_output()` | Claude received (logged) |
|------|------------------|-------------------------------|----------------------|--------------------------|
| 1 | `system_a` | `1776686400`, `2` | `to_iso()` (UTC), `NUMERIC_STATUS` | `2026-04-20`, `shipped` |
| 2 | `system_b` (with step 3, one response) | `2026-04-28`, `delivered` | `date.fromisoformat()`, `.lower()` | `2026-04-28`, `delivered` |
| 3 | `system_c` | `04/05/2026`, `P` | `%d/%m/%Y`, `LETTER_STATUS` | `2026-05-04`, `pending` |
| 4 | *(text)* the answer | | | `end_turn` |

The "handler returned" column comes from the code (`ORDERS` in `hooks_setup.py`) and from the baseline run's log, where the same handlers' output reached Claude unchanged.

**Variable values:**

| Variable / field | Value |
|------------------|-------|
| `hooks` | `NORMALIZE_HOOKS`: one `PostToolUse` matcher, `mcp__orders__.*` |
| `normalize_output()` return | `{"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": ...}}`, three times |
| `run["tool_results"]` | the three normalized results |
| `summary` | `{'orders': ['LS-1042', 'LS-2087', 'LS-3150'], 'pending': ['LS-3150']}` |
| `summary == TRUTH` | `True` → `matches the truth` |

**Lessons from the real data:**
- **Same prompt, same tools, right answer.** The hook is the only difference, and it turned `WRONG` into `matches the truth`.
- **"Exactly as the tools give them" now means ISO and English.** Claude quoted `2026-05-04` and `pending`, because that is what it received. It never saw the raw formats.
- **No ambiguity, no caveats, no thinking.** The answer is shorter and certain, and the run took 6 s instead of 12.
- **The hook worked on every tool.** One regex matcher covered all three systems; system B's already-correct values passed through unchanged.

### 5.3 The two runs side by side

| | `baseline` | `normalized` |
|-|------------|--------------|
| `hooks` | `None` | `{"PostToolUse": [HookMatcher("mcp__orders__.*", [normalize_output])]}` |
| Tool calls | `system_a`, then `system_b` + `system_c` together | the same |
| Dates Claude received | `1776686400`, `2026-04-28`, `04/05/2026` | `2026-04-20`, `2026-04-28`, `2026-05-04` |
| Statuses Claude received | `2`, `delivered`, `P` | `shipped`, `delivered`, `pending` |
| `thinking` lines | 1 (decoding) | 0 |
| ORDERS line | `LS-3150, LS-1042, LS-2087` | `LS-1042, LS-2087, LS-3150` |
| PENDING line | `LS-3150` (a guess) | `LS-3150` |
| Result line | `WRONG` | `matches the truth` |
| Final `subtype` / `stop_reason` | `success` / `end_turn` | `success` / `end_turn` |
| Wall time (from log) | about 12 s | about 6 s |

The log has no `SDK error:`, `Safety cap hit:` or `The run failed:` line, so `main()` returned `0`.

---

## 6. Agentic AI concepts recap

| Concept | How this POC shows it |
|---------|-----------------------|
| **Agent SDK hooks** | Your callbacks, run by the SDK at fixed points of every tool call; the model can't skip them. |
| **`PostToolUse`** | Runs after the handler, before Claude: sees `tool_response`, can replace it. |
| **`updatedToolOutput` in `hookSpecificOutput`** | The return value of `normalize_output()`; shape kept by `same_shape()`. |
| **Hook direction** | `PostToolUse` for transforming results; `PreToolUse` only sees `tool_input` (POC 2 uses it for policy). |
| **Matchers on full MCP names** | `mcp__orders__.*`: a regex over `mcp__<server>__<tool>`. |
| **Data format chaos** | Epoch + codes, ISO + words, `DD/MM/YYYY` + letters: `ORDERS` in `hooks_setup.py`. |
| **Deterministic normalization** | `to_iso()`, `to_status()`: the meaning of each format lives in code, once. |
| **Fail safe** | `return {}` when a result isn't an order list: no half-rewritten output. |
| **Evidence in the stream** | `tool_result` lines and `run["tool_results"]` hold what Claude received, after the hook. |
| **Verify against the truth** | `parse_summary()` vs `TRUTH`: `WRONG` without the hook, `matches the truth` with it. |

---

## 7. Common mistakes this POC helps you avoid

1. **Letting the model decode inconsistent formats.** It will guess, sometimes wrong: `04/05/2026` became April 5.
2. **Fixing formats with prompt instructions.** "Dates from system C are day-first" helps most of the time; a hook converts every time.
3. **Normalizing in `PreToolUse`.** There is no result yet; `PreToolUse` sees only `tool_input`.
4. **Returning `updatedToolOutput` at the top level of the hook output.** It belongs inside `hookSpecificOutput`, with `hookEventName`.
5. **Changing the output's shape.** Keep the tool's structure (`same_shape()`); MCP tool output isn't validated for you.
6. **A matcher with the bare tool name.** MCP tools are `mcp__<server>__<tool>`; `system_a` alone matches nothing.
7. **Converting epochs in local time.** The same instant can be another day; pin UTC.
8. **A hook that breaks results it doesn't understand.** Catch parse errors and return `{}`.
9. **Checking the answer by eye.** Ask for a machine-readable line and compare it with the truth in code.

---

## 8. Claude Architect exam lens

### 8.1 What the exam tests on this topic

The objectives come from `curriculum/01-Agentic-Architecture-&-Orchestration/05-raw-Agent-SDK-Hooks.md`. POC 1 covers objectives 1 to 3; POC 2 covers the `PreToolUse` policy hooks (4 to 6).

| Exam objective | What a correct answer looks like | Where this POC shows it |
|----------------|----------------------------------|-------------------------|
| 1. Three MCP tools with different formats | Tool A: Unix timestamps and numeric status codes. Tool B: ISO 8601 and English statuses. Tool C: `DD/MM/YYYY` and one-letter codes. Without normalization the model must interpret all three, inconsistently. | `ORDERS` and `build_orders_server()` in `hooks_setup.py`; run `baseline` |
| 2. A `PostToolUse` hook that normalizes every result | A callback registered under `PostToolUse` reads `tool_response`, converts dates to ISO 8601 and codes to English, and returns the rewrite as `updatedToolOutput` inside `hookSpecificOutput`. `PostToolUse` runs after execution, before the model: the right direction for data. | `normalize_output()`, `NORMALIZE_HOOKS`, `to_iso()`, `to_status()` |
| 3. Verify with queries that need all three tools | All three results use ISO dates and English statuses, whichever tool produced them; the model's answer uses them consistently. Without it, day/month confusion and `P` read as "processed" are the classic errors. | `TEST_PROMPT`, `TRUTH`, `parse_summary()`; run `normalized`: `matches the truth`; run `baseline`: the day/month misread |
| 4–6. `PreToolUse` policy hooks | Deny before execution; never block in `PostToolUse` | POC 2 |

> **Exam tip:** the exam pairs the two hook directions with two jobs. **Transforming data** a tool returned → `PostToolUse` (after execution, before the model). **Blocking an action** → `PreToolUse` (before execution). An answer that "blocks a refund in `PostToolUse`" or "normalizes the result in `PreToolUse`" is wrong in the direction.

### 8.2 The same normalization with the raw Messages API

The raw Messages API has no hooks. Your code runs the tools and builds each `tool_result`, so the normalization goes there: after the tool returns, before the result goes into `messages`.

```python
import json

import anthropic

client = anthropic.Anthropic()
# ORDER_TOOLS (the three tool schemas), call_order_system() and normalize_record() are as in the POC.


def tool_result_for(block) -> dict:
    raw = call_order_system(block.name, block.input)  # the source system's own format
    data = json.loads(raw)
    data["orders"] = [normalize_record(record) for record in data["orders"]]  # the "PostToolUse" step
    return {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(data)}
```

The loop around it is topic 01's: call `client.messages.create(..., tools=ORDER_TOOLS)`, build a `tool_result` for each `tool_use` block with `tool_result_for()`, and send them back in one user message.

| Raw Messages API (you write it) | Agent SDK (`poc1_normalize_test.py`) |
|---------------------------------|--------------------------------------|
| You call the tool and get its raw output | The SDK calls your `@tool` handler |
| You normalize before building the `tool_result` | A `PostToolUse` hook returns `updatedToolOutput` |
| Your normalization runs because your loop calls it | The SDK runs every hook whose matcher fits the tool name |
| One function wraps all tools, if you route them through it | One `HookMatcher` regex (`mcp__orders__.*`) covers all tools on the server |
| No hook output contract | `{"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": ...}}` |

In both forms the model only ever sees the normalized data.

### 8.3 Scenario questions

Try each one before reading the answer. These questions were written for this article to match the curriculum objectives above. They are not official exam questions.

---

**Scenario 1: Dates in three formats**

An agent queries three order systems. One returns Unix timestamps, one ISO 8601 dates, one `DD/MM/YYYY`. The agent sometimes lists orders in the wrong sequence. What is the most reliable fix with the Agent SDK?

- A. Add a paragraph to the system prompt explaining each system's date format.
- B. Register a `PostToolUse` hook that converts every result's dates to ISO 8601 before the model sees them.
- C. Register a `PreToolUse` hook that converts the dates.
- D. Ask the model to double-check its date parsing.

**Answer: B.** A `PostToolUse` hook runs after the tool returns and before the model processes the result, so it can rewrite the data deterministically for every call. A and D stay probabilistic. C is the wrong direction: before execution there is no result. *POC link:* `NORMALIZE_HOOKS` and `to_iso()`; run `baseline` misread `04/05/2026`, run `normalized` got `2026-05-04`.

---

**Scenario 2: Which hook direction?**

A team wants a hook that rewrites status codes in tool results into English words. A developer registers it under `PreToolUse`. Why doesn't it work?

- A. Hooks can't change status codes.
- B. `PreToolUse` runs before the tool executes and only sees the tool's input; there is no result to rewrite yet. It belongs in `PostToolUse`.
- C. The matcher is wrong.
- D. `PreToolUse` hooks only run for built-in tools.

**Answer: B.** Hook direction follows the data: input before execution, output after. *POC link:* the comment above `NORMALIZE_HOOKS`: "a PreToolUse hook runs before the handler, so there is no result yet to rewrite; it only sees tool_input".

---

**Scenario 3: Returning the rewrite**

A `PostToolUse` hook computes a normalized result, but the model still sees the raw values. The hook returns `{"updatedToolOutput": normalized}`. What is wrong?

- A. The hook must return `None`.
- B. `updatedToolOutput` must be inside `hookSpecificOutput`, with `hookEventName: "PostToolUse"`.
- C. The hook must modify `input_data` in place.
- D. The hook must raise an exception to apply changes.

**Answer: B.** The hook output contract puts the replacement under `hookSpecificOutput`. *POC link:* `normalize_output()` returns `{"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": ...}}`, with the comment "never at the top level".

---

**Scenario 4: The hook that never fires**

A `PostToolUse` hook is registered with `HookMatcher(matcher="system_a", ...)` for an MCP tool on a server named `orders`. It never runs. Why?

- A. MCP tools don't support hooks.
- B. MCP tool names are `mcp__<server>__<tool>`, so the matcher must match `mcp__orders__system_a` (for example `mcp__orders__.*` for every tool on the server).
- C. Matchers are case-sensitive and must be upper case.
- D. Hooks need `setting_sources` to be set.

**Answer: B.** The matcher is tested against the full tool name. *POC link:* `HookMatcher(matcher="mcp__orders__.*", hooks=[normalize_output])`, with the comment "a regex: every tool of the orders server". D is wrong too: `build_hook_options()` sets `setting_sources=[]` and the callback hooks still run.

---

**Scenario 5: "P" for processed?**

An order tool returns a one-letter status `P`. In testing, the agent sometimes tells customers their order is "processed" when it's actually pending. What is the best fix?

- A. Tell the model that `P` means pending.
- B. Map the codes to English words in a `PostToolUse` hook, so the model receives `"pending"`.
- C. Remove the status from the tool's output.
- D. Ask customers to check the status themselves.

**Answer: B.** The meaning of a code is a fact about the source system; encode it once, in code, on every result. A works most of the time; C loses information. *POC link:* `LETTER_STATUS` and `to_status()`, with the comment `"P" is pending, not processed (that's "R")`; in the baseline Claude called its `P` → pending reading "an assumption".

---

**Scenario 6: Proving the hook works**

How should a team verify that a normalization hook works across all its tools?

- A. Read the hook's code carefully.
- B. Ask a question that needs every tool's data, check that every tool result the model received uses the target formats, and compare the model's answer with a known truth, with and without the hook.
- C. Check that the hook function was imported.
- D. Ask the model whether the data looked consistent.

**Answer: B.** Test across all tools, look at what the model actually received, and check the outcome. *POC link:* `TEST_PROMPT` needs all three systems; the `tool_result` lines show the received data; `parse_summary()` vs `TRUTH` gives `WRONG` vs `matches the truth`.

---

**Scenario 7: A result the hook doesn't understand**

A normalization hook is registered for all tools on a server. One tool returns an error message instead of the usual JSON. What should the hook do?

- A. Raise an exception so the run stops.
- B. Return nothing to change (an empty output), so the original result reaches the model unchanged.
- C. Replace the result with an empty order list.
- D. Retry the tool.

**Answer: B.** A hook must not break or invent data it can't parse. C would hide the error from the model. *POC link:* `except (ValueError, KeyError, TypeError): return {}` in `normalize_output()`.

---

**Scenario 8: Off by one day**

A hook converts Unix timestamps to dates with the server's local time zone. Orders placed late in the day sometimes show the next day's date. What is the fix?

- A. Round timestamps to the nearest hour.
- B. Convert epochs in a fixed time zone (UTC), since the same instant can fall on different days in different zones.
- C. Let the model convert timestamps instead.
- D. Store dates as strings in the source system.

**Answer: B.** Pin the time zone in the conversion. *POC link:* `to_iso()`: `datetime.fromtimestamp(value, tz=timezone.utc)`, with the comment "Pin UTC: in local time the same instant can be another day".

---

### 8.4 Quick-recall cheat sheet

```
hooks                  → your callbacks; the SDK runs them on every matching tool call; the model can't skip them
PostToolUse            → after the handler, before the model: sees tool_response, can REPLACE it
PreToolUse             → before the handler: sees tool_input only; for policy (POC 2), not for data
replace a result       → {"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": ...}}
keep the shape         → same structure as the tool's output; MCP output isn't validated for you
matcher                → regex over the FULL name: mcp__<server>__<tool>  (e.g. mcp__orders__.*)
normalize              → dates → ISO 8601 (epochs in UTC, DD/MM/YYYY day first); codes → English words
format chaos           → 04/05/2026 read month-first = April 5 instead of 4 May; P ≠ processed
fail safe              → can't parse the result? return {} and leave it alone
evidence               → the tool_result Claude received (log, run["tool_results"]) shows the rewrite
verify                 → a query needing all tools + a machine-checkable answer vs the truth
```

---

## 9. How to run it

```bash
cd 01-Agentic-Architecture-Orchestration/05-Agent-SDK-Hooks
source .venv/bin/activate        # the folder's venv (claude-agent-sdk 0.2.181)
python poc1_normalize_test.py    # paid: 2 short runs, 2 query() calls, uses ANTHROPIC_API_KEY from .env
python poc2_policy_test.py       # paid: POC 2, PreToolUse policy hooks
```

- Both scripts call the API. This folder has no free offline demo.
- `.env` needs `ANTHROPIC_API_KEY`; copy `.env.example` and fill it in. `MODEL_ID`, `MAX_TURNS` and `MAX_BUDGET_USD` fall back to `claude-sonnet-5-5`, `15` and `0.50`.
- Every model input and output, plus one result line per run, goes to the console and to `logs/poc1_normalize_test_<date>_<time>.log`. The baseline may or may not misread the dates on a given run; the normalized run should match the truth every time.
- The exit code is `0` when both runs finish. It's `1` on a setup failure or an SDK runtime failure (`ClaudeSDKError`).
