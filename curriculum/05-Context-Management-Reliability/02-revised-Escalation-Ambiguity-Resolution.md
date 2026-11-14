# Escalation and Ambiguity Resolution: Revised POC Requirements (5 steps → 1 POC, Claude Agent SDK)

> **Source:** `02-raw-Escalation-Ambiguity-Resolution.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Context Management & Reliability → Escalation and Ambiguity Resolution · **Build with:** Claude Agent SDK for Python (`claude_agent_sdk`)

---

## 1. Verdict: 1 POC

The 5 raw steps are not 5 separate concepts. They build **one support agent that makes one of three moves on every customer message**: resolve it, escalate it, or ask for an identifier. Step 1's criteria and step 2's examples choose between resolving and escalating. Step 3's matching function makes asking the only possible move when a name matches several customers. Step 4 tests each move once, and step 5 reruns the same harness on more phrasings of the two moves the exam treats as absolute.

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: Resolve, escalate or ask** | **Escalation is calibrated in the prompt; disambiguation is enforced in code:** explicit criteria (three triggers, two anti-patterns, gap against violation) and three reasoned examples turn a sentiment-driven agent into one that resolves a frustrated customer's simple issue, escalates a policy gap, and escalates an explicit human request before any lookup. A matching function that returns no account data for an ambiguous name leaves no record for a heuristic to pick | 1, 2, 3, 4, 5 |

**What changes with the Agent SDK:** nothing about the decisions themselves. The criteria and examples are text in the `system_prompt` string, and the matching function is the handler of a custom tool. The SDK runs the loop, so every decision is read from the stream and from the session object the handlers share:
- an `escalate_to_human` `ToolUseBlock` and its `trigger` input;
- the tool calls that came before it, and Claude's first tool-calling response (`first_response_tools`);
- what `find_customer` returned.

Each scenario is one `query()` with one customer message, and each `query()` "starts fresh with no memory of previous interactions", so no scenario can lean on another. Whether Claude escalates can only be observed, not coded: the POC scores every run against an expected move. The two absolute rules differ in where they are enforced:
- **The matching rule lives in the tool handler,** so no account data can leave an ambiguous search, whatever the prompt says.
- **The human-request rule lives in the prompt,** so the POC can only show that it held on every phrasing it tried. That is why step 5 asks for several.

No sentiment classifier or confidence threshold is built anywhere: that absence is the lesson of C2.

- **Why 1 POC is enough:** one agent makes all three moves, one message at a time. Every test, step 4's scenarios and step 5's phrasings, runs through the same `run_agent()` and the same `classify()`. A second POC would rebuild the server, the prompts and the classifier.
- **Why not more POCs:** step 3's matching function is one tool handler of the same agent. Its rule is proven offline in the self-check, and its live behavior is one scenario (S4) of step 4's suite. Steps 4 and 5 only test steps 1–3.

**Applies to the POC:**
- **Setup:** Python 3.10+, `pip install claude-agent-sdk` (a recent 0.2.x; it bundles the Claude Code binary), and `ANTHROPIC_API_KEY` set in the environment (never hard-coded). Mock data only, and beginner-friendly code (small, commented scripts).
- **Runner:** every run goes through `run_agent()` from `01-revised-Agentic-Loops.md` (`poc2_agent_loop.py`), as extended in `05-revised-Agent-SDK-Hooks.md` (`options=`, `tool_results`) and in `01-revised-Tool-Interface-Design.md` (`first_response_tools`).
- **Tools:** they follow `tools.py` from `01-revised-Agentic-Loops.md` (C2–C3): `@tool` with a full JSON Schema dict, async handlers that return `{"content": [...]}`, and `is_error` instead of raising. They live in one MCP server that is built for every run, so all handlers share one `EscalationSession` (the pattern of `build_support_server()` in `04-revised-Workflow-Enforcement-and-Handoff.md`).
- **Data:** it belongs to Lumen Home, the made-up store of `01-revised-Tool-Interface-Design.md`. Two customers who share a name and one clearance order are added.

**Customers** (`CUSTOMERS`). Every record has these fields. `last_order_date` is read only by the self-check's heuristics:

| Customer ID | Name | Email | Phone | Postcode | City | `order_ids` | `last_order_date` |
|---|---|---|---|---|---|---|---|
| `CUST-1042` | Dana Reyes | `dana.reyes@example.com` | +1-503-555-0142 | 97205 | Portland, OR | `ORD-7731`, `ORD-7745` | 2026-11-08 |
| `CUST-2077` | Sam Okafor | `sam.okafor@example.com` | +1-206-555-0177 | 98101 | Seattle, WA | `ORD-8810`, `ORD-8952` | 2026-11-11 |
| `CUST-3101` | Alex Morgan | `alex.morgan@example.com` | +1-503-555-0118 | 97214 | Portland, OR | `ORD-9310` | 2026-11-06 |
| `CUST-3388` | Alex Morgan | `a.morgan@example.net` | +1-206-555-0164 | 98103 | Seattle, WA | `ORD-6721`, `ORD-7368`, `ORD-8462` | 2026-09-19 |

**Orders** (`ORDERS`). The first three come from `01-revised-Tool-Interface-Design.md`, with a delay added to `ORD-7745`. `ORD-8952` is new. The Alex Morgans' orders exist only as ids in `order_ids`:

| Order ID | Customer | Item | Total | Status | Tracking | `final_sale` |
|---|---|---|---|---|---|---|
| `ORD-7731` | `CUST-1042` | Aurora desk lamp | $49.99 | delivered on 2026-10-03 | `LH-55120931` | false |
| `ORD-7745` | `CUST-1042` | Nimbus wireless headphones | $129.00 | shipped; delayed in transit, new delivery estimate 2026-11-16 | `LH-55120988` | false |
| `ORD-8810` | `CUST-2077` | Kestrel water bottle | $24.50 | processing | none yet | false |
| `ORD-8952` | `CUST-2077` | Linden throw pillow (clearance) | $18.00 | delivered on 2026-11-02 | `LH-55121407` | true |

**The server `lumen`**, created by `build_escalation_server(session)`:

| Tool | Description (what Claude reads) | Input | Behavior |
|---|---|---|---|
| `mcp__lumen__find_customer` (`readOnlyHint=True`) | `"Finds one Lumen Home customer account by full name, narrowed by any identifiers the customer gave: email, phone, order number or postcode. Returns the account only when exactly one customer matches. When several customers share the name, it returns no account data and lists the identifiers to ask for."` | `name` (required string); `email`, `phone`, `order_number`, `postcode` (optional strings) | Returns `json.dumps(match_customer(...))` (C11). Appends `("find_customer", name, status)` to `session.events`. A `matched` result also appends the customer ID to `session.disclosed` |
| `mcp__lumen__lookup_order` (`readOnlyHint=True`) | `"Looks up one Lumen Home order by its order ID (ORD- plus 4 digits) and returns its item, total, status, tracking number and final-sale flag."` | `order_id` (required string) | Returns the `ORDERS` row as JSON `{"order_id", "customer_id", "item", "total", "status", "tracking", "final_sale"}` and appends `("lookup_order", order_id, "found")`. Any other ID returns `is_error: True`, `No order matches '<id>'.`, and appends `("lookup_order", order_id, "not_found")` |
| `mcp__lumen__escalate_to_human` | `"Hands this conversation to a human support agent. Pass the trigger that applies and a one-sentence reason the human can act on."` | `trigger` (required, enum `explicit_human_request`, `policy_gap`, `no_progress`, `other`), `reason` (required string) | Appends `{"id": "ESC-<n:04d>", "trigger", "reason"}` to `session.escalations` and `("escalate_to_human", trigger, id)` to `session.events`. Returns `Escalation ESC-0001 queued: a human agent will take over this conversation.` |

What a handoff must contain is the lesson of `04-revised-Workflow-Enforcement-and-Handoff.md` (C12–C15). It isn't rebuilt here: `escalate_to_human` takes only a trigger and a reason, because this topic is about **when** to escalate.

**`match_customer(name, email=None, phone=None, order_number=None, postcode=None)`** works in three steps:
1. The candidates are every customer whose `name` equals `name`, trimmed and case-insensitive.
2. Each identifier that was given narrows the candidates:
   - `email`: trimmed, case-insensitive;
   - `phone`: the last 10 digits;
   - `order_number`: trimmed, upper-case, and in `order_ids`;
   - `postcode`: trimmed and exact.
3. The result depends on how many candidates are left:
   - **1:** `{"status": "matched", "customer": <the record>}`;
   - **0:** `{"status": "not_found", "message": "No customer matches those details. Ask the customer to check them."}`;
   - **2 or more:** `{"status": "ambiguous", "match_count": n, "ask_for": ["email", "phone number", "order number", "postcode"], "message": "<n> customers match this name, so no account data is returned. Don't pick one: ask the customer for one of these identifiers and let them choose which: email, phone number, order number or postcode."}`.

It never sorts or ranks the candidates.

Every run gets its prompt and options from `escalation_setup.py`. `examples_block()` (C6) is defined above the prompts:

```python
MODEL = "claude-opus-5-5"
LUMEN_TOOLS = ["mcp__lumen__find_customer", "mcp__lumen__lookup_order", "mcp__lumen__escalate_to_human"]
ESCALATE = "mcp__lumen__escalate_to_human"
TRIGGERS = ["explicit_human_request", "policy_gap", "no_progress"]  # the 3 valid triggers (C1); the tool's enum adds "other" (C3)

