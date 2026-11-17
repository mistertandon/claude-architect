# POC 2: The Coordinator Checks Its Own Work

> **File:** `poc2_refinement.py` (with `coordinator.py`, `research_setup.py` and `common.py`)
> **Domain:** 01 Agentic Architecture & Orchestration → 02 Multi-Agent Orchestration
> **SDK:** Claude Agent SDK for Python (`claude-agent-sdk >=0.2.174,<0.3`; 0.2.174 in the folder's `.venv`)
> **Page:** https://claude.ai/artifact/8EZq6uxJtm928QnBjbDk3k

---

## 1. What this POC proves

POC 1 ran one delegation round and found that the decomposition had missed fusion. It couldn't repair the miss. POC 2 wraps the same hub and spokes in a loop: the coordinator judges its own report, re-delegates only the gaps, and stops at a coverage threshold or an iteration cap.

| # | Idea | Where it shows up in the code |
|---|------|------------------------------|
| 1 | **Coverage is judged against the whole topic, not against the sections you already have.** A category with no section is `missing`, even though no section mentions it. | `assess_coverage()`: "List every category this topic needs"; `COVERAGE_SCHEMA` with `well_covered` / `partial` / `missing` |
| 2 | **Claude judges, Python decides.** Claude rates each category. Python counts the ratings, compares them with the threshold and runs the loop, so the stop rules are deterministic. | `coverage_percent()`, `COVERAGE_THRESHOLD`, `MAX_ITERATIONS`, the `for` loop in `research()` |
| 3 | **Only the gaps are re-delegated, each with its reason.** A follow-up round never re-researches what is already well covered. | `subtopics = [g["subtopic"] for g in gaps]`, `gap_notes = {...}`, and the `Fix only these gaps:` lines in `delegate()` |
| 4 | **Every round's results are kept.** New sections are merged into the report by subtopic name. | `merge_sections()` |
| 5 | **Two stops: a quality threshold first, an iteration cap as the safety net.** When the cap fires, the coordinator logs a warning and still returns the partial report, flagged `complete: False`. | `if percent >= COVERAGE_THRESHOLD` and the `log.warning(...)` after the loop |
| 6 | **A missing category traces back to the decomposition.** Python checks what round 1's Agent prompts never mentioned. | `missing_categories([call["prompt"] for call in first_round["agent_calls"]])` in `main()` |
| 7 | **A coordinator is more than a dispatcher.** Round 1's coverage is what a single-shot dispatcher would return; the loop's final coverage is what the coordinator returns. | The `Run '...': dispatcher ...% -> coordinator ...%` line in `main()` |
| 8 | **The cap is a real stop, not a formality.** In the real run, no run reached 100%. All three ended at the cap, with the partial report. | Log lines `Coverage 88% after 3 iteration(s)`, `Coverage 25% after 1 iteration(s)`, `Coverage 64% after 3 iteration(s)` |

The pattern in one picture:

```
delegate ─▶ merge_sections ─▶ assess_coverage ─▶ coverage_percent >= 100? ── yes ─▶ return {complete: True}
   ▲                                                   │ no
   └──── only the gaps + their reasons (gap_notes) ◀───┤ iteration < cap
                                                       └ iteration == cap ─▶ WARNING, return {complete: False}
```

---

## 2. The files involved

```
02-Multi-Agent-Orchestration/
├── .env                    ← ANTHROPIC_API_KEY, MODEL_ID, MAX_TURNS, MAX_BUDGET_USD
├── common.py               ← load_settings(), setup_logging(), log_model_io(): settings and the log
├── research_setup.py       ← mock Helios corpus, REQUIRED, 2 tools, COORDINATOR_PROMPT, AGENTS, build_coordinator_options()
├── coordinator.py          ← run_coordinator() and the coordinator's jobs: decompose(), delegate(), research_once()
├── poc1_hub_and_spoke.py   ← POC 1: one delegation round (not covered here)
├── poc2_refinement.py      ← entry point: 3 runs, the refinement loop
└── logs/
    └── poc2_refinement_20261027_183353.log   ← the real run used in this article
```

All the code in this article, logging statements included, comes from this folder. The real run in sections 3.2 and 5 is the log file above, written by the same code on 2026-10-27.

`poc2_refinement.py` reuses everything POC 1 built and adds only the loop:
- `common.py` covers **configuration** (model, turn cap, budget) and the **log** (one line per model input or output, tagged with its agent).
- `research_setup.py` covers **capabilities** (the two tools and the two subagents), the **required categories** and the **guardrails** of every coordinator call.
- `coordinator.py` covers **orchestration** (stream one coordinator call; decompose; delegate, now with optional `gap_notes`).
- `poc2_refinement.py` covers **the refinement loop**: assess coverage, count it, re-delegate the gaps, stop.

---

## 3. End-to-end execution flow

### 3.1 The big picture

```
python poc2_refinement.py
        │
        ▼
asyncio.run(main())
        │
        ├─▶ load_settings()                                               [common.py]
        │      └─ .env → Settings(model_id, max_turns, max_budget_usd), frozen
        ├─▶ setup_logging("poc2_refinement")                              [common.py]
        │      └─ console + logs/poc2_refinement_<date>_<time>.log
        │
        └─▶ for name, subtopics, max_iterations in RUNS:                  ("narrow", "capped", "full")
               │
               ├─▶ report = research(settings, TOPIC, max_iterations, subtopics)
               │      │
               │      ├─ subtopics or decompose(settings, topic)          [coordinator.py]   → query() (run "full" only)
               │      │
               │      └─ for iteration in 1..max_iterations:
               │            ├─ delegate(settings, topic, subtopics, gap_notes)  [coordinator.py] → query() with Agent + 2 spokes
               │            ├─ sections = merge_sections(sections, new sections)
               │            ├─ coverage = assess_coverage(settings, topic, sections, REQUIRED)    → query() with tools=[]
               │            ├─ percent  = coverage_percent(coverage)        (Python counts)
               │            ├─ gaps     = entries whose status != "well_covered"
               │            ├─ log.info("iteration %d: delegated %d -> coverage %d%% -> gaps %s")
               │            ├─ percent >= COVERAGE_THRESHOLD? → return {..., "complete": True}
               │            └─ else: subtopics = gap names; gap_notes = {gap: reason}
               │         after the loop: log.warning("Coverage %d%% after %d iteration(s); ...")
               │                         return {..., "complete": False}
               │
               ├─▶ never_delegated = missing_categories(round 1's Agent prompts)   [research_setup.py]
               │      └─ log.info("Never delegated in round 1: ...")      (only when non-empty)
               └─▶ log.info("Run '%s': dispatcher %d%% -> coordinator %d%% after %d round(s), ...")
```

Every coordinator step goes through the same function, `run_coordinator()`. Inside it, the SDK runs the coordinator and, for `delegate()`, its subagents:

```
run_coordinator(prompt, options)                                          [coordinator.py]
   │
   ├─ log.info("MODEL INPUT   prompt       [coordinator] %s", prompt)
   └─▶ async for message in query(prompt=prompt, options=options):
          │
          │   ┌─────────────────────── SDK-owned: one coordinator call ────────────────────────┐
          │   │ starts the bundled Claude Code; the coordinator gets COORDINATOR_PROMPT        │
          │   │                                                                                │
          │   │ delegate():  tools=["Agent"], agents=AGENTS, SECTIONS_SCHEMA                   │
          │   │ ┌─▶ coordinator Claude responds                                                │
          │   │ │     ├─ tool_use Agent {subagent_type, prompt = the brief}       (id = A)     │
          │   │ │     │    ┌──── subagent: fresh context = its own prompt + the brief ────┐    │
          │   │ │     │    │  tool_use mcp__research__* → your handler → tool_result ...  │    │
          │   │ │     │    │  final text = the report                                     │    │
          │   │ │     │    └──────────────────────────────────────────────────────────────┘    │
          │   │ │     │   tool_result (tool_use_id = A) = the report                           │
          │   │ └─────┘   (next coordinator turn)                                              │
          │   │       └─ StructuredOutput {sections: [...]}  → accepted                        │
          │   │                                                                                │
          │   │ decompose() / assess_coverage():  tools=[], no agents, a schema                │
          │   │       └─ StructuredOutput {subtopics | coverage: [...]}  → accepted            │
          │   │                                                                                │
          │   │ yields ResultMessage (success / error_*)                                       │
          │   └────────────────────────────────────────────────────────────────────────────────┘
          │
          ├─ log_model_io(message, agent_names)   → the MODEL INPUT / MODEL OUTPUT lines
          ├─ hub's Agent call → agent_calls[id] = {"id", "subagent_type", "prompt", "report": None}
          ├─ its tool_result  → agent_calls[id]["report"] = text_of(block.content)
          ├─ ResultMessage    → subtype; if "success": output = structured_output
          └─ ResultError      → log.error(...); output stays None → the caller raises RuntimeError
```

The loop itself is plain Python **outside** the SDK. The SDK runs one coordinator call at a time; `research()` decides whether there is a next one.

### 3.2 Messages your `async for` receives (run `narrow`, round 3: re-delegating one gap, real output)

The values below come from the real run on 2026-10-27, `logs/poc2_refinement_20261027_183353.log`. Each log line holds fields of one message from the stream, or one line the loop writes itself:

| Log line tag | Written by | Message class / source | Field logged |
|--------------|------------|------------------------|--------------|
| `MODEL INPUT   prompt` | `log.info` at the top of `run_coordinator()` | *(none: the `prompt` argument)* | `prompt` |
| `MODEL OUTPUT  thinking` | `log_model_io()` | `AssistantMessage` → `ThinkingBlock` | `block.thinking`, only when non-empty |
| `MODEL OUTPUT  text` | `log_model_io()` | `AssistantMessage` → `TextBlock` | `block.text` (none in this log) |
| `MODEL OUTPUT  tool_use` | `log_model_io()` | `AssistantMessage` → `ToolUseBlock` | `block.name`, `block.input`, `block.id` |
| `MODEL OUTPUT  structured` | `log_model_io()` | `AssistantMessage` → `ToolUseBlock` named `StructuredOutput` | `block.input`, `block.id` |
| `MODEL INPUT   tool_result` | `log_model_io()` | `UserMessage` → `ToolResultBlock` | `block.content`, `block.tool_use_id`, `block.is_error` |
| `MODEL OUTPUT  stop_reason` | `log_model_io()` | `ResultMessage` | `message.stop_reason`, `message.subtype` |
| `[coordinator]`, `[web-searcher]`, `[doc-analyst]` | `log_model_io()` | the message the line came from | `message.parent_tool_use_id`: `None` gives `coordinator`; any other value gives the `subagent_type` of the Agent call with that id |
| `iteration n: delegated k -> coverage p% -> gaps [...]` | `log.info` in `research()` | *(Python: the loop)* | `iteration`, `len(subtopics)`, `percent`, the gap names |
| `Coverage p% after n iteration(s); gaps: [...]` | `log.warning` in `research()` | *(Python: the cap fired)* | `percent`, `max_iterations`, `subtopics` (the last gaps) |
| `Never delegated in round 1: [...] -> root cause: ...` | `log.info` in `main()` | *(Python)* | `never_delegated` |
| `Run '...': dispatcher p% -> coordinator q% after n round(s), ...` | `log.info` in `main()` | *(Python)* | `first_round["coverage_percent"]`, `report["coverage_percent"]`, `len(report["history"])`, `missing_categories(<section names>)` |

The formatter is `"%(asctime)s  %(message)s"`, so the log shows no level name: the `log.warning` line looks like any other line.

Round 2 of run `narrow` had left one gap, rated `missing` with the reason "The section is empty: no web findings, no document and no source ids. It needs a different search approach or source." Round 3, as it really streamed:

```
18:34:57  iteration 2: delegated 6 -> coverage 88% -> gaps ['green hydrogen']        ← research(): round 2's result

18:34:57  (input)                            [coordinator]        delegate(), round 3
            prompt = Research goal: a sourced overview of "renewable energy technologies" with key figures from Helios Institute sources.
                     Subtopics for this round (delegate only these, using these exact names): ["green hydrogen"]
                     Fix only these gaps:
                     - green hydrogen: The section is empty: no web findings, no document and no source ids. It needs a different search approach or source.
                     Delegate with one Agent call that finds sources for all of these subtopics, then one Agent call that reads ...

18:35:02  AssistantMessage › ToolUseBlock    [coordinator]
            name  = "Agent"
            input = {'description': 'Find green hydrogen sources', 'subagent_type': 'web-searcher',
                     'prompt': 'Research goal: ... Subtopic (exact name): "green hydrogen". A previous search returned nothing for it,
                                so try different search approaches: e.g. "green hydrogen", "hydrogen", "electrolysis", "electrolyzer",
                                "power-to-gas", "renewable hydrogen". ... If nothing is found after several attempts, say so explicitly.'}
            id    = "toolu_01YSbKJGQVNE6dfL989bQWaC"                          ← call A

18:35:04  AssistantMessage › ToolUseBlock    [web-searcher]
            name  = "mcp__research__web_search",  input = {'query': 'green hydrogen'},  id = "toolu_0187nvEB5yGvrznotJ1tword"
18:35:04  UserMessage › ToolResultBlock      [web-searcher]
            content = [{'type': 'text', 'text': "No Helios results for 'green hydrogen'."}]
            tool_use_id = "toolu_0187nvEB5yGvrznotJ1tword",  is_error = None

          ... 5 more web_search round trips: 'hydrogen', 'electrolysis', 'electrolyzer', 'power-to-gas', 'renewable hydrogen',
              every one "No Helios results ...", every one is_error = None ...

18:35:08  UserMessage › ToolResultBlock      [coordinator]
            content     = [{'type': 'text', 'text': '[Subagent hand-back] ... The report follows:\n  I found nothing on "green hydrogen"
                            in the Helios Institute sources. I ran six searches, ... Your overview should either leave green hydrogen
                            out or cite a source outside Helios for it.\nagentId: a9bea2ba4fc2ca0e2\n<usage>subagent_tokens: 2375
                            \ntool_uses: 6\nduration_ms: 6152</usage>'}]
            tool_use_id = "toolu_01YSbKJGQVNE6dfL989bQWaC"                    ← call A: the report is its tool_result
            is_error    = None

18:35:12  AssistantMessage › ThinkingBlock   [coordinator]
            thinking = "There are no document ids available, so there's nothing for the doc-analyst to read here. I'll skip that call
                        and just report this honestly rather than inventing something to read."

18:35:12  AssistantMessage › ToolUseBlock    [coordinator]                    (logged as "structured")
            name  = "StructuredOutput"
            input = {'sections': [{'subtopic': 'green hydrogen', 'web_findings': 'No Helios Institute sources found. The web-searcher ran
                     six differently worded queries ...', 'document_findings': 'Not researched. The search named no documents, so I did
                     not call the doc-analyst. ...', 'sources': []}]}
            id    = "toolu_01HKN8q5h49HD1rPE46djuSH"
18:35:12  UserMessage › ToolResultBlock      [coordinator]
            content = Structured output provided successfully,  tool_use_id = "toolu_01HKN8q5h49HD1rPE46djuSH",  is_error = None
18:35:12  ResultMessage                      [coordinator]
            subtype = "success", stop_reason = "tool_use"

18:35:13  (input)                            [coordinator]        assess_coverage(), round 3
            prompt = Topic: renewable energy technologies. Must cover at least: ['solar', 'wind', 'geothermal', 'tidal', 'biomass', 'fusion'].
                     Report sections so far: [ ...8 sections: solar power, wind power, geothermal, tidal, biomass, fusion, hydropower,
                     green hydrogen... ]. List every category this topic needs ... Give a one-line reason for each.

18:35:20  AssistantMessage › ThinkingBlock   [coordinator]
            thinking = "... Green hydrogen stands out differently though — it has no web findings, no document findings, and no sources,
                        so it's missing all three elements rather than just one, which puts it in the missing category rather than partial."
18:35:21  AssistantMessage › ToolUseBlock    [coordinator]                    (logged as "structured")
            name  = "StructuredOutput"
            input = {'coverage': [{'subtopic': 'solar', 'status': 'well_covered', ...}, ... 7 × well_covered ...,
                                  {'subtopic': 'green hydrogen', 'status': 'missing', 'reason': 'The section is empty. Six queries returned
                                   no Helios results, ... It needs a new search approach.'}]}
            id    = "toolu_01Pf3a9L7giCH5WXTr3N6a82"
18:35:21  ResultMessage                      [coordinator]
            subtype = "success", stop_reason = "tool_use"

18:35:22  iteration 3: delegated 1 -> coverage 88% -> gaps ['green hydrogen']        ← 7 / 8 = 87.5 → round() = 88
18:35:22  Coverage 88% after 3 iteration(s); gaps: ['green hydrogen']                  ← the cap (log.warning)
18:35:22  Never delegated in round 1: ['geothermal', 'tidal', 'biomass', 'fusion'] -> root cause: the coordinator's decomposition, not the subagents
18:35:22  Run 'narrow': dispatcher 25% -> coordinator 88% after 3 round(s), categories still missing: []
```

What to notice in the real data:
- **The gap reason became the brief.** The assessment said "It needs a different search approach". `delegate()` copied that reason into the prompt (`Fix only these gaps:`), the coordinator turned it into six alternative queries in the web-searcher's brief, and the web-searcher ran exactly those six (`tool_uses: 6`). No Python wrote the queries: Python only passed the reason along.
- **Only the gap was re-delegated.** Round 3 delegated 1 subtopic. The seven well-covered categories were neither searched nor read again, and `merge_sections()` kept their round-1 and round-2 sections.
- **The coordinator skipped a step it couldn't do honestly.** The prompt says "then one Agent call that reads the documents". With no document id, the coordinator made no doc-analyst call, and its `thinking` line says why. Round 3 has 1 Agent call, not 2.
- **The loop can't fix a gap the data source doesn't have.** `CORPUS` has no hydrogen entry, so `web_search` can only return "No Helios results". With 8 rated categories, the best possible score was 7 / 8 = 88%. The threshold of 100 was out of reach; the cap ended the run, logged the warning and returned the partial report.
- **The coordinator's reasoning is in the log.** The run logged 6 `thinking` lines, all `[coordinator]`: 4 in assessments and 2 in delegations (this round's is one of them). `thinking={"type": "adaptive", "display": "summarized"}` makes them visible. The assessment ones show the rubric from the prompt being applied: "web findings, document findings and a source id".
- **`tool_use_id` pairing works at two levels**, as in POC 1: each search's `id` comes back as its result's `tool_use_id`, and call A's `id` comes back as the `tool_use_id` of the web-searcher's report.
- **`success` with `stop_reason = "tool_use"`, every time.** All 15 calls in this log used `output_format`, so each ended right after its accepted `StructuredOutput` call. `run_coordinator()` checks only `subtype`.
- **Not shown:** `SystemMessage`s and other system events also arrive in the stream (see the "No `break`" comment in `run_coordinator()`), but the log records only model input and output. Cost, turn counts and session ids are not logged. The only usage numbers are those inside each `[Subagent hand-back]` frame (`subagent_tokens`, `tool_uses`, `duration_ms`), which the harness adds to every report.

