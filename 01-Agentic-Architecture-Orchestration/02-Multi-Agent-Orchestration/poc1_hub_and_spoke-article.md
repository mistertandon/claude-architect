# POC 1: The Hub, Its Spokes and the Brief Between Them

> **File:** `poc1_hub_and_spoke.py` (with `coordinator.py`, `research_setup.py` and `common.py`)
> **Domain:** 01 Agentic Architecture & Orchestration → 02 Multi-Agent Orchestration
> **SDK:** Claude Agent SDK for Python (`claude-agent-sdk >=0.2.174,<0.3`)

---

## 1. What this POC proves

This POC builds one research round the way the exam describes a hub-and-spoke system. Then it runs a controlled test of what a subagent can and can't know.

| # | Idea | Where it shows up in the code |
|---|------|------------------------------|
| 1 | **The coordinator is the hub.** It decomposes the topic, picks each subagent, writes each subagent's brief and merges the reports. The subagents only research. | `COORDINATOR_PROMPT`, `decompose()`, `delegate()` |
| 2 | **Spawning a subagent is a tool call.** The coordinator calls the built-in `Agent` tool. The SDK runs the subagent and returns its report as that call's `tool_result`. Your code has no subagent loop. | `tools=["Agent"]` and `agents=AGENTS` in `build_coordinator_options()`; `run_coordinator()` pairs each Agent call `id` with its report |
| 3 | **A subagent knows only its brief.** No shared memory, no inherited conversation. A fact the coordinator leaves out of the Agent `prompt` doesn't exist for the subagent. | Run 2: the thin brief in `BRIEFS[0]` |
| 4 | **Poor subagent result? Check the brief first.** Run 3 fixes Run 2 by changing only the brief. The subagent stays the same. | Run 3: the full brief in `BRIEFS[1]` |
| 5 | **The decomposition decides the coverage.** A category the coordinator never lists is never researched. A deterministic check catches it. | `decompose()` + `missing_categories()`; in the real run it returned `['fusion']` |

The pattern in one line:

```
coordinator ──Agent{subagent_type, prompt}──▶ subagent (fresh context: its own prompt + the brief) ──report = tool_result──▶ coordinator
```

---

## 2. The files involved

```
02-Multi-Agent-Orchestration/
├── .env                    ← ANTHROPIC_API_KEY, MODEL_ID, MAX_TURNS, MAX_BUDGET_USD
├── common.py               ← load_settings(): reads .env into a frozen Settings object
├── research_setup.py       ← mock Helios corpus, 2 tools, COORDINATOR_PROMPT, AGENTS, build_coordinator_options()
├── coordinator.py          ← run_coordinator() and the coordinator's jobs: decompose(), delegate(), research_once()
├── poc1_hub_and_spoke.py   ← entry point: 3 runs, 4 query() calls
└── poc2_refinement.py      ← POC 2: the refinement loop (not covered here)
```

The code in this article is the logging-free copy in `raw-poc/01-Agentic-Architecture-Orchestration/02-Multi-Agent-Orchestration/`. The real run in sections 3.2 and 5 comes from the logging version of the same scripts, in `01-Agentic-Architecture-Orchestration/02-Multi-Agent-Orchestration/`.

`poc1_hub_and_spoke.py` is 65 lines because the setup lives in three modules:
- `common.py` covers **configuration** (which model, how many turns, how much money).
- `research_setup.py` covers **capabilities** (the two tools and the two subagents) and **guardrails** (the options of every coordinator call).
- `coordinator.py` covers **orchestration** (stream one coordinator call; decompose, then delegate).
- `poc1_hub_and_spoke.py` covers **the experiments** (one research round, then the isolation test).

---

## 3. End-to-end execution flow

### 3.1 The big picture

```
python poc1_hub_and_spoke.py
        │
        ▼
asyncio.run(main())
        │
        ├─▶ load_settings()                                               [common.py]
        │      └─ .env → Settings(model_id, max_turns, max_budget_usd), frozen
        │
        ├─▶ Run 1: report = research_once(settings, TOPIC)                [coordinator.py]
        │      ├─▶ decompose(settings, topic)
        │      │      ├─ build_coordinator_options(settings, SUBTOPICS_SCHEMA, with_agents=False)
        │      │      │     → tools=[], no agents, no MCP server: the coordinator only thinks
        │      │      ├─ run_coordinator(prompt, options)                 → query() call 1
        │      │      └─ Python check: at least 5 distinct subtopics, else ValueError
        │      └─▶ delegate(settings, topic, subtopics)
        │             ├─ build_coordinator_options(settings, SECTIONS_SCHEMA)
        │             │     → tools=["Agent"], agents=AGENTS, mcp_servers={"research": ...}
        │             └─ run_coordinator(prompt, options)                 → query() call 2
        │
        ├─▶ missed = missing_categories(report["subtopics"])              [research_setup.py]
        │
        └─▶ Runs 2-3: for brief in BRIEFS:
               └─ run_coordinator(ISOLATION_TEST.format(brief=brief),
                                  build_coordinator_options(settings))    → query() calls 3 and 4
```

All four calls go through the same function, and this is what happens inside it:

```
run_coordinator(prompt, options)                                          [coordinator.py]
   │
   └─▶ async for message in query(prompt=prompt, options=options):
          │
          │   ┌─────────────────────── SDK-owned: one coordinator call ────────────────────────┐
          │   │ starts the bundled Claude Code; the coordinator gets COORDINATOR_PROMPT        │
          │   │ ┌─▶ coordinator Claude responds                                                │
          │   │ │     ├─ tool_use Agent {subagent_type, prompt = the brief}       (id = A)     │
          │   │ │     │    ┌──── subagent: fresh context = its own prompt + the brief ────┐    │
          │   │ │     │    │  its own loop: tool_use mcp__research__* → your handler      │    │
          │   │ │     │    │               → tool_result → ... → final text = the report  │    │
          │   │ │     │    └──────────────────────────────────────────────────────────────┘    │
          │   │ │     │   tool_result (tool_use_id = A) = the report                           │
          │   │ └─────┘   (next coordinator turn)                                              │
          │   │       ├─ StructuredOutput call (with output_format) → accepted                 │
          │   │       └─ or final text, no tool_use (stop_reason = end_turn)                   │
          │   │ yields ResultMessage (success / error_*)                                       │
          │   └────────────────────────────────────────────────────────────────────────────────┘
          │
          ├─ hub's Agent call → agent_calls[id] = {"id", "subagent_type", "prompt", "report": None}
          ├─ its tool_result  → agent_calls[id]["report"] = text_of(block.content)
          ├─ ResultMessage    → subtype; if "success": output = structured_output or result
          └─ ResultError      → pass; output stays None
```

### 3.2 Messages your `async for` receives (Run 1's `delegate()` call, real output)

The values below come from the real run on 2026-10-27, recorded in `01-Agentic-Architecture-Orchestration/02-Multi-Agent-Orchestration/logs/poc1_hub_and_spoke_20261027_182029.log`. That log was written by the **logging version** of this POC: the same code, plus one log line for each prompt and for each model input or output in the stream. Each log line holds fields of one message from the stream:

