# Subagent Invocation and Context Passing: Revised POC Requirements (6 steps → 2 POCs, Claude Agent SDK)

> **Source:** `03-raw-Subagent-Invocation-and-Context-Passing.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Agentic Architecture & Orchestration → Subagent Invocation and Context Passing · **Build with:** Claude Agent SDK for Python (`claude_agent_sdk`)

---

## 1. Verdict: 2 POCs

The 6 raw steps are not 6 separate concepts. Steps 1–3 build **one research round** whose subagents return findings that keep content and metadata apart. Steps 4–6 build **one pipeline** on top of that round: step 5 tests step 4, and step 6 changes how step 4's inputs are produced. What you need to learn splits into two mental models:

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: Invoking scoped subagents that return content + metadata** | **How a subagent gets spawned and what it hands back:** the `Agent` tool is the hard gate (no tool, no subagents), each spoke has role-scoped tools, and every finding separates its content (`claim`, `analysis`) from its metadata (`source_url`, `document_name`, `page_number`, `confidence`, `retrieved_by`) | 1, 2, 3 (format) |
| **POC 2: Parallel fan-out, metadata-preserving fan-in** | **How context moves between subagents:** spawn both researchers in one response, wait for both, and pass the complete findings to the synthesizer. Then check every claim's attribution, and trace a failure back to the handoff | 3 (failure pattern), 4, 5, 6 |

**What changes with the Agent SDK:** the SDK spawns and runs the subagents. When the coordinator Claude calls the `Agent` tool, the SDK starts that subagent in a fresh context holding only the call's `prompt` and runs its tool calls. The subagent's final message comes back as the Agent call's `ToolResultBlock`. When one coordinator response holds several Agent calls, the SDK runs them for you. So the POCs teach the raw concepts by **checking the message stream**: the `system:init` tool list and the Agent calls show the gate (POC 1), and the Agent calls' `message_id`s and arrival times show parallel spawning (POC 2). They also **parse and check in Python** what crosses each handoff: the JSON findings in each research report, and the exact findings in the synthesizer's Agent prompt. Three things differ from the raw file:
- **The gate.** In the SDK, the hard gate is the session's tool set (`tools`, minus bare-name `disallowed_tools`). `allowed_tools` only pre-approves, and `Agent` needs no approval in `default` mode (E1). The exam's answer is still "`Agent` (or `Task`) must be in `allowedTools`", so the code lists it in both.
- **Structured output from subagents.** The SDK has no per-subagent output schema: `AgentDefinition` has no schema field. Each subagent therefore returns JSON as text, and Python parses and validates it (C8, E2).
- **TypeScript.** The raw file's "TypeScript interface" becomes Python field lists plus a validator.

- **Why not 1 POC:** the attribution checks in POC 2 only mean something once the findings are known to be correct. POC 1 validates every finding against the mock corpus and saves it to `findings.json`. Then, when a claim in POC 2 has no source, the cause is the handoff and not bad research.
- **Why not 3 or more:** step 5 only tests step 4. Step 6 is a change to the same coordinator, and you measure it against POC 1's sequential round. Its "wait for both" part only matters because synthesis comes next. A separate parallel POC would rebuild the pipeline to test one prompt rule.

**Applies to both POCs:** Python 3.10+, `pip install claude-agent-sdk` (a recent 0.2.x; it bundles the Claude Code binary), `ANTHROPIC_API_KEY` set in the environment (never hard-coded), mock data only, and beginner-friendly code (small, commented scripts). The coordinator runs through `run_coordinator()` from `02-revised-Multi-Agent-Orchestration.md` (`coordinator.py`), extended as described in POC 1's Build. The mock tools follow `tools.py` from `01-revised-Agentic-Loops.md` (C2–C3): `@tool` with a full JSON Schema, async handlers that return `{"content": [...]}`, `is_error` instead of raising, and `ToolAnnotations(readOnlyHint=True)`. They live in `attribution_setup.py`, bundled with `create_sdk_mcp_server(name="sources", version="1.0.0", tools=[web_search, list_documents, read_document])`. Their data is a made-up "Tessaly" sodium-ion battery pilot at the made-up utility Kestrel Ridge, so Claude can't answer from memory. Each figure exists in exactly one source and page:

| # | Tool | `document_name` (title) | `source_url` | Page | Text (the figure is in bold) |
|---|---|---|---|---|---|
| 1 | `web_search` | Tessaly Grid Pilot: Year-One Results | `https://example.com/tessaly/year-one-results` | 3 | The Tessaly pilot delivered **48 MWh** of storage at peak demand in 2025. |
| 2 | `web_search` | Sodium-Ion Cost Tracker 2026 | `https://example.org/sodium-ion-cost-tracker-2026` | 2 | Tessaly cells cost **$61** per kWh at pack level. |
| 3 | `web_search` | Kestrel Ridge Utility Newsroom | `https://example.net/kestrel-ridge/news/tessaly-expansion` | 1 | Kestrel Ridge plans a **300 MWh** Tessaly expansion by 2028. |
| 4 | `read_document` | Tessaly Pilot Safety Audit (`tessaly-safety-audit.pdf`) | `https://example.com/library/tessaly-safety-audit.pdf` | 2 | No thermal runaway events were recorded across **1,200** charge cycles. |
| 5 | `read_document` | (same document) | (same) | 5 | Round-trip efficiency averaged **87.4%**. |
| 6 | `read_document` | (same document) | (same) | 7 | Capacity fade was **3.1%** after the first year. |
| 7 | `read_document` | Kestrel Ridge Board Minutes, March 2026 (`kestrel-ridge-board-minutes.pdf`) | `https://example.com/library/kestrel-ridge-board-minutes.pdf` | 4 | The board approved **$42 million** for phase two of the Tessaly deployment. |

