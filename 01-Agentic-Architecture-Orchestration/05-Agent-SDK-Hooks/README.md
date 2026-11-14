# Agent SDK Hooks: beginner POCs (Claude Agent SDK, Python)

Hands-on POCs for **Agentic Architecture & Orchestration → Agent SDK Hooks** (Claude Certified Architect – Foundations).
Build spec: `curriculum/01-Agentic-Architecture-&-Orchestration/05-revised-Agent-SDK-Hooks.md`.

## The idea in 30 seconds

Every tool call passes two fixed points where the SDK runs **your** callbacks:

```
Claude asks for a tool ──► PreToolUse hook ──► handler runs ──► PostToolUse hook ──► result goes to Claude
                              │                                     │
                              deny: the handler NEVER runs;         can REPLACE the result (updatedToolOutput),
                              Claude gets the reason instead        but the tool has already run
```

* **PostToolUse is for data:** it sees `tool_response`, so it can normalize three systems' formats before Claude reads them.
* **PreToolUse is for policy:** it decides before anything happens. A `PostToolUse` "block" comes after the money moved.
* **Hooks are code, not instructions:** Claude can't skip them, and a hook's deny wins even for a tool in `allowed_tools`.
* **Hooks can share state:** one hook records a passing AML check, another one reads it before allowing a transfer.

## Files

