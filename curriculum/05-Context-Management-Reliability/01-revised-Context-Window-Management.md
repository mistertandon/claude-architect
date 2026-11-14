# Context Window Management: Revised POC Requirements (5 steps → 2 POCs, Claude Agent SDK)

> **Source:** `01-raw-Context-Window-Management.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Context Management & Reliability → Context Window Management · **Build with:** Claude Agent SDK for Python (`claude_agent_sdk`)

---

## 1. Verdict: 2 POCs

The 5 raw steps are not 5 separate concepts. Steps 1–4 follow **one support conversation through its context window**: step 1 copies the facts out of each tool result, step 3 cuts the rest of the result down, step 2 puts the facts on top of every prompt, and step 4 summarises the history and checks what survived. Step 5 is **a different kind of input**: one long aggregation of many sources, where a finding isn't lost from the history but overlooked where it sits.

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: Case facts that survive summarisation** | **What a long conversation keeps, and in what form:** one `PostToolUse` hook copies the transactional facts out of each raw tool result and hands Claude a 5-field trim of a 42-field order lookup (88.3% smaller). Every prompt starts with the facts as a delimited JSON block, outside the history. After turn 4, a lossy summary replaces the history, and only the version with the block can still quote $247.83, ORD-8891 and the order date | 1, 2, 3, 4 |
| **POC 2: Key findings first** | **Where a finding sits in a long input:** the same 9 back-office findings are combined three ways: plain concatenation, the same with a "read everything" note, and a Key Findings Summary above headed sections. The one finding that blocks a refund sits at 42–57% of the plain text and in the first 8% of the structured one, and a reviewer decides on both layouts | 5 |

**What changes with the Agent SDK:** within a session, the context only grows ("Everything accumulates: the system prompt, tool definitions, conversation history, tool inputs, and tool outputs"). When the context window nears its limit, the SDK summarises on its own: automatic compaction (or `/compact` sent as a prompt) replaces older messages with a summary the model writes. A `PreCompact` hook fires first, and a `SystemMessage` with subtype `compact_boundary` marks it in the stream. Which values that summary keeps is up to the model, so it can't show summarisation losing a number on purpose. POC 1 therefore keeps the history in Python. Each customer turn is a fresh `query()`, which "starts fresh with no memory of previous interactions", and Python writes its whole prompt: the case facts block, then the summary or the earlier turns, then the new message. That is the raw file's "every API call" on the stateless Messages API. The tool boundary uses the SDK's own hook: a `PostToolUse` callback sees each raw result before Claude does, records its facts, and returns the trimmed result as `updatedToolOutput` (`05-revised-Agent-SDK-Hooks.md`). Claude Code applies the same idea to itself: its docs warn that compaction "replaces older messages with a summary, so specific instructions from early in the conversation may not be preserved", and put persistent rules in CLAUDE.md, which "is re-injected on every request". Two things can only be observed, not coded. One is what the agent can still quote after summarisation: POC 1 checks its replies for the exact values. The other is whether a model overlooks a finding in the middle of a long input: POC 2 measures the finding's position, which is deterministic, and runs the reviewer once per layout.

- **Why not 1 POC:** POC 2 has a different input and a different failure. Its input is one long aggregation of 9 sources, not a conversation, and its finding is overlooked in place, not lost from history. It needs no tools, no hook and no history, and its main measurement, the finding's position, is offline. In one POC, two unrelated experiments would share one script.
- **Why not 3 or more:** step 1's extractor and step 3's trimmer run in the same `PostToolUse` hook on the same result (facts first, then the trim). Step 2's block is filled from step 1's store, and step 4 only tests steps 1–3 on one conversation. A separate trimming POC would rebuild the tools, the hook and the runner to measure one function.

**Applies to both POCs:** Python 3.10+, `pip install claude-agent-sdk` (a recent 0.2.x; it bundles the Claude Code binary), `ANTHROPIC_API_KEY` set in the environment (never hard-coded), mock data only, and beginner-friendly code (small, commented scripts). Every agent turn goes through `run_agent()` from `01-revised-Agentic-Loops.md` (`poc2_agent_loop.py`), as extended in `05-revised-Agent-SDK-Hooks.md` (`options=`, `tool_results`), and the hook reuses that file's `response_text()` and `same_shape()` (05 E3). The tools follow `tools.py` from `01-revised-Agentic-Loops.md` (C2–C3): `@tool` with a full JSON Schema dict, async handlers that return `{"content": [...]}`, and `is_error` instead of raising. The data belongs to Lumen Home, the made-up store of `01-revised-Tool-Interface-Design.md`, and its customer `CUST-1042` Dana Reyes (gold tier, 12 Alder St, Portland, OR 97205, Visa ending 4417), with two new orders. Every POC 1 turn gets its options from `context_setup.py`, and POC 2 imports `MODEL` from it:

```python
MODEL = "claude-opus-5-5"
LUMEN_TOOLS = ["mcp__lumen__lookup_order", "mcp__lumen__process_refund"]

