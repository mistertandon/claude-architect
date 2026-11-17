# POC 2: The Handoff Is All the Human Sees

> **File:** `poc2_handoff_test.py` (with `support_setup.py` and `common.py`)
> **Domain:** 01 Agentic Architecture & Orchestration → 04 Workflow Enforcement and Handoff
> **SDK:** Claude Agent SDK for Python (`claude-agent-sdk >=0.2.174,<0.3`; 0.2.181 in the folder's `.venv`)
> **Page:** https://claude.ai/artifact/GGgn9XecB6M2ji3KqV7wPS

---

## 1. What this POC proves

Some requests need a person: a billing dispute, an account change. The agent finishes what it may do itself and hands the rest to a human with `escalate_to_human`. The human never sees the conversation, so the handoff must stand on its own. Every claim below is checked against one real run: `logs/poc2_handoff_test_20261113_205100.log`.

| # | Idea | Where it shows up in the code |
|---|------|------------------------------|
| 1 | **A handoff is a structured tool call with five required fields:** customer ID, conversation summary, root cause, refund amount, recommended action. | `HANDOFF_FIELDS`; the `required` list in `escalate_to_human`'s schema |
| 2 | **Completeness is checked in code, inside the handler.** Empty fields, placeholder text and back-references such as "see above" are rejected, and an invalid handoff never reaches the human. | `validate_handoff()` called in `escalate_to_human()` |
| 3 | **A rejected handoff is an error result Claude can fix.** It says which field failed and why; Claude rewrites and calls again. | `Handoff rejected: ... Fix and call escalate_to_human again.`; run 1 |
| 4 | **The agent does what it may and hands off only the rest.** The cracked-lamp return is refunded by the agent; the duplicate charge and the address change go to the human. | `HANDOFF_RULE`; run 2 |
| 5 | **One handoff covers every concern.** A three-part request ends in one handoff that lists all three, each with its status. | the `escalate_to_human` description; `concern_coverage()` |
| 6 | **Independent lookups run in one response.** Two `lookup_order` calls (and, in run 1, `get_customer` with `lookup_order`) were sent together. | `readOnlyHint=True` on the lookups |

The pattern in one picture:

```
request ──▶ agent ──┬─ lookups (in parallel) ─▶ facts
                    ├─ what it may do (refund a return, gated) ─▶ done
                    └─ what it may not ─▶ escalate_to_human(5 fields) ─▶ validate_handoff() ─┬─ rejected → fix, call again
                                                                                              └─ queued → the human's ONLY input
```

---

## 2. The files involved

```
04-Workflow-Enforcement-and-Handoff/
├── .env / .env.example     ← ANTHROPIC_API_KEY, MODEL_ID, MAX_TURNS, MAX_BUDGET_USD
├── requirements.txt        ← claude-agent-sdk >=0.2.174,<0.3 and python-dotenv
├── common.py               ← Settings, load_settings(), setup_logging(), log_model_io()
├── support_setup.py        ← mock data, SupportSession, the 4 tools, validate_handoff(), prompts, options, run_support()
├── poc1_gate_test.py       ← POC 1: the refund gate (not covered here)
├── poc2_handoff_test.py    ← entry point: 2 runs ending in a handoff
└── logs/
    └── poc2_handoff_test_20261113_205100.log   ← the real run used in sections 3.2 and 5
```

Every snippet in this article is copied from these files, logging statements included. Each logging statement is named with the log line it writes.

The responsibilities split like this:
- `common.py` covers **configuration and observability** (single-agent log lines, no agent tag).
- `support_setup.py` covers **capabilities** (the four tools), **state** (`SupportSession`), **enforcement** (the refund gate from POC 1 and the handoff validator), the **prompts**, the **options** and the agent loop.
- `poc2_handoff_test.py` covers **the experiment**: two requests and a check of what each stored handoff covers.

---

## 3. End-to-end execution flow

### 3.1 The big picture

```
python poc2_handoff_test.py
        │
        ▼
asyncio.run(main())                                                      [poc2_handoff_test.py]
        │
        ├─▶ load_settings(), setup_logging("poc2_handoff_test")          [common.py]
        │
        └─▶ for prompt, concerns in RUNS:            (DISPUTE_PROMPT, MULTI_PROMPT)
               │
               ├─▶ session = SupportSession()                            [support_setup.py]
               ├─▶ options = build_support_options(settings, session, handoff=True)
               │       ├─ system_prompt = SYSTEM_PROMPT + VERIFY_RULE + HANDOFF_RULE
               │       └─ mcp_servers   = 4 tools: get_customer, lookup_order, process_refund (gated), escalate_to_human
               ├─▶ run_support(prompt, options)                          → one query() call
               ├─▶ log.info("Refunds paid: %s · handoffs stored: %d")    reads session.refunds, session.handoffs
               └─▶ for handoff in session.handoffs:
                      log.info("Handoff covers %s · amount left for the human: $%.2f",
                               concern_coverage(handoff, concerns), handoff["refund_amount"])
```

Inside `run_support()`, for the escalation. The right-hand column names the log line each step writes.

```
run_support(prompt, options)                                                          [support_setup.py]
   │
   ├─ log.info("MODEL INPUT   prompt ...")                                          → log: prompt
   └─▶ async for message in query(prompt=prompt, options=options):
          │
          │   ┌────────────────────── SDK-owned: the agent loop ───────────────────────────┐
          │   │ lookups (get_customer, lookup_order) → your handlers                        │  → log: tool_use / tool_result
          │   │ process_refund (if a return is due) → the gate, then pay                    │  → log: tool_use / tool_result
          │   │ escalate_to_human(5 fields) → your handler                                  │  → log: tool_use
          │   │      errors = validate_handoff(args)                                        │
          │   │      errors → "Handoff rejected: ...", is_error=True  → Claude fixes it     │  → log: tool_result (is_error=True)
          │   │      none   → session.handoffs.append(args), "Handoff HO-0001 queued ..."   │  → log: tool_result
          │   │ final text for the customer, stop_reason = end_turn                         │  → log: text, stop_reason
          │   └─────────────────────────────────────────────────────────────────────────────┘
          │
          ├─ log_model_io(message)
          └─ ResultMessage success + end_turn → answer = message.result
```

### 3.2 Messages your `async for` receives (run 1, the billing dispute, real output)

Run 1 is the more instructive one: its first handoff was rejected. The values below come from the real run on 2026-11-13, recorded in `logs/poc2_handoff_test_20261113_205100.log`. Each log line comes from one statement in the code:

| Log line tag | Message class yielded by `query()` | Field logged | Written by |
|--------------|------------------------------------|--------------|------------|
| `MODEL INPUT   prompt` | *(none: the `prompt` passed to `run_support()`)* | `prompt` | `log.info("MODEL INPUT   prompt ...")` in `run_support()` (`support_setup.py`) |
| `MODEL OUTPUT  thinking` | `AssistantMessage` → `ThinkingBlock` | `block.thinking`, only when non-empty | `log_model_io()` (`common.py`) |
| `MODEL OUTPUT  text` | `AssistantMessage` → `TextBlock` | `block.text` | `log_model_io()` |
| `MODEL OUTPUT  tool_use` | `AssistantMessage` → `ToolUseBlock` | `block.name`, `block.input`, `block.id` | `log_model_io()` |
| `MODEL INPUT   tool_result` | `UserMessage` → `ToolResultBlock` | `block.content`, `block.tool_use_id`, `block.is_error` | `log_model_io()` |
| `MODEL OUTPUT  stop_reason` | `ResultMessage` | `message.stop_reason`, `message.subtype` | `log_model_io()` |
| `Refunds paid: [...] · handoffs stored: N` | *(none: Python reads the session)* | `session.refunds`, `session.handoffs` | `log.info(...)` in `main()` (`poc2_handoff_test.py`) |
| `Handoff covers {...} · amount left for the human: $...` | *(none)* | `concern_coverage()`, `handoff["refund_amount"]` | `log.info(...)` in `main()` |
| `The run failed: ...`, `SDK error: ...` | *(none)* | the exception | `run_support()` and `main()`. None in this log |

Run 1 as it really streamed:

```
20:51:00  (input)                                                              log: prompt
            prompt = Hi, this is Dana Reyes (dana.reyes@example.com). I was charged twice for order
                       ORD-7745. Please sort it out.

20:51:03  AssistantMessage › ToolUseBlock                                      log: tool_use
            name = "mcp__support__get_customer", input = {'name_or_email': 'dana.reyes@example.com'}
            id   = "toolu_0177GLkEn7qjsTB8r8YNGBim"
20:51:03  AssistantMessage › ToolUseBlock                                      log: tool_use
            name = "mcp__support__lookup_order", input = {'order_id': 'ORD-7745'}
            id   = "toolu_01LSebuzerdaxiHxRNqYJQF4"                           ← both calls before any result
20:51:03  UserMessage › ToolResultBlock                                        log: tool_result
            content = [{'type': 'text', 'text': '{"customer_id": "CUST-1042", "name": "Dana Reyes",
                        "verified": true}'}]
            tool_use_id = "toolu_0177GLkEn7qjsTB8r8YNGBim", is_error = None
20:51:03  UserMessage › ToolResultBlock                                        log: tool_result
            content = [{'type': 'text', 'text': '{"order_id": "ORD-7745", ..., "total": 129.0,
                        "charges": [129.0, 129.0], "charged_on": "2026-10-02", "status": "delivered"}'}]
            tool_use_id = "toolu_01LSebuzerdaxiHxRNqYJQF4", is_error = None

20:51:06  AssistantMessage › ThinkingBlock                                     log: thinking
            thinking = "I've confirmed the double charge, so this is a billing dispute and needs
                        escalating. The refund doesn't apply because it's tied to a returned item ..."

20:51:07  AssistantMessage › ToolUseBlock                                      log: tool_use
            name  = "mcp__support__escalate_to_human"
            input = {'customer_id': 'CUST-1042',
                     'conversation_summary': "1. Duplicate charge on order ORD-7745 ...: needs a human. ...
                                              and no return was mentioned, so I did not process a refund. ...",
                     'root_cause': 'The order was charged twice ... The cause is unknown and probably a
                                    duplicate payment capture.',
                     'refund_amount': 129, 'recommended_action': "Review the two charges on ORD-7745. ..."}
            id    = "toolu_01PUCyrapuXi7v4HaUAeXz7H"
20:51:07  UserMessage › ToolResultBlock                                        log: tool_result
            content     = Handoff rejected: conversation_summary contains ['as mentioned']: write it for a
                          reader who never saw the conversation; root_cause contains ['unknown']: write it
                          for a reader who never saw the conversation. Fix and call escalate_to_human again.
            tool_use_id = "toolu_01PUCyrapuXi7v4HaUAeXz7H", is_error = True    ← nothing stored

20:51:09  AssistantMessage › ThinkingBlock                                     log: thinking
            thinking = "I'm checking my wording, since the phrase "as mentioned" doesn't appear verbatim
                        in what I wrote; the point is that no return was mentioned, so I'll reword it ..."

20:51:10  AssistantMessage › ToolUseBlock                                      log: tool_use
            name  = "mcp__support__escalate_to_human"
            input = { ...the same five fields, reworded: "The customer did not say the item was returned",
                      "The likely cause is a duplicate payment capture, but I could not confirm that." ... }
            id    = "toolu_01NmyHyo7VHGvwBBzyVZE3v5"
20:51:10  UserMessage › ToolResultBlock                                        log: tool_result
            content = [{'type': 'text', 'text': 'Handoff HO-0001 queued for a human agent.'}]
            tool_use_id = "toolu_01NmyHyo7VHGvwBBzyVZE3v5", is_error = None   ← session.handoffs = [this one]

20:51:12  AssistantMessage › TextBlock                                         log: text
            text = "Hi Dana, I checked order ORD-7745 and you were charged twice. ... (reference HO-0001) ..."
20:51:12  ResultMessage                                                        log: stop_reason
            stop_reason = "end_turn", subtype = "success"

20:51:13  Refunds paid: [] · handoffs stored: 1                                ← main()
20:51:13  Handoff covers {'billing dispute': True} · amount left for the human: $129.00
```

What to notice in the real data:
- **The validator ran inside the handler, and it decided.** The first `escalate_to_human` call came back `is_error=True`, and the second was queued. Only the second is in `session.handoffs`: `handoffs stored: 1`.
- **One rejection was a false positive.** The summary said "no return w**as mentioned**". `validate_handoff()` matches substrings, and "was mentioned" contains the back-reference "as mentioned". Claude's next thinking line spotted it: "the phrase "as mentioned" doesn't appear verbatim in what I wrote".
- **The other flagged honest uncertainty.** "The cause is unknown" contains the placeholder token `unknown`. Claude rewrote it as "The likely cause is a duplicate payment capture, but I could not confirm that", which is clearer for the human anyway.
- **The error result names the field and the fix,** so one retry was enough.
- **An error result's `content` is a plain string here.** The rejected call's `tool_result` was logged as text, while the successful results are lists of text blocks. The log shows that difference; it doesn't show why.
- **Two lookups in one response.** `get_customer` and `lookup_order` were both logged before either result, so Claude sent them together.
- **No refund for a dispute.** The thinking line explains it: `process_refund` is for returned items (`SYSTEM_PROMPT`), and the headphones were not returned. `refund_amount: 129` hands the decision to the human.
- **Not shown:** the `SystemMessage`, cost and turn counts are in the stream but not in the log.

> The `UserMessage` items are **not** typed by a human. They carry the tool results your handlers returned, including the rejection.

---

## 4. Code walkthrough

The snippets follow the order in which the code runs: the script first, then the module functions it calls. Where a snippet writes log lines, they're shown under it, copied from the real log (long values trimmed with `...`).

### 4.1 Module docstring: three guarantees for the human

```python
"""
POC 2 - The structured handoff
===============================
When a request needs something the agent may not do (a billing dispute, an account change), it finishes what it
can and hands the rest to a human with escalate_to_human. The human sees ONLY that handoff, so:

  * its five fields are required by the tool's JSON Schema,
  * validate_handoff() runs inside the handler and rejects empty, placeholder or "see above" text,
  * one handoff covers every concern of the request.

The POC 1 gate stays on: the return refund still needs a verified customer. Besides model I/O, the log shows
per run the refunds paid and the handoffs stored, and which concerns each handoff covers.

Run:  python poc2_handoff_test.py     (2 short API runs)
"""
```

**Why it matters:** the docstring lists three layers that protect the human: the schema (shape), the validator (content) and the instruction to cover every concern (scope). It also keeps POC 1's gate on, so the agent's own refund still needs verification.

---

### 4.2 Imports

```python
import asyncio
import sys

from claude_agent_sdk import ClaudeSDKError

from common import load_settings, log, setup_logging
from support_setup import SupportSession, build_support_options, run_support
```

The same imports as POC 1: the event loop and exit code, the SDK's base error, settings and logging, and from `support_setup` the session, the options builder and the agent loop. Everything handoff-specific lives in `support_setup.py`.

---

### 4.3 The two requests and what each handoff must mention

```python
DISPUTE_PROMPT = "Hi, this is Dana Reyes (dana.reyes@example.com). I was charged twice for order ORD-7745. Please sort it out."
MULTI_PROMPT = (
    "Hi, this is Dana Reyes (dana.reyes@example.com). Three things: 1) the Aurora desk lamp from order ORD-7731 "
    "arrived cracked, so I'm returning it and want my money back; 2) I was charged twice for order ORD-7745; "
    "3) please change my shipping address to 88 Larkspur Lane, Portland, OR 97211."
)

RUNS = [  # (prompt, concern -> the detail the handoff must mention)
    (DISPUTE_PROMPT, {"billing dispute": "ORD-7745"}),  # expect a handoff with refund_amount 129.0
    (MULTI_PROMPT, {"return": "ORD-7731", "billing dispute": "ORD-7745", "account update": "88 Larkspur Lane"}),
]
```

**Why it matters:**
- **`DISPUTE_PROMPT`** is a single concern the agent can investigate but not resolve: a billing dispute. The mock order `ORD-7745` has two charges of `129.00` against a total of `129.00`.
- **`MULTI_PROMPT`** is the exam's multi-concern test: a return the agent *can* handle, a dispute it can't, and an account change it can't. A good agent splits it into three items.
- **Each run carries its own checklist.** The dict maps each concern to one detail the handoff text must contain: an order ID, or the new street address. That's what `concern_coverage()` checks.

**Agentic concept:** request decomposition: one message, several independent concerns, each with its own outcome.

---

### 4.4 `concern_coverage()`: does the handoff name every concern?

```python
def concern_coverage(handoff: dict, concerns: dict[str, str]) -> dict[str, bool]:
    """Does the handoff's text name each concern's key detail? (C16)"""
    text = " ".join(str(handoff[name]) for name in ("conversation_summary", "root_cause", "recommended_action")).lower()
    return {concern: detail.lower() in text for concern, detail in concerns.items()}
```

**Why it matters:**
- It reads the three free-text fields of the **stored** handoff, the one the human would get.
- It checks for a concrete detail per concern, not for a vague word like "address". A handoff that says "the customer had some other issues" fails.
- It's a coverage check, not a quality check: `validate_handoff()` has already rejected placeholders and back-references before the handoff could be stored.

---

### 4.5 `main()`: two runs, two result lines each

```python
async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc2_handoff_test")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    for prompt, concerns in RUNS:
        session = SupportSession()
        try:
            await run_support(prompt, build_support_options(settings, session, handoff=True))  # gate and rule on
        except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
            log.error("SDK error: %s", exc)
            return 1
        # Expected: the $49.99 return is refunded by the agent; the $129.00 duplicate charge goes to the human.
        log.info("Refunds paid: %s · handoffs stored: %d", [f"${r['amount']:.2f}" for r in session.refunds],
                 len(session.handoffs))
        for handoff in session.handoffs:
            log.info("Handoff covers %s · amount left for the human: $%.2f",
                     concern_coverage(handoff, concerns), handoff["refund_amount"])
    return 0
```

**Why it matters:**
- **`handoff=True`** adds `escalate_to_human` and `HANDOFF_RULE`. `gate` and `verify_rule` keep their defaults (`True`), so POC 1's gate is on.
- **A new `SupportSession` per run,** so the multi-concern run starts unverified and with no handoffs.
- **The result lines read the session.** `session.handoffs` holds only handoffs that passed `validate_handoff()`; a rejected call never gets there.
- **`refund_amount`** is the amount the human still has to decide on. The comment states the expected split: $49.99 refunded by the agent, $129.00 left for the human.

The four lines it wrote:

```
20:51:13  Refunds paid: [] · handoffs stored: 1
20:51:13  Handoff covers {'billing dispute': True} · amount left for the human: $129.00
20:51:24  Refunds paid: ['$49.99'] · handoffs stored: 1
20:51:24  Handoff covers {'return': True, 'billing dispute': True, 'account update': True} · amount left for the human: $129.00
```

Both runs match the expectation in the comment. No `SDK error:` line, so `main()` returned `0`.

---

### 4.6 `__main__`

```python
if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

---

### 4.7 `escalate_to_human`: the handoff tool (from `support_setup.py`)

```python
    @tool(
        "escalate_to_human",
        "Hand the case to a human agent. Call it once, when a request needs an account change or a billing-dispute "
        "decision. The human sees ONLY this handoff: in conversation_summary, number every concern the customer "
        "raised and give each one's status (resolved, or needs a human).",
        {"type": "object",
         "properties": {
             "customer_id": {"type": "string"},
             "conversation_summary": {"type": "string"},
             "root_cause": {"type": "string"},
             "refund_amount": {"type": "number", "minimum": 0, "description": "the amount in USD that the human "
                               "must still decide on, not refunds you already processed"},
             "recommended_action": {"type": "string"}},
         "required": HANDOFF_FIELDS},
    )
    async def escalate_to_human(args: dict[str, Any]) -> dict[str, Any]:
        errors = validate_handoff(args)  # in the handler: an incomplete handoff can't reach the human (C15)
        if errors:
            return {"content": [{"type": "text", "text": f"Handoff rejected: {'; '.join(errors)}. Fix and call "
                                                         "escalate_to_human again."}], "is_error": True}
        session.handoffs.append(dict(args))
        return {"content": [{"type": "text", "text": f"Handoff HO-{len(session.handoffs):04d} queued for a human agent."}]}
```

| Part | What it does | Seen in the real run |
|------|--------------|----------------------|
| Description: "Call it once" | One handoff per request | 1 stored handoff per run |
| Description: "The human sees ONLY this handoff" | Tells Claude who the reader is | Self-contained summaries with order IDs, dates and amounts |
| Description: "number every concern ... and give each one's status" | Shapes `conversation_summary` | Run 2: `1) ... RESOLVED ... 2) ... NEEDS A HUMAN ... 3) ... NEEDS A HUMAN` |
| `required: HANDOFF_FIELDS` | All five keys must be in the call | Every call had all five |
| `refund_amount`: `minimum: 0` and its description | The amount the human still decides on, not refunds already paid | `129` in both runs; the $49.99 already refunded is not in it |
| `errors = validate_handoff(args)` | Content check before anything is stored | Run 1's first call: 2 errors, rejected |
| `is_error: True` + "Fix and call escalate_to_human again." | A recoverable error result | Run 1: the second call passed |
| `session.handoffs.append(...)` | Stores only a valid handoff | `handoffs stored: 1` in both runs |

**Why it matters:**
- **The schema guarantees shape; the handler guarantees content.** A JSON Schema can require a key, but not reject "see above" or "TBD" inside it. That's why `validate_handoff()` runs in the handler.
- **The tool call *is* the handoff.** The human gets exactly the arguments of the accepted `escalate_to_human` call; in the log, that's the `tool_use` line just before `Handoff HO-0001 queued`.
- **No `readOnlyHint`:** this tool has an effect (it queues work for a person).

**Agentic concept:** structured human-in-the-loop escalation: a typed, validated payload instead of "a human will read the chat".

---

### 4.8 `validate_handoff()`: what "self-contained" means in code (from `support_setup.py`)

```python
HANDOFF_FIELDS = ["customer_id", "conversation_summary", "root_cause", "refund_amount", "recommended_action"]
PLACEHOLDERS = ["tbd", "todo", "n/a", "unknown", "placeholder", "[", "<", "..."]
BACK_REFERENCES = ["see above", "as mentioned", "as discussed", "earlier in the conversation", "the transcript"]


