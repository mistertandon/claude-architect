# Error Propagation in Multi-Agent Systems: Revised POC Requirements (5 steps → 2 POCs, Claude Agent SDK)

> **Source:** `03-raw-Error-Propagation-in-Multi-Agent-Systems.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Context Management & Reliability → Error Propagation in Multi-Agent Systems · **Build with:** Claude Agent SDK for Python (`claude_agent_sdk`)

---

## 1. Verdict: 2 POCs

The 5 raw steps are not 5 separate concepts. Steps 1–3 build **one subagent search layer and the report it sends**: step 1 is the report's shape, step 2 the try/except that fills it, and step 3 the local retry that decides when a failure is final. Steps 4–5 are **one coordinator run that consumes those reports**: step 4 recovers from them, and step 5 states what the finished brief covers. What you need to learn splits into the two sides of that hop:

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: The subagent reports precisely and retries locally** | **Only what can't be fixed locally leaves the subagent, and it leaves complete:** a try/except tells timeouts from valid empty results, transient failures get 3 retries with doubling delays, every source that arrived is kept, and one structured report goes out (`status`, `shouldRetry`, `failureType`, `attemptedAction`, `partialResults`, `alternativeApproaches`). Offline, on 8 topics with planted failures | 1, 2, 3 |
| **POC 2: The coordinator recovers and annotates coverage** | **Different failures get different recoveries, and no gap is silent:** a coordinator delegates 7 topics and reads each researcher's report. It recovers by failure type: proceed with partial results, re-delegate with a narrower query or fixed parameters, escalate, or alert an administrator. Then it writes a brief whose separate coverage section names every gap and its cause. Two offline anti-pattern coordinators show what suppression and termination would have delivered | 4, 5 |

**What changes with the Agent SDK:** a Claude subagent can't catch a Python exception or wait between attempts, so the subagent's error handling lives in its tool's code. The handler of `search_sources` catches the backend's exceptions, retries, and returns the report; POC 1 proves that code offline. POC 2 puts it behind a real `AgentDefinition` whose prompt makes it relay the report unchanged. The report crosses the hop as the subagent's final message, which the coordinator receives as the Agent tool result (`02-revised-Multi-Agent-Orchestration.md` C13). Two SDK facts shape the design:
- **`is_error` stops at the subagent.** The tool result's `is_error` flag reaches only the subagent. The coordinator gets the subagent's final message, so the outcome has to be written into the report itself (C5).
- **An escaped exception becomes a bare message.** An exception that escapes a handler doesn't stop the loop: "The MCP server converts it to an error result carrying the raw exception message." That raw message is the generic error the exam warns about (C3), so no exception may escape (C8).

The coordinator's recovery choices are model decisions, so they can only be observed, not coded. POC 2 reads them from the stream (later Agent calls, `escalate_to_human` and `alert_admin` calls) and checks each one against an expected action per topic. The brief comes back as structured output (`output_format`), so Python checks every coverage annotation.

- **Why not 1 POC:** POC 2's recovery decisions only mean something once every report is known to be right. POC 1 proves offline, with exact attempt counts, waits and partial results, that each report says what happened. A wrong recovery in POC 2 can then only come from the coordinator, not from a malformed report or a lost source. POC 1 also runs its 17 seconds of backoff and its planted failures without paying for a model call.
- **Why not 3 or more:** steps 1–3 build one function and the report it returns. The try/except fills the schema, and the retry decides when a failure is final, so they can't be tested apart. Step 5's coverage section is written by the same coordinator run as step 4's recovery, from the same reports.

**Applies to both POCs:**
- **Setup:** Python 3.10+ and `pip install claude-agent-sdk` (a recent 0.2.x; it bundles the Claude Code binary). POC 2 needs `ANTHROPIC_API_KEY` set in the environment (never hard-coded); POC 1 makes no API calls. Mock data only, and beginner-friendly code (small, commented scripts).
- **Runner:** the coordinator runs through `run_coordinator()` from `02-revised-Multi-Agent-Orchestration.md` (`coordinator.py`). It is used as extended in `03-revised-Subagent-Invocation-and-Context-Passing.md` (`options=`, per-call `message_id`/`started`/`finished`, `research_calls` from any MCP server) and in `06-revised-Task-Decomposition-Strategies.md`.
- **Parsing:** reports are parsed with `parse_json_object()`, copied from `03-revised-Subagent-Invocation-and-Context-Passing.md` (E2).
- **Tools:** they follow `tools.py` from `01-revised-Agentic-Loops.md` (C2–C3): `@tool` with a full JSON Schema dict, async handlers that return `{"content": [...]}`, and `is_error` instead of raising.
- **Data:** the made-up "Helios Institute 2026 Renewables Review" of `02-revised-Multi-Agent-Orchestration.md`, served by a mock source library with failures planted per topic.

**The source library** (`SOURCES`). Every source is `{"id", "fact"}`:

| Topic | Sources |
|---|---|
| solar | `SOL-1` Solar capacity grew 31% in 2025. · `SOL-2` Utility-scale solar cost fell to $27.40/MWh. · `SOL-3` Rooftop systems made up 38% of new solar capacity. |
| wind | `WND-1` Offshore wind added 19.6 GW in 2025. · `WND-2` The average wind capacity factor reached 41.3%. · `WND-3` Turbine orders rose 12% year on year. |
| geothermal | `GEO-1` Geothermal output rose 8.7%. · `GEO-2` Enhanced-geothermal pilot wells reached 245 °C. · `GEO-3` Three new binary-cycle plants came online. · `GEO-4` Drilling costs fell 14% per metre. · `GEO-5` Geothermal heat networks served 1.2 million homes. |
| tidal | `TID-1` Tidal stream capacity reached 1.9 GW. · `TID-2` The Kestrel Strait array ran at a 37.5% capacity factor. · `TID-3` Two new tidal stream projects passed permitting. |
| hydropower | `HYD-1` Hydropower supplied 14.2% of electricity. · `HYD-2` Pumped-storage capacity rose to 212 GW. · `HYD-3` Drought cut output at 6 major dams by 9%. |
| biomass, fusion, ocean thermal | none ever returned (see the plan) |

**The planted failures.** `backend_stream(topic, query, region, attempt)` is a generator that yields sources one at a time and may raise:
- `NARROW = {"geothermal": "capacity", "tidal": "stream"}` holds the keyword that makes a query narrow enough to finish.
- `REGIONS = ["global", "americas", "europe", "asia"]`.
- `SourceRejected(failure_type, description, alternatives)` is the exception for a source that answers and refuses.

Any topic not in the table raises `SourceRejected("validation", "Unknown topic '<topic>'.", ["use one of the brief's topics"])`.

| Topic | What the backend does | Report after local retries |
|---|---|---|
| solar | yields all 3 | `success`, 3 results |
| wind | attempt 1 raises `TimeoutError`, attempt 2 raises `ConnectionError`, attempt 3 yields all 3 | `success`, 3 results: the 2 failures stay inside the subagent |
| geothermal | a query containing `capacity` yields all 5. Otherwise, attempt 1 yields `GEO-1` and `GEO-2` and then raises `TimeoutError`; attempt 2 yields `GEO-3` and then raises `TimeoutError`; attempts 3 and 4 raise `TimeoutError` | `partial_failure`, transient, 3 partial results |
| tidal | a query containing `stream` yields all 3. Otherwise, attempt 1 yields `TID-1` and then raises `TimeoutError`; attempts 2–4 raise `TimeoutError` | `partial_failure`, transient, 1 partial result |
| hydropower | without a `region` from `REGIONS`, raises `SourceRejected("validation", "Hydropower sources are indexed by region, and no region was given.", ["call search_sources again with region set to global, americas, europe or asia"])`. With one, it yields all 3 | `error`, validation |
| biomass | raises `SourceRejected("business", "The Bioenergy Monitor dataset is licensed: access costs $4,800, and the research budget allows $500 per source.", ["ask a human to approve the $4,800 licence", "report biomass as unavailable"])` | `error`, business |
| fusion | raises `SourceRejected("permission", "Access denied: the Aurora Labs fusion data room needs the research:restricted scope, which this research key doesn't have.", ["ask an administrator to grant the research:restricted scope", "report fusion as unavailable"])` | `error`, permission |
| ocean thermal (POC 1 only) | yields nothing: the library has no 2026 sources on it | `success`, 0 results |

**The report** (`REPORT_SCHEMA`) is what a researcher returns for one topic. `build_report()` writes it in Python and `validate_report()` checks it. Each property's `description` says why the coordinator needs it:

```python
REPORT_SCHEMA = {
    "type": "object", "required": ["topic", "status", "shouldRetry", "results", "error"],
    "properties": {
        "topic": {"type": "string", "description": "The topic this report covers."},
        "status": {"type": "string", "enum": ["success", "partial_failure", "error"],
                   "description": "success: the search finished, even with 0 results. partial_failure: it failed after "
                                  "retrieving some sources. error: it failed with nothing retrieved."},
        "shouldRetry": {"type": "boolean",
                        "description": "true only for an access failure (timeout, connection error): trying again may work."},
        "results": {"type": "array", "description": "The sources of a finished search; [] for a valid empty result or a failure."},
        "error": {"type": ["object", "null"], "description": "null on success; otherwise the context the coordinator decides with.",
                  "required": ["failureType", "attemptedAction", "partialResults", "alternativeApproaches", "description"],
                  "properties": {
                      "failureType": {"type": "string", "enum": ["transient", "validation", "business", "permission"],
                                      "description": "The kind of failure, which selects the recovery."},
                      "attemptedAction": {"type": "object", "required": ["tool", "query", "parameters"],
                                          "description": "Exactly what was tried, so a retry can change it on purpose."},
                      "partialResults": {"type": "array",
                                         "description": "Every source retrieved before the failure, across all attempts."},
                      "alternativeApproaches": {"type": "array", "items": {"type": "string"},
                                                "description": "Recovery options the coordinator can choose from."},
                      "description": {"type": "string", "description": "What went wrong, in one or two sentences."}}}}}