| Log line tag | Message class yielded by `query()` | Field logged |
|--------------|------------------------------------|--------------|
| `MODEL INPUT   prompt` | *(none: it's the `prompt` passed to `run_coordinator()`)* | `prompt` |
| `MODEL OUTPUT  thinking` | `AssistantMessage` → `ThinkingBlock` | `block.thinking`, only when non-empty (none in this log) |
| `MODEL OUTPUT  text` | `AssistantMessage` → `TextBlock` | `block.text` |
| `MODEL OUTPUT  tool_use` | `AssistantMessage` → `ToolUseBlock` | `block.name`, `block.input`, `block.id` |
| `MODEL OUTPUT  structured` | `AssistantMessage` → `ToolUseBlock` named `StructuredOutput` | `block.input`, `block.id` |
| `MODEL INPUT   tool_result` | `UserMessage` → `ToolResultBlock` | `block.content`, `block.tool_use_id`, `block.is_error` |
| `MODEL OUTPUT  stop_reason` | `ResultMessage` | `message.stop_reason`, `message.subtype` |
| `[coordinator]`, `[web-searcher]`, `[doc-analyst]` | the message the line came from | `message.parent_tool_use_id`: `None` gives `coordinator`; any other value gives the `subagent_type` of the Agent call with that id |
| `Categories the decomposition missed: ...` | *(none: the logging version's `main()` writes it; this code keeps it in `missed`)* | `missing_categories(report["subtopics"])` |

The `delegate()` call as it really streamed, in order, inside the **one** `async for` loop:

```
18:20:34  (input)                            [coordinator]
            prompt = Research goal: a sourced overview of "renewable energy technologies" with key figures from Helios Institute sources.
                     Subtopics for this round (delegate only these, using these exact names): ["Solar photovoltaics (...)", ..., "Green hydrogen ... (...)"]
                     Delegate with one Agent call that finds sources for all of these subtopics, then one Agent call that reads ...

18:20:39  AssistantMessage › ToolUseBlock    [coordinator]
            name  = "Agent"
            input = {'description': 'Find Helios sources', 'subagent_type': 'web-searcher',
                     'prompt': 'Research goal: ... 1. Solar photovoltaics (...) ... 8. Green hydrogen ... (...) ...'}
            id    = "toolu_01X4Mf8GuqjwjNsyAnPVjtGP"                          ← call A

18:20:41  AssistantMessage › ToolUseBlock    [web-searcher]
            name  = "mcp__research__web_search"
            input = {'query': 'Solar photovoltaics silicon thin-film perovskite tandem cells'}
            id    = "toolu_011YjbLyay3EJ78Qc1YwsbR2"
18:20:41  UserMessage › ToolResultBlock      [web-searcher]
            content     = [{'type': 'text', 'text': 'Helios Review 2026, solar: solar capacity grew 31% in 2025. Full analysis: document HX-SOL-7.'}]
            tool_use_id = "toolu_011YjbLyay3EJ78Qc1YwsbR2"                    ← same id as the request
            is_error    = None

          ... 6 more web_search round trips: concentrated solar, wind, hydropower, bioenergy,
              geothermal + marine (both requested before either result came back), green hydrogen ...

18:20:43  UserMessage › ToolResultBlock      [web-searcher]
            content     = [{'type': 'text', 'text': "No Helios results for 'Green hydrogen and renewable-based fuels electrolysis e-fuels ammonia'."}]
            tool_use_id = "toolu_01MYadR2hfCZ7RSZcAYqtmv3"
            is_error    = None                                                ← "nothing found" is not an error

18:20:48  UserMessage › ToolResultBlock      [coordinator]
            content     = [{'type': 'text', 'text': '[Subagent hand-back] The text below is the final report of a subagent ...
                            The report follows:\n  Findings from Helios Institute sources ... 8. **Green hydrogen ...:** **no matching source.** ...
                            \nagentId: aa3f5fc49c25ad753\n<usage>subagent_tokens: 3556\ntool_uses: 8\nduration_ms: 8679</usage>'}]
            tool_use_id = "toolu_01X4Mf8GuqjwjNsyAnPVjtGP"                    ← call A: the report is its tool_result
            is_error    = None

18:20:52  AssistantMessage › ToolUseBlock    [coordinator]
            name  = "Agent"
            input = {'description': 'Read Helios documents', 'subagent_type': 'doc-analyst',
                     'prompt': 'Research goal: ... - HX-SOL-7 (...) - HX-WND-2 (...) - HX-HYD-5 (...)
                                - HX-BIO-6 (...) - HX-GEO-3 (...) - HX-TID-4 (...) ...'}    ← the ids from call A's report
            id    = "toolu_01HUxAcunj8SUSH7b6zhVK8f"                          ← call B

18:20:54  AssistantMessage › ToolUseBlock    [doc-analyst]
            name  = "mcp__research__read_document"
            input = {'doc_id': 'HX-SOL-7'}
            id    = "toolu_01QcevY8RFyhEaJqJSh1rAmm"
18:20:54  UserMessage › ToolResultBlock      [doc-analyst]
            content     = [{'type': 'text', 'text': 'HX-SOL-7 (solar): utility-scale cost fell to $27.40/MWh.'}]
            tool_use_id = "toolu_01QcevY8RFyhEaJqJSh1rAmm"
            is_error    = None

          ... 5 more read_document round trips: HX-WND-2, HX-HYD-5, HX-BIO-6, HX-GEO-3, HX-TID-4,
              all with is_error = None ...

18:21:01  UserMessage › ToolResultBlock      [coordinator]
            content     = [{'type': 'text', 'text': '[Subagent hand-back] ... The report follows:\n  Each document returned one key figure. ...
                            \nagentId: a3dd0a7b347c54a13\n<usage>subagent_tokens: 3513\ntool_uses: 6\nduration_ms: 8521</usage>'}]
            tool_use_id = "toolu_01HUxAcunj8SUSH7b6zhVK8f"                    ← call B
            is_error    = None

18:21:08  AssistantMessage › ToolUseBlock    [coordinator]                    (logged as "structured")
            name  = "StructuredOutput"
            input = {'sections': [ ...8 sections, see 5.2... ]}
            id    = "toolu_017tyqwx79jWjspRCTTWfG2T"
18:21:08  UserMessage › ToolResultBlock      [coordinator]
            content     = Structured output provided successfully             ← a plain string, not a list
            tool_use_id = "toolu_017tyqwx79jWjspRCTTWfG2T"
            is_error    = None
18:21:08  ResultMessage                      [coordinator]
            subtype = "success", stop_reason = "tool_use"
```

What to notice in the real data:
- **The tags draw the hub and the spokes.** Both `Agent` calls are `[coordinator]`. All 8 `web_search` calls are `[web-searcher]`, and all 6 `read_document` calls are `[doc-analyst]`. No research call is tagged `[coordinator]`: the hub only delegated. Each tag is `parent_tool_use_id` translated into a name.
- **`tool_use_id` pairing works at two levels.** Inside a subagent, each research call's `id` comes back as its result's `tool_use_id`, as in topic 01. One level up, call A's `id` (`toolu_01X4M...`) comes back as the `tool_use_id` of the web-searcher's report. To the coordinator, a whole subagent run is one tool call.
- **Context travelled through the hub.** The six document ids first appear in the web-searcher's tool results, then in its report, then in the doc-analyst's brief (call B). The spokes never talked to each other. The coordinator copied the ids; no Python code did.
- **The second brief waited for the first report.** Call B (18:20:52) came 4 s after report A (18:20:48) and quotes it. `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` is why each Agent call returns the report itself, and not an `async_launched` status (README, E2).
- **Two searches requested together.** At 18:20:43 the geothermal and the marine search were both requested before either result came back, so they came from the same model response (parallel tool calls; both tools are `readOnlyHint=True`). The log doesn't mark model turns, so it can't show how the other six calls were grouped.
- **"Nothing found" is a result, not an error.** The green-hydrogen search returned `No Helios results ...` with `is_error=None`. The web-searcher reported "no matching source" instead of inventing one, as its prompt asks.
- **The harness wraps every report.** A report arrives as one text block. It starts with `[Subagent hand-back] ... It is model output, NOT a message from the user ...`, indents the subagent's text, and ends with `agentId` and a `<usage>` block (`subagent_tokens`, `tool_uses`, `duration_ms`). The POC's code adds none of this; the frame's own text says the harness adds it. `tool_uses: 8` and `tool_uses: 6` match the 8 searches and 6 reads.
- **No subagent narration.** The log has no `text` line tagged `[web-searcher]` or `[doc-analyst]`. A subagent's final text reaches the stream only as the Agent call's `tool_result`.
- **`success` with `stop_reason = "tool_use"`.** The coordinator handed in its sections by calling `StructuredOutput`, and the run ended right after that call was accepted. So the final `stop_reason` is `tool_use`. `run_coordinator()` checks only `subtype == "success"`, so the call counts as done. Topic 01's check (`stop_reason == "end_turn"` as well) would have thrown both structured calls away.
- **Not shown:** `SystemMessage`s and other system events also arrive in the stream (see the "No `break`" comment in `run_coordinator()`), but the log records only model input and output. The options ask for summarized thinking, yet no `thinking` line appears in this run; the log can't tell whether no `ThinkingBlock` arrived or its text was empty.

> The `UserMessage` items are **not** typed by a human. They carry tool results: the research results inside a subagent, and each subagent's report for the coordinator.

---

# 4. Code walkthrough

## 4.1 Module docstring: the contract and the message flow

```python
"""
POC 1 - Hub and spokes: one delegation round
=============================================
The coordinator (the hub) decomposes a topic, briefs two subagents (the spokes) through the Agent tool,
and merges their reports. Every log line names the agent it belongs to:

    MODEL INPUT   prompt       [coordinator] the task
    MODEL OUTPUT  tool_use     [coordinator] Agent {'subagent_type': 'web-searcher', 'prompt': ...}  (id=A)
    MODEL OUTPUT  tool_use     [web-searcher] mcp__research__web_search {...}  (id=B)
    MODEL INPUT   tool_result  [web-searcher] ...  (tool_use_id=B)
    MODEL INPUT   tool_result  [coordinator] the subagent's report  (tool_use_id=A)

Runs 2 and 3 test isolation: a subagent knows ONLY what the coordinator writes into the Agent prompt.

Run:  python poc1_hub_and_spoke.py     (3 runs, 4 query() calls)
"""
```

**Why it matters:** the docstring states both lessons before any code. First, the four-line flow shows hub-and-spoke as **nested tool calls**: the coordinator's Agent call `A` comes back as `tool_use_id=A`, and the web-searcher's own call `B` and its result happen inside it. Second, Runs 2 and 3 test isolation. "3 runs, 4 query() calls" because Run 1 makes two coordinator calls: `decompose()`, then `delegate()`.

---

## 4.2 Imports

```python
import asyncio
import sys

from claude_agent_sdk import ClaudeSDKError

from common import load_settings, log, setup_logging
from coordinator import research_once, run_coordinator
from research_setup import build_coordinator_options, missing_categories
```

| Import | What it brings in | Why this file needs it |
| --- | --- | --- |
| **asyncio** | Async runtime, `async` / `await` and event loop | The coordinator runs through async `query()` calls, so this file needs to run them asynchronously |
| **sys** | Process control, `sys.exit()` | Lets the file return `0` on success or `1` on failure to the shell |
| **ClaudeSDKError** | Exception type from `claude_agent_sdk` | Lets this file catch a failure of the SDK / coordinator process separately from a logic failure |
| **load_settings** | From `common`, loads `Settings` | Supplies the coordinator configuration for this run |
| **research_once** | From `coordinator`, the hub function | Runs one full hub round: decompose, delegate to spokes, aggregate |
| **run_coordinator** | From `coordinator`, single coordinator call | Runs one isolated coordinator `query()` for the thin brief and full brief tests |
| **build_coordinator_options** | From `research_setup` | Builds the `ClaudeAgentOptions` used for each `run_coordinator()` call |
| **missing_categories** | From `research_setup` | Checks which required categories the decomposition missed |

---

## 4.3 The topic, the isolation test and the two briefs

```python
TOPIC = "renewable energy technologies"

# The isolation test: the coordinator knows the doc id, but must pass the subagent exactly the brief in <<< >>>.
ISOLATION_TEST = (
    "Controlled isolation test. Your notes say the Helios document on tidal energy is HX-TID-4. "
    "Call the doc-analyst subagent once and pass it exactly the text between <<< and >>>, adding nothing: "
    "<<<{brief}>>> Then reply with its report unchanged."
)
BRIEFS = [
    # thin: no goal and no doc id. The subagent never saw the coordinator's notes, so it can't find the document.
    "Analyse the Helios document on tidal energy and report its key figures.",
    # full: the goal, the subtopic and the context a prior agent produced. Same subagent, only the brief changed.
    "Research goal: a sourced overview of renewable energy technologies. Subtopic: tidal energy. Context from the "
    "web-searcher: the Helios entry for tidal energy is document HX-TID-4. Read it and report its key figures.",
]
```

---

## 4.4 `main()`: setup, three runs, two failure boundaries

#### a) Setup

```python
async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc1_hub_and_spoke")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1
```

---

#### b) Run 1: the research round and its coverage check

```python
    try:
        # Run 1 (2 query() calls): decompose -> delegate to both spokes -> aggregate into sections.
        report = await research_once(settings, TOPIC)
        log.info("Categories the decomposition missed: %s", missing_categories(report["subtopics"]))  # [] expected
```

---

#### c) Runs 2 and 3: the isolation test

```python
        # Runs 2-3: the same doc-analyst, briefed thin and then full. Poor result? Check the coordinator's brief first.
        for brief in BRIEFS:
            await run_coordinator(ISOLATION_TEST.format(brief=brief), build_coordinator_options(settings))
```

---

#### d) Failure boundaries

```python
    except (RuntimeError, ValueError) as exc:  # a coordinator step returned nothing usable
        log.error("Stopped: %s", exc)
        return 1
    except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
        log.error("SDK error: %s", exc)
        return 1
    return 0
```

---

## 4.5 `__main__`

```python
if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

`asyncio.run` starts the event loop, and `sys.exit` passes `0` or `1` to the shell. The real run's log has no error line, so `main()` returned `0`.

---

## 4.6 `research_once()`, `decompose()` and `delegate()`: the coordinator's jobs (from `coordinator.py`)

```python
async def research_once(settings: Settings, topic: str, subtopics: list[str] | None = None) -> dict[str, Any]:
    """The coordinator function (C3): a topic string in, a structured report out. One round, no loop."""
    subtopics = subtopics or await decompose(settings, topic)
    round_result = await delegate(settings, topic, subtopics)
    return {"topic": topic, "subtopics": subtopics, **round_result}
```

---

#### a) `decompose()`: job 1, the coordinator only thinks

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

---

#### b) `delegate()`: jobs 2 and 3

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

---

#### c) The two schemas

```python
SUBTOPICS_SCHEMA = {
    "type": "object",
    "properties": {"subtopics": {"type": "array", "items": {"type": "string"}}},
    "required": ["subtopics"],
}

SECTIONS_SCHEMA = {  # one section per subtopic, merged from both reports (C13)
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subtopic": {"type": "string"},
                    "web_findings": {"type": "string"},  # from web-searcher's report
                    "document_findings": {"type": "string"},  # from doc-analyst's report
                    "sources": {"type": "array", "items": {"type": "string"}},  # doc ids
                },
                "required": ["subtopic", "web_findings", "document_findings", "sources"],
            },
        }
    },
    "required": ["sections"],
}
```

---

## 4.7 `run_coordinator()`: one stream, two levels of agents (from `coordinator.py`)

#### a) Setup

```python
async def run_coordinator(prompt: str, options: ClaudeAgentOptions) -> dict[str, Any]:
    """Stream one coordinator query(). Returns {"output", "agent_calls", "subtype"}.

    output: ResultMessage.structured_output when the options ask for JSON, else the final text; None on failure.
    agent_calls: one {"id", "subagent_type", "prompt", "report"} per Agent call, in call order.
    """
    log.info("MODEL INPUT   prompt       [coordinator] %s", prompt)
    agent_names: dict[str, str] = {}  # Agent call id -> subagent name, for the log tags
    agent_calls: dict[str, dict[str, Any]] = {}
    output, subtype = None, None
