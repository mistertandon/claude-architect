# POC 2: Deny It Before It Happens

> **File:** `poc2_policy_test.py` (with `hooks_setup.py` and `common.py`)
> **Domain:** 01 Agentic Architecture & Orchestration → 05 Agent SDK Hooks
> **SDK:** Claude Agent SDK for Python (`claude-agent-sdk >=0.2.174,<0.3`; 0.2.181 in the folder's `.venv`)
> **Page:** https://claude.ai/artifact/URaWkhRpitfB1yHNaWQymM

---

## 1. What this POC proves

Two payment policies are enforced only by hooks: no handler, prompt or tool description mentions them. Refunds over $500 must go to a human; transfers need a passing AML check first. Every claim below is checked against one real run: `logs/poc2_policy_test_20261113_205350.log`.

| # | Idea | Where it shows up in the code |
|---|------|------------------------------|
| 1 | **A `PreToolUse` hook can deny a call before it runs.** The handler never executes, and Claude receives the hook's reason as the call's tool result. | `refund_limit()`, `deny()`; run `refund-pre`: `denied by a hook 1, handler ran 1` |
| 2 | **The redirect is as deterministic as the block.** The hook itself opens the human escalation and names it in the reason. | `state.escalations.append(...)` in `refund_limit()`; `ESC-0001` |
| 3 | **`PostToolUse` is too late for policy.** The same check in `PostToolUse` fires after the refund was paid. | `refund_limit_after()`; run `refund-post`: `handler ran 2`, `('LS-4475', 1200.0)` |
| 4 | **Hooks can share state.** A `PostToolUse` hook on `aml_check` records the result; a `PreToolUse` hook on `transfer_funds` reads it. | `record_aml()`, `aml_gate()`, `state.aml_results` |
| 5 | **A hook's deny wins over `allowed_tools`.** Every payment tool is pre-approved, so only a hook can stop one. | `allowed_tools=tool_names` in `build_hook_options()`; the comment in `build_policy_hooks()` |
| 6 | **Matchers name the full MCP tool.** `process_refund` alone would match nothing, and the hook would silently never run. | `HookMatcher(matcher=REFUND, ...)` with `REFUND = "mcp__payments__process_refund"` |

The pattern in one picture:

```
Claude asks for a tool ──▶ PreToolUse hooks ──▶ handler runs ──▶ PostToolUse hooks ──▶ result goes to Claude
                              │                                     │
                              deny: the handler NEVER runs;         sees the result; can record it or rewrite it,
                              Claude gets the reason instead        but the action has already happened
```

---

## 2. The files involved

```
05-Agent-SDK-Hooks/
├── .env / .env.example       ← ANTHROPIC_API_KEY, MODEL_ID, MAX_TURNS, MAX_BUDGET_USD
├── requirements.txt          ← claude-agent-sdk >=0.2.174,<0.3 and python-dotenv
├── common.py                 ← Settings, load_settings(), setup_logging(), log_model_io()
├── hooks_setup.py            ← order systems, 3 payment tools (no policy code), HookState, build_hook_options(), run_agent()
├── poc1_normalize_test.py    ← POC 1: the PostToolUse normalization hook (not covered here)
├── poc2_policy_test.py       ← entry point: the policy hooks, 3 runs
└── logs/
    └── poc2_policy_test_20261113_205350.log   ← the real run used in sections 3.2 and 5
```

Every snippet in this article is copied from these files, logging statements included. Each logging statement is named with the log line it writes.

The responsibilities split like this:
- `common.py` covers **configuration and observability** (single-agent log lines).
- `hooks_setup.py` covers **capabilities**: three payment tools that do exactly what they say, with **no policy code** in any handler; **state** (`HookState`); the **options**; and the agent loop.
- `poc2_policy_test.py` covers **enforcement**: the four hook callbacks and their matchers, and **the experiment**: three runs, with counts of what was requested, denied and actually run.

---

## 3. End-to-end execution flow

### 3.1 The big picture

```
python poc2_policy_test.py
        │
        ▼
asyncio.run(main())                                                     [poc2_policy_test.py]
        │
        ├─▶ load_settings(), setup_logging("poc2_policy_test")          [common.py]
        │
        └─▶ for name, prompt, refund_check in RUNS:    ("refund-pre", "refund-post", "aml-pass")
               │
               ├─▶ state = HookState()                                  [hooks_setup.py]  a new state per run
               ├─▶ hooks = build_policy_hooks(state, refund_check)
               │       PreToolUse:  transfer_funds → aml_gate;  process_refund → refund_limit   (refund_check="pre")
               │       PostToolUse: aml_check → record_aml;     process_refund → refund_limit_after (refund_check="post")
               ├─▶ run = run_agent(prompt, build_hook_options(settings, state, "payments", hooks))   → one query()
               ├─▶ per tool: log.info("Run '%s': %s requested %d, denied by a hook %d, handler ran %d")
               └─▶ log.info("Run '%s': refunds %s, transfers %s, escalations %s, AML results %s")
```

Inside `run_agent()`, for one `process_refund` call in run `refund-pre`. The right-hand column names the log line each step writes.

```
run_agent(user_prompt, options)                                                         [hooks_setup.py]
   │
   ├─ log.info("MODEL INPUT   prompt ...")                                            → log: prompt
   └─▶ async for message in query(prompt=user_prompt, options=options):
          │
          │   ┌──────────────────────── SDK-owned: the agent loop ──────────────────────────┐
          │   │ Claude: tool_use mcp__payments__process_refund {order_id, amount}            │  → log: tool_use
          │   │    └─▶ PreToolUse hooks matching the tool: refund_limit(input_data, id, ctx) │
          │   │          amount ≤ 500 → {} (no objection)                                    │
          │   │          amount > 500 → open escalation; deny(...) → log.warning(...)        │  → log: PreToolUse hook denied ...
          │   │                         {"permissionDecision": "deny", "...Reason": reason}  │
          │   │    └─▶ allowed? handler runs (state.calls += 1, refund recorded)             │
          │   │        denied?  handler skipped; Claude gets the reason as an error result   │  → log: tool_result
          │   │    └─▶ PostToolUse hooks (if any match)                                      │
          │   │ ... final text, stop_reason = end_turn                                       │  → log: text, stop_reason
          │   └──────────────────────────────────────────────────────────────────────────────┘
          │
          ├─ log_model_io(message)
          ├─ run["tool_results"]: one item per tool result, with its tool_use_id
          └─ ResultMessage success + end_turn → run["answer"]
```

### 3.2 Messages your `async for` receives (run `refund-pre`, real output)

The values below come from the real run on 2026-11-13, recorded in `logs/poc2_policy_test_20261113_205350.log`. Each log line comes from one statement in the code:

| Log line tag | Message class / source | Field logged | Written by |
|--------------|------------------------|--------------|------------|
| `MODEL INPUT   prompt` | *(none: the `user_prompt`)* | `user_prompt` | `log.info(...)` in `run_agent()` (`hooks_setup.py`) |
| `MODEL OUTPUT  thinking` / `text` / `tool_use` | `AssistantMessage` blocks | as in POC 1 | `log_model_io()` (`common.py`) |
| `MODEL INPUT   tool_result` | `UserMessage` → `ToolResultBlock` | `block.content`, `block.tool_use_id`, `block.is_error` | `log_model_io()` |
| `MODEL OUTPUT  stop_reason` | `ResultMessage` | `message.stop_reason`, `message.subtype` | `log_model_io()` |
| `PreToolUse hook denied the call (id=...): its handler will not run` | *(a hook callback)* | `tool_use_id` | `log.warning(...)` in `deny()` (`poc2_policy_test.py`) |
| `PostToolUse fired after the refund ran: too late to block it. ...` | *(a hook callback)* | none | `log.warning(...)` in `refund_limit_after()` |
| `Run '...': <tool> requested N, denied by a hook N, handler ran N` | *(Python counts)* | `run["tool_results"]`, `state.denials`, `state.calls` | `log.info(...)` in `main()` |
| `Run '...': refunds [...], transfers [...], escalations [...], AML results {...}` | *(Python reads state)* | `state.*` | `log.info(...)` in `main()` |

The format has no level name, so the two `log.warning` lines look like the others. They are the only lines a hook writes.

Run `refund-pre` as it really streamed:

```
20:53:50  (input)                                                              log: prompt
            prompt = Please process two refunds: $350.00 for order LS-4410, which arrived late, and
                       $1,200.00 for order LS-4475, which arrived damaged.

20:53:53  AssistantMessage › ToolUseBlock                                      log: tool_use
            name = "mcp__payments__process_refund", input = {'order_id': 'LS-4410', 'amount': 350}
            id   = "toolu_01CdX3H2X6S6koWNeamFzvv7"
          refund_limit(): 350 ≤ 500, no escalation → {}                        (no log line)
          handler: state.calls["process_refund"] = 1, refund RF-0001 recorded  (no log line)
20:53:53  UserMessage › ToolResultBlock                                        log: tool_result
            content = [{'type': 'text', 'text': 'Refund RF-0001 of $350.00 for order LS-4410 processed.'}]
            tool_use_id = "toolu_01CdX3H2X6S6koWNeamFzvv7", is_error = None

20:53:54  AssistantMessage › ToolUseBlock                                      log: tool_use
            name = "mcp__payments__process_refund", input = {'order_id': 'LS-4475', 'amount': 1200}
            id   = "toolu_0116V4Rt3fmZhTMUYTy8YD55"
          refund_limit(): 1200 > 500 → escalation ESC-0001 opened, deny(...)
20:53:54  PreToolUse hook denied the call (id=toolu_0116V4Rt3fmZhTMUYTy8YD55): its   log: deny()'s warning
            handler will not run
20:53:54  UserMessage › ToolResultBlock                                        log: tool_result
            content = PreToolUse:mcp__payments__process_refund hook error: Refund not processed:
                      refunds over $500 need human approval. Escalation ESC-0001 is open for order
                      LS-4475 ($1,200.00); tell the customer a human agent will review it. Do not
                      retry or split this refund.
            tool_use_id = "toolu_0116V4Rt3fmZhTMUYTy8YD55", is_error = True   ← the same id the hook saw

20:53:55  AssistantMessage › TextBlock                                         log: text
            text = I processed one refund. The other needs human approval first. ... LS-4475
                   ($1,200.00 ...): Not processed. ... escalation ESC-0001 is now open. ...
20:53:56  ResultMessage                                                        log: stop_reason
            stop_reason = "end_turn", subtype = "success"

20:53:57  Run 'refund-pre': process_refund requested 2, denied by a hook 1, handler ran 1
20:53:57  Run 'refund-pre': refunds [('LS-4410', 350.0)], transfers [], escalations
            [('ESC-0001', 'LS-4475')], AML results {}
```

What to notice in the real data:
- **Requested 2, ran 1.** Both refunds reached the stream as `tool_use` lines, but `state.calls["process_refund"]` is `1`: the $1,200 handler never ran, and `state.refunds` holds only LS-4410.
- **The denied call's result came from the hook, not the handler.** Its `content` is the hook's `permissionDecisionReason`, prefixed with `PreToolUse:mcp__payments__process_refund hook error:`. No handler code wrote it.
- **The deny is an error result.** `is_error=True`, and its `content` is a plain string; the successful result is a list of text blocks.
- **The ids line up.** The hook logged `id=toolu_0116V...`, the error result has `tool_use_id=toolu_0116V...`, and `main()` counted it as denied because that id is in `state.denials`. The `tool_use_id` a hook receives is the tool call's id.
- **Claude followed the reason.** It told the customer about `ESC-0001` and said it hadn't retried or split the refund, exactly as the reason asked.
- **The calls went one at a time here.** The $350 result arrived before the $1,200 call was made.
- **Not shown:** hooks write nothing to the stream; only the two `log.warning` lines in `deny()` and `refund_limit_after()` make them visible. The `SystemMessage`, cost and `num_turns` aren't logged either.

> The `UserMessage` items are **not** typed by a human. They carry tool results, including the hook's denial reason.

---

## 4. Code walkthrough

The snippets follow the order in which the code runs: the script first, then the module functions it calls. Where a snippet writes log lines, they're shown under it, copied from the real log (long values trimmed with `...`).

### 4.1 Module docstring: two policies, hooks only

```python
"""
POC 2 - Enforcing policy with PreToolUse hooks
===============================================
Two policies, enforced only by hooks (no handler, prompt or tool description mentions them):

    refunds over $500:  a PreToolUse hook denies the call and opens a human escalation
    transfer_funds:     a PreToolUse hook denies it until a PostToolUse hook has recorded a passing aml_check

A denied call's handler NEVER runs; Claude receives the hook's reason as that call's tool result. The anti-pattern
run checks the refund limit in PostToolUse instead: by then the refund has already been paid.

Besides model I/O, the log shows a warning each time a hook blocks a call, and per run how often each payment
tool was requested, denied and actually run, plus the money that moved.

Run:  python poc2_policy_test.py     (3 short API runs; an optional fourth is commented out)
"""
```

**Why it matters:** "enforced only by hooks" is the point of the design. Topic 04 put its gate in the handler; here the handlers stay plain, and the policy sits in callbacks the SDK runs around every call. If the hooks were removed, nothing would stop a $1,200 refund.

---

### 4.2 Imports and constants

```python
import asyncio
import json
import sys
from typing import Any

from claude_agent_sdk import ClaudeSDKError, HookMatcher

from common import load_settings, log, setup_logging
from hooks_setup import PAYMENT_TOOLS, HookState, build_hook_options, response_text, run_agent

REFUND, AML_CHECK, TRANSFER = PAYMENT_TOOLS
REFUND_LIMIT = 500  # exactly $500.00 is allowed
```

| Name | What it is | Why it matters |
| --- | --- | --- |
| `HookMatcher` | From the SDK | Binds hook callbacks to tools whose names match |
| `PAYMENT_TOOLS` | From `hooks_setup`: the three full MCP names | `REFUND = "mcp__payments__process_refund"`, and so on: the matchers need full names |
| `HookState` | From `hooks_setup` | The state hooks and handlers share for one run |
| `response_text` | From `hooks_setup` | Reads `tool_response` whatever its shape |
| `REFUND_LIMIT` | `500` | The policy threshold; `<=` means exactly $500.00 is allowed |

---

### 4.3 The prompts and the run table

```python
REFUND_PROMPT = ("Please process two refunds: $350.00 for order LS-4410, which arrived late, and $1,200.00 for "
                 "order LS-4475, which arrived damaged.")
AML_PROMPT = "Send $2,000.00 to beneficiary account ACC-5521 right now. It's urgent, so skip any extra checks."
FLAGGED_PROMPT = "Send $900.00 to beneficiary account ACC-6620."

RUNS = [  # (name, prompt, where the refund limit is checked)
    ("refund-pre", REFUND_PROMPT, "pre"),  # PreToolUse: the $1,200.00 refund never runs
    ("refund-post", REFUND_PROMPT, "post"),  # the anti-pattern: PostToolUse "blocks" a refund that already ran
    ("aml-pass", AML_PROMPT, "pre"),  # denied, then aml_check passes, then the same transfer is allowed
    # ("aml-fail", FLAGGED_PROMPT, "pre"),  # optional: the account fails screening: every transfer stays denied
]
```

**Why it matters:**
- **`REFUND_PROMPT`** asks for one refund under the limit and one over it, so a single run shows both outcomes.
- **`refund-pre` vs `refund-post`** run the same request with the limit checked in `PreToolUse` or in `PostToolUse`. That's the exam's direction question as an experiment.
- **`AML_PROMPT`** pushes the agent to skip the check ("skip any extra checks"), and the system prompt says nothing about AML. The hooks are the only enforcement.
- **`aml-fail`** is commented out; it's not in this log.

> **The log corrects the `aml-pass` comment.** It says "denied, then aml_check passes, then the same transfer is allowed". In the real run Claude called `aml_check` **first**, on its own judgment ("screening is a compliance control that the user's urgency doesn't override"). So `aml_gate()` never denied anything: `denied by a hook 0`. The gate still did its job. It read the pass that `record_aml()` had stored and let the transfer through. Section 5.4 shows the deny path from the code.

---

### 4.4 `deny()`: one shape for every denial

```python
def deny(state: HookState, tool_use_id: str | None, reason: str) -> dict:
    """A PreToolUse deny: the handler never runs, and Claude receives the reason as the tool result (C14, C20)."""
    state.denials[str(tool_use_id)] = reason
    log.warning("PreToolUse hook denied the call (id=%s): its handler will not run", tool_use_id)
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}
```

| Part | What it does |
|------|--------------|
| `state.denials[...] = reason` | Records the denial by `tool_use_id`, so `main()` can count denied calls |
| `log.warning(...)` | Makes the denial visible in the log; hooks write nothing to the stream themselves |
| `hookSpecificOutput` with `hookEventName: "PreToolUse"` | The hook output contract for this event |
| `permissionDecision: "deny"` | Stops the call: the handler won't run |
| `permissionDecisionReason` | What Claude receives as the call's result: the place to explain and redirect |

**Why it matters:** the reason is the model's only signal. A good one says what didn't happen, why, what to do instead, and what not to do ("Do not retry or split this refund").

The lines it led to in run `refund-pre`:

```
20:53:54  PreToolUse hook denied the call (id=toolu_0116V4Rt3fmZhTMUYTy8YD55): its handler will not run
20:53:54  MODEL INPUT   tool_result  PreToolUse:mcp__payments__process_refund hook error: Refund not processed: refunds over $500 need human approval. Escalation ESC-0001 is open for order LS-4475 ($1,200.00); tell the customer a human agent will review it. Do not retry or split this refund.  (tool_use_id=toolu_0116V4Rt3fmZhTMUYTy8YD55, is_error=True)
```

The `PreToolUse:mcp__payments__process_refund hook error:` prefix isn't in the code. It was added between the hook and Claude.

---

### 4.5 `build_policy_hooks()`: the four callbacks

```python
def build_policy_hooks(state: HookState, refund_check: str = "pre") -> dict[str, list[HookMatcher]]:
    """The callbacks close over this run's state, like the tools in 04's build_support_server()."""
```

**Why it matters:** the callbacks are defined inside the function, so each one reads and writes the `state` of the current run, the same pattern topic 04 used for its tools.

#### a) `refund_limit()`: deny over $500, and open the escalation

```python
    async def refund_limit(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        """PreToolUse on process_refund: over the limit, deny and redirect to a human (C12, C13)."""
        order_id, amount = input_data["tool_input"]["order_id"], float(input_data["tool_input"]["amount"])
        escalation = next((e for e in state.escalations if e["order_id"] == order_id), None)
        if amount <= REFUND_LIMIT and escalation is None:  # an open escalation also blocks a split refund
            return {}  # no objection: the call goes on to the permission rules, where allowed_tools approves it
        if escalation is None:  # the redirect is as deterministic as the block: the hook opens the escalation
            escalation = {"id": f"ESC-{len(state.escalations) + 1:04d}", "order_id": order_id, "amount": amount,
                          "reason": f"refund over ${REFUND_LIMIT}"}
            state.escalations.append(escalation)
        return deny(state, tool_use_id, (
            f"Refund not processed: refunds over ${REFUND_LIMIT} need human approval. Escalation {escalation['id']} "
            f"is open for order {order_id} (${escalation['amount']:,.2f}); tell the customer a human agent will "
            "review it. Do not retry or split this refund."))
```

**Why it matters:**
- **`input_data["tool_input"]`** is all a `PreToolUse` hook has: the arguments Claude chose. There is no result yet.
- **`return {}`** means "no objection". The call continues to the permission rules, where `allowed_tools` approves it.
- **The redirect is code too.** The hook opens `ESC-0001` itself, so the human escalation happens even if Claude never mentions it.
- **Split refunds are blocked.** Once an order has an open escalation, even a $400 refund for it is denied, so "two refunds of $600" can't get around the limit.

**Agentic concept:** pre-execution policy enforcement with a deterministic redirect.

#### b) `aml_gate()` and `record_aml()`: two hooks, one state

```python
    async def aml_gate(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        """PreToolUse on transfer_funds: no passing aml_check for this account in this run, no transfer (C16)."""
        account = input_data["tool_input"]["to_account"]
        if state.aml_results.get(account) == "pass":  # a pass for one account unlocks no other
            return {}
        if state.aml_results.get(account) == "fail":
            return deny(state, tool_use_id, f"Transfer blocked: {account} failed its AML check in this session. "
                                            "Do not retry; tell the user that compliance must review it.")
        return deny(state, tool_use_id, f"AML check required: no passing aml_check for {account} in this session. "
                                        "Call aml_check for it first; transfer_funds runs only after a pass.")

    async def record_aml(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        """PostToolUse on aml_check: record the result in state for aml_gate; never rewrite it (C17)."""
        try:
            screening = json.loads(response_text(input_data["tool_response"]))
            state.aml_results[screening["account_id"]] = screening["result"]
        except (ValueError, KeyError, TypeError):
            pass
        return {}
```

| Hook | Event | Reads | Writes | Returns |
|------|-------|-------|--------|---------|
| `record_aml()` | `PostToolUse` on `aml_check` | `tool_response` | `state.aml_results[account]` | `{}`: the result reaches Claude unchanged |
| `aml_gate()` | `PreToolUse` on `transfer_funds` | `tool_input["to_account"]`, `state.aml_results` | `state.denials` (through `deny()`) | `{}` on a pass; a deny otherwise |

**Why it matters:**
- **The prerequisite state is written by code that saw the real result.** Only `record_aml()` writes `aml_results`, from `aml_check`'s actual output. Claude can't claim a pass.
- **Per account.** "a pass for one account unlocks no other".
- **Three outcomes, three reasons.** Pass → allowed. Fail → denied, "Do not retry". Never checked → denied, "Call aml_check for it first", so Claude can recover.
- **`PostToolUse` used correctly:** to observe a result, not to block anything.

**Agentic concept:** a multi-step prerequisite enforced across two hook events through shared session state.

#### c) `refund_limit_after()`: the anti-pattern

```python
    async def refund_limit_after(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        """THE ANTI-PATTERN (C15): PostToolUse fires after the handler. The refund has already been paid."""
        if float(input_data["tool_input"]["amount"]) <= REFUND_LIMIT:
            return {}
        log.warning("PostToolUse fired after the refund ran: too late to block it. Enforce policy in PreToolUse.")
        # "block" only adds the reason next to the result: Claude still sees "processed", and the money is gone.
        return {"decision": "block", "reason": f"Refunds over ${REFUND_LIMIT} need human approval."}
```

**Why it matters:** this is the wrong answer the exam warns about. The check is correct; the timing isn't. By the time `PostToolUse` runs, the handler has paid the refund. `"decision": "block"` can only tell Claude afterwards.

The line it wrote, and the result Claude got for the same call:

```
20:54:00  PostToolUse fired after the refund ran: too late to block it. Enforce policy in PreToolUse.
20:54:00  MODEL INPUT   tool_result  [{'type': 'text', 'text': 'Refund RF-0002 of $1,200.00 for order LS-4475 processed.'}]  (tool_use_id=toolu_017hBWa6pzjU3eA2vfTEEpsp, is_error=None)
```

The tool result is still "processed", with `is_error=None`. Section 5.2 shows how the block's reason reached Claude anyway.

#### d) The matchers

```python
    # Matchers name the full MCP tool: "process_refund" alone would match no tool, and the hook would silently
    # never run (E2). Hooks run before the permission rules, so a deny wins over allowed_tools (E1).
    pre = [HookMatcher(matcher=TRANSFER, hooks=[aml_gate])]
    post = [HookMatcher(matcher=AML_CHECK, hooks=[record_aml])]
    if refund_check == "pre":
        pre.append(HookMatcher(matcher=REFUND, hooks=[refund_limit]))
    else:
        post.append(HookMatcher(matcher=REFUND, hooks=[refund_limit_after]))
    return {"PreToolUse": pre, "PostToolUse": post}
```

| `refund_check` | `PreToolUse` | `PostToolUse` |
|----------------|--------------|---------------|
| `"pre"` (runs `refund-pre`, `aml-pass`) | `transfer_funds` → `aml_gate`; `process_refund` → `refund_limit` | `aml_check` → `record_aml` |
| `"post"` (run `refund-post`) | `transfer_funds` → `aml_gate` | `aml_check` → `record_aml`; `process_refund` → `refund_limit_after` |

**Why it matters:**
- **Full MCP names.** `REFUND` is `mcp__payments__process_refund`. A bare `process_refund` matcher would match no tool, and nothing would warn you; the policy would just never run.
- **Hooks run before the permission rules.** All three tools are in `allowed_tools`, yet a `PreToolUse` deny still stops the call. Pre-approval doesn't bypass a hook.

---

### 4.6 `main()`: requested, denied, ran

```python
async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc2_policy_test")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    for name, prompt, refund_check in RUNS:
        state = HookState()  # a new state per run: a pass from one run unlocks nothing in the next
        try:
            run = await run_agent(prompt, build_hook_options(settings, state, "payments", build_policy_hooks(state, refund_check)))
        except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
            log.error("SDK error: %s", exc)
            return 1
        for tool_name in ("process_refund", "transfer_funds"):  # blocked calls never reach the handler (C14, C19)
            requested = [r for r in run["tool_results"] if r["name"] == f"mcp__payments__{tool_name}"]
            if requested:
                denied = sum(r["tool_use_id"] in state.denials for r in requested)
                log.info("Run '%s': %s requested %d, denied by a hook %d, handler ran %d",
                         name, tool_name, len(requested), denied, state.calls[tool_name])
        log.info("Run '%s': refunds %s, transfers %s, escalations %s, AML results %s", name,
                 [(r["order_id"], r["amount"]) for r in state.refunds], [(t["to_account"], t["amount"]) for t in state.transfers],
                 [(e["id"], e["order_id"]) for e in state.escalations], state.aml_results)
    return 0
```

**Why it matters:**
- **Three numbers from three sources.** *Requested* comes from the stream (`run["tool_results"]`), *denied* from the hooks (`state.denials`), and *ran* from the handlers (`state.calls`). If a denied call had run anyway, *ran* would be higher than *requested − denied*.
- **The money line reads state the handlers wrote.** It shows what actually happened, whatever Claude says.
- **A new `HookState` per run,** so an AML pass in one run can't unlock a transfer in another.

The lines it wrote:

```
20:53:57  Run 'refund-pre': process_refund requested 2, denied by a hook 1, handler ran 1
20:53:57  Run 'refund-pre': refunds [('LS-4410', 350.0)], transfers [], escalations [('ESC-0001', 'LS-4475')], AML results {}
20:54:06  Run 'refund-post': process_refund requested 2, denied by a hook 0, handler ran 2
20:54:06  Run 'refund-post': refunds [('LS-4410', 350.0), ('LS-4475', 1200.0)], transfers [], escalations [], AML results {}
20:54:17  Run 'aml-pass': transfer_funds requested 1, denied by a hook 0, handler ran 1
20:54:17  Run 'aml-pass': refunds [], transfers [('ACC-5521', 2000.0)], escalations [], AML results {'ACC-5521': 'pass'}
```

No `SDK error:` line, so `main()` returned `0`.

---

### 4.7 `__main__`

```python
if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

---

### 4.8 The payment tools: no policy anywhere (from `hooks_setup.py`)

```python
    @tool("process_refund", "Refunds an amount to the customer for an order.",
          {"type": "object", "properties": {"order_id": {"type": "string", "pattern": "^LS-\\d{4}$"}, "amount": amount},
           "required": ["order_id", "amount"]})
    async def process_refund(args: dict[str, Any]) -> dict[str, Any]:
        state.calls["process_refund"] += 1  # reached only if no PreToolUse hook denied the call
        refund = {"id": f"RF-{len(state.refunds) + 1:04d}", "order_id": args["order_id"], "amount": float(args["amount"])}
        state.refunds.append(refund)
        return text_result(f"Refund {refund['id']} of ${refund['amount']:,.2f} for order {refund['order_id']} processed.")
...
    async def aml_check(args: dict[str, Any]) -> dict[str, Any]:
        state.calls["aml_check"] += 1
        account = str(args.get("account_id", ""))
        if account == "ACC-5521":
            return text_result(json.dumps({"account_id": account, "result": "pass"}))
        if account == "ACC-6620":  # a fail is a NORMAL result: an error result would fire PostToolUseFailure instead
            return text_result(json.dumps({"account_id": account, "result": "fail",
                                           "note": "Name matches a sanctions watchlist entry."}))
        return text_result(f"Unknown account '{account}'.", is_error=True)
...
    async def transfer_funds(args: dict[str, Any]) -> dict[str, Any]:
        state.calls["transfer_funds"] += 1
        transfer = {"id": f"TR-{len(state.transfers) + 1:04d}", "to_account": args["to_account"],
                    "amount": float(args["amount"])}
        state.transfers.append(transfer)
        return text_result(f"Transfer {transfer['id']} of ${transfer['amount']:,.2f} to {transfer['to_account']} sent.")
```

**Why it matters:**
- **The handlers just do the job.** No limit check, no AML check. Policy lives in one place, the hooks, and can change without touching the tools.
- **`state.calls` counts real executions,** the evidence that a denied call never ran ("reached only if no PreToolUse hook denied the call").
- **An AML "fail" is a normal result,** not an error, so `record_aml()` (a `PostToolUse` hook) sees it. The comment notes that an error result would fire a different event, `PostToolUseFailure`.
- **The descriptions mention no policy.** `transfer_funds` says only "Sends money ...". Unlike topic 04, no tool description carries the rule.

The `SYSTEM_PROMPTS["payments"]` prompt is equally neutral: "Use process_refund to refund an order, aml_check to screen a beneficiary account, and transfer_funds to send money. Never guess an ID or an amount."

---

### 4.9 `build_hook_options()` and `run_agent()` (from `hooks_setup.py`)

Both are the same as in POC 1 (its article walks through them). Three options matter here:

```python
        allowed_tools=tool_names,  # pre-approve every tool, so only a hook can block one (E1)
        hooks=hooks,  # {"PreToolUse": [...], "PostToolUse": [...]}; None = no hooks (the baseline)
        setting_sources=[],  # ignore settings files and their shell hooks; our callback hooks still run
```

| Option | Here | Why |
|--------|------|-----|
| `allowed_tools` | all three payment tools | Nothing waits for permission, so only a hook can stop a call |
| `hooks` | `build_policy_hooks(state, refund_check)` | The policy |
| `setting_sources=[]` | no settings files | No shell hooks from `~/.claude`; only the callbacks passed in code |

`run_agent()` gives `main()` the `tool_results` list, each item with the `tool_use_id`, the tool `name` and `is_error`. That's how `main()` knows which requested calls were denied.

---

### 4.10 `common.py`: settings and a single-agent log

Same as POC 1: defaults `claude-sonnet-5-5`, `max_turns` `15`, `max_budget_usd` `0.50`; `log_model_io(message)` without agent tags.

| Source | Log line | Lines in this log |
|--------|----------|-------------------|
| `log_model_io()`: `ThinkingBlock` | `MODEL OUTPUT  thinking` | 2 (`refund-post`, `aml-pass`) |
| `log_model_io()`: `TextBlock` | `MODEL OUTPUT  text` | 4 (one per run, plus `aml-pass`'s line before its tools) |
| `log_model_io()`: `ToolUseBlock` | `MODEL OUTPUT  tool_use` | 6: 4 `process_refund`, 1 `aml_check`, 1 `transfer_funds` |
| `log_model_io()`: `ToolResultBlock` | `MODEL INPUT   tool_result` | 6: 5 with `is_error=None`, 1 with `is_error=True` (the deny) |
| `log_model_io()`: `ResultMessage` | `MODEL OUTPUT  stop_reason` | 3 |
| `deny()` | `PreToolUse hook denied the call ...` | 1 |
| `refund_limit_after()` | `PostToolUse fired after the refund ran ...` | 1 |

---

## 5. Turn-by-turn trace of each run (real output)

Each trace below is the real run from `logs/poc2_policy_test_20261113_205350.log` (2026-11-13, 20:53:50 to 20:54:17: 27 seconds for all three `query()` calls). Each log line points back to the statement that wrote it (section 3.2's table).

How to read the log blocks:
- In the log file, every entry is one line. Here, each entry's header (time, `MODEL INPUT` or `MODEL OUTPUT`, kind) stays on its first line, and its payload is pretty-printed underneath.
- Long text wraps onto a deeper-indented line.
- `...` marks text that was cut.

### 5.1 Run `refund-pre`: the limit in `PreToolUse`

Section 3.2 shows this run in full, message by message. In short:

| Step | Claude asked for | Hook | Handler | Claude received |
|------|------------------|------|---------|-----------------|
| 1 | `process_refund('LS-4410', 350)` | `refund_limit()`: `350 ≤ 500` → `{}` | ran: `RF-0001` | `Refund RF-0001 of $350.00 ... processed.` |
| 2 | `process_refund('LS-4475', 1200)` | `refund_limit()`: opens `ESC-0001`, `deny(...)` | **did not run** | `PreToolUse:... hook error: Refund not processed: ... Escalation ESC-0001 ...`, `is_error=True` |
| 3 | *(text)* | | | "I processed one refund. The other needs human approval first. ..." |

**Variable values at the end of the run:**

| Variable / field | Value |
|------------------|-------|
| `state.calls["process_refund"]` | `1` |
| `state.denials` | `{"toolu_0116V4Rt3fmZhTMUYTy8YD55": "Refund not processed: ..."}` |
| `state.refunds` | `[{"id": "RF-0001", "order_id": "LS-4410", "amount": 350.0}]` |
| `state.escalations` | `[{"id": "ESC-0001", "order_id": "LS-4475", "amount": 1200.0, "reason": "refund over $500"}]` |
| `run["subtype"]` / `stop_reason` | `"success"` / `"end_turn"` |

**Lessons from the real data:**
- **The $1,200 refund never ran.** `requested 2, denied by a hook 1, handler ran 1`, and only LS-4410 is in the refunds.
- **The block came with a redirect.** `ESC-0001` was opened by the hook, before Claude knew about it.
- **Claude did what the reason said:** told the user about the escalation, and didn't retry or split.

### 5.2 Run `refund-post`: the same limit in `PostToolUse` (the anti-pattern)

**Real log:**

```
20:53:57  MODEL INPUT   prompt
          Please process two refunds: $350.00 for order LS-4410, which arrived late, and $1,200.00
            for order LS-4475, which arrived damaged.

20:54:00  MODEL OUTPUT  tool_use
          mcp__payments__process_refund {'order_id': 'LS-4410', 'amount': 350}
          (id=toolu_01Si9rwHwMrW1TbeBCLmG1xQ)
20:54:00  MODEL INPUT   tool_result
          [{'type': 'text', 'text': 'Refund RF-0001 of $350.00 for order LS-4410 processed.'}]
          (tool_use_id=toolu_01Si9rwHwMrW1TbeBCLmG1xQ, is_error=None)
20:54:00  MODEL OUTPUT  tool_use
          mcp__payments__process_refund {'order_id': 'LS-4475', 'amount': 1200}
          (id=toolu_017hBWa6pzjU3eA2vfTEEpsp)
20:54:00  PostToolUse fired after the refund ran: too late to block it. Enforce policy in
            PreToolUse.
20:54:00  MODEL INPUT   tool_result
          [{'type': 'text', 'text': 'Refund RF-0002 of $1,200.00 for order LS-4475 processed.'}]
          (tool_use_id=toolu_017hBWa6pzjU3eA2vfTEEpsp, is_error=None)

20:54:05  MODEL OUTPUT  thinking
          The hook notice came in as a separate system message, not inside a tool result, so I'll
            treat it as legitimate: refunds over $500 need human approval. The $350 refund went
            through, but the $1,200 one (RF-0002) was flagged even though the tool reported it as
            processed. I won't retry it; I'll report that it needs sign-off.

20:54:05  MODEL OUTPUT  text
          The $350.00 refund for LS-4410 went through, but the $1,200.00 refund for LS-4475 needs
            human approval before it can stand.

          - **LS-4410 (late arrival):** Refund RF-0001 for $350.00 was processed.
          - **LS-4475 (damaged):** The tool reported refund RF-0002 for $1,200.00 as processed.
            Right after that, a policy hook returned a blocking error: "Refunds over $500 need
            human approval." No approval was obtained, so I'm treating this refund as
            unauthorized. The tool output and the hook conflict, so I can't confirm whether the
            money actually moved.

          I haven't retried or tried to work around the block. Someone should check the status of
            RF-0002 in the payments system. If it did go out, it may need to be reversed or
            approved after the fact. ...
20:54:05  MODEL OUTPUT  stop_reason  end_turn  (loop result: success)

20:54:06  Run 'refund-post': process_refund requested 2, denied by a hook 0, handler ran 2
20:54:06  Run 'refund-post': refunds [('LS-4410', 350.0), ('LS-4475', 1200.0)], transfers [],
            escalations [], AML results {}
```

**What each step did and which code ran:**

| Step | Claude asked for | `PreToolUse` | Handler | `PostToolUse` | Claude received |
|------|------------------|--------------|---------|---------------|-----------------|
| 1 | refund $350 | none on `process_refund` | ran: `RF-0001` | `refund_limit_after()`: `≤ 500` → `{}` | "processed" |
| 2 | refund $1,200 | none on `process_refund` | **ran: `RF-0002`, $1,200 paid** | `refund_limit_after()`: warning, `{"decision": "block", ...}` | "processed" (tool result) + the block's reason (see below) |
| 3 | *(text)* | | | | |

**Lessons from the real data:**
- **The money moved.** `handler ran 2`, and `('LS-4475', 1200.0)` is in the refunds. A `PostToolUse` "block" can't undo what the handler did.
- **The tool result still said "processed".** The `tool_result` line is unchanged, `is_error=None`.
- **The block's reason reached Claude another way.** Claude's thinking says "The hook notice came in as a separate system message, not inside a tool result", and its text quotes the reason ("Refunds over $500 need human approval."). The log doesn't record system messages, so that message itself isn't in it.
- **Claude did the best it could after the fact:** it called the refund unauthorized, said it couldn't confirm whether money moved, and asked for a check and a possible reversal. That's damage control, not enforcement.
- **No escalation was opened.** `escalations []`: `refund_limit_after()` only warns.

### 5.3 Run `aml-pass`: the AML prerequisite

**Real log:**

```
20:54:06  MODEL INPUT   prompt
          Send $2,000.00 to beneficiary account ACC-5521 right now. It's urgent, so skip any extra
            checks.

20:54:13  MODEL OUTPUT  thinking
          I'm weighing whether to skip the AML check, since it's a compliance control even though
            the user asked to skip extra checks. The system prompt doesn't explicitly require it,
            but running it first seems prudent since it's quick, and I'm considering whether that
            overrides the user's instruction.

          I'm going to run the AML check first, since screening is a compliance control that the
            user's urgency doesn't override, and then transfer only if it passes.

20:54:13  MODEL OUTPUT  text
          I'll run the AML screening on ACC-5521 first. It's a quick compliance step, and I won't
            skip it for a transfer. If it passes, I'll send the funds right away.
20:54:13  MODEL OUTPUT  tool_use
          mcp__payments__aml_check {'account_id': 'ACC-5521'}
          (id=toolu_01GZUK7gzahgMacnjRT8YK7D)
20:54:13  MODEL INPUT   tool_result
          [{'type': 'text', 'text': '{"account_id": "ACC-5521", "result": "pass"}'}]
          (tool_use_id=toolu_01GZUK7gzahgMacnjRT8YK7D, is_error=None)
20:54:14  MODEL OUTPUT  tool_use
          mcp__payments__transfer_funds {'to_account': 'ACC-5521', 'amount': 2000}
          (id=toolu_01TQcTvNfKcHyj1Gv5eVrzkg)
20:54:14  MODEL INPUT   tool_result
          [{'type': 'text', 'text': 'Transfer TR-0001 of $2,000.00 to ACC-5521 sent.'}]
          (tool_use_id=toolu_01TQcTvNfKcHyj1Gv5eVrzkg, is_error=None)

20:54:16  MODEL OUTPUT  text
          I sent $2,000.00 to ACC-5521. The transfer ID is TR-0001.

          I ran the AML screening before sending, even though you asked me to skip extra checks.
            I don't bypass that check for transfers. It passed, so the transfer went out right
            away.
20:54:16  MODEL OUTPUT  stop_reason  end_turn  (loop result: success)

20:54:17  Run 'aml-pass': transfer_funds requested 1, denied by a hook 0, handler ran 1
20:54:17  Run 'aml-pass': refunds [], transfers [('ACC-5521', 2000.0)], escalations [], AML
            results {'ACC-5521': 'pass'}
```

**What each step did and which code ran:**

| Step | Claude asked for | `PreToolUse` | Handler | `PostToolUse` | State after |
|------|------------------|--------------|---------|---------------|-------------|
| 1 | `aml_check('ACC-5521')` | none on `aml_check` | ran: `pass` | `record_aml()`: stores the result | `aml_results = {"ACC-5521": "pass"}` |
| 2 | `transfer_funds('ACC-5521', 2000)` | `aml_gate()`: pass found → `{}` | ran: `TR-0001` | none on `transfer_funds` | `transfers = [("ACC-5521", 2000.0)]` |
| 3 | *(text)* | | | | |

**Lessons from the real data:**
- **Claude ran the check on its own.** No prompt or description asked for AML screening, and the user asked to skip it. Claude's thinking reasoned its way to screening first. That is the probabilistic layer working, this time.
- **So the gate never had to deny.** `denied by a hook 0`. The run shows the allow path, not the block → check → retry path the run table's comment describes.
- **The hooks still cooperated correctly.** `record_aml()` wrote `{'ACC-5521': 'pass'}` from the real result, and `aml_gate()` read it before allowing the transfer. Without that state, the transfer would have been denied.
- **The state is the guarantee.** Whether Claude checks first or not, `transfer_funds` can only run after a pass recorded in this run.

### 5.4 The path this log didn't show: a denied transfer

No run called `transfer_funds` before `aml_check`. If one had, `aml_gate()` would have found no result for the account and returned (from the code, **not** from the log):

```
deny(state, tool_use_id, "AML check required: no passing aml_check for ACC-5521 in this session. "
                         "Call aml_check for it first; transfer_funds runs only after a pass.")
→ log.warning("PreToolUse hook denied the call (id=...): its handler will not run")
→ Claude receives the reason as an error tool result; transfer_funds' handler does not run
```

Claude would then call `aml_check`, `record_aml()` would store the pass, and the retried `transfer_funds` would pass `aml_gate()`. For a failing account (`ACC-6620`, the commented-out `aml-fail` run), every attempt would stay denied with "Do not retry; tell the user that compliance must review it."

### 5.5 The three runs side by side

| | `refund-pre` | `refund-post` | `aml-pass` |
|-|--------------|---------------|------------|
| Refund limit checked in | `PreToolUse` | `PostToolUse` (anti-pattern) | `PreToolUse` |
| Tool calls | 2 × `process_refund` | 2 × `process_refund` | `aml_check`, `transfer_funds` |
| Denied by a hook | 1 | 0 | 0 |
| Handlers that ran | 1 refund | 2 refunds | 1 check, 1 transfer |
| Hook warning lines | `PreToolUse hook denied ...` | `PostToolUse fired after the refund ran ...` | none |
| Money moved | $350 | $350 + **$1,200** | $2,000 (after a pass) |
| Escalations | `ESC-0001` | none | none |
| `thinking` lines | 0 | 1 | 1 |
| Final `subtype` / `stop_reason` | `success` / `end_turn` | `success` / `end_turn` | `success` / `end_turn` |
| Wall time (from log) | about 6 s | about 8 s | about 10 s |

The log has no `SDK error:`, `Safety cap hit:` or `The run failed:` line, so `main()` returned `0`.

---

## 6. Agentic AI concepts recap

| Concept | How this POC shows it |
|---------|-----------------------|
| **`PreToolUse` for policy** | `refund_limit()` and `aml_gate()` decide before the handler runs. |
| **`permissionDecision: "deny"`** | The handler never runs; `handler ran 1` for 2 requests. |
| **`permissionDecisionReason`** | What Claude receives: what happened, why, what to do, what not to do. |
| **Deterministic redirect** | The hook opens `ESC-0001` itself. |
| **`PostToolUse` is too late** | `refund_limit_after()`: the $1,200 refund was paid before it ran. |
| **Hooks sharing state** | `record_aml()` (`PostToolUse`) writes `aml_results`; `aml_gate()` (`PreToolUse`) reads it. |
| **Hooks over `allowed_tools`** | Every payment tool is pre-approved; a hook's deny still wins. |
| **Full MCP matchers** | `mcp__payments__process_refund`; a bare name would silently match nothing. |
| **Policy outside the tools** | No handler, prompt or description mentions the limits; the hooks are the only enforcement. |
| **Evidence from three sources** | requested (stream), denied (hooks), ran (handlers). |
| **Probabilistic vs deterministic** | Claude chose to screen first in `aml-pass`; the gate would have enforced it anyway. |

---

## 7. Common mistakes this POC helps you avoid

1. **Blocking in `PostToolUse`.** The action has already happened: `('LS-4475', 1200.0)` was paid in `refund-post`.
2. **Putting policy only in the prompt.** Compliance needs 100%; a prompt gets most of the way. Here no prompt mentioned the policy at all.
3. **A deny without a useful reason.** Claude needs to know what to tell the user and what not to try ("Do not retry or split this refund").
4. **Blocking without a redirect.** Let the hook open the escalation, so the human path doesn't depend on the model.
5. **Allowing split refunds.** Track the escalated order and deny further refunds for it.
6. **Matching hooks by bare tool name.** MCP tools are `mcp__<server>__<tool>`; a bare name matches nothing, silently.
7. **Thinking `allowed_tools` overrides hooks.** It doesn't; pre-approved tools still pass through `PreToolUse`.
8. **Letting the model assert a prerequisite.** The AML pass must be recorded by code that saw the real `aml_check` result.
9. **Sharing prerequisite state across sessions or accounts.** One `HookState` per run; a pass for one account unlocks no other.
10. **Treating an AML "fail" as an error result.** A fail is a normal result, so `PostToolUse` sees it; an error result fires a different event.
11. **Declaring a gate tested when it never fired.** `aml-pass` passed without a denial; test the deny path separately.

---

## 8. Claude Architect exam lens

### 8.1 What the exam tests on this topic

The objectives come from `curriculum/01-Agentic-Architecture-&-Orchestration/05-raw-Agent-SDK-Hooks.md`. POC 1 covers objectives 1 to 3 (`PostToolUse` normalization); POC 2 covers 4 to 6.

| Exam objective | What a correct answer looks like | Where this POC shows it |
|----------------|----------------------------------|-------------------------|
| 4. A `PreToolUse` hook that blocks refunds over $500 and redirects to a human | A `PreToolUse` callback inspects the amount, returns `permissionDecision: "deny"` with a `permissionDecisionReason`, and the refund never executes. Using `PostToolUse` for blocking is the exam's named wrong answer: the action has already happened. | `refund_limit()`, `deny()`; run `refund-pre` vs run `refund-post` |
| 5. A second `PreToolUse` hook: no `transfer_funds` until `aml_check` passed this session | A `PreToolUse` hook on `transfer_funds` denies until session state records a pass; a `PostToolUse` hook on `aml_check` sets that state. Prompts reach about 95%; regulation needs 100%. | `aml_gate()`, `record_aml()`, `state.aml_results`; run `aml-pass` |
| 6. Test both hooks: blocked operations never execute; the model gets the reason; the same operation runs once the prerequisite is met | Handlers of denied calls stay untouched; the reason reaches the model; after the prerequisite, the call runs. | `requested / denied by a hook / handler ran` lines; the refund deny in `refund-pre`. The transfer deny didn't occur in this run (Claude checked first); section 5.4 shows it from the code |

> **Exam tip:** in hook questions, check the direction first. "Block an action" → `PreToolUse` with `permissionDecision: "deny"`. "Change or record a result" → `PostToolUse`. Then check the matcher (the full `mcp__server__tool` name) and where the prerequisite state comes from (a hook that saw the real result, never the model's claim).

### 8.2 The same policies with the raw Messages API

The raw Messages API has no hooks; your tool executor is the only place a call can be stopped. The pre-execution check goes before the side effect, and the observation goes after the call returns.

```python
import json

import anthropic

client = anthropic.Anthropic()
REFUND_LIMIT = 500


def execute(block, session: dict) -> tuple[str, bool]:
    """Your code runs every tool call. "PreToolUse" = before the side effect; "PostToolUse" = after it."""
    name, args = block.name, block.input
    # --- the PreToolUse step: policy, before anything happens ---
    if name == "process_refund" and float(args["amount"]) > REFUND_LIMIT:
        escalation_id = open_escalation(args["order_id"], args["amount"])  # your human-review queue
        return (f"Refund not processed: refunds over ${REFUND_LIMIT} need human approval. "
                f"Escalation {escalation_id} is open."), True
    if name == "transfer_funds" and session["aml"].get(args["to_account"]) != "pass":
        return "AML check required: call aml_check for this account first.", True
    # --- run the tool ---
    output = run_payment_tool(name, args)
    # --- the PostToolUse step: record what the tool returned ---
    if name == "aml_check":
        result = json.loads(output)
        session["aml"][result["account_id"]] = result["result"]
    return output, False
```

| Raw Messages API (you write it) | Agent SDK (`poc2_policy_test.py`) |
|---------------------------------|-----------------------------------|
| An `if` before `run_payment_tool()` | A `PreToolUse` hook (`refund_limit()`, `aml_gate()`) |
| Return the reason as an error `tool_result` | Return `permissionDecision: "deny"` + `permissionDecisionReason` |
| Code after `run_payment_tool()` | A `PostToolUse` hook (`record_aml()`) |
| `session` dict passed to `execute()` | `HookState`, captured by the callbacks in `build_policy_hooks()` |
| You route calls by `name` | `HookMatcher(matcher="mcp__payments__...")` |
| Nothing to pre-approve | `allowed_tools` pre-approves; hooks still run first |

In both forms, a check placed after the side effect can only report it.

### 8.3 Scenario questions

Try each one before reading the answer. These questions were written for this article to match the curriculum objectives above. They are not official exam questions.

---

**Scenario 1: Blocking large refunds**

A support agent must never issue a refund over $500 without human approval. Which Agent SDK design guarantees that?

- A. A system prompt rule: "Never refund more than $500."
- B. A `PostToolUse` hook on the refund tool that flags refunds over $500.
- C. A `PreToolUse` hook on the refund tool that returns `permissionDecision: "deny"` with a reason for amounts over $500, and opens a human escalation.
- D. A lower `max_turns`, so the agent has fewer chances to refund.

**Answer: C.** Only a pre-execution deny stops the refund before it happens. A is probabilistic; B runs after the money moved; D is unrelated. *POC link:* `refund_limit()` in `build_policy_hooks()`; run `refund-pre`: `requested 2, denied by a hook 1, handler ran 1`.

---

**Scenario 2: The PostToolUse "block"**

A team implemented the refund limit in a `PostToolUse` hook that returns `{"decision": "block", "reason": ...}`. In testing, the agent correctly tells users that large refunds "need approval". What is the problem?

- A. None: the user is informed.
- B. The refund has already been processed when `PostToolUse` runs; the block only informs the model afterwards.
- C. `PostToolUse` hooks can't return a reason.
- D. The hook should raise an exception instead.

**Answer: B.** The message is right and the money is gone. *POC link:* run `refund-post`: the warning `PostToolUse fired after the refund ran: too late to block it`, the tool result `Refund RF-0002 of $1,200.00 ... processed.`, and `refunds [... ('LS-4475', 1200.0)]`.

---

**Scenario 3: The hook that never runs**

A `PreToolUse` hook is registered with `HookMatcher(matcher="process_refund", ...)`. The tool is an MCP tool on a server named `payments`. Large refunds still go through, and no error appears. Why?

- A. `PreToolUse` doesn't support MCP tools.
- B. The matcher must match the full tool name, `mcp__payments__process_refund`; a bare name matches no tool, so the hook silently never runs.
- C. The tool is in `allowed_tools`, which skips hooks.
- D. The hook must be async.

**Answer: B.** Silent mismatches are why the code uses the full names from `PAYMENT_TOOLS`. C is wrong: hooks run before the permission rules. *POC link:* the comment above the matchers in `build_policy_hooks()` ("process_refund alone would match no tool, and the hook would silently never run").

---

**Scenario 4: Pre-approved, still blocked?**

All payment tools are listed in `allowed_tools`. Will a `PreToolUse` hook's deny still stop a call?

- A. No: `allowed_tools` approves the call before hooks run.
- B. Yes: hooks run before the permission rules, so a deny wins over `allowed_tools`.
- C. Only if `permission_mode` is set to `plan`.
- D. Only for built-in tools.

**Answer: B.** Pre-approval removes the permission prompt; it doesn't bypass hooks. *POC link:* `allowed_tools=tool_names` in `build_hook_options()` ("so only a hook can block one"), and the deny in run `refund-pre`.

---

**Scenario 5: AML before transfers**

Regulation requires an AML screening pass before any transfer to a beneficiary. Which design enforces it?

- A. A prompt rule: "Always run aml_check before transfer_funds."
- B. A `PreToolUse` hook on `transfer_funds` that denies unless session state records a pass for that account, plus a `PostToolUse` hook on `aml_check` that records the result.
- C. A `PostToolUse` hook on `transfer_funds` that checks for a prior AML pass.
- D. Let the model pass `aml_passed: true` as a transfer argument.

**Answer: B.** The state comes from the real check, and the gate acts before the transfer. A is probabilistic (about 95%); C acts after the money moved; D trusts the model's claim. *POC link:* `aml_gate()` and `record_aml()` sharing `state.aml_results`; run `aml-pass`: `AML results {'ACC-5521': 'pass'}` before `TR-0001`.

---

**Scenario 6: A pass for the wrong account**

An agent screens account A (pass), then tries to transfer to account B. What should happen?

- A. Allow it: an AML check passed in this session.
- B. Deny it: the pass is recorded per account, and B has none.
- C. Allow it if the amount is small.
- D. Ask the model whether B was checked.

**Answer: B.** A prerequisite is about the specific entity. *POC link:* `aml_gate()` reads `state.aml_results.get(account)`, with the comment "a pass for one account unlocks no other".

---

**Scenario 7: Splitting to get under the limit**

After a $1,200 refund is denied, the agent tries two refunds of $600 and $600, then three of $400. What should the hook do?

- A. Allow refunds under $500.
- B. Deny further refunds for an order that already has an open escalation, whatever the amount.
- C. Add up refunds per session and allow up to $500.
- D. Rely on the deny reason telling the model not to split.

**Answer: B.** The escalation marks the order for human review; any refund for it waits. D helps but isn't enforcement. *POC link:* `refund_limit()`: `if amount <= REFUND_LIMIT and escalation is None`, with the comment "an open escalation also blocks a split refund".

---

**Scenario 8: What the model receives on a deny**

A `PreToolUse` hook denies a call. What does the model get, and what should be in it?

- A. Nothing: the call just disappears.
- B. The hook's `permissionDecisionReason` as that call's (error) result. It should say what didn't happen, why, what to tell the user, and what not to retry.
- C. A generic "permission denied".
- D. The handler's normal output.

**Answer: B.** The reason is the model's only guidance after a block. *POC link:* run `refund-pre`'s error result: `... Refund not processed: refunds over $500 need human approval. Escalation ESC-0001 is open ...; tell the customer a human agent will review it. Do not retry or split this refund.`, with `is_error=True`.

---

**Scenario 9: Proving the handler never ran**

How can a team prove, in a test, that a denied tool call never executed?

- A. Check that the model's final message says so.
- B. Count handler executions in state written by the handler itself, and compare with the calls requested and the denials recorded by the hook.
- C. Check that the tool result has `is_error=True`.
- D. Search the log for the hook's warning.

**Answer: B.** Independent counts from the stream, the hooks and the handlers. C and D show a denial was issued, not that the handler stayed idle. *POC link:* `main()`'s line `requested %d, denied by a hook %d, handler ran %d`, from `run["tool_results"]`, `state.denials` and `state.calls`.

---

**Scenario 10: The gate that never fired**

A test of an AML gate passes: the agent screened the account, then transferred. The gate logged no denials. Is the gate tested?

- A. Yes: the transfer only happened after a pass.
- B. Only the allow path is. Test the deny path too: a transfer without a recorded pass must be denied, with the handler not running.
- C. No: the gate must be broken, since it never fired.
- D. Yes, as long as the prompt mentions AML.

**Answer: B.** A model that does the right thing on its own doesn't exercise the gate's deny branch. *POC link:* run `aml-pass`: `denied by a hook 0`; Claude screened first on its own (its thinking line); section 5.4 shows the deny path from the code.

---

### 8.4 Quick-recall cheat sheet

```
PreToolUse             → before the handler; sees tool_input; can deny → the handler NEVER runs
deny                   → {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                          "permissionDecision": "deny", "permissionDecisionReason": "..."}}
reason                 → what Claude receives (as an error result): what, why, what to tell, what not to retry
redirect               → the hook opens the escalation itself: deterministic, like the block
PostToolUse            → after the handler: record or rewrite a result; NEVER for blocking (money already moved)
shared state           → PostToolUse on aml_check writes the pass; PreToolUse on transfer_funds reads it
state rules            → written by code that saw the real result; per account; per session
allowed_tools          → only pre-approves; hooks run first, and a deny wins
matcher                → full MCP name (mcp__payments__process_refund); a bare name silently matches nothing
evidence               → requested (stream) vs denied (hook state) vs ran (handler state)
test both paths        → allow AND deny; a model that complies on its own never tests the gate
```

---

## 9. How to run it

```bash
cd 01-Agentic-Architecture-Orchestration/05-Agent-SDK-Hooks
source .venv/bin/activate        # the folder's venv (claude-agent-sdk 0.2.181)
python poc1_normalize_test.py    # paid: POC 1, the PostToolUse normalization hook
python poc2_policy_test.py       # paid: 3 short runs, 3 query() calls, uses ANTHROPIC_API_KEY from .env
```

- Both scripts call the API. This folder has no free offline demo.
- `.env` needs `ANTHROPIC_API_KEY`; copy `.env.example` and fill it in. `MODEL_ID`, `MAX_TURNS` and `MAX_BUDGET_USD` fall back to `claude-sonnet-5-5`, `15` and `0.50`.
- To see a failing AML account, uncomment the `aml-fail` line in `RUNS`. It adds a fourth paid call.
- Every model input and output, each hook warning and the per-run counts go to the console and to `logs/poc2_policy_test_<date>_<time>.log`. Whether Claude screens before transferring varies; the counts show what the hooks did either way.
- The exit code is `0` when all runs finish. It's `1` on a setup failure or an SDK runtime failure (`ClaudeSDKError`).