```

`build_report()` always fills `attemptedAction` with `{"tool": "search_sources", "query": query, "parameters": {"region": region}}`.
- **A final access failure** gets `failureType` `transient` and the `description` `The Helios library timed out on all 4 attempts (1 try and 3 local retries); <n> source(s) arrived before the timeouts.` Its `alternativeApproaches` are `["retry with a narrower query, such as '<topic> <NARROW[topic]> 2026'", "proceed with the <n> partial result(s)"]`.
- **A rejection** uses its own failure type, description and alternatives.

**The coordinator** (POC 2). Every coordinator call gets its options from `propagation_setup.py`:

```python
MODEL = "claude-opus-5-5"
SUFFICIENT_SOURCES = 3   # partial results at or above this are enough to proceed (C17)

RECOVERY_POLICY = (  # one recovery per failure type (C16), plus the partial-results rule (C17)
    "- success: use the results. A success with no results is a valid answer: don't retry it.\n"
    f"- transient: if partialResults hold at least {SUFFICIENT_SOURCES} sources, proceed with them and mark the topic "
    "limited; otherwise delegate the topic once more with the narrower query from alternativeApproaches.\n"
    "- validation: delegate the topic once more, with the parameters fixed as the error says.\n"
    "- business: don't retry; call escalate_to_human with the topic and the reason.\n"
    "- permission: don't retry; call alert_admin with the topic, the missing scope and the reason.")

