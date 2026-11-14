# Tool Interface Design: Revised POC Requirements (5 steps → 2 POCs, Claude Agent SDK)

> **Source:** `01-raw-Tool-Interface-Design.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Tool Design & MCP Integration → Tool Interface Design · **Build with:** Claude Agent SDK for Python (`claude_agent_sdk`)

---

## 1. Verdict: 2 POCs

The 5 raw steps are not 5 separate concepts. Steps 1–4 are **one before/after experiment**: step 1 builds the ambiguous tools, step 2 measures them, step 3 changes one thing (the description text), and step 4 measures again. Step 5 tests a **second routing signal**, the system prompt, which can undo the fix. What you need to learn splits into two mental models:

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: Descriptions drive tool selection** | **Measured, not assumed:** the same 10 queries run against two tools whose names, schema and handlers never change. Only the description text changes, from one vague sentence to five sentences with formats, examples, edge cases and boundaries, and selection accuracy rises from typically 6–8/10 to 9–10/10 | 1, 2, 3, 4 |
| **POC 2: System-prompt keyword conflicts** | **The other routing signal:** an offline audit lists the system-prompt sentences that tie a trigger word ("always", "first") to one tool's vocabulary. A live A/B shows such sentences pulling Claude to `get_customer` on order questions, despite the improved descriptions | 5 |

**What changes with the Agent SDK:** the SDK sends every tool's name, description and input schema to Claude with each request. Claude picks a tool, and the SDK runs its handler. Selection happens inside the model, so it can only be observed, not coded. The POCs read it from the `ToolUseBlock`s of Claude's first tool-calling response and score it against an expected tool. With `tools=[]` and tool search off, Claude has only two routing signals: the two descriptions and the system prompt. POC 1 varies the descriptions, and POC 2 varies the system prompt. Nothing else changes between runs, which is what lets a change in accuracy be pinned on the text.

- **Why not 1 POC:** POC 2 must run on descriptions already proven to route 9–10/10 correctly. Then a misroute in POC 2 can only come from the system prompt. In one POC, a misroute could come from either signal, and you couldn't tell which.
- **Why not 3 or more:** steps 2 and 4 are the same harness run on two description versions, step 3 changes two strings, and step 1's tools have no lesson without the measurement. Splitting them would rebuild the same server and runner.

**Applies to both POCs:** Python 3.10+, `pip install claude-agent-sdk` (a recent 0.2.x; it bundles the Claude Code binary), `ANTHROPIC_API_KEY` set in the environment (never hard-coded), mock data only, and beginner-friendly code (small, commented scripts). Every run goes through `run_agent()` from `01-revised-Agentic-Loops.md` (`poc2_agent_loop.py`), already extended in `05-revised-Agent-SDK-Hooks.md` (`options=`, `tool_results`) and extended again in POC 1's Build. The tools follow `tools.py` from `01-revised-Agentic-Loops.md` (C2–C3): `@tool` with a full JSON Schema dict, async handlers that return `{"content": [...]}`, `is_error` instead of raising, and `ToolAnnotations(readOnlyHint=True)`. They live in `routing_setup.py` and use the made-up store "Lumen Home" from `04-revised-Workflow-Enforcement-and-Handoff.md`, with fields added so that every query has an answer:

| Customer ID | Name | Email | Phone | Address on file | Tier | Account status | Orders |
|---|---|---|---|---|---|---|---|
| `CUST-1042` | Dana Reyes | `dana.reyes@example.com` | +1-503-555-0142 | 12 Alder St, Portland, OR 97205 | gold | active | `ORD-7731`, `ORD-7745` |
| `CUST-2077` | Sam Okafor | `sam.okafor@example.com` | +1-206-555-0177 | 9 Birch Ave, Seattle, WA 98101 | silver | identity check pending | `ORD-8810` |

| Order ID | Placed by | Item | Total | Status | Tracking | Shipped to | Paid with |
|---|---|---|---|---|---|---|---|
| `ORD-7731` | `CUST-1042` Dana Reyes | Aurora desk lamp | $49.99 | delivered on 2026-10-03 | `LH-55120931` | 12 Alder St, Portland, OR 97205 | Visa ending 4417 |
| `ORD-7745` | `CUST-1042` Dana Reyes | Nimbus wireless headphones | $129.00 | shipped, in transit | `LH-55120988` | 410 Market St, Suite 200, Portland, OR 97204 | Visa ending 4417 |
| `ORD-8810` | `CUST-2077` Sam Okafor | Kestrel water bottle | $24.50 | processing | none yet | 9 Birch Ave, Seattle, WA 98101 | Mastercard ending 0921 |

`ORD-7745` shipped to Dana's office, not to her address on file. So "address on file" (an account field) and "shipped to" (an order field) have different answers, which is why the store needs two tools.

In every version, both tools take one argument with one schema, `IDENTIFIER_SCHEMA = {"type": "object", "properties": {"identifier": {"type": "string"}}, "required": ["identifier"]}`. It has no field description and no pattern, so formats can reach Claude only through the tool description. The handlers are two module-level async functions that never change:
- **`get_customer_handler(args)`** matches a customer ID (case-insensitive), an email (case-insensitive) or a full name (case-insensitive, exact). It returns JSON `{"customer_id", "name", "email", "phone", "address_on_file", "tier", "account_status", "order_ids"}`. Anything else returns `is_error: True` with `No customer matches '<identifier>'.`
- **`lookup_order_handler(args)`** trims and upper-cases its input and adds `ORD-` to a bare 4-digit number. It returns JSON `{"order_id", "customer_id", "customer_name", "item", "total", "status", "tracking", "shipped_to", "paid_with"}`. Anything else returns `is_error: True` with `No order matches '<identifier>'.`

Neither error text says which tool to use instead, so the descriptions stay the only routing signal. `build_tools(version)` wraps the same two handlers as `tool("get_customer", DESCRIPTIONS[version]["get_customer"], IDENTIFIER_SCHEMA, annotations=ToolAnnotations(readOnlyHint=True))(get_customer_handler)`, and does the same for `lookup_order`. `build_routing_server(version)` bundles them with `create_sdk_mcp_server(name="lumen", version="1.0.0", tools=build_tools(version))`, so their full names are `mcp__lumen__get_customer` and `mcp__lumen__lookup_order`. Every run gets its options from `routing_setup.py`:

```python
BASE_PROMPT = ("You are a support assistant for Lumen Home, an online store. Answer each question with the tools, "
               "and never guess an ID, a date or an amount.")

