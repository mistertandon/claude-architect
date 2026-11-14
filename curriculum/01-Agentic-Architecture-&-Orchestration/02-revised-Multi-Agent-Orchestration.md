# Multi-Agent Orchestration: Revised POC Requirements (6 steps → 2 POCs, Claude Agent SDK)

> **Source:** `02-raw-Multi-Agent-Orchestration.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Agentic Architecture & Orchestration → Multi-Agent Orchestration · **Build with:** Claude Agent SDK for Python (`claude_agent_sdk`)

---

## 1. Verdict: 2 POCs

The 6 raw steps are not 6 separate concepts. They build **one coordinator program**: steps 1–3 set up one delegation round, steps 4–5 are one feedback loop around that round, and step 6 tests the result. What you need to learn splits into two mental models:

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: Hub and spokes, one delegation round** | **Who does what, and who knows what:** the coordinator decomposes the topic, briefs two isolated subagents through the `Agent` tool and aggregates their reports; a subagent knows only the prompt the coordinator writes for it | 1, 2, 3, 4 (aggregation) |
| **POC 2: The coordinator's refinement loop** | **The control flow:** assess coverage against the whole topic, re-delegate only the gaps with targeted prompts, and stop at 100% coverage or at the iteration cap; then run the renewable-energy test | 4 (coverage), 5, 6 |

**What changes with the Agent SDK:** the SDK supplies the spokes. You declare each subagent as an `AgentDefinition` (a description, its own system prompt, its tools) and pass them with `agents=`. The coordinator Claude spawns a subagent by calling the built-in `Agent` tool. The SDK runs that subagent in a fresh context that holds only the Agent call's `prompt`, runs its tool calls, and returns its final report as the Agent call's tool result. You write no subagent loop and no message passing. So the POCs teach the raw concepts by **making the delegation visible** in the message stream (POC 1: which subagent was called, with exactly which prompt, and which tools it used, linked by `parent_tool_use_id`) and by **writing the refinement loop in plain Python** around coordinator calls (POC 2), so the iteration cap and the coverage threshold are deterministic. Two things can only be observed, not coded: isolation itself (POC 1 proves it with a demo), and a subagent's own reasoning (by default the stream carries a subagent's tool calls but not its text; its report arrives only as the Agent tool result). Exam material and older SDKs call the spawning tool **Task**. `tool_use` blocks now name it `Agent` (the `system:init` tool list still says `Task`), so match both names.

- **Why not 1 POC:** one round already streams a decomposition, two subagents and their tool calls. Its isolation and context checks must pass before a loop repeats it. Otherwise a gap could come from the decomposition, the context passing or the loop, and you couldn't tell which.
- **Why not 3 or more:** steps 1–3 can't run apart (a coordinator without spokes produces nothing, and decomposition alone is one call), step 4's coverage assessment exists only to drive step 5's re-delegation, and step 6 only tests steps 1–5.

**Applies to both POCs:** Python 3.10+, `pip install claude-agent-sdk` (a recent 0.2.x; it bundles the Claude Code binary), `ANTHROPIC_API_KEY` set in the environment (never hard-coded), mock data only, and beginner-friendly code (small, commented scripts). The two mock tools in `research_setup.py` follow `tools.py` from `01-revised-Agentic-Loops.md` (C2–C3: `@tool` with a full JSON Schema, async handlers that return `{"content": [...]}`, and `is_error` instead of raising). They are bundled with `create_sdk_mcp_server(name="research", version="1.0.0", tools=[web_search, read_document])`, so their full names are `mcp__research__web_search` and `mcp__research__read_document`. Their data is a made-up "Helios Institute 2026 Renewables Review", so Claude can't answer from memory, and each figure in a report shows which subagent fetched it:

| Category | `web_search` matches (case-insensitive substring) | Doc id | `web_search` fact | `read_document` fact |
|---|---|---|---|---|
| solar | solar, photovoltaic | `HX-SOL-7` | solar capacity grew 31% in 2025 | utility-scale cost fell to $27.40/MWh |
| wind | wind | `HX-WND-2` | offshore wind added 19.6 GW in 2025 | the average capacity factor reached 41.3% |
| hydropower | hydropower, hydroelectric, hydro power | `HX-HYD-5` | hydropower supplied 14.2% of electricity | pumped-storage capacity rose to 212 GW |
| geothermal | geothermal | `HX-GEO-3` | geothermal output rose 8.7% | enhanced-geothermal pilot wells reached 245 °C |
| tidal | tidal, wave, ocean, marine | `HX-TID-4` | tidal stream capacity reached 1.9 GW | the Kestrel Strait array ran at a 37.5% capacity factor |
| biomass | biomass, bioenergy, biofuel, biogas | `HX-BIO-6` | bioenergy supplied 9.4% of industrial heat | waste feedstocks made up 63% of supply |
| fusion | fusion | `HX-FUS-1` | the Aurora-3 test reactor held plasma for 412 seconds | a 140 MW grid pilot is planned for 2034 |

`web_search(query)` returns one line per matching category, `Helios Review 2026, <category>: <fact>. Full analysis: document <doc id>.`, or `No Helios results for '<query>'.` when nothing matches. `read_document(doc_id)` matches the id exactly (trimmed, case-insensitive) and returns `<doc id> (<category>): <fact>.`; for any other id it returns an `is_error: True` result, `Unknown document id '<id>'. Only ids that appear in web_search results exist.` Hydropower is in the corpus only because a full-breadth decomposition usually adds it. `REQUIRED = ["solar", "wind", "geothermal", "tidal", "biomass", "fusion"]`, and `missing_categories(texts)` returns, in `REQUIRED` order, the categories that no text matches by the aliases above.

Every coordinator call gets its options from one function in `research_setup.py`:

```python
COORDINATOR_PROMPT = (
    "You are the coordinator of a research team: the hub of a hub-and-spoke system. You own three jobs. "
    "1) Decompose: split a topic into 5 to 8 distinct subtopics that cover its full breadth, including "
    "mainstream, niche, and emerging or experimental categories. Each subtopic is one category of the topic "
    "itself, never a cross-cutting theme such as policy, cost or history. "
    "2) Delegate: never research yourself. The web-searcher subagent finds sources; the doc-analyst subagent "
    "reads the documents they name. Subagents share no memory with you or with each other, so every Agent "
    "prompt must state the research goal, the exact subtopic names, and every fact from earlier reports that "
    "the subagent needs, such as document ids. "
    "3) Aggregate: combine both reports into one section per subtopic, and judge coverage honestly."
)