COORDINATOR_PROMPT = (
    "You coordinate the research for the Helios Institute 2026 renewables brief. Never search yourself: give each "
    "topic to the researcher subagent with the Agent tool. Every Agent prompt is exactly three lines: "
    "'topic: <topic>', 'query: <query>' and 'parameters: <JSON object, {} if none>'. First, delegate every topic at "
    "once, in one response, with the query '<topic> 2026' and parameters {}. Each researcher returns a JSON report "
    "with status, shouldRetry, results and error. Recover from each report by its status and failureType:\n"
    + RECOVERY_POLICY + "\n"
    "Never drop a topic, and never abandon the brief because one topic failed. Write findings only from sources the "
    "reports returned, citing their ids. Give every topic one coverage entry: well_supported (complete results), "
    "limited (partial results, with the reason) or unavailable (no usable results, with what failed and why).")

AGENTS = {
    "researcher": AgentDefinition(
        description="Researches one topic of the Helios brief with search_sources and returns its JSON report.",
        prompt=("You are a research subagent. Call search_sources exactly once, with exactly the topic, query and "
                "parameters in your task and nothing else. Your final message must be only the JSON report that "
                "search_sources returned, unchanged: never summarise it, shorten it or describe an error in your own words."),
        tools=["mcp__sources__search_sources"],   # its only tool
        model="inherit",
        maxTurns=5,
    ),
}

BRIEF_SCHEMA = {  # the findings, and a separate coverage section (C18, C20)
    "type": "object", "required": ["sections", "coverage"],
    "properties": {
        "sections": {"type": "array", "items": {"type": "object", "required": ["topic", "findings"], "properties": {
            "topic": {"type": "string"},
            "findings": {"type": "array", "items": {"type": "object", "required": ["claim", "source_ids"], "properties": {
                "claim": {"type": "string"}, "source_ids": {"type": "array", "items": {"type": "string"}}}}}}}},
        "coverage": {"type": "array", "items": {"type": "object", "required": ["topic", "status", "reason", "sources_used"],
            "properties": {"topic": {"type": "string"},
                           "status": {"type": "string", "enum": ["well_supported", "limited", "unavailable"]},
                           "reason": {"type": "string"},
                           "sources_used": {"type": "integer"}}}}}}

@dataclass
class PropagationState:  # one per run (05's HookState pattern)
    attempts: list[tuple] = field(default_factory=list)   # (topic, attempt, outcome, sources_received, wait) per backend attempt
    reports: list[dict] = field(default_factory=list)     # every report search_with_retry() built, in order
    escalations: list[dict] = field(default_factory=list)
    alerts: list[dict] = field(default_factory=list)