DESCRIPTIONS = {
    "minimal": {   # step 1: one vague sentence each (C1)
        "get_customer": "Retrieves customer information.",
        "lookup_order": "Retrieves order details.",
    },
    "improved": {  # step 3: five sentences each, with all five elements (C7, C9)
        "get_customer": (
            "Looks up one Lumen Home customer account and returns its customer ID, name, email, phone, address on "
            "file, loyalty tier, account status and order IDs. "
            "Pass identifier as a customer ID (CUST- plus 4 digits, such as CUST-1042), an email address or a full "
            "name; a bare number is never a customer ID. "
            "Use it for questions about a customer or their account, such as \"Look up CUST-1042\", \"What's Dana "
            "Reyes' address on file?\" or \"Is sam.okafor@example.com a gold member?\", and call it first when the "
            "user names a customer but gives no order ID, because it returns the order IDs that lookup_order needs. "
            "If a name matches no customer exactly, it returns an error, so ask for the email or customer ID instead "
            "of guessing. "
            "Do NOT use it for order-specific details (items, order status, tracking, where an order shipped, how it "
            "was paid): use lookup_order for those."
        ),
        "lookup_order": (
            "Looks up one Lumen Home order and returns its item, total, order status, tracking number, shipping "
            "address, payment card and the customer who placed it (ID and name). "
            "Pass identifier as an order ID, ORD- plus 4 digits such as ORD-7745; a bare 4-digit number such as "
            "7745 is an order number, so pass it with the ORD- prefix. "
            "Use it for questions about one specific order, such as \"Has ORD-7745 shipped?\", \"Which card paid "
            "for ORD-7731?\" or \"Who placed order ORD-8810?\". "
            "If the user gives only a name, an email or a customer ID, call get_customer first to get their order IDs. "
            "Do NOT use it for account questions (contact details, address on file, loyalty tier, account status): "
            "use get_customer for those."
        ),
    },
}

