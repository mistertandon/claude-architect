# Structured Error Responses: Revised POC Requirements (5 steps → 2 POCs, Claude Agent SDK)

> **Source:** `02-raw-Structured-Error-Responses.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Tool Design & MCP Integration → Structured Error Responses · **Build with:** Claude Agent SDK for Python (`claude_agent_sdk`)

---

## 1. Verdict: 2 POCs

The 5 raw steps are not 5 separate concepts. Steps 1–4 define **one response contract**: step 1 builds the tool, step 2 lists the four error types, step 3 fixes their three-field shape, and step 4 adds the one success case that must never look like an error. Step 5 is **one recovery loop** that reads that contract. What you need to learn splits into what the tool says and what the agent does with it:

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: The error contract** | **What a tool must say when it fails:** `is_error` plus a JSON body with exactly `errorCategory`, `isRetryable` and `description`, for four categories, and a valid empty result (`resultCount: 0`, no error) that is structurally different from an access failure on the same ID | 1, 2, 3, 4 |
| **POC 2: Recovery branches in the agent loop** | **What the agent does with it:** retry a transient error up to 3 times with backoff, fix the input after a validation error, escalate a business error, request credentials after a permission error, and never retry an empty result. The same failures with an unstructured `Operation failed.` show the wasted retries and wrong escalations | 5 (and the anti-patterns in the "Why" of 1, 3 and 4) |

**What changes with the Agent SDK:** the SDK runs the loop. It calls your handler when Claude asks for a tool and sends the handler's return value to Claude as a `ToolResultBlock`. The handler's `is_error` becomes that block's `is_error`, the Python spelling of MCP's `isError` flag. So the raw file's "agent loop that branches on `errorCategory`" splits in two:
- **Claude** reads the JSON body and picks the recovery: retry, fix the input, escalate or request credentials. It follows a recovery policy in the system prompt, and the structured metadata is what makes that choice possible.
- **A `PreToolUse` hook** (the pattern of `05-revised-Agent-SDK-Hooks.md`) enforces the rules a model can't keep by itself. It waits 1, 2 and 4 seconds before each retry of a transient failure, allows at most 3 retries, and denies any repeat of a call whose error said `isRetryable: false`.

Python then checks which branch Claude took, from the stream and from counters the handlers keep. One thing can only be observed, not coded: how Claude reacts when an error has no structure. POC 2 measures that against a structured twin of each run.

- **Why not 1 POC:** POC 2's comparisons only mean something once every response is proven to follow the contract. Then a bad recovery can only come from the agent's branching, not from a malformed error body. POC 1 checks every response offline and shows that Claude receives them intact.
- **Why not 3 or more:** steps 2–4 define one contract (the types, their fields, and empty versus failure) that can't be tested piece by piece. Step 1's tool has no lesson without the contract, and step 5's four branches are one loop over the same tool.

**Applies to both POCs:** Python 3.10+, `pip install claude-agent-sdk` (a recent 0.2.x; it bundles the Claude Code binary), `ANTHROPIC_API_KEY` set in the environment (never hard-coded), mock data only, and beginner-friendly code (small, commented scripts). Every run goes through `run_agent()` from `01-revised-Agentic-Loops.md` (`poc2_agent_loop.py`), as extended in `05-revised-Agent-SDK-Hooks.md` (`options=`, `tool_results`). The tools follow `tools.py` from the same file (C2–C3): `@tool` with a full JSON Schema dict, async handlers that return `{"content": [...]}`, and `is_error` instead of raising. They live in `errors_setup.py`, in one MCP server built for every run, so that all handlers and hooks share one `ErrorState` (the pattern of `build_support_server()` in `04-revised-Workflow-Enforcement-and-Handoff.md`). The customers are Lumen Home's from `01-revised-Tool-Interface-Design.md`: `CUST-1042` Dana Reyes (gold tier, `dana.reyes@example.com`) and `CUST-2077` Sam Okafor (silver tier, `sam.okafor@example.com`, +1-206-555-0177). No customer has the ID `CUST-9999`.

**The server `crm`**, created by `build_crm_server(state, failure_mode="none", structured=True)`:

| Tool | Description (what Claude reads) | Input | Behavior |
|---|---|---|---|
| `mcp__crm__customer_lookup` (`readOnlyHint=True`) | `"Looks up one Lumen Home customer by customer ID. Success returns JSON {\"resultCount\", \"customers\"}; resultCount 0 means the lookup ran and no customer has that ID. A failure returns JSON {\"errorCategory\", \"isRetryable\", \"description\"}."` | `customer_id` (string, `"description": "The customer's ID"`) | Calls `mock_db_lookup(customer_id, failure_mode, attempt)`, where `attempt` is this run's count of `customer_lookup` calls |
| `mcp__crm__process_refund` | `"Issues a refund to a Lumen Home customer. Returns the refund ID, or a JSON error {\"errorCategory\", \"isRetryable\", \"description\"}."` | `customer_id` (string), `amount` (number, `"exclusiveMinimum": 0`) | A bad ID gives a validation error, and an amount over `REFUND_LIMIT = 500` a business error. Otherwise it appends to `state.refunds` and returns `Refund RF-0001 of $<amount> issued to <id>.` |
| `mcp__crm__escalate_to_human` | `"Opens a case for a human agent when a request needs a decision you can't make. Pass the error category and a short summary."` | `category` (enum of the four categories), `summary` (string) | Appends to `state.escalations` and returns `Escalation ESC-0001 opened for a human agent.` |
| `mcp__crm__request_credentials` | `"Asks a supervisor for elevated access after a permission error. Pass the scope named in the error and the reason."` | `scope` (string), `reason` (string) | Appends to `state.credential_requests` and returns `Credential request CR-0001 sent to a supervisor for scope <scope>.` |

**The responses.** `customer_lookup` checks in this order: the ID format (a bad ID never reaches the database), then `failure_mode` (the database is unreachable or refuses), then the query. Each error result is `{"content": [{"type": "text", "text": json.dumps(body)}], "is_error": True}`:

| Situation | How it is triggered | `is_error` | JSON body |
|---|---|---|---|
| success | `CUST-1042`, `failure_mode="none"` | not set | `{"resultCount": 1, "customers": [{"customer_id": "CUST-1042", "name": "Dana Reyes", "email": "dana.reyes@example.com", "phone": "+1-503-555-0142", "tier": "gold"}]}` |
| valid empty result | `CUST-9999`, `failure_mode="none"` | not set | `{"resultCount": 0, "customers": []}` |
| transient | `failure_mode="timeout"` (every lookup) or `"flaky"` (lookups 1 and 2 only) | `True` | `{"errorCategory": "transient", "isRetryable": true, "description": "The customer database did not answer within 5 seconds. This is temporary: retry the same request."}` |
| validation | an ID that isn't `CUST-` plus 4 digits, such as `1042` | `True` | `{"errorCategory": "validation", "isRetryable": false, "description": "customer_id '1042' is not a valid customer ID. Use CUST- followed by 4 digits, such as CUST-1042, then call again."}` |
| business | `process_refund` over $500, such as `750` | `True` | `{"errorCategory": "business", "isRetryable": false, "description": "Refund of $750.00 exceeds the $500.00 policy limit for agent refunds. Do not retry or split it; escalate to a human agent, who can approve it."}` |
| permission | `failure_mode="denied"` (every lookup) | `True` | `{"errorCategory": "permission", "isRetryable": false, "description": "Access denied: this agent's role (support-tier1) cannot read customer records. Do not retry with the same access; call request_credentials for scope customers:read."}` |

With `structured=False` (the anti-pattern used in POC 2), every error above and the valid empty result return `{"content": [{"type": "text", "text": "Operation failed."}], "is_error": True}`. The success result doesn't change.

Every run gets its options from `errors_setup.py`:

```python
REFUND_LIMIT = 500
ERROR_CATEGORIES = ("transient", "validation", "business", "permission")
RECOVERY = {  # one recovery action per category (C5, C13)
    "transient": "retry the same call; after 3 retries, call escalate_to_human",
    "validation": "fix the input as the description says, then call again",
    "business": "never retry: call escalate_to_human with the reason",
    "permission": "never retry: call request_credentials for the scope named in the description",
}