FACT_FIELDS = {                       # the fixed set of transactional field types (C2) and the fields that carry them
    "customer_id": ["customer_id"],
    "reference":   ["order_id", "refund_id"],
    "amount":      ["total_amount", "refund_amount"],
    "date":        ["order_date", "refund_date"],
    "status":      ["order_status", "refund_status"],
}
TASK_FIELDS = {                       # what each task needs from an order lookup (C7)
    "refund":   ["order_id", "order_date", "total_amount", "return_eligible", "item_description"],
    "delivery": ["order_id", "carrier", "tracking_number", "shipped_date", "delivered_date"],
}

AGENT_PROMPT = (
    "You are a customer support agent for Lumen Home, an online store. Look orders up with lookup_order and refund "
    "them with process_refund; never guess an ID, a date or an amount. Each message you receive is built from labelled "
    "sections: CASE FACTS holds exact values copied from tool results in this case and is always correct; "
    "CONVERSATION SUMMARY is a shortened record of earlier turns that may leave details out; RECENT TURNS are the "
    "latest turns, word for word; CUSTOMER MESSAGE is what you answer now. Reply to the customer message only.")

@dataclass
class CaseState:                                      # one per conversation (05's HookState pattern)
    case_facts: dict = field(default_factory=dict)    # the case facts: written only by the hook, never summarised (C3)
    sizes: list[tuple] = field(default_factory=list)  # (tool, raw_chars, sent_chars) for every result the hook saw (C10)
    refunds: list[dict] = field(default_factory=list)

def build_case_options(state):
    return ClaudeAgentOptions(
        model=MODEL,
        system_prompt=AGENT_PROMPT,                        # names the sections of every prompt (C5)
        mcp_servers={"lumen": build_lumen_server(state)},  # lookup_order and process_refund, bound to this state
        tools=[],                                          # no built-in tools: Claude can use only ours
        allowed_tools=LUMEN_TOOLS,                         # run without permission prompts
        hooks=build_case_hooks(state),                     # PostToolUse: record the facts, then trim (C1, C9)
        setting_sources=[],                                # ignore ~/.claude and project settings, CLAUDE.md and hooks
        env={"ENABLE_TOOL_SEARCH": "false"},               # load tool schemas upfront: no ToolSearch calls
        max_turns=6,                                       # safety cap (01 C16); one customer turn needs at most 3
    )