def build_propagation_options(state):
    return ClaudeAgentOptions(
        model=MODEL,
        system_prompt=COORDINATOR_PROMPT,                               # the recovery policy and the coverage rule
        output_format={"type": "json_schema", "schema": BRIEF_SCHEMA},  # the brief as validated JSON
        tools=["Agent"],                                                # the coordinator's only built-in tool: it delegates
        agents=AGENTS,                                                  # the researcher subagent
        mcp_servers={"sources": build_sources_server(state),            # search_sources, used by the researcher
                     "ops": build_ops_server(state)},                   # escalate_to_human and alert_admin, used by the coordinator
        allowed_tools=["Agent", "mcp__sources__search_sources",
                       "mcp__ops__escalate_to_human", "mcp__ops__alert_admin"],  # no permission prompts
        disallowed_tools=["Agent(fork)"],                               # no forks (01-02 E1)
        setting_sources=[],                                             # ignore ~/.claude and project settings, CLAUDE.md and hooks
        env={
            "ENABLE_TOOL_SEARCH": "false",                              # load tool schemas upfront: no ToolSearch calls
            "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",                # each Agent result holds the report (01-02 E2)
            "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",             # only the researcher, no general-purpose fallback (01-02 E3)
        },
        max_turns=30,                                                   # safety cap per coordinator call (01 C16)
    )