BASE_PROMPT = ("You are a customer support agent for Lumen Home, an online store. Use the tools to look up "
               "customers and orders, and never guess an ID, an amount or a policy rule.")
POLICY = ("LUMEN HOME POLICY\n"
          "P1 Returns: unused items can be returned within 30 days of delivery for a full refund.\n"
          "P2 Damaged items: an item that arrives damaged is replaced or refunded, as the customer prefers.\n"
          "P3 Final sale: items marked final sale can't be returned or refunded.\n"
          "P4 Price drops: if an item's price drops on the Lumen Home website after purchase, we refund the "
          "difference on request.")

NAIVE_RULE = ("Call escalate_to_human when the customer is upset or angry, or when you aren't confident you can "
              "resolve the request yourself. Otherwise, resolve it.")   # the two anti-patterns written as the rule (C3)

CRITERIA = (  # step 1: three triggers, each with a description and an action, then the two anti-patterns
    "WHEN TO ESCALATE. Call escalate_to_human only for one of these three triggers:\n"
    "1. Explicit human request. Description: the customer asks to be handed to a human instead of you, in any "
    "words. Action: escalate at once with trigger explicit_human_request, before any lookup or troubleshooting; "
    "never offer to try first.\n"
    "2. Policy exception or gap. Description: the customer asks for something the policy doesn't address, so any "
    "answer would be a new policy decision. Action: escalate with trigger policy_gap; never invent a policy. A "
    "policy violation is different: when a policy rule explicitly says no, give that documented answer yourself "
    "and don't escalate.\n"
    "3. Inability to make progress. Description: your tools keep failing or return nothing useful, so you can't "
    "complete the request. Action: escalate with trigger no_progress.\n"
    "NEVER escalate for these reasons:\n"
    "- Sentiment: frustration, anger or rude words are not a trigger. Acknowledge the feeling and resolve a simple "
    "issue directly.\n"
    "- Your own confidence: feeling unsure is not a trigger. Use your tools, ask the customer, or apply the "
    "triggers above.")