RECOVERY_PROMPT = (
    "You are a support assistant for Lumen Home, an online store. Use the tools and never guess an ID or an amount. "
    "Tool errors come back as JSON with errorCategory, isRetryable and description. Recover by category: "
    + "; ".join(f"{category}: {action}" for category, action in RECOVERY.items()) + ". "
    "A result with resultCount 0 is a successful lookup that found nothing: tell the user, and don't retry it."
)

@dataclass
class ErrorState:  # one per run: "the current session" (04 C7, 05's HookState)
    calls: Counter = field(default_factory=Counter)               # handler runs per short tool name
    events: list[tuple] = field(default_factory=list)             # (seconds since start, tool, input, outcome) from handlers and the hook
    last_error: dict = field(default_factory=dict)                # call_key -> the error body the handler returned, or None after a success
    retries: Counter = field(default_factory=Counter)             # call_key -> retries the hook allowed (POC 2)
    escalations: list[dict] = field(default_factory=list)
    credential_requests: list[dict] = field(default_factory=list)
    refunds: list[dict] = field(default_factory=list)
    started: float = field(default_factory=time.monotonic)

CRM_TOOLS = ["mcp__crm__customer_lookup", "mcp__crm__process_refund",
             "mcp__crm__escalate_to_human", "mcp__crm__request_credentials"]

