# Information Provenance and Multi-Source Synthesis: Revised POC Requirements (5 steps → 2 POCs, Claude Agent SDK)

> **Source:** `06-raw-Information-Provenance-Multi-Source-Synthesis.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Context Management & Reliability → Information Provenance and Multi-Source Synthesis · **Build with:** Claude Agent SDK for Python (`claude_agent_sdk`)

---

## 1. Verdict: 2 POCs

The 5 raw steps are not 5 separate concepts. Steps 1–3 carry **one claim-source mapping from the source to the synthesis**: step 1 defines it, step 2 makes the research subagents produce it, and step 3 keeps it attached through the merge. Steps 4–5 decide **how the merged findings are presented**: conflicting figures side by side with an explanation, and each kind of content in its own format, with the citations unchanged.

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: Provenance from source to synthesis** | **A claim is only as good as its trail:** two research subagents return 13 claim-source mappings (`claim`, `sourceUrl`, `documentName`, `relevantExcerpt`, `publicationDate`), checked word for word against the sources. The same mappings go to two synthesis prompts. A plain one compresses them into prose nobody can trace; the other requires an inline `[Mn]` marker on every claim and a references section | 1, 2, 3 |
| **POC 2: Conflicts and content-appropriate rendering** | **Show both numbers, in the right shape:** a structured synthesis of a fixed set of 13 mappings flags the 2 planted conflicts: a 12% against 18% growth rate published a year apart, and 4.2 against 5.1 GWh of capacity measured with different scope. It keeps both values with their sources and an explanation, and the brief renders financial findings as a table, news as prose and technical findings as a list, with every citation intact | 4, 5 |

**What changes with the Agent SDK:** the SDK runs the subagents and the synthesis sessions. Each subagent's report comes back as its Agent tool result (`02-revised-Multi-Agent-Orchestration.md` C13), and structured output (`output_format`) returns the final brief as validated JSON. What no SDK feature does is keep a claim attached to its source: that depends on the formats the prompts require and on code that checks them. So the POCs check provenance in Python at every hop:
- each mapping against the source text;
- each marker against the mappings;
- each conflict against the planted pairs;
- each rendered line for its citation.

Whether a synthesizer keeps its citations, notices a conflict or classifies a section can only be observed, not coded: the POCs measure it against known answers.

- **Why not 1 POC:** POC 2 starts from known mappings with planted conflicts (`gold_mappings()`), so a missed conflict or a missing citation can only come from the synthesis, not from an analyst who skipped a passage. POC 1 shows that the same mappings come out of live subagents. The two POCs also need different synthesis output: POC 1 compares free-text briefs as a reader sees them, while POC 2 needs structured sections that it can render by type.
- **Why not 3 or more:** steps 1–3 are one pipeline whose product, the mappings, is checked at each hop. Step 4's conflicts and step 5's sections come out of the same structured synthesis, so separating them would run that synthesis twice.

**Applies to both POCs:**
- **Setup:** Python 3.10+, `pip install claude-agent-sdk` (a recent 0.2.x; it bundles the Claude Code binary), and `ANTHROPIC_API_KEY` set in the environment (never hard-coded). Mock data only, and beginner-friendly code (small, commented scripts).
- **Runner:** every call goes through `run_coordinator()` from `02-revised-Multi-Agent-Orchestration.md` (`coordinator.py`), as extended in `03-revised-Subagent-Invocation-and-Context-Passing.md` (`options=`) and `06-revised-Task-Decomposition-Strategies.md`.
- **Parsing:** reports are parsed with `parse_json_object()`, copied from `03-revised-Subagent-Invocation-and-Context-Passing.md` (E2).
- **Tools:** they follow `tools.py` from `01-revised-Agentic-Loops.md` (C2–C3).
- **Data:** a made-up library on sodium-ion grid storage that continues the Tessaly and Kestrel Ridge story of `03-revised-Subagent-Invocation-and-Context-Passing.md`, so Claude can't answer from memory.

**The library** (`DOCUMENTS`) has 6 documents. Each is a context line that states no finding, followed by passages, and each passage is one finding (its id is in brackets):

| # | `sourceUrl` | `documentName` | `publicationDate` | Focus | Context line | Passages |
|---|---|---|---|---|---|---|
| 1 | `https://example.com/helios/market-outlook-2025` | Helios Market Outlook 2025 | 2025-03-10 | market | `This outlook covers grid storage markets.` | [M1] `The sodium-ion grid storage market is growing 12% a year.` · [M2] `Average sodium-ion pack prices fell to $78 per kWh in 2024.` |
| 2 | `https://example.org/kestrel-analytics/storage-brief-2026` | Kestrel Analytics Storage Brief 2026 | 2026-02-20 | market | `This brief summarises storage market data.` | [M3] `The sodium-ion grid storage market is growing 18% a year.` · [M4] `Sodium-ion pack prices averaged $64 per kWh in 2025.` |
| 3 | `https://example.net/tessaly/datasheet-v3` | Tessaly Cell Datasheet v3 | 2026-01-15 | market | `Datasheet for Tessaly sodium-ion cells.` | [M5] `Tessaly cells reach an energy density of 160 Wh/kg.` · [M6] `Rated cycle life is 6,000 cycles at 80% depth of discharge.` · [M7] `The operating temperature range is -20 °C to 55 °C.` |
| 4 | `https://example.org/grid-storage-regulator/bulletin-2026-01` | Grid Storage Regulator Bulletin, January 2026 | 2026-01-28 | policy | `Official bulletin of the Grid Storage Regulator.` | [M8] `On 27 January 2026 the regulator approved sodium-ion systems for frequency-response markets.` · [M9] `Installed sodium-ion grid capacity reached 4.2 GWh at the end of 2025, counting grid-connected systems only.` |
| 5 | `https://example.net/kestrel-ridge/news/2026-02` | Kestrel Ridge Utility Newsroom | 2026-02-05 | policy | `News from Kestrel Ridge Utility.` | [M10] `Kestrel Ridge broke ground on its 300 MWh Tessaly expansion this month.` · [M11] `Installed sodium-ion capacity reached 5.1 GWh at the end of 2025, including behind-the-meter systems.` |
| 6 | `https://example.org/clean-grid/policy-review-2026` | Clean Grid Policy Review 2026 | 2026-03-02 | policy | `Annual review of clean-grid policy.` | [M12] `Three states added sodium-ion storage to their procurement targets this year.` · [M13] `A federal safety standard for sodium-ion systems is expected in late 2026.` |