- **`web_search(query)`** returns rows 1–3 as a JSON list of `{"title", "url", "page", "snippet"}` when the query contains "tessaly" (case-insensitive). Otherwise it returns `No results for '<query>'.`
- **`list_documents()`** returns both file names with their titles.
- **`read_document(document_name)`** matches the file name exactly (trimmed, case-insensitive). It returns a header line, `Title: <title> · URL: <url>`, then one `[page N] <text>` line per page. The audit also has a figure-free cover page: `[page 1] Scope: independent audit of the Tessaly sodium-ion pilot at Kestrel Ridge.` Any other name returns an `is_error: True` result: `Unknown document '<name>'. Call list_documents first.`

`FACTS` lists the 7 rows as `(figure, source_url, page)`. `KNOWN_SOURCES` is the set of their `(source_url, page)` pairs. `QUESTION = "What is known about the Tessaly sodium-ion grid battery pilot at Kestrel Ridge?"`

Every coordinator call gets its options from `attribution_setup.py`:

```python
CONTENT_FIELDS = ["claim", "analysis"]
METADATA_FIELDS = ["source_url", "document_name", "page_number", "confidence", "retrieved_by"]
SOURCE_TOOLS = ["mcp__sources__web_search", "mcp__sources__list_documents", "mcp__sources__read_document"]

FINDING_FORMAT = (
    'Your final message must be only a JSON object {"findings": [...]}, with no other text. '
    'Each finding has exactly these keys. Content: "claim" (one factual sentence) and "analysis" '
    '(one sentence on why it matters). Metadata: "source_url", "document_name", "page_number" '
    '(an integer), "confidence" ("high", "medium" or "low") and "retrieved_by" (your agent name). '
    "Copy source_url, document_name and page_number exactly from the tool output; never invent them."
)

AGENTS = {
    "web-searcher": AgentDefinition(
        description="Searches the web for sources on a research question. Returns findings with source URLs and titles.",
        prompt=("You are a web-search specialist. Call web_search for the question in your task and report one "
                "finding per search result, using the result's title as document_name and its page as page_number. "
                + FINDING_FORMAT),
        tools=["mcp__sources__web_search"],                                     # search tools only
        model="inherit",
        maxTurns=10,
    ),
    "doc-analyst": AgentDefinition(
        description="Reads the local document library for a research question. Returns analysis with page references.",
        prompt=("You are a document analyst. Call list_documents, read every document with read_document, and report "
                "one finding per page that states a figure, using the document's title as document_name. "
                + FINDING_FORMAT),
        tools=["mcp__sources__list_documents", "mcp__sources__read_document"],  # file-reading tools only
        model="inherit",
        maxTurns=10,
    ),
    "synthesizer": AgentDefinition(
        description="Writes the final sourced brief from the findings in its task. Call it last, after both research reports.",
        prompt=('You are a synthesis writer with no tools: use only the findings in your task. Your final message must be '
                'only a JSON object {"statements": [{"text": "...", "citations": [{"source_url": "...", "page_number": 1}]}]}. '
                "Cite the source_url and page_number of every finding a statement uses, copied exactly from the findings. "
                "If a finding has no source_url or page_number, still write the statement but leave its citations empty: "
                "never invent a citation."),
        tools=[],                                                               # no tools: it reasons only over its task
        model="inherit",
        maxTurns=5,
    ),
}

SEQUENTIAL_RULE = "Call web-searcher first and wait for its report; only then call doc-analyst."
PARALLEL_RULE = ("web-searcher and doc-analyst are independent: call both in one response, with two Agent tool "
                 "calls, and wait for both reports before you go on.")

def coordinator_prompt(parallel):
    return ("You are the coordinator of a research team. Never research yourself: delegate. web-searcher finds web "
            "sources; doc-analyst reads the local document library. "
            + (PARALLEL_RULE if parallel else SEQUENTIAL_RULE)
            + " Subagents start with no context, so give each research subagent the full research question. "
            "Call synthesizer only when your task asks for a brief: call it last, and pass it one JSON object "
            '{"findings": [...]} holding every finding from both reports, unchanged. Never drop, shorten or '
            "summarize any field.")

def build_pipeline_options(parallel=False, agent_tool=True, approve_agent=True):
    return ClaudeAgentOptions(
        model="claude-opus-5-5",
        system_prompt=coordinator_prompt(parallel),           # POC 1: sequential; POC 2: parallel (C15)
        tools=["Agent"] if agent_tool else [],                # the gate: the only built-in tool is Agent (C1)
        agents=AGENTS,                                        # the three spokes
        mcp_servers={"sources": sources_server},              # the mock tools, used by the subagents
        allowed_tools=(["Agent"] if approve_agent else []) + SOURCE_TOOLS,  # exam: Agent in allowedTools (C1, E1)
        disallowed_tools=["Agent(fork)"] + ([] if agent_tool else ["Agent"]),  # no forks (02 E1); gate off: remove Agent
        setting_sources=[],                                   # ignore ~/.claude and project settings, CLAUDE.md and hooks
        env={
            "ENABLE_TOOL_SEARCH": "false",                    # load tool schemas upfront: no ToolSearch calls
            "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",      # the coordinator waits for every report (02 E2, C17)
            "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",   # only our spokes, no general-purpose fallback (02 E3)
        },
        max_turns=20,                                         # safety cap per coordinator call (01 C16)
    )
```