> The `UserMessage` items are **not** typed by a human. They carry tool results: the research results inside a subagent, each subagent's report for the coordinator, and the `StructuredOutput` acknowledgement.

---

## 4. Code walkthrough

### 4.1 Module docstring: the loop in five lines

```python
"""
POC 2 - The coordinator's refinement loop
==========================================
One delegation round can miss whole categories. A coordinator checks its own result and repairs it:

    delegate -> merge sections -> assess coverage -> 100%?  stop
                    ^                                 no:   re-delegate ONLY the gaps, each with its reason
                    +---------------------------------------+   (at most MAX_ITERATIONS rounds)

Claude judges the coverage (assess_coverage). Python counts it and runs the loop, so the threshold and the
iteration cap are deterministic. Besides model I/O, the log shows one line per iteration and the cap warning.

Run:  python poc2_refinement.py     (3 runs, about 9 query() calls)
"""
```

**Why it matters:** the docstring states the split of work the exam cares about. Claude makes the judgment (which categories are covered). Python makes the control decisions (is it 100%? is this the last round?). That's why both stops are reliable.

The estimate "about 9 query() calls" assumes the runs stop early. In the real run, `narrow` and `full` both used all 3 rounds, so the script made **15** `query()` calls (6 + 2 + 7, see 5.4).

---

### 4.2 Imports

```python
import asyncio
import json
import sys
from typing import Any

from claude_agent_sdk import ClaudeSDKError

from common import Settings, load_settings, log, setup_logging
from coordinator import decompose, delegate, run_coordinator
from research_setup import REQUIRED, build_coordinator_options, missing_categories
```

| Import | What it brings in | Why this file needs it |
| --- | --- | --- |
| **asyncio** | The event loop | Every coordinator step is an async `query()` call |
| **json** | `json.dumps()` | Puts the current sections into the assessment prompt as JSON |
| **sys** | `sys.exit()` | Returns `0` or `1` to the shell |
| **Any** | Type hint | For the `history` items |
| **ClaudeSDKError** | The SDK's base exception | Stops the script on an SDK runtime failure (Claude Code missing, process crash) |
| **Settings**, **load_settings** | From `common` | The model, `max_turns` and `max_budget_usd` for every call |
| **log**, **setup_logging** | From `common` | The `poc` logger: model I/O plus the loop's own lines |
| **decompose**, **delegate** | From `coordinator` | The coordinator's jobs 1 and 2–3, reused from POC 1 |
| **run_coordinator** | From `coordinator` | Streams the assessment call |
| **REQUIRED** | From `research_setup` | The must-cover list passed to `assess_coverage()` |
| **build_coordinator_options** | From `research_setup` | Options for the assessment call (`with_agents=False`) |
| **missing_categories** | From `research_setup` | The deterministic root-cause and final-coverage checks |

---

### 4.3 Constants and the run table

```python
TOPIC = "renewable energy technologies"
COVERAGE_THRESHOLD = 100  # the primary stop: every category well covered
MAX_ITERATIONS = 3  # the fallback stop: delegation rounds, not the SDK's tool turns (01 C16)
NARROW = ["solar power", "wind power"]  # plays a coordinator that decomposed too narrowly (C6)

# (name, starting subtopics or None = decompose first, max iterations)
RUNS = [
    ("narrow", NARROW, MAX_ITERATIONS),  # 33% after round 1, then the gaps get re-delegated
    ("capped", NARROW, 1),  # the same start, but the cap stops the loop: a warning and a partial report
    ("full", None, MAX_ITERATIONS),  # a real decomposition: typically 100% after round 1
]
```

| Constant | Value | Role |
|----------|-------|------|
| `COVERAGE_THRESHOLD` | `100` | **Primary stop.** A quality condition: every rated category `well_covered`. |
| `MAX_ITERATIONS` | `3` | **Fallback stop.** Counts delegation rounds. It's a third cap, separate from `max_turns` (per coordinator call) and `maxTurns=15` (per subagent). |
| `NARROW` | solar, wind | The exam's failure pattern, injected on purpose so the loop has something to repair. |
| `RUNS` | 3 runs | `narrow`: repair a bad start. `capped`: the same start with a cap of 1, to show the fallback stop. `full`: a real decomposition. |

**Real values vs the comments:** run `narrow` started at **25%**, not 33%, because the assessor rated 8 categories (the 6 required ones plus hydropower and green hydrogen): 2 / 8. Run `full` started at **55%**, not 100%, and ended at 64% (section 5.3).

**Agentic concept:** stop conditions belong to code. The model can't talk the loop into another round or out of the cap.

---

### 4.4 `COVERAGE_SCHEMA`: the assessment's output contract

```python
COVERAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "coverage": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subtopic": {"type": "string"},
                    "status": {"type": "string", "enum": ["well_covered", "partial", "missing"]},
                    "reason": {"type": "string"},
                },
                "required": ["subtopic", "status", "reason"],
            },
        }
    },
    "required": ["coverage"],
}
```

**Why it matters:**
- `status` is an **enum**. Python can count `well_covered` exactly, with no prose to parse and no "mostly covered" to interpret.
- `reason` is **required**. It's the text that becomes the targeted follow-up in the next round (`gap_notes`).
- The three values are the objective's own words: well covered, partially covered, missing.

**Agentic concept:** structured output turns a model judgment into data that control flow can use.

---

### 4.5 `assess_coverage()`: judge against the whole topic

```python
async def assess_coverage(settings: Settings, topic: str, sections: list[dict], must_cover: list[str]) -> list[dict]:
    """The coordinator judges the report against the WHOLE topic, not against the sections it has (C14)."""
    prompt = (
        f"Topic: {topic}. Must cover at least: {must_cover}. Report sections so far: {json.dumps(sections)}. "
        "List every category this topic needs (each must-cover item plus any other major category of the topic) "
        "and rate each one: well_covered = a section with web findings, document findings and a source id; "
        "partial = a section missing one of these; missing = no section. Give a one-line reason for each."
    )
    result = await run_coordinator(prompt, build_coordinator_options(settings, COVERAGE_SCHEMA, with_agents=False))
    if result["output"] is None:
        raise RuntimeError("assess_coverage() returned no coverage")
    return result["output"]["coverage"]
```

Its prompt is logged as `MODEL INPUT   prompt       [coordinator] Topic: ...` by `run_coordinator()`; its answer is the `structured` line with `{'coverage': [...]}`.

| Part | What it does | Seen in the real run |
|------|--------------|----------------------|
| `Must cover at least: {must_cover}` | Anchors the list to `REQUIRED`, so a category with no section still gets rated | Round 1 of `narrow`: only 2 sections, yet geothermal, tidal, biomass and fusion were rated `missing` |
| "plus any other major category of the topic" | Lets the coordinator add categories beyond `REQUIRED` | Hydropower and green hydrogen in `narrow` (8 entries); CSP, wave/ocean thermal, green hydrogen and emerging technologies in `full` (11 entries) |
| The rubric (`web findings, document findings and a source id`) | Defines each status by what the section contains | The `thinking` lines apply it literally: "missing all three elements rather than just one" |
| `with_agents=False` | No Agent tool, no spokes, no research tools: the coordinator only judges | No `tool_use` line in any assessment call, only `structured` |
| `RuntimeError` on `None` | An assessment that failed doesn't pass as "no gaps" | Never raised in the real run |

**Agentic concept:** evaluation is a separate coordinator call with its own contract. The coordinator, not a subagent, judges coverage, because only it holds the whole report and the whole topic.

> **The open clause has a cost.** "Any other major category" made the denominator grow with categories the mock corpus has no source for (green hydrogen, CSP, wave and ocean thermal, emerging technologies). Those can never become `well_covered`, so 100% was out of reach in both 3-round runs. That's why the cap fired (section 5).

---

### 4.6 `coverage_percent()`: Python counts

```python
def coverage_percent(coverage: list[dict]) -> int:
    """Counted in Python from the statuses, never parsed from Claude's prose (01 C7)."""
    return round(100 * sum(c["status"] == "well_covered" for c in coverage) / len(coverage))
```

| Assessment (real) | `well_covered` / entries | `coverage_percent()` |
|-------------------|--------------------------|----------------------|
| `narrow` round 1, `capped` round 1 | 2 / 8 | 25 |
| `narrow` rounds 2 and 3 | 7 / 8 | 88 (87.5 rounded) |
| `full` rounds 1 and 2 | 6 / 11 | 55 (54.5 rounded) |
| `full` round 3 | 7 / 11 | 64 (63.6 rounded) |

**Why it matters:** the number that decides the stop is computed, not read from Claude's text. `partial` counts as a gap, the same as `missing`.