def validate_handoff(handoff: dict[str, Any]) -> list[str]:
    """All five fields filled in and self-contained: the human never sees the conversation (C13-C15)."""
    errors = [f"missing {name}" for name in HANDOFF_FIELDS if name not in handoff]
    if handoff.get("customer_id") not in CUSTOMERS:
        errors.append(f"unknown customer_id {handoff.get('customer_id')!r}")
    amount = handoff.get("refund_amount")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
        errors.append("refund_amount must be a number >= 0")
    for name in ("conversation_summary", "root_cause", "recommended_action"):
        text = str(handoff.get(name, "")).strip().lower()
        found = [token for token in PLACEHOLDERS + BACK_REFERENCES if token in text]
        if not text:
            errors.append(f"{name} is empty")
        elif found:
            errors.append(f"{name} contains {found}: write it for a reader who never saw the conversation")
    return errors
```

| Check | Catches | In the real run |
|-------|---------|-----------------|
| `missing {name}` | A field left out | never |
| `customer_id` in `CUSTOMERS` | An invented or mistyped customer | passed (`CUST-1042`) |
| `refund_amount` a number ≥ 0, not a bool | `"129 USD"`, `-5`, `True` | passed (`129`) |
| empty text | A blank summary, cause or action | never |
| `PLACEHOLDERS` | `tbd`, `todo`, `n/a`, `unknown`, `[`, `<`, `...` | `root_cause` "The cause is **unknown** ..." → rejected |
| `BACK_REFERENCES` | `see above`, `as mentioned`, `as discussed`, ... | `conversation_summary` "no return w**as mentioned**" → rejected (a false positive) |

**Why it matters:**
- **It encodes the exam's rule:** the human has no transcript, so every field must stand alone, with no gaps and no pointers back into the chat.
- **It returns a list of errors, not a bool,** so the rejection can tell Claude exactly what to fix.

> **Substring matching is blunt.** `token in text` matches anywhere, so "was mentioned" trips `as mentioned`, and an honest "unknown" trips the placeholder list. In this run both flags still led to clearer text, and Claude recovered in one retry. In production you'd match whole words or phrases and allow stated uncertainty ("not confirmed"), so the validator rejects real gaps, not good writing.

---

### 4.9 `HANDOFF_RULE` and the options (from `support_setup.py`)

```python
HANDOFF_RULE = (" You cannot change account details or resolve billing disputes. When a request needs either, "
                "finish everything you can, then call escalate_to_human once with a summary that covers every "
                "concern the customer raised. The human agent sees only that summary, never this conversation.")
```

```python
        system_prompt=SYSTEM_PROMPT + (VERIFY_RULE if verify_rule else "") + (HANDOFF_RULE if handoff else ""),
        mcp_servers={SERVER_NAME: build_support_server(session, gate, handoff)},  # tools bound to THIS session (C7)
        tools=[],  # remove ALL built-in tools: Claude can use only ours
        allowed_tools=SUPPORT_TOOLS + ([ESCALATE] if handoff else []),  # our tools run without asking for permission
```

| Rule in `HANDOFF_RULE` | What the real runs did |
|------------------------|------------------------|
| "You cannot change account details or resolve billing disputes." | No tool exists for either; both went to the human |
| "finish everything you can" | Run 2: the lamp return was refunded ($49.99, `RF-0001`) before the handoff |
| "call escalate_to_human once" | One accepted call per run (run 1 needed one retry after a rejection) |
| "covers every concern the customer raised" | Run 2: all three concerns, numbered, with status |
| "The human agent sees only that summary" | Summaries restate IDs, dates, amounts and the address |

**Why it matters:** with `handoff=True`, the system prompt gains `HANDOFF_RULE`, the tool server gains `escalate_to_human`, and `allowed_tools` pre-approves it. The other options are POC 1's: no built-in tools, the three support tools, thinking, turn and cost caps.

**Agentic concept:** a capability boundary. The agent has no tool for account changes or dispute decisions, and the prompt tells it the right exit: a handoff.

---

### 4.10 Parts reused from POC 1 (from `support_setup.py`)

- **The refund gate** in `process_refund()` (`if gate and not verified:`). In run 2, `get_customer` ran first, so the $49.99 refund passed.
- **`readOnlyHint=True`** on `get_customer` and `lookup_order`, with the comment "reads only: the SDK may run lookups in parallel (C18)". Both runs show lookups sent together (section 5).
- **`SupportSession`**, now using its `handoffs` list.
- **`run_support()`**, which logs the prompt, passes every message to `log_model_io()`, and returns the final text when the run ends with `success` and `end_turn`.

The POC 1 article walks through each of these in full.

---

### 4.11 `common.py`: settings and a single-agent log

Same as POC 1: defaults `claude-sonnet-5-5`, `max_turns` `15`, `max_budget_usd` `0.50`; `HH:MM:SS  message` lines on the console and in the file; `log_model_io(message)` without agent tags.

| `log_model_io()` branch | Log line tag | Lines in this log |
|-------------------------|--------------|-------------------|
| `ThinkingBlock` with text | `MODEL OUTPUT  thinking` | 2 (run 1) |
| `TextBlock` | `MODEL OUTPUT  text` | 2, the final answer of each run |
| `ToolUseBlock` | `MODEL OUTPUT  tool_use` | 9: run 1 `get_customer`, `lookup_order`, `escalate_to_human` × 2; run 2 `get_customer`, `lookup_order` × 2, `process_refund`, `escalate_to_human` |
| `ToolResultBlock` | `MODEL INPUT   tool_result` | 9: 8 with `is_error=None`, 1 with `is_error=True` |
| `ResultMessage` | `MODEL OUTPUT  stop_reason` | 2 |

---

## 5. Turn-by-turn trace of each run (real output)

Each trace below is the real run from `logs/poc2_handoff_test_20261113_205100.log` (2026-11-13, 20:51:00 to 20:51:24: 24 seconds for both `query()` calls). Each log line points back to the statement that wrote it (section 3.2's table).

How to read the log blocks:
- In the log file, every entry is one line. Here, each entry's header (time, `MODEL INPUT` or `MODEL OUTPUT`, kind) stays on its first line, and its payload is pretty-printed underneath: one key per line.
- Long text wraps onto a deeper-indented line.
- `...` marks text that was cut.

### 5.1 Run 1: the billing dispute

**Real log:**

```
20:51:00  MODEL INPUT   prompt
          Hi, this is Dana Reyes (dana.reyes@example.com). I was charged twice for order ORD-7745.
            Please sort it out.

20:51:03  MODEL OUTPUT  tool_use
          mcp__support__get_customer {'name_or_email': 'dana.reyes@example.com'}
          (id=toolu_0177GLkEn7qjsTB8r8YNGBim)
20:51:03  MODEL OUTPUT  tool_use
          mcp__support__lookup_order {'order_id': 'ORD-7745'}
          (id=toolu_01LSebuzerdaxiHxRNqYJQF4)
20:51:03  MODEL INPUT   tool_result
          [{'type': 'text', 'text': '{"customer_id": "CUST-1042", "name": "Dana Reyes",
              "verified": true}'}]
          (tool_use_id=toolu_0177GLkEn7qjsTB8r8YNGBim, is_error=None)
20:51:03  MODEL INPUT   tool_result
          [{'type': 'text', 'text': '{"order_id": "ORD-7745", "customer_id": "CUST-1042",
              "item": "Nimbus wireless headphones", "total": 129.0, "charges": [129.0, 129.0],
              "charged_on": "2026-10-02", "status": "delivered"}'}]
          (tool_use_id=toolu_01LSebuzerdaxiHxRNqYJQF4, is_error=None)

20:51:06  MODEL OUTPUT  thinking
          I've confirmed the double charge, so this is a billing dispute and needs escalating. The
            refund doesn't apply because it's tied to a returned item, and this one was never
            returned; its status shows delivered. So I'll escalate rather than refund.

20:51:07  MODEL OUTPUT  tool_use
          mcp__support__escalate_to_human {
              'customer_id': 'CUST-1042',
              'conversation_summary': "1. Duplicate charge on order ORD-7745 (Nimbus wireless
                  headphones): needs a human. Customer Dana Reyes (verified) says she was charged
                  twice. The order lookup confirms two charges of $129.00 each on 2026-10-02,
                  against an order total of $129.00. The order status is delivered, and no return
                  was mentioned, so I did not process a refund. This is a billing dispute, which I
                  can't resolve.",
              'root_cause': 'The order was charged twice, with two $129.00 charges against a
                  $129.00 total. The cause is unknown and probably a duplicate payment capture.',
              'refund_amount': 129,
              'recommended_action': "Review the two charges on ORD-7745. If the duplicate is
                  confirmed, refund the extra $129.00 to the customer's original payment method."}
          (id=toolu_01PUCyrapuXi7v4HaUAeXz7H)
20:51:07  MODEL INPUT   tool_result
          Handoff rejected: conversation_summary contains ['as mentioned']: write it for a reader
            who never saw the conversation; root_cause contains ['unknown']: write it for a reader
            who never saw the conversation. Fix and call escalate_to_human again.
          (tool_use_id=toolu_01PUCyrapuXi7v4HaUAeXz7H, is_error=True)

20:51:09  MODEL OUTPUT  thinking
          I'm checking my wording, since the phrase "as mentioned" doesn't appear verbatim in what
            I wrote; the point is that no return was mentioned, so I'll reword it to say that.

20:51:10  MODEL OUTPUT  tool_use
          mcp__support__escalate_to_human {
              'customer_id': 'CUST-1042',
              'conversation_summary': "1. Duplicate charge on order ORD-7745 (Nimbus wireless
                  headphones): needs a human. Customer Dana Reyes (verified, CUST-1042) reports
                  being charged twice. The order record shows two charges of $129.00 each on
                  2026-10-02, against an order total of $129.00. The order status is delivered.
                  The customer did not say the item was returned, so I did not process a refund.
                  This is a billing dispute, which I can't resolve.",
              'root_cause': 'The order was charged twice: two $129.00 charges against a $129.00
                  total. The likely cause is a duplicate payment capture, but I could not confirm
                  that.',
              'refund_amount': 129,
              'recommended_action': "Review the two charges on ORD-7745. If the duplicate is
                  confirmed, refund the extra $129.00 to the customer's original payment method."}
          (id=toolu_01NmyHyo7VHGvwBBzyVZE3v5)
20:51:10  MODEL INPUT   tool_result
          [{'type': 'text', 'text': 'Handoff HO-0001 queued for a human agent.'}]
          (tool_use_id=toolu_01NmyHyo7VHGvwBBzyVZE3v5, is_error=None)

20:51:12  MODEL OUTPUT  text
          Hi Dana, I checked order ORD-7745 and you were charged twice. There are two charges of
            $129.00 on 2026-10-02, but the order total is only $129.00.

          I can't resolve billing disputes myself, so I've sent the case to a human agent
            (reference HO-0001). I asked them to review the charges and refund the extra $129.00
            if the duplicate is confirmed. I didn't issue a refund myself because the headphones
            were delivered and haven't been returned.
20:51:12  MODEL OUTPUT  stop_reason  end_turn  (loop result: success)

20:51:13  Refunds paid: [] · handoffs stored: 1
20:51:13  Handoff covers {'billing dispute': True} · amount left for the human: $129.00
```

**What each step did and which code ran:**

| Step | Claude asked for | Handler code that ran | Returned | Session after |
|------|------------------|-----------------------|----------|---------------|
| 1 | `get_customer` **and** `lookup_order('ORD-7745')`, together | both lookups | verified `CUST-1042`; two charges of `129.0` | `verified_ids = {"CUST-1042"}` |
| 2 | *(thinking)* dispute → escalate, not refund | none | none | |
| 3 | `escalate_to_human` (first try) | `validate_handoff()` → 2 errors | `Handoff rejected: ...`, `is_error=True` | `handoffs = []` |
| 4 | *(thinking)* reword | none | none | |
| 5 | `escalate_to_human` (second try) | `validate_handoff()` → no errors; append | `Handoff HO-0001 queued ...` | `handoffs = [the second call's args]` |
| 6 | *(text)* the reply to the customer | none | `end_turn` | |

**Variable values at the end of the run:**

| Variable / field | Value |
|------------------|-------|
| `errors` (first call) | `["conversation_summary contains ['as mentioned']: ...", "root_cause contains ['unknown']: ..."]` |
| `errors` (second call) | `[]` |
| `session.refunds` | `[]` |
| `session.handoffs` | 1 dict: the five fields of the second call |
| `concern_coverage(...)` | `{'billing dispute': True}`: `ORD-7745` is in the text |
| `handoff["refund_amount"]` | `129` → logged as `$129.00` |
| `message.subtype` / `stop_reason` | `"success"` / `"end_turn"` |

**Lessons from the real data:**
- **The validator is a gate for the handoff.** The first call never reached the human; the stored handoff is the corrected one.
- **The rejection was recoverable in one step,** because the error named both fields and the fix.
- **Its matching was too broad.** "w**as mentioned**" isn't a back-reference, and "unknown" was honest. A real validator should match whole phrases and allow stated uncertainty. Here the rewrite still made the handoff clearer for the human.
- **The agent didn't overreach.** It didn't refund a disputed charge; it put `129` in `refund_amount` and recommended a review, as the schema's description asks.

### 5.2 Run 2: return + dispute + address change

**Real log:**

```
20:51:13  MODEL INPUT   prompt
          Hi, this is Dana Reyes (dana.reyes@example.com). Three things: 1) the Aurora desk lamp
            from order ORD-7731 arrived cracked, so I'm returning it and want my money back; 2) I
            was charged twice for order ORD-7745; 3) please change my shipping address to 88
            Larkspur Lane, Portland, OR 97211.

20:51:15  MODEL OUTPUT  tool_use
          mcp__support__get_customer {'name_or_email': 'dana.reyes@example.com'}
          (id=toolu_01NxnGPaWYGFBtu24iXJkFAN)
20:51:15  MODEL INPUT   tool_result
          [{'type': 'text', 'text': '{"customer_id": "CUST-1042", "name": "Dana Reyes",
              "verified": true}'}]
          (tool_use_id=toolu_01NxnGPaWYGFBtu24iXJkFAN, is_error=None)
20:51:16  MODEL OUTPUT  tool_use
          mcp__support__lookup_order {'order_id': 'ORD-7731'}
          (id=toolu_01MMWK1CerB5dHNS9oYsiwLR)
20:51:16  MODEL OUTPUT  tool_use
          mcp__support__lookup_order {'order_id': 'ORD-7745'}
          (id=toolu_013qvZjk56f6chZJT8bPQqrW)
20:51:16  MODEL INPUT   tool_result
          [{'type': 'text', 'text': '{"order_id": "ORD-7731", "customer_id": "CUST-1042",
              "item": "Aurora desk lamp", "total": 49.99, "charges": [49.99],
              "status": "delivered, return eligible"}'}]
          (tool_use_id=toolu_01MMWK1CerB5dHNS9oYsiwLR, is_error=None)
20:51:16  MODEL INPUT   tool_result
          [{'type': 'text', 'text': '{"order_id": "ORD-7745", ... "charges": [129.0, 129.0], ...}'}]
          (tool_use_id=toolu_013qvZjk56f6chZJT8bPQqrW, is_error=None)
20:51:17  MODEL OUTPUT  tool_use
          mcp__support__process_refund {'customer_id': 'CUST-1042', 'amount': 49.99}
          (id=toolu_01MdXE1arhaX3WdpgFo5eSSM)
20:51:17  MODEL INPUT   tool_result
          [{'type': 'text', 'text': 'Refund of $49.99 processed for CUST-1042. Refund ID RF-0001.'}]
          (tool_use_id=toolu_01MdXE1arhaX3WdpgFo5eSSM, is_error=None)

20:51:21  MODEL OUTPUT  tool_use
          mcp__support__escalate_to_human {
              'customer_id': 'CUST-1042',
              'conversation_summary': '1) Aurora desk lamp (ORD-7731) arrived cracked, customer
                  returning it and wants refund: RESOLVED. Refunded $49.99 (RF-0001). 2) Double
                  charge on ORD-7745 (Nimbus wireless headphones): two charges of $129.00 on
                  2026-10-02, order total $129.00. NEEDS A HUMAN (billing dispute). 3) Change
                  shipping address to 88 Larkspur Lane, Portland, OR 97211: NEEDS A HUMAN
                  (account change).',
              'root_cause': 'Duplicate charge of $129.00 on ORD-7745; customer also requests an
                  account shipping address update, which I cannot perform.',
              'refund_amount': 129,
              'recommended_action': 'Verify the duplicate $129.00 charge on ORD-7745 and refund it
                  if confirmed. Update the shipping address on CUST-1042 to 88 Larkspur Lane,
                  Portland, OR 97211.'}
          (id=toolu_018GM7LbgZwh897uSZex92MS)
20:51:21  MODEL INPUT   tool_result
          [{'type': 'text', 'text': 'Handoff HO-0001 queued for a human agent.'}]
          (tool_use_id=toolu_018GM7LbgZwh897uSZex92MS, is_error=None)

20:51:23  MODEL OUTPUT  text
          Hi Dana, here's where each of your three requests stands:

          1. **Cracked Aurora desk lamp (ORD-7731):** This is done. I refunded $49.99 to you
             (refund ID RF-0001).
          2. **Double charge on ORD-7745:** I confirmed that you were charged $129.00 twice on
             2026-10-02. I can't resolve billing disputes, so I passed it to a human agent to
             review and refund the duplicate.
          3. **Shipping address change to 88 Larkspur Lane, Portland, OR 97211:** I can't change
             account details either, so I included this in the same handoff (HO-0001).

          The human agent will follow up on items 2 and 3.
20:51:23  MODEL OUTPUT  stop_reason  end_turn  (loop result: success)

20:51:24  Refunds paid: ['$49.99'] · handoffs stored: 1
20:51:24  Handoff covers {'return': True, 'billing dispute': True, 'account update': True} ·
            amount left for the human: $129.00
```

**What each step did and which code ran:**

| Step | Concern | Claude asked for | Handler code that ran | Result |
|------|---------|------------------|-----------------------|--------|
| 1 | all | `get_customer` | `get_customer()`: verified → `verified_ids` | `CUST-1042`, verified |
| 2 | return, dispute | `lookup_order('ORD-7731')` **and** `lookup_order('ORD-7745')`, together | `lookup_order()` × 2 | lamp `49.99`, return eligible; headphones charged twice |
| 3 | return | `process_refund('CUST-1042', 49.99)` | the gate passes (`CUST-1042` verified); append | `RF-0001` |
| 4 | dispute + address | `escalate_to_human` with all three concerns, numbered | `validate_handoff()` → no errors; append | `HO-0001` queued |
| 5 | all | *(text)* a numbered status per concern | none | `end_turn` |

**Lessons from the real data:**
- **Decomposition, then the right action per item.** The return was resolved by the agent (inside its limits, through the gate); the dispute and the address change went to the human.
- **Parallel investigation.** The two order lookups went out in one response: both `tool_use` lines before either result.
- **One unified handoff.** A single `escalate_to_human` call covers all three concerns, each with a status (`RESOLVED`, `NEEDS A HUMAN`), as the tool's description asks. `concern_coverage()` found all three details.
- **`refund_amount` excludes what's already done.** The human gets `129`, not `178.99`: the $49.99 was refunded already, as the field's description demands.
- **First call accepted.** No placeholders or back-references this time; the validator returned no errors.
- **The customer's reply mirrors the handoff,** item by item, with the same reference `HO-0001`.

### 5.3 The two runs side by side

| | Run 1: dispute | Run 2: three concerns |
|-|----------------|-----------------------|
| Concerns | billing dispute | return, billing dispute, account update |
| Lookups | `get_customer` + `lookup_order` in one response | `get_customer`, then 2 × `lookup_order` in one response |
| Refunds by the agent | none | `$49.99` (`RF-0001`), gate passed |
| `escalate_to_human` calls | 2 (1 rejected, 1 accepted) | 1 (accepted) |
| Rejection reasons | `as mentioned` (false positive), `unknown` | none |
| Handoffs stored | 1 | 1 |
| `concern_coverage` | `{'billing dispute': True}` | all three `True` |
| `refund_amount` for the human | `$129.00` | `$129.00` |
| `thinking` lines | 2 | 0 |
| Final `subtype` / `stop_reason` | `success` / `end_turn` | `success` / `end_turn` |
| Wall time (from log) | about 12 s | about 10 s |

The log has no `SDK error:` or `The run failed:` line, so `main()` returned `0`.

---

## 6. Agentic AI concepts recap

| Concept | How this POC shows it |
|---------|-----------------------|
| **Structured handoff protocol** | `escalate_to_human` with five required fields: the human's only input. |
| **Self-contained context** | The human never sees the chat; `BACK_REFERENCES` and the description enforce standalone text. |
| **Deterministic validation in the handler** | `validate_handoff()` runs before the handoff is stored; run 1's first call was rejected. |
| **Recoverable error results** | `Handoff rejected: ... Fix and call escalate_to_human again.` with `is_error=True`; one retry fixed it. |
| **Schema for shape, code for content** | `required: HANDOFF_FIELDS` and `minimum: 0`, then placeholder and back-reference checks. |
| **Capability boundaries** | No tool for disputes or account changes; `HANDOFF_RULE` names the exit. |
| **Do what you can, hand off the rest** | Run 2: the return refunded, the rest escalated. |
| **Request decomposition** | Run 2's summary numbers each concern with its status. |
| **Parallel investigation** | Read-only lookups sent together in one response. |
| **Enforcement from POC 1 still on** | The $49.99 refund passed the gate after `get_customer`. |
| **Measure in state** | `session.handoffs` and `session.refunds` drive the result lines, not the reply text. |

---

## 7. Common mistakes this POC helps you avoid

1. **"The human can read the transcript."** They can't. A handoff that says "see above" hands over nothing.
2. **Optional handoff fields.** Make all five required in the schema.
3. **Trusting the schema to check content.** Required keys can still hold "TBD". Validate the text in the handler.
4. **Storing the handoff before validating it.** Validate first; store only a clean one.
5. **Rejecting without saying why.** Name the field and the problem, so the agent can fix it in one retry.
6. **Over-eager pattern matching.** Substring checks flag "was mentioned" and honest "unknown". Match whole phrases; let the agent state uncertainty.
7. **One handoff per concern, or a handoff that drops one.** One request, one handoff, every concern numbered with its status.
8. **Escalating what the agent could have done.** Run 2 refunded the eligible return itself.
9. **Putting money already refunded in the human's amount.** `refund_amount` is what the human still decides on.
10. **Handling concerns one by one with lookups in sequence.** Independent read-only lookups can go out together.

---

## 8. Claude Architect exam lens

### 8.1 What the exam tests on this topic

The objectives come from `curriculum/01-Agentic-Architecture-&-Orchestration/04-raw-Workflow-Enforcement-and-Handoff.md`. POC 1 covers objectives 1 to 3 (the gate); POC 2 covers 4 and 5 (the handoff), with the gate still on.

| Exam objective | What a correct answer looks like | Where this POC shows it |
|----------------|----------------------------------|-------------------------|
| 2. The prerequisite gate (still on) | A refund only after a verified `get_customer` in this session | Run 2: `get_customer` → `process_refund` → `RF-0001` |
| 4. A structured handoff protocol | A self-contained object with customer ID, conversation summary, root cause, refund amount and recommended action, all filled, no placeholders. The human has no transcript; the handoff is all they get. | `escalate_to_human` (schema with `required: HANDOFF_FIELDS`), `validate_handoff()`; run 1's rejection and fix |
| 5. A multi-concern test (return + dispute + account update) | The agent identifies every concern, investigates each (in parallel where independent), and produces one handoff covering all of them with specific details. Nothing omitted, nothing handled one by one. | Run 2: two lookups in one response, the return refunded, one handoff with three numbered items; `concern_coverage()` all `True` |

> **Exam tip:** the exam's handoff questions usually hinge on one fact: human agents do **not** have the conversation transcript. Any answer that relies on "the human can scroll up", or that leaves a field for the human to fill in, is wrong. The fix is a complete, standalone handoff, with all five fields required and checked.

### 8.2 The same handoff with the raw Messages API

With the raw Messages API, the handoff is an ordinary tool whose arguments your code receives. The validation goes in your tool executor; a rejection goes back as a `tool_result` with `is_error: true`.

```python
import anthropic

client = anthropic.Anthropic()

ESCALATE_TOOL = {
    "name": "escalate_to_human",
    "description": "Hand the case to a human agent. Call it once. The human sees ONLY this handoff: in "
                   "conversation_summary, number every concern the customer raised and give each one's status.",
    "input_schema": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "string"},
            "conversation_summary": {"type": "string"},
            "root_cause": {"type": "string"},
            "refund_amount": {"type": "number", "minimum": 0},
            "recommended_action": {"type": "string"},
        },
        "required": ["customer_id", "conversation_summary", "root_cause", "refund_amount", "recommended_action"],
    },
}


def run_escalation(args: dict, queue: list) -> tuple[str, bool]:
    errors = validate_handoff(args)  # the same validator as the POC
    if errors:
        return f"Handoff rejected: {'; '.join(errors)}. Fix and call escalate_to_human again.", True
    queue.append(args)  # only a valid handoff reaches the human
    return f"Handoff HO-{len(queue):04d} queued for a human agent.", False
```

| Raw Messages API (you write it) | Agent SDK (`poc2_handoff_test.py`) |
|---------------------------------|------------------------------------|
| `ESCALATE_TOOL` with `input_schema` and `required` | `@tool("escalate_to_human", ..., {..., "required": HANDOFF_FIELDS})` |
| `run_escalation()` called from your tool loop | The SDK calls the `escalate_to_human` handler |
| `validate_handoff(args)` before `queue.append(args)` | The same, inside the handler, before `session.handoffs.append(...)` |
| `tool_result` with `is_error: true` → the model retries | `{"content": [...], "is_error": True}` → the SDK loop continues |
| Run independent lookups from one response concurrently in your loop | `readOnlyHint=True` on the lookup tools |

In both forms the human's input is exactly the accepted tool call's arguments.

### 8.3 Scenario questions

Try each one before reading the answer. These questions were written for this article to match the curriculum objectives above. They are not official exam questions.

---

**Scenario 1: The handoff that says "see above"**

Human agents complain that escalated cases often say things like "customer issue as discussed above, please resolve". The agent's escalation tool takes one free-text field. What is the best fix?

- A. Give human agents access to the full transcript.
- B. Replace the free text with a structured handoff of required fields (customer ID, conversation summary, root cause, amount, recommended action), and reject text that refers back to the conversation.
- C. Tell the agent to write longer summaries.
- D. Escalate every conversation, so humans see more context.

**Answer: B.** The human's only input is the handoff, so it must be complete and standalone, and code should enforce that. A contradicts the exam's premise (humans don't get the transcript); C is a prompt-only fix; D floods the queue. *POC link:* `escalate_to_human`'s schema with `required: HANDOFF_FIELDS`, and `BACK_REFERENCES` in `validate_handoff()`.

---

**Scenario 2: Required, but "TBD"**

A handoff tool's schema marks all five fields as required. Some handoffs still arrive with `root_cause: "TBD"`. What is missing?

- A. Nothing: the schema guarantees completeness.
- B. A content check in the handler that rejects empty, placeholder or back-reference text before the handoff is stored, with an error the agent can act on.
- C. A larger model.
- D. Making `root_cause` an enum.

**Answer: B.** A schema guarantees keys and types, not meaningful content. The handler is where you check what's inside, and where you can refuse to store it. *POC link:* `validate_handoff()` runs inside `escalate_to_human()`; run 1's first call was rejected for `unknown` and stored nothing.

---

**Scenario 3: After a rejection**

The handoff tool rejects a call because one field is a placeholder. What should happen next?

- A. The run should fail, and a developer should look at it.
- B. The tool returns an error result naming the field and the fix; the agent rewrites the handoff and calls again.
- C. The tool fills in the field with a default.
- D. The tool accepts the handoff and flags it for later.

**Answer: B.** An actionable error keeps the loop going and gets a valid handoff in one more turn. C and D both let an incomplete handoff reach the human. *POC link:* run 1: `Handoff rejected: ... Fix and call escalate_to_human again.` with `is_error=True`, then `Handoff HO-0001 queued` two seconds later.

---

**Scenario 4: Three concerns, one message**

A customer asks, in one message, for a refund on a damaged item, a review of a duplicate charge and an address change. The agent may refund returns but can't decide disputes or change accounts. Which outcome is correct?

- A. Escalate the whole message to a human, since part of it needs one.
- B. Refund the return itself, then send one handoff that lists all three concerns with their status, with specific details for the two that need a human.
- C. Handle the refund and ignore the rest until the customer asks again.
- D. Send three separate handoffs, one per concern.

**Answer: B.** Decompose, resolve what you may, and hand off the rest in one unified, complete summary. A wastes the human's time; C drops concerns; D splits one case across three tickets. *POC link:* run 2: `Refunds paid: ['$49.99'] · handoffs stored: 1` and `Handoff covers {'return': True, 'billing dispute': True, 'account update': True}`.

---

**Scenario 5: The amount for the human**

In a multi-concern case, the agent already refunded $49.99 for a return. A $129.00 duplicate charge needs a human decision. What should the handoff's `refund_amount` be?

- A. $178.99: the total of everything refunded or disputed.
- B. $129.00: only the amount the human still has to decide on.
- C. $49.99: what the agent refunded.
- D. Leave it empty for the human to work out.

**Answer: B.** The field tells the human what's left to decide. The completed refund belongs in the summary as resolved. D leaves a field incomplete. *POC link:* the `refund_amount` description ("the amount in USD that the human must still decide on, not refunds you already processed"); run 2: `amount left for the human: $129.00`, with `RF-0001` listed as resolved.

---

**Scenario 6: Investigating in parallel**

An agent handling a three-concern request looks up the first order, waits, then looks up the second order. The lookups don't depend on each other. What does the exam expect?

- A. Sequential lookups, because order matters for support.
- B. Independent investigations run in parallel (several read-only tool calls in one response), then one unified resolution.
- C. One subagent per concern.
- D. Skipping the second lookup if the first one explains enough.

**Answer: B.** Decomposition, parallel investigation and unified resolution. Read-only lookups can safely go out together. *POC link:* run 2: both `lookup_order` calls logged before either result; `readOnlyHint=True` on `lookup_order` in `build_support_server()`.

---

**Scenario 7: A validator that's too strict**

A handoff validator rejects any field containing the substring "as mentioned". It keeps rejecting summaries that say "no return was mentioned". What should the team do?

- A. Remove the validator.
- B. Keep the check but match whole phrases (word boundaries), so real back-references are caught and ordinary words aren't.
- C. Tell the agent never to use the word "mentioned".
- D. Let the agent retry until it passes, however long that takes.

**Answer: B.** The check is right in purpose; its matching is wrong. A removes the protection; C is a prompt workaround for a code bug; D wastes turns. *POC link:* `found = [token for token in PLACEHOLDERS + BACK_REFERENCES if token in text]` in `validate_handoff()`; run 1's false positive and Claude's thinking line: "the phrase "as mentioned" doesn't appear verbatim in what I wrote".

---

**Scenario 8: Disputes and refunds**

A customer reports a duplicate charge on a delivered item they are keeping. The agent has a refund tool for returned items. What should it do?

- A. Refund the duplicate charge, since the evidence is clear.
- B. Confirm the facts with the lookup tools, then escalate the dispute with the amount and a recommended action, without refunding.
- C. Ask the customer to return the item so a refund becomes possible.
- D. Tell the customer to contact their bank.

**Answer: B.** Billing disputes are outside the agent's authority; it should investigate and hand off a complete case. A acts outside policy; C and D push work onto the customer. *POC link:* run 1's thinking line ("this is a billing dispute and needs escalating ... So I'll escalate rather than refund") and `Refunds paid: []`.

---

**Scenario 9: Checking coverage**

How can a team test that handoffs cover every concern of a multi-part request?

- A. Read a few handoffs by hand each month.
- B. For each test request, list a concrete detail per concern (an order ID, an address) and check that the stored handoff's text contains each one.
- C. Count the handoff's sentences.
- D. Ask the model whether it covered everything.

**Answer: B.** A deterministic check on concrete details catches a dropped concern every time. *POC link:* `concern_coverage()` in `poc2_handoff_test.py`, with the concern map in `RUNS`.

---

### 8.4 Quick-recall cheat sheet

```
human's input          → ONLY the handoff; no transcript, ever
five required fields   → customer_id, conversation_summary, root_cause, refund_amount, recommended_action
schema                 → guarantees keys and types (required, minimum: 0)
handler validation     → rejects empty, placeholder (TBD, unknown, ...) and back-reference ("see above") text
validate before store  → an invalid handoff never reaches the human
rejection              → is_error=True + which field + "Fix and call escalate_to_human again" → one retry
matching               → whole phrases, not substrings ("was mentioned" ≠ "as mentioned")
refund_amount          → what the human still decides on; not refunds already processed
multi-concern          → decompose → investigate in parallel → resolve what you may → ONE handoff, every concern + status
capability boundary    → no tool for disputes / account changes; HANDOFF_RULE names the exit
gate still on          → the agent's own refund still needs a verified get_customer
```

---

## 9. How to run it

```bash
cd 01-Agentic-Architecture-Orchestration/04-Workflow-Enforcement-and-Handoff
source .venv/bin/activate        # the folder's venv (claude-agent-sdk 0.2.181)
python poc1_gate_test.py         # paid: POC 1, the refund gate
python poc2_handoff_test.py      # paid: 2 short runs, 2 query() calls, uses ANTHROPIC_API_KEY from .env
```

- Both scripts call the API. This folder has no free offline demo.
- `.env` needs `ANTHROPIC_API_KEY`; copy `.env.example` and fill it in. `MODEL_ID`, `MAX_TURNS` and `MAX_BUDGET_USD` fall back to `claude-sonnet-5-5`, `15` and `0.50`.
- Every model input and output, plus the result lines per run, goes to the console and to `logs/poc2_handoff_test_<date>_<time>.log`. The accepted `escalate_to_human` tool_use line is exactly what the human would receive. Wording, and whether the first handoff is rejected, vary between runs.
- The exit code is `0` when both runs finish. It's `1` on a setup failure or an SDK runtime failure (`ClaudeSDKError`). A failed run (`ResultError`) is logged as `The run failed: ...` and the script goes on.