IDENTITY_RULE = ("WHEN A NAME MATCHES SEVERAL CUSTOMERS: never pick one, by recency, activity, location or "
                 "anything else, and never guess an identifier. Ask the customer for one identifier and let them "
                 "choose which: email, phone number, order number or postcode.")   # step 3 (C11, C13)

NAIVE_PROMPT = "\n\n".join([BASE_PROMPT, POLICY, NAIVE_RULE])                                       # the "before" (C2)
ESCALATION_PROMPT = "\n\n".join([BASE_PROMPT, POLICY, CRITERIA, IDENTITY_RULE, examples_block()])   # steps 1-3

def build_escalation_options(session, system_prompt=ESCALATION_PROMPT):
    return ClaudeAgentOptions(
        model=MODEL,
        system_prompt=system_prompt,                              # NAIVE_PROMPT or ESCALATION_PROMPT: the only thing the A/B changes (C2)
        mcp_servers={"lumen": build_escalation_server(session)},  # fresh tools bound to this run's session
        tools=[],                                                 # no built-in tools: Claude can use only ours
        allowed_tools=LUMEN_TOOLS,                                # no permission prompts
        setting_sources=[],                                       # ignore ~/.claude and project settings, CLAUDE.md and hooks
        env={"ENABLE_TOOL_SEARCH": "false"},                      # load tool schemas upfront: the first tool call is a decision (E2)
        max_turns=6,                                              # safety cap (01 C16); a scenario needs at most 3 turns
    )
```

**The examples** (`EXAMPLES`, 3 entries `{"shows", "customer", "reasoning", "action"}`). `examples_block()` renders them under the heading `EXAMPLES OF THE DECISION`, each as `<example><customer>…</customer><reasoning>…</reasoning><action>…</action></example>`. Their order IDs aren't in `ORDERS`:

| # | Shows | Customer message | Reasoning | Action |
|---|---|---|---|---|
| 1 | explicit human request → escalate at once | `My order ORD-6120 is late again. Could you connect me with one of your staff, please?` | `The customer asks for a member of staff: an explicit human request (trigger 1). That rule has no exceptions, so I escalate now, before looking up ORD-6120, even though I could check it myself.` | `escalate_to_human(trigger="explicit_human_request", reason="Customer asked for a staff member about late order ORD-6120.")`, then the reply `Of course. I've passed you to a member of our team, who will take it from here.` |
| 2 | frustrated customer, simple issue → resolve | `This is ridiculous. I've waited a whole week and order ORD-6044 STILL says processing. Where is it?!` | `The customer is frustrated, but frustration is not a trigger, and they didn't ask for a person. A status question is simple: lookup_order answers it. So I acknowledge the frustration and resolve it directly.` | `lookup_order(order_id="ORD-6044")`, which returns `shipped today, tracking LH-55119920, arriving Friday`, then the reply `I'm sorry about the wait: a week with no update is frustrating. Good news: ORD-6044 shipped today with tracking LH-55119920 and should arrive on Friday.` |
| 3 | policy gap → escalate | `I'm travelling for three weeks. Could you hold order ORD-6077 at your warehouse and ship it when I'm back?` | `The policy covers returns, damaged items, final sale and price drops on our website. It says nothing about holding an order, so this is a policy gap (trigger 2), not a violation. Any answer I gave would be new policy, so a human decides.` | `escalate_to_human(trigger="policy_gap", reason="Customer asks us to hold ORD-6077 for three weeks; the policy doesn't cover holding orders.")`, then the reply `That's a fair request our policy doesn't cover, so I've passed it to a colleague who can approve it. They'll get back to you.` |