**Agentic concept:** deterministic control around a probabilistic judgment. The *count* is deterministic; the *ratings* still come from Claude and can change between rounds (section 5.3 shows Fusion rated `missing`, then `partial`, then `well_covered`).

---

### 4.7 `merge_sections()`: keep every round's results

```python
def merge_sections(report_sections: list[dict], new_sections: list[dict]) -> list[dict]:
    """Keep every round's results: a re-delegated subtopic's new section replaces its old one (C13)."""
    merged = {section["subtopic"].lower(): section for section in report_sections}
    merged.update({section["subtopic"].lower(): section for section in new_sections})
    return list(merged.values())
```

**Why it matters:** a follow-up round returns sections for the gaps only. Without the merge, round 2's report would lose solar and wind. The key is the subtopic name, lower-cased, so a re-delegated subtopic replaces its old section.

Real section counts sent to `assess_coverage()`: `narrow` 2 → 8 → 8; `capped` 2; `full` 9 → 12 → 12.

**Edge case seen in the real run:** the key is the exact name. In `full`, the assessor renamed "Emerging and experimental renewables (..., perovskite **tandem cells**, ...)" to "(..., perovskite **tandem**, ...)". That gap name went into round 2, so the merge kept **both** sections: the final report has two "Emerging and experimental renewables" sections. Names that drift between rounds defeat a merge keyed on names.

**Agentic concept:** aggregation across rounds, owned by the coordinator's code.

---

### 4.8 `research()`: the refinement loop

#### a) Start: decompose only when no subtopics are given

```python
async def research(settings: Settings, topic: str, max_iterations: int, subtopics: list[str] | None = None) -> dict:
    """The refinement loop (C16): delegate, assess, then stop or re-delegate the gaps."""
    subtopics = subtopics or await decompose(settings, topic)
    sections: list[dict] = []
    gap_notes: dict[str, str] | None = None
    history: list[dict[str, Any]] = []
```

- Runs `narrow` and `capped` pass `NARROW`, so `decompose()` never runs. Run `full` passes `None`, so it decomposes first.
- `gap_notes` starts as `None`: round 1 is an ordinary delegation, with no `Fix only these gaps:` lines.
- `history` keeps one item per round: that round's Agent calls and its coverage. `main()` reads round 1 from it.

#### b) One round: delegate, merge, assess, count

```python
    for iteration in range(1, max_iterations + 1):
        round_result = await delegate(settings, topic, subtopics, gap_notes)
        sections = merge_sections(sections, round_result["sections"])
        coverage = await assess_coverage(settings, topic, sections, REQUIRED)
        percent = coverage_percent(coverage)
        gaps = [c for c in coverage if c["status"] != "well_covered"]
        history.append({"agent_calls": round_result["agent_calls"], "coverage_percent": percent})
        log.info("iteration %d: delegated %d -> coverage %d%% -> gaps %s",
                 iteration, len(subtopics), percent, [g["subtopic"] for g in gaps])
```

- Two `query()` calls per round: `delegate()` (with spokes) and `assess_coverage()` (without).
- The `log.info` writes the `iteration n: delegated k -> coverage p% -> gaps [...]` line. `k` is the number of subtopics delegated **this** round, so you can see the rounds narrow down: `narrow` delegated 2, then 6, then 1.

#### c) The primary stop

```python
        if percent >= COVERAGE_THRESHOLD:  # the primary stop: a quality threshold (C17)
            return {"sections": sections, "coverage_percent": percent, "complete": True, "history": history}
```

Never true in the real run: the best score was 88%.

#### d) Targeted follow-ups

```python
        # Targeted follow-ups: only the gaps, each with the reason the assessment gave (C15)
        subtopics = [g["subtopic"] for g in gaps]
        gap_notes = {g["subtopic"]: g["reason"] for g in gaps}
```

- The next round delegates **only** the gap names, and `delegate()` writes one `- {subtopic}: {reason}` line per gap.
- The gap names are the assessor's names, not the original subtopics. That's how `narrow` round 2 delegated "geothermal", "tidal", "biomass", "fusion", "hydropower" and "green hydrogen": six categories the starting list never had.

#### e) The fallback stop

```python
    # The fallback stop: the cap, with a warning and the partial report (C17)
    log.warning("Coverage %d%% after %d iteration(s); gaps: %s", percent, max_iterations, subtopics)
    return {"sections": sections, "coverage_percent": percent, "complete": False, "history": history}
```

- Reached in **all three** real runs.
- `subtopics` here holds the gaps of the last assessment (step d ran before the loop ended), so the warning names exactly what is still open.
- The partial report is still returned, flagged `complete: False`. The caller gets everything that was found and knows it's incomplete.

**Agentic concept:** an iterative refinement loop with two exits. The threshold expresses "good enough"; the cap expresses "stop spending". Neither depends on the model agreeing.

---

### 4.9 `main()`: three runs, the diagnosis and two failure boundaries

#### a) Setup

```python
async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc2_refinement")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1
```

`setup_logging()` runs before any `query()`, so the log file exists before the first paid call. The log's name, `poc2_refinement_20261027_183353.log`, is the time of this call.

#### b) The runs and their failure boundaries

```python
    for name, subtopics, max_iterations in RUNS:
        try:
            report = await research(settings, TOPIC, max_iterations, subtopics)
        except (RuntimeError, ValueError) as exc:  # a coordinator step returned nothing usable: next run
            log.error("Run '%s' stopped: %s", name, exc)
            continue
        except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
            log.error("SDK error: %s", exc)
            return 1
```

| Exception | Raised by | Effect |
|-----------|-----------|--------|
| `RuntimeError` | `decompose()`, `delegate()` or `assess_coverage()` when `output` is `None` | Logs `Run '...' stopped: ...` and moves on to the **next run** |
| `ValueError` | `decompose()`: fewer than 5 subtopics, or duplicates | The same |
| `ClaudeSDKError` | The SDK (Claude Code missing, process crash) | Stops the script with exit code `1` |

No `error` line appears in the real log: every call returned usable output.

#### c) The diagnosis lines

```python
        first_round = report["history"][0]
        never_delegated = missing_categories([call["prompt"] for call in first_round["agent_calls"]])
        if never_delegated:  # the subagents did all they were asked: these categories were never asked for (C7)
            log.info("Never delegated in round 1: %s -> root cause: the coordinator's decomposition, not the subagents",
                     never_delegated)
        # A single-shot dispatcher would have stopped after round 1 (C18).
        log.info("Run '%s': dispatcher %d%% -> coordinator %d%% after %d round(s), categories still missing: %s",
                 name, first_round["coverage_percent"], report["coverage_percent"], len(report["history"]),
                 missing_categories([section["subtopic"] for section in report["sections"]]))
    return 0
```

| Line | What it checks | Real values |
|------|----------------|-------------|
| `Never delegated in round 1` | The required categories that **no round-1 Agent prompt** mentions: the briefs the subagents actually got | `narrow` and `capped`: `['geothermal', 'tidal', 'biomass', 'fusion']`; `full`: `['fusion']` |
| `dispatcher p%` | Round 1's coverage: the result a single-shot dispatcher such as `research_once()` (one round, no loop) would have stopped at | 25%, 25%, 55% |
| `coordinator q%` | The final coverage after the loop | 88%, 25%, 64% |
| `categories still missing` | The required categories that no **final section** names | `[]`, `['geothermal', 'tidal', 'biomass', 'fusion']`, `[]` |

**Why it matters:** the first line is the exam's diagnosis, made by code. It checks the Agent prompts, not the decomposition list, so it proves the categories were never **asked for**. The subagents can't be blamed for them.

---

### 4.10 `__main__`

```python
if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

`asyncio.run` starts the event loop, and `sys.exit` passes `main()`'s return value to the shell. The real log has no error line, so the script exited with `0`, even though every run ended at the cap: the cap is a warning, not a failure.

---

### 4.11 `delegate()` and `decompose()`: the jobs the loop calls (from `coordinator.py`)

```python
async def delegate(
    settings: Settings, topic: str, subtopics: list[str], gap_notes: dict[str, str] | None = None
) -> dict[str, Any]:
    """Jobs 2 and 3: brief both subagents, then merge their reports into one section per subtopic.

    The prompt names no subagent: Claude picks each one from its description (C2) and writes its prompt.
    """
    lines = [
        f'Research goal: a sourced overview of "{topic}" with key figures from Helios Institute sources.',
        f"Subtopics for this round (delegate only these, using these exact names): {json.dumps(subtopics)}",
    ]
    if gap_notes:  # a follow-up round: each gap with the reason it is a gap (POC 2)
        lines += ["Fix only these gaps:"] + [f"- {subtopic}: {reason}" for subtopic, reason in gap_notes.items()]
    lines.append("Delegate with one Agent call that finds sources for all of these subtopics, then one Agent call "
                 "that reads the documents those sources name. Return one section per subtopic.")
    result = await run_coordinator("\n".join(lines), build_coordinator_options(settings, SECTIONS_SCHEMA))
    if result["output"] is None:
        raise RuntimeError("delegate() returned no sections")
    return {"sections": result["output"]["sections"], "agent_calls": result["agent_calls"]}
```

**The one POC 2 addition is `gap_notes`.** In a follow-up round, each gap arrives with the reason the assessment gave. The coordinator then writes the subagents' briefs from those reasons. Real examples:

| Gap reason in the prompt | What the coordinator put in the brief |
|--------------------------|---------------------------------------|
| `tidal: No section yet. Tidal and wave/marine energy needs research.` (`narrow`, round 2) | `"tidal" (include wave/marine energy)` |
| `green hydrogen: ... It needs a different search approach or source.` (`narrow`, round 3) | Six alternative queries, from "hydrogen" to "renewable hydrogen" |
| `Fusion: ... the Aurora-3 412-second web claim and its attribution are unverified.` (`full`, round 3) | `please verify the claim that 'Aurora-3 sustained 412 seconds' and who it is attributed to`; then a doc-analyst brief to verify it in `HX-FUS-1` |

```python
async def decompose(settings: Settings, topic: str) -> list[str]:
    """Job 1: split the topic into subtopics. One call with no tools: the coordinator only thinks (C5)."""
    prompt = f"Decompose this research topic into subtopics. Do not delegate yet. Topic: {topic}"
    result = await run_coordinator(prompt, build_coordinator_options(settings, SUBTOPICS_SCHEMA, with_agents=False))
    if result["output"] is None:
        raise RuntimeError("decompose() returned no subtopics")
    subtopics = result["output"]["subtopics"]
    # The breadth rule lives in COORDINATOR_PROMPT; Python checks the part it can check, deterministically.
    if len(subtopics) < 5 or len({s.lower() for s in subtopics}) < len(subtopics):
        raise ValueError(f"need at least 5 distinct subtopics, got {subtopics}")
    return subtopics
```

Only run `full` calls it. In the real run it returned **9** subtopics, one more than `COORDINATOR_PROMPT`'s "5 to 8". The Python check enforces only the minimum, so 9 passed. Fusion was not among them.

---

### 4.12 `run_coordinator()`: one call, its delegation record (from `coordinator.py`)

```python
async def run_coordinator(prompt: str, options: ClaudeAgentOptions) -> dict[str, Any]:
    ...
    log.info("MODEL INPUT   prompt       [coordinator] %s", prompt)
    agent_names: dict[str, str] = {}  # Agent call id -> subagent name, for the log tags
    agent_calls: dict[str, dict[str, Any]] = {}
    output, subtype = None, None
    try:
        async for message in query(prompt=prompt, options=options):
            log_model_io(message, agent_names)
            if isinstance(message, AssistantMessage) and message.parent_tool_use_id is None:  # the hub's own response
                for block in message.content:
                    if isinstance(block, ToolUseBlock) and block.name in ("Agent", "Task"):  # "Task" on older versions
                        agent_calls[block.id] = {"id": block.id, "subagent_type": block.input.get("subagent_type"),
                                                 "prompt": block.input.get("prompt", ""), "report": None}
            elif isinstance(message, UserMessage) and isinstance(message.content, list):
                for block in message.content:
                    # A subagent's report is the tool result of the Agent call that spawned it (same id).
                    if isinstance(block, ToolResultBlock) and block.tool_use_id in agent_calls:
                        agent_calls[block.tool_use_id]["report"] = text_of(block.content)
            elif isinstance(message, ResultMessage):
                subtype = message.subtype
                if message.subtype == "success":  # JSON comes only from structured_output, never parsed from text
                    output = message.structured_output if options.output_format else message.result
            # No `break`: a few system events can still arrive after the ResultMessage.
    except ResultError as exc:  # raised AFTER the error ResultMessage (already logged), e.g. error_max_turns
        log.error("The coordinator call failed: %s", exc)
    return {"output": output, "agent_calls": list(agent_calls.values()), "subtype": subtype}
```

What POC 2 relies on:
- **`agent_calls`** carries each Agent call's `prompt`. `research()` stores it in `history`, and `main()` checks round 1's prompts for categories never delegated.
- **`output`** is set only on `success`, from `structured_output`. Every `stop_reason` in the log is `tool_use`, so a check on `end_turn` would have thrown all 15 results away.
- **`log_model_io()`** writes every `MODEL OUTPUT` / `MODEL INPUT   tool_result` line. The `log.info` at the top writes the `MODEL INPUT   prompt` line. The `log.error` would write `The coordinator call failed: ...` (not in this log).

---

### 4.13 `build_coordinator_options()`: two shapes of the same call (from `research_setup.py`)

```python
def build_coordinator_options(
    settings: Settings, schema: dict[str, Any] | None = None, with_agents: bool = True
) -> ClaudeAgentOptions:
    """Options for one coordinator call. with_agents=False (decompose, assess coverage): the coordinator only thinks."""
    research_server = create_sdk_mcp_server(name=SERVER_NAME, version="1.0.0", tools=[web_search, read_document])
    return ClaudeAgentOptions(
        model=settings.model_id,
        system_prompt=COORDINATOR_PROMPT,  # the hub's role (C4); the subagents never see it
        output_format={"type": "json_schema", "schema": schema} if schema else None,  # JSON in .structured_output
        tools=["Agent"] if with_agents else [],  # the ONLY built-in tool is Agent, which spawns subagents (C9)
        agents=AGENTS if with_agents else None,  # the two spokes
        mcp_servers={SERVER_NAME: research_server} if with_agents else {},  # the mock tools, used by the subagents
        allowed_tools=["Agent", WEB_SEARCH, READ_DOCUMENT],  # no permission prompts
        disallowed_tools=["Agent(fork)"],  # no forks: a fork inherits the coordinator's whole conversation (E1)
        setting_sources=[],  # ignore ~/.claude settings, CLAUDE.md and hooks: the same run on any machine
        env={
            "ENABLE_TOOL_SEARCH": "false",  # send all tool schemas up front: no ToolSearch calls
            "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",  # subagents run in the foreground: wait for each report (E2)
            "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",  # only our two spokes, no general-purpose fallback (E3)
        },
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=settings.max_turns,  # safety cap per coordinator call (01 C16)
        max_budget_usd=settings.max_budget_usd,  # cost guard per call, subagents included
    )