---

## 2. Concepts and POC requirements

All 17 concepts in the raw file (C1–C17) are covered. 13 are new or build on earlier POCs, and are taught below. 4 are already covered by `02-revised-Multi-Agent-Orchestration.md` (see the end of this section).
Previous revised files checked: `01-revised-Agentic-Loops.md`, `02-revised-Multi-Agent-Orchestration.md` (`04-revised-…` and `05-revised-…` are still empty).
Raw step → concepts: **1** → C1–C4 · **2** → C5–C7 · **3** → C8–C10 · **4** → C11–C12 · **5** → C13–C14 · **6** → C15–C17.
Rows marked **E** are extras that are not in the raw file. Without them, the POC breaks or gives misleading results.

### POC 1: Invoking scoped subagents that return content + metadata

**Build:** three pieces of code.

**`attribution_setup.py`:** the mock corpus, `FACTS`, `KNOWN_SOURCES`, `QUESTION`, the three tools and `sources_server`, and the field lists, `FINDING_FORMAT`, `AGENTS`, `coordinator_prompt()` and `build_pipeline_options()` (code above). It also defines `parse_json_object(text)`, `parse_findings(report, retrieved_by)` and `validate_finding(finding, retrieved_by)`. `python attribution_setup.py` runs an offline self-check that makes no API calls.