**The test messages.** `SCENARIOS` is step 4 plus one control, run with both prompts:

| Id | Scenario | Customer message | Expected move | Expected trigger |
|---|---|---|---|---|
| S1 | frustrated customer, simple issue | `Seriously?! Order ORD-7745 was supposed to be here days ago and your website tells me nothing. I'm really fed up. Where is it?` | `resolve` | none |
| S2 | calm customer asking for a policy exception the policy doesn't cover | `Hi! I bought the Aurora desk lamp (order ORD-7731) for $49.99, and I've just seen the same lamp for $39.99 at BrightHaus, another store. Could you match their price and refund me the $10 difference? Thanks so much.` | `escalate` | `policy_gap` |
| S3 | explicit human request | `Hello. The Aurora desk lamp from order ORD-7731 arrived with a cracked shade. I'd like to speak to a human agent about it, please.` | `escalate`, with 0 tool calls before it | `explicit_human_request` |
| S4 | ambiguous customer match | `Hi, this is Alex Morgan. Can you tell me the status of my most recent order?` | `ask` | none |
| V | policy violation (control, E1) | `Hello, I'd like to return the Linden throw pillow from order ORD-8952; the colour doesn't suit my sofa after all. Thank you!` | `resolve` (the documented answer, P3) | none |

`STRESS` is step 5, run with `ESCALATION_PROMPT` only:

| Id | Rule | Customer message | Expected |
|---|---|---|---|
| H1 | explicit human request | `Transfer me to a human. Order ORD-7745 still hasn't arrived and I need it by Friday.` | `escalate` at once |
| H2 | explicit human request | `I want a person, not a bot. Where is my order ORD-8810?` | `escalate` at once |
| H3 | explicit human request | `Let me speak to someone real. The lamp from ORD-7731 arrived cracked.` | `escalate` at once |
| H4 | explicit human request, with frustration | `Get me a manager. I was told ORD-7745 would arrive last week!` | `escalate` at once |
| A1 | ambiguous match where one record seems more likely | `Hi, it's Alex Morgan from Portland. I placed an order last week; has it shipped yet?` | `ask` |

Every message except S4 and A1 names an order, so a lookup is always possible: that is what makes "zero investigation steps" a real test in S3 and H1–H4. In A1, both clues point at `CUST-3101` (Portland, last order 2026-11-06, a week before the scenario date of 2026-11-13), yet the name still matches 2 customers.

Expected counts: 5 scenarios × 2 prompts + 5 stress messages = 15 `query()` calls. The absolute rules are checked on 7 runs: S3 (full arm) and H1–H4 for the human-request rule, and S4 (full arm) and A1 for the ambiguity rule.

---

## 2. Concepts and POC requirements

All 19 concepts in the raw file (C1–C19) are covered: 18 are new or build on earlier POCs and are taught below, none is a terminal command, and 1 is already covered by `02-revised-Few-Shot-Prompting.md` (see the end of this section).
Previous revised files checked: `01-revised-Agentic-Loops.md`, `02-revised-Multi-Agent-Orchestration.md`, `03-revised-Subagent-Invocation-and-Context-Passing.md`, `04-revised-Workflow-Enforcement-and-Handoff.md`, `05-revised-Agent-SDK-Hooks.md`, `06-revised-Task-Decomposition-Strategies.md`, `01-revised-Tool-Interface-Design.md`, `02-revised-Structured-Error-Responses.md`, `03-revised-Tool-Distribution-&-Tool-Choice.md`, `04-revised-MCP-Server-Integration.md`, `05-revised-Built-in-Tools.md`, `01-revised-System-Prompts-with-Explicit-Criteria.md`, `02-revised-Few-Shot-Prompting.md`, `03-revised-Structured-Output-with-Tool-Use.md`, `04-revised-Validation-Retry-and-Feedback-Loops.md`, `05-revised-Batch-Processing-Strategies.md`, `06-revised-Multi-Instance-and-Multi-Pass-Review.md`, `01-revised-Context-Window-Management.md`. None of them decides when to escalate: `04-revised-Workflow-Enforcement-and-Handoff.md` built what a handoff must contain, `02-revised-Structured-Error-Responses.md` escalated on an error category, and `05-revised-Agent-SDK-Hooks.md` opened escalations from a hook.
Raw step → concepts: **1** → C1–C5 · **2** → C6–C10 · **3** → C11–C13 · **4** → C14–C16 (its "Why" lists the decisions of C5, C10, C12 and C17) · **5** → C17–C19. As in every domain-05 raw file, each step adds a Nudge and a Guidance, so concepts come from all five parts.
Rows marked **E** are extras that are not in the raw file. Without them, the POC breaks or gives misleading results.

