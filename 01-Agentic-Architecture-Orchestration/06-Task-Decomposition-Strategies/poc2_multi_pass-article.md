# POC 2: One File per Pass, Then the Seams

> **File:** `poc2_multi_pass.py` (with `review_setup.py` and `common.py`)
> **Domain:** 01 Agentic Architecture & Orchestration → 06 Task Decomposition Strategies
> **SDK:** Claude Agent SDK for Python (`claude-agent-sdk >=0.2.174,<0.3`; 0.2.181 in the folder's `.venv`)
> **Page:** https://claude.ai/artifact/PydjP7zkna95rzrDrxG9mb

---

## 1. What this POC proves

POC 1 reviewed the whole repo in one request. POC 2 decomposes the same review: one fresh session per file, then one integration session that sees only each file's interface, no code. Same model, same reviewer prompt, same per-file schema; only the structure changes. Every claim below is checked against one real run: `logs/poc2_multi_pass_20261113_214442.log`.

| # | Idea | Where it shows up in the code |
|---|------|------------------------------|
| 1 | **Per-file passes give each file the whole attention budget.** Each call is a new session holding one file. | layer 1 of `multi_pass()`: a loop of `run_review()` calls with `FILE_PROMPT` |
| 2 | **Each per-file review records the file's interface:** what it exports and what it assumes about other files. | `exports` and `uses` in `FILE_REVIEW` |
| 3 | **A per-file pass can never see a two-file bug.** It sees one file. | `FILE_PROMPT`: "You can see only this file." |
| 4 | **An integration pass over the interfaces finds the seams:** data flow, API mismatches, inconsistent patterns. It never sees code. | layer 2 of `multi_pass()`: `INTEGRATION_PROMPT` + the summaries |
| 5 | **Python decides the split** (prompt chaining), so the decomposition is the same on every run. | the `for f in files:` loop, then one integration call |
| 6 | **Same model, better structure, more found.** 16 issues against POC 1's 10, both planted cross-file bugs, and both copies of the duplicated pattern flagged. | the five `log_scores()` lines, compared with POC 1's |

The pattern in one picture:

```
checkout.ts  ──▶ call 1 ──▶ review + interface ─┐
inventory.ts ──▶ call 2 ──▶ review + interface ─┼──▶ call 4: the interfaces only (no code) ──▶ cross-file issues
pricing.ts   ──▶ call 3 ──▶ review + interface ─┘
```

---

## 2. The files involved

```
06-Task-Decomposition-Strategies/
├── .env / .env.example       ← ANTHROPIC_API_KEY, MODEL_ID, MAX_TURNS, MAX_BUDGET_USD
├── requirements.txt          ← claude-agent-sdk >=0.2.174,<0.3 and python-dotenv
├── common.py                 ← Settings, load_settings(), setup_logging(), log_model_io()
├── review_setup.py           ← load_repo(), format_file(), REVIEWER_PROMPT, schemas, options, run_review(), answer key
├── sample_repo/              ← checkout.ts (31 lines), inventory.ts (26), pricing.ts (40), with planted defects
├── poc1_single_pass.py       ← POC 1: every file in one request (not covered here)
├── poc2_multi_pass.py        ← entry point: 3 per-file passes + 1 integration pass
└── logs/
    └── poc2_multi_pass_20261113_214442.log   ← the real run used in sections 3.2 and 5
```

Every snippet in this article is copied from these files, logging statements included. Each logging statement is named with the log line it writes.

The responsibilities split like this:
- `common.py` covers **configuration and observability**.
- `review_setup.py` covers **what both architectures share**: the repo loader, the numbered listing, the reviewer prompt, the schemas, the options, the review call and the answer key.
- `poc2_multi_pass.py` covers **the decomposition**: two prompts, the two-layer pipeline in `multi_pass()`, and the scoring call.

---

## 3. End-to-end execution flow

### 3.1 The big picture

```
python poc2_multi_pass.py
        │
        ▼
asyncio.run(main())                                                      [poc2_multi_pass.py]
        │
        ├─▶ load_settings(), setup_logging("poc2_multi_pass"), files = load_repo()   [common.py, review_setup.py]
        │
        └─▶ reviews, cross_file_issues = multi_pass(settings, files)
               │
               ├─ layer 1: for f in files:                             (checkout.ts, inventory.ts, pricing.ts)
               │     run_review(FILE_PROMPT.format(n=3, listing=format_file(f)),
               │                build_review_options(settings, FILE_REVIEW_SCHEMA))      → query() calls 1-3
               │     None → RuntimeError("no review for <file>")
               │
               ├─ summaries = [{"file", "exports", "uses"} for each review]     no code, no local issues
               │
               └─ layer 2: run_review(INTEGRATION_PROMPT + json.dumps(summaries, indent=2),
                                      build_review_options(settings, INTEGRATION_SCHEMA))     → query() call 4
                     None → RuntimeError("no integration review")
        │
        └─▶ log_scores(reviews, files, cross_file_issues)                  [review_setup.py]  the same lines as POC 1
```

Each `run_review()` call is its own session. The right-hand column names the log line each step writes.

```
run_review(prompt, options)                                                          [review_setup.py]
   │
   ├─ log.info("MODEL INPUT   prompt ...")                                         → log: prompt
   └─▶ async for message in query(prompt=prompt, options=options):
          │
          │   ┌──────────────────────── SDK-owned: one NEW session ─────────────────────────┐
          │   │ empty history; system prompt = REVIEWER_PROMPT; output_format = this schema  │
          │   │ Claude reads only this prompt and calls StructuredOutput                     │  → log: structured
          │   │ the JSON is checked against the schema → accepted                            │  → log: tool_result
          │   │ yields ResultMessage (success, stop_reason = tool_use)                       │  → log: stop_reason
          │   └──────────────────────────────────────────────────────────────────────────────┘
          │
          └─ ResultMessage success → output = message.structured_output
```

### 3.2 Messages your `async for` receives (the integration pass, real output)

The integration pass is the new layer, so it's the one shown in full. The values below come from the real run on 2026-11-13, recorded in `logs/poc2_multi_pass_20261113_214442.log`. Each log line comes from one statement in the code:

| Log line tag | Message class / source | Field logged | Written by |
|--------------|------------------------|--------------|------------|
| `MODEL INPUT   prompt` | *(none: the `prompt` passed to `run_review()`)* | `prompt` | `log.info("MODEL INPUT   prompt ...")` in `run_review()` (`review_setup.py`) |
| `MODEL OUTPUT  structured` | `AssistantMessage` → `ToolUseBlock` named `StructuredOutput` | `block.input`, `block.id` | `log_model_io()` (`common.py`) |
| `MODEL INPUT   tool_result` | `UserMessage` → `ToolResultBlock` | `block.content`, `block.tool_use_id`, `block.is_error` | `log_model_io()` |
| `MODEL OUTPUT  stop_reason` | `ResultMessage` | `message.stop_reason`, `message.subtype` | `log_model_io()` |
| `#n <file>: ...`, `forEach + nested find ...`, `Cross-file issues found: ...` | *(none: Python scores)* | the reviews and the cross-file issues | `log.info(...)` in `log_scores()` (`review_setup.py`) |
| `Run '...' stopped: ...`, `The review failed: ...`, `SDK error: ...` | *(none)* | the failure | `main()` and `run_review()`. None in this log |

Call 4, the integration pass, as it really streamed:

```
21:45:10  (input)                                                              log: prompt
            prompt = These are the per-file summaries of one TypeScript codebase; the code itself is not
                       included. Find cross-file issues only: data flow problems between modules,
                       inconsistent API usage (a caller's assumptions that contradict the callee's
                       contract), and patterns or conventions used differently across files. Name every
                       file each issue involves. Do not repeat single-file issues.

                     [ {"file": "checkout.ts",
                        "exports": [ ...3... ],
                        "uses": ["inventory.reserveStock(...) — ... assumes it throws when stock is
                                  insufficient (and only then), and ignores any return value; ...",
                                 "pricing.orderTotal(...) — ... assumes it returns a finite number in
                                  dollars (not cents) ...", ...]},
                       {"file": "inventory.ts",
                        "exports": ["reserveStock(...): boolean — ... Returns false when stock is short
                                     or the SKU is unknown. It never throws ...", ...],
                        "uses": []},
                       {"file": "pricing.ts",
                        "exports": [..., "orderTotal(...): number - returns total in integer cents; ...", ...],
                        "uses": []} ]                        ← no code: only what layer 1 recorded

21:45:18  AssistantMessage › ToolUseBlock                                      log: structured
            name  = "StructuredOutput"
            input = {'cross_file_issues': [ ...6 issues, see 5.2... ]}
            id    = "toolu_01Rdo3k6Jsv5xkXPVTxeTrs9"
21:45:18  UserMessage › ToolResultBlock                                        log: tool_result
            content = Structured output provided successfully, tool_use_id = "toolu_01Rdo3k6Jsv5xkXPVTxeTrs9"
21:45:18  ResultMessage                                                        log: stop_reason
            stop_reason = "tool_use", subtype = "success"

21:45:19  #1 checkout.ts: 5 issue(s), planted bug flagged: True               ← log_scores()
21:45:19  #2 inventory.ts: 5 issue(s), planted bug flagged: True
21:45:19  #3 pricing.ts: 6 issue(s), planted bug flagged: True
21:45:19  forEach + nested find, identical in both files: {'pricing.ts': True, 'inventory.ts': True} -> consistent
21:45:19  Cross-file issues found: ['cents vs dollars', 'false vs throw'] (2 of 2)
```

What to notice in the real data:
- **The integration pass found the bugs without the code.** `checkout.ts`'s `uses` said "assumes it throws" and "assumes ... dollars (not cents)"; `inventory.ts`'s export said "never throws"; `pricing.ts`'s said "integer cents". Matching assumptions against contracts was enough.
- **Layer 1 set this up honestly.** The `checkout.ts` pass couldn't see `pricing.ts`, and said so: "The unit of orderTotal's result (dollars) is assumed, not verified." That unverified assumption is exactly what layer 2 checked.
- **Four sessions, four answers.** Each call has its own `MODEL INPUT   prompt`, `structured`, `tool_result` and `stop_reason` line: 16 entries in all, plus the five score lines.
- **`success` with `stop_reason = "tool_use"`** every time: each session ends on its accepted `StructuredOutput` call.
- **No thinking and no text lines.** Every model output is structured JSON.
- **Not shown:** the `SystemMessage`, cost and turn counts are in each stream but not in the log.

---

## 4. Code walkthrough

The snippets follow the order in which the code runs: the script first, then the module functions it calls. Where a snippet writes log lines, they're shown under it, copied from the real log (long values trimmed with `...`).

### 4.1 Module docstring: two layers, chained by Python

```python
"""
POC 2 - Decompose the review: per-file passes, then one integration pass
=========================================================================
Python decides the split, so it is the same every time (prompt chaining):

    layer 1:  one NEW session per file   -> the file gets the whole attention budget; its review also records
              (pricing, checkout, ...)      its interface: what it exports and what it assumes about other files
    layer 2:  one session over the per-file summaries only (no code)  -> data flow, API and pattern mismatches

Same model, same reviewer prompt and same per-file schema as POC 1: only the structure changed. A per-file pass
sees one file, so it can never report a two-file issue; the integration pass exists for exactly those.

Besides model I/O, the log shows the same score lines as POC 1: compare the two logs.

Run:  python poc2_multi_pass.py     (1 run: 3 per-file calls + 1 integration call)
"""
```

**Why it matters:** "Python decides the split" is a design choice. The decomposition is a fixed pipeline (prompt chaining), not something a coordinator model invents each run, so every run splits the work the same way. The docstring also says why layer 2 exists: a per-file pass can never report a two-file issue.

---

### 4.2 Imports

```python
import asyncio
import json
import sys
from typing import Any

from claude_agent_sdk import ClaudeSDKError

from common import Settings, load_settings, log, setup_logging
from review_setup import (
    FILE_REVIEW_SCHEMA,
    INTEGRATION_SCHEMA,
    build_review_options,
    format_file,
    load_repo,
    log_scores,
    run_review,
)
```

| Import | What it brings in | Why this file needs it |
| --- | --- | --- |
| `json` | `json.dumps()` | Puts the per-file summaries into the integration prompt |
| `ClaudeSDKError` | The SDK's base error | Stops the script on an SDK runtime failure |
| `FILE_REVIEW_SCHEMA` | From `review_setup` | One file's review: the same `FILE_REVIEW` POC 1 used in a list |
| `INTEGRATION_SCHEMA` | From `review_setup` | Only `cross_file_issues` |
| `build_review_options`, `format_file`, `load_repo`, `log_scores`, `run_review` | From `review_setup` | The same helpers as POC 1 |

---

### 4.3 The two prompts

```python
FILE_PROMPT = "Review this one file from a {n}-file codebase. You can see only this file.\n\n{listing}"
INTEGRATION_PROMPT = (
    "These are the per-file summaries of one TypeScript codebase; the code itself is not included. Find cross-file "
    "issues only: data flow problems between modules, inconsistent API usage (a caller's assumptions that contradict "
    "the callee's contract), and patterns or conventions used differently across files. Name every file each issue "
    "involves. Do not repeat single-file issues.\n\n"
)

RUNS = ["multi-pass"]
```

**Why it matters:**
- **`FILE_PROMPT` tells the pass its scope.** "You can see only this file" keeps it from guessing about other modules, and pushes it to record assumptions in `uses` instead.
- **`INTEGRATION_PROMPT` defines what a cross-file issue is:** data flow, "a caller's assumptions that contradict the callee's contract", and inconsistent patterns. That middle phrase is exactly how `exports` and `uses` are meant to be compared.
- **"Do not repeat single-file issues"** keeps layer 2 to its job.
- **One run.** `RUNS` has a single entry.

---

### 4.4 `multi_pass()`: the two layers

```python
async def multi_pass(settings: Settings, files: list[dict[str, Any]]) -> tuple[dict[str, dict], list[dict]]:
    reviews = {}
    for f in files:  # layer 1: a plain loop, each call a fresh session that holds ONE file (C5)
        review = await run_review(FILE_PROMPT.format(n=len(files), listing=format_file(f)),
                                  build_review_options(settings, FILE_REVIEW_SCHEMA))
        if review is None:
            raise RuntimeError(f"no review for {f['name']}")
        reviews[f["name"]] = review
    # layer 2: the interfaces only, no code and no local issues (C8)
    summaries = [{"file": name, "exports": r["exports"], "uses": r["uses"]} for name, r in reviews.items()]
    integration = await run_review(INTEGRATION_PROMPT + json.dumps(summaries, indent=2),
                                   build_review_options(settings, INTEGRATION_SCHEMA))
    if integration is None:
        raise RuntimeError("no integration review")
    return reviews, integration["cross_file_issues"]
```

| Step | What it does | Agentic concept |
|------|--------------|-----------------|
| `for f in files:` | One `run_review()` per file, in `load_repo()`'s order | **Decomposition by file**: each pass gets the full attention budget |
| `run_review(...)` | A new session each time (empty history) | **Isolation**: no file's review is affected by the others |
| `raise RuntimeError(...)` on `None` | A missing review stops the pipeline | Fail loudly: layer 2 would be incomplete |
| `summaries = [...]` | Keeps only `file`, `exports`, `uses` per file | **Context engineering**: the integration pass gets interfaces, not code or local issues |
| `json.dumps(summaries, indent=2)` | Readable JSON appended to the prompt | A structured hand-off between layers |
| `run_review(..., INTEGRATION_SCHEMA)` | One session over all summaries | **The integration layer** for cross-file issues |

**Why it matters:**
- **The loop is plain Python.** The calls run one after another here; they're independent, so they could also run in parallel.
- **Layer 2 is small by design.** It gets three short interface summaries instead of 97 lines of code, so its whole attention goes to the seams between files.
- **The quality of layer 2 depends on layer 1's `exports` and `uses`.** If a per-file pass doesn't record an assumption, the integration pass can't check it. That's why `REVIEWER_PROMPT` asks for "units and error behavior" and "what it assumes about the result".

The four prompts this sent, logged by `run_review()` (first lines only; each continues with its listing or its summaries):

```
21:44:42  MODEL INPUT   prompt       Review this one file from a 3-file codebase. You can see only this file.
21:44:52  MODEL INPUT   prompt       Review this one file from a 3-file codebase. You can see only this file.
21:45:02  MODEL INPUT   prompt       Review this one file from a 3-file codebase. You can see only this file.
21:45:10  MODEL INPUT   prompt       These are the per-file summaries of one TypeScript codebase; the code itself is not included. Find cross-file issues only: data flow problems between modules, inconsistent API usage (a caller's assumptions that contradict the callee's contract), and patterns or conventions used differently across files. Name every file each issue involves. Do not repeat single-file issues.
```

---

### 4.5 `main()`: run the pipeline, score it the same way as POC 1

```python
async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc2_multi_pass")
        files = load_repo()
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    for name in RUNS:
        try:
            reviews, cross_file_issues = await multi_pass(settings, files)
        except RuntimeError as exc:  # a pass returned no structured review
            log.error("Run '%s' stopped: %s", name, exc)
            return 1
        except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
            log.error("SDK error: %s", exc)
            return 1
        log_scores(reviews, files, cross_file_issues)
    return 0
```

**Why it matters:**
- **The same `log_scores()` as POC 1,** on the same answer key, so the two logs' last five lines are directly comparable.
- **A failed pass stops the run** (`Run '...' stopped: ...`), unlike POC 1, which skipped a failed trial: without every layer-1 review, the comparison would be unfair.

The five lines it wrote:

```
21:45:19  #1 checkout.ts: 5 issue(s), planted bug flagged: True
21:45:19  #2 inventory.ts: 5 issue(s), planted bug flagged: True
21:45:19  #3 pricing.ts: 6 issue(s), planted bug flagged: True
21:45:19  forEach + nested find, identical in both files: {'pricing.ts': True, 'inventory.ts': True} -> consistent
21:45:19  Cross-file issues found: ['cents vs dollars', 'false vs throw'] (2 of 2)
```

No `Run '...' stopped:` or `SDK error:` line, so `main()` returned `0`.

---

### 4.6 `__main__`

```python
if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

---

### 4.7 The shared parts (from `review_setup.py`)

POC 2 reuses everything POC 1 used; its article walks through each in full:
- **`load_repo()` and `format_file()`:** the same numbered listing, in the same order (checkout, inventory, pricing).
- **`REVIEWER_PROMPT`:** the same reviewer, with the equal-depth rule and the instruction to record `exports` (signature, units, error behavior) and `uses` (what each call passes and assumes).
- **`build_review_options()`:** the same model, prompt, `tools=[]` and limits. Only the schema changes.
- **`run_review()`:** each call is a new session; it returns `structured_output` or `None`.
- **`log_scores()`:** the same planted answer key and the same five lines.

The schemas POC 2 uses come from the same definitions as POC 1's:

```python
FILE_REVIEW_SCHEMA = FILE_REVIEW
INTEGRATION_SCHEMA = {"type": "object", "properties": {"cross_file_issues": CROSS_FILE_ISSUES},
                      "required": ["cross_file_issues"]}
```

| Schema | Used by | Shape |
|--------|---------|-------|
| `FILE_REVIEW_SCHEMA` (= `FILE_REVIEW`) | each layer-1 pass | one file: `file`, `bug_count`, `issues`, `exports`, `uses` |
| `INTEGRATION_SCHEMA` | the layer-2 pass | `cross_file_issues`, each with `files`, `kind` (`data_flow`, `api_consistency`, `pattern_consistency`) and `description` |
| `SINGLE_PASS_SCHEMA` (POC 1) | the single pass | a list of `FILE_REVIEW` + `cross_file_issues` |

**Why it matters:** the per-file schema is literally the same object in both POCs, and the cross-file items are the same `CROSS_FILE_ISSUES`. The only difference is how many files one call holds.

---

### 4.8 `common.py`: settings and a single-agent log

Same as POC 1: defaults `claude-sonnet-5-5`, `max_turns` `10`, `max_budget_usd` `0.50` (per review call); `log_model_io(message)` with a `structured` branch for `StructuredOutput`.

| `log_model_io()` branch | Log line tag | Lines in this log |
|-------------------------|--------------|-------------------|
| `ToolUseBlock` named `StructuredOutput` | `MODEL OUTPUT  structured` | 4, one per call |
| `ToolResultBlock` | `MODEL INPUT   tool_result` | 4 (`Structured output provided successfully`) |
| `ResultMessage` | `MODEL OUTPUT  stop_reason` | 4 |
| `ThinkingBlock`, `TextBlock`, other `ToolUseBlock` | `thinking`, `text`, `tool_use` | 0 |

With four calls, `max_budget_usd` applies to each call separately, not to the run.

---

## 5. Turn-by-turn trace of each pass (real output)

Each trace below is the real run from `logs/poc2_multi_pass_20261113_214442.log` (2026-11-13, 21:44:42 to 21:45:19: 37 seconds for all four `query()` calls and the scoring). Each log line points back to the statement that wrote it (section 3.2's table).

How to read the log blocks:
- In the log file, every entry is one line. Here, each entry's header stays on its first line, and its payload is pretty-printed underneath: one key or list item per line.
- Long text wraps onto a deeper-indented line.
- `...` marks text that was cut. A line that starts with `...` summarizes log lines left out.

### 5.1 Layer 1: one session per file

**Real log (the three structured reviews; each prompt holds one numbered file):**

```
21:44:42  MODEL INPUT   prompt
          Review this one file from a 3-file codebase. You can see only this file.
          === checkout.ts (31 lines) === ...
21:44:51  MODEL OUTPUT  structured
          {'file': 'checkout.ts', 'bug_count': 5,
           'issues': [
               {'line': 27, 'severity': 'critical', 'description': 'Assignment `=` is used instead of
                   comparison `===` in the condition, ...'},
               {'line': 17, 'severity': 'major', 'description': "The catch block treats any error from
                   reserveStock as 'out of stock' and discards the original error, ..."},
               {'line': 14, 'severity': 'major', 'description': 'Reservations are made one item at a
                   time with no rollback, ...'},
               {'line': 21, 'severity': 'major', 'description': "The total is computed in dollars as a
                   floating-point number ... The unit of orderTotal's result (dollars) is assumed, not
                   verified."},
               {'line': 13, 'severity': 'minor', 'description': 'There is no validation of the order,
                   ... The function is also not idempotent, ...'}],
           'exports': [...3 exports...],
           'uses': ['inventory.reserveStock(sku: string, quantity: number) — passes item.sku and
                       item.quantity; assumes it throws when stock is insufficient (and only then), and
                       ignores any return value; ...',
                    "pricing.orderTotal(items: LineItem[], prices: PriceEntry[]) — ... assumes it returns
                       a finite number in dollars (not cents) and handles SKUs missing from prices",
                    ...]}
          (id=toolu_015xt5yohZvTq7wTj7CBxJAb)
21:44:51  MODEL INPUT   tool_result  Structured output provided successfully  (... is_error=None)
21:44:51  MODEL OUTPUT  stop_reason  tool_use  (loop result: success)

21:44:52  MODEL INPUT   prompt
          Review this one file from a 3-file codebase. You can see only this file.
          === inventory.ts (26 lines) === ...
21:45:00  MODEL OUTPUT  structured
          {'file': 'inventory.ts', 'bug_count': 5,
           'issues': [
               {'line': 8, 'severity': 'major', 'description': 'reserveStock does not validate
                   quantity: a negative quantity passes the check and increases stock, ...'},
               {'line': 3, 'severity': 'major', 'description': 'The stock map is never populated ...'},
               {'line': 7, 'severity': 'minor', 'description': 'An unknown SKU is treated as zero stock,
                   ...'},
               {'line': 15, 'severity': 'major', 'description': 'Exact floating-point equality on a money
                   value (units * unitFee === invoiced) gives false mismatches, ...'},
               {'line': 22, 'severity': 'minor', 'description': 'lookup.find runs inside forEach, so the
                   cost is O(n*m). Build a Map by id once. ...'}],
           'exports': ['reserveStock(sku: string, quantity: number): boolean — ... Returns false when
                          stock is short or the SKU is unknown. It never throws and does not validate
                          quantity.', ...],
           'uses': []}
          (id=toolu_01AzjkwbzV6ERoyq1WcHa9Dv)
21:45:01  ... tool_result "Structured output provided successfully", stop_reason tool_use (success) ...

21:45:02  MODEL INPUT   prompt
          Review this one file from a 3-file codebase. You can see only this file.
          === pricing.ts (40 lines) === ...
21:45:09  MODEL OUTPUT  structured
          {'file': 'pricing.ts', 'bug_count': 5,
           'issues': [
               {'line': 26, 'severity': 'major', 'description': 'Loop condition `i <= tiers.length` reads
                   one element past the end, ...'},
               {'line': 27, 'severity': 'major', 'description': 'The discount assumes tiers are sorted
                   ascending; ...'},
               {'line': 18, 'severity': 'major', 'description': 'A SKU missing from prices silently counts
                   as 0 cents, ...'},
               {'line': 18, 'severity': 'major', 'description': 'Quantity is not validated, ...'},
               {'line': 15, 'severity': 'minor', 'description': 'Duplicate SKUs in prices are silently
                   resolved by last-one-wins in the Map, ...'},
               {'line': 36, 'severity': 'minor', 'description': 'Linear `lookup.find` inside the loop
                   makes pricedNames O(n*m); build a Map by id first.'}],
           'exports': [..., 'orderTotal(items: LineItem[], prices: PriceEntry[]): number - returns total
                          in integer cents; does not throw, unknown SKUs count as 0 and invalid
                          quantities are not rejected', ...],
           'uses': []}
          (id=toolu_01NtSrKfK8WRaj2nf8vX8QUX)
21:45:09  ... tool_result "Structured output provided successfully", stop_reason tool_use (success) ...
```

**What each pass found:**

| Pass | File | Issues | Planted bug | Pattern copy | Interface recorded |
|------|------|--------|-------------|--------------|--------------------|
| 1 | checkout.ts | 5 (1 critical, 3 major, 1 minor) | line 27 `=` vs `===`: critical | n/a | `uses`: "assumes it throws", "assumes ... dollars (not cents)" |
| 2 | inventory.ts | 5 (3 major, 2 minor) | line 15 float equality: major | line 22, the `find` itself | `exports`: `reserveStock` "Returns false ... never throws" |
| 3 | pricing.ts | 6 (4 major, 2 minor); `bug_count` says 5 | line 26 off by one: major | line 36, the `find` itself | `exports`: `orderTotal` "returns total in integer cents" |

**Lessons from the real data:**
- **More depth per file.** 5, 5 and 6 issues, against POC 1's 3, 3 and 4 for the same files with the same prompt.
- **Each pass stayed in its file.** The `checkout.ts` pass didn't claim to know `orderTotal`'s unit; it wrote "assumed, not verified" and recorded the assumption in `uses`. Its line-21 issue calls the total "dollars as a floating-point number", taking the variable name at face value, because it couldn't see `pricing.ts`.
- **Both pattern copies pointed at the `find` line** (22 and 36), so `flagged()` scored both `True`. In POC 1, both were pointed at the function's first line instead.
- **`bug_count` disagreed again** for `pricing.ts` (5 against 6 issues). The schema can't catch that; `log_scores()` counts the issues.

### 5.2 Layer 2: the integration pass

**Real log:**

```
21:45:10  MODEL INPUT   prompt
          These are the per-file summaries of one TypeScript codebase; the code itself is not
            included. Find cross-file issues only: ... Do not repeat single-file issues.

          [ {"file": "checkout.ts", "exports": [...], "uses": [...4 calls and types...]},
            {"file": "inventory.ts", "exports": [...3...], "uses": []},
            {"file": "pricing.ts", "exports": [...5...], "uses": []} ]

21:45:18  MODEL OUTPUT  structured
          {'cross_file_issues': [
              {'files': ['checkout.ts', 'inventory.ts'], 'kind': 'api_consistency',
               'description': 'checkout assumes reserveStock throws on insufficient stock and wraps it
                   in try/catch to raise "Out of stock", but reserveStock never throws and returns
                   false when stock is short or the SKU is unknown; the return value is ignored, so
                   checkout proceeds and charges for items that were not reserved.'},
              {'files': ['checkout.ts', 'pricing.ts'], 'kind': 'data_flow',
               'description': 'checkout assumes orderTotal returns dollars and formats it as "Charged
                   $X.XX", but orderTotal returns integer cents, so the message overstates the charge
                   by 100x unless the amount is divided by 100.'},
              {'files': ['checkout.ts', 'pricing.ts'], 'kind': 'api_consistency',
               'description': 'checkout assumes orderTotal handles SKUs missing from prices ..., but
                   orderTotal counts unknown SKUs as 0 ...'},
              {'files': ['checkout.ts', 'inventory.ts'], 'kind': 'data_flow',
               'description': 'checkout reserves stock for every item before computing the total. ...
                   inventory has no release function; stock leaks. ...'},
              {'files': ['inventory.ts', 'pricing.ts'], 'kind': 'pattern_consistency',
               'description': 'backorderedNames and pricedNames are near-duplicate lookup-join
                   functions in different modules; ...'},
              {'files': ['inventory.ts', 'pricing.ts'], 'kind': 'pattern_consistency',
               'description': 'Currency units are handled inconsistently: pricing uses integer cents
                   (unitPriceCents), while inventory.feeMatchesInvoice takes unspecified currency
                   units and compares with strict float equality, ...'}
          ]}
          (id=toolu_01Rdo3k6Jsv5xkXPVTxeTrs9)
21:45:18  MODEL INPUT   tool_result
          Structured output provided successfully
          (tool_use_id=toolu_01Rdo3k6Jsv5xkXPVTxeTrs9, is_error=None)
21:45:18  MODEL OUTPUT  stop_reason  tool_use  (loop result: success)

21:45:19  #1 checkout.ts: 5 issue(s), planted bug flagged: True
21:45:19  #2 inventory.ts: 5 issue(s), planted bug flagged: True
21:45:19  #3 pricing.ts: 6 issue(s), planted bug flagged: True
21:45:19  forEach + nested find, identical in both files: {'pricing.ts': True, 'inventory.ts':
            True} -> consistent
21:45:19  Cross-file issues found: ['cents vs dollars', 'false vs throw'] (2 of 2)
```

**How each planted cross-file bug was found:**

| Bug | From the caller's `uses` (checkout.ts) | From the callee's `exports` | Integration issue |
|-----|---------------------------------------|-----------------------------|-------------------|
| false vs throw | `reserveStock`: "assumes it throws when stock is insufficient ... ignores any return value" | inventory.ts: "Returns false when stock is short ... It never throws" | `api_consistency`, checkout + inventory |
| cents vs dollars | `orderTotal`: "assumes it returns a finite number in dollars (not cents)" | pricing.ts: "returns total in integer cents" | `data_flow`, checkout + pricing |

**Variable values at the end of the run:**

| Variable / field | Value |
|------------------|-------|
| `reviews` | 3 per-file reviews, keyed `checkout.ts`, `inventory.ts`, `pricing.ts` |
| `summaries` | 3 dicts with only `file`, `exports`, `uses` |
| `cross_file_issues` | 6 issues: 2 `api_consistency`, 2 `data_flow`, 2 `pattern_consistency` |
| `found` (in `log_scores()`) | `['cents vs dollars', 'false vs throw']` |
| each call's `subtype` / `stop_reason` | `"success"` / `"tool_use"` |

**Lessons from the real data:**
- **Contracts are enough to find integration bugs.** The integration pass never saw a line of code, yet named both planted mismatches and four more seams (missing-price handling, leaked reservations, duplicated lookup code, inconsistent money units).
- **Layer 2 is only as good as layer 1's summaries.** It found exactly the mismatches that the per-file passes had written down as assumptions and contracts.
- **Each layer did one job.** No per-file pass reported a two-file issue, and the integration pass didn't repeat single-file bugs, as its prompt asked.

### 5.3 Single pass (POC 1) vs multi-pass (POC 2)

POC 1's numbers come from its own real run, `logs/poc1_single_pass_20261113_214420.log` (see the POC 1 article).

| | POC 1: single pass | POC 2: multi-pass |
|-|--------------------|-------------------|
| Calls | 1 | 4 (3 per-file + 1 integration) |
| Code per call | all 3 files (97 lines) | one file (31, 26, 40 lines); none in the integration call |
| Issues per file (#1, #2, #3) | 3, 3, 4 | 5, 5, 6 |
| Issues in total (per-file) | 10 | 16 |
| Planted local bugs flagged | 3 of 3 | 3 of 3 |
| Planted cross-file bugs | 2 of 2 | 2 of 2, from the integration pass |
| Cross-file issues reported | 4 | 6 |
| Pattern verdict (scored) | `{'pricing.ts': False, 'inventory.ts': False}` → consistent | `{'pricing.ts': True, 'inventory.ts': True}` → consistent |
| `bug_count` mismatches | pricing.ts (3 vs 4) | pricing.ts (5 vs 6) |
| Final `subtype` / `stop_reason` per call | `success` / `tool_use` | `success` / `tool_use` × 4 |
| Wall time (from logs) | about 13 s | about 36 s |

**Lessons from the comparison:**
- **More found, with the same model and prompt.** 16 issues against 10, and two more cross-file issues. At 3 files, the single pass didn't miss a planted bug, so the gain here is depth and breadth, not rescue.
- **Depth stayed even across files.** No drop-off from #1 to #3 in either run at this size; the per-file structure is what keeps it even at 14 files.
- **The cost is time and calls.** Four sequential calls took about three times as long. The per-file calls don't depend on each other, so they could run in parallel.

The log has no `Run '...' stopped:`, `SDK error:` or `The review failed:` line, so `main()` returned `0`.

---

## 6. Agentic AI concepts recap

| Concept | How this POC shows it |
|---------|-----------------------|
| **Task decomposition** | One review split into per-file passes and an integration pass. |
| **Prompt chaining** | Python runs layer 1, builds the summaries, then runs layer 2: a fixed pipeline. |
| **Full attention per file** | A new session per file; each pass sees only its file. |
| **Interfaces as the hand-off** | `exports` (signature, units, errors) and `uses` (what each call assumes). |
| **Integration pass** | Finds data flow, API and pattern mismatches from the interfaces alone. |
| **Context engineering** | Layer 2 gets the summaries only: no code, no local issues. |
| **Same model, better structure** | Same model, `REVIEWER_PROMPT` and `FILE_REVIEW` as POC 1; 16 issues vs 10. |
| **Consistent verdicts** | Both copies of the duplicated pattern flagged at the same line. |
| **Fail loudly** | A missing review raises `RuntimeError`; the run stops rather than integrating partial data. |
| **Ground truth comparison** | The same `log_scores()` on the same answer key in both POCs. |

---

## 7. Common mistakes this POC helps you avoid

1. **Batching files without an integration pass.** Per-file passes alone can't see two-file bugs.
2. **Giving the integration pass all the code again.** That rebuilds the single pass; give it the interfaces.
3. **Thin per-file summaries.** If a pass doesn't record units, error behavior and assumptions, layer 2 has nothing to check.
4. **Letting a per-file pass guess about other files.** Ask it to record the assumption instead ("assumed, not verified").
5. **Letting a model choose the split on every run.** For a known structure (one pass per file), Python's fixed pipeline is repeatable.
6. **Integrating after a failed pass.** Stop, or the cross-file check works on partial data.
7. **Changing the prompt or model while comparing architectures.** Hold them constant, or the comparison means nothing.
8. **Trusting `bug_count`.** Count the issues; the field disagreed in both POCs.
9. **Ignoring the cost.** Four calls took about three times as long as one; run independent per-file passes in parallel where latency matters.

---

## 8. Claude Architect exam lens

### 8.1 What the exam tests on this topic

The objectives come from `curriculum/01-Agentic-Architecture-&-Orchestration/06-raw-Task-Decomposition-Strategies.md`. POC 2 covers objectives 3 and 4 and the multi-pass side of 5 and 6.

| Exam objective | What a correct answer looks like | Where this POC shows it |
|----------------|----------------------------------|-------------------------|
| 3. Per-file local passes with structured feedback | Each file gets the full attention budget; the last file gets the same depth as the first; each review has a bug count, severities and line numbers. Decomposition, not a better prompt or a bigger window, solves dilution. | layer 1 of `multi_pass()`; `FILE_REVIEW`; 5, 5, 6 issues |
| 4. A cross-file integration pass | A separate pass over the per-file summaries checks data flow, API consistency and pattern consistency. Batching without it still misses cross-cutting issues. | layer 2: `INTEGRATION_PROMPT` + `exports`/`uses`; 6 cross-file issues, both planted ones |
| 5. Compare single pass with multi-pass | More issues found, consistent depth across files, cross-file issues from the integration pass. The same model does better: the fix is structural. | Section 5.3: 16 vs 10 issues, 6 vs 4 cross-file issues |
| 6. Contradictory verdicts on identical code | The multi-pass review treats the same pattern consistently. | `forEach + nested find ... {'pricing.ts': True, 'inventory.ts': True} -> consistent` |

> **Exam tip:** the exam's correct multi-pass answer has two layers. "Split the files into batches" alone is a trap answer: without a cross-file integration pass, data flow and API mismatches between files are still missed. And the integration pass works on summaries (interfaces), not on all the code again.

### 8.2 The same pipeline with the raw Messages API

With the raw Messages API, the two layers are the same loop around `messages.create()`. Each call is independent, so layer 1 can run concurrently.

```python
import asyncio
import json

import anthropic

client = anthropic.AsyncAnthropic()
# MODEL_ID, REVIEWER_PROMPT, FILE_PROMPT, INTEGRATION_PROMPT, the schemas, load_repo() and format_file()
# are as in the POC. Structured outputs need "additionalProperties": False on every object in the schemas.


async def review(prompt: str, schema: dict) -> dict:
    response = await client.messages.create(
        model=MODEL_ID, max_tokens=8000, system=REVIEWER_PROMPT,
        messages=[{"role": "user", "content": prompt}],  # a new conversation per call
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    return json.loads(response.content[0].text)


async def multi_pass(files: list[dict]) -> tuple[list[dict], list[dict]]:
    # layer 1: one call per file, run concurrently
    reviews = await asyncio.gather(*(
        review(FILE_PROMPT.format(n=len(files), listing=format_file(f)), FILE_REVIEW_SCHEMA) for f in files))
    # layer 2: the interfaces only
    summaries = [{"file": r["file"], "exports": r["exports"], "uses": r["uses"]} for r in reviews]
    integration = await review(INTEGRATION_PROMPT + json.dumps(summaries, indent=2), INTEGRATION_SCHEMA)
    return reviews, integration["cross_file_issues"]
```

| Raw Messages API (you write it) | Agent SDK (`poc2_multi_pass.py`) |
|---------------------------------|----------------------------------|
| A new `messages` list per call | `run_review()`: a new `query()` session per call |
| `asyncio.gather()` for layer 1 (optional) | A sequential `for` loop |
| `output_config` with a schema; parse the text | `output_format`; read `structured_output` |
| `summaries` built in your code | The same `summaries` list |
| Integration call over the summaries | The same, with `INTEGRATION_SCHEMA` |

The architecture is identical: the decomposition is in your code either way.

### 8.3 Scenario questions

Try each one before reading the answer. These questions were written for this article to match the curriculum objectives above. They are not official exam questions.

---

**Scenario 1: Batches without integration**

A team fixes attention dilution by reviewing a 14-file repo in per-file passes. Local bug detection improves, but a bug where one module returns cents and another formats the value as dollars is no longer reported. What is missing?

- A. A larger model for the per-file passes.
- B. A cross-file integration pass over the per-file summaries, checking data flow, API consistency and pattern consistency.
- C. Reviewing the files in pairs.
- D. A prompt telling each per-file pass to check other files.

**Answer: B.** A per-file pass sees one file, so it can't see a two-file bug. D asks for something the pass can't see; C covers some pairs and misses others. *POC link:* layer 2 of `multi_pass()`; the integration pass found `cents vs dollars` from `checkout.ts`'s `uses` and `pricing.ts`'s `exports`.

---

**Scenario 2: What the integration pass should receive**

What input gives a cross-file integration pass the best chance of finding mismatches between modules?

- A. All the source code again.
- B. Each file's interface: its exports (signatures, units, error behavior) and its uses (what each call into another module passes and assumes).
- C. Only the list of local bugs from each file.
- D. The file names.

**Answer: B.** Mismatches are caller assumptions that contradict callee contracts; the interfaces state both. A rebuilds the single pass and its dilution; C has no contract information. *POC link:* `summaries = [{"file": name, "exports": r["exports"], "uses": r["uses"]} ...]` in `multi_pass()`, and `INTEGRATION_PROMPT`'s "a caller's assumptions that contradict the callee's contract".

---

**Scenario 3: The integration pass missed one**

An integration pass misses a mismatch where module A assumes module B throws on failure, but B returns `false`. The per-file reviews are otherwise good. Where should the team look first?

- A. The integration prompt's wording.
- B. The per-file summaries of A and B: whether A's `uses` recorded the assumption and B's `exports` recorded its error behavior.
- C. The model's temperature.
- D. The order of the files.

**Answer: B.** The integration pass knows only what the summaries say; if the assumption or the contract wasn't recorded, it can't be compared. *POC link:* `REVIEWER_PROMPT` asks for "error behavior" in exports and "what it assumes about the result" in uses; in the real run, `checkout.ts`'s `uses` and `inventory.ts`'s `exports` stated both sides.

---

**Scenario 4: Proving the fix is structural**

A team wants to show management that multi-pass review beats single-pass because of the architecture, not because of tuning. How should they run the comparison?

- A. Use a better prompt for the multi-pass version.
- B. Use the same model, reviewer prompt, per-file schema and code listing in both, score both against the same planted defects, and compare depth per file and cross-file findings.
- C. Use a bigger model for the single pass to be fair.
- D. Compare the length of the two reports.

**Answer: B.** Change only the structure, and measure against ground truth. *POC link:* `build_review_options()` and `REVIEWER_PROMPT` shared by both POCs; `log_scores()` gives 3/3/4 vs 5/5/6 issues and 4 vs 6 cross-file issues.

---

**Scenario 5: Who decides the split?**

For a code review with a known structure (one pass per file, then integration), should a coordinator model decide the decomposition on each run, or should code?

- A. A model, every time, for flexibility.
- B. Code: a fixed pipeline (prompt chaining) splits the work the same way on every run, which makes results repeatable and comparable.
- C. The user, by hand.
- D. Neither: let one call decide everything.

**Answer: B.** When the structure is known, a fixed decomposition is predictable; dynamic decomposition suits open-ended tasks whose subtasks aren't known in advance. *POC link:* the docstring ("Python decides the split, so it is the same every time (prompt chaining)") and the `for f in files:` loop.

---

**Scenario 6: A per-file pass that guesses**

A per-file reviewer sees `checkout.ts` call `orderTotal()` and assumes the result is in dollars, reporting a "rounding risk with floating-point dollars". The function actually returns cents. What should the design do about such guesses?

- A. Forbid per-file passes from mentioning other modules.
- B. Have each per-file pass record its assumptions about other modules in a structured `uses` field, and let the integration pass check them against the callee's recorded contract.
- C. Give each per-file pass access to all files.
- D. Ignore it: per-file passes are always right.

**Answer: B.** A single-file view can't verify cross-module facts; recording them as assumptions turns guesses into checkable claims. *POC link:* the real `checkout.ts` review: "The unit of orderTotal's result (dollars) is assumed, not verified", with `uses` saying "assumes it returns a finite number in dollars (not cents)"; the integration pass flagged the mismatch.

---

**Scenario 7: Same code, same verdict**

How does a multi-pass architecture help with identical code getting different verdicts in different files?

- A. It doesn't: verdicts are random.
- B. Each file is reviewed with full attention and the same prompt, so the same pattern gets the same scrutiny wherever it appears; the integration pass can also flag the duplication itself.
- C. It only reviews one of the duplicates.
- D. It merges duplicate files first.

**Answer: B.** *POC link:* both copies of the `forEach` + nested `find` were flagged at the `find` line (inventory.ts:22, pricing.ts:36), scored `{'pricing.ts': True, 'inventory.ts': True} -> consistent`, and the integration pass reported the duplication as `pattern_consistency`.

---

**Scenario 8: The latency question**

A multi-pass review of 3 files took about three times as long as the single pass. A stakeholder asks whether it's worth it. What is the best answer?

- A. No: always prefer the single pass for speed.
- B. Yes at scale, where the single pass loses depth; and the per-file passes are independent, so they can run in parallel to cut the wall time.
- C. Only if the model is upgraded.
- D. Remove the integration pass to save time.

**Answer: B.** The structure trades calls for consistent depth; independence between per-file passes allows parallelism. D brings back the missed cross-file issues. *POC link:* section 5.3 (about 13 s vs 36 s); the sequential loop in `multi_pass()` and the `asyncio.gather()` version in 8.2.

---

### 8.4 Quick-recall cheat sheet

```
multi-pass             → layer 1: one NEW session per file; layer 2: one integration session
layer 1 output         → per-file review (bug_count, issues {line, severity, description}) + interface
interface              → exports: signature, units, error behavior | uses: what each call passes and assumes
layer 2 input          → the interfaces only: no code, no local issues
layer 2 finds          → data flow, API consistency (caller assumption vs callee contract), pattern consistency
batching alone         → still misses cross-file issues: the integration pass is required
prompt chaining        → code decides the split; same decomposition every run
fair comparison        → same model, prompt, schema, listing, answer key; only the structure changes
real run (3 files)     → 16 vs 10 issues; 6 vs 4 cross-file; both planted cross-file bugs from layer 2 alone
cost                   → more calls and time; independent per-file passes can run in parallel
```

---

## 9. How to run it

```bash
cd 01-Agentic-Architecture-Orchestration/06-Task-Decomposition-Strategies
source .venv/bin/activate        # the folder's venv (claude-agent-sdk 0.2.181)
python poc1_single_pass.py       # paid: POC 1, 1 call (all files)
python poc2_multi_pass.py        # paid: 4 calls (3 per-file + 1 integration), uses ANTHROPIC_API_KEY from .env
```

- Both scripts call the API. This folder has no free offline demo.
- `.env` needs `ANTHROPIC_API_KEY`; copy `.env.example` and fill it in. `MODEL_ID`, `MAX_TURNS` and `MAX_BUDGET_USD` fall back to `claude-sonnet-5-5`, `10` and `0.50` (per review call).
- Every prompt (with the code or the summaries), each structured review and the five score lines go to the console and to `logs/poc2_multi_pass_<date>_<time>.log`. Compare its last five lines with POC 1's.
- The exit code is `0` when the run finishes. It's `1` on a setup failure, on a pass that returned no structured review (`Run '...' stopped: ...`), or on an SDK runtime failure (`ClaudeSDKError`).