def build_routing_options(version, system_prompt=BASE_PROMPT):
    return ClaudeAgentOptions(
        model="claude-opus-5-5",
        system_prompt=system_prompt,                          # POC 2 passes CONFLICT_PROMPT or FIXED_PROMPT
        mcp_servers={"lumen": build_routing_server(version)}, # same names, schema and handlers; only the descriptions differ (C11)
        tools=[],                                             # no built-in tools: the two lumen tools are the only choice
        allowed_tools=["mcp__lumen__get_customer", "mcp__lumen__lookup_order"],  # no permission prompts
        setting_sources=[],                                   # ignore ~/.claude and project settings, CLAUDE.md and hooks
        env={"ENABLE_TOOL_SEARCH": "false"},                  # full definitions upfront, so the first tool call is a routing choice (E2)
        max_turns=6,                                          # safety cap (01 C16); a misroute costs a turn or two
    )
```

The 10 test queries, `QUERIES`, in this order. Four are controls that name their entity plainly, and six sit where the two minimal descriptions overlap:

| # | Query | Expected first tool | Why the minimal descriptions can misroute it |
|---|---|---|---|
| 1 | `Look up customer CUST-1042.` | `get_customer` | control |
| 2 | `Has order ORD-7745 shipped yet?` | `lookup_order` | control |
| 3 | `What's the shipping address on file for Dana Reyes?` | `get_customer` | "shipping" sounds like an order detail |
| 4 | `Pull up 7745.` | `lookup_order` | a bare number could be either |
| 5 | `Who placed order ORD-8810?` | `lookup_order` | "who" sounds like customer information |
| 6 | `Which card was used to pay for ORD-7731?` | `lookup_order` | a payment card sounds like account information |
| 7 | `Is Sam Okafor a gold-tier member?` | `get_customer` | control |
| 8 | `What did sam.okafor@example.com buy recently?` | `get_customer` | "buy" sounds like an order, but there is no order ID |
| 9 | `Can you check the status for dana.reyes@example.com?` | `get_customer` | "status" could mean an order's status |
| 10 | `What's the phone number on CUST-2077's account?` | `get_customer` | control |

Expected totals: 6 `get_customer` (1, 3, 7, 8, 9, 10) and 4 `lookup_order` (2, 4, 5, 6). If all 4 controls are right and 2–4 of the 6 overlap queries misroute, accuracy is 6/10–8/10.

---

## 2. Concepts and POC requirements

All 14 concepts in the raw file (C1–C14) are covered: all 14 are new or build on earlier POCs and are taught below, none is a terminal command, and none was already covered by an earlier revised file (see the end of this section).
Previous revised files checked: `01-revised-Agentic-Loops.md`, `02-revised-Multi-Agent-Orchestration.md`, `03-revised-Subagent-Invocation-and-Context-Passing.md`, `04-revised-Workflow-Enforcement-and-Handoff.md`, `05-revised-Agent-SDK-Hooks.md`, `06-revised-Task-Decomposition-Strategies.md` (the other domain-02 revised files are still empty).
Raw step → concepts: **1** → C1–C3 · **2** → C4–C6 · **3** → C7–C9 · **4** → C10–C11 · **5** → C12–C14.
Rows marked **E** are extras that are not in the raw file. Without them, the POC breaks or gives misleading results.

### POC 1: Descriptions drive tool selection

**Build:** three pieces of code.

**`routing_setup.py`:** the mock data, `BASE_PROMPT`, `IDENTIFIER_SCHEMA`, `DESCRIPTIONS`, the two handlers, `build_tools()`, `build_routing_server()` and `build_routing_options()` (code above), `QUERIES` (10 `(query, expected)` pairs, with `expected` a short tool name), and three offline helpers:
- `sentence_count(text)`: `len(re.split(r"(?<=[.!?])\s+", text.strip()))`, so a `?` inside a quoted example doesn't end a sentence;
- `check_description(name, text)`: returns a dict of the five elements, each True or False:
  - `purpose`: the first sentence says what the tool `returns`;
  - `formats`: a `CUST-` or `ORD-` format;
  - `examples`: at least one quoted query;
  - `edge_cases`: a sentence that starts with `If `;
  - `boundary`: `Do NOT use` plus the other tool's name;