```

---

## 2. Concepts and POC requirements

All 17 concepts in the raw file (C1–C17) are covered: all 17 are new or build on earlier POCs and are taught below, none is a terminal command, and none was already covered by an earlier revised file (see the end of this section).
Previous revised files checked: `01-revised-Agentic-Loops.md`, `02-revised-Multi-Agent-Orchestration.md`, `03-revised-Subagent-Invocation-and-Context-Passing.md`, `04-revised-Workflow-Enforcement-and-Handoff.md`, `05-revised-Agent-SDK-Hooks.md`, `06-revised-Task-Decomposition-Strategies.md`, `01-revised-Tool-Interface-Design.md`, `02-revised-Structured-Error-Responses.md`, `03-revised-Tool-Distribution-&-Tool-Choice.md`, `04-revised-MCP-Server-Integration.md`, `05-revised-Built-in-Tools.md`, `01-revised-System-Prompts-with-Explicit-Criteria.md`, `02-revised-Few-Shot-Prompting.md`, `03-revised-Structured-Output-with-Tool-Use.md`, `04-revised-Validation-Retry-and-Feedback-Loops.md`, `05-revised-Batch-Processing-Strategies.md`, `06-revised-Multi-Instance-and-Multi-Pass-Review.md`. None manages conversation history: `05-revised-Agent-SDK-Hooks.md` rewrote tool results for their format, not their size, and `06-revised-Task-Decomposition-Strategies.md` measured position effects across 14 files and fixed them by splitting the work.
Raw step → concepts: **1** → C1–C3 · **2** → C4–C6 · **3** → C7–C10 · **4** → C11–C14 · **5** → C15–C17. Each raw step in this domain adds a Nudge and a Guidance to its instruction, "Why" and "You should see", so concepts come from all five parts.
Rows marked **E** are extras that are not in the raw file. Without them, the POC breaks or gives misleading results.

### POC 1: Case facts that survive summarisation

**Build:** `context_setup.py` and `poc1_case_facts.py`.

`context_setup.py` holds the code above and:
- `ORDER_8891` (below) and `REFUND`, the record `process_refund` returns;
- `build_lumen_server(state)`, which defines the two tools inside the function, so both handlers share one `CaseState`, and bundles them with `create_sdk_mcp_server(name="lumen", version="1.0.0", tools=[...])`;
- `extract_case_facts(result)` (C1), `trim_result(result, task="refund")` (C7) and `build_case_hooks(state)` (C9);
- the four section headers, `render_history(turns)` and `build_prompt(case_facts, summary, recent, message)` (C5);
- `LOSSY_SUMMARY` and `summarise(turns)` (C11, E2), and `quoted(text)` (C13).

`python context_setup.py` runs an offline self-check that makes no API calls.

`poc1_case_facts.py` defines `TURNS`, `SUMMARISE_AFTER = 4` and `async def run_turn(n, message, state, summary, recent, with_facts)`. `run_turn()` builds the prompt, calls `run_agent(prompt, options=build_case_options(state))` and returns the turn record `{"n", "customer", "tools", "agent", "prompt_chars", "lookups"}`. `tools` holds one `(short tool name, text Claude received)` per `tool_results` entry, and `lookups` is the number of `lookup_order` results in the prompt's history. `main()` runs turns 1–4 once, summarises, and then runs turns 5–6 in two arms, `with-facts` and `without-facts`: 4 + 2 × 2 = 8 `query()` calls. The script prints each prompt's size, each tool result Claude received, each reply and the case facts after each turn, then the cost table (C8) and the survival table (C13).

`ORDER_8891` is the full record that `lookup_order` returns: 42 fields, and `json.dumps()` gives 1,341 characters. Its total is $229.47 + $18.36 tax = $247.83.

```python
ORDER_8891 = {
    "order_id": "ORD-8891", "order_date": "2026-03-03", "order_status": "delivered",
    "customer_id": "CUST-1042", "customer_name": "Dana Reyes", "customer_email": "dana.reyes@example.com",
    "loyalty_tier": "gold",
    "item_sku": "AUR-FL-BR-01", "item_description": "Aurora floor lamp, brushed brass", "item_quantity": 1,
    "item_unit_price": 229.47, "item_weight_kg": 6.8,
    "currency": "USD", "subtotal_amount": 229.47, "discount_amount": 0.0, "shipping_amount": 0.0,
    "tax_amount": 18.36, "total_amount": 247.83,
    "payment_method": "card", "card_brand": "Visa", "card_last4": "4417", "payment_status": "captured",
    "invoice_number": "INV-2026-03318",
    "shipping_address": "12 Alder St, Portland, OR 97205", "carrier": "Lumen Freight",
    "tracking_number": "LH-55129904", "shipped_date": "2026-03-04", "delivered_date": "2026-03-07",
    "warehouse_id": "WH-PDX-2", "fulfillment_status": "fulfilled",
    "return_eligible": True, "return_window_ends": "2026-04-06", "return_policy_code": "RP-30-STD",
    "sales_channel": "web", "loyalty_points": 229, "marketing_opt_in": False, "fraud_score": 0.02,
    "created_at": "2026-03-03T18:42:11Z", "updated_at": "2026-03-07T15:05:42Z",
    "delivery_instructions": "Leave at the side door.",
    "customer_note": "A birthday present, please pack it carefully!",
    "internal_note": "Customer called on 2026-03-05 about the delivery window.",
}
```

The tools:

| Tool | Description (what Claude reads) | Input | Behavior |
|---|---|---|---|
| `mcp__lumen__lookup_order` (`readOnlyHint=True`) | `"Looks up one Lumen Home order by its order ID (ORD- plus 4 digits) and returns the order record as JSON."` | `order_id` (string) | `ORD-8891` (trimmed, case-insensitive) returns `json.dumps(ORDER_8891)`: all 42 fields, as an order API you can't change would. Any other ID returns `is_error: True`, `No order matches '<id>'.` |
| `mcp__lumen__process_refund` | `"Refunds the full total of a returnable Lumen Home order to the card that paid for it, and returns the refund record as JSON."` | `order_id` (string) | Refunds a `return_eligible` order once: it appends to `state.refunds` and returns `json.dumps(REFUND)`, with `refund_id` `RF-<n:04d>`. `REFUND = {"refund_id": "RF-0001", "order_id": "ORD-8891", "refund_amount": 247.83, "refund_date": "2026-03-20", "refund_status": "processed", "refund_method": "Visa ending 4417", "message": "Refunds usually reach the card within 5-7 business days. A prepaid return label has been emailed; please send the lamp back within 14 days."}`. A second refund of the same order returns `is_error: True`, `Order ORD-8891 was already refunded (RF-0001).` |

`TURNS`, the customer's 6 messages:

| # | Customer message | Typically |
|---|---|---|
| 1 | `Hi, this is Dana Reyes (customer CUST-1042). The floor lamp from order ORD-8891 arrived with a cracked base. Can I return it?` | `lookup_order`; the case facts now hold 5 values |
| 2 | `Yes please, refund it to my card.` | `process_refund`; the case facts now hold 9 values |
| 3 | `How long until the money shows up?` | no tool: the refund record says 5–7 business days |
| 4 | `Do I need to send the lamp back first?` | no tool. Then the summary replaces turns 1–4 |
| 5 | `What's my refund reference number, and has the refund actually gone through?` | probe: `RF-0001` |
| 6 | `Before I go, can you confirm the refund amount, my order number and the date I placed that order?` | probes: `247.83`, `8891` and the order date |