AGENTS = {
    "web-searcher": AgentDefinition(
        description="Finds Helios Institute sources for a list of subtopics. Use it before doc-analyst.",
        prompt=("You are a web-search specialist. Call web_search once for each subtopic in your task. "
                "For each subtopic, report the key figure and the document id from the result. "
                "Use only what the tool returns; if a search finds nothing, say so."),
        tools=["mcp__research__web_search"],   # its only tool: it can't read documents or spawn agents
        model="inherit",                        # same model as the coordinator
        maxTurns=15,                            # per-subagent safety cap (camelCase, as in the SDK)
    ),
    "doc-analyst": AgentDefinition(
        description="Reads Helios documents by exact document id and extracts their key figures.",
        prompt=("You are a document analyst. Read each document id in your task with read_document and "
                "report its key figures per subtopic. You cannot search. If your task gives no document "
                "id, say which ids you need instead of guessing."),
        tools=["mcp__research__read_document"],
        model="inherit",
        maxTurns=15,
    ),
}

def build_coordinator_options(schema=None, with_agents=True):
    # with_agents=False (decompose, assess_coverage): no tools and no subagents, the coordinator only thinks
    return ClaudeAgentOptions(
        model="claude-opus-5-5",
        system_prompt=COORDINATOR_PROMPT,          # the hub's role (C4); subagents never see it
        output_format={"type": "json_schema", "schema": schema} if schema else None,  # JSON in ResultMessage.structured_output (C3)
        tools=["Agent"] if with_agents else [],    # the only built-in tool is Agent, which spawns subagents (C9)
        agents=AGENTS if with_agents else None,    # the two spokes (C9)
        mcp_servers={"research": research_server} if with_agents else {},  # the mock tools, used by the subagents
        allowed_tools=["Agent", "mcp__research__web_search", "mcp__research__read_document"],  # no permission prompts
        disallowed_tools=["Agent(fork)"],          # no forks: a fork inherits the whole conversation (E1)
        setting_sources=[],                        # ignore ~/.claude and project settings, CLAUDE.md and hooks
        env={
            "ENABLE_TOOL_SEARCH": "false",                   # load tool schemas upfront: no ToolSearch calls
            "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",     # the coordinator waits for every report (E2)
            "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",  # no general-purpose fallback: only our spokes (E3)
        },
        max_turns=20,                              # safety cap per coordinator call (01 C16)
    )