```

| Option | `delegate()` | `decompose()`, `assess_coverage()` | Agentic concept |
|--------|--------------|------------------------------------|-----------------|
| `system_prompt=COORDINATOR_PROMPT` | yes | yes | **One role for every coordinator call.** The assessor is the hub, told to "judge coverage honestly". |
| `output_format` | `SECTIONS_SCHEMA` | `SUBTOPICS_SCHEMA` / `COVERAGE_SCHEMA` | **Structured hand-off.** Every call in the log ends with a `structured` line. |
| `tools` | `["Agent"]` | `[]` | **Delegation is a tool.** Without it, the coordinator can only think and answer. |
| `agents`, `mcp_servers` | `AGENTS`, the research server | `None`, `{}` | The spokes exist only in delegation calls. |
| `thinking` | adaptive, summarized | the same | **Visible reasoning.** 6 `thinking` lines in this log, all from the coordinator. |
| `max_turns`, `max_budget_usd` | per call | per call | Guardrails **inside** one call. `MAX_ITERATIONS` is the guardrail **across** calls. |

The other options (`allowed_tools`, `disallowed_tools`, `setting_sources`, the three `env` switches) are explained in the POC 1 article; POC 2 uses them unchanged.

---

### 4.14 `REQUIRED`, `missing_categories()` and the corpus (from `research_setup.py`)

```python
# category -> (words web_search matches, doc id, web_search fact, read_document fact)
CORPUS = {
    "solar": (("solar", "photovoltaic"), "HX-SOL-7",
              "solar capacity grew 31% in 2025", "utility-scale cost fell to $27.40/MWh"),
    ...
    "tidal": (("tidal", "wave", "ocean", "marine"), "HX-TID-4",
              "tidal stream capacity reached 1.9 GW", "the Kestrel Strait array ran at a 37.5% capacity factor"),
    ...
    "fusion": (("fusion",), "HX-FUS-1",
               "the Aurora-3 test reactor held plasma for 412 seconds", "a 140 MW grid pilot is planned for 2034"),
}

# What a full report on "renewable energy technologies" must cover (C8). No decomposition prompt lists these:
# the coordinator has to find the breadth itself.
REQUIRED = ["solar", "wind", "geothermal", "tidal", "biomass", "fusion"]


def missing_categories(texts: list[str]) -> list[str]:
    """The REQUIRED categories that none of the texts mentions (by the words web_search matches)."""
    joined = " ".join(texts).lower()
    return [category for category in REQUIRED if not any(word in joined for word in CORPUS[category][0])]
```

- `CORPUS` has 7 categories: the 6 in `REQUIRED` plus hydropower. **Anything else has no source**: green hydrogen, concentrated solar, wave and ocean thermal energy, airborne wind and the other emerging technologies. That's the ceiling the loop ran into.
- `web_search()` matches words in the query, so it returns loose matches. "Concentrated solar power ..." returned the general solar line, "wave and ocean thermal energy" returned the tidal line (tidal's words include "wave" and "ocean"), and the long "Emerging ... (airborne wind, space-based solar, ...)" query returned the solar and the wind lines. The assessor correctly refused to count these loose matches as coverage.
- `missing_categories()` is used twice in `main()`: on round 1's Agent prompts (root cause) and on the final section names (what the report still lacks).

The tools themselves (`web_search`, `read_document`, the `is_error` result for a guessed id) are unchanged from POC 1. In this log no `read_document` call used a guessed id: `is_error` is `None` on every result.

---

### 4.15 `Settings` and the log helpers (from `common.py`)

```python
@dataclass(frozen=True)
class Settings:
    model_id: str  # MODEL_ID: the Claude model that runs the coordinator (the subagents inherit it)
    max_turns: int  # MAX_TURNS: safety cap on tool-use turns per coordinator call
    max_budget_usd: float  # MAX_BUDGET_USD: cost guard per coordinator call, its subagents included
```

```python
def setup_logging(script_name: str) -> None:
    """Log to the console and to logs/<script>_<time>.log, so a paid run can be re-read later."""
    log_dir = POC_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"{script_name}_{datetime.now():%Y%m%d_%H%M%S}.log"
    formatter = logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    ...
```

- The same `Settings` object serves all 15 calls. `max_turns` and `max_budget_usd` apply **per call**, so a 3-round run can spend up to 6 × `max_budget_usd` (7 × with `decompose()`). The iteration cap is what bounds the whole run.
- The formatter writes only the time and the message, so the `log.warning` cap line has no `WARNING` prefix in the file.
- `log_model_io()` (shown in the table in 3.2) turns each stream message into one line and tags it with the agent. A `ThinkingBlock` is logged only when its text is non-empty.

---

## 5. Turn-by-turn trace of each run (real output)

Each trace below is the real run from `logs/poc2_refinement_20261027_183353.log` (2026-10-27, 18:33:53 to 18:38:05: 4 min 12 s for all 15 `query()` calls). Each log line points back to the statement that wrote it (section 3.2's table).

How to read the log blocks:
- In the log file, every entry is one line. Here, each entry's header (time, `MODEL INPUT` or `MODEL OUTPUT`, kind, `[agent]`) stays on its first line, and its payload is pretty-printed underneath: one key or list item per line.
- Long text wraps onto a deeper-indented line. A `\n` inside a string ends the line, as it does in the real text.
- `...` marks text that was cut. A line that starts with `...` summarizes log lines left out, such as a subagent's research calls with what each returned.

### 5.1 Run `narrow`: start from solar and wind, repair the gaps

**Real log (condensed):**

```
── round 1 ───────────────────────────────────────────────────────────────────────────────