- `compare_versions()`: compares `name`, `description`, `input_schema`, `annotations` and `handler` of each tool between `build_tools("minimal")` and `build_tools("improved")`, and returns the fields that differ.

POC 2 reuses it. `python routing_setup.py` runs an offline self-check that makes no API calls.

**An extension to `run_agent()`** (in `poc2_agent_loop.py`, from `01-revised-Agentic-Loops.md`, already extended in `05-revised-Agent-SDK-Hooks.md`): add a new key, `first_response_tools`. It holds the full names of the `ToolUseBlock`s in Claude's first tool-calling response, meaning the `AssistantMessage`s that share the first `ToolUseBlock`'s `message_id`. It is `[]` when Claude calls no tool. 01's and 05's scripts must still run unchanged.

**`poc1_selection_test.py`:**
- `async def evaluate(version)` runs the 10 `QUERIES` in order, each with `run_agent(query, options=build_routing_options(version))`. It returns one row per query: `{"n", "query", "expected", "first_tools", "correct", "tool_calls", "answer"}`.
- `accuracy(rows)` returns the number of correct rows.
- `main()` runs `evaluate("minimal")` and then `evaluate("improved")`, and prints the comparison.

No system-prompt changes here: every run uses `BASE_PROMPT`. Prompt conflicts are POC 2.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C1 | Two MCP tools with intentionally ambiguous one-sentence descriptions (`get_customer`: "Retrieves customer information", `lookup_order`: "Retrieves order details"), registered with an MCP server, with no input formats, example queries or boundaries (**Builds on** `01-revised-Agentic-Loops.md` C2) | `DESCRIPTIONS["minimal"]` holds the raw file's two sentences (code above). `build_routing_server("minimal")` registers them under the server key `"lumen"`. New compared with 01 C2: the description is deliberately vague, and both tools share one bare `identifier` schema. Nothing but the description tells them apart | The self-check prints both full tool names and their descriptions. `sentence_count()` gives 1 for each minimal description, and `check_description()` gives False for all five elements |
| C7 | Rewrite both descriptions with five elements: purpose, expected inputs with formats, example queries, edge cases, and explicit boundaries against the other tool (**Builds on** `01-revised-Agentic-Loops.md` C2 and `04-revised-Workflow-Enforcement-and-Handoff.md` C2) | `DESCRIPTIONS["improved"]` (code above): sentence 1 is the purpose and what the tool returns, sentence 2 the input formats, sentence 3 example queries and when to call it first, sentence 4 an edge case, and sentence 5 the boundary. New compared with 01 C2 and 04 C2: the formats are stated in the description, not in a schema `pattern`, and each tool names the other one as the right choice outside its scope | `check_description()` gives True for all five elements of both improved descriptions |
| C9 | The production-grade shape: 3–5 sentences, the accepted identifier formats, example queries, and a boundary such as "Do NOT use for order-specific queries — use lookup_order for those" (**New**) | Print each improved description with its `sentence_count()`, its formats, its quoted examples and its last sentence | `sentence_count()` gives 5 for both. Formats: `get_customer` gives `CUST-` plus 4 digits, an email or a full name; `lookup_order` gives `ORD-` plus 4 digits, or a bare 4-digit number. Each quotes 3 example queries. The last sentences are `Do NOT use it for order-specific details … use lookup_order for those.` and `Do NOT use it for account questions … use get_customer for those.` |
| C11 | Measured improvement with no architectural change (same names, schema, handlers, system prompt, model and options) validates description quality as the root cause (**New**) | Offline: `compare_versions()`. Live: both passes use `BASE_PROMPT` and `build_routing_options()`, which differ only in `version`. After both passes, list the queries that were wrong with `minimal` and right with `improved` as `fixed`, and print `Only the descriptions changed, so they were the root cause` | `compare_versions()` returns exactly `["get_customer.description", "lookup_order.description"]`. The `fixed` list typically holds every query that `minimal` misrouted, and the 4 controls stay correct |
| E2 | Tool search off, so the first tool call is a routing choice | `env={"ENABLE_TOOL_SEARCH": "false"}` (code above). With tool search on (the default), Claude Code defers MCP tools: Claude first sees only their names and may call `ToolSearch` before choosing. Then the first `ToolUseBlock` would be `ToolSearch`, not a routing decision, and the descriptions would arrive later | No run's `tool_calls` contains `ToolSearch` |
| C4 | Test with 10 queries covering different user intents, and log which tool the model selects for each (**Builds on** `01-revised-Agentic-Loops.md` C4) | `evaluate()` runs `QUERIES` (table above). For each query, print one line: the number, the query, the expected tool, `first_response_tools` (short names) and ✅/❌. New compared with 01 C4: 10 queries chosen to probe the overlap between two similar tools, each scored against an expected tool, instead of 3 queries with obvious choices | 10 lines per pass, in `QUERIES` order |
| E1 | Score the first tool choice, not the final answer | `correct` is `first_response_tools == [f"mcp__lumen__{expected}"]`. A first response that calls both tools counts as wrong (Claude hedged), and so does one that calls no tool. Never score the answer text: after a misroute, the handler's `No … matches` error usually sends Claude to the other tool, and the final answer can be right even though the selection was wrong | Code review: `correct` reads only `first_response_tools` |
| C5 | Quantified selection accuracy before and after a description change is the concrete evidence: description quality directly affects selection reliability (**New**) | After each pass, print `selection accuracy (<version>): <k>/10` from `accuracy()`. At the end, print both numbers on one line, such as `7/10 -> 10/10` | Typically `minimal` 6–8/10 and `improved` 9–10/10 |
| C6 | The baseline log shows at least 2–3 misrouted queries, in either direction: `get_customer` for order queries, or `lookup_order` for customer queries (**New**) | After the `minimal` pass, print the misrouted queries in two groups: order queries sent to `get_customer`, and customer queries sent to `lookup_order` | Typically 2–4 misrouted, typically with at least one in each group, such as 5 or 6 sent to `get_customer` and 3, 8 or 9 sent to `lookup_order`. Results vary between runs. If fewer than 2 misroute, rerun the `minimal` pass once |
| C2 | Reproducing a misrouting scenario first-hand shows why minimal descriptions fail (**New**) | For each misrouted query of the `minimal` pass, print its `tool_calls` and the `is_error` results from `tool_results`, so the cost of the wrong first choice is visible | Each misrouted query's `tool_calls` typically starts with the wrong tool, followed by a `No customer matches …` or `No order matches …` error and then the right tool: one wasted round trip per misroute |
| C3 | Ambiguous descriptions are the root cause of tool selection errors, which the exam asks you to identify (**New**) | Mark each `minimal` misroute as a control or an overlap query (numbers 3, 4, 5, 6, 8 and 9 are the overlap). Print the two minimal descriptions next to the misroutes | Typically every misroute is an overlap query, and the 4 controls are correct. The vague sentences fail exactly where both fit the question: "Retrieves customer information" and "Retrieves order details" both seem to answer "Who placed order ORD-8810?" |
| C10 | Re-run the same 10 queries and compare accuracy before and after: 9/10 or 10/10, with the previously misrouted queries now correct (**New**) | `evaluate("improved")` runs the same `QUERIES`, in the same order and with the same options. Print one comparison table: the query number, the first tools with `minimal`, the first tools with `improved`, and whether it is `fixed`, `still wrong` or `unchanged` | `improved` gives 9/10 or 10/10. Every query that `minimal` misrouted is typically `fixed` |
| C8 | Rewriting the descriptions is the lowest-effort, highest-leverage fix for misrouting: the core exam skill (**New**) | Print `Fix: 2 description strings changed; no code, schema, handler, prompt or model change`, using `len(compare_versions())` for the 2, next to the accuracy gain from C5 | `2 description strings changed`, and a gain of typically 2–4 queries out of 10, for a text edit only |