```

---

## 2. Concepts and POC requirements

All 20 concepts in the raw file (C1–C20) are covered: all 20 are new or build on earlier POCs and are taught below, and none was already covered by an earlier revised file (see the end of this section).
Previous revised files checked: `01-revised-Agentic-Loops.md`.
Raw step → concepts: **1** → C1–C4 · **2** → C5–C8 · **3** → C9–C12 · **4** → C13–C15 · **5** → C16–C18 · **6** → C19–C20 (its "Why" repeats C7).
Rows marked **E** are extras that are not in the raw file. Without them, the POC breaks or gives misleading results.

### POC 1: Hub and spokes, one delegation round

**Build:** `research_setup.py` (the mock corpus and tools, `REQUIRED` and `missing_categories()`, `COORDINATOR_PROMPT`, `AGENTS` and `build_coordinator_options()`; POC 2 reuses it, and `python research_setup.py` runs an offline self-check), `coordinator.py` and `poc1_isolation_demo.py`. `coordinator.py` defines:
- `async def run_coordinator(prompt, schema=None, with_agents=True)`, which streams one `query()` inside `try/except` (a single-shot `query()` raises after yielding an error result) and prints the hub-and-spoke log. It returns `{"output", "agent_calls", "research_calls", "subtype"}`: `output` is `ResultMessage.structured_output` when a schema is given and `.result` otherwise; each `agent_calls` item is `{"id", "subagent_type", "prompt", "report"}`; each `research_calls` item is `{"name", "input", "parent_tool_use_id"}`. It raises if the result isn't `success`.
- `decompose(topic)`, `delegate(topic, subtopics, gap_notes=None)`, `check_context(agent_calls, topic, subtopics, doc_ids=None)` and `research_once(topic, subtopics=None)`.

No coverage scoring and no loop here: those are POC 2.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C9 | Two subagents: web search and document analysis (**New**) | In `research_setup.py`, define `AGENTS` (code above): two `AgentDefinition`s, each with a `description` that says when to use it, its own system prompt in `prompt`, a one-tool `tools` list, `model="inherit"` and `maxTurns=15`. The coordinator gets `tools=["Agent"]`, `"Agent"` in `allowed_tools`, and `agents=AGENTS`: subagents are spawned only through the `Agent` tool. In the stream, a spawn is a `ToolUseBlock` whose `name` is `"Agent"` (or `"Task"` on older versions); read `input["subagent_type"]` and `input["prompt"]` | One round shows two Agent calls, `web-searcher` then `doc-analyst`. Every tool call inside `web-searcher` is `mcp__research__web_search`, and every one inside `doc-analyst` is `mcp__research__read_document` |
| C4 | The coordinator's system prompt defines its role as the orchestrating hub (**New**) | Every coordinator call (`decompose()`, `delegate()`, POC 2's `assess_coverage()`) uses `system_prompt=COORDINATOR_PROMPT` (code above): the hub, its three jobs, its two subagents, and the rule that every Agent prompt carries its own context. A subagent's system prompt is its `AgentDefinition.prompt`; it never sees the coordinator's | Code review: one `COORDINATOR_PROMPT` is used by every coordinator call, and neither subagent prompt mentions decomposing or summarizing the whole topic |
| C1 | Hub-and-spoke: the coordinator is the central hub (**New**) | `run_coordinator()` prints the flow from the stream. The coordinator's Agent calls (`parent_tool_use_id is None`) print as `[coordinator -> <subagent>] prompt: ...`. Each subagent's tool calls and results (messages whose `parent_tool_use_id` is the spawning Agent call's `id`) print indented, labeled with that subagent's name. Each report prints as `[<subagent> -> coordinator] report: ...`, taken from the `ToolResultBlock` whose `tool_use_id` is the Agent call's `id` (join its text parts). Subagents have no `Agent` tool, so they can't spawn agents or message each other: everything goes through the hub | Every Agent call has `parent_tool_use_id is None`. Every `mcp__research__*` call has a `parent_tool_use_id` equal to an Agent call's `id`, so the coordinator never researched itself. Every report's `tool_use_id` equals its Agent call's `id` |
| C5 | Decomposition into at least 5 distinct subtopics covering the full breadth (**New**) | `decompose(topic)` calls `run_coordinator(f"Decompose this research topic into subtopics. Do not delegate yet. Topic: {topic}", SUBTOPICS_SCHEMA, with_agents=False)`, with `SUBTOPICS_SCHEMA = {"type": "object", "properties": {"subtopics": {"type": "array", "items": {"type": "string"}}}, "required": ["subtopics"]}`. The breadth rule lives in `COORDINATOR_PROMPT`; Python then checks it deterministically and raises `ValueError` on fewer than 5 subtopics or on duplicates (case-insensitive) | `decompose("renewable energy technologies")` and `decompose("public transport systems")` each return 5–8 distinct names, and neither run makes an Agent or research call |
| C8 | Renewable energy needs solar, wind, geothermal, tidal, biomass and fusion at minimum (**New**) | Print `missing_categories(subtopics)` for `decompose("renewable energy technologies")`. Never list the six categories in a prompt: the coordinator has to find the breadth itself | `[]`, typically with 6–7 subtopics (hydropower is often added). If a category is missing (fusion is the usual one), reword the breadth rule in `COORDINATOR_PROMPT`, never the subagents (C7) |
| C6 | Narrow decomposition is an exam failure pattern (**New**) | In the offline self-check of `research_setup.py`, print `missing_categories(["solar power", "wind power"])`, the decomposition that assigns only solar and wind. POC 2 runs this narrow list live (C7) | `['geothermal', 'tidal', 'biomass', 'fusion']`: 4 of the 6 categories are lost before any subagent runs |
| C2 | The coordinator owns decomposition, subagent selection and result aggregation, not the subagents (**New**) | `delegate(topic, subtopics, gap_notes=None)` runs `run_coordinator()` with agents on, `SECTIONS_SCHEMA` (C13) and this prompt, one line each: `Research goal: a sourced overview of "{topic}" with key figures from Helios Institute sources.` · `Subtopics for this round (delegate only these, using these exact names): {json.dumps(subtopics)}` · in a follow-up round, `Fix only these gaps:` plus one `- {subtopic}: {reason}` line per gap · `Delegate with one Agent call that finds sources for all of these subtopics, then one Agent call that reads the documents those sources name. Return one section per subtopic.` The prompt names no subagent: Claude picks each one from its `description`, as it picks tools (`01-revised-Agentic-Loops.md` C4), and writes their prompts itself | The subtopics named in the Agent prompts are exactly the `subtopics` argument, and `web-searcher`'s queries cover only those. The sections come from the coordinator's `structured_output`, never from a subagent |
| C11 | Explicit context passing: every prompt carries the full assigned subtopic, the research goal and context from prior agents (**New**) | `check_context(agent_calls, topic, subtopics, doc_ids=None)` prints ✅/❌ per Agent call for the topic phrase (case-insensitive), each subtopic name, and (for `doc-analyst`) each doc id. By default `doc_ids` is `re.findall(r"HX-[A-Z]{3}-\d", <web-searcher's report>)`: context that only a prior agent produced, which the doc-analyst can't get any other way | For `research_once("renewable energy technologies")`, every check is ✅, and the `doc-analyst` prompt contains every doc id from the `web-searcher` report |
| C13 | Aggregate the results from both subagents (**Builds on** `01-revised-Agentic-Loops.md` C10) | Each report reaches the coordinator as the `ToolResultBlock` of its Agent call, an ordinary tool round trip (01 C10). New: the coordinator merges both reports per subtopic. `delegate()` passes `SECTIONS_SCHEMA`: an object with a required `sections` array whose items require `subtopic`, `web_findings` (from `web-searcher`), `document_findings` (from `doc-analyst`) and `sources` (an array of doc ids) | One section per subtopic, each with non-empty `web_findings` and `document_findings` and its doc id in `sources`. The findings typically quote mock-only figures, such as fusion's `412 seconds` (web) and `140 MW` (document) |
| C3 | Coordinator function: a topic string in, a structured research report out (**Builds on** `01-revised-Agentic-Loops.md` C13) | `research_once(topic, subtopics=None)` sets `subtopics = subtopics or await decompose(topic)`, calls `delegate()`, and returns `{"topic", "subtopics", "sections", "agent_calls"}`. New: the report comes from `ResultMessage.structured_output` (set by `output_format`, present only on `success`), not from the `.result` text of 01 C13 | `json.dumps(report)` works, and `research_once("renewable energy technologies")` returns 5 or more sections, each with the four keys |
| C10 | Subagent isolation: no shared memory, no inherited context (**New**) | `poc1_isolation_demo.py`, thin run: `run_coordinator()` with agents on and the prompt `Controlled isolation test. Your notes say the Helios document on tidal energy is HX-TID-4. Call the doc-analyst subagent once and pass it exactly the text between <<< and >>>, adding nothing: <<<Analyse the Helios document on tidal energy and report its key figures.>>> Then reply with its report unchanged.` Print the Agent call's `prompt` and its report | The coordinator knew `HX-TID-4`, but the printed Agent prompt doesn't contain it (if it does, rerun: the test needs the thin prompt). The report has no `37.5%` and typically asks for a document id: the subagent never saw the coordinator's conversation |
| C12 | When a subagent gives poor results, check the coordinator's context first, not the subagent (**New**) | Full run: the same wrapper with `<<<Research goal: a sourced overview of renewable energy technologies. Subtopic: tidal energy. Context from the web-searcher: the Helios entry for tidal energy is document HX-TID-4. Read it and report its key figures.>>>`. Run `check_context(calls, "renewable energy technologies", ["tidal energy"], doc_ids=["HX-TID-4"])` on both runs, then print which run succeeded | Thin run: ❌ for the goal and the doc id. Full run: all ✅, `read_document` is called with `HX-TID-4` inside `doc-analyst`, and the report contains `37.5%`. The subagent definition never changed, so the fix belonged in the coordinator's prompt |
| E1 | No forks | `disallowed_tools=["Agent(fork)"]` (code above). A fork is a subagent that inherits the coordinator's whole conversation: it would read `HX-TID-4` from the coordinator's context, so C10's thin run would succeed and hide the isolation lesson | No Agent call has `subagent_type` `fork` |
| E2 | Wait for every subagent | `env` sets `"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"`. Without it, subagents start in the background by default: the Agent call returns at once with `async_launched`, and the report arrives in a later turn, so the per-call report checks (C1, C11, C13) break | Every Agent `ToolResultBlock` holds the subagent's report, never an `async_launched` status |
| E3 | Only our two subagents | `env` sets `"CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1"`. Otherwise Claude can delegate to the built-in `general-purpose` subagent, which bypasses both spokes and their one-tool limits | Every `subagent_type` is `web-searcher` or `doc-analyst` |
| E4 | `StructuredOutput` is not a research step | With `output_format`, Claude Code adds a `StructuredOutput` tool that the coordinator calls to return its JSON (again if the JSON fails the schema). `run_coordinator()` leaves `ToolUseBlock`s named `StructuredOutput`, and the results with their `tool_use_id`, out of the log and the call lists. It reads data only from `ResultMessage.structured_output`, and raises on `error_max_structured_output_retries` | The log shows no `StructuredOutput` step, and a `decompose()` run lists zero tool calls |

### POC 2: The coordinator's refinement loop

**Build:** `poc2_refinement.py`, reusing `coordinator.py` and `research_setup.py`. It defines:
- `COVERAGE_THRESHOLD = 100` and `MAX_ITERATIONS = 3`;
- `async def assess_coverage(topic, sections, must_cover=None) -> list[dict]`, `def coverage_percent(coverage) -> int` and `def merge_sections(report_sections, new_sections)`;
- `async def research(topic, max_iterations=MAX_ITERATIONS, subtopics=None, must_cover=None)`, which returns `{"topic", "sections", "coverage", "coverage_percent", "iterations", "complete", "history"}`. Each `history` item is `{"iteration", "delegated", "agent_calls", "coverage_percent", "gaps"}`. Passing `subtopics` skips `decompose()`, so a test can play a coordinator that decomposed narrowly.

The script runs three tests on `TOPIC = "renewable energy technologies"`:
- **narrow:** `subtopics=["solar power", "wind power"]`, `must_cover=REQUIRED`;
- **capped:** the same, with `max_iterations=1`;
- **full:** `must_cover=REQUIRED`, with a real decomposition.

Expected percentages: 2 of 6 categories well covered is `round(100 * 2 / 6)` = 33; if the coordinator also lists hydropower, it is `round(100 * 2 / 7)` = 29.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C14 | Coverage evaluation against the full breadth of the original topic: well covered, partially covered or missing (**New**) | `assess_coverage()` calls `run_coordinator(prompt, COVERAGE_SCHEMA, with_agents=False)`. `COVERAGE_SCHEMA` is an object with a required `coverage` array whose items require `subtopic`, `status` (enum `well_covered`, `partial`, `missing`) and `reason`. Prompt: `Topic: {topic}. Must cover at least: {must_cover}. Report sections so far: {json.dumps(sections)}. List every category this topic needs (each must-cover item plus any other major category of the topic) and rate each one: well_covered = a section with web findings, document findings and a source id; partial = a section missing one of these; missing = no section. Give a one-line reason for each.` `coverage_percent()` returns `round(100 * <number of well_covered> / len(coverage))`, computed in Python from the statuses, never by parsing prose (`01-revised-Agentic-Loops.md` C7) | Narrow test, iteration 1: the entries for solar and wind are `well_covered`, and those for geothermal, tidal, biomass and fusion are `missing`, although the report has only 2 sections (coverage is judged against the topic, not against the sections). `coverage_percent` is 33 (29 with hydropower) |
| C13 (across rounds) | Aggregation keeps every round's results | `merge_sections()` keys sections by subtopic name (case-insensitive): a re-delegated subtopic's new section replaces its old one, and all other sections are kept | The narrow test's final report keeps solar and wind from iteration 1 and adds the 4 categories from iteration 2: 6 sections (7 with hydropower) |
| C15 | Gaps found by the assessment trigger re-delegation (**New**) | `gaps = [c for c in coverage if c["status"] != "well_covered"]`. The next round calls `delegate(topic, [g["subtopic"] for g in gaps], gap_notes={g["subtopic"]: g["reason"] for g in gaps})`, so each follow-up is a targeted query about one known gap | Narrow test: iteration 2's `delegated` list equals the iteration-1 gap names, and `missing_categories(<iteration 2 delegated>)` is `['solar', 'wind']`: the well-covered subtopics are not researched again |
| C16 | Iterative refinement loop: check coverage, find gaps, send targeted follow-ups, re-evaluate (**New**) | `research()` decomposes once (unless `subtopics` is given). Then, for each iteration from 1 to `max_iterations`, it runs `delegate()` → `merge_sections()` → `assess_coverage()`, appends a `history` item, and prints `iteration {n}: delegated {k} -> coverage {p}% -> gaps {names}`. It then stops (C17) or re-delegates the gaps (C15) | Narrow test: `[h["coverage_percent"] for h in history]` is `[33, 100]` (`[29, 100]` with hydropower), `iterations == 2` and `complete is True` |
| C11 (in loop) | Targeted follow-ups still carry their full context | Run `check_context()` on every iteration's `agent_calls`. A follow-up round's prompts must carry the research goal, the gap subtopics, the gap reasons, and that round's new doc ids | Narrow test: every check is ✅ in iterations 1 and 2 |
| C17 | Stop when the coverage threshold is met or the maximum iteration count is reached (**Builds on** `01-revised-Agentic-Loops.md` C16, C17) | Primary stop: `coverage_percent >= COVERAGE_THRESHOLD`, which sets `complete=True`. Fallback: after `max_iterations`, call `logging.warning("Coverage %d%% after %d iteration(s); gaps: %s", ...)`, set `complete=False` and still return the partial report. New compared with 01 C16–C17: this cap counts the coordinator's delegation rounds, not the SDK's tool turns, and a quality threshold is the primary stop | Capped test: one `WARNING`, `iterations == 1`, `complete is False`, `coverage_percent` 33 (29 with hydropower). The narrow and full tests stop at the threshold, below the cap |
| C7 | Incomplete output traces back to the coordinator's decomposition, the diagnosis the exam expects (**New**) | After the narrow test, print `missing_categories([c["prompt"] for c in history[0]["agent_calls"]])` and the iteration-1 statuses of solar and wind, then the line `Root cause: the coordinator's decomposition (narrow), not the subagents` | `['geothermal', 'tidal', 'biomass', 'fusion']`: no iteration-1 Agent prompt mentions those 4 categories, while solar and wind are `well_covered`. The subagents did everything they were asked; the categories were never delegated (C6 live) |
| C18 | Single-shot delegation is not enough: evaluating and re-delegating is what makes a coordinator rather than a dispatcher (**New**) | After the narrow test, print `history[0]["coverage_percent"]`, which is what a single-shot dispatcher such as `research_once()` would have returned, next to the final `coverage_percent` | Dispatcher: 33 (29 with hydropower), covering 2 categories. Coordinator: 100, covering all 6 |
| C19 | Test with "renewable energy technologies": the final report has substantive sections on solar, wind, geothermal, tidal, biomass and fusion (**New**) | Full test: assert `missing_categories([s["subtopic"] for s in sections]) == []`. For each `REQUIRED` category, assert that a section whose `subtopic` matches it has non-empty `web_findings` and `document_findings` and that category's doc id in `sources`: `HX-SOL-7`, `HX-WND-2`, `HX-GEO-3`, `HX-TID-4`, `HX-BIO-6`, `HX-FUS-1` | All six asserts pass. The findings typically quote the mock figures, such as wind's `41.3%` and fusion's `412 seconds` |
| C20 | The coverage evaluation shows 100% completeness (**New**) | Full test: assert `coverage_percent == 100` and `complete is True`, and print every coverage entry with its status | Every entry is `well_covered`. `iterations` is typically 1; 2 also passes, if the loop repaired a category the decomposition missed (log it as a decomposition miss, C7) |

### Already covered by earlier POCs

None: every concept in this topic is new or builds on an earlier POC (cited in its row).