def build_error_options(state, failure_mode="none", structured=True, hooks=None):
    return ClaudeAgentOptions(
        model="claude-opus-5-5",
        system_prompt=RECOVERY_PROMPT,                 # the same policy in every run, structured or not (C8)
        mcp_servers={"crm": build_crm_server(state, failure_mode, structured)},  # fresh tools bound to this run's state
        tools=[],                                      # no built-in tools: Claude can use only ours
        allowed_tools=CRM_TOOLS,                       # no permission prompts
        hooks=hooks,                                   # POC 2: build_retry_hooks(state); None = no loop policy
        setting_sources=[],                            # ignore ~/.claude and project settings, CLAUDE.md and hooks
        env={"ENABLE_TOOL_SEARCH": "false"},           # load tool schemas upfront: no ToolSearch calls
        max_turns=15,                                  # safety cap (01 C16); 3 retries plus an escalation need about 6
    )
```

---

## 2. Concepts and POC requirements

All 17 concepts in the raw file (C1–C17) are covered: all 17 are new or build on earlier POCs and are taught below, none is a terminal command, and none was already covered by an earlier revised file (see the end of this section).
Previous revised files checked: `01-revised-Agentic-Loops.md`, `02-revised-Multi-Agent-Orchestration.md`, `03-revised-Subagent-Invocation-and-Context-Passing.md`, `04-revised-Workflow-Enforcement-and-Handoff.md`, `05-revised-Agent-SDK-Hooks.md`, `06-revised-Task-Decomposition-Strategies.md`, `01-revised-Tool-Interface-Design.md` (the domain-02 files `03-` to `05-revised-…` are still empty).
Raw step → concepts: **1** → C1–C3 · **2** → C4–C6 · **3** → C7–C9 · **4** → C10–C12 · **5** → C13–C17.
Rows marked **E** are extras that are not in the raw file. Without them, the POC breaks or gives misleading results.

### POC 1: The error contract

**Build:** two pieces of code.

**`errors_setup.py`:** the mock customers, `REFUND_LIMIT`, `ERROR_CATEGORIES`, `RECOVERY`, `RECOVERY_PROMPT`, `ErrorState`, `CRM_TOOLS` and `build_error_options()` (code above). It also defines:
- `mock_db_lookup(customer_id, failure_mode, attempt)`: returns `("error", body)` or `("ok", customers)`, in the check order above;
- `build_crm_server(state, failure_mode="none", structured=True)`: defines the four tools inside the function, so every handler reads and writes that one state. Every handler adds 1 to `state.calls[<tool>]`, appends `(seconds, tool, input, outcome)` to `state.events`, and sets `state.last_error[call_key(tool, args)]` to the error body it returned, or to `None`;
- `call_key(tool, args)`: returns `(tool, json.dumps(args, sort_keys=True))`, so a corrected input is a different call;
- `parse_body(result)`: the JSON body of a result's text, or `None` when the text isn't JSON;
- `validate_error(body)`: returns a list of errors, empty if the body is valid;
- `is_valid_empty(result)`: True only for a result that isn't an error and whose body is exactly `{"resultCount": 0, "customers": []}`.

POC 2 reuses it. `python errors_setup.py` runs an offline self-check that makes no API calls. It calls the handlers directly, with a new `ErrorState` per case, for the six situations in the responses table.

**`poc1_contract.py`:** two live runs of `EMPTY_PROMPT = "Is there a customer with ID CUST-9999?"`. Each gets a new `ErrorState` and `run_agent(EMPTY_PROMPT, options=build_error_options(state, failure_mode))`, with `failure_mode="none"` and then `"timeout"`. No hook and no `structured=False` run here: recovery is POC 2.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C1 | An MCP tool, `customer_lookup`, that queries a mock customer database, with a `failure_mode` parameter that triggers specific error conditions on demand (**Builds on** `01-revised-Agentic-Loops.md` C3) | Define `customer_lookup` in `build_crm_server()` (tables above). `mock_db_lookup(customer_id, failure_mode, attempt)` is the mock database: it takes the identifier and the failure mode and returns the condition asked for. New compared with 01 C3: the mock can fail on demand, and the tool's result says how it failed. Run `poc1_contract.py` | The self-check prints all 4 full tool names. In both live runs, Claude calls `mcp__crm__customer_lookup` with `{"customer_id": "CUST-9999"}`, so the server is running |
| E1 | `failure_mode` is a harness switch, not a tool input | `failure_mode` is an argument of `build_crm_server()`, set by the script before the run, and the tool's input schema has only `customer_id`. If Claude passed the failure mode itself, it would know which failure was coming before it saw the error, and POC 2's unstructured runs couldn't show what an agent does with an error that carries no information. Validation and business errors need no switch: they come from the input (a bad ID, or a refund over $500) | Code review: the `customer_lookup` input schema has exactly one property, `customer_id` |
| C4 | Four error types: transient (a simulated timeout), validation (invalid input format), business (a refund over the policy limit) and permission (access denied) (**New**) | The self-check triggers each one: `CUST-9999` with `"timeout"`, `1042` with `"none"`, `process_refund("CUST-1042", 750)`, and `CUST-1042` with `"denied"`. It prints each result's `is_error` and body | 4 results, each with `is_error: True` and the body from the responses table. Their `errorCategory` values are `transient`, `validation`, `business` and `permission`, one each |
| C7 | Structured metadata in every error: the JSON body has exactly 3 fields, `errorCategory` (one of the 4 categories), `isRetryable` (a boolean) and `description` (a sentence explaining the error and suggesting a recovery) (**New**) | `validate_error(body)` checks four rules: exactly the 3 keys and nothing else; `errorCategory` in `ERROR_CATEGORIES`; `isRetryable` a real `bool` that is `True` only for `transient`; and `description` a non-empty string of at least 2 sentences, what went wrong and what to do next, split as in `01-revised-Tool-Interface-Design.md` (`sentence_count()`). `isError` stays outside the body: it is the result flag (`is_error`), not a JSON field | `validate_error()` returns `[]` for all 4 bodies. It returns an error for a body with a 4th key, for `"isRetryable": "true"` (a string), and for a business body with `"isRetryable": true`. Each description has exactly 2 sentences |
| C6 | Each error response has `isError: true`, a specific `errorCategory`, the correct `isRetryable`, and a message saying what went wrong and what to do next (**Builds on** `01-revised-Agentic-Loops.md` E4 and `04-revised-Workflow-Enforcement-and-Handoff.md` C8) | In the `"timeout"` live run, print the first `tool_results` entry: its `is_error` and its text. New compared with 01 E4 and 04 C8: the error is still a returned result that names the next step, but the category and the retry decision are machine-readable fields, not prose | The `ToolResultBlock` that Claude received has `is_error=True`, and its text parses to the transient body unchanged, with all 3 fields |
| C5 | Each category needs a different recovery strategy: identify the category, then the recovery. Transient errors are retryable; business errors never are (**New**) | `RECOVERY` maps each category to its action (code above). The self-check prints, for each of the 4 bodies, the category, `isRetryable` and the `RECOVERY` action | The `isRetryable` values in category order are `[True, False, False, False]`. `RECOVERY` has exactly the 4 categories, and only `transient` says "retry" |
| C10 | A valid empty result (`isError: false`, `resultCount: 0`: the query ran and found nothing) is structurally different from an access failure (`isError: true`, `errorCategory: transient`, `isRetryable: true`) (**New**) | Print both live runs side by side: the same prompt and the same ID, with `failure_mode` `"none"` and then `"timeout"`. Show each first `ToolResultBlock` and `is_valid_empty()` | `"none"`: `is_error` not `True`, the body is `{"resultCount": 0, "customers": []}`, `is_valid_empty()` is True, and Claude typically answers that no customer has that ID after 1 call. `"timeout"`: `is_error=True`, the transient body, and `is_valid_empty()` is False. Claude typically says the lookup failed for now; how often it retries is POC 2's subject |

### POC 2: Recovery branches in the agent loop

**Build:** `recovery_hooks.py` and three scripts, reusing `errors_setup.py` and `run_agent()`.

**`recovery_hooks.py`** defines `MAX_RETRIES = 3`, `BACKOFF_SECONDS = (1, 2, 4)` and `build_retry_hooks(state)`. It returns `{"PreToolUse": [HookMatcher(matcher="mcp__crm__customer_lookup|mcp__crm__process_refund", hooks=[retry_policy])]}`, a list of exact names (`05-revised-Agent-SDK-Hooks.md` E2). Its callback `retry_policy(input_data, tool_use_id, context)` closes over `state`. It reads `state.last_error[call_key(tool, tool_input)]` and works as follows:
- **no error recorded** (a first call, or the last call succeeded): returns `{}`;
- **`isRetryable` true:** if `state.retries[key] < MAX_RETRIES`, it awaits `asyncio.sleep(BACKOFF_SECONDS[n])`, adds 1 to `state.retries[key]`, appends a `retry n after s seconds` event and returns `{}`. Otherwise it denies with `Retry budget exhausted: 3 retries of this call already failed with a transient error. Do not retry again; call escalate_to_human with category transient.`;
- **`isRetryable` false:** it denies with `Not retryable (<category>): this exact call already failed and isRetryable is false. Instead: <RECOVERY[category]>.`

Every deny is `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": ...}}` and is appended to `state.events`. `python recovery_hooks.py` runs an offline self-check that calls `retry_policy` directly.