### POC 2: System-prompt keyword conflicts

**Build:** two scripts, reusing `routing_setup.py` and the extended `run_agent()`.

**`prompt_audit.py`** (offline, no API calls) defines:
- `TRIGGERS = r"\b(always|first|every|before|whenever|must)\b"`;
- `TOOL_KEYWORDS = {"get_customer": r"\bcustomer (details|information|info|data|record|profile)\b", "lookup_order": r"\border (details|information|info|data|record)\b"}`: the vocabulary of each tool's minimal description;
- `audit_prompt(prompt)`: splits the prompt into sentences with the same rule as `sentence_count()`. It returns one finding `{"sentence", "trigger", "phrase", "tool"}` for each sentence that matches both a trigger (case-insensitive; the first match is reported) and a tool keyword;
- `CONFLICT_PROMPT`, `REWRITES` and `FIXED_PROMPT`:

```python
CONFLICT_PROMPT = BASE_PROMPT + (" Always check customer details before you answer any question."
                                 " For anything about a purchase, retrieve the customer information first.")

REWRITES = {  # each keyword-sensitive sentence -> a rewrite that keeps its intent and names a precise condition
    "Always check customer details before you answer any question.":
        "Before you change anything on an account, confirm who the customer is with get_customer; "
        "for questions about an order, lookup_order is enough.",
    "For anything about a purchase, retrieve the customer information first.":
        "For a question about one purchase, start with lookup_order and its order ID.",
}

FIXED_PROMPT = BASE_PROMPT + " " + " ".join(REWRITES.values())
```