```

- `agent_calls` is the delegation record that the function returns. It's keyed by the Agent call `id`, so each report can find its spawn.
- `output` starts as `None` and is set only by a `success` result, so `None` means "nothing usable".

#### b) Recording each spawn

```python
    try:
        async for message in query(prompt=prompt, options=options):
            log_model_io(message, agent_names)
            if isinstance(message, AssistantMessage) and message.parent_tool_use_id is None:  # the hub's own response
                for block in message.content:
                    if isinstance(block, ToolUseBlock) and block.name in ("Agent", "Task"):  # "Task" on older versions
                        agent_calls[block.id] = {"id": block.id, "subagent_type": block.input.get("subagent_type"),
                                                 "prompt": block.input.get("prompt", ""), "report": None}
```

---

#### c) Pairing each report with its spawn

```python
            elif isinstance(message, UserMessage) and isinstance(message.content, list):
                for block in message.content:
                    # A subagent's report is the tool result of the Agent call that spawned it (same id).
                    if isinstance(block, ToolResultBlock) and block.tool_use_id in agent_calls:
                        agent_calls[block.tool_use_id]["report"] = text_of(block.content)
```

---

#### d) Reading the outcome

```python
            elif isinstance(message, ResultMessage):
                subtype = message.subtype
                if message.subtype == "success":  # JSON comes only from structured_output, never parsed from text
                    output = message.structured_output if options.output_format else message.result
            # No `break`: a few system events can still arrive after the ResultMessage.
    except ResultError as exc:  # raised AFTER the error ResultMessage (already logged), e.g. error_max_turns
        log.error("The coordinator call failed: %s", exc)
    return {"output": output, "agent_calls": list(agent_calls.values()), "subtype": subtype}
```

---

#### e) `text_of()`

```python
def text_of(content: Any) -> str:
    """A tool result's text: content is a string or a list of {"type": "text", "text": ...} blocks."""
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content or ""
```

---

## 4.8 `Settings`: the limits of one hub-and-spokes call (from `common.py`)

```python
@dataclass(frozen=True)
class Settings:
    model_id: str  # MODEL_ID: the Claude model that runs the coordinator (the subagents inherit it)
    max_turns: int  # MAX_TURNS: safety cap on tool-use turns per coordinator call
    max_budget_usd: float  # MAX_BUDGET_USD: cost guard per coordinator call, its subagents included
```

| Field | Default in `load_settings()` | What it limits here |
|-------|------------------------------|---------------------|
| `model_id` | `"claude-sonnet-5-5"` | The coordinator's model. Both spokes have `model="inherit"`, so all three agents run on it. |
| `max_turns` | `20` | Tool-use turns per coordinator call. Each subagent also has its own `maxTurns=15` in `AGENTS`. |
| `max_budget_usd` | `1.00` | The estimated spend per coordinator call, its subagents included. |

**Agentic concept:** guardrails are configuration. `frozen=True` keeps them fixed for all four `query()` calls.

---

## 4.9 `build_coordinator_options()`: each option is a decision (from `research_setup.py`)

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

| Option | What it does | Agentic concept |
|--------|--------------|-----------------|
| `model` | The coordinator's model. Each subagent has `model="inherit"`, so all three agents use it. | Model choice is config, not code. |
| `system_prompt=COORDINATOR_PROMPT` | The hub's role: three jobs, two spokes, the context rule. The subagents never see it. | **Role definition** for the orchestrator. |
| `output_format` | With a schema, Claude returns JSON by calling the `StructuredOutput` tool, and the code reads `ResultMessage.structured_output`. `None` means a plain-text answer. | **Structured hand-off** from the agent to code. |
| `tools=["Agent"]` / `tools=[]` | `Agent` is the only built-in tool. `[]` (in `decompose()`) leaves none. | **Delegation is a tool**, and the hub gets no other built-in tool. |
| `agents=AGENTS` | Registers the two spokes. Claude picks one by its `description` and names it in `subagent_type`. | **Subagent registry.** |
| `mcp_servers` | Makes the two research tools available in the call, as `mcp__research__web_search` and `mcp__research__read_document`. Each subagent's `tools` list names the one it may use. | Custom tools through an in-process MCP server. |
| `allowed_tools` | Pre-approves `Agent` and both research tools, so nothing waits on a permission prompt. | **Permission model.** |
| `disallowed_tools=["Agent(fork)"]` | No forks: a fork inherits the coordinator's whole conversation. | **Keeps isolation testable.** A fork would have seen `HX-TID-4` and hidden Run 2's lesson. |
| `setting_sources=[]` | Ignores `~/.claude` settings, `CLAUDE.md` and hooks. | **Reproducibility.** |
| `ENABLE_TOOL_SEARCH=false` | Sends every tool schema up front. | No extra `ToolSearch` steps in the stream. |
| `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` | Subagents run in the foreground, so each Agent call returns the report itself. | **Synchronous delegation**: the next brief can use the last report. |
| `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1` | Only our two spokes; no general-purpose fallback. | **A closed set of spokes.** |
| `thinking` | Adaptive thinking with summarized reasoning text, at the same cost. | Visible reasoning (no `thinking` line appeared in this run). |
| `max_turns` | Safety cap per coordinator call. | Runaway guard (topic 01). |
| `max_budget_usd` | Cost guard per coordinator call, subagents included. | **One budget for the whole hub-and-spokes call.** |

> **Note what the options don't do.** The research tools are registered for the whole coordinator call (`mcp_servers`, `allowed_tools`) because the subagents need them. Nothing in the options removes them from the coordinator itself. "Never research yourself" is a rule in `COORDINATOR_PROMPT`, and the real run's log is where you check that it held: no `mcp__research__*` call is tagged `[coordinator]`.

---

## 4.10 The hub's role and its two spokes (from `research_setup.py`)

#### a) `COORDINATOR_PROMPT`

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
```

| Job | What the prompt says | What the real run did |
|-----|----------------------|-----------------------|
| 1. Decompose | "5 to 8 distinct subtopics that cover its full breadth, including mainstream, niche, and emerging or experimental categories", "never a cross-cutting theme" | 8 categories and no themes, with emerging technologies folded in (perovskite cells, floating and airborne wind, closed-loop geothermal, green hydrogen). Fusion never appeared. |
| 2. Delegate | "never research yourself", "every Agent prompt must state the research goal, the exact subtopic names, and every fact from earlier reports that the subagent needs, such as document ids" | No research call is tagged `[coordinator]`. Both briefs state the goal, the web-searcher's lists the 8 exact names, and the doc-analyst's carries the 6 ids. |
| 3. Aggregate | "one section per subtopic, and judge coverage honestly" | 8 sections; concentrated solar and green hydrogen marked as gaps. |

#### b) `AGENTS`

```python
# Each spoke: a description (Claude picks the subagent from it, as it picks a tool), its own system prompt,
# and one tool. The subagent sees its prompt plus the Agent call's prompt, and nothing else.
AGENTS = {
    "web-searcher": AgentDefinition(
        description="Finds Helios Institute sources for a list of subtopics. Use it before doc-analyst.",
        prompt=("You are a web-search specialist. Call web_search once for each subtopic in your task. "
                "For each subtopic, report the key figure and the document id from the result. "
                "Use only what the tool returns; if a search finds nothing, say so."),
        tools=[WEB_SEARCH],  # its only tool: it can't read documents or spawn agents
        model="inherit",  # the coordinator's model
        maxTurns=15,  # per-subagent safety cap (camelCase, as in the SDK)
    ),
    "doc-analyst": AgentDefinition(
        description="Reads Helios documents by exact document id and extracts their key figures.",
        prompt=("You are a document analyst. Read each document id in your task with read_document and "
                "report its key figures per subtopic. You cannot search. If your task gives no document "
                "id, say which ids you need instead of guessing."),
        tools=[READ_DOCUMENT],
        model="inherit",
        maxTurns=15,
    ),
}
```

| Field | Role | Seen in the real run |
|-------|------|----------------------|
| The key (`"web-searcher"`) | The name the coordinator puts in `subagent_type`. | `'subagent_type': 'web-searcher'` |
| `description` | How the coordinator chooses, as with a tool description. "Use it before doc-analyst" also sets the order. | `web-searcher` was called first, `doc-analyst` second. |
| `prompt` | The subagent's own system prompt. | "Call web_search once for each subtopic": 8 subtopics, 8 searches. "if a search finds nothing, say so": "no matching source". "say which ids you need instead of guessing": Run 2. |
| `tools` | One tool each, and no `Agent` tool. | Every `web_search` is `[web-searcher]`; every `read_document` is `[doc-analyst]`. |
| `model="inherit"` | The coordinator's model. | none |
| `maxTurns=15` | Per-subagent safety cap. | Not reached: both subagents finished with a report. |

**Agentic concept: specialization and least privilege.** Each spoke has one job and one tool. Neither has the `Agent` tool, so a spoke can't spawn agents or talk to the other spoke. Everything goes through the hub.

---

## 4.11 The mock corpus and the two tools (from `research_setup.py`)

#### a) `CORPUS`, `REQUIRED` and `missing_categories()`

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

- **Made-up data:** Claude can't answer from memory, so it has to delegate.
- **Two facts per category, one per tool.** Every figure in the final report shows which spoke fetched it: marine's `1.9 GW` came from the web-searcher, `37.5%` from the doc-analyst.
- `REQUIRED` is the curriculum's list. No prompt lists it: the coordinator has to find the breadth itself.
- `missing_categories()` matches the same words `web_search` matches. On the real subtopics, "Marine energy (tidal, ...)" counts as tidal and "Bioenergy and biofuels (biomass, ...)" as biomass. Nothing mentions fusion.

#### b) `web_search` and `read_document`

```python
@tool(
    "web_search",
    "Search Helios Institute sources. Returns one line per matching renewable-energy category, with a key "
    "figure and the id of the document that holds the full analysis.",
    {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "What to search for, e.g. 'tidal energy'"}},
        "required": ["query"],
    },
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def web_search(args: dict[str, Any]) -> dict[str, Any]:
    query_text = str(args.get("query", ""))
    lines = [
        f"Helios Review 2026, {category}: {web_fact}. Full analysis: document {doc_id}."
        for category, (words, doc_id, web_fact, _) in CORPUS.items()
        if any(word in query_text.lower() for word in words)
    ]
    return {"content": [{"type": "text", "text": "\n".join(lines) or f"No Helios results for '{query_text}'."}]}


@tool(
    "read_document",
    "Read one Helios document by its exact id, as named in web_search results (e.g. 'HX-SOL-7'), "
    "and return its key figures.",
    {...},
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def read_document(args: dict[str, Any]) -> dict[str, Any]:
    doc_id = str(args.get("doc_id", ""))
    for category, (_, known_id, _, document_fact) in CORPUS.items():
        if doc_id.strip().upper() == known_id:
            return {"content": [{"type": "text", "text": f"{known_id} ({category}): {document_fact}."}]}
    # A guessed id gets an error RESULT with a hint, so the subagent can recover (01 E4).
    message = f"Unknown document id '{doc_id}'. Only ids that appear in web_search results exist."
    return {"content": [{"type": "text", "text": message}], "is_error": True}
```