**An extension to `coordinator.py` from `02-revised-Multi-Agent-Orchestration.md`.** Add these to `run_coordinator()` without breaking 02's behavior:
- an optional `options=None` argument: when it is given, it replaces `build_coordinator_options(schema, with_agents)`;
- three new keys in each `agent_calls` item:
  - `message_id`: the `message_id` of the `AssistantMessage` that holds the Agent call;
  - `started`: when the Agent `ToolUseBlock` arrived, in seconds since the call began (`time.monotonic()`);
  - `finished`: when its `ToolResultBlock` arrived, on the same clock;
- a top-level `init_tools`: `data["tools"]` of the `SystemMessage` whose `subtype` is `"init"`;
- `research_calls` recording every tool call other than `Agent` and `StructuredOutput`, from any MCP server.

02's scripts must still run unchanged.

**`poc1_gate_test.py` and `poc1_research_round.py`.** `poc1_research_round.py` defines `async def research_round(question=QUESTION, parallel=False)`. It calls `run_coordinator(f"Research this question with both research subagents, then reply with one line saying both reports are in. Do not call the synthesizer. Question: {question}", options=build_pipeline_options(parallel))` and returns `{"findings", "agent_calls", "errors"}`. A `__main__` block runs it with `parallel=False` and writes the findings to `findings.json`, the fixed input for POC 2.