`python prompt_audit.py` prints the audit of `BASE_PROMPT`, `CONFLICT_PROMPT` and `FIXED_PROMPT`. For each finding, it prints the phrase, the tool it pulls toward and its rewrite.

**`poc2_prompt_conflict.py`:** `ORDER_QUERIES` are the 4 `QUERIES` whose expected tool is `lookup_order` (2, 4, 5 and 6). The order rows say who placed the order, so none of them needs `get_customer`. `async def compare_prompts()` runs every order query with `build_routing_options("improved", CONFLICT_PROMPT)` and then with `build_routing_options("improved", FIXED_PROMPT)`. For each prompt, it prints, per query, `first_response_tools` and whether `mcp__lumen__get_customer` appears anywhere in `tool_calls`. Then it prints the two counts: queries with a `get_customer` call, and first-tool misroutes.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C12 | Review the system prompt for keyword-sensitive instructions that could override the improved descriptions (**New**) | Run `audit_prompt()` on `BASE_PROMPT`, `CONFLICT_PROMPT` and `FIXED_PROMPT`, and print every finding with its trigger, its phrase and its tool | `BASE_PROMPT`: 0 findings, so POC 1's results came from the descriptions alone. `CONFLICT_PROMPT`: exactly 2 findings, `Always` + `customer details` and `first` + `customer information`, both pulling toward `get_customer`. `FIXED_PROMPT`: 0 findings |
| C14 | The review's output: each keyword-sensitive phrase, the tool it pulls toward, and a rewrite that avoids the conflict (**New**) | For each `CONFLICT_PROMPT` finding, print `<phrase> -> <tool>` and its rewrite from `REWRITES`. Each rewrite keeps the original intent but replaces the blanket trigger with a precise condition: verify identity only before an account change, and start an order question from its order ID | 2 lines, each pairing a flagged sentence with its rewrite. Running `audit_prompt()` on the 2 rewrites gives 0 findings |
| C13 | System-prompt conflicts are a subtle failure mode: keywords such as "always check customer details" create unintended tool associations that override even well-written descriptions (**New**) | Run `compare_prompts()`. Both arms use the `improved` descriptions, the same ones that scored 9–10/10 in POC 1, so the system prompt is the only difference. Print `Same descriptions in both arms: the prompt caused the extra get_customer calls` when the conflict arm has more of them | Conflict arm: typically at least 2 of the 4 order queries call `get_customer`, either first (a misroute) or after `lookup_order` (an extra round trip that the question never needed). Fixed arm: typically 0 of 4 call `get_customer`, and all 4 first choices are `lookup_order`, as in POC 1 |

### Terminal commands (for the later tutorial)

None: every concept in this topic is a programming concept.

### Already covered by earlier POCs

None: every concept in this topic is new or builds on an earlier POC (cited in its row).