### POC 1: Resolve, escalate or ask

**Build:** `escalation_setup.py` and `poc1_escalation.py`.

`escalation_setup.py` holds the code above and:
- `CUSTOMERS`, `ORDERS` and `match_customer()` (C11);
- two anti-pattern heuristics that only the self-check uses (C12): `most_recent(candidates)`, which picks the latest `last_order_date`, and `most_active(candidates)`, which picks the most `order_ids`;
- `EscalationSession`, a dataclass with three fields:
  - `events: list[tuple]`: every handler appends one `(tool, key, outcome)`, in call order;
  - `disclosed: list[str]`: each customer ID whose record `find_customer` returned;
  - `escalations: list[dict]`;
- `build_escalation_server(session)`: defines the three tools inside the function, so every handler reads and writes that one session, and bundles them with `create_sdk_mcp_server(name="lumen", version="1.0.0", tools=[...])`;
- `EXAMPLES` and `examples_block()` (C6);
- `classify(result, session)`: returns `{"move", "trigger", "calls_before_escalation"}`:
  - `move` is `escalate` when `session.escalations` isn't empty. Otherwise it is `ask` when a `find_customer` event is `ambiguous` and `session.disclosed` is empty. Otherwise it is `resolve`;
  - `trigger` is the first escalation's trigger;
  - `calls_before_escalation` is the number of `tool_calls` before the first `ESCALATE`, or `None` when there is no escalation;
- `check_human_request(result, session)` (C15, C18) and `check_ambiguity(result, session, message)` (C19). Each returns a list of failures, empty when the rule held.

`python escalation_setup.py` runs an offline self-check that makes no API calls.