**The scripts.** Each run gets a new `ErrorState` and `run_agent(prompt, options=build_error_options(state, failure_mode, structured, hooks))`. Each script prints, for each run:
- `state.events`, with their times;
- `state.calls`, the escalations, the credential requests and the refunds;
- the answer.

Each run's summary is saved under its name in `recovery_results.json`. The prompts:
- `LOOKUP_PROMPT = "What loyalty tier is customer CUST-1042 in?"`
- `VALIDATION_PROMPT = "What's the email address of customer number 1042?"`
- `REFUND_PROMPT = "Please refund $750.00 to customer CUST-1042 for the damaged Nimbus headphones."`
- `PERMISSION_PROMPT = "What's the phone number of customer CUST-2077?"`
- `EMPTY_PROMPT` from POC 1.

| Script | Run | `failure_mode` | `structured` | `hooks` | Prompt |
|---|---|---|---|---|---|
| `poc2_retry_runs.py` | `flaky` | `"flaky"` | True | `build_retry_hooks(state)` | `LOOKUP_PROMPT` |
| | `timeout` | `"timeout"` | True | `build_retry_hooks(state)` | `LOOKUP_PROMPT` |
| | `validation` | `"none"` | True | `build_retry_hooks(state)` | `VALIDATION_PROMPT` |
| `poc2_redirect_runs.py` | `business` | `"none"` | True | `build_retry_hooks(state)` | `REFUND_PROMPT` |
| | `permission` | `"denied"` | True | `build_retry_hooks(state)` | `PERMISSION_PROMPT` |
| | `empty` | `"none"` | True | `build_retry_hooks(state)` | `EMPTY_PROMPT` |
| `poc2_without_structure.py` | `flaky-unstructured` | `"flaky"` | False | `None` | `LOOKUP_PROMPT` |
| | `business-unstructured` | `"none"` | False | `None` | `REFUND_PROMPT` |
| | `empty-unstructured` | `"none"` | False | `None` | `EMPTY_PROMPT` |