No synthesis and no parallel spawning here: those are POC 2.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C1 | `Agent` (formerly `Task`) in the coordinator's `allowedTools` is the hard gate for spawning subagents (**Builds on** `02-revised-Multi-Agent-Orchestration.md` C9) | `build_pipeline_options()` puts `"Agent"` in `tools` and in `allowed_tools`, next to the three source tools, and passes `agents=AGENTS` (code above). New compared with 02 C9: test the gate both ways. `poc1_gate_test.py` runs `run_coordinator(f"Use the web-searcher subagent to research this question, then summarize its report: {QUESTION}", options=...)` twice. The **on** run uses `build_pipeline_options()`. The **off** run uses `build_pipeline_options(agent_tool=False)`, which removes `Agent` from `tools` and `allowed_tools` and adds a bare `"Agent"` deny rule. For each run, print `init_tools`, the number of Agent calls, the number of `research_calls` whose `parent_tool_use_id` is set, and the final text | **on:** `init_tools` contains `"Task"` (the `system:init` name, 02 C9), there is at least 1 Agent call with `subagent_type` `web-searcher`, and its `web_search` call has that Agent call's `id` as `parent_tool_use_id`. **off:** `init_tools` contains neither `"Task"` nor `"Agent"`, there are 0 Agent calls, and 0 calls have a `parent_tool_use_id` |
| C3 | The gate is binary: not optional, and not configurable at runtime (**New**) | In the **off** run, the prompt still names `web-searcher`, and `agents=AGENTS` still defines it. Print the line `Tool set is fixed when query() starts; definitions without the Agent tool can't run` | The off run has 0 Agent calls even though the prompt asks for the subagent by name. Its final text typically says the coordinator can't delegate. If the coordinator researches itself, every `research_calls` item has `parent_tool_use_id is None`. Either way, no subagent ran |
| E1 | In the SDK, the real gate is the tool set; `allowed_tools` only pre-approves | Add a third run, **unlisted**, with `build_pipeline_options(approve_agent=False)`: `Agent` stays in `tools` but is left out of `allowed_tools`. Comment in the code: `Agent` needs no approval in `default` mode, so leaving it out of `allowed_tools` doesn't block it. Only `tools` or a bare `disallowed_tools` entry does. For the exam, answer "it must be in `allowedTools`", and in code, list it in both | The unlisted run still shows at least 1 Agent call with a report. Without this run, a builder who removes `Agent` only from `allowed_tools` would see subagents spawn anyway and wrongly decide that C1 is false |
| C5 | Two subagents with role-specific outputs: web search returns source URLs and titles, document analysis returns page references (**Builds on** `02-revised-Multi-Agent-Orchestration.md` C9) | Define `web-searcher` and `doc-analyst` in `AGENTS` (code above). New compared with 02 C9: their prompts say which metadata each one must copy from its tools. `web-searcher` copies the result's `url`, `title` and `page`. `doc-analyst` copies the document's URL, title and `[page N]` marker. Run `research_round()` with `parallel=False` | Exactly 2 Agent calls: `web-searcher` first, then `doc-analyst`, with different `message_id`s (two responses, as `SEQUENTIAL_RULE` says). No `synthesizer` call. Inside `web-searcher`, the only tool call is `web_search`. Inside `doc-analyst`, the calls are `list_documents` and `read_document` |
| C8 | A structured format that separates content (`claim`, `analysis`) from metadata (`source_url`, `document_name`, `page_number`, `confidence`, `retrieved_by`) (**New**) | Both research prompts end with `FINDING_FORMAT`. `CONTENT_FIELDS` and `METADATA_FIELDS` are the Python version of the raw file's TypeScript `Finding` interface. `validate_finding(finding, retrieved_by)` returns a list of errors, empty if the finding is valid. It checks that all 7 keys are present and nothing else; that `claim`, `analysis`, `source_url` and `document_name` are non-empty strings; that `page_number` is an `int` ≥ 1; that `confidence` is one of `high`, `medium`, `low`; that `retrieved_by` equals the agent that produced the report; and that `(source_url, page_number)` is in `KNOWN_SOURCES`, so invented metadata is caught. `research_round()` runs `parse_findings()` on each report, gathers every error in `errors`, and prints each finding as two lines, `content: ...` and `metadata: ...` | The offline self-check runs the validator on a valid sample finding and gets `[]`. A sample without `page_number` gives an error naming `page_number`, and a sample with an invented URL gives a `KNOWN_SOURCES` error. In the live round, `errors == []`, there are 3 `web-searcher` findings and 4 `doc-analyst` findings (7 in all, no finding for the cover page), and each `FACTS` figure (commas removed) appears in the `claim` of the finding with its `(source_url, page)` pair, typically 7 of 7 |
| E2 | A subagent's report is text: parse the first JSON object | The Agent `ToolResultBlock` joins the subagent's final message with a trailer such as `agentId: ...`, and Claude may wrap the JSON in a code fence. `parse_json_object(text)` therefore calls `json.JSONDecoder().raw_decode(text[text.index("{"):])` and ignores whatever follows. `parse_findings(report, retrieved_by)` returns `parse_json_object(report)["findings"]` and raises `ValueError` if there is no JSON object or no `findings` list | The self-check parses ``'```json\n{"findings": []}\n```\nagentId: a1b2'`` to `[]`, and a report with no `{` raises `ValueError` |

### POC 2: Parallel fan-out, metadata-preserving fan-in

**Build:** three files, reusing `attribution_setup.py`, `coordinator.py` and `research_round()`.

**`attribution_check.py`** defines six helpers:
- `strip_metadata(findings)`: returns each finding with only `CONTENT_FIELDS`;
- `check_metadata_passed(agent_prompt, findings)`: parses the prompt's JSON object with `parse_json_object()`, matches each finding by its exact `claim`, prints ✅/❌ for each of its `METADATA_FIELDS`, and returns `(passed, total)`;
- `parse_statements(report)`: returns `parse_json_object(report)["statements"]`;
- `verify_attribution(statements, findings)`: returns `{"statements", "orphaned", "invalid", "cited"}`. `orphaned` is the statements with no citations, `invalid` is the citations whose `(source_url, page_number)` pair isn't in the findings, and `cited` is the set of valid pairs;
- `diagnose(agent_prompt, findings, attribution)`: prints one root-cause line (C14);
- `delegation_timing(agent_calls, names=("web-searcher", "doc-analyst"))`: returns `{"responses", "overlap", "delegation_seconds", "durations"}`:
  - `responses` is the number of distinct `message_id`s among those Agent calls;
  - `overlap` is True when each call started before the other finished;
  - `delegation_seconds` is `max(finished) - min(started)`;
  - `durations` maps each call to `finished - started`.