**The gold mappings** (`gold_mappings()`, POC 2's fixed input): one mapping per passage, in id order. The passage is the `relevantExcerpt`, the document supplies `sourceUrl`, `documentName` and `publicationDate`, and the claim is written in other words:

| Id | Kind (`KIND`) | Gold claim |
|---|---|---|
| M1 | financial | The sodium-ion grid storage market grows 12% a year. |
| M2 | financial | Sodium-ion pack prices fell to $78/kWh in 2024. |
| M3 | financial | The sodium-ion grid storage market grows 18% a year. |
| M4 | financial | Sodium-ion pack prices averaged $64/kWh in 2025. |
| M5 | technical | Tessaly cells store 160 Wh/kg. |
| M6 | technical | Tessaly cells are rated for 6,000 cycles at 80% depth of discharge. |
| M7 | technical | Tessaly cells operate from -20 °C to 55 °C. |
| M8 | news | The regulator approved sodium-ion systems for frequency-response markets on 27 January 2026. |
| M9 | financial | Grid-connected sodium-ion capacity was 4.2 GWh at the end of 2025. |
| M10 | news | Kestrel Ridge broke ground on a 300 MWh Tessaly expansion. |
| M11 | financial | Sodium-ion capacity including behind-the-meter systems was 5.1 GWh at the end of 2025. |
| M12 | news | Three states added sodium-ion storage to their procurement targets. |
| M13 | news | A federal safety standard for sodium-ion systems is expected in late 2026. |

The planted conflicts are `CONFLICTS = {"K1": ("M1", "M3", "temporal"), "K2": ("M9", "M11", "scope")}`: the same measure with different values. The pack prices (`M2`, `M4`) differ too, but each states its year, so they are a trend, not a conflict.

**The library tools**, in the MCP server `library`:

| Tool | Description (what Claude reads) | Input | Behavior |
|---|---|---|---|
| `mcp__library__list_sources` (`readOnlyHint=True`) | `"Lists the library's sources for one research focus, with each source's URL, title and publication date."` | `focus` (enum `market`, `policy`) | Returns a JSON list of `{"sourceUrl", "documentName", "publicationDate"}` for that focus's 3 documents |
| `mcp__library__read_source` (`readOnlyHint=True`) | `"Returns one source's full text: its title, URL and publication date, then one passage per line."` | `source_url` (string) | Returns `Title: …`, `URL: …` and `Published: …` lines, then the context line, then one passage per line. Any other URL returns `is_error: True` with `Unknown source '<url>'. Call list_sources first.` |

Every call gets its options from `provenance_setup.py`:

```python
MODEL = "claude-opus-5-5"
LIBRARY_TOOLS = ["mcp__library__list_sources", "mcp__library__read_source"]

MAPPING_FIELDS = {  # the claim-source mapping: all five are required (C1)
    "claim": "One factual sentence, in your own words: what the source says.",
    "sourceUrl": "The source's URL, copied exactly: where a reader can check the claim.",
    "documentName": "The source's title, copied exactly: how a reader recognises the source.",
    "relevantExcerpt": "The supporting passage, copied word for word: the evidence itself.",
    "publicationDate": "When the source was published (YYYY-MM-DD): needed to compare figures that differ (C3).",
}
MAPPING_SCHEMA = {"type": "object", "additionalProperties": False, "required": list(MAPPING_FIELDS),
                  "properties": {name: {"type": "string", "description": text} for name, text in MAPPING_FIELDS.items()}}

MAPPING_FORMAT = (
    'Your final message must be only a JSON object {"findings": [...]}, with no other text. Each finding is a '
    'claim-source mapping with exactly these five fields, all required: "claim" (one factual sentence, in your '
    'own words), "sourceUrl", "documentName" and "publicationDate" (copied exactly from the source), and '
    '"relevantExcerpt" (the supporting passage, copied word for word). Write one finding per factual passage.')

AGENTS = {  # two research subagents, one focus each (C4)
    "market-analyst": AgentDefinition(
        description="Researches market data and technology: growth, prices, capacity and cell specifications.",
        prompt=("You are a market and technology analyst. Call list_sources with focus 'market', read every source "
                "with read_source, and report its findings. " + MAPPING_FORMAT),
        tools=LIBRARY_TOOLS, model="inherit", maxTurns=12),
    "policy-analyst": AgentDefinition(
        description="Researches regulation and news: approvals, standards, projects and policy.",
        prompt=("You are a regulation and news analyst. Call list_sources with focus 'policy', read every source "
                "with read_source, and report its findings. " + MAPPING_FORMAT),
        tools=LIBRARY_TOOLS, model="inherit", maxTurns=12),
}

COORDINATOR_PROMPT = (
    "You coordinate a research team. Never research yourself: delegate. market-analyst covers market data and "
    "technology; policy-analyst covers regulation and news. Give both of them the full research question in one "
    "response, with two Agent calls, and wait for both reports.")

def build_research_options():
    return ClaudeAgentOptions(
        model=MODEL,
        system_prompt=COORDINATOR_PROMPT,
        tools=["Agent"],                                     # the coordinator only delegates
        agents=AGENTS,                                       # the two analysts
        mcp_servers={"library": library_server},             # list_sources and read_source, used by the analysts
        allowed_tools=["Agent"] + LIBRARY_TOOLS,             # no permission prompts
        disallowed_tools=["Agent(fork)"],                    # no forks (01-02 E1)
        setting_sources=[],                                  # ignore ~/.claude and project settings, CLAUDE.md and hooks
        env={
            "ENABLE_TOOL_SEARCH": "false",                   # load tool schemas upfront: no ToolSearch calls
            "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",     # each Agent result holds the report (01-02 E2)
            "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",  # only the two analysts (01-02 E3)
        },
        max_turns=20,                                        # safety cap (01 C16)
    )

def build_synth_options(system_prompt, schema=None):
    # A synthesis session: no tools, only the findings in its prompt
    return ClaudeAgentOptions(
        model=MODEL,
        system_prompt=system_prompt,                         # PLAIN_PROMPT, TRACEABLE_PROMPT or BRIEF_PROMPT
        output_format={"type": "json_schema", "schema": schema} if schema else None,  # POC 2's structured brief
        tools=[],                                            # it can't fetch anything the findings don't hold
        setting_sources=[],
        env={"ENABLE_TOOL_SEARCH": "false"},
        max_turns=5,                                         # safety cap (01 C16)
    )

SYNTH_TASK = "Write a short brief on the state of sodium-ion grid storage in 2026 from these findings:\n"
PLAIN_PROMPT = "You write short research briefs from the findings you are given."   # the anti-pattern (C8)
TRACEABLE_PROMPT = (                                                                  # POC 1 (C8, C9)
    "You write short research briefs from the findings you are given. Combine related findings, but every "
    "sentence that states a fact must end with the id of each finding it uses, in brackets, such as [M3]: never "
    "state a fact without its marker. End with a 'References' section: one line per cited finding, in the form "
    "[Mn] documentName — sourceUrl — publicationDate, copied exactly from the findings.")
BRIEF_PROMPT = (                                                                      # POC 2 (C10, C12, C13, C15)
    "You write research briefs as structured JSON from the findings you are given. Group the findings into "
    "sections by content type: financial (numerical comparisons such as rates, prices and capacities), news "
    "(events such as approvals, announcements and projects) and technical (specifications and patterns). In a "
    "financial section, each entry gives measure, year (the period the value describes, or the source's "
    "publication year when it doesn't say) and value. Every entry cites the ids of the findings it uses, and "
    "every finding is cited at least once. When two findings give different values for the same measure, keep "
    "both entries and add the pair to conflicts, with both values, their citations and a possibleExplanation "
    "(different reporting periods, methods or scope). Never choose one value over another.")

BRIEF_SCHEMA = {
    "type": "object", "required": ["sections", "conflicts"],
    "properties": {
        "sections": {"type": "array", "items": {"type": "object", "required": ["title", "content_type", "entries"],
            "properties": {
                "title": {"type": "string"},
                "content_type": {"type": "string", "enum": ["financial", "news", "technical"]},
                "entries": {"type": "array", "items": {"type": "object", "required": ["text", "citations"],
                    "properties": {"text": {"type": "string"},
                                   "measure": {"type": ["string", "null"]},
                                   "year": {"type": ["string", "null"]},
                                   "value": {"type": ["string", "null"]},
                                   "citations": {"type": "array", "items": {"type": "string"}}}}}}}},
        "conflicts": {"type": "array", "items": {"type": "object", "required": ["measure", "values", "possibleExplanation"],
            "properties": {
                "measure": {"type": "string"},
                "values": {"type": "array", "items": {"type": "object", "required": ["value", "citation"],
                    "properties": {"value": {"type": "string"}, "citation": {"type": "string"}}}},
                "possibleExplanation": {"type": "string"}}}}}}
```

---

## 2. Concepts and POC requirements

All 16 concepts in the raw file (C1–C16) are covered: 13 are new or build on earlier POCs and are taught below, none is a terminal command, and 3 are already covered by `03-revised-Subagent-Invocation-and-Context-Passing.md` (see the end of this section).
Previous revised files checked: `01-revised-Agentic-Loops.md`, `02-revised-Multi-Agent-Orchestration.md`, `03-revised-Subagent-Invocation-and-Context-Passing.md`, `04-revised-Workflow-Enforcement-and-Handoff.md`, `05-revised-Agent-SDK-Hooks.md`, `06-revised-Task-Decomposition-Strategies.md`, `01-revised-Tool-Interface-Design.md`, `02-revised-Structured-Error-Responses.md`, `03-revised-Tool-Distribution-&-Tool-Choice.md`, `04-revised-MCP-Server-Integration.md`, `05-revised-Built-in-Tools.md`, `01-revised-System-Prompts-with-Explicit-Criteria.md`, `02-revised-Few-Shot-Prompting.md`, `03-revised-Structured-Output-with-Tool-Use.md`, `04-revised-Validation-Retry-and-Feedback-Loops.md`, `05-revised-Batch-Processing-Strategies.md`, `06-revised-Multi-Instance-and-Multi-Pass-Review.md`, `01-revised-Context-Window-Management.md`, `02-revised-Escalation-Ambiguity-Resolution.md`, `03-revised-Error-Propagation-in-Multi-Agent-Systems.md`, `04-revised-Codebase-Exploration-Context-Degradation.md`, `05-revised-Human-Review-Confidence-Calibration.md`.

The closest earlier work is `03-revised-Subagent-Invocation-and-Context-Passing.md`. It already has findings that keep content and metadata apart, a synthesizer that must cite them, and the diagnosis that a missing citation usually means the handoff stripped the metadata. This topic adds the excerpt and the publication date, the synthesis prompt's own share of the blame, conflicting sources, and rendering.

Raw step → concepts: **1** → C1–C3 · **2** → C4–C6 · **3** → C7–C9 · **4** → C10–C12 · **5** → C13–C16. Each step adds a Nudge and a Guidance, so concepts come from all five parts.
Rows marked **E** are extras that are not in the raw file. Without them, the POC breaks or gives misleading results.

### POC 1: Provenance from source to synthesis

**Build:** `provenance_setup.py` and `poc1_provenance.py`.

`provenance_setup.py` holds the code above, `DOCUMENTS`, the `library` server, `gold_mappings()`, `with_ids(mappings)` (which adds `"id": "M<n>"` to each mapping, in order), `KIND`, `CONFLICTS` and `validate_mapping(m)`. POC 2 reuses it. `validate_mapping(m)` returns a list of errors, empty when the mapping is valid. It checks four things:
- the mapping has exactly the 5 keys, each a non-empty string;
- `publicationDate` matches `^\d{4}-\d{2}-\d{2}$`;
- `sourceUrl`, `documentName` and `publicationDate` together match one document of `DOCUMENTS` exactly;
- `relevantExcerpt` appears word for word in that document's passages.

`python provenance_setup.py` runs an offline self-check that makes no API calls.

`poc1_provenance.py` makes 3 `query()` calls:
1. **`research_round()`:** `run_coordinator(RESEARCH_PROMPT, options=build_research_options())`, with `RESEARCH_PROMPT = "Research this question with both analysts, then reply with one line saying both reports are in. Question: What is the state of sodium-ion grid storage in 2026?"`. It parses each Agent report with `parse_json_object(report)["findings"]`, runs `validate_mapping()` on every finding, and returns `{"mappings", "errors", "by_agent"}`.
2. **`synthesize(PLAIN_PROMPT, mappings)`.**
3. **`synthesize(TRACEABLE_PROMPT, mappings)`.**

`synthesize()` sends `SYNTH_TASK` plus `json.dumps(with_ids(mappings), indent=2)` through `run_coordinator(prompt, options=build_synth_options(system_prompt))` and returns the brief's text. `traceability(brief, mappings)` scores each brief (C9).

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C1 | A claim-source mapping schema with the fields `claim`, `sourceUrl`, `documentName`, `relevantExcerpt` and `publicationDate`, all required, each with a description of what it holds and why provenance tracking needs it (**Builds on** `03-revised-Subagent-Invocation-and-Context-Passing.md` C8) | `MAPPING_FIELDS` and `MAPPING_SCHEMA` (code above): 5 required string fields, `additionalProperties: false`, and a description per field that says what it holds and why. `validate_mapping()` checks a mapping against the schema and the library (rules in the Build). New compared with 01-03 C8: the mapping carries the evidence itself (`relevantExcerpt`, word for word) and the time it speaks for (`publicationDate`), instead of a page number and a confidence | `MAPPING_SCHEMA["required"]` lists all 5 fields, and each property has a non-empty description. The self-check gets `[]` from `validate_mapping(gold_mappings()[0])`. It gets an error for 3 altered copies: one without `publicationDate`, one dated `March 2025`, and one whose excerpt isn't in its source |
| C4 | Two research subagents that each return an array of claim-source mappings with every field populated, publication dates included, each researching a different aspect of the same topic, such as market data against regulatory developments (**Builds on** `03-revised-Subagent-Invocation-and-Context-Passing.md` C5) | `AGENTS` (code above): `market-analyst` (focus `market`) and `policy-analyst` (focus `policy`), with the same two library tools and the same `MAPPING_FORMAT`. `research_round()` (Build) prints each analyst's mappings with their validation errors. New compared with 01-03 C5: both analysts return the same format, and they are split by research focus, not by tool | 2 Agent calls, typically in one response. Typically 7 mappings from `market-analyst` and 6 from `policy-analyst`, with 0 validation errors: every excerpt appears word for word in its source, and every date matches its source |
| C7 | A synthesis agent that merges both subagents' findings while explicitly preserving every claim-source mapping through the merge (**Builds on** `03-revised-Subagent-Invocation-and-Context-Passing.md` C11) | `synthesize()` (Build) gives the research round's mappings the ids `M1`… in order, `market-analyst`'s first, and sends the same JSON to both prompts. New compared with 01-03 C11, where the goal was that all the metadata reached the synthesizer: here the synthesizer must also keep each claim tied to its mapping in what it writes | Both briefs come from the same mappings (typically 13), and neither synthesis session makes a tool call |
| C9 | Inline citation markers ([1], [2]) linked to a references section at the end that holds the full claim-source mappings. Related findings may be combined, but every claim stays traceable to its source URL, document name and publication date (**Builds on** `03-revised-Subagent-Invocation-and-Context-Passing.md` C13) | `TRACEABLE_PROMPT` (code above) asks for `[Mn]` markers and a `References` section. `traceability(brief, mappings)` splits the body (everything before `References`) into sentences; a marker right after a sentence's full stop belongs to that sentence. It returns four counts: the body sentences, those with at least 1 valid marker, the distinct findings cited, and the reference lines that contain their finding's exact `documentName`, `sourceUrl` and `publicationDate`. New compared with 01-03 C13: the citations sit inline in prose, and the reference list rebuilds the full mapping for a reader | Traceable brief: typically every body sentence has a valid marker, all the findings are cited, and every reference line is complete. A sentence that combines findings, such as one on both pack prices, typically carries one marker per finding |
| C8 | Synthesis is the most common failure point for attribution: a synthesis agent naturally compresses and paraphrases, and drops the claim-source mappings unless its prompt explicitly requires every claim to be traceable. The exam tests that attribution must be maintained explicitly through every synthesis step (**Builds on** `03-revised-Subagent-Invocation-and-Context-Passing.md` C14) | Run `PLAIN_PROMPT` and `TRACEABLE_PROMPT` on the same mappings. Print `traceability()` for both side by side, with 2 sample sentences from each. New compared with 01-03 C14, which traced a missing citation back to a handoff that had stripped the metadata: here the metadata reached the synthesizer in full, so the second branch of that diagnosis applies, the synthesis prompt | Plain: typically 0 valid markers and no reference lines, with at most a source named in passing, without its URL or date. Traceable: typically 100% of body sentences traceable. Same model and same findings: only the instruction differed |

### POC 2: Conflicts and content-appropriate rendering

**Build:** `poc2_conflicts_rendering.py`, reusing `provenance_setup.py` and `run_coordinator()`. It makes one call: `run_coordinator(SYNTH_TASK + json.dumps(GOLD, indent=2), BRIEF_SCHEMA, options=build_synth_options(BRIEF_PROMPT, BRIEF_SCHEMA))`, with `GOLD = with_ids(gold_mappings())`. Everything after that runs offline, through these functions:
- `check_conflicts(brief)`;
- `pick_one(conflict, mappings, rule="latest")`, the anti-pattern;
- `render(brief, mappings)` and `render_uniform(brief, mappings)`;
- `check_rendering(text, mappings)`;
- `section_kinds(brief)`.

`render()` writes Markdown, with markers written as `[Mn]`:
- one `## <title>` per section, then content shaped by its `content_type`:
  - `financial`: a table `| Measure | Year | Value | Source |` with one row per entry, the Source column holding the entry's markers;
  - `news`: one paragraph, each entry's `text` followed by its markers;
  - `technical`: one `- <text> <markers>` line per entry;
- `## Conflicting figures`: one line per conflict, `<measure>: <value> [Mx] (<documentName>, <publicationDate>) vs <value> [My] (<documentName>, <publicationDate>). Possible explanation: <possibleExplanation>`, with the attribution taken from the mappings;
- `## References`: one line per cited id, in id order, `[Mn] <claim> — <documentName> — <sourceUrl> — <publicationDate> — "<relevantExcerpt>"`.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| E1 | A fixed set of mappings as POC 2's input | `GOLD`: the 13 mappings a perfect research round would return, built in code from the library, with the ids `M1`–`M13` of the library table. If POC 2 ran on live research, a conflict that was missed because an analyst skipped a passage would look like a synthesis failure. POC 1 already shows live analysts producing these mappings | `GOLD` has 13 mappings, each passing `validate_mapping()`, and it contains the planted pairs `M1`/`M3` and `M9`/`M11` |
| C10 | A conflict-handling function that detects overlapping claims about the same measure with different values, preserves both with full attribution, and never silently picks one (**New**) | `BRIEF_PROMPT` makes the synthesizer list conflicts (code above). `check_conflicts(brief)` matches each `CONFLICTS` pair to a conflict whose citations are exactly that pair, and checks that both values are present, each with its own citation. `render()` adds each value's document name and publication date from the mappings, so the attribution is complete whatever the model wrote | `K1` (`M1` 12% against `M3` 18%, the growth rate) and `K2` (`M9` 4.2 GWh against `M11` 5.1 GWh, the installed capacity) are both found, each with 2 values and 2 citations. Typically there is no other conflict: the pack prices (`M2`, `M4`) state their years, so they form a trend in the table, not a conflict |
| C12 | Different publication dates often explain different numbers as a trend rather than a contradiction. A `possibleExplanation` field notes temporal differences (different reporting periods), methodological differences or scope differences that may explain a discrepancy (**New**) | Print each conflict's `possibleExplanation` next to the planted reason in `CONFLICTS`: `temporal` for `K1` and `scope` for `K2` | Both explanations are non-empty. `K1`'s typically names the two publication dates or reporting periods, or calls the change a trend. `K2`'s typically names the scope difference: behind-the-meter systems against grid-connected systems only |
| C3 | The publication date is not just metadata tidiness: it is essential for interpreting two sources that report different numbers (**New**) | Print `K1` twice: without dates (`12% [M1] vs 18% [M3]`), and with the dates that `render()` adds | Without dates, the pair reads as a contradiction. With them, `12% (2025-03-10) vs 18% (2026-02-20)`, 347 days apart, reads as a rate that rose within a year. Only the dates make that reading possible |
| C11 | Arbitrarily selecting one of two credible values destroys information and presents false certainty. The correct approach, which the exam tests, is to annotate both values with their sources and let the reader decide (**New**) | `pick_one(conflict, mappings, rule="latest")`, offline and used only here, is the anti-pattern: it keeps the value whose mapping has the latest `publicationDate` and drops the other. Run it on both conflicts, and print what the reader loses | `K1` keeps 18% (`M3`) and loses 12% (`M1`), with its source and date. `K2` keeps 5.1 GWh (`M11`, 2026-02-05) and loses the regulator's 4.2 GWh (`M9`, 2026-01-28). The brief would then present 5.1 GWh as grid capacity, although that figure includes behind-the-meter systems: a certainty the sources don't support |
| C13 | Content-appropriate rendering: detect each section's content type and apply its format. Financial data becomes a table with year, value and source columns, news becomes prose paragraphs, and technical findings become bulleted lists (**New**) | `render(brief, mappings)` (rules in the Build) formats each section by its `content_type`. `check_rendering(text, mappings)` checks the shapes: every financial section is a table with the columns `Measure`, `Year`, `Value` and `Source`; every technical section is a bulleted list; every news section is prose, with neither a table nor bullets | Typically 3 sections: a financial table with 6 rows (`M1`, `M2`, `M3`, `M4`, `M9`, `M11`), a technical list of 3 bullets (`M5`–`M7`), and news prose of 4 cited sentences (`M8`, `M10`, `M12`, `M13`) |
| C15 | Classify the content type from the nature of the claims: numerical comparisons are financial (a table), narrative events are news (prose), and specifications or patterns are technical (a list) (**New**) | The synthesizer labels each section's `content_type` using `BRIEF_PROMPT`'s definitions. `section_kinds(brief)` compares every citation in a section with `KIND`, the expected type of each finding, and lists the mismatches | Typically 0 mismatches: the 6 financial findings sit in financial sections, the 3 technical ones in technical sections, and the 4 news ones in news sections |
| C16 | Each rendered section still carries inline citations that link back to the claim-source mappings: the format changes, but the attribution doesn't (**New**) | `check_rendering()` also checks that every table row, bullet and news sentence carries at least 1 marker, and that every marker has a line in `References` with that mapping's full fields | Every rendered line has a marker, all 13 findings are cited (as the prompt requires), and `References` has 13 complete lines |
| C14 | Synthesis shouldn't force all content into one uniform format: that degrades readability, and the exam tests choosing the format by the content (**New**) | `render_uniform(brief, mappings)`, the anti-pattern, renders every entry as a `- ` bullet, whatever its type. Print it next to `render()` | In the uniform version, the 6 figures become loose bullets with no year or value columns to compare, and the news events read as disconnected fragments. Both versions carry the same markers: only the format differs, not the attribution |

### Terminal commands (for the later tutorial)

None: every concept in this topic is a programming concept.

### Already covered by earlier POCs

| ID | Concept | Covered in | Check when reused |
|---|---|---|---|
| C2 | Every finding in a multi-agent research system must carry its provenance. Without structured claim-source mappings, attribution is lost during summarisation, and the output becomes plausible-sounding text that nobody can trace | `03-revised-Subagent-Invocation-and-Context-Passing.md` C9, C10 | POC 1's plain synthesis shows the same failure again (C8): fluent sentences with no marker that leads back to a URL or a date |
| C5 | Subagents must output the structured format from the start: if they return prose, attribution is lost before synthesis begins, and end-to-end provenance depends on structured output at the subagent level | `03-revised-Subagent-Invocation-and-Context-Passing.md` C8, C12 | Both analysts' reports are parsed as mapping arrays and validated before any synthesis. A report that isn't valid JSON counts as an error, never as prose to summarise |
| C6 | The subagent prompt must explicitly require structured output with all five claim-source mapping fields; without that instruction, subagents return prose | `03-revised-Subagent-Invocation-and-Context-Passing.md` C8 | `MAPPING_FORMAT` ends both analysts' prompts and names all five fields |