18:33:53  MODEL INPUT   prompt       [coordinator]
          Research goal: a sourced overview of "renewable energy technologies" with key
            figures from Helios Institute sources.
          Subtopics for this round (delegate only these, using these exact names): ["solar
            power", "wind power"]
          Delegate with one Agent call that finds sources for all of these subtopics, then
            one Agent call that reads the documents those sources name. Return one section
            per subtopic.

18:33:57  MODEL OUTPUT  tool_use     [coordinator]
          Agent {'description': 'Find sources', 'subagent_type': 'web-searcher',
                 'prompt': 'Research goal: a sourced overview of "renewable energy
                     technologies" with key figures from Helios Institute sources. Find
                     Helios Institute sources for exactly these subtopics: "solar power"
                     and "wind power". For each subtopic, report the key figure shown in
                     search results and the exact document id that holds the full analysis
                     (e.g. HX-SOL-7). Report per subtopic.'}
          (id=toolu_01YH3adjwNbSjQYi4MTTj12i)

18:33:58  ... 2 × web_search [web-searcher] and their tool_results, all is_error=None:
              'solar power' → HX-SOL-7
              'wind power'  → HX-WND-2

18:34:00  MODEL INPUT   tool_result  [coordinator]
          [{'type': 'text',
            'text': '[Subagent hand-back] ... The report follows:\n
                  **Solar power**\n
                  - Key figure: solar capacity grew 31% in 2025 (Helios Review 2026).\n
                  - Document id: HX-SOL-7\n
                  \n
                  **Wind power**\n
                  - Key figure: offshore wind added 19.6 GW in 2025 (Helios Review 2026).
                    This figure covers offshore wind only, not total wind capacity.\n
                  - Document id: HX-WND-2\n
                  \n
                  Each search returned one result, and I used only what those results
                    said.\n
                agentId: a30997290a9e1b26a\n
                <usage>subagent_tokens: 1896\n
                tool_uses: 2\n
                duration_ms: 3272</usage>'}]
          (tool_use_id=toolu_01YH3adjwNbSjQYi4MTTj12i, is_error=None)

18:34:03  MODEL OUTPUT  tool_use     [coordinator]
          Agent {'description': 'Read documents', 'subagent_type': 'doc-analyst',
                 'prompt': 'Research goal: a sourced overview of "renewable energy
                     technologies" with key figures from Helios Institute sources. Read
                     these two Helios documents by exact id and extract key figures for
                     each subtopic: "solar power" -> HX-SOL-7 (search snippet: solar
                     capacity grew 31% in 2025); "wind power" -> HX-WND-2 (search snippet:
                     offshore wind added 19.6 GW in 2025, offshore only, not total wind).
                     Report key figures per subtopic, noting whether figures are
                     onshore/offshore/total and units/years.'}
          (id=toolu_016V8VNqRXpPncQGUCiyE95d)

18:34:05  ... 2 × read_document [doc-analyst] and their tool_results, all is_error=None:
              'HX-SOL-7' → utility-scale cost fell to $27.40/MWh.
              'HX-WND-2' → the average capacity factor reached 41.3%.

18:34:14  MODEL OUTPUT  structured   [coordinator]
          {'sections': [
              {'subtopic': 'solar power',
               'web_findings': 'Search result (Helios Review 2026): solar capacity grew
                   31% in 2025. Full analysis is in HX-SOL-7.',
               'document_findings': 'HX-SOL-7 gives utility-scale solar cost fell to
                   $27.40/MWh. The document does not state the year ...',
               'sources': ['HX-SOL-7', 'Helios Review 2026']},
              {'subtopic': 'wind power',
               'web_findings': 'Search result (Helios Review 2026): offshore wind added
                   19.6 GW in 2025. This covers offshore wind ...',
               'document_findings': 'HX-WND-2 gives an average capacity factor of 41.3%.
                   The document does not say whether this is ...',
               'sources': ['HX-WND-2', 'Helios Review 2026']}
          ]}
          (id=toolu_015B6d4Sah5e8FgjzfCF8yzr)
18:34:14  MODEL OUTPUT  stop_reason  [coordinator] tool_use  (loop result: success)

18:34:15  MODEL INPUT   prompt       [coordinator]
          Topic: renewable energy technologies. Must cover at least: ['solar', 'wind',
            'geothermal', 'tidal', 'biomass', 'fusion']. Report sections so far: [ ...2
            sections: solar power, wind power... ]. List every category this topic needs
            ... Give a one-line reason for each.

18:34:20  MODEL OUTPUT  structured   [coordinator]
          {'coverage': [
              {'subtopic': 'solar', 'status': 'well_covered',
               'reason': 'Section has web findings, document findings and source ids
                   (HX-SOL-7) ...'},
              {'subtopic': 'wind', 'status': 'well_covered',
               'reason': 'Section has web findings, document findings and source ids
                   (HX-WND-2) ...'},
              {'subtopic': 'geothermal', 'status': 'missing',
               'reason': 'No section yet.'},
              {'subtopic': 'tidal', 'status': 'missing',
               'reason': 'No section yet. Tidal and wave/marine energy needs research.'},
              {'subtopic': 'biomass', 'status': 'missing', 'reason': 'No section yet.'},
              {'subtopic': 'fusion', 'status': 'missing',
               'reason': 'No section yet. It is an experimental category.'},
              {'subtopic': 'hydropower', 'status': 'missing',
               'reason': 'Major mainstream renewable category with no section yet.'},
              {'subtopic': 'green hydrogen', 'status': 'missing',
               'reason': 'Emerging category with no section yet. It is an energy carrier
                   and ...'}
          ]}
          (id=toolu_01Xuzq6RPumTjpDdZRuEmt2Z)
18:34:20  MODEL OUTPUT  stop_reason  [coordinator] tool_use  (loop result: success)

18:34:21  iteration 1: delegated 2 -> coverage 25% -> gaps ['geothermal', 'tidal',
            'biomass', 'fusion', 'hydropower', 'green hydrogen']

── round 2 ───────────────────────────────────────────────────────────────────────────────

18:34:21  MODEL INPUT   prompt       [coordinator]
          Research goal: a sourced overview of "renewable energy technologies" with key
            figures from Helios Institute sources.
          Subtopics for this round (delegate only these, using these exact names):
            ["geothermal", "tidal", "biomass", "fusion", "hydropower", "green hydrogen"]
          Fix only these gaps:
          - geothermal: No section yet.
          - tidal: No section yet. Tidal and wave/marine energy needs research.
          - biomass: No section yet.
          - fusion: No section yet. It is an experimental category.
          - hydropower: Major mainstream renewable category with no section yet.
          - green hydrogen: Emerging category with no section yet. It is an energy carrier
            and could be folded in with other emerging technologies.
          Delegate with one Agent call that finds sources for all of these subtopics, then
            one Agent call that reads the documents those sources name. Return one section
            per subtopic.

18:34:25  MODEL OUTPUT  tool_use     [coordinator]
          Agent {'description': 'Find Helios sources', 'subagent_type': 'web-searcher',
                 'prompt': 'Research goal: ... Find Helios Institute sources for each of
                     these exact subtopics: "geothermal", "tidal" (include wave/marine
                     energy), "biomass", "fusion", "hydropower", "green hydrogen". ...'}
          (id=toolu_01VxKb1ScB2gaWPxvT9ZveAC)

18:34:27  ... 6 × web_search [web-searcher] and their tool_results, all is_error=None:
              'geothermal'               → HX-GEO-3
              'tidal wave marine energy' → HX-TID-4
              'biomass'                  → HX-BIO-6
              'fusion'                   → HX-FUS-1
              'hydropower'               → HX-HYD-5
              'green hydrogen'           → "No Helios results for 'green hydrogen'."

18:34:34  MODEL OUTPUT  tool_use     [coordinator]
          Agent {'description': 'Read Helios documents', 'subagent_type': 'doc-analyst',
                 'prompt': 'Research goal: ... HX-GEO-3 (subtopic "geothermal"; search
                     noted output rose 8.7%), HX-TID-4 (subtopic "tidal"; search noted
                     tidal stream capacity 1.9 GW; note whether it covers wave/marine),
                     ... Green hydrogen had no document found; do not read anything for
                     it. ...'}
          (id=toolu_01PWe3BMFx1ztKhhFUmzfXm9)

18:34:36  ... 5 × read_document [doc-analyst] and their tool_results, all is_error=None:
              'HX-GEO-3' → enhanced-geothermal pilot wells reached 245 °C.
              'HX-TID-4' → the Kestrel Strait array ran at a 37.5% capacity factor.
              'HX-BIO-6' → waste feedstocks made up 63% of supply.
              'HX-FUS-1' → a 140 MW grid pilot is planned for 2034.
              'HX-HYD-5' → pumped-storage capacity rose to 212 GW.

18:34:47  MODEL OUTPUT  structured   [coordinator]
          {'sections': [
              {'subtopic': 'geothermal',
               'web_findings': 'Search result (HX-GEO-3): geothermal output rose 8.7%.',
               'document_findings': 'HX-GEO-3: enhanced-geothermal pilot wells reached
                   245 °C (no year given). The 8.7% output rise was ...',
               'sources': ['HX-GEO-3']},
              ... tidal, biomass, fusion, hydropower: the same shape ...
              {'subtopic': 'green hydrogen',
               'web_findings': 'No Helios results were found for green hydrogen.',
               'document_findings': 'No document was found, so none was read. This
                   subtopic is not covered. Coverage is incomplete ...',
               'sources': []}
          ]}
          (id=toolu_01UukrskYx8LHcndiJNQ2xEi)

18:34:48  MODEL INPUT   prompt       [coordinator]
          Topic: renewable energy technologies. Must cover at least: ['solar', 'wind',
            'geothermal', 'tidal', 'biomass', 'fusion']. Report sections so far: [ ...8
            sections: solar power, wind power, geothermal, tidal, biomass, fusion,
            hydropower, green hydrogen... ]. List every category this topic needs ... Give
            a one-line reason for each.

18:34:54  MODEL OUTPUT  thinking     [coordinator]
          I'm applying the coverage definition structurally: solar, wind, geothermal,
            tidal, biomass, fusion, and hydropower all have web findings, document
            findings, and a source id, so they count as well_covered even though some like
            tidal have gaps on related topics like wave/marine energy.
          Green hydrogen stands out as a section with no actual findings or sources, so
            despite having a heading it effectively counts as missing. I'll finalize the
            coverage list with these classifications.

18:34:56  MODEL OUTPUT  structured   [coordinator]
          {'coverage': [
              ... solar, wind, geothermal, tidal, biomass, fusion, hydropower:
                  'well_covered' ...
              {'subtopic': 'green hydrogen', 'status': 'missing',
               'reason': 'The section is empty: no web findings, no document and no source
                   ids. It needs a different search approach or source.'}
          ]}
          (id=toolu_01HD1r19A34RHTiMh6WqrtAS)

18:34:57  iteration 2: delegated 6 -> coverage 88% -> gaps ['green hydrogen']

── round 3 (traced in full in 3.2) ───────────────────────────────────────────────────────

18:34:57  ... delegate(): 1 Agent call (web-searcher), 6 × web_search, all "No Helios
              results"; no doc-analyst call. assess_coverage(): 7 × 'well_covered', green
              hydrogen 'missing' ...

18:35:22  iteration 3: delegated 1 -> coverage 88% -> gaps ['green hydrogen']
18:35:22  Coverage 88% after 3 iteration(s); gaps: ['green hydrogen']
18:35:22  Never delegated in round 1: ['geothermal', 'tidal', 'biomass', 'fusion'] -> root
            cause: the coordinator's decomposition, not the subagents
18:35:22  Run 'narrow': dispatcher 25% -> coordinator 88% after 3 round(s), categories
            still missing: []
```

**Round by round:**

| Round | `subtopics` delegated | `gap_notes` | Agent calls | Research calls | Sections after merge | Rated / `well_covered` | `percent` |
|-------|----------------------|-------------|-------------|----------------|----------------------|------------------------|-----------|
| 1 | solar power, wind power | `None` | web-searcher, doc-analyst | 2 `web_search` + 2 `read_document` | 2 | 8 / 2 | 25 |
| 2 | geothermal, tidal, biomass, fusion, hydropower, green hydrogen | 6 reasons | web-searcher, doc-analyst | 6 `web_search` + 5 `read_document` | 8 | 8 / 7 | 88 |
| 3 | green hydrogen | 1 reason | web-searcher only | 6 `web_search` | 8 | 8 / 7 | 88 |

**What each step of round 2 did and which code ran:**

| Step | Agent | Claude asked for | Code that ran | Result |
|------|-------|------------------|---------------|--------|
| 1 | coordinator | `Agent` → `web-searcher`, brief = goal + the 6 gap names, tidal widened to "wave/marine" | The SDK starts the subagent | A subagent run under id `toolu_01VxK...` |
| 2 | web-searcher | 6 × `web_search` | `web_search()`: keyword match on `CORPUS` | 5 hits, 1 "No Helios results" (green hydrogen) |
| 3 | coordinator | `Agent` → `doc-analyst`, brief = 5 ids + "do not read anything for" green hydrogen | The SDK starts the subagent | `toolu_01PWe...` |
| 4 | doc-analyst | 5 × `read_document` | `read_document()`: exact id match | 5 document facts, `is_error=None` |
| 5 | coordinator | `StructuredOutput` with 6 sections | The built-in tool | `success` / `tool_use` |
| 6 | Python | none | `merge_sections()` → 8 sections; `assess_coverage()` → 7 × `well_covered` + 1 `missing` | `percent = 88`; `gaps = ['green hydrogen']` |

**Variable values at the end of the run:**

| Variable / field | Value |
|------------------|-------|
| `history` | `[{"agent_calls": [2 calls], "coverage_percent": 25}, {"agent_calls": [2], "coverage_percent": 88}, {"agent_calls": [1], "coverage_percent": 88}]` |
| `percent >= COVERAGE_THRESHOLD` | never true |
| `subtopics` at the warning | `['green hydrogen']` |
| `report["complete"]` | `False` |
| `report["sections"]` | 8 sections: solar power, wind power, geothermal, tidal, biomass, fusion, hydropower, green hydrogen (`sources: []`) |
| `never_delegated` | `['geothermal', 'tidal', 'biomass', 'fusion']` |
| `missing_categories(<section names>)` | `[]` |
| Exceptions | none |

**Lessons from the real data:**
- **The loop repaired the narrow decomposition.** Round 1 never asked for four required categories; round 2 asked for exactly those (plus hydropower and green hydrogen), and every required category ended `well_covered`. A dispatcher would have stopped at 25% with two sections.
- **Coverage is judged against the topic, not the report.** Round 1's report held 2 sections, and the assessment still listed 8 categories. That's what turned "2 out of 2 done" into 25%.
- **The diagnosis is mechanical.** No round-1 brief mentions geothermal, tidal, biomass or fusion. The subagents did everything they were asked; the categories were never asked for.
- **The gap reasons steered the briefs** (tidal widened to wave/marine in round 2; six alternative queries in round 3).
- **Round 3 was spent on a gap no source can fill.** The cap, not the threshold, ended the run. That's the fallback working as designed: a warning, `complete: False` and the partial report.

### 5.2 Run `capped`: the same start, a cap of 1

**Real log (condensed):**

```
18:35:22  MODEL INPUT   prompt       [coordinator]
          Research goal: ...
          Subtopics for this round (delegate only these, using these exact names): ["solar
            power", "wind power"]
          Delegate with one Agent call ...

18:35:26  MODEL OUTPUT  tool_use     [coordinator]
          Agent {'description': 'Find Helios sources', 'subagent_type': 'web-searcher',
                 'prompt': 'Research goal: ... Find Helios Institute sources for exactly
                     these subtopics: "solar power", "wind power". ...'}
          (id=toolu_01Tu2vqjMreBJPBviASoL2st)

18:35:27  ... 2 × web_search [web-searcher] and their tool_results, all is_error=None:
              'solar power' → HX-SOL-7
              'wind power'  → HX-WND-2

18:35:33  MODEL OUTPUT  tool_use     [coordinator]
          Agent {'description': 'Read Helios documents', 'subagent_type': 'doc-analyst',
                 'prompt': 'Research goal: a sourced overview of "renewable energy
                     technologies" with key figures from Helios Institute sources. Read
                     these Helios documents by exact id and extract their key figures:
                     HX-SOL-7 (subtopic "solar power"; search snippet: solar capacity grew
                     31% in 2025, Helios Review 2026) and HX-WND-2 (subtopic "wind power";
                     search snippet: offshore wind added 19.6 GW in 2025, Helios Review
                     2026). Report key figures per subtopic.'}
          (id=toolu_01GcAnEYKWj4EwLZBoCASCKw)

18:35:35  ... 2 × read_document [doc-analyst] and their tool_results, all is_error=None:
              'HX-SOL-7' → utility-scale cost fell to $27.40/MWh.
              'HX-WND-2' → the average capacity factor reached 41.3%.

18:35:41  MODEL OUTPUT  structured   [coordinator]
          {'sections': [
              {'subtopic': 'solar power', ...,
               'sources': ['HX-SOL-7', 'Helios Review 2026 (search snippet)']},
              {'subtopic': 'wind power', ...,
               'sources': ['HX-WND-2', 'Helios Review 2026 (search snippet)']}
          ]}
          (id=toolu_01XZd3AKWin9ggUbDFHN4pne)

18:35:42  MODEL INPUT   prompt       [coordinator]
          Topic: renewable energy technologies. Must cover at least: ['solar', 'wind',
            'geothermal', 'tidal', 'biomass', 'fusion']. Report sections so far: [ ...2
            sections: solar power, wind power... ]. List every category this topic needs
            ... Give a one-line reason for each.

18:35:47  MODEL OUTPUT  structured   [coordinator]
          {'coverage': [
              {'subtopic': 'solar', 'status': 'well_covered', ...},
              {'subtopic': 'wind', 'status': 'well_covered', ...},
              {'subtopic': 'geothermal', 'status': 'missing', ...},
              {'subtopic': 'tidal', 'status': 'missing', ...},
              {'subtopic': 'biomass', 'status': 'missing', ...},
              {'subtopic': 'fusion', 'status': 'missing', ...},
              {'subtopic': 'hydropower', 'status': 'missing', ...},
              {'subtopic': 'green hydrogen', 'status': 'missing', ...}
          ]}
          (id=toolu_01XkPbXeVQZekDK7QFUXJ2Ub)

18:35:48  iteration 1: delegated 2 -> coverage 25% -> gaps ['geothermal', 'tidal',
            'biomass', 'fusion', 'hydropower', 'green hydrogen']
18:35:48  Coverage 25% after 1 iteration(s); gaps: ['geothermal', 'tidal', 'biomass',
            'fusion', 'hydropower', 'green hydrogen']
18:35:48  Never delegated in round 1: ['geothermal', 'tidal', 'biomass', 'fusion'] -> root
            cause: the coordinator's decomposition, not the subagents
18:35:48  Run 'capped': dispatcher 25% -> coordinator 25% after 1 round(s), categories
            still missing: ['geothermal', 'tidal', 'biomass', 'fusion']
```

| Variable / field | Value |
|------------------|-------|
| `max_iterations` | `1` |
| `percent` | `25` (2 / 8) |
| `gaps` → `subtopics` at the warning | the 6 gap names, computed but never delegated |
| `report["complete"]` | `False` |
| `report["sections"]` | 2 (solar power, wind power) |
| `history` | 1 item: 2 Agent calls, 25% |
| `missing_categories(<section names>)` | `['geothermal', 'tidal', 'biomass', 'fusion']` |

**Lessons from the real data:**
- **This is what a dispatcher returns.** One round, no repair: `dispatcher 25% -> coordinator 25%`.
- **The cap still returns useful output.** The warning names the six open gaps, so a caller (or a person) knows exactly what is missing.
- **Same start, same 25%.** Rounds 1 of `narrow` and `capped` rated the same 8 categories the same way. The two runs differ only in `max_iterations`.

### 5.3 Run `full`: a real decomposition

**Real log (condensed):**

```
── decompose() ───────────────────────────────────────────────────────────────────────────

18:35:48  MODEL INPUT   prompt       [coordinator]
          Decompose this research topic into subtopics. Do not delegate yet. Topic:
            renewable energy technologies

18:35:52  MODEL OUTPUT  structured   [coordinator]
          {'subtopics': [
              'Solar photovoltaic (PV) technologies',
              'Concentrated solar power and solar thermal',
              'Onshore and offshore wind power',
              'Hydropower and pumped storage',
              'Bioenergy and biofuels',
              'Geothermal energy',
              'Marine energy (wave, tidal, ocean thermal)',
              'Green hydrogen and renewable-derived fuels',
              'Emerging and experimental renewables (airborne wind, space-based solar,
                  perovskite tandem cells, artificial photosynthesis)'
          ]}
          (id=toolu_01F9qpL5tPaCFmH4S75T36KA)

── round 1 ───────────────────────────────────────────────────────────────────────────────

18:35:58  MODEL OUTPUT  tool_use     [coordinator]
          Agent {'description': 'Find Helios sources', 'subagent_type': 'web-searcher',
                 'prompt': 'Research goal: ... Find Helios Institute sources for each of
                     these exact subtopics, ...\n
                     1. Solar photovoltaic (PV) technologies\n
                     ...\n
                     9. Emerging and experimental renewables (airborne wind, space-based
                       solar, perovskite tandem cells, artificial photosynthesis)\n
                     Report per subtopic: document id, key figure, and say explicitly if
                       no source was found.'}
          (id=toolu_019JgLABXyi2o3PwArkwypVL)

18:35:59  ... 9 × web_search [web-searcher] and their tool_results, all is_error=None:
              'Solar photovoltaic (PV) technologies' → HX-SOL-7
              'Concentrated solar power and solar thermal' → HX-SOL-7
              'Onshore and offshore wind power' → HX-WND-2
              'Hydropower and pumped storage' → HX-HYD-5
              'Bioenergy and biofuels' → HX-BIO-6
              'Geothermal energy' → HX-GEO-3
              'Marine energy (wave, tidal, ocean thermal)' → HX-TID-4
              'Green hydrogen and renewable-derived fuels' → "No Helios results for 'Green
                  hydrogen and renewable-derived fuels'."
              'Emerging and experimental renewables (airborne wind, space-based solar,
                  perovskite tandem cells, artificial photosynthesis)' → HX-SOL-7,
                  HX-WND-2

18:36:11  MODEL OUTPUT  tool_use     [coordinator]
          Agent {'description': 'Read Helios documents', 'subagent_type': 'doc-analyst',
                 'prompt': 'Research goal: ... Read each of these Helios documents by
                     exact id and extract key figures, noting which subtopic each covers
                     and whether it actually addresses the specifics listed:\n
                     - HX-SOL-7 (subtopics: "Solar photovoltaic (PV) technologies"; also a
                       loose match for "Concentrated solar power and solar thermal" and
                       "Emerging and experimental renewables (airborne wind, space-based
                       solar, perovskite tandem cells, artificial photosynthesis)").
                       Earlier search figure: solar capacity grew 31% in 2025.\n
                     ...\n
                     Report per document: key figures, and any explicit mention of
                       CSP/solar thermal, onshore wind, pumped storage, biofuels, wave,
                       ocean thermal, airborne wind, space solar, perovskite tandem,
                       artificial photosynthesis.'}
          (id=toolu_01U16QxjRgjYJoaBfpRTSQo1)

18:36:14  ... 6 × read_document [doc-analyst] and their tool_results, all is_error=None:
              'HX-SOL-7' → utility-scale cost fell to $27.40/MWh.
              'HX-WND-2' → the average capacity factor reached 41.3%.
              'HX-HYD-5' → pumped-storage capacity rose to 212 GW.
              'HX-BIO-6' → waste feedstocks made up 63% of supply.
              'HX-GEO-3' → enhanced-geothermal pilot wells reached 245 °C.
              'HX-TID-4' → the Kestrel Strait array ran at a 37.5% capacity factor.

18:36:29  MODEL OUTPUT  structured   [coordinator]
          {'sections': [
              {'subtopic': 'Solar photovoltaic (PV) technologies',
               'web_findings': 'HX-SOL-7: search snippet said solar capacity grew 31% in
                   2025.',
               'document_findings': 'HX-SOL-7 read: utility-scale cost fell to $27.40/MWh.
                   The 31% growth figure was not found in the ...',
               'sources': ['HX-SOL-7']},
              {'subtopic': 'Concentrated solar power and solar thermal',
               'web_findings': 'Only a loose match: HX-SOL-7 general solar result;
                   CSP/solar thermal not mentioned.',
               'document_findings': 'HX-SOL-7 does not mention CSP or solar thermal. No
                   dedicated source: coverage gap.',
               'sources': ['HX-SOL-7']},
              ... 7 more; 'Green hydrogen ...' and 'Emerging ...' have 'sources': [] ...
          ]}
          (id=toolu_01HDUZ3fVAwQfhyBmJxBozwR)

18:36:41  MODEL OUTPUT  thinking     [coordinator]
          ... Fusion appears to be missing from the emerging section entirely, ...
          For CSP specifically, the cited source doesn't actually address it, ... I'm
            leaning toward calling it "partial" ...

18:36:42  MODEL OUTPUT  structured   [coordinator]
          {'coverage': [
              {'subtopic': 'Solar (photovoltaic)', 'status': 'well_covered', ...},
              {'subtopic': 'Wind (onshore and offshore)', 'status': 'well_covered', ...},
              {'subtopic': 'Geothermal', 'status': 'well_covered', ...},
              {'subtopic': 'Tidal', 'status': 'well_covered', ...},
              {'subtopic': 'Biomass / bioenergy', 'status': 'well_covered', ...},
              {'subtopic': 'Fusion', 'status': 'missing',
               'reason': "This is a must-cover item, but no section exists for it. The
                   emerging-technologies section doesn't mention fusion, and no source was
                   searched or read."},
              {'subtopic': 'Hydropower and pumped storage', 'status': 'well_covered',
               ...},
              {'subtopic': 'Concentrated solar power and solar thermal',
               'status': 'partial',
               'reason': "A section exists, but its only source is the generic solar
                   document HX-SOL-7, which doesn't mention CSP or solar thermal. It has
                   no real CSP findings and needs a ..."},
              {'subtopic': 'Wave and ocean thermal energy', 'status': 'missing', ...},
              {'subtopic': 'Green hydrogen and renewable-derived fuels',
               'status': 'missing', ...},
              {'subtopic': 'Emerging and experimental renewables (airborne wind ...',
               'status': 'missing', ...}
          ]}
          (id=toolu_01WrzqdnBAT4KmbQaznFiVZd)

18:36:43  iteration 1: delegated 9 -> coverage 55% -> gaps ['Fusion', 'Concentrated solar
            power and solar thermal', 'Wave and ocean thermal energy', 'Green hydrogen and
            renewable-derived fuels', 'Emerging and experimental renewables (airborne
            wind, space-based solar, perovskite tandem, artificial photosynthesis)']

── round 2 ───────────────────────────────────────────────────────────────────────────────

18:36:43  MODEL INPUT   prompt       [coordinator]
          Research goal: ...
          Subtopics for this round (delegate only these, using these exact names) ...
          Fix only these gaps:
          - Fusion: This is a must-cover item, but no section exists for it. The
            emerging-technologies section doesn't mention fusion, and no source was ...
          - Concentrated solar power and solar thermal: A section exists, but its only
            source is the generic solar document HX-SOL-7, which doesn't mention CSP ...
          - Wave and ocean thermal energy: The marine section covers tidal only. Wave and
            ocean thermal energy have no findings and no sources.
          - Green hydrogen and renewable-derived fuels: The section is empty. It has no
            web findings, no document and no source id.
          - Emerging and experimental renewables (airborne wind, space-based solar,
            perovskite tandem, artificial photosynthesis): The section is empty. It has
            ...
          Delegate with one Agent call ...

18:36:49  ... 5 × web_search [web-searcher] and their tool_results, all is_error=None:
              'fusion' → HX-FUS-1
              'concentrated solar power and solar thermal' → HX-SOL-7
              'wave and ocean thermal energy' → HX-TID-4
              'green hydrogen and renewable-derived fuels' → "No Helios results for 'green
                  hydrogen and renewable-derived fuels'."
              'emerging and experimental renewables airborne wind, space-based solar,
                  perovskite tandem, artificial photosynthesis' → HX-SOL-7, HX-WND-2

18:37:01  ... 4 × read_document [doc-analyst] and their tool_results, all is_error=None:
              'HX-FUS-1' → a 140 MW grid pilot is planned for 2034.
              'HX-TID-4' → the Kestrel Strait array ran at a 37.5% capacity factor.
              'HX-SOL-7' → utility-scale cost fell to $27.40/MWh.
              'HX-WND-2' → the average capacity factor reached 41.3%.

18:37:12  MODEL OUTPUT  structured   [coordinator]
          {'sections': [
              {'subtopic': 'Fusion',
               'web_findings': 'Search found dedicated source HX-FUS-1. Search line:
                   Aurora-3 test reactor held plasma for 412 seconds (Helios Review
                   2026).',
               'document_findings': 'HX-FUS-1 states a 140 MW grid pilot is planned for
                   2034. The document did not confirm the Aurora-3 412-second figure or
                   the Helios Review ...',
               'sources': ['HX-FUS-1']},
              ... 4 more sections (CSP, wave and ocean thermal, green hydrogen, emerging),
                  each saying 'Gap remains' ...
          ]}
          (id=toolu_016DFodfNrTHZvLoQnF7wgry)

18:37:20  MODEL OUTPUT  structured   [coordinator]
          {'coverage': [
              {'subtopic': 'Solar (photovoltaic)', 'status': 'well_covered', ...},
              {'subtopic': 'Concentrated solar power and solar thermal',
               'status': 'partial', ...},
              {'subtopic': 'Wind (onshore and offshore)', 'status': 'well_covered', ...},
              {'subtopic': 'Geothermal', 'status': 'well_covered', ...},
              {'subtopic': 'Tidal / marine energy', 'status': 'well_covered', ...},
              {'subtopic': 'Biomass / bioenergy', 'status': 'well_covered', ...},
              {'subtopic': 'Fusion', 'status': 'partial',
               'reason': 'Section has a source (HX-FUS-1) and a 140 MW pilot by 2034
                   finding, but the Aurora-3 412-second web claim and its attribution are
                   unverified.'},
              {'subtopic': 'Hydropower and pumped storage', 'status': 'well_covered',
               ...},
              {'subtopic': 'Wave and ocean thermal energy', 'status': 'partial', ...},
              {'subtopic': 'Green hydrogen and renewable-derived fuels',
               'status': 'partial', ...},
              {'subtopic': 'Emerging and experimental renewables (airborne wind ...',
               'status': 'partial', ...}
          ]}
          (id=toolu_01KBwqW3peMZdD9fUZTCVy5o)

18:37:21  iteration 2: delegated 5 -> coverage 55% -> gaps ['Concentrated solar power and
            solar thermal', 'Fusion', 'Wave and ocean thermal energy', 'Green hydrogen and
            renewable-derived fuels', 'Emerging and experimental renewables (airborne
            wind, space-based solar, perovskite tandem, artificial photosynthesis)']

── round 3 ───────────────────────────────────────────────────────────────────────────────

18:37:26  MODEL OUTPUT  tool_use     [coordinator]
          Agent {'description': 'Find Helios sources', 'subagent_type': 'web-searcher',
                 'prompt': 'Research goal: a sourced overview of "renewable energy
                     technologies" with key figures from Helios Institute sources. Find
                     Helios Institute sources (document ids) for each of these exact
                     subtopics:\n
                     1. Concentrated solar power and solar thermal (previous source
                       HX-SOL-7 does not mention CSP; find a real CSP source)\n
                     2. Fusion (existing source HX-FUS-1 with a 140 MW pilot by 2034
                       finding; please verify the claim that \'Aurora-3 sustained 412
                       seconds\' and who it is attributed to)\n
                     3. Wave and ocean thermal energy (previous source HX-TID-4 is tidal
                       only; find wave/OTEC sources)\n
                     4. Green hydrogen and renewable-derived fuels (no source yet)\n
                     5. Emerging and experimental renewables (airborne wind, space-based
                       solar, perovskite tandem, artificial photosynthesis) (previous
                       sources HX-WND-2, HX-SOL-7 do not mention these)\n
                     For each subtopic report the document id(s), the key figure from the
                       search result line, and the exact wording. Say clearly if nothing
                       relevant is found; do not invent ids.'}
          (id=toolu_01WSvGRvAyHj3niNFn4Zk79x)

18:37:28  ... 5 × web_search [web-searcher] and their tool_results, all is_error=None:
              'concentrated solar power and solar thermal' → HX-SOL-7
              'fusion' → HX-FUS-1
              'wave and ocean thermal energy' → HX-TID-4
              'green hydrogen and renewable-derived fuels' → "No Helios results for 'green
                  hydrogen and renewable-derived fuels'."
              'emerging and experimental renewables' → "No Helios results for 'emerging
                  and experimental renewables'."

18:37:37  MODEL OUTPUT  thinking     [coordinator]
          I'll delegate to doc-analyst to read HX-FUS-1, since it's the only new relevant
            document — HX-SOL-7 and HX-TID-4 are already known not to cover this.

18:37:38  MODEL OUTPUT  tool_use     [coordinator]
          Agent {'description': 'Read fusion document', 'subagent_type': 'doc-analyst',
                 'prompt': 'Research goal: sourced overview of renewable energy
                     technologies with key figures from Helios Institute sources.
                     Subtopic: "Fusion". Please read document HX-FUS-1 and report its key
                     figures. Specifically verify: (a) the Aurora-3 test reactor plasma
                     duration (a search line said \'held plasma for 412 seconds\', Helios
                     Review 2026) and who/what organisation it is attributed to; (b) a
                     claimed 140 MW pilot by 2034. Quote exact wording, and state clearly
                     anything not found in the document.'}
          (id=toolu_01HTM64aYD2Xo4uPCRxKdmrx)

18:37:39  ... 1 × read_document [doc-analyst] and their tool_results, all is_error=None:
              'HX-FUS-1' → a 140 MW grid pilot is planned for 2034.

18:37:49  MODEL OUTPUT  structured   [coordinator]
          {'sections': [
              {'subtopic': 'Concentrated solar power and solar thermal', ...,
               'sources': []},
              {'subtopic': 'Fusion', ..., 'sources': ['HX-FUS-1']},
              {'subtopic': 'Wave and ocean thermal energy', ..., 'sources': []},
              {'subtopic': 'Green hydrogen and renewable-derived fuels', ...,
               'sources': []},
              {'subtopic': 'Emerging and experimental renewables (airborne wind ...', ...,
               'sources': []}
          ]}
          (id=toolu_01VJDCXFhs7qE15tUF9AfqQr)

18:38:04  MODEL OUTPUT  structured   [coordinator]
          {'coverage': [
              {'subtopic': 'Solar (photovoltaic)', 'status': 'well_covered', ...},
              {'subtopic': 'Concentrated solar power and solar thermal',
               'status': 'missing', ...},
              {'subtopic': 'Wind (onshore and offshore)', 'status': 'well_covered', ...},
              {'subtopic': 'Geothermal', 'status': 'well_covered', ...},
              {'subtopic': 'Tidal', 'status': 'well_covered', ...},
              {'subtopic': 'Biomass (bioenergy and biofuels)', 'status': 'well_covered',
               ...},
              {'subtopic': 'Fusion', 'status': 'well_covered',
               'reason': 'Has web findings, document findings and source HX-FUS-1. The
                   document only says a 140 MW grid pilot is planned for 2034. The
                   Aurora-3 412-second plasma claim rests on ...'},
              {'subtopic': 'Hydropower and pumped storage', 'status': 'well_covered',
               ...},
              {'subtopic': 'Wave and ocean thermal (OTEC) energy', 'status': 'missing',
               ...},
              {'subtopic': 'Green hydrogen and renewable-derived fuels',
               'status': 'missing', ...},
              {'subtopic': 'Emerging and experimental renewables (airborne wind ...',
               'status': 'missing', ...}
          ]}
          (id=toolu_01ByeuBT8VroFu5cZRF4RWMC)

18:38:05  iteration 3: delegated 5 -> coverage 64% -> gaps ['Concentrated solar power and
            solar thermal', 'Wave and ocean thermal (OTEC) energy', 'Green hydrogen and
            renewable-derived fuels', 'Emerging and experimental renewables (airborne
            wind, space-based solar, perovskite tandem, artificial photosynthesis)']
18:38:05  Coverage 64% after 3 iteration(s); gaps: ['Concentrated solar power and solar
            thermal', 'Wave and ocean thermal (OTEC) energy', 'Green hydrogen and
            renewable-derived fuels', 'Emerging and experimental renewables (airborne
            wind, space-based solar, perovskite tandem, artificial photosynthesis)']
18:38:05  Never delegated in round 1: ['fusion'] -> root cause: the coordinator's
            decomposition, not the subagents
18:38:05  Run 'full': dispatcher 55% -> coordinator 64% after 3 round(s), categories still
            missing: []
```

**The 11 rated categories, round by round** (from the three `coverage` lines):

| Category (assessor's name) | Round 1 | Round 2 | Round 3 | Why |
|----------------------------|---------|---------|---------|-----|
| Solar (photovoltaic) | `well_covered` | `well_covered` | `well_covered` | `HX-SOL-7` |
| Wind (onshore and offshore) | `well_covered` | `well_covered` | `well_covered` | `HX-WND-2` |
| Geothermal | `well_covered` | `well_covered` | `well_covered` | `HX-GEO-3` |
| Tidal | `well_covered` | `well_covered` | `well_covered` | `HX-TID-4` |
| Biomass | `well_covered` | `well_covered` | `well_covered` | `HX-BIO-6` |
| Hydropower and pumped storage | `well_covered` | `well_covered` | `well_covered` | `HX-HYD-5` |
| Fusion | `missing` | `partial` | `well_covered` | Never decomposed; section added in round 2; the 412 s claim "unverified" in round 2, accepted with a caveat in round 3 |
| Concentrated solar power and solar thermal | `partial` | `partial` | `missing` | Only the generic `HX-SOL-7` |
| Wave and ocean thermal energy | `missing` | `partial` | `missing` | Only the tidal `HX-TID-4` |
| Green hydrogen and renewable-derived fuels | `missing` | `partial` | `missing` | No source in `CORPUS` |
| Emerging and experimental renewables | `missing` | `partial` | `missing` | No source in `CORPUS` |
| **`coverage_percent()`** | **55** (6/11) | **55** (6/11) | **64** (7/11) | |

**Variable values at the end of the run:**

| Variable / field | Value |
|------------------|-------|
| `subtopics` from `decompose()` | 9 strings, no fusion; passes the `>= 5` and distinct checks |
| `history` | `[{"agent_calls": [2], "coverage_percent": 55}, {"agent_calls": [2], "coverage_percent": 55}, {"agent_calls": [2], "coverage_percent": 64}]` |
| `report["sections"]` | 12: the 9 from round 1, plus "Fusion", "Wave and ocean thermal energy" and a second "Emerging and experimental renewables (... perovskite tandem ...)" |
| `report["complete"]` | `False` |
| `never_delegated` | `['fusion']` |
| `missing_categories(<section names>)` | `[]`: all six required categories have a section |
| Exceptions | none |

**Lessons from the real data:**
- **The decomposition missed fusion again**, as in POC 1. Its "emerging and experimental" subtopic listed airborne wind, space-based solar, perovskite cells and artificial photosynthesis, but not fusion. The round-1 assessment caught it ("This is a must-cover item, but no section exists for it"), and round 2 repaired it. The loop fixed what the decomposition missed.
- **Objective 6 passed in part.** All six required categories have sections (`categories still missing: []`), but coverage ended at 64%, not 100%. The four open categories have no source in the corpus, and the assessor added them itself ("any other major category").
- **The ratings are a judgment and they moved.** Fusion went `missing` → `partial` → `well_covered`. Wave and ocean thermal, green hydrogen and emerging technologies went `missing` → `partial` → `missing`, and concentrated solar `partial` → `partial` → `missing`, although round 3 found nothing new for them. The rubric was the same in every call; the reading of it wasn't. Python's count is deterministic, but its input is not.
- **Round 2 spent its effort on loose matches.** The web-searcher's keyword matches returned `HX-SOL-7`, `HX-TID-4` and `HX-WND-2` again for CSP, wave and emerging technologies, and the doc-analyst re-read them to confirm they didn't apply. Round 3's coordinator learned from that: its `thinking` line skips the documents "already known not to cover this".
- **Names drifted between rounds**: "Wave and ocean thermal energy" became "Wave and ocean thermal (OTEC) energy", and one "Emerging" name lost the word "cells". Because `merge_sections()` keys on the name, the report ended with two "Emerging" sections.

### 5.4 The three runs side by side

| | `narrow` | `capped` | `full` |
|-|----------|----------|--------|
| Starting `subtopics` | `NARROW` (2) | `NARROW` (2) | `decompose()` → 9 |
| `max_iterations` | 3 | 1 | 3 |
| `query()` calls | 6 (3 × delegate + 3 × assess) | 2 | 7 (decompose + 3 × 2) |
| Agent calls per round | 2, 2, 1 | 2 | 2, 2, 2 |
| Research tool calls | 14 `web_search` + 7 `read_document` | 2 + 2 | 19 `web_search` + 11 `read_document` |
| Coverage per round (`history`) | 25 → 88 → 88 | 25 | 55 → 55 → 64 |
| Rated categories | 8 | 8 | 11 |
| Stop | cap (warning) | cap (warning) | cap (warning) |
| `complete` | `False` | `False` | `False` |
| Final sections | 8 | 2 | 12 |
| Never delegated in round 1 | geothermal, tidal, biomass, fusion | geothermal, tidal, biomass, fusion | fusion |
| Required categories still missing | none | geothermal, tidal, biomass, fusion | none |
| Every `message.subtype` / `stop_reason` | `success` / `tool_use` | `success` / `tool_use` | `success` / `tool_use` |
| `ResultError`, `RuntimeError`, `ValueError` | none | none | none |
| `thinking` lines | 3 | 0 | 3 |
| Wall time (from log) | 89 s (18:33:53 → 18:35:22) | 26 s (→ 18:35:48) | 137 s (→ 18:38:05) |

The log has no error line, so `main()` returned `0`.

---

## 6. Agentic AI concepts recap

| Concept | How this POC shows it |
|---------|-----------------------|
| **Iterative refinement** | `research()`: delegate → merge → assess → stop or re-delegate, up to `MAX_ITERATIONS` rounds |
| **Coordinator vs dispatcher** | Round 1's coverage (the dispatcher) next to the final coverage (the coordinator): 25% → 88% in `narrow` |
| **Coverage against the whole topic** | `assess_coverage()` rates every category the topic needs, including those with no section |
| **Structured evaluation** | `COVERAGE_SCHEMA`: an enum status and a required reason per category |
| **Model judges, code decides** | Claude rates; `coverage_percent()` counts; `COVERAGE_THRESHOLD` and `MAX_ITERATIONS` stop the loop |
| **Targeted re-delegation** | Only the gaps, each with its reason (`gap_notes` → `Fix only these gaps:`) |
| **Explicit context in follow-ups** | The coordinator turns each reason into the brief: "include wave/marine", six alternative queries, "verify the 412 s claim" |
| **Aggregation across rounds** | `merge_sections()` keeps earlier sections and replaces re-delegated ones |
| **Two stop conditions** | Threshold (quality) first, cap (cost and time) as the fallback, with a warning and a partial report |
| **Three levels of caps** | `MAX_ITERATIONS` across calls, `max_turns` / `max_budget_usd` per coordinator call, `maxTurns=15` per subagent |
| **Root-cause diagnosis** | `missing_categories()` on round 1's Agent prompts: the categories were never asked for |
| **Honest gaps** | "No Helios results", `sources: []`, and a coordinator that skips the doc-analyst when there is nothing to read |

---

## 7. Common mistakes this POC helps you avoid

1. **Stopping after one round.** One round is a dispatcher. `capped` shows what that returns: 25%.
2. **Judging coverage against the sections you have.** Two sections that are both complete are not a complete report. Rate the categories the topic needs.
3. **Re-running everything to fix a gap.** Re-delegate only the gaps; `merge_sections()` keeps the rest.
4. **Re-delegating without the reason.** A bare "geothermal" gets the same search again. "It needs a different search approach" got six new queries.
5. **Letting Claude decide when to stop.** Count the statuses in Python and compare with a fixed threshold.
6. **A loop with no cap.** Green hydrogen had no source. Without `MAX_ITERATIONS`, the loop would have kept searching for it.
7. **Treating the cap as a failure and throwing the work away.** Return the partial report, flagged incomplete, with the open gaps named.
8. **Confusing the caps.** `max_turns` limits one coordinator call; it can't stop a loop of calls. `MAX_ITERATIONS` does.
9. **Blaming the subagents for a missing category.** If no round-1 brief mentioned it, the decomposition is the root cause.
10. **A threshold the data can't reach.** An open-ended category list plus a 100% threshold can make the threshold unreachable. Decide what counts toward the threshold (for example the required list), or how a gap with no source is resolved.
11. **Merging on names that can drift.** The assessor renamed a category and the report ended with two sections for it.

---

## 8. Claude Architect exam lens

### 8.1 What the exam tests on this topic

The objectives come from `curriculum/01-Agentic-Architecture-&-Orchestration/02-raw-Multi-Agent-Orchestration.md`. POC 1 covers objectives 1 to 3 and the aggregation half of 4; POC 2 covers the coverage evaluation of 4, and 5 and 6.

| Exam objective | What a correct answer looks like | Where this POC shows it |
|----------------|----------------------------------|-------------------------|
| 1. A coordinator agent takes a broad research topic | The coordinator owns decomposition, subagent selection and aggregation, and now also evaluation and re-delegation. | `research()`: topic in, `{"sections", "coverage_percent", "complete", "history"}` out; `COORDINATOR_PROMPT` on every call, the assessment included |
| 2. Decompose into at least 5 subtopics covering the full breadth | Breadth, not count. A narrow decomposition is the root cause of missing categories. | Run `full`: 9 subtopics, no fusion; `Never delegated in round 1: ['fusion']`. Runs `narrow`/`capped`: the solar-and-wind failure pattern |
| 3. Two subagents with explicit context | Every brief, including each follow-up, carries the goal, the exact subtopics and the facts it needs. | Follow-up briefs carry the gap reasons and the known doc ids ("Green hydrogen had no document found; do not read anything for it") |
| 4. Aggregate and evaluate coverage completeness | Combine both subagents' results, then rate every category of the **whole topic**: well covered, partial, missing. Gaps trigger re-delegation. | `merge_sections()`; `assess_coverage()` + `COVERAGE_SCHEMA`; round 1 of `narrow` rated 4 categories `missing` with only 2 sections in the report |
| 5. Iterative refinement loop | Check coverage, find gaps, send targeted follow-ups for the gaps only, re-evaluate; stop at a threshold or a max iteration count. A single shot is a dispatcher. | `research()`; `COVERAGE_THRESHOLD`, `MAX_ITERATIONS`; `dispatcher 25% -> coordinator 88%` |
| 6. Test with renewable energy: all six categories, 100% | Final sections on solar, wind, geothermal, tidal, biomass and fusion; coverage evaluation at 100%. If only solar and wind appear, blame the decomposition. | Run `full`: all six present (`categories still missing: []`), but 64%, because the assessor added four categories the corpus can't serve; the cap ended the loop |

> **Exam tip:** the exam phrases this as "a coordinator vs a simple dispatcher". The answer that evaluates the output and re-delegates the gaps is the coordinator. Answers that only add more subagents, more turns or a bigger model don't change a dispatcher into a coordinator. Also expect "the report covers only solar and wind" to point at the decomposition, never at the subagents.

### 8.2 The same loop with the raw Messages API

The refinement loop is already plain Python in the POC, so it stays the same. What changes is the inside of each coordinator step. With the raw Messages API, `assess_coverage()` is one `messages.create` call with a JSON schema and no tools, and `delegate()` is POC 1's hand-written coordinator loop with its `agent` tool (see the POC 1 article, 8.2).

```python
import json

import anthropic

client = anthropic.Anthropic()
# MODEL_ID, COORDINATOR_PROMPT, REQUIRED, the schemas and merge_sections() are as in the POC. delegate() is POC 1's
# raw version, plus the optional gap_notes lines; it returns the round's sections.


def assess_coverage(topic: str, sections: list[dict], must_cover: list[str]) -> list[dict]:
    """One call, no tools: the coordinator only judges. The schema makes the status an enum."""
    prompt = (f"Topic: {topic}. Must cover at least: {must_cover}. Report sections so far: {json.dumps(sections)}. "
              "List every category this topic needs ... and rate each one ... Give a one-line reason for each.")
    response = client.messages.create(
        model=MODEL_ID, max_tokens=16000, system=COORDINATOR_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        # structured outputs: every object in the schema needs "additionalProperties": False
        output_config={"format": {"type": "json_schema", "schema": COVERAGE_SCHEMA}},
    )
    if response.stop_reason != "end_turn":  # max_tokens, refusal, ...: no usable JSON
        raise RuntimeError(f"assess_coverage() stopped with {response.stop_reason}")
    text = "".join(block.text for block in response.content if block.type == "text")
    return json.loads(text)["coverage"]


def research(topic: str, subtopics: list[str], max_iterations: int = 3, threshold: int = 100) -> dict:
    sections, gap_notes, history = [], None, []
    for iteration in range(1, max_iterations + 1):
        sections = merge_sections(sections, delegate(topic, subtopics, gap_notes))
        coverage = assess_coverage(topic, sections, REQUIRED)
        percent = round(100 * sum(c["status"] == "well_covered" for c in coverage) / len(coverage))
        history.append(percent)
        if percent >= threshold:
            return {"sections": sections, "coverage_percent": percent, "complete": True, "history": history}
        gaps = [c for c in coverage if c["status"] != "well_covered"]
        subtopics = [g["subtopic"] for g in gaps]
        gap_notes = {g["subtopic"]: g["reason"] for g in gaps}
    return {"sections": sections, "coverage_percent": percent, "complete": False, "history": history}
```

| Raw Messages API (you write it) | Agent SDK (`poc2_refinement.py`) |
|---------------------------------|----------------------------------|
| `assess_coverage()`: one `messages.create`, no `tools` | `assess_coverage()`: one `query()` with `tools=[]`, no agents (`with_agents=False`) |
| `output_config={"format": {"type": "json_schema", ...}}`; the final text is JSON, read with `json.loads()`; success is `stop_reason == "end_turn"` | `output_format`; Claude calls `StructuredOutput`; the code reads `structured_output`; success is `subtype == "success"` with `stop_reason == "tool_use"` |
| `delegate()`: your coordinator loop with an `agent` tool and `run_subagent()` | `delegate()`: one `query()` with `tools=["Agent"]` and `agents=AGENTS`; the SDK runs the subagents |
| The refinement loop in Python | The same refinement loop in Python |
| `max_iterations` of the refinement loop, plus each inner loop's own cap | `MAX_ITERATIONS`, plus `max_turns` per call and `maxTurns` per subagent |
| You add up every call's cost yourself | `max_budget_usd` per coordinator call; the loop's total is still yours to bound |

What doesn't change: the evaluation is a separate call with a fixed schema, Python counts and stops, and only the gaps go back out with their reasons.

### 8.3 Scenario questions

Try each one before reading the answer. These questions were written for this article to match the curriculum objectives above. They are not official exam questions.

---

**Scenario 1: Two sections, both perfect**

A coordinator's report on "renewable energy technologies" has two sections, solar and wind, each with web findings, document findings and a source. Its coverage check compares each section against what a good section needs and reports 100%. What's wrong?

- A. Nothing: both sections are complete.
- B. The check judges the sections it has, not the topic. It must rate every category the topic needs, so geothermal, tidal, biomass and fusion count as missing.
- C. The subagents should have added more figures to each section.
- D. The threshold should be 80%, not 100%.

**Answer: B.** Coverage is measured against the whole topic. A check that only looks at existing sections can never find a missing category. A and C confuse depth with breadth, and D lowers the bar without fixing the measurement. *POC link:* `assess_coverage()` passes `Must cover at least: {must_cover}` and asks for "every category this topic needs". In the real run, round 1 of `narrow` had 2 sections and scored 25%.

---

**Scenario 2: Who decides that the loop is done?**

A team's coordinator ends each assessment with "Coverage looks complete, I think we can stop." Their loop stops when this text contains "complete". Sometimes it stops with categories missing. What is the best fix?

- A. Ask Claude to write "COMPLETE" in capitals.
- B. Have Claude return a rating per category in a schema with an enum status, count the ratings in code, and stop on a fixed threshold.
- C. Let the subagents decide when to stop.
- D. Raise `max_turns`.

**Answer: B.** The model judges each category; the code decides whether the loop ends. That makes the stop deterministic and testable. A still parses prose, C hands the decision to agents that can't see the whole report, and D doesn't affect the stop. *POC link:* `COVERAGE_SCHEMA`, `coverage_percent()` and `if percent >= COVERAGE_THRESHOLD` in `research()`.

---

**Scenario 3: Fixing four missing categories**

After round 1, the coverage assessment lists geothermal, tidal, biomass and fusion as missing, and solar and wind as well covered. What should round 2 do?

- A. Re-run the whole pipeline with all six categories.
- B. Delegate only the four missing categories, each with the reason it's a gap, and merge the new sections with the existing ones.
- C. Ask the web-search subagent to search harder for solar and wind.
- D. Return the report; the loop has done its job.

**Answer: B.** Targeted re-delegation fixes the gaps without paying again for what is already well covered, and the reasons tell the subagents what to do differently. A wastes work and can lose good sections. C researches the wrong thing. D is a dispatcher. *POC link:* `subtopics = [g["subtopic"] for g in gaps]`, `gap_notes`, `merge_sections()`. In the real run, round 2 of `narrow` delegated only the gaps and reached 88%.

---

**Scenario 4: The gap that never closes**

A coordinator's loop keeps re-delegating "green hydrogen". Every search returns nothing, because the source system has no data on it. The loop has a coverage threshold of 100% and no other stop. What should the architect add?

- A. A larger model for the web-search subagent.
- B. A higher `max_turns` per call.
- C. A maximum iteration count. When it's reached, log a warning and return the partial report, marked incomplete, with the open gaps named.
- D. Remove green hydrogen from the report silently.

**Answer: C.** The threshold is the primary stop; the iteration cap is the safety net for gaps that can't be fixed. Returning the partial report keeps the work done so far and tells the caller what's missing. A and B can't create data that doesn't exist, and D hides the gap. *POC link:* the `log.warning(...)` and `"complete": False` after the loop in `research()`. In the real run: `Coverage 88% after 3 iteration(s); gaps: ['green hydrogen']`.

---

**Scenario 5: Which cap stops the loop?**

A coordinator calls the Agent SDK's `query()` once per refinement round. The team sets `max_turns=5` and expects it to limit the loop to 5 rounds. The loop still runs 12 rounds. Why?

- A. `max_turns` is ignored when subagents are used.
- B. `max_turns` caps the tool-use turns inside one `query()` call. The number of rounds is a loop in your code, and it needs its own cap.
- C. `max_turns` counts only subagent turns.
- D. The budget cap overrides `max_turns`.

**Answer: B.** Each round is a new call, and each call gets a fresh `max_turns`. Only a cap in the loop itself limits the rounds. *POC link:* `MAX_ITERATIONS = 3  # the fallback stop: delegation rounds, not the SDK's tool turns`; `max_turns=settings.max_turns  # safety cap per coordinator call`.

---

**Scenario 6: Single-shot vs refinement**

Two designs run the same subagents. Design X delegates once and returns the merged report. Design Y delegates, evaluates coverage, and re-delegates the gaps until a threshold or a cap. Which statement is correct?

- A. X and Y are both coordinators; Y just costs more.
- B. Y is a coordinator; X is a dispatcher. Evaluating the output and re-delegating the gaps is the coordinator's job.
- C. X is safer, because a loop can't be bounded.
- D. Y should let each subagent re-delegate its own gaps.

**Answer: B.** The exam draws this exact line. C is wrong because the loop is bounded by its cap. D moves the evaluation to agents that see only their own brief. *POC link:* the log line `Run 'narrow': dispatcher 25% -> coordinator 88% after 3 round(s)`; `research_once()` in `coordinator.py` is X.

---

**Scenario 7: Blame the right component**

A refinement loop ends with fusion missing in round 1 and added in round 2. A reviewer suggests improving the web-search subagent's prompt, "because it didn't find fusion the first time". The round-1 Agent prompts don't mention fusion. What is the right diagnosis?

- A. The web-search subagent needs a better prompt.
- B. The document-analysis subagent should have read fusion's document.
- C. The coordinator's decomposition: fusion was never delegated in round 1. The subagents did everything they were asked.
- D. The coverage assessment was wrong in round 1.

**Answer: C.** A subagent can only research what its brief assigns. Checking the briefs, not the subagents, finds the root cause. D is wrong because the assessment correctly flagged fusion as missing, which is how round 2 fixed it. *POC link:* `never_delegated = missing_categories([call["prompt"] for call in first_round["agent_calls"]])`. In the real run `full`: `Never delegated in round 1: ['fusion']`.

---

**Scenario 8: Round 2 lost the solar section**

In round 2, the coordinator re-delegates only the gaps. The final report has the gap sections but no solar or wind sections, which round 1 had. What is the bug?

- A. Round 2 should have re-delegated solar and wind too.
- B. The code replaced the report with round 2's sections instead of merging them: keep earlier sections and replace only the re-delegated ones.
- C. The subagents deleted the old sections.
- D. The coverage threshold was too low.

**Answer: B.** Aggregation across rounds is the coordinator's job. Merge by subtopic so every round's results survive. A undoes the point of targeted re-delegation. *POC link:* `merge_sections()`. A related edge case from the real run: the merge keys on names, so a renamed category ("... perovskite tandem cells" → "... perovskite tandem") produced two sections.

---

**Scenario 9: Stuck below the threshold**

A coordinator's assessment rates "every category the topic needs", and it keeps adding categories such as green hydrogen and ocean thermal energy for which the company's document store has no sources. With a 100% threshold, every run ends at the iteration cap at around 64%. The six categories the business requires are all well covered. What is the best change?

- A. Raise the iteration cap to 10.
- B. Lower the threshold to 50%.
- C. Define what counts toward the threshold, for example the required categories, and report the extra categories (or gaps with no available source) separately instead of letting them block completion.
- D. Remove the coverage check.

**Answer: C.** A threshold works only if it measures something the system can reach. Tie it to the required list, and keep the extra findings visible. A spends more rounds on gaps no source can fill. B hides real gaps in the required list too. D turns the coordinator back into a dispatcher. *POC link:* the open clause "plus any other major category of the topic" in `assess_coverage()`; run `full` ended at 64% with `categories still missing: []`.

---

**Scenario 10: Testing the renewable-energy case**

You need an acceptance test for "the final output covers solar, wind, geothermal, tidal, biomass and fusion, and the coverage evaluation shows 100%". Which test is right?

- A. Check that the decomposition has at least 5 subtopics.
- B. Check that the report has at least 6 sections.
- C. Check that each required category has a section with findings and a source, and that the final coverage evaluation is 100% with `complete` true.
- D. Check that the run ended with `subtype == "success"`.

**Answer: C.** The objective has two parts, and both must be checked: the six categories by content, and the evaluation at 100%. A and B count without checking which categories (POC 1's 8 subtopics had no fusion). D only says the last call ended normally. *POC link:* `missing_categories([section["subtopic"] for section in report["sections"]])` (the first part) and `report["coverage_percent"]` / `report["complete"]` (the second). In the real run `full`, the first part passed (`[]`) and the second didn't (64%, `complete: False`).

---

### 8.4 Quick-recall cheat sheet

```
coordinator vs dispatcher → dispatcher: delegate once; coordinator: evaluate, re-delegate gaps, repeat
coverage is judged        → against the WHOLE topic (required list), not against the sections you have
statuses                  → well_covered / partial / missing, each with a reason (schema, enum)
model vs code             → Claude rates each category; Python counts, compares, loops and stops
percent                   → round(100 * well_covered / rated); partial counts as a gap
follow-up round           → ONLY the gaps, each with its reason ("Fix only these gaps:")
aggregation across rounds → merge by subtopic: keep old sections, replace re-delegated ones
stop 1 (primary)          → coverage >= threshold → complete: True
stop 2 (fallback)         → max iterations → WARNING + partial report, complete: False, gaps named
caps                      → MAX_ITERATIONS (rounds) ≠ max_turns (one call) ≠ maxTurns (one subagent)
missing category          → check round 1's briefs: never delegated = decomposition is the root cause
unreachable threshold     → a gap with no source never closes; the cap ends the loop
SDK structured output     → StructuredOutput tool → structured_output; success + stop_reason "tool_use"
```

---

## 9. How to run it

```bash
cd 01-Agentic-Architecture-Orchestration/02-Multi-Agent-Orchestration
source .venv/bin/activate        # the folder's venv (claude-agent-sdk 0.2.174)
python poc2_refinement.py        # paid: 3 runs; 15 query() calls in the logged run (the docstring estimates about 9)
python poc1_hub_and_spoke.py     # paid: POC 1, one delegation round and the isolation test
```

- Both scripts call the API. This folder has no free offline demo.
- `.env` needs `ANTHROPIC_API_KEY`. `MODEL_ID`, `MAX_TURNS` and `MAX_BUDGET_USD` fall back to `claude-sonnet-5-5`, `20` and `1.00`. The budget applies per coordinator call, so a 3-round run makes up to 7 budgeted calls.
- The script prints the model's input and output to the console and writes the same lines to `logs/poc2_refinement_<date>_<time>.log`.
- **Exit codes:** `0` when the runs finish, **including** when the iteration cap fires (that's a warning). A coordinator step that returned nothing usable (`RuntimeError`) or a bad decomposition (`ValueError`) logs `Run '...' stopped: ...` and the script moves on to the next run, still ending with `0`. It's `1` on a setup failure or an SDK runtime failure (`ClaudeSDKError`).