**`poc2_handoff_test.py`** reads `findings.json` from POC 1 and runs two controlled handoffs (**full** and **stripped**). Both use `run_coordinator()` with `build_pipeline_options(parallel=True)` and this prompt: `Controlled handoff test. Call the synthesizer subagent once and pass it exactly the text between <<< and >>>, adding nothing: <<<Write a sourced brief answering the question below from these findings. Question: {QUESTION} Findings: {payload}>>> Then reply with its report unchanged.` This is the same wrapper as 02 C10. The **full** payload is `json.dumps({"findings": findings})`. The **stripped** payload is `json.dumps({"findings": strip_metadata(findings)})`.

**`poc2_pipeline.py`** defines `async def run_pipeline(question=QUESTION)`, which returns `{"findings", "statements", "agent_calls", "timing", "attribution"}`. It runs `run_coordinator(f"Write a sourced brief answering: {question}", options=build_pipeline_options(parallel=True))`, parses the findings from both research reports, and parses the statements from the synthesizer's report. The script first runs `research_round()` once with `parallel=False` and once with `parallel=True` (C16), then runs `run_pipeline()`.

With POC 1's 7 findings, a full handoff carries 7 × 5 = 35 metadata values, and a stripped one carries 0.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C11 | Pass complete structured results from both subagents to the synthesizer, preserving all metadata (**Builds on** `02-revised-Multi-Agent-Orchestration.md` C11) | Full handoff run. Pass the synthesizer the complete findings array as JSON, with every content field and every metadata field. New compared with 02 C11: 02 passed context as prose, such as doc ids; here every field of every finding must reach the next agent unchanged. Run `check_metadata_passed(<synthesizer Agent prompt>, findings)` | `(35, 35)`: every ✅. The synthesizer's prompt holds all 7 findings from both `retrieved_by` values |
| C12 | Stripping metadata before the handoff is the root cause of attribution failures, the step the exam targets (**New**) | Stripped handoff run: the same synthesizer, the same findings, and only `CONTENT_FIELDS` passed. Run `check_metadata_passed()` on its synthesizer prompt | `(0, 35)`: every metadata field ❌, although every `claim` matched |
| C9 | The attribution failure pattern: the synthesis produces unsourced claims (**New**) | For the stripped run, print each statement with its citations | The statements still state the mock figures, such as `87.4%` and `$42 million`, so the content survived. Every statement has empty citations, or only citations that `verify_attribution()` marks `invalid`. These are claims without attribution |
| C13 | Verify that every claim in the synthesis is attributed to a specific source with a URL and page number, with no orphaned claims (**New**) | Run `verify_attribution(parse_statements(report), findings)` on both runs, always against the real findings from `findings.json` as ground truth. Print `statements`, `len(orphaned)`, `len(invalid)` and `len(cited)` | Full run: at least 1 statement, `orphaned == []`, `invalid == []`, and every citation has both a `source_url` and a `page_number`. `cited` typically holds all 7 pairs. Stripped run: no statement has a valid citation, typically `len(orphaned) == statements` |
| C14 | When a claim lacks attribution, trace back to whether the metadata was passed; don't blame the synthesis prompt (**Builds on** `02-revised-Multi-Agent-Orchestration.md` C12) | `diagnose()` checks the handoff first. If `orphaned` or `invalid` is non-empty and `check_metadata_passed()` is below 100%, print `Root cause: metadata was not passed to the synthesizer. Fix the coordinator's handoff, not the synthesizer prompt.` If the metadata was fully passed but claims are still orphaned, print `Metadata reached the synthesizer: now review its prompt.` Otherwise, print `All claims attributed.` Assert `AGENTS["synthesizer"]` is the same object in both runs. New compared with 02 C12: the evidence is a field-by-field check of structured metadata, not a missing prose fact | Stripped run: the "Root cause: metadata was not passed" line. Full run: `All claims attributed.` The synthesizer definition never changed between the two runs |
| C10 | Separating content from metadata is the fix (**New**) | Print both runs side by side: the payload keys per finding, the metadata check, and the orphan count. The two payloads differ only in `METADATA_FIELDS`, which is possible only because C8 keeps those fields separate from the content | Keys per finding: full 7, stripped 2. Metadata: 35/35 against 0/35. Orphans: 0 against all. The same claims went in both times; only the metadata decides whether the synthesis can be attributed |
| C15 | Spawn both research subagents in parallel: several Agent tool calls in one coordinator response (**Builds on** `01-revised-Agentic-Loops.md` E1) | Refactor the coordinator by switching `coordinator_prompt(parallel=True)`, which swaps `SEQUENTIAL_RULE` for `PARALLEL_RULE`. Change nothing else. Run `research_round(parallel=True)` and print each Agent call's `message_id`, `started` and `finished`. New compared with 01 E1: the parallel calls are subagent spawns, not custom tools. Each runs a whole subagent loop, so the time saved is large | `delegation_timing()` gives `responses == 1` (both Agent calls share one `message_id`) and `overlap is True` (both subagents were running at the same time). If `responses == 1` but `overlap` is False, the installed version ran them one after the other: record it, because the exam pattern (one response) is still met |
| C16 | Latency awareness: sequential spawning of independent subagents wastes time (**New**) | `poc2_pipeline.py` prints `delegation_seconds` and `durations` for the sequential round and the parallel round, and the ratio between them. Neither research task needs the other's output, which is why they can run in parallel | Sequential: `responses == 2`, `overlap is False`, and `delegation_seconds` is about the sum of both durations. Parallel: `delegation_seconds` is lower, typically close to the slower subagent's duration. Exact times vary from run to run |
| C17 | The coordinator waits for both subagents to finish before it goes on to synthesis (**New**) | In `run_pipeline()`, find the synthesizer's Agent call. The wait is enforced by `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` (02 E2) and asked for by `PARALLEL_RULE` | The synthesizer call's `started` is later than both research calls' `finished`, and its `message_id` differs from theirs (a later response). Its prompt holds findings with both `retrieved_by` values. Both research calls' `delegation_timing()` gives `responses == 1` |
| C11 (in pipeline) | The coordinator itself passes every finding unchanged | Run `check_metadata_passed(<synthesizer Agent prompt>, findings)` on the pipeline run. Here the coordinator wrote the prompt itself, so there is no `<<< >>>` wrapper | Every metadata field ✅ for every finding the two reports returned (35/35 when there are 7) |
| C13 (in pipeline) | End-to-end attribution check | Run `verify_attribution()` and `diagnose()` on the pipeline's statements | `orphaned == []`, `invalid == []`, and `All claims attributed.` Every statement in the final brief cites a source URL and page number |

### Already covered by earlier POCs

| ID | Concept | Covered in | Check when reused |
|---|---|---|---|
| C2 | `Task` was renamed `Agent` in Claude Code v2.1.63, and `Task` still works as an alias | `02-revised-Multi-Agent-Orchestration.md` C9 (and its verdict: match both names) | `run_coordinator()` detects Agent calls with `block.name in ("Agent", "Task")`, and the gate test reads `"Task"` from `init_tools` |
| C4 | `query()` options list `Agent` in `allowedTools` next to the coordinator's other tools, with the subagents under `options.agents` | `02-revised-Multi-Agent-Orchestration.md` C9 | `build_pipeline_options()` has `"Agent"` in `tools` and `allowed_tools`, the three source tools in `allowed_tools`, and `agents=AGENTS` |
| C6 | Each subagent's tools are scoped to its role: search tools only for web search, file-reading tools only for document analysis | `02-revised-Multi-Agent-Orchestration.md` C9 | Every `research_calls` item under `web-searcher` is `mcp__sources__web_search`, every one under `doc-analyst` is `list_documents` or `read_document`, and `synthesizer` makes no tool calls |
| C7 | An `AgentDefinition` has a description, a system prompt and tool restrictions | `02-revised-Multi-Agent-Orchestration.md` C9 | Each of the three `AGENTS` entries sets `description`, `prompt`, `tools`, `model="inherit"` and `maxTurns` |