Expected numbers: the lookup shrinks from 1,341 to 157 characters, 1 − 157 / 1,341 = 88.3% smaller. So every later prompt that carries it is 1,341 − 157 = 1,184 characters shorter: 3 × 1,184 = 3,552 over turns 2–4.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C2 | A fixed set of transactional field types: monetary amounts, dates, order/reference numbers, status values and customer identifiers. They are the data types summarisation destroys, and the fields a support agent needs to process a refund (**New**) | `FACT_FIELDS` (code above) maps each of the 5 types to the fields that carry it in Lumen Home's tool results. The extractor reads only these named fields and never pattern-matches values out of text, so a date inside a note can't become a fact. Fields of the same kinds that a refund doesn't need, such as `tax_amount`, `delivered_date`, `tracking_number`, `payment_status` and `invoice_number`, stay out on purpose, so the block stays small | Self-check: `FACT_FIELDS` has exactly 5 types and 9 fields. `ORDER_8891` holds 5 of those fields and `REFUND` holds 5 (`order_id` is in both) |
| C1 | A case facts extractor: a function that takes raw tool output and returns a structured object holding only the transactional facts (customer ID, order numbers, amounts, dates, statuses), with non-transactional narrative content excluded (**New**) | `extract_case_facts(result)` takes a parsed tool result (a dict) and returns `{field: result[field]}` for every `FACT_FIELDS` field present in it, in `FACT_FIELDS` order. Values are copied unchanged: no rounding, reformatting or rewording | Self-check: `extract_case_facts(ORDER_8891) == {"customer_id": "CUST-1042", "order_id": "ORD-8891", "total_amount": 247.83, "order_date": "2026-03-03", "order_status": "delivered"}`. On the record that a direct `process_refund` handler call returns in a new `CaseState`, it gives `{"order_id": "ORD-8891", "refund_id": "RF-0001", "refund_amount": 247.83, "refund_date": "2026-03-20", "refund_status": "processed"}`. No value from `customer_note`, `internal_note`, `delivery_instructions` or `message` appears, including the date `2026-03-05` inside `internal_note` |
| C7 | A tool result trimmer that filters an order lookup from 40+ fields to the 5 fields a return needs (`order_id`, `order_date`, `total_amount`, `return_eligible`, `item_description`); the task context defines which fields are relevant (**New**) | `trim_result(result, task="refund")` returns `{field: result[field] for field in TASK_FIELDS[task]}`. `TASK_FIELDS` (code above) holds the refund task's 5 fields and, to show that the task decides, a `delivery` task's 5 | Self-check: `json.dumps(trim_result(ORDER_8891))` is exactly `{"order_id": "ORD-8891", "order_date": "2026-03-03", "total_amount": 247.83, "return_eligible": true, "item_description": "Aurora floor lamp, brushed brass"}`. `trim_result(ORDER_8891, "delivery")` keeps `carrier`, `tracking_number`, `shipped_date` and `delivered_date` instead of the date, total, eligibility and item |
| C10 | The trimmed result is 80–90% smaller than the original (**New**) | The hook appends `(tool, raw_chars, sent_chars)` to `state.sizes` for every result it sees: the length of the result text it received and of the text it passes on. The self-check prints both lengths for `ORDER_8891` and the reduction, `1 - sent_chars / raw_chars` | Self-check: 42 fields, 1,341 → 157 characters: 1 − 157 / 1,341 = 88.3% smaller. Live, turn 1: `state.sizes` holds `("mcp__lumen__lookup_order", 1341, 157)` |
| C9 | Trimming before results enter the context is essential, not optional: do it in a `PostToolUse` hook or inside the tool implementation, before the result enters the conversation history (**Builds on** `05-revised-Agent-SDK-Hooks.md` C4, C6) | `build_case_hooks(state)` returns `{"PostToolUse": [HookMatcher(matcher="mcp__lumen__lookup_order\|mcp__lumen__process_refund", hooks=[case_hook])]}`, a list of exact names (05 E2). `case_hook` parses `response_text(input_data["tool_response"])` as JSON (a result that doesn't parse is left alone: `{}`). Then, in this order: 1) `state.case_facts.update(extract_case_facts(result))`, on the **raw** result; 2) for `lookup_order` only, it returns `{"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": same_shape(input_data["tool_response"], json.dumps(trim_result(result)))}}`. Any other result passes unchanged (`{}`). The order matters: `customer_id` and `order_status` are facts but not refund fields, so extracting after the trim would lose them. New compared with 05 C4 and C6: the hook removes fields to save context instead of rewriting formats. The handler returns all 42 fields on purpose, as an order API you can't change would; when you own the tool, its handler can trim the result and record the facts itself | Self-check: calling `case_hook` directly with `ORDER_8891` as a list of text blocks returns a list whose text parses to the 5 refund fields, and fills `state.case_facts`. Live, turn 1: the `lookup_order` `ToolResultBlock` Claude received parses to exactly the 5 refund fields, while `state.case_facts` holds `customer_id` `CUST-1042` and `order_status` `delivered`, which that block doesn't contain: the facts came from the raw result |
| C8 | Untrimmed tool results consume the context budget without anyone noticing: a 40+ field lookup costs tokens again in every later turn, as the history grows (**Builds on** `05-revised-Built-in-Tools.md` C8) | `run_turn()` stores each prompt's `prompt_chars` and `lookups`. After the run, print one row per turn and arm with `prompt_chars` and `untrimmed = prompt_chars + lookups × (raw_chars − sent_chars)`, using the lookup's entry in `state.sizes`, then the total extra characters. New compared with 05's C8: there the waste was reading files the task didn't need. Here it is the unneeded fields of a result the task did need, and every later prompt pays for them again, because each prompt resends the history | Typically `lookups` is 1 in turns 2–4 and 0 in turns 5–6. So the trim saves 1,184 characters in each of turns 2–4, 3 × 1,184 = 3,552 in all, and from turn 5 on the summary has removed the result. Without summarisation, one untrimmed lookup would add 1,184 characters to every later prompt |
| C6 | The block is structured data (JSON or a clear key-value list), prepended to the system prompt or to the first user message of every API call (**New**) | The block is `FACTS_HEADER`, a newline, then `json.dumps(case_facts, indent=2)`. `build_prompt()` puts it first in the prompt string, which becomes the first user message of that turn's session. So every API call the SDK makes during the turn, before and after a tool call, starts with it. A per-turn `system_prompt=AGENT_PROMPT + block` would also work, because each turn is a new session (E1) | In every with-facts prompt, the JSON under `FACTS_HEADER` parses back with `json.loads` to the `state.case_facts` of that moment. From turn 3 on, it typically holds 9 keys in 261 characters of JSON |
| C5 | A prompt construction function: the case facts block at the top of every message, then any summarised history, then the current turn. A section header clearly delimits the block, so the model treats it differently from the history (**New**) | `build_prompt(case_facts, summary, recent, message)` joins up to four sections with blank lines, each starting with its header: `FACTS_HEADER = "=== CASE FACTS (exact values from tool results; never summarised) ==="` (left out when `case_facts` is `None`); `SUMMARY_HEADER = "=== CONVERSATION SUMMARY (turns 1-4) ==="` (only once a summary exists); `RECENT_HEADER = "=== RECENT TURNS ==="` (only when there are recent turns); and `MESSAGE_HEADER = "=== CUSTOMER MESSAGE ==="`. `render_history(turns)` writes each turn as `Turn <n>`, `Customer: …`, one `Tool <short name>: <text Claude received>` line per tool result, and `Agent: …`. `AGENT_PROMPT` names each section and says how far to trust it | Self-check: in a prompt with all four sections, the header offsets increase in the order facts, summary, recent, message. The script prints the with-facts turn-6 prompt in full |
| C4 | The block is prepended to every prompt, outside the summarised history. It persists across every turn whatever happens to the history, so amounts, dates and order numbers survive when earlier turns are compressed (**New**) | `run_turn()` rebuilds the block from `state.case_facts` on every with-facts turn. The history never holds it: a turn record keeps only the customer message, the tool results and the reply | All 6 with-facts prompts start with `FACTS_HEADER`: typically `{}` in turn 1, 5 facts in turn 2 and 9 from turn 3 on. No turn record contains `FACTS_HEADER` |
| E1 | Python owns the history: each turn is a fresh `query()` | Each turn is one `run_agent()` call, with no `resume`, no `continue_conversation` and no `ClaudeSDKClient`. A `query()` call "starts fresh with no memory of previous interactions", so the only history Claude sees is the one `build_prompt()` wrote, and `summarise()` can replace it. In a continued session, the SDK keeps the history itself and compacts it with a summary it writes ("keeping your most recent exchanges and key decisions intact"). Whether a value survived would then be up to the model, and the A/B couldn't show the loss on purpose. This builds on `01-revised-Agentic-Loops.md` C11 (the API is stateless): here Python, not the SDK, resends the history | Code review: no `resume`, `continue_conversation` or `ClaudeSDKClient` anywhere, and 8 `run_agent()` calls in all |
| C11 | A 6–8 turn conversation in which summarisation occurs after turn 4, simulated by replacing turns 1–4 with a compressed summary (**New**) | `TURNS` (table above) and `SUMMARISE_AFTER = 4`. After turn 4, set `summary = summarise(recent)` and `recent = []`. `summarise(turns)` takes only the turn records and returns `LOSSY_SUMMARY`; in production, it would be a model call | 6 turns, with the summary after turn 4. The turn-5 prompts of both arms contain `SUMMARY_HEADER` and none of the customer messages of turns 1–4, and their `prompt_chars` is typically below turn 4's |
| E2 | The summary is fixed text, the same in both arms, with no digit in it | `LOSSY_SUMMARY = "The customer contacted us about a lamp from a recent order that arrived damaged. The agent looked the order up, confirmed it could be returned and refunded it in full to the customer's card. The customer then asked how long the refund takes and whether the lamp has to be sent back, and the agent explained the usual timing and the emailed return label."` It keeps the story in vague words ("a recent order", "in full", "the usual timing"), the way progressive summaries end up. A live summariser could keep the numbers in one arm and lose them in the other, or keep them in both, and the without-facts arm would then pass by luck | `re.search(r"\d", LOSSY_SUMMARY) is None`: no ID, amount or date survived into the summary |
| C3 | The persistent case facts block is the single most important pattern in context window management: facts kept in a structured block that is never summarised can't be destroyed by progressive summarisation (**New**) | `summarise()` never receives `state.case_facts`; it takes only the turn records. Copy `state.case_facts` before summarising, and assert afterwards that it is unchanged | The assert passes: all 9 facts survive summarisation unchanged, including `247.83`, `ORD-8891` and `2026-03-03`, while `LOSSY_SUMMARY` holds none of them (E2) |
| C12 | Two versions, one with the case facts block and one without; after summarisation, ask the agent to confirm the refund amount and order number (**New**) | After turn 4, run turns 5–6 twice: `with-facts` (`build_prompt(state.case_facts, …)`) and `without-facts` (`build_prompt(None, …)`). Each arm starts from the same summary and from its own `copy.deepcopy(state)`, with the same `AGENT_PROMPT`, tools and hook. Turn 5 asks for the refund reference and status; turn 6 asks for the refund amount, the order number and the order date. The tools stay available: the without-facts arm could look the order up again, but nothing in its prompt holds the order number | The two turn-5 prompts differ only by the block: `with_prompt == FACTS_HEADER + "\n" + json.dumps(facts, indent=2) + "\n\n" + without_prompt` |
| C13 | Expected: with the block, the agent still quotes the exact refund amount ($247.83), order number (#8891) and date (March 3rd); without it, those values are lost to summarisation (**New**) | `quoted(text)` reports, for 4 probe values, whether each appears in a reply: `RF-0001` (turn 5), and `247.83`, `8891` and the order date as `2026-03-03`, `March 3` or `3 March` (turn 6). Print one row per arm, with ✅/❌ per value | `with-facts`: typically 4 of 4, read from the block with no tool call. `without-facts`: typically 0 of 4. Its replies say the details aren't available or ask the customer for them, while the story ("refunded in full") may survive. If a without-facts reply quotes a value, check where it came from: a new tool call, or an invention |
| C14 | The exam tests that progressive summarisation destroys specific amounts and dates and that the case facts block is the fix; verifying it empirically validates the pattern (**New**) | Under the table, print each arm's count and the line `Same summary, model, tools and hook: only the CASE FACTS block differed` | The line is printed once. The counts are typically 4/4 against 0/4: the summary kept the story and lost the numbers, and only the block, outside the summary, kept them |

### POC 2: Key findings first

**Build:** `poc2_key_findings.py`, which imports `MODEL` from `context_setup.py`. Everything is offline except 2 `query()` calls. It defines:
- `SOURCES`: 9 dicts `{"name", "key_finding", "details"}` (table below), in this order;
- `figures(text)`: the whitespace-separated tokens of `text` that contain a digit, with `$`, `.`, `,`, `;`, `:`, `(` and `)` stripped from both ends;
- `aggregate(sources)` and `drawn_from(source)` (C16), `aggregate_plain(sources)` and `ATTENTION_NOTE` (C17), and `position(text, needle="CB-4471")`, which returns `text.index(needle) / len(text)`;
- `REVIEWER_PROMPT`, `DECISION_SCHEMA` and `build_review_options()` (code below);
- `async def review(text)`: one `query()` with the prompt `f"{text}\n\nQuestion: Should Lumen Home approve the $312.40 refund for order ORD-9024 now?"`, streamed inside `try/except` (a single-shot `query()` raises after yielding an error result). It returns `structured_output`, or `None`: the pattern of `extract()` in `04-revised-Validation-Retry-and-Feedback-Loops.md`.

The scenario: Dana Reyes asks for a refund of another order, `ORD-9024` ($312.40), and a reviewer gets the findings of 9 back-office checks. One finding blocks the refund: the card issuer has already opened chargeback `CB-4471` for the same $312.40, so a refund would pay her twice. It sits in the middle source, Payments (#5 of 9).

| # | `name` | `key_finding` |
|---|---|---|
| 1 | Order system | `ORD-9024, Nimbus portable speaker, $312.40, delivered 2026-04-06; returnable until 2026-05-06.` |
| 2 | Customer request | `CUST-1042 asked on 2026-04-25 for a full refund of $312.40: the speaker stopped charging.` |
| 3 | Carrier tracking | `Return parcel LR-7781 reached the returns desk on 2026-04-24.` |
| 4 | Returns inspection | `Speaker received complete; charging fault confirmed; not resellable.` |
| 5 | Payments | `Chargeback CB-4471 for $312.40 opened by the card issuer on 2026-04-21; still open.` |
| 6 | Fraud and risk | `Risk score 0.03 (low); no linked accounts, no recent address change.` |
| 7 | Product quality | `4 other charging-fault reports for batch B-2207 since 2026-04-01; supplier notified.` |
| 8 | Inventory | `12 units in stock; a replacement could ship on 2026-04-27.` |
| 9 | Customer history | `Gold tier since 2023; 1 earlier return, refunded; no earlier disputes.` |

Rules for `details`:
- 500–700 characters and 5–9 lines each: plausible logs or notes from that system;
- every token of `figures(key_finding)` appears in its own details;
- no other source mentions a chargeback, a dispute or `CB-4471`, and no line flags itself as important.

The Payments details are exactly these 7 lines (569 characters; `CB-4471` starts at character 256, 45% of the way in):

```text
2026-04-02 10:14 authorization AUTH-55102 approved: $312.40, Visa ending 4417, order ORD-9024
2026-04-02 10:15 capture CAP-55102 settled: $312.40
2026-04-03 02:00 settlement batch SB-0402 closed: 418 transactions, no exceptions
2026-04-21 16:37 chargeback CB-4471 opened by the card issuer: $312.40 on ORD-9024, reason 13.3 (not as described), status open
2026-04-22 02:00 settlement batch SB-0422 closed: 391 transactions, no exceptions
2026-04-23 09:12 issuer notice: merchant response due by 2026-05-05
2026-04-25 08:00 daily reconciliation completed: balances match
```

The reviewer, the same for both layouts:

```python
REVIEWER_PROMPT = ("You review refund requests for Lumen Home. Decide from the findings in the message whether to "
                   "approve the refund now or hold it. Hold it if any finding shows that the money is already coming "
                   "back to the customer another way, because a refund would then pay them twice; otherwise approve a "
                   "refund the findings support. In reason, name every finding that drives your decision.")
DECISION_SCHEMA = {"type": "object", "required": ["decision", "reason"],
                   "properties": {"decision": {"type": "string", "enum": ["approve", "hold"]},
                                  "reason": {"type": "string"}}}

def build_review_options():
    return ClaudeAgentOptions(
        model=MODEL,
        system_prompt=REVIEWER_PROMPT,                                     # the same reviewer for both layouts
        output_format={"type": "json_schema", "schema": DECISION_SCHEMA},  # the decision as validated JSON
        tools=[],                                                          # no tools: the findings are in the prompt
        setting_sources=[],                                                # ignore ~/.claude and project settings, CLAUDE.md and hooks
        env={"ENABLE_TOOL_SEARCH": "false"},                               # no ToolSearch calls
        max_turns=5,                                                       # safety cap (01 C16)
    )
```

Expected positions, computed from the rules above with the other 8 details anywhere from 500 to 700 characters: plain 0.42–0.57, with the note 0.43–0.58, and structured 0.061–0.078. In the structured text, `CB-4471` first appears at character 441 (in the Payments bullet), and the whole text is 5,671–7,271 characters long.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C16 | An aggregation function that puts a Key Findings Summary section at the top of the combined input, with one concise bullet per source drawn from the detailed content, followed by the detailed results under explicit section headers (**New**) | `aggregate(sources)` returns these lines joined with newlines: `## Key Findings Summary`; one `- <name>: <key_finding>` per source, in `SOURCES` order; a blank line and `## Detailed Results`; then, per source, a blank line, `### <n>. <name>` and its details. The one-line summaries are the sources' own `key_finding`s, so the aggregator only places text and never rewrites it. `drawn_from(source)` is True when every token of `figures(key_finding)` appears in that source's details | Offline: the text starts with `## Key Findings Summary`. It has 9 bullets, each one line of at most 120 characters (the longest is 110), and 9 `### ` headers from `### 1. Order system` to `### 9. Customer history`. `drawn_from()` is True for all 9 sources |
| C17 | The fix is structural, not prompt-based: don't tell the model to pay attention to everything; reorganise the input so critical information comes first (**Builds on** `06-revised-Task-Decomposition-Strategies.md` C7) | `aggregate_plain(sources)` joins the 9 details with blank lines, with no summary and no headers: a naive aggregation. The prompt-based "fix" is `ATTENTION_NOTE + "\n\n" + aggregate_plain(sources)`, with `ATTENTION_NOTE = "Read every finding carefully, including the ones in the middle, and don't miss anything."`. Print `position()` for the plain, note and structured texts, then the line `A prompt can't move a finding: only the layout can`. New compared with 06 C7: the structural fix reorders one input instead of splitting the work into passes | Plain: 0.42–0.57. With the note: 0.43–0.58, so the note moved nothing. Structured: `CB-4471` first appears at character 441, in the Payments bullet, at 0.061–0.078 of the text |
| C15 | The lost-in-the-middle effect: models process the beginning and end of long inputs reliably, but findings buried in the middle may be missed (**Builds on** `06-revised-Task-Decomposition-Strategies.md` C4) | Run `review()` twice, on `aggregate_plain(SOURCES)` and on `aggregate(SOURCES)`, with the same question at the end of both. Print each `decision`, its `reason`, and whether the reason mentions `CB-4471` or "chargeback". New compared with 06 C4: the risk is one finding in the middle of one input, not the later files of a long review | Structured: `hold`, with a reason that cites the chargeback. Plain: the input is only 4,585–6,185 characters, so a strong model typically reads all of it and holds too; if it approves, that is the lost-in-the-middle effect. Record either result: the lesson doesn't depend on catching a miss. Only the structured layout puts the finding in the first 8% of the input, the part models read reliably, at any input length |

### Terminal commands (for the later tutorial)

None: every concept in this topic is a programming concept.

### Already covered by earlier POCs

None: every concept in this topic is new or builds on an earlier POC (cited in its row).