```

**The tools** (POC 2) live in two servers that are built for every run, so their handlers share one `PropagationState`:

| Tool | Description (what Claude reads) | Input | Behavior |
|---|---|---|---|
| `mcp__sources__search_sources` (`readOnlyHint=True`) | `"Searches the Helios Institute source library for one topic. It retries timeouts itself (3 retries, waiting 1, 2 and 4 seconds) and returns one JSON report with status, shouldRetry, results and error."` | `topic`, `query` (required strings), `region` (optional, enum `REGIONS`) | `report = await search_with_retry(topic, query, region, state)`. Returns `json.dumps(report)` as the text, with `is_error: True` when `status` isn't `success` |
| `mcp__ops__escalate_to_human` | `"Opens a case for a human to decide about one topic of the brief, such as approving a paid licence."` | `topic`, `reason` (required strings) | Appends `{"id": "ESC-<n:04d>", "topic", "reason"}` to `state.escalations`. Returns `Escalation ESC-0001 opened for <topic>.` |
| `mcp__ops__alert_admin` | `"Alerts an administrator that the research key lacks an access scope a topic needs."` | `topic`, `scope`, `reason` (required strings) | Appends `{"id": "ADM-<n:04d>", "topic", "scope", "reason"}` to `state.alerts`. Returns `Alert ADM-0001 sent: an administrator will review the <scope> scope.` |

---

## 2. Concepts and POC requirements

All 20 concepts in the raw file (C1–C20) are covered: 18 are new or build on earlier POCs and are taught below, none is a terminal command, and 2 are already covered by `02-revised-Structured-Error-Responses.md` (see the end of this section).
Previous revised files checked: `01-revised-Agentic-Loops.md`, `02-revised-Multi-Agent-Orchestration.md`, `03-revised-Subagent-Invocation-and-Context-Passing.md`, `04-revised-Workflow-Enforcement-and-Handoff.md`, `05-revised-Agent-SDK-Hooks.md`, `06-revised-Task-Decomposition-Strategies.md`, `01-revised-Tool-Interface-Design.md`, `02-revised-Structured-Error-Responses.md`, `03-revised-Tool-Distribution-&-Tool-Choice.md`, `04-revised-MCP-Server-Integration.md`, `05-revised-Built-in-Tools.md`, `01-revised-System-Prompts-with-Explicit-Criteria.md`, `02-revised-Few-Shot-Prompting.md`, `03-revised-Structured-Output-with-Tool-Use.md`, `04-revised-Validation-Retry-and-Feedback-Loops.md`, `05-revised-Batch-Processing-Strategies.md`, `06-revised-Multi-Instance-and-Multi-Pass-Review.md`, `01-revised-Context-Window-Management.md`, `02-revised-Escalation-Ambiguity-Resolution.md`. None of them propagates errors between agents: `02-revised-Structured-Error-Responses.md` built the error contract and its recovery for one agent and its own tools, and `02-revised-Multi-Agent-Orchestration.md` rated coverage only to decide what to re-delegate.
Raw step → concepts: **1** → C1–C5 · **2** → C6–C9 · **3** → C10–C13 · **4** → C14–C17 · **5** → C18–C20. Each step adds a Nudge and a Guidance, so concepts come from all five parts.
Rows marked **E** are extras that are not in the raw file. Without them, the POC breaks or gives misleading results.

### POC 1: The subagent reports precisely and retries locally

**Build:** `propagation_setup.py` and `poc1_subagent_errors.py`. POC 1 makes no API calls.

`propagation_setup.py` holds everything both POCs share:
- `SOURCES`, `NARROW`, `REGIONS`, `SourceRejected` and `backend_stream()` (the plan above);
- `MAX_RETRIES = 3`, `BASE_DELAY = 1`, `search_once()` (C8), `search_with_retry()` (C10), `build_report()` and `REPORT_SCHEMA` (C1);
- `validate_report(report)`: returns a list of errors, empty when the report is valid. It checks four rules:
  - the report has exactly the 5 keys, `status` is in its enum, `shouldRetry` is a `bool`, and `results` is a list;
  - a `success` has `error` set to `None`;
  - a `partial_failure` or an `error` has `results == []` and an `error` object with exactly the 5 error keys:
    - `failureType` is in its enum, and `attemptedAction` has `tool`, `query` and `parameters`;
    - `alternativeApproaches` is a non-empty list of strings, and `description` isn't empty;
    - `partialResults` isn't empty for a `partial_failure` and is empty for an `error`;
  - `shouldRetry` is `True` exactly when `failureType` is `transient`;
- `PropagationState`, the two servers, the prompts, `AGENTS`, `BRIEF_SCHEMA` and `build_propagation_options()` (code above). Only POC 2 runs these.

`poc1_subagent_errors.py` defines `POC1_TOPICS` (the 7 brief topics plus ocean thermal) and `suppressing_search()` (C7). It runs `search_with_retry()` once per topic, one after another, with the first-round input (`<topic> 2026`, no region) and one `PropagationState`. For each topic, it prints:
- the attempts: outcome, sources received, and `wait`, the delay before the next attempt (0 when none follows);
- the report and its `validate_report()` result.

Then it prints the comparisons in the rows below. The backoff makes the run last about 3 + 7 + 7 = 17 seconds.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C1 | A structured error schema: `failureType` (an enum of transient, validation, business and permission), `attemptedAction` (the tool, query and parameters), `partialResults` (an array of whatever was retrieved) and `alternativeApproaches` (an array of suggested recovery strategies), with a description of each field's purpose (**Builds on** `02-revised-Structured-Error-Responses.md` C7) | `REPORT_SCHEMA` (code above) is a JSON Schema with a `description` on every property. Its `error` object holds the four fields plus the `description` sentence of 02-02 C7. `build_report()` fills it and `validate_report()` checks it (rules in the Build). New compared with 02-02 C7: the error also says what was attempted, what was already retrieved and what to try next. Its reader is a coordinator that must choose between several recoveries, not the agent that made the call | The script prints every property of `REPORT_SCHEMA` with its description. `validate_report()` returns `[]` for all 8 reports. It returns an error for each of 3 hand-built reports: `failureType` `timeout`, no `attemptedAction`, and a `partial_failure` with empty `partialResults` |
| C5 | A `status` field (`success`, `partial_failure` or `error`) separates a complete failure from a partial success that gathered some results (**New**) | `build_report()` sets `status` from the final outcome: `success` when the search finished (with any number of sources), `partial_failure` when it failed after keeping some sources, and `error` when it failed with none. The status belongs in the report. In POC 2, the tool result's `is_error` flag reaches only the subagent, while the coordinator receives the subagent's final message, so a failure that isn't written into the report can't reach the coordinator | `success` for solar, wind and ocean thermal; `partial_failure` for geothermal (3 sources) and tidal (1); `error` for hydropower, biomass and fusion |
| C8 | Use try/catch to separate infrastructure errors from empty results: the catch block handles access failures, and a successful empty response is a valid result (**New**) | `search_once(topic, query, region, attempt)` collects the sources of `backend_stream()` in a list inside `try`, and returns one of three outcomes:<br>• `except (TimeoutError, ConnectionError)` returns `{"outcome": "access_failure", "sources": <what arrived before the exception>, "detail": "<exception type>: <message>"}`.<br>• `except SourceRejected` returns the rejection's `failure_type` as the outcome, with its description and alternatives: the source answered, and the answer was no.<br>• The normal path returns `{"outcome": "ok", "sources": [...]}`, even when the list is empty.<br>No exception may escape: the custom-tools docs say that an uncaught handler exception becomes an error result carrying only the raw exception message (C3) | Wind's attempt 1 is `access_failure` (`TimeoutError`), and its attempt 2 is `access_failure` (`ConnectionError`). Ocean thermal's only attempt is `ok` with 0 sources, and hydropower's is `validation`. Code review: `backend_stream()` is called only inside `search_once()`'s `try` |
| C6 | A subagent that distinguishes access failures (timeout, connection error) from valid empty results (a successful query with no matches) in its error reporting (**Builds on** `02-revised-Structured-Error-Responses.md` C10) | Print the ocean thermal report (the library has no 2026 sources on it) next to the geothermal report (the library timed out). New compared with 02-02 C10: the subagent's search layer makes the distinction, for a coordinator one hop away. That coordinator never sees the exception and has only the report to go on | Ocean thermal: `status` `success`, `results` `[]`, `shouldRetry` `false` and `error` `null`. Geothermal: `status` `partial_failure`, `failureType` `transient`, `shouldRetry` `true` and 3 `partialResults` |
| C9 | A `shouldRetry` flag in the response schema: `true` for access failures and `false` for valid empty results (**Builds on** `02-revised-Structured-Error-Responses.md` C7) | `shouldRetry` is a required top-level boolean on every report, success included, and `validate_report()` requires it to be `True` exactly when `failureType` is `transient`. New compared with the `isRetryable` of 02-02 C7, which existed only on errors: the flag is on every report, so a coordinator never has to infer it from a missing field | Of the 8 reports, only geothermal and tidal have `shouldRetry: true`. A hand-built `success` report with `shouldRetry: true` fails `validate_report()` |
| C7 | Conflating access failures with valid empty results is a critical error the exam tests. An access failure means the query didn't run and should be retried. A valid empty result means it ran and found nothing, which IS the answer. Treating them the same means either never retrying when you should, or wasting retries on queries that will always return nothing (**Builds on** `02-revised-Structured-Error-Responses.md` C11) | `suppressing_search(topic, query)`, used only here, is the anti-pattern: it catches any exception and returns `{"topic", "status": "success", "shouldRetry": false, "results": [], "error": null}`. Run it on geothermal and print its report next to ocean thermal's real one. Then print `Same report for "the library was down" and "the library has nothing": a coordinator would never retry geothermal`. New compared with 02-02 C11, where the costly direction was retrying a real empty result: here a failure is reported as empty, which hides it instead of wasting calls | The two reports are equal except for `topic`. The suppressed geothermal report has also lost the 2 sources that had already arrived (`GEO-1`, `GEO-2`), because the attempt's data was thrown away with the exception |
| C10 | Local retry logic for transient failures inside the subagent: 3 retries with exponential backoff (1 s, 2 s, 4 s) before the structured error goes to the coordinator (**Builds on** `02-revised-Structured-Error-Responses.md` C14) | `search_with_retry(topic, query, region, state)` calls `search_once()` up to `1 + MAX_RETRIES` times. After an `access_failure`, it awaits the backoff (C12) and tries again. Any other outcome ends the loop at once: a finished search needs no retry, and a rejection would be rejected again. Every attempt appends `(topic, attempt, outcome, sources_received, wait)` to `state.attempts`, and the final report goes to `state.reports`. New compared with 02-02 C14, where a hook delayed Claude's own retries: here the retries run inside the subagent's tool, so neither the subagent's model nor the coordinator sees them | Attempts per topic: solar 1, wind 3, geothermal 4, tidal 4, hydropower 1, biomass 1, fusion 1 and ocean thermal 1, for 16 in all. Waits: 1 and 2 s for wind, and 1, 2 and 4 s each for geothermal and tidal. Hydropower, biomass and fusion get 0 retries |
| C12 | Exponential backoff avoids overwhelming a recovering service: the delay doubles with each retry (**Builds on** `02-revised-Structured-Error-Responses.md` C14) | The wait before retry n is `BASE_DELAY * 2 ** (n - 1)`, with `BASE_DELAY = 1`. The code computes it instead of listing it, so the doubling is visible. Print geothermal's waits next to the waits a fixed 1-second delay would give. New compared with 02-02 C14, which used a fixed `(1, 2, 4)` tuple: why the delay doubles. A struggling service gets more room after each failure, instead of a steady stream of calls that keeps it overloaded | Geothermal: `[1, 2, 4]`, 7 s in all, against `[1, 1, 1]`, 3 s, with a fixed delay. Each wait is twice the one before |
| C13 | Partial results gathered before a failure are kept, and accumulated across retries: if attempt 1 retrieves 2 of 5 sources and attempt 2 retrieves 1 more, the propagated error includes all 3 (**New**) | `search_with_retry()` keeps `retrieved`, a dict from source id to source, across all attempts. It merges each attempt's sources into it, so a source that arrives twice counts once. A failure report's `partialResults` is `list(retrieved.values())`. Print geothermal's sources per attempt, then its `partialResults` | Geothermal: attempt 1 brings `GEO-1` and `GEO-2`, attempt 2 brings `GEO-3`, and attempts 3 and 4 bring nothing. `partialResults` holds `GEO-1`, `GEO-2` and `GEO-3`. Keeping only the last attempt's sources would give 0, and the status would be `error` instead of `partial_failure` |
| C11 | Subagents handle their own transient failures locally, which keeps retry logic out of the coordinator: only failures that persist after local retry propagate (**New**) | After the 8 searches, count from `state.attempts` the failed attempts and the local retries, then the failure reports that leave the subagent (`status` other than `success`). Print `The coordinator will see <r> failure reports, not <a> failed attempts` | 13 failed attempts (wind 2, geothermal 4, tidal 4, and 1 each for hydropower, biomass and fusion) and 8 local retries (wind 2, geothermal 3, tidal 3) leave 5 failure reports: geothermal, tidal, hydropower, biomass and fusion. Wind's 2 failures never leave the subagent: its report is a plain `success` with 3 sources |

### POC 2: The coordinator recovers and annotates coverage

**Build:** `poc2_coordinator.py`, reusing `propagation_setup.py`, `run_coordinator()` and `parse_json_object()`. It makes one coordinator call, `run_coordinator(BRIEF_PROMPT, BRIEF_SCHEMA, options=build_propagation_options(state))` with a new `PropagationState`, and then works offline on what comes back. It defines:
- `TOPICS = ["solar", "wind", "geothermal", "tidal", "hydropower", "biomass", "fusion"]`;
- `BRIEF_PROMPT = "Write the Helios Institute 2026 renewables brief on these topics: solar, wind, geothermal, tidal, hydropower, biomass, fusion."`;
- `EXPECTED` (table below);
- `received_reports(result)`: for each Agent call, its topic (from the prompt's `topic:` line), its order, and its report parsed with `parse_json_object()`, with `validate_report()`'s errors;
- `decisions(result, state)` (C14), `check_coverage(brief, state)` (C18) and `render_brief(brief, with_coverage=True)` (C20);
- `suppress(reports)` and `terminate(reports)`, the two anti-pattern coordinators (C15), which run offline over the first-round reports.

| Topic | First report | Expected action | Coverage | `sources_used` |
|---|---|---|---|---|
| solar | `success`, 3 results | none | `well_supported` | 3 |
| wind | `success`, 3 results | none | `well_supported` | 3 |
| geothermal | `partial_failure`, transient, 3 partial results | proceed | `limited` | 3 |
| tidal | `partial_failure`, transient, 1 partial result | re-delegate with the narrower query | `well_supported` | 3 |
| hydropower | `error`, validation | re-delegate with a region | `well_supported` | 3 |
| biomass | `error`, business | escalate | `unavailable` | 0 |
| fusion | `error`, permission | alert an administrator | `unavailable` | 0 |

Expected counts: 7 first-round Agent calls and 2 re-delegations, so 9 Agent calls in all, plus 1 escalation and 1 alert.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| E1 | The first round sends fixed inputs | `COORDINATOR_PROMPT` makes the coordinator first delegate every topic with the query `<topic> 2026` and `parameters: {}`, in the three-line Agent prompt format. The planted failures depend on that input: hydropower's validation error needs a missing region, and the timeouts of geothermal and tidal need the broad query. If Claude picked a region or a narrower query on its own, those branches would never run, and their recovery couldn't be tested | Every first-round Agent prompt has the query `<topic> 2026` and `parameters: {}`. Typically all 7 share one `message_id` (`03-revised-Subagent-Invocation-and-Context-Passing.md` C15) |
| C2 | Structured error context enables intelligent coordinator recovery: the four fields give the coordinator what it needs to decide whether to retry, try an alternative, proceed with partial results or escalate (**Builds on** `02-revised-Structured-Error-Responses.md` C8) | The `researcher` relays the tool's report unchanged (its prompt is above). `received_reports()` parses each Agent call's report, runs `validate_report()`, and compares it with the report the tool built for that call (`state.reports`, matched by topic and order). Then print which report fields each recovery used: tidal's re-delegation should carry the narrower query from `alternativeApproaches`, and hydropower's the region its error names. New compared with 02-02 C8: the metadata must survive one more hop, the subagent's final message, before it can drive a decision | All 9 reports the coordinator received are valid and equal to the tool's reports. Tidal's second Agent prompt has a query containing `stream`, and hydropower's has a region in its parameters (typically `global`): both values came from the reports. Wind's report is a plain `success`, although `state.attempts` shows its 2 failures (C11) |
| C14 | A coordinator that receives structured errors and decides between a retry with a modified query, an alternative approach, or proceeding with partial results (**Builds on** `02-revised-Structured-Error-Responses.md` C13) | `COORDINATOR_PROMPT` carries `RECOVERY_POLICY` (code above). `decisions(result, state)` derives each topic's actions from the stream:<br>• `redelegate` for each later Agent call on that topic;<br>• `escalate` for an `escalate_to_human` call that names it;<br>• `alert` for an `alert_admin` call that names it;<br>• with none of these, `proceed` after a failure report, or `none` after a success.<br>Print one row per topic: the first report's status and failure type, the actions, the expected action from `EXPECTED`, and ✅/❌. New compared with 02-02 C13: the decider reads other agents' reports, and proceeding with partial results is one of its choices | Typically 7 ✅, as in `EXPECTED`, with 9 Agent calls in all. No `search_sources` call has `parent_tool_use_id is None`, so the coordinator never searched itself (`02-revised-Multi-Agent-Orchestration.md` C1) |
| C16 | The coordinator handles all four failure types differently and never silently suppresses an error: transient = retry with a modification, validation = fix the query parameters, business = escalate, permission = alert an administrator (**Builds on** `02-revised-Structured-Error-Responses.md` C5) | Print the decisions grouped by `failureType`. Assert that biomass and fusion have exactly 1 Agent call each: their reports say `shouldRetry: false`, and another try would be refused again. New compared with 02-02 C5: these are a coordinator's actions (re-delegate with a narrower query, re-delegate with fixed parameters, open an escalation for the topic, alert an administrator), and every failure still has to end up in the brief | Four failure types, four different actions. Transient leads to a narrower re-delegation (tidal) or to proceeding (geothermal, C17). Validation leads to a re-delegation with a region. Business leads to 1 escalation, for biomass. Permission leads to 1 alert, for fusion, with scope `research:restricted` |
| C17 | When partial results exist, the coordinator assesses whether they are enough to proceed without full data, or whether a retry is worth the extra latency (**New**) | `RECOVERY_POLICY` writes the judgment as a rule: proceed when `partialResults` hold at least `SUFFICIENT_SOURCES = 3` sources; otherwise, re-delegate once with the narrower query. Print both partial cases with their count, the rule's verdict and the action taken. For tidal, also print the re-delegation's `finished - started`: the latency the retry cost | Geothermal: 3 ≥ 3, so it proceeds. There is no second Agent call, and its coverage is `limited` with 3 sources. Tidal: 1 < 3, so it is re-delegated. The narrower query returns all 3 sources, and its coverage is `well_supported`. The re-delegation typically adds a few seconds |
| C15 | The coordinator is the intelligent recovery decision-maker: structured error context lets it make informed choices instead of applying one rule to every failure. That avoids both silent suppression (ignoring failures) and workflow termination (killing the pipeline over one failure) (**New**) | Two anti-pattern coordinators, offline and used only here, run over the 7 first-round reports of the live run:<br>• `suppress(reports)` keeps the `success` reports and drops the rest without a trace.<br>• `terminate(reports)` stops at the first report that isn't `success`, in `TOPICS` order, and delivers no brief.<br>Print one row per policy, the live coordinator included: topics with findings, topics annotated as unavailable, and topics missing from the brief | `suppress`: 2 with findings (solar, wind), 0 annotated, 5 missing. `terminate`: it stops at geothermal, so 0, 0 and 7. The live coordinator: 5 with findings (solar, wind, geothermal, tidal, hydropower), 2 annotated (biomass, fusion) and 0 missing |
| C18 | Coverage annotations in the synthesis output: each topic area with its data-quality status (well-supported, limited with a reason, or unavailable with a reason), so the topics of failed subagents are named, never silently omitted (**Builds on** `02-revised-Multi-Agent-Orchestration.md` C14) | `BRIEF_SCHEMA` (code above) requires `coverage`: one entry per topic with `status` (enum `well_supported`, `limited`, `unavailable`), `reason` and `sources_used`. `check_coverage(brief, state)` checks five things:<br>• every topic has exactly one entry;<br>• each status matches `EXPECTED`;<br>• no `reason` is empty;<br>• `sources_used` equals the number of distinct sources the reports returned for that topic, in `results` or `partialResults`;<br>• every `source_ids` value in the findings came from a report.<br>New compared with 01-02 C14: there the coordinator rated coverage to decide what to re-delegate; here the rating is part of the delivered brief, and each gap says what failed | 7 entries: solar, wind, tidal and hydropower `well_supported` with 3 sources each, geothermal `limited` with 3, and biomass and fusion `unavailable` with 0. No invented source id: in particular, no `GEO-4` or `GEO-5`, which never arrived |
| C20 | The coverage annotations are a dedicated section of the synthesis output, separate from the findings (**New**) | `coverage` is its own array in `BRIEF_SCHEMA`, next to `sections`. `render_brief(brief)` prints the findings first, then a `Coverage` section with one line per topic: status, sources used and reason. No finding carries a status, and no coverage line carries a claim | Code review: `sections` and `coverage` are separate required keys. The rendered brief ends with a 7-line `Coverage` section that lists biomass and fusion, which have no findings |
| C19 | Without annotations, a gap looks as if the topic wasn't relevant rather than as if its source was unavailable. Each gap becomes a documented limitation that readers can see, which is far better than silently omitting topics (**New**) | Print the brief twice: `render_brief(brief)` and `render_brief(brief, with_coverage=False)`. Then print each `limited` or `unavailable` reason next to the `failureType` and `description` of the report that caused it | Without the section, biomass and fusion just aren't there, and geothermal's 3 findings look complete. With it, each reason names its cause: typically the $4,800 licence and the escalation for biomass, the missing `research:restricted` scope and the alert for fusion, and the timeout for geothermal |

### Terminal commands (for the later tutorial)

None: every concept in this topic is a programming concept.

### Already covered by earlier POCs

| ID | Concept | Covered in | Check when reused |
|---|---|---|---|
| C3 | Generic error messages such as "search unavailable" prevent all informed recovery | `02-revised-Structured-Error-Responses.md` C8, C3 | No report is a bare message. `validate_report()` rejects one without `status`, `shouldRetry` and, on failure, all 5 error fields. The researcher's prompt forbids describing an error in its own words. And `search_once()` lets no exception escape, so the SDK never passes on a raw exception message instead of a report |
| C4 | The four failure types map to different recovery strategies: transient = retry, validation = fix the input, business = escalate, permission = an authorization change | `02-revised-Structured-Error-Responses.md` C5 | `RECOVERY_POLICY` keeps the `RECOVERY` mapping of 02-02, now applied by a coordinator (C16) |