`poc2_without_structure.py` runs its 3 runs and then prints each next to its structured twin from `recovery_results.json`.

Expected counts: `flaky` fails twice and succeeds on lookup 3, after waits of 1 and 2 seconds. `timeout` makes 1 + 3 = 4 lookups, with 1 + 2 + 4 = 7 seconds of backoff.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C13 | An agent loop that parses the error metadata and branches on `errorCategory`, with one recovery action per category: the practical outcome of structured metadata, and the decision logic the exam expects (**Builds on** `04-revised-Workflow-Enforcement-and-Handoff.md` C11) | Claude does the branching, from `RECOVERY_PROMPT` and the error body. Each script prints one branch line per run: the category of the first error, the next tool Claude called, the expected action from `RECOVERY`, and ✅/❌. New compared with 04 C11: there, one error had one recovery; here, four categories need four different actions, and only the metadata tells them apart | Typically ✅ for all 6 structured runs: `flaky` and `timeout`: the same lookup again; `validation`: `customer_lookup` with a changed input; `business`: `escalate_to_human`; `permission`: `request_credentials`; `empty`: no error, so no recovery |
| C14 | Transient errors are retried up to 3 times with backoff (**Builds on** `05-revised-Agent-SDK-Hooks.md` C12 and `01-revised-Agentic-Loops.md` C16) | `retry_policy` (above) sleeps before each allowed retry and denies a 4th one. New compared with 05 C12 and 01 C16: the hook allows a call and only delays it, and the cap counts retries of one failing call, not the whole loop's turns. Claude can't wait between calls, and a cap must hold every time, so both live in code | Self-check: with a transient error recorded, 3 calls return `{}`, with `state.retries` rising to 3, and the 4th returns a deny with `Retry budget exhausted`. `flaky`: `state.calls["customer_lookup"] == 3`, the event gaps are at least 1 and 2 seconds, and the answer is `gold`. `timeout`: 4 lookups, gaps of at least 1, 2 and 4 seconds, then 1 escalation with category `transient`. A 5th lookup attempt, if Claude makes one, is denied |
| C15 | After a validation error, reformat the input and try again (**New**) | Run `validation`. The validation body says which format to use (responses table) | 2 lookups: `{"customer_id": "1042"}` gives the validation error, then `{"customer_id": "CUST-1042"}` succeeds. The answer contains `dana.reyes@example.com`. No escalation |
| E2 | The validation branch needs a description without the ID format | The `customer_lookup` description deliberately leaves out the `CUST-` format. Otherwise Claude would write `CUST-1042` on the first call, and the validation error would never happen. In production, state the format in the description (`01-revised-Tool-Interface-Design.md` C9) and still validate in the handler: the description lowers the error rate, and the validation catches what slips through | Code review: no `CUST-` in the `customer_lookup` description. The `validation` run's first lookup uses `1042` |
| C16 | After a business error, escalate to a human and never retry (**Builds on** `04-revised-Workflow-Enforcement-and-Handoff.md` C12) | Run `business`. New compared with 04 C12: the escalation is chosen because of a machine-readable category, not a business rule written in the prompt. 04's five-field handoff isn't rebuilt here | `state.calls["process_refund"] == 1`, `state.refunds == []`, and 1 escalation with category `business` whose summary typically mentions the $500 limit. If Claude repeats the refund call, the hook denies it with `Not retryable (business)` |
| C17 | After a permission error, request elevated credentials and never retry with the same access (**New**) | Run `permission` | `state.calls["customer_lookup"] == 1`, and 1 credential request with scope `customers:read`. The answer typically tells the user that access has been requested. If Claude repeats the lookup, the hook denies it with `Not retryable (permission)` |
| C9 | `isRetryable: false` means take an alternative path, not retry (**New**) | Across the `validation`, `business` and `permission` runs, count the repeats of a failed call with the identical input (the same `call_key`), and print which other path each run took | 0 identical repeats ran in all three runs: the corrected input in `validation` is a different call, and any identical repeat was denied by the hook. The alternative paths: a fixed input, `escalate_to_human` and `request_credentials` |
| C12 | Retrying a successful empty query is the canonical anti-pattern (**New**) | Run `empty`. No error is recorded for a successful empty result, so the hook allows a repeat, and only the metadata (`resultCount: 0`, no error) can stop it | `state.calls["customer_lookup"] == 1`, no escalation, and an answer that says no customer has the ID `CUST-9999` |
| C2 | Simulated failure modes in a controlled environment let you observe how agents behave when errors lack structure (**New**) | `poc2_without_structure.py` replays three structured runs with `structured=False` and no hook, keeping the same `failure_mode`, prompt and `RECOVERY_PROMPT`. Only the response format changes. Print each pair side by side: the calls per tool, the escalations, the gaps between lookups, and the answer | 3 pairs. In every unstructured run, each failure reached Claude as `Operation failed.` with `is_error=True` |
| C8 | Structured metadata is what enables intelligent recovery: without these fields, the agent can't tell a transient timeout from a permanent policy violation (**New**) | Print the first error text of `flaky-unstructured` next to that of `business-unstructured`, then the same pair from the structured runs | Unstructured: the two texts are identical, `Operation failed.`, so nothing in them separates a timeout that will pass from a refund that must never be retried. Structured: they differ in `errorCategory` (`transient` against `business`) and `isRetryable` (`true` against `false`). The system prompt was the same in all four runs |
| C11 | Confusing an access failure with a valid empty result causes wasted retries and incorrect escalations, one of Domain 2's most critical distinctions (**New**) | Compare `empty` with `empty-unstructured`: the same successful empty lookup, once as `resultCount: 0` and once as `Operation failed.` | `empty`: 1 lookup, and the answer says no such customer exists. `empty-unstructured`: typically 2 or more lookups of `CUST-9999` (wasted retries of a query that had succeeded), an escalation, or an answer that blames a system problem instead of saying no such customer exists |
| C3 | Poor error responses cause wasted retries and incorrect escalations (**New**) | For each unstructured run, compute the wasted retries (that run's calls to the failing tool minus its structured twin's) and the incorrect escalations (escalations in `flaky-unstructured` or `empty-unstructured`, whose twins needed none). Print the totals over the three runs | Typically at least 1 wasted retry or incorrect escalation per unstructured run, against 0 in the structured twins. Examples: `business-unstructured` calls `process_refund` again, and `flaky-unstructured` gives up or escalates before lookup 3, which would have succeeded. The exact behavior varies between runs |

### Terminal commands (for the later tutorial)

None: every concept in this topic is a programming concept.

### Already covered by earlier POCs

None: every concept in this topic is new or builds on an earlier POC (cited in its row).