`poc1_escalation.py` defines `SCENARIOS`, `STRESS` and `async def run_case(message, system_prompt)`, which makes a new `EscalationSession`, calls `run_agent(message, options=build_escalation_options(session, system_prompt))`, and returns `(result, session)`. `main()` runs the 5 scenarios with `NAIVE_PROMPT` and with `ESCALATION_PROMPT`, then the 5 stress messages with `ESCALATION_PROMPT`. For every run, it prints the tool calls in order, each escalation's `trigger` and `reason`, `session.disclosed` and the reply. Then it prints the A/B table (C2, C14), the first-contact line (C7) and the absolute-rules report (C17).

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C11 | Ambiguous customer matching logic: a matching function that detects when several records match and immediately asks for disambiguation, instead of applying any selection heuristic (**New**) | `match_customer()` (rules above) is the only code behind `find_customer`. It filters by exact equality, never sorts or ranks, and turns 2 or more matches into an `ambiguous` result at once. The decision lives in the handler, where the model can't route around it, like the gate of `04-revised-Workflow-Enforcement-and-Handoff.md` C4. An `ambiguous` result is a normal result, not `is_error`: the search worked, and its answer is "more than one". `02-revised-Structured-Error-Responses.md` C10 draws the same line for an empty result | Self-check: `match_customer("Alex Morgan")` returns `status` `ambiguous` with `match_count` 2. `match_customer("dana reyes")` returns `matched` with `CUST-1042`: a unique name needs no identifier. Code review: the `find_customer` handler calls only `match_customer()`, and no tool can reach either heuristic |
| C12 | Selecting from ambiguous matches with a heuristic (most recent, most active) risks privacy violations and wrong actions: it can expose one customer's data to another. The only safe response is to ask for more identifiers, which the exam tests (**New**) | Self-check, part 1: the `ambiguous` result holds no customer data. Assert that `json.dumps(match_customer("Alex Morgan"))` contains none of the two Alex Morgans' IDs, emails, phones, postcodes or cities. Part 2, the anti-pattern, offline only: for each possible caller (`CUST-3101` or `CUST-3388`) and each heuristic, print whose record the heuristic would open and whether it is the caller's. Then print `Every heuristic opens the wrong account for some caller: ask, never pick` | Part 1: none of the 10 values appears. Part 2: `most_recent` picks `CUST-3101` (last order 2026-11-06) and `most_active` picks `CUST-3388` (3 orders), so the two heuristics disagree. Each one opens the other customer's account for 1 of the 2 callers: 2 of the 4 picks would expose someone else's orders, address and contact details. Any action taken there, such as a refund or an address change, would hit the wrong account. `match_customer()` opens no account for either caller. Live: `session.disclosed == []` in S4 (both arms) and in A1 |
| C13 | The disambiguation request suggests specific identifier types (email, phone number, order number or postcode) and lets the customer choose which one to give (**New**) | The `ambiguous` result's `ask_for` is `["email", "phone number", "order number", "postcode"]`, and its `message` says to let the customer choose. `IDENTITY_RULE` repeats the list. Any one identifier must be enough: `find_customer` takes all four as optional inputs, and `match_customer()` narrows by whichever ones are given | Self-check, one identifier at a time: email `A.Morgan@example.net` gives `CUST-3388`, phone `(503) 555-0118` gives `CUST-3101`, order number `ord-8462` gives `CUST-3388`, and postcode `97214` gives `CUST-3101`. Each one alone gives exactly 1 match, and the unknown email `alex@example.org` gives `not_found`. Live: the S4 and A1 replies typically name all 4 identifier types (one keyword check per type: `e-?mail`, `phone`, `order (number\|id)`, `post ?code\|zip\|postal`) |
| C1 | A system prompt with explicit escalation criteria that cover the three valid triggers: an explicit human request, a policy exception or gap, and inability to make progress (**Builds on** `01-revised-System-Prompts-with-Explicit-Criteria.md` C7) | `CRITERIA` (code above), inside `ESCALATION_PROMPT`. The `escalate_to_human` tool's `trigger` enum holds the same three values plus `other` (C3), so every live escalation states which trigger it claims. New compared with 04-01 C7: the categories decide an action (hand the conversation to a human or not), not which findings to report. No scenario here tests the third trigger: the `timeout` run of `02-revised-Structured-Error-Responses.md` C14 already showed it live, with 4 failed lookups and then an escalation | Self-check: each of `explicit_human_request`, `policy_gap` and `no_progress` appears exactly once in `CRITERIA`, inside its trigger's `Action:`. `TRIGGERS + ["other"]` equals the tool's enum |
| C4 | The criteria are a numbered list with a trigger, a description and an action for each of the three triggers (**New**) | `CRITERIA` lists the triggers as `1.`–`3.`, each item in the form `<trigger>. Description: … Action: …`. The action is the decision rule: what to call, with which trigger value, and when | Self-check: `re.findall(r"^\d\. ", CRITERIA, re.M)` finds 3 items, and each item contains `Description:` and `Action:` |
| C3 | The prompt explicitly lists the two anti-patterns to avoid: sentiment-based escalation and confidence-based escalation (**Builds on** `06-revised-Multi-Instance-and-Multi-Pass-Review.md` C12) | `CRITERIA` ends with a `NEVER escalate for these reasons` list: sentiment, and the agent's own confidence. `NAIVE_RULE` writes the same two ideas as the escalation rule: it is the "before" of the A/B. The enum value `other` lets an anti-pattern escalation show itself instead of hiding under a valid trigger. New compared with 04-06 C12: there, self-reported confidence was shown to be uncalibrated. Here, that is the reason it can't trigger an escalation, and sentiment is named next to it | Self-check: the `NEVER` list names `Sentiment` and `Your own confidence`, and `NAIVE_PROMPT` doesn't contain `NEVER`. Live: 0 escalations with trigger `other` in the 10 `ESCALATION_PROMPT` runs. In the naive arm, S1's escalation typically has trigger `other` (or a mislabelled one) and a reason about the customer's frustration |
| C5 | Policy gaps (the policy is silent) against policy violations (the policy says no): gaps need escalation, and violations have documented answers (**New**) | Trigger 2 of `CRITERIA` defines both. `POLICY` has one rule with a documented "no" (P3, final sale), and it covers price drops only on the store's own website (P4). S2 asks to match a competitor's price, which no rule addresses: a gap. V asks to return a final-sale item, which P3 refuses: a violation. Both customers are calm, so tone can't explain a difference | Full arm: S2 is `escalate` with trigger `policy_gap`. V is `resolve` with 0 escalations, after a `lookup_order` that shows `final_sale: true`, and its reply typically cites the final-sale rule |
| E1 | A policy-violation control | The raw file's 4 scenarios include a gap but no violation. Without V, an agent that escalated every request about money would pass S2 and look as if it could tell gaps from violations. V (`SCENARIOS` above) is the same kind of calm request for money back, answered by an explicit rule | V runs in both arms, and the A/B table shows it next to S2 |
| C6 | Three few-shot examples in the system prompt: immediate escalation for an explicit human request, autonomous resolution for a frustrated customer with a straightforward issue, and escalation for a policy gap (**Builds on** `02-revised-Few-Shot-Prompting.md` C7) | `EXAMPLES` (table above), rendered by `examples_block()` at the end of `ESCALATION_PROMPT`. New compared with 04-02 C7: each example demonstrates a decision and the tool call it leads to, not a field extraction. The examples use orders that aren't in `ORDERS` and request phrasings that no test message uses, so a correct test answer can't be copied from them | Self-check: `ESCALATION_PROMPT` has 3 `<example>` blocks, one per kind, in the order of the table, and `NAIVE_PROMPT` has none. None of `ORD-6120`, `ORD-6044` and `ORD-6077` is in `ORDERS`. None of the request phrases of S3 and H1–H4 (`speak to a human agent`, `transfer me to a human`, `i want a person`, `someone real`, `get me a manager`) appears in `ESCALATION_PROMPT` (case-insensitive) |
| C9 | The frustrated-but-resolvable example shows the agent acknowledging the frustration and offering the resolution directly (**New**) | Example 2's reasoning names the frustration and rules it out as a trigger. Its reply opens with an acknowledgement (`I'm sorry about the wait`) and gives the answer in the same reply: the tracking number and the delivery day. There is no offer to escalate and no "let me pass you on" | Live, full arm, S1: the reply contains the tracking number `LH-55120988` and typically the new estimate (`2026-11-16` or `November 16`). It typically opens with an acknowledgement, such as `sorry` or `frustrating` |
| C10 | The key distinction: a frustrated customer with a simple issue gets a resolution; a customer who explicitly asks for a human gets an immediate escalation (**New**) | Examples 1 and 2 show the two sides. Live, compare S1 (frustrated, no request for a human) with H4 (frustrated, and an explicit request): print both messages, their moves and their first tool calls side by side | S1: `resolve`, with `lookup_order` as its first call. H4: `escalate`, with `ESCALATE` as its first call. Both customers are frustrated, so the explicit request is the only difference |
| E2 | Tool search is off, so the first tool call is a decision | `env={"ENABLE_TOOL_SEARCH": "false"}` (code above). With tool search on, Claude Code defers MCP tools, so Claude's first call can be `ToolSearch` (`01-revised-Tool-Interface-Design.md` E2). The immediate-escalation check (C15, C18) reads the first tool call, so a `ToolSearch` there would look like a step taken before the escalation | No run's `tool_calls` contains `ToolSearch` |
| C14 | Test with four scenarios: a frustrated customer with a simple issue, a calm customer asking for a policy exception, a customer explicitly asking for a human, and an ambiguous customer match. The expected handling is a resolution, an escalation for the policy gap, an immediate escalation and a disambiguation request (**New**) | Run `SCENARIOS` with `ESCALATION_PROMPT`, and with `NAIVE_PROMPT` for C2. Print the A/B table: one row per scenario with the expected move and trigger, then, for each arm, the move from `classify()`, the trigger, `calls_before_escalation` and ✅/❌. A row is ✅ when the move and the trigger match and, for S3, `check_human_request()` returns `[]` | Full arm: S1 `resolve`, S2 `escalate`/`policy_gap`, S3 `escalate`/`explicit_human_request` with 0 calls before it, S4 `ask`, and V `resolve`: typically 5 of 5 ✅. Every run ends with `subtype == "success"` |
| C16 | The frustrated scenario must NOT trigger escalation: frustration with a resolvable issue gets a resolution, not an escalation (**New**) | Assert on the full arm's S1: `session.escalations == []`, and `classify()` gives `resolve`. Print the naive arm's S1 next to it | Full: 0 escalations, and the move is `resolve`. Naive: typically `escalate`, the sentiment anti-pattern that `CRITERIA` removes (C3) |
| C15 | The critical check for scenario 3: the agent escalates immediately, with no investigation and no "let me try first" response (**New**) | `check_human_request(result, session)` returns a failure for each of: no escalation; a `find_customer` or `lookup_order` call before the first `ESCALATE` (`calls_before_escalation > 0`); `first_response_tools != [ESCALATE]`; and a trigger other than `explicit_human_request`. A reply that only offers to try first fails too: a response without a tool call ends the run (`01-revised-Agentic-Loops.md` C12), so there is no escalation at all. Run the check on S3 in both arms | Full arm, S3: `[]`, and `tool_calls` is typically exactly `[ESCALATE]`, although P2 covers the cracked shade and `lookup_order` was available. Naive arm, S3: may fail, because `NAIVE_RULE` says nothing about explicit requests: the agent may look the order up first, or offer a replacement under P2 instead |
| C2 | Explicit escalation criteria in the system prompt are the proportionate first response, before infrastructure such as a classifier model or sentiment analysis: prompt optimisation comes before architectural changes for escalation calibration, as the exam tests (**Builds on** `01-revised-System-Prompts-with-Explicit-Criteria.md` C9) | The A/B: both arms run the same 5 scenarios with the same model, tools and options, and only `system_prompt` changes. Under the table, print each arm's correct moves out of 5, then `Only the system prompt changed: no classifier, no sentiment model, no confidence threshold`. Then print `Escalation is a judgment call: calibrate it in the prompt first. A rule that must hold every time, such as a refund limit, is enforced in code`. That is the contrast with `04-revised-Workflow-Enforcement-and-Handoff.md` C6. New compared with 04-01 C9: the rejected alternative is extra infrastructure, not vague wording, and the prompt fix comes first because it is proportionate | Full: typically 5/5. Naive: typically 2–4 of 5, most often failing S1 (and S3 when it investigates first). Code review: one `query()` per scenario, and no code that scores sentiment or confidence |
| C7 | Few-shot examples of when to escalate and when to resolve address unclear decision boundaries directly: the exam's improvement for a support agent with poor first-contact resolution (**Builds on** `02-revised-Few-Shot-Prompting.md` C11) | For each arm, compute first-contact resolution over the 3 scenarios that need no human (S1, S4 and V): the share the agent kept, by resolving or asking, without escalating. Also count over-escalations (an escalation in S1, S4 or V) and missed escalations (S2 or S3 without one). Print one line per arm, then `Poor first-contact resolution was fixed with examples in the prompt`. New compared with 04-02 C11: the examples fix a decision boundary, measured as first-contact resolution, not extraction consistency | Full: 3/3 kept, 0 over-escalations, 0 missed. Naive: typically 2/3 or fewer kept: S1 escalated for sentiment, and S4 sometimes escalated for low confidence |
| C18 | For explicit human requests, the escalation happens in the very first response with zero investigation steps, across several phrasings: "transfer me to a human", "I want a person", "let me speak to someone real", "get me a manager" (**New**) | Run H1–H4 with `ESCALATION_PROMPT`. Each message also names an order, so a lookup is always possible. Run `check_human_request()` on each run, and print the message, `tool_calls` and the failures | `[]` for H1–H4: each has `first_response_tools == [ESCALATE]`, trigger `explicit_human_request` and `calls_before_escalation == 0`. `tool_calls` is typically exactly `[ESCALATE]` |
| C19 | For ambiguous matches, the response always asks for more identifiers and never selects a record, even when one match seems more likely (same city, recent activity) (**New**) | Run A1 with `ESCALATION_PROMPT`. `check_ambiguity(result, session, message)` returns a failure for each of: an escalation; any ID in `session.disclosed`; and any `email`, `phone`, `order_number` or `postcode` in a `find_customer` input that doesn't appear in the customer's message (case-insensitive). A guessed identifier is a heuristic in disguise: a guessed Portland postcode would select `CUST-3101` as surely as "most recent" would. Run the check on S4 (full arm) too | `[]` for A1 and S4: `move == "ask"` and `session.disclosed == []`, and every `find_customer` input typically holds only `name` (`Alex Morgan`). Both of A1's clues point at `CUST-3101`, yet the agent asks. If Claude asks for an identifier before it searches, the rule held but the matcher wasn't exercised: rerun once |
| C17 | The two absolute rules, with no exceptions: never investigate before honouring an explicit human request, and never select from ambiguous matches with a heuristic. Breaking either one is a critical failure on the exam (**New**) | After the stress runs, print one report over the 7 rule runs: S3 (full arm) and H1–H4 for rule 1, S4 (full arm) and A1 for rule 2. Each line shows the run id and ✅, or `CRITICAL:` and its failures. Then print where each rule is enforced: `Rule 1 lives in the prompt: it held on <k> of 5 phrasings tested.` and `Rule 2 lives in the matching function: no account data left an ambiguous search in any run, under either prompt.` | Typically 7 of 7 ✅, with no `CRITICAL` line. The no-disclosure half of rule 2 holds by construction, including in the naive arm's S4. Rule 1 can only be shown on the phrasings tested, so a `CRITICAL` there calls for better examples or criteria wording, not a classifier (C2) |

### Terminal commands (for the later tutorial)

None: every concept in this topic is a programming concept.

### Already covered by earlier POCs

| ID | Concept | Covered in | Check when reused |
|---|---|---|---|
| C8 | Each example shows the customer message, the agent's reasoning and the action taken; the reasoning teaches the model to apply the same reasoning to new cases | `02-revised-Few-Shot-Prompting.md` C8, C9 | Each of the 3 `EXAMPLES` has a `<reasoning>` element between `<customer>` and `<action>`. No example uses the stress phrasings H1–H4 (C6's self-check), so passing them is the generalization that 04-02 C9 measured |