| File | What it is | Calls the API? |
|---|---|---|
| `hooks_setup.py` | the 3 order systems and 3 payment tools (no policy code), `HookState`, `build_hook_options()`, `response_text()`, and `run_agent()` (01's, with `options=` and `tool_results`) | – |
| `poc1_normalize_test.py` | **POC 1**: a `PostToolUse` hook that rewrites every order result to ISO dates and English statuses | Yes, 2 short runs |
| `poc2_policy_test.py` | **POC 2**: `PreToolUse` hooks for the $500 refund limit and the AML prerequisite, and the `PostToolUse` anti-pattern | Yes, 3 short runs |
| `common.py` | reads `.env`, sets up logging, logs the model's input and output | – |

## Setup (once)

```bash
cd "01-Agentic-Architecture-&-Orchestration/05-Agent-SDK-Hooks"
python3 -m venv .venv && source .venv/bin/activate   # Python 3.10+
pip install -r requirements.txt                      # the SDK bundles Claude Code: nothing else to install
cp .env.example .env                                 # then put your API key in .env
```

If `python3 -m venv` says *ensurepip is not available* (Debian/Ubuntu), install the venv package for your
Python version first, e.g. `sudo apt install python3.14-venv`. You can also copy the `.env` from an earlier POC folder.

## Run (in this order)

```bash
python poc1_normalize_test.py   # 2 runs: baseline (no hook), normalized (PostToolUse hook)
python poc2_policy_test.py      # 3 runs: refund-pre, refund-post (the anti-pattern), aml-pass
```

Optional extra, commented out in `poc2_policy_test.py`: `aml-fail`, where the account fails screening and every
transfer attempt stays denied.

## Reading the log

The log shows only what goes **into** the model and what comes **out** of it. Hooks are invisible there, so each
blocked call adds one warning line. Each run is also saved to `logs/<script>_<date>_<time>.log`.

Example from POC 2, run `refund-pre` (illustrative: your ids and wording will differ):

```
15:30:02  MODEL INPUT   prompt       Please process two refunds: $350.00 for order LS-4410, which arrived late, and $1,200.00 ...
15:30:05  MODEL OUTPUT  tool_use     mcp__payments__process_refund {'order_id': 'LS-4410', 'amount': 350.0}  (id=toolu_A)
15:30:05  MODEL OUTPUT  tool_use     mcp__payments__process_refund {'order_id': 'LS-4475', 'amount': 1200.0}  (id=toolu_B)
15:30:05  MODEL INPUT   tool_result  [{'type': 'text', 'text': 'Refund RF-0001 of $350.00 for order LS-4410 processed.'}]  (tool_use_id=toolu_A, is_error=False)
15:30:05  PreToolUse hook denied the call (id=toolu_B): its handler will not run
15:30:05  MODEL INPUT   tool_result  Refund not processed: refunds over $500 need human approval. Escalation ESC-0001 is open for order LS-4475 ($1,200.00); ...  (tool_use_id=toolu_B, is_error=True)
15:30:08  MODEL OUTPUT  text         I refunded $350.00 for LS-4410. The $1,200.00 refund needs human approval: escalation ESC-0001 ...
15:30:08  MODEL OUTPUT  stop_reason  end_turn  (loop result: success)
15:30:08  Run 'refund-pre': process_refund requested 2, denied by a hook 1, handler ran 1
15:30:08  Run 'refund-pre': refunds [('LS-4410', 350.0)], transfers [], escalations [('ESC-0001', 'LS-4475')], AML results {}
```

* The denied call's tool_result is the hook's reason: no handler wrote it. `handler ran 1` proves the $1,200.00
  refund never executed.
* In `refund-post` the same request ends with `handler ran 2` and `('LS-4475', 1200.0)` in the refunds: the
  PostToolUse warning came after the payment.
* In POC 1, compare the baseline's tool_result lines (`1776686400`, `2`, `04/05/2026`, `P`) with the normalized ones
  (`2026-04-20`, `shipped`, `2026-05-04`, `pending`): that is exactly what Claude received.

## Concept map (IDs from the build spec)

| ID | Concept | Where you see it |
|---|---|---|
| C1 | Three MCP tools whose results use different formats | `ORDERS` and `build_orders_server()` in `hooks_setup.py` |
| C2 | Format chaos: without normalization, Claude decodes three formats every time | POC 1 run `baseline`: the tool_result lines show `1776686400`/`2`, `"2026-04-28"`/`"delivered"`, `"04/05/2026"`/`"P"` |
| C3 | A `PostToolUse` hook intercepts every tool result | `normalize_output` registered under `"PostToolUse"` in `NORMALIZE_HOOKS` (`poc1_normalize_test.py`) |
| C4 | `PostToolUse` runs after execution, before the model | POC 1 run `normalized`: the handlers still return raw formats, but the tool_result lines Claude receives are normalized |
| C5 | Normalization rules: ISO 8601 dates, English statuses | `to_iso()`, `to_status()`, `normalize_record()` in `poc1_normalize_test.py` |
| C6 | Return the rewrite as `updatedToolOutput` inside `hookSpecificOutput` | the return value of `normalize_output()` |
| C7 | `PostToolUse` is the right direction for normalization | the comment above `NORMALIZE_HOOKS`: a `PreToolUse` hook only sees `tool_input`, the result doesn't exist yet |
| C8 | Queries that need all three tools | `TEST_PROMPT`: one order per system, so three `tool_use` lines (typically in one response) |
| C9 | Consistent data prevents misreads (day vs month, `P` = pending) | line `Run '...': summary ... -> matches the truth` or `WRONG`; comments in `to_iso()` and `to_status()`; the note below |
| C10 | Every result normalized, whichever tool produced it | POC 1 run `normalized`: all three tool_result lines use ISO dates and English statuses |
| C11 | The answer uses dates and statuses consistently | POC 1 run `normalized`: the text quotes `2026-04-20`, `2026-04-28`, `2026-05-04`, `shipped`, `delivered`, `pending` |
| C12 | A `PreToolUse` callback denies refunds over $500 with a reason | `refund_limit()` and `deny()` in `poc2_policy_test.py` |
| C13 | A blocked refund is redirected to a human escalation | `refund_limit()` opens the escalation itself; line `escalations [('ESC-0001', 'LS-4475')]` |
| C14 | `PreToolUse` runs before execution: the handler never runs | run `refund-pre`: `process_refund requested 2, denied by a hook 1, handler ran 1` |
| C15 | `PostToolUse` is too late for blocking | run `refund-post`: warning `PostToolUse fired after the refund ran ...`; the refunds include `('LS-4475', 1200.0)` |
| C16 | A second `PreToolUse` hook blocks `transfer_funds` until AML passes | `aml_gate()` in `poc2_policy_test.py` |
| C17 | A `PostToolUse` hook on `aml_check` records that state | `record_aml()`; line `AML results {'ACC-5521': 'pass'}` |
| C18 | A prompt rule reaches about 95%; regulation needs 100% | already covered in `../04-Workflow-Enforcement-and-Handoff` (C5, C6); here `SYSTEM_PROMPTS["payments"]` has no AML rule, yet no transfer runs before a pass |
| C19 | Blocked tools never execute | the `requested / denied by a hook / handler ran` line of every run |
| C20 | The model receives the `permissionDecisionReason` | the tool_result line after each `PreToolUse hook denied` warning, e.g. `AML check required: ...` with `is_error=True` |
| C21 | Once the prerequisite is met, the same operation runs | run `aml-pass`: denied → `aml_check` pass → the same `transfer_funds` runs (`TR-0001`) |
| E1 | The gated tools stay in `allowed_tools` | `build_hook_options()`; run `refund-post` shows the refund runs when no `PreToolUse` hook objects |
| E2 | Matchers must name the full MCP tool | the `HookMatcher(matcher=...)` lines in `build_policy_hooks()`: `"process_refund"` alone would match no tool |
| E3 | `tool_response` has no fixed shape | `response_text()` in `hooks_setup.py`; `same_shape()` in `poc1_normalize_test.py` |

System C's `04/05/2026` is day-first: 4 May 2026. Read month-first it becomes 5 April, 29 days earlier, and the
oldest-first order turns into `LS-3150, LS-1042, LS-2087`. System A's epoch is read in UTC: on a UTC+14 machine,
local time would make it `2026-04-21`.

## Settings (`.env`)

* `MODEL_ID`: the model (default `claude-sonnet-5-5`).
* `MAX_BUDGET_USD`: the SDK stops any single run whose estimated spend passes this (default `0.50`).
* `MAX_TURNS`: the safety cap on tool-use turns per run (default `15`).