- **The description is a prompt.** `web_search` promises "the id of the document that holds the full analysis": that id is the hand-off key between the two spokes. `read_document` asks for "its exact id, as named in web_search results".
- **No match is a normal result.** `web_search` returns `No Helios results for '...'` without `is_error`.
- **A guessed id is an error result, not an exception.** `read_document` returns `is_error: True` with a hint, so the subagent can recover (topic 01's pattern). This branch never ran in the real log: all 7 reads used real ids, and in Run 2 the subagent didn't guess.

---

## 5. Turn-by-turn trace of each run (real output)

Each trace below is the real run from the log named in 3.2, written by the logging version (2026-10-27, 18:20:29 to 18:21:26: 57 seconds for all four `query()` calls). Each logged value is tied to the code above that produced or used it. Long values are trimmed with `...` and wrapped across lines.

### 5.1 Run 1, call 1: `decompose()`

**Real log:**

```
18:20:29  MODEL INPUT   prompt       [coordinator] Decompose this research topic into subtopics. Do not delegate yet. Topic: renewable energy technologies
18:20:33  MODEL OUTPUT  structured   [coordinator] {'subtopics': ['Solar photovoltaics (silicon, thin-film, perovskite and tandem cells)',
                                     'Concentrated solar power and solar thermal',
                                     'Onshore and offshore wind power (including floating wind and airborne wind)',
                                     'Hydropower and pumped storage (conventional, run-of-river, small-scale)',
                                     'Bioenergy and biofuels (biomass, biogas, advanced and algae-based fuels)',
                                     'Geothermal energy (conventional, enhanced/engineered and closed-loop systems)',
                                     'Marine energy (tidal, wave, ocean thermal and salinity gradient)',
                                     'Green hydrogen and renewable-based fuels (electrolysis, e-fuels, ammonia)']}  (id=toolu_0126Levgivd5ukFhTwK9yeGx)
18:20:33  MODEL INPUT   tool_result  [coordinator] Structured output provided successfully  (tool_use_id=toolu_0126Levgivd5ukFhTwK9yeGx, is_error=None)
18:20:33  MODEL OUTPUT  stop_reason  [coordinator] tool_use  (loop result: success)
```

**Variable values inside `decompose()` and `run_coordinator()`:**

| Variable / field | Value |
|------------------|-------|
| `prompt` | `"Decompose this research topic into subtopics. Do not delegate yet. Topic: renewable energy technologies"` |
| `options` | `tools=[]`, no `agents`, no `mcp_servers`, `output_format` with `SUBTOPICS_SCHEMA` |
| `agent_calls` | empty: no Agent call |
| Only tool call | `StructuredOutput`, logged as `structured` |
| `message.subtype` | `"success"` |
| `message.stop_reason` | `"tool_use"` |
| `output` (`message.structured_output`) | `{'subtopics': [...8 strings...]}` |
| Count and distinct check | 8 subtopics, 8 distinct: no `ValueError` |
| `subtopics` (returned) | the 8 strings |

**Lessons from the real data:**
- About 4 seconds, with no Agent call and no research call. With `tools=[]`, the only tool the coordinator used was the built-in `StructuredOutput`.
- The decomposition has the shape the prompt asks for: mainstream categories (solar PV, wind, hydropower), niche ones (concentrated solar, marine) and emerging ones (green hydrogen), with no cross-cutting themes.
- **Fusion is missing.** The build spec (`02-revised-Multi-Agent-Orchestration.md`, C8) names fusion as "the usual one" to go missing, and this run missed it too. The `ValueError` guard still passed, because 8 is at least 5 and all are distinct.

### 5.2 Run 1, call 2: `delegate()`, the hub-and-spoke round

**Real log:**

```
18:20:34  MODEL INPUT   prompt       [coordinator] Research goal: a sourced overview of "renewable energy technologies" with key figures from Helios Institute sources.
                                     Subtopics for this round (delegate only these, using these exact names): ["Solar photovoltaics (silicon, thin-film,
                                     perovskite and tandem cells)", "Concentrated solar power and solar thermal", ..., "Green hydrogen and renewable-based
                                     fuels (electrolysis, e-fuels, ammonia)"]
                                     Delegate with one Agent call that finds sources for all of these subtopics, then one Agent call that reads the
                                     documents those sources name. Return one section per subtopic.
18:20:39  MODEL OUTPUT  tool_use     [coordinator] Agent {'description': 'Find Helios sources', 'subagent_type': 'web-searcher', 'prompt': 'Research
                                     goal: a sourced overview of "renewable energy technologies" with key figures from Helios Institute sources. Find
                                     Helios Institute sources for each of these exact subtopics, and for each report the document id(s) and any key
                                     figure returned:\n1. Solar photovoltaics (silicon, thin-film, perovskite and tandem cells)\n2. ...\n8. Green hydrogen
                                     and renewable-based fuels (electrolysis, e-fuels, ammonia)\nReport per subtopic: document id(s), key figure, and
                                     clearly note any subtopic with no matching source.'}  (id=toolu_01X4Mf8GuqjwjNsyAnPVjtGP)
18:20:41  MODEL OUTPUT  tool_use     [web-searcher] mcp__research__web_search {'query': 'Solar photovoltaics silicon thin-film perovskite tandem cells'}  (id=toolu_011YjbLyay3EJ78Qc1YwsbR2)
18:20:41  MODEL INPUT   tool_result  [web-searcher] [{'type': 'text', 'text': 'Helios Review 2026, solar: solar capacity grew 31% in 2025. Full analysis: document HX-SOL-7.'}]  (tool_use_id=toolu_011YjbLyay3EJ78Qc1YwsbR2, is_error=None)
18:20:41  MODEL OUTPUT  tool_use     [web-searcher] mcp__research__web_search {'query': 'Concentrated solar power and solar thermal'}  (id=toolu_01BPt4odDAp6pR9fC6wJCAGN)
18:20:41  MODEL INPUT   tool_result  [web-searcher] [{'type': 'text', 'text': 'Helios Review 2026, solar: solar capacity grew 31% in 2025. Full analysis: document HX-SOL-7.'}]  (tool_use_id=toolu_01BPt4odDAp6pR9fC6wJCAGN, is_error=None)
18:20:42  MODEL OUTPUT  tool_use     [web-searcher] mcp__research__web_search {'query': 'Onshore and offshore wind power floating wind airborne wind'}  (id=toolu_01SiLaBuimKdhVTnXxFLhQ67)
18:20:42  MODEL INPUT   tool_result  [web-searcher] [{'type': 'text', 'text': 'Helios Review 2026, wind: offshore wind added 19.6 GW in 2025. Full analysis: document HX-WND-2.'}]  (tool_use_id=toolu_01SiLaBuimKdhVTnXxFLhQ67, is_error=None)
18:20:42  MODEL OUTPUT  tool_use     [web-searcher] mcp__research__web_search {'query': 'Hydropower and pumped storage'}  (id=toolu_01SN1b9UW5TYhGdiLxQGomgq)
18:20:42  MODEL INPUT   tool_result  [web-searcher] [{'type': 'text', 'text': 'Helios Review 2026, hydropower: hydropower supplied 14.2% of electricity. Full analysis: document HX-HYD-5.'}]  (tool_use_id=toolu_01SN1b9UW5TYhGdiLxQGomgq, is_error=None)
18:20:42  MODEL OUTPUT  tool_use     [web-searcher] mcp__research__web_search {'query': 'Bioenergy and biofuels biomass biogas advanced algae-based fuels'}  (id=toolu_01UDG3v1xHcLbcWNWoUGqaqQ)
18:20:42  MODEL INPUT   tool_result  [web-searcher] [{'type': 'text', 'text': 'Helios Review 2026, biomass: bioenergy supplied 9.4% of industrial heat. Full analysis: document HX-BIO-6.'}]  (tool_use_id=toolu_01UDG3v1xHcLbcWNWoUGqaqQ, is_error=None)
18:20:43  MODEL OUTPUT  tool_use     [web-searcher] mcp__research__web_search {'query': 'Geothermal energy enhanced engineered closed-loop'}  (id=toolu_01ShBdxB8zQTbmog7c8ynajC)
18:20:43  MODEL OUTPUT  tool_use     [web-searcher] mcp__research__web_search {'query': 'Marine energy tidal wave ocean thermal salinity gradient'}  (id=toolu_01Qns4bED55AZXWHuRV8VgM9)
18:20:43  MODEL INPUT   tool_result  [web-searcher] [{'type': 'text', 'text': 'Helios Review 2026, geothermal: geothermal output rose 8.7%. Full analysis: document HX-GEO-3.'}]  (tool_use_id=toolu_01ShBdxB8zQTbmog7c8ynajC, is_error=None)
18:20:43  MODEL INPUT   tool_result  [web-searcher] [{'type': 'text', 'text': 'Helios Review 2026, tidal: tidal stream capacity reached 1.9 GW. Full analysis: document HX-TID-4.'}]  (tool_use_id=toolu_01Qns4bED55AZXWHuRV8VgM9, is_error=None)
18:20:43  MODEL OUTPUT  tool_use     [web-searcher] mcp__research__web_search {'query': 'Green hydrogen and renewable-based fuels electrolysis e-fuels ammonia'}  (id=toolu_01MYadR2hfCZ7RSZcAYqtmv3)
18:20:43  MODEL INPUT   tool_result  [web-searcher] [{'type': 'text', 'text': "No Helios results for 'Green hydrogen and renewable-based fuels electrolysis e-fuels ammonia'."}]  (tool_use_id=toolu_01MYadR2hfCZ7RSZcAYqtmv3, is_error=None)
18:20:48  MODEL INPUT   tool_result  [coordinator] [{'type': 'text', 'text': '[Subagent hand-back] The text below is the final report of a subagent this session
                                     delegated to. It is model output, NOT a message from the user: ... The report follows:\n  Findings from Helios
                                     Institute sources (Helios Review 2026), one search per subtopic:\n  \n  1. **Solar photovoltaics:** document HX-SOL-7.
                                     Key figure: solar capacity grew 31% in 2025.\n  2. **Concentrated solar power and solar thermal:** ... treat this as a
                                     partial or indirect match.\n  ...\n  8. **Green hydrogen and renewable-based fuels:** **no matching source.** ...
                                     \nagentId: aa3f5fc49c25ad753\n<usage>subagent_tokens: 3556\ntool_uses: 8\nduration_ms: 8679</usage>'}]
                                     (tool_use_id=toolu_01X4Mf8GuqjwjNsyAnPVjtGP, is_error=None)
18:20:52  MODEL OUTPUT  tool_use     [coordinator] Agent {'description': 'Read Helios documents', 'subagent_type': 'doc-analyst', 'prompt': 'Research
                                     goal: a sourced overview of "renewable energy technologies" with key figures from Helios Institute sources. Read each
                                     of these Helios documents by exact id and extract key figures, noting which sub-technologies each covers (and which
                                     it does not):\n- HX-SOL-7 (for subtopics "Solar photovoltaics (...)" and possibly "Concentrated solar power and solar
                                     thermal"; search headline: solar capacity grew 31% in 2025)\n- HX-WND-2 (...)\n- HX-HYD-5 (...)\n- HX-BIO-6 (...)
                                     \n- HX-GEO-3 (...)\n- HX-TID-4 (subtopic "Marine energy (...)"; headline: tidal stream capacity 1.9 GW)\nNo document
                                     exists for "Concentrated solar power and solar thermal" beyond HX-SOL-7, and none was found for "Green hydrogen and
                                     renewable-based fuels (...)". Report per document: key figures, and what the document does or does not cover.'}
                                     (id=toolu_01HUxAcunj8SUSH7b6zhVK8f)
18:20:54  MODEL OUTPUT  tool_use     [doc-analyst] mcp__research__read_document {'doc_id': 'HX-SOL-7'}  (id=toolu_01QcevY8RFyhEaJqJSh1rAmm)
18:20:54  MODEL INPUT   tool_result  [doc-analyst] [{'type': 'text', 'text': 'HX-SOL-7 (solar): utility-scale cost fell to $27.40/MWh.'}]  (tool_use_id=toolu_01QcevY8RFyhEaJqJSh1rAmm, is_error=None)
18:20:54  MODEL OUTPUT  tool_use     [doc-analyst] mcp__research__read_document {'doc_id': 'HX-WND-2'}  (id=toolu_017LGhEQyXyQhFgYjrTvwuB8)
18:20:54  MODEL INPUT   tool_result  [doc-analyst] [{'type': 'text', 'text': 'HX-WND-2 (wind): the average capacity factor reached 41.3%.'}]  (tool_use_id=toolu_017LGhEQyXyQhFgYjrTvwuB8, is_error=None)
18:20:54  MODEL OUTPUT  tool_use     [doc-analyst] mcp__research__read_document {'doc_id': 'HX-HYD-5'}  (id=toolu_017vxnUqhjZ79xb2o9wWfkyQ)
18:20:55  MODEL INPUT   tool_result  [doc-analyst] [{'type': 'text', 'text': 'HX-HYD-5 (hydropower): pumped-storage capacity rose to 212 GW.'}]  (tool_use_id=toolu_017vxnUqhjZ79xb2o9wWfkyQ, is_error=None)
18:20:55  MODEL OUTPUT  tool_use     [doc-analyst] mcp__research__read_document {'doc_id': 'HX-BIO-6'}  (id=toolu_01HhXAKdxo7dHFNqPE5SdTqR)
18:20:55  MODEL INPUT   tool_result  [doc-analyst] [{'type': 'text', 'text': 'HX-BIO-6 (biomass): waste feedstocks made up 63% of supply.'}]  (tool_use_id=toolu_01HhXAKdxo7dHFNqPE5SdTqR, is_error=None)
18:20:55  MODEL OUTPUT  tool_use     [doc-analyst] mcp__research__read_document {'doc_id': 'HX-GEO-3'}  (id=toolu_01Cjg11Xn5apWkw7pzUhsfPJ)
18:20:55  MODEL INPUT   tool_result  [doc-analyst] [{'type': 'text', 'text': 'HX-GEO-3 (geothermal): enhanced-geothermal pilot wells reached 245 °C.'}]  (tool_use_id=toolu_01Cjg11Xn5apWkw7pzUhsfPJ, is_error=None)
18:20:55  MODEL OUTPUT  tool_use     [doc-analyst] mcp__research__read_document {'doc_id': 'HX-TID-4'}  (id=toolu_01QwJvcYQnwDEokgByQhGuMx)
18:20:55  MODEL INPUT   tool_result  [doc-analyst] [{'type': 'text', 'text': 'HX-TID-4 (tidal): the Kestrel Strait array ran at a 37.5% capacity factor.'}]  (tool_use_id=toolu_01QwJvcYQnwDEokgByQhGuMx, is_error=None)
18:21:01  MODEL INPUT   tool_result  [coordinator] [{'type': 'text', 'text': '[Subagent hand-back] ... The report follows:\n  Each document returned one key
                                     figure. None returned the headline figure from the search results, so those headlines are unverified by the documents
                                     themselves.\n  ...\n  - **HX-TID-4 (tidal):** The Kestrel Strait array ran at a 37.5% capacity factor.\n  ...\n
                                     **Gaps**\n  - No Helios document is available for concentrated solar power and solar thermal beyond HX-SOL-7, ...\n
                                     - No document was found for green hydrogen and renewable-based fuels.\n  ...\nagentId: a3dd0a7b347c54a13\n<usage>
                                     subagent_tokens: 3513\ntool_uses: 6\nduration_ms: 8521</usage>'}]  (tool_use_id=toolu_01HUxAcunj8SUSH7b6zhVK8f, is_error=None)
18:21:08  MODEL OUTPUT  structured   [coordinator] {'sections': [{'subtopic': 'Solar photovoltaics (silicon, thin-film, perovskite and tandem cells)',
                                     'web_findings': 'Search returned HX-SOL-7 with headline: solar capacity grew 31% in 2025.', 'document_findings':
                                     'HX-SOL-7 gives utility-scale solar cost fell to $27.40/MWh. ...', 'sources': ['HX-SOL-7']}, ..., {'subtopic': 'Green
                                     hydrogen and renewable-based fuels (electrolysis, e-fuels, ammonia)', 'web_findings': 'No Helios results returned for
                                     this subtopic.', 'document_findings': 'No document available. Complete coverage gap.', 'sources': []}]}
                                     (id=toolu_017tyqwx79jWjspRCTTWfG2T)
18:21:08  MODEL INPUT   tool_result  [coordinator] Structured output provided successfully  (tool_use_id=toolu_017tyqwx79jWjspRCTTWfG2T, is_error=None)
18:21:08  MODEL OUTPUT  stop_reason  [coordinator] tool_use  (loop result: success)
18:21:09  Categories the decomposition missed: ['fusion']
```

**What each step did and which code ran:**

| Step | Agent | Claude asked for | Code the SDK ran | Result |
|------|-------|------------------|------------------|--------|
| 1 | coordinator | `Agent` → `web-searcher`; brief = goal + the 8 exact subtopics + the report format | Starts the subagent with `AGENTS["web-searcher"].prompt` + the brief | A subagent run under id `toolu_01X4M...` |
| 2 | web-searcher | 8 × `web_search`, one per subtopic | `web_search()`: keyword match on `CORPUS` | 7 hits (`HX-SOL-7` twice) and 1 "No Helios results" |
| 3 | web-searcher → coordinator | *(final text)* | none | The report, as the `tool_result` of step 1 |
| 4 | coordinator | `Agent` → `doc-analyst`; brief = goal + 6 doc ids + headlines + known gaps | Starts the second subagent | A subagent run under id `toolu_01HUx...` |
| 5 | doc-analyst | 6 × `read_document` | `read_document()`: exact id match on `CORPUS` | 6 document facts, no errors |
| 6 | doc-analyst → coordinator | *(final text)* | none | The report, as the `tool_result` of step 4 |
| 7 | coordinator | `StructuredOutput` with 8 sections | The built-in tool (no POC code) | "Structured output provided successfully" |
| 8 | none | none | none | `ResultMessage`: `success` / `tool_use` |

**What the web-searcher's 8 searches matched:**

| # | `query` | Words `web_search()` matched | Result |
|---|---------|------------------------------|--------|
| 1 | Solar photovoltaics silicon thin-film perovskite tandem cells | solar, photovoltaic | solar → `HX-SOL-7` |
| 2 | Concentrated solar power and solar thermal | solar | solar → `HX-SOL-7` again |
| 3 | Onshore and offshore wind power floating wind airborne wind | wind | wind → `HX-WND-2` |
| 4 | Hydropower and pumped storage | hydropower | hydropower → `HX-HYD-5` |
| 5 | Bioenergy and biofuels biomass biogas advanced algae-based fuels | biomass, bioenergy, biofuel, biogas | biomass → `HX-BIO-6` |
| 6 | Geothermal energy enhanced engineered closed-loop | geothermal | geothermal → `HX-GEO-3` |
| 7 | Marine energy tidal wave ocean thermal salinity gradient | tidal, wave, ocean, marine | tidal → `HX-TID-4` |
| 8 | Green hydrogen and renewable-based fuels electrolysis e-fuels ammonia | none | "No Helios results ..." |

**The 8 sections the coordinator handed in (from the `structured` line):**

| Subtopic (shortened) | `web_findings` (web-searcher) | `document_findings` (doc-analyst) | `sources` |
|----------------------|-------------------------------|-----------------------------------|-----------|
| Solar photovoltaics | capacity grew 31% | $27.40/MWh; no cell technology named; the 31% "stays unverified" | `['HX-SOL-7']` |
| Concentrated solar power and solar thermal | only the general solar result | nothing on CSP: "Coverage gap" | `['HX-SOL-7']` |
| Onshore and offshore wind | offshore added 19.6 GW | capacity factor 41.3% | `['HX-WND-2']` |
| Hydropower and pumped storage | 14.2% of electricity | pumped storage 212 GW | `['HX-HYD-5']` |
| Bioenergy and biofuels | 9.4% of industrial heat | waste feedstocks 63% | `['HX-BIO-6']` |
| Geothermal energy | output rose 8.7% | enhanced-geothermal wells at 245 °C | `['HX-GEO-3']` |
| Marine energy | tidal stream 1.9 GW | Kestrel Strait array at 37.5% | `['HX-TID-4']` |
| Green hydrogen and renewable-based fuels | no Helios results | "Complete coverage gap" | `[]` |

**Variable values at the end of the call:**

| Variable / field | Value |
|------------------|-------|
| `agent_calls` | 2 items in call order: `{"id": "toolu_01X4Mf8GuqjwjNsyAnPVjtGP", "subagent_type": "web-searcher", "prompt": "Research goal: ...", "report": "[Subagent hand-back] ..."}`, then `{"id": "toolu_01HUxAcunj8SUSH7b6zhVK8f", "subagent_type": "doc-analyst", ...}` |
| `message.subtype` | `"success"` |
| `message.stop_reason` | `"tool_use"` |
| `output` (`message.structured_output`) | Not logged. `delegate()` returned without an error, so it held the `sections` list. |
| `delegate()` returned | `{"sections": [...8 sections...], "agent_calls": [...2 calls...]}` |
| `report` (from `research_once()`) | `{"topic": "renewable energy technologies", "subtopics": [8], "sections": [8], "agent_calls": [2]}` |
| `missed` = `missing_categories(report["subtopics"])` | `['fusion']` (the logging version logged it at 18:21:09) |

**Lessons from the real data:**
- **Context from a prior agent travelled through the hub.** The doc-analyst's brief carries all six document ids from the web-searcher's report, plus the headline figures and the two known gaps. Claude wrote that brief because `COORDINATOR_PROMPT` asks for "every fact from earlier reports that the subagent needs"; no Python copied the ids.
- **Every figure is attributable.** Web and document facts differ by design, so the sections show which spoke found what: marine's `1.9 GW` (web-searcher) next to `37.5%` (doc-analyst).
- **The spokes reported honestly, and the hub kept their caveats.** The web-searcher flagged the concentrated-solar hit as "partial or indirect" and green hydrogen as "no matching source". The doc-analyst noticed that no document repeated its search headline and said to cite the headlines "only as search-result snippets". The coordinator carried these caveats into the sections ("not confirmed", "Coverage gap", `sources: []`).
- **Fusion is missing, and POC 1 can't repair it.** The decomposition never listed fusion, so no brief mentioned it and no subagent searched for it, even though `HX-FUS-1` sits in the corpus. The subagents did everything they were asked. The root cause is the decomposition, which is the diagnosis the exam expects. Repairing it takes a coverage check and a re-delegation round: that's POC 2.
- **The sections mirror the decomposition.** Concentrated solar power got its own section only because the decomposition split solar in two, and both solar sections cite the same `HX-SOL-7`.

### 5.3 Run 2: the thin brief (isolation)

**Real log:**

```
18:21:09  MODEL INPUT   prompt       [coordinator] Controlled isolation test. Your notes say the Helios document on tidal energy is HX-TID-4. Call the
                                     doc-analyst subagent once and pass it exactly the text between <<< and >>>, adding nothing: <<<Analyse the Helios
                                     document on tidal energy and report its key figures.>>> Then reply with its report unchanged.
18:21:12  MODEL OUTPUT  tool_use     [coordinator] Agent {'description': 'Analyse tidal document', 'subagent_type': 'doc-analyst', 'prompt': 'Analyse the
                                     Helios document on tidal energy and report its key figures.'}  (id=toolu_01N3dW6FJb3PrP7PfvJycahG)
18:21:14  MODEL INPUT   tool_result  [coordinator] [{'type': 'text', 'text': '[Subagent hand-back] ... The report follows:\n  I can\'t identify which document to
                                     read. The task refers to "the Helios document on tidal energy" but gives no document id, and I have no search tool, so I
                                     won\'t guess one.\n  \n  Please send the exact id (for example, something like \'HX-SOL-7\'), and I\'ll read it and
                                     report its key figures by subtopic. If there are several tidal energy documents, send all of their ids.\nagentId:
                                     a4db8fd94a9618db0\n<usage>subagent_tokens: 1471\ntool_uses: 0\nduration_ms: 1795</usage>'}]
                                     (tool_use_id=toolu_01N3dW6FJb3PrP7PfvJycahG, is_error=None)
18:21:17  MODEL OUTPUT  text         [coordinator] The doc-analyst's report, unchanged:

                                     > I can't identify which document to read. The task refers to "the Helios document on tidal energy" but gives no
                                     > document id, and I have no search tool, so I won't guess one.
                                     >
                                     > Please send the exact id (for example, something like 'HX-SOL-7'), and I'll read it and report its key figures by
                                     > subtopic. If there are several tidal energy documents, send all of their ids.

                                     The subagent returned no key figures. I passed along your exact text, which didn't include the id HX-TID-4, so it had
                                     nothing to look up. I can re-run it with the id included if you want.
18:21:17  MODEL OUTPUT  stop_reason  [coordinator] end_turn  (loop result: success)
```

**Variable values inside `run_coordinator()`:**

| Variable / field | Value | Effect in the code |
|------------------|-------|--------------------|
| `prompt` | `ISOLATION_TEST` with `BRIEFS[0]` | `HX-TID-4` is in the coordinator's context |
| `options` | `build_coordinator_options(settings)`: agents on, `output_format=None` | A plain-text answer |
| `agent_calls[0]["prompt"]` | `"Analyse the Helios document on tidal energy and report its key figures."` | Exactly the thin brief: no goal, no `HX-TID-4` |
| doc-analyst tool calls | none (`tool_uses: 0`) | No `read_document`, so no `is_error` result either |
| `agent_calls[0]["report"]` | "... gives no document id, and I have no search tool, so I won't guess one. ..." | No `37.5%` |
| `message.subtype` / `message.stop_reason` | `"success"` / `"end_turn"` | The `if` is true |
| `output` (`message.result`) | The coordinator's text: the report, then "I passed along your exact text, which didn't include the id HX-TID-4 ..." | Returned, then ignored by `main()` |

**Lessons from the real data:**
- **Isolation is real.** `HX-TID-4` sat in the coordinator's prompt, one level up, and the doc-analyst never saw it. It knew only its own system prompt, the brief and its tool.
- **What it did see shows in its answer.** Its example id, `'HX-SOL-7'`, is the example in `read_document`'s description, the only id in its context. It used it as a format hint, not as a guess, because its prompt says "say which ids you need instead of guessing".
- **`success` doesn't mean the task worked.** The run ended normally (`success`, `end_turn`) and produced no figures. The SDK reports how the loop ended; judging the content is your job.
- **The coordinator diagnosed the gap itself.** It knew the id, saw that the subagent didn't, and said so. In doing that, it broke the instruction "reply with its report unchanged" by adding the diagnosis.

### 5.4 Run 3: the full brief, same subagent

**Real log:**

```
18:21:18  MODEL INPUT   prompt       [coordinator] Controlled isolation test. Your notes say the Helios document on tidal energy is HX-TID-4. Call the
                                     doc-analyst subagent once and pass it exactly the text between <<< and >>>, adding nothing: <<<Research goal: a
                                     sourced overview of renewable energy technologies. Subtopic: tidal energy. Context from the web-searcher: the Helios
                                     entry for tidal energy is document HX-TID-4. Read it and report its key figures.>>> Then reply with its report unchanged.
18:21:20  MODEL OUTPUT  tool_use     [coordinator] Agent {'description': 'Read tidal document', 'subagent_type': 'doc-analyst', 'prompt': 'Research goal: a
                                     sourced overview of renewable energy technologies. Subtopic: tidal energy. Context from the web-searcher: the Helios
                                     entry for tidal energy is document HX-TID-4. Read it and report its key figures.'}  (id=toolu_0118dmoxaTYfw8R46rt7nTPH)
18:21:22  MODEL OUTPUT  tool_use     [doc-analyst] mcp__research__read_document {'doc_id': 'HX-TID-4'}  (id=toolu_01A2yEKJ5VWnUy6L5Mmpm6LW)
18:21:22  MODEL INPUT   tool_result  [doc-analyst] [{'type': 'text', 'text': 'HX-TID-4 (tidal): the Kestrel Strait array ran at a 37.5% capacity factor.'}]  (tool_use_id=toolu_01A2yEKJ5VWnUy6L5Mmpm6LW, is_error=None)
18:21:24  MODEL INPUT   tool_result  [coordinator] [{'type': 'text', 'text': "[Subagent hand-back] ... The report follows:\n  Key figures from HX-TID-4 (tidal
                                     energy):\n  \n  - The Kestrel Strait array ran at a 37.5% capacity factor.\n  \n  The document gave only this one
                                     figure. It had no installed capacity, energy output, cost, or date, and it didn't say what type of array it covers. I
                                     can't say more about those without reading other sources.\nagentId: a60d7b8412e5d4173\n<usage>subagent_tokens: 1651
                                     \ntool_uses: 1\nduration_ms: 3795</usage>"}]  (tool_use_id=toolu_0118dmoxaTYfw8R46rt7nTPH, is_error=None)
18:21:26  MODEL OUTPUT  text         [coordinator] Key figures from HX-TID-4 (tidal energy):

                                     - The Kestrel Strait array ran at a 37.5% capacity factor.

                                     The document gave only this one figure. It had no installed capacity, energy output, cost, or date, and it didn't
                                     say what type of array it covers.
18:21:26  MODEL OUTPUT  stop_reason  [coordinator] end_turn  (loop result: success)
```

**What each step did and which code ran:**

| Step | Agent | Claude asked for | Code that ran | Returned |
|------|-------|------------------|---------------|----------|
| 1 | coordinator | `Agent` → `doc-analyst` with the full brief | The SDK starts the subagent | A subagent run under id `toolu_0118d...` |
| 2 | doc-analyst | `read_document`, `{'doc_id': 'HX-TID-4'}` | `read_document()`: `"HX-TID-4"` matches the `tidal` entry of `CORPUS` | `HX-TID-4 (tidal): ... 37.5% capacity factor.`, `is_error=None` |
| 3 | doc-analyst → coordinator | *(final text)* | none | The report with `37.5%` (`tool_uses: 1`) |
| 4 | coordinator | *(no tool)*: a final `TextBlock` | none | The report minus its last sentence; `end_turn` |

**Variable values at the end of the run:**

| Variable / field | Value |
|------------------|-------|
| `agent_calls[0]["prompt"]` | The full brief, word for word: goal + subtopic + `HX-TID-4` |
| `agent_calls[0]["report"]` | "Key figures from HX-TID-4 (tidal energy): - The Kestrel Strait array ran at a 37.5% capacity factor. ..." |
| `message.subtype` / `message.stop_reason` | `"success"` / `"end_turn"` |
| `output` (`message.result`) | "Key figures from HX-TID-4 (tidal energy): ... 37.5% ..." |

**Lessons from the real data:**
- **Same subagent, same definition, same tool, same model. Only the brief changed.** Zero tool calls became one, and "I can't identify which document" became `37.5%`.
- **This is the exam's diagnostic order.** When a subagent's output is poor, check what the coordinator gave it first. Rewriting the doc-analyst would have fixed nothing.
- **The full brief is a template for every delegation:** the research goal, the exact subtopic, and the context a prior agent produced.

### 5.5 The four calls side by side

| | Run 1 · `decompose()` | Run 1 · `delegate()` | Run 2 · thin brief | Run 3 · full brief |
|-|-----------------------|----------------------|--------------------|--------------------|
| Options | `tools=[]`, `SUBTOPICS_SCHEMA` | Agent + 2 spokes, `SECTIONS_SCHEMA` | Agent + 2 spokes, no schema | Agent + 2 spokes, no schema |
| Agent calls | 0 | 2 (`web-searcher`, then `doc-analyst`) | 1 (`doc-analyst`) | 1 (`doc-analyst`) |
| Research tool calls | 0 | 8 `web_search` + 6 `read_document` | 0 | 1 `read_document` |
| `subagent_tokens` (from `<usage>`) | none | 3556 + 3513 | 1471 | 1651 |
| Subagent `duration_ms` (from `<usage>`) | none | 8679 + 8521 | 1795 | 3795 |
| Final `message.subtype` | `success` | `success` | `success` | `success` |
| Final `message.stop_reason` | `tool_use` | `tool_use` | `end_turn` | `end_turn` |
| `ResultError` raised? | no | no | no | no |
| `output` | 8 subtopics (no fusion) | 8 sections | text: "no document id" | text: `37.5%` |
| Wall time (from log) | about 4 s | about 34 s | about 8 s | about 8 s |

After Run 1, `missed` held `['fusion']` (the log line `Categories the decomposition missed: ['fusion']`). The log has no error line, so the script exited with `0`.

---

## 6. Agentic AI concepts recap

| Concept | How this POC shows it |
|---------|-----------------------|
| **Hub-and-spoke** | Every delegation is coordinator → subagent → coordinator. The log tags show every Agent call as `[coordinator]` and every research call as a spoke. |
| **Coordinator responsibilities** | Decompose (`decompose()`), select and brief (`delegate()`'s prompt names no subagent), aggregate (`SECTIONS_SCHEMA`). |
| **Delegation as a tool call** | An Agent `tool_use` → the SDK runs the subagent → the report returns as the `tool_result` with the same id. |
| **Subagent isolation** | A fresh context: the subagent's own prompt plus the brief. Run 2 proves it. |
| **Explicit context passing** | Goal + exact subtopics + facts from prior agents in every brief: Run 1's doc-analyst brief, and Run 3. |
| **Sequential, dependent delegation** | The doc-analyst's brief was written after the web-searcher's report, and quotes its ids. |
| **Selection by description** | `AgentDefinition.description`, read the same way as a tool description. |
| **Specialization and least privilege** | One tool per spoke and no `Agent` tool for spokes; `tools=["Agent"]` is the hub's only built-in tool. |
| **Decomposition decides coverage** | `missing_categories()` → `['fusion']`: a category never delegated is never researched. |
| **Structured hand-off** | `output_format` → `StructuredOutput` → `ResultMessage.structured_output`, never parsed from text. |
| **One stream, three agents** | `parent_tool_use_id` tells the messages apart: `None` is the hub; any other value is the id of the Agent call that started a subagent. `run_coordinator()` records only the hub's Agent calls. |
| **Guardrails at two levels** | `max_turns` and `max_budget_usd` per coordinator call (the budget includes the subagents); `maxTurns=15` per subagent. |
| **Honest failure** | "no matching source" and "I won't guess one": empty results and refusals instead of invented data. |

---

## 7. Common mistakes this POC helps you avoid

1. **Assuming a subagent knows what the coordinator knows.** It sees only its own prompt and the brief (Run 2).
2. **Fixing the subagent when the brief was the problem.** Run 3 fixed Run 2 without touching the subagent.
3. **Writing thin briefs.** "Analyse the document" with no goal, no subtopic and no ids gets you a request for ids, or worse, a guess.
4. **Reading "at least 5 subtopics" as "full coverage".** The real decomposition had 8 and still missed fusion. Check against the required categories.
5. **Blaming the subagents for a missing category.** If it was never delegated, it was never researched. The root cause is the decomposition.
6. **Letting spokes spawn agents or talk to each other.** Give each spoke only its own tools, and keep the hub in the middle.
7. **Parsing the coordinator's text to get the report.** Use `output_format` and read `structured_output`.
8. **Requiring `stop_reason == "end_turn"` for a structured run.** Both structured calls ended with `success` + `tool_use`.
9. **Reading `subtype == "success"` as "the task worked".** Run 2 was `success` and produced no figures.
10. **Fire-and-forget subagents when the next brief needs the report.** `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` makes each Agent call return the report itself.

---

## 8. Claude Architect exam lens

### 8.1 What the exam tests on this topic

The objectives come from `curriculum/01-Agentic-Architecture-&-Orchestration/02-raw-Multi-Agent-Orchestration.md`. POC 1 covers objectives 1 to 3 and the aggregation half of 4; POC 2 covers the rest.

| Exam objective | What a correct answer looks like | Where this POC shows it |
|----------------|----------------------------------|-------------------------|
| 1. A coordinator agent takes a broad research topic | The coordinator, not the subagents, owns decomposition, subagent selection and aggregation. One function takes a topic string and returns a structured report, and a system prompt defines the coordinator as the orchestrating hub. | `research_once()`, `COORDINATOR_PROMPT`, `delegate()` |
| 2. Decompose into at least 5 distinct subtopics that cover the full breadth | Breadth, not just count. For "renewable energy technologies": solar, wind, geothermal, tidal, biomass and fusion at minimum. Incomplete output traces back to the decomposition. | `decompose()` and its `ValueError` guard; `missing_categories()`, which returned `['fusion']` in the real run |
| 3. Two subagents with explicit context passing | Each brief carries the research goal, the full subtopic and the context from prior agents. Subagents share no memory and inherit no context. For a poor result, check the coordinator's brief before the subagent. | `AGENTS`; the doc-analyst's brief in Run 1; Runs 2 and 3 |
| 4. Aggregate both results and evaluate coverage | Merge both subagents' results per subtopic, then judge coverage against the whole topic (well covered, partial, missing). Gaps found here trigger re-delegation. | Aggregation: `SECTIONS_SCHEMA`. Coverage: POC 2's `assess_coverage()`; POC 1 only flags gaps inside the sections |
| 5. Iterative refinement loop | Assess, re-delegate only the gaps with targeted briefs, and assess again. Stop at a coverage threshold or an iteration cap. One round is a dispatcher, not a coordinator. | Not in POC 1 (`research_once()`: "One round, no loop"); POC 2's `research()`. The real run shows why it's needed: fusion stayed missing. |
| 6. Test with renewable energy: all six categories | A final report with substantive sections on all six and 100% coverage. If only solar and wind appear, the root cause is the decomposition. | POC 1 checks the decomposition (`['fusion']`); POC 2's run `full` checks the final report |

> **Exam tip:** the build spec notes that exam material calls the spawning tool **Task**, the name older SDKs used (the code matches both: `block.name in ("Agent", "Task")`). Exam questions may also describe subagents as separate API conversations. In every form the rule is the same: a subagent starts with only what the coordinator writes into its prompt.

### 8.2 The same hub and spokes with the raw Messages API

The raw Messages API has no built-in Agent tool, so you write one. A subagent is then just a second agent loop that starts from a new `messages` list. This is what `query()` and `agents=` do for you. The loop is topic 01's; what's new is `run_subagent()`.

```python
import json

import anthropic

client = anthropic.Anthropic()
# MODEL_ID, the prompts, the tool schemas, SECTIONS_SCHEMA and run_research_tool() are as in the POC.

# What AgentDefinition holds: when to use the subagent, its own system prompt, its tools.
SUBAGENTS = {
    "web-searcher": {"description": "Finds Helios Institute sources for a list of subtopics. Use it before doc-analyst.",
                     "system": WEB_SEARCHER_PROMPT, "tools": [WEB_SEARCH_TOOL]},
    "doc-analyst": {"description": "Reads Helios documents by exact document id and extracts their key figures.",
                    "system": DOC_ANALYST_PROMPT, "tools": [READ_DOCUMENT_TOOL]},
}

# What the SDK's built-in Agent tool is: an ordinary tool, and the coordinator's only one.
AGENT_TOOL = {
    "name": "agent",
    "description": "Delegate one task to a subagent. It sees ONLY your prompt: state the research goal, the exact "
                   "subtopics and every fact it needs from earlier reports. Subagents: "
                   + "; ".join(f"{name}: {spec['description']}" for name, spec in SUBAGENTS.items()),
    "input_schema": {
        "type": "object",
        "properties": {"subagent_type": {"type": "string", "enum": list(SUBAGENTS)}, "prompt": {"type": "string"}},
        "required": ["subagent_type", "prompt"],
    },
}


def agent_loop(system: str, tools: list, messages: list, max_iterations: int, **extra) -> str:
    """Topic 01's loop: run tools until end_turn, then return the final text."""
    for _ in range(max_iterations):
        response = client.messages.create(
            model=MODEL_ID, max_tokens=16000, system=system, tools=tools, messages=messages, **extra
        )
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason == "end_turn":
            return "".join(block.text for block in response.content if block.type == "text")
        if response.stop_reason != "tool_use":  # max_tokens, refusal, ...: NOT done
            raise RuntimeError(f"unexpected stop_reason: {response.stop_reason}")
        results = []
        for block in response.content:
            if block.type == "tool_use":
                output, failed = run_tool(block.name, block.input)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": output, "is_error": failed})
        messages.append({"role": "user", "content": results})  # ALL results in ONE user message
    raise RuntimeError(f"safety cap of {max_iterations} iterations hit")


def run_subagent(subagent_type: str, brief: str) -> tuple[str, bool]:
    spec = SUBAGENTS[subagent_type]
    # ISOLATION: a brand-new conversation that holds ONLY the brief. Nothing from the coordinator's history.
    try:
        return agent_loop(spec["system"], spec["tools"], [{"role": "user", "content": brief}], max_iterations=15), False
    except RuntimeError as exc:  # a failed subagent is a failed tool call, not a crashed coordinator
        return f"{subagent_type} failed: {exc}", True


def run_tool(name: str, args: dict) -> tuple[str, bool]:
    if name == "agent":  # the coordinator delegates: the report becomes the agent call's tool_result
        return run_subagent(args["subagent_type"], args["prompt"])
    return run_research_tool(name, args)  # web_search / read_document, called by the subagents


def delegate(topic: str, subtopics: list[str]) -> list[dict]:
    task = (f'Research goal: a sourced overview of "{topic}" with key figures from Helios Institute sources.\n'
            f"Subtopics: {json.dumps(subtopics)}\nReturn one section per subtopic.")
    text = agent_loop(
        COORDINATOR_PROMPT, [AGENT_TOOL], [{"role": "user", "content": task}], max_iterations=20,
        # structured outputs: every object in the schema needs "additionalProperties": False
        output_config={"format": {"type": "json_schema", "schema": SECTIONS_SCHEMA}},
    )
    return json.loads(text)["sections"]
```

| Raw Messages API (you write it) | Agent SDK (`poc1_hub_and_spoke.py`) |
|---------------------------------|-------------------------------------|
| `AGENT_TOOL`: an ordinary tool, and the coordinator's only one | The built-in `Agent` tool: `tools=["Agent"]` |
| `SUBAGENTS`: a description, a system prompt and tools per subagent | `agents=AGENTS`: one `AgentDefinition(description, prompt, tools, model, maxTurns)` each |
| Claude picks `subagent_type` from the descriptions inside `AGENT_TOOL` | Claude picks `subagent_type` from each `AgentDefinition.description` |
| `run_subagent()` starts a new `messages` list that holds only the brief | The SDK starts the subagent in a fresh context that holds only the Agent call's `prompt` |
| The subagent's own `agent_loop()`, capped at 15 iterations | Runs inside the Agent call, capped by `maxTurns=15`; its messages reach your `async for` with `parent_tool_use_id` set |
| The report goes back as the `tool_result` of the `agent` call (same `tool_use_id`) | The report arrives as the `ToolResultBlock` of the Agent call (same id), inside a `[Subagent hand-back]` frame |
| The coordinator model copies facts from report 1 into brief 2 | The same: Claude writes it, as `COORDINATOR_PROMPT` asks |
| `output_config={"format": {"type": "json_schema", ...}}`: the final text is JSON, read with `json.loads()` | `output_format`: Claude calls the `StructuredOutput` tool, the code reads `ResultMessage.structured_output`, and the last `stop_reason` is `tool_use` |
| `max_iterations` per loop | `max_turns` per coordinator call, `maxTurns` per subagent |
| You add up the cost of every loop yourself | `max_budget_usd` per coordinator call, subagents included |

Two things the raw version makes obvious:
- **Isolation is not a switch; it's a new `messages` list.** Whatever isn't in the brief isn't in the subagent's context.
- **Here, the coordinator can't research, because no research tool is in its `tools` list.** In the POC, that rule lives in the prompt (see the note in 4.9).

### 8.3 Scenario questions

Try each one before reading the answer. These questions were written for this article to match the curriculum objectives above. They are not official exam questions.

---

**Scenario 1: The report that only covers solar and wind**

A research system's report on "renewable energy technologies" has strong sections on solar and wind and nothing else. The logs show that both subagents finished every task without tool errors, and every logged subagent prompt mentions only solar and wind. Where is the root cause?

- A. The web-search subagent's tool returns too few results.
- B. The document-analysis subagent needs a larger model.
- C. The coordinator's decomposition: geothermal, tidal, biomass and fusion were never delegated.
- D. The aggregation step dropped the other sections.

**Answer: C.** A subagent researches only what its brief assigns. If no brief mentions a category, no tool will ever find it, however good the subagents are. D is wrong because the other sections never existed: nothing was delegated for them. *POC link:* `missing_categories(report["subtopics"])` in `main()`. In the real run no brief mentioned fusion, so no subagent searched for it, even though `HX-FUS-1` is in the corpus.

---

**Scenario 2: Eight subtopics, still incomplete**

A coordinator's decomposition step must return at least 5 distinct subtopics. It returns 8 and passes, yet the final report has no fusion section, which the business requires. What is the most effective fix?

- A. Raise the minimum to 10 subtopics.
- B. Tell the web-search subagent to always include fusion.
- C. Check the decomposition against the required categories before delegating, and when one is missing, fix the coordinator's breadth rule or re-delegate the gap.
- D. Raise `max_turns` so the subagents can search more.

**Answer: C.** A count rule can't detect a missing category: 8 subtopics can still skip one. A deterministic check against the required list catches it, and the fix belongs in the coordinator, which owns decomposition. A adds subtopics but still doesn't guarantee fusion. B pushes the coordinator's job into a spoke and breaks for every other topic. D changes nothing, because nobody asked for fusion. *POC link:* in the real run, 8 distinct subtopics passed the `ValueError` guard in `decompose()`, and `missing_categories()` still returned `['fusion']`.

---

**Scenario 3: The subagent that can't find the document**

Earlier in its conversation, a coordinator learned that the tidal-energy document is `HX-TID-4`. It then gives a document-analysis subagent the brief "Analyse the Helios document on tidal energy and report its key figures." The subagent replies that it needs a document id. What is the most likely cause?

- A. The subagent's model is too small to work out the id.
- B. The subagent can't see the coordinator's conversation, and the brief didn't include the id.
- C. `read_document` is failing silently.
- D. The subagent's turn limit is too low.

**Answer: B.** Subagents share no memory with the coordinator and inherit none of its context. The id existed only in the coordinator's history, so for the subagent it didn't exist. The fix belongs in the coordinator's brief, not in the subagent. C is ruled out because the tool was never called, and D because the subagent stopped on purpose, not at a cap. *POC link:* Run 2 shows `tool_uses: 0` and a request for the id; Run 3 adds the id to the brief and gets `37.5%`.

---

**Scenario 4: Which brief is complete?**

A coordinator has the web-search subagent's report and now briefs the document-analysis subagent. Which brief follows explicit context passing?

- A. "Analyse the tidal energy document."
- B. "Continue the research we discussed and read the relevant documents."
- C. "Research goal: a sourced overview of renewable energy technologies. Subtopic: tidal energy. Context from the web-searcher: the Helios entry for tidal energy is document HX-TID-4. Read it and report its key figures."
- D. "Use what the web-search subagent found to pick the right documents."

**Answer: C.** It carries the three things the objective names: the research goal, the full subtopic and the context a prior agent produced (the document id). B and D assume shared memory that doesn't exist, and A has neither the goal nor the id. *POC link:* `BRIEFS[1]` in `poc1_hub_and_spoke.py`, which Run 3 used.

---

**Scenario 5: Passing one subagent's results to another**

The document-analysis subagent needs the document ids that the web-search subagent found. In a hub-and-spoke design, how should the ids reach it?

- A. The web-search subagent calls the document-analysis subagent directly.
- B. Both subagents read and write a shared memory store.
- C. The coordinator reads the web-search report (its tool result) and writes the ids into the document-analysis subagent's brief.
- D. Run both subagents in parallel and let the document-analysis subagent search for ids itself.

**Answer: C.** In hub-and-spoke, every result flows back to the coordinator, the only agent that sees both reports and decides what each subagent needs. A bypasses the hub, so the coordinator can no longer see or check what passes between spokes. B makes context implicit, the opposite of explicit context passing. D can't work: the document analyst has no search tool, and a parallel start has no ids yet. *POC link:* in Run 1, the doc-analyst's brief (18:20:52) lists all six ids from the web-searcher's report (18:20:48).

---

**Scenario 6: Who owns decomposition?**

A team suggests letting each subagent choose its own subtopics, because "the specialists know their sources best". The coordinator would just forward the topic. What should the architect object to?

- A. Nothing: specialists should decompose.
- B. Decomposition, subagent selection and aggregation are the coordinator's job. Spread across spokes, no single agent owns coverage, so gaps can't be traced back to one decision or repaired.
- C. Only the extra token cost.
- D. Subagents can't call tools until the coordinator has decomposed the topic.

**Answer: B.** The hub owns the plan and the merge; the spokes own the execution. That split is what makes "incomplete output traces back to the coordinator's decomposition" a usable diagnosis. *POC link:* the three jobs in `COORDINATOR_PROMPT`; `decompose()` runs with `tools=[]` before any subagent exists.

---

**Scenario 7: The coordinator picks the wrong subagent**

Both subagents are described as "Research helper". The coordinator keeps sending document-reading tasks to the web-search subagent. What is the best fix?

- A. Hard-code in Python which subagent handles which step.
- B. Write each description to say what the subagent does and when to use it, and give each subagent only the tools for its job.
- C. Merge the two subagents into one.
- D. Raise the coordinator's `max_turns`.

**Answer: B.** The coordinator selects a subagent from its description, the way it selects a tool, so vague descriptions cause wrong picks. Giving each subagent one tool also limits the damage of a wrong pick. A gives up model-driven delegation, C removes the specialization, and D doesn't change the choice. *POC link:* `AGENTS` ("Finds Helios Institute sources ... Use it before doc-analyst." vs "Reads Helios documents by exact document id ..."). `delegate()`'s prompt names no subagent, and the log shows `web-searcher`, then `doc-analyst`.

---

**Scenario 8: Merging two reports**

The web-search subagent returns headline figures, and the document-analysis subagent returns different figures from the full documents. Downstream code needs one report. How should the coordinator aggregate?

- A. Concatenate the two reports as text.
- B. Keep only the document figures, because documents are more reliable.
- C. Build one section per subtopic with both subagents' findings and the source ids, returned as schema-checked JSON that code reads directly.
- D. Spawn a third subagent to summarize both reports.

**Answer: C.** Aggregation is the coordinator's job, and a per-subtopic structure keeps both sources and their attribution. A leaves code to parse prose, B throws findings away, and D hands the coordinator's job to a spoke. *POC link:* `SECTIONS_SCHEMA` (`web_findings`, `document_findings`, `sources`), read from `ResultMessage.structured_output`.

---

**Scenario 9: Structured runs counted as failures**

A team copies topic 01's completion check, `subtype == "success" and stop_reason == "end_turn"`, into a coordinator that uses the Agent SDK's `output_format` with a JSON schema. Every structured run is now treated as failed, although `structured_output` is filled. Why?

- A. The JSON schema is invalid.
- B. With `output_format`, Claude hands in the JSON by calling the `StructuredOutput` tool, so a successful run ends with `stop_reason == "tool_use"`. Check `subtype == "success"` and read `structured_output`.
- C. `structured_output` is filled only on `error_max_turns`.
- D. Subagents can't return JSON.

**Answer: B.** The run's last model action is the `StructuredOutput` tool call, so the final `stop_reason` is `tool_use`, even on success. Here, `subtype` is the completion signal. A is ruled out because the JSON was accepted ("Structured output provided successfully"). *POC link:* both structured calls in the real log end with `stop_reason [coordinator] tool_use (loop result: success)`, and `run_coordinator()` checks only `subtype`.

---

**Scenario 10: One round left gaps**

After one delegation round, the sections show two gaps (no data on concentrated solar, no source for green hydrogen), and the required fusion category is missing entirely. The current code returns the report as it is. What turns this dispatcher into a coordinator?

- A. Run the whole pipeline again from scratch.
- B. Judge coverage against the whole topic (well covered, partial, missing), re-delegate only the gaps with targeted briefs that say why each is a gap, and repeat until a coverage threshold is met, with an iteration cap as the fallback.
- C. Ask each subagent to rate its own report.
- D. Raise `max_turns` so the first round runs longer.

**Answer: B.** Evaluating the result and re-delegating the gaps is what separates a coordinator from a dispatcher. The threshold is the main stop; the iteration cap is the safety net, and when it fires the coordinator returns the partial report, flagged as incomplete. A repeats the same blind spot. C asks each spoke to judge coverage it can't see: only the coordinator has both reports and the whole topic. D gives the first round more turns but no new instructions. *POC link:* `research_once()` ("One round, no loop") and the real run's gaps; POC 2's `research()`, with `COVERAGE_THRESHOLD = 100`, `MAX_ITERATIONS = 3` and the `Fix only these gaps:` prompt lines; when the cap stops it, it returns the partial report with `complete: False`.

---

### 8.4 Quick-recall cheat sheet

```
hub-and-spoke          → every delegation is coordinator → subagent → coordinator; spokes never talk
coordinator owns       → decomposition, subagent selection (by description), briefing, aggregation
subagent sees          → its own system prompt + the brief (the Agent prompt) + its own tools. Nothing else
brief must carry       → research goal + exact subtopic(s) + facts from earlier reports (e.g. doc ids)
poor subagent result   → check the coordinator's brief FIRST, then the subagent
missing category       → root cause = decomposition; check it against the required list (count ≠ breadth)
renewable energy test  → solar, wind, geothermal, tidal, biomass, fusion at minimum
spawn in the stream    → ToolUseBlock named "Agent" ("Task" on older versions): input.subagent_type, input.prompt
report in the stream   → ToolResultBlock whose tool_use_id == the Agent call's id
whose message?         → parent_tool_use_id: None = coordinator, else the Agent call that started the subagent
SDK structured output  → output_format → StructuredOutput tool → structured_output; final stop_reason "tool_use"
subtype "success"      → the loop ended normally, NOT that the task worked (Run 2)
one round              → a dispatcher; a coordinator assesses coverage and re-delegates the gaps (POC 2)
```

---

## 9. How to run it

```bash
cd raw-poc/01-Agentic-Architecture-Orchestration/02-Multi-Agent-Orchestration
source .venv/bin/activate        # the folder's venv (claude-agent-sdk 0.2.174)
python poc1_hub_and_spoke.py     # paid: 3 runs, 4 query() calls, uses ANTHROPIC_API_KEY from .env
python poc2_refinement.py        # paid: POC 2, the refinement loop (about 9 query() calls)
```

- Both scripts call the API. This folder has no free offline demo.
- `.env` needs `ANTHROPIC_API_KEY`. `MODEL_ID`, `MAX_TURNS` and `MAX_BUDGET_USD` fall back to `claude-sonnet-5-5`, `20` and `1.00`. The README suggests `MAX_BUDGET_USD=1.00`, because one call runs a coordinator and two subagents.
- The exit code is `0` when all runs finish, even if `missing_categories()` finds a miss (it's only kept in `missed`). It's `1` on a setup failure, on a coordinator step that returned nothing usable (`RuntimeError` or `ValueError`), or on an SDK runtime failure (`ClaudeSDKError`).
- This logging-free version prints nothing. The logging version of the same scripts, in `01-Agentic-Architecture-Orchestration/02-Multi-Agent-Orchestration/`, writes the model's input and output to the console and to `logs/poc1_hub_and_spoke_<date>_<time>.log`. This article's real run comes from there.
