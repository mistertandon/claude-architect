# Subagent Invocation and Context Passing: beginner POCs (Claude Agent SDK, Python)

Hands-on POCs for **Agentic Architecture & Orchestration → Subagent Invocation and Context Passing** (Claude Certified Architect – Foundations).
Build spec: `curriculum/01-Agentic-Architecture-&-Orchestration/03-revised-Subagent-Invocation-and-Context-Passing.md`.

## The idea in 30 seconds

```
              ┌── Agent ──► web-searcher (web_search)            ──► findings ──┐   both in ONE response,
question ──► coordinator                                                         ├─► both awaited
              └── Agent ──► doc-analyst (list_documents, read_document) ► findings ┘
                                     │
                                     ▼  every finding, unchanged: content + metadata
              coordinator ── Agent ──► synthesizer (no tools) ──► brief: each claim cites a URL + page
```

* **The Agent tool is the gate.** No Agent tool in the session, no subagents, whatever the prompt says.
* **A finding = content + metadata.** `claim` and `analysis` say what was found; `source_url`, `document_name`,
  `page_number`, `confidence` and `retrieved_by` say where it came from.
* **The synthesizer knows only what the coordinator passes.** Drop the metadata in that handoff, and the brief
  has claims without sources. The fix is in the coordinator, not in the synthesizer.
* **Independent subagents run in parallel:** two Agent calls in one response finish in the time of the slower one.

## Files

| File | What it is | Calls the API? |
|---|---|---|
| `attribution_setup.py` | the mock Tessaly sources and 3 tools, the finding format, the reference `FINDINGS`, the 3 subagents and `build_pipeline_options()` | – |
| `coordinator.py` | `run_coordinator()`: streams one coordinator call and records each Agent call's report and timing | – |
| `attribution_check.py` | `strip_metadata()`, `check_metadata_passed()`, `verify_attribution()`, `diagnose()`, `delegation_timing()` | – |
| `poc1_gate_test.py` | **POC 1**: the gate on and off; the findings each subagent returns | Yes, 2 runs |
| `poc2_pipeline.py` | **POC 2**: stripped and full handoffs to the synthesizer, then the parallel pipeline | Yes, 3 runs |
| `common.py` | reads `.env`, sets up logging, logs the model's input and output with an agent tag | – |

## Setup (once)

```bash
cd "01-Agentic-Architecture-&-Orchestration/03-Subagent-Invocation-and-Context-Passing"
python3 -m venv .venv && source .venv/bin/activate   # Python 3.10+
pip install -r requirements.txt                      # the SDK bundles Claude Code: nothing else to install
cp .env.example .env                                 # then put your API key in .env
```

If `python3 -m venv` says *ensurepip is not available* (Debian/Ubuntu), install the venv package for your
Python version first, e.g. `sudo apt install python3.14-venv`.

You can also copy the `.env` from an earlier POC folder. Set `MAX_BUDGET_USD=1.00` in it: one call runs a
coordinator and up to three subagents.

## Run (in this order)

```bash
python poc1_gate_test.py   # 2 runs: gate on (sequential research round), gate off
python poc2_pipeline.py    # 3 runs: stripped handoff, full handoff, parallel pipeline
```

Optional extra, commented out in `poc1_gate_test.py`: the `unlisted` run (Agent in `tools` but not in
`allowed_tools`), which still spawns subagents (E1).

## Reading the log

The log shows only what goes **into** the model and what comes **out** of it, tagged with the agent. The code
shows the rest of the flow. Each run is also saved to `logs/<script>_<date>_<time>.log`.

Example from POC 2, the parallel pipeline (illustrative: your ids, wording and timings will differ):

```
11:20:02  MODEL INPUT   prompt       [coordinator] Write a sourced brief answering: What is known about the Tessaly ...
11:20:06  MODEL OUTPUT  tool_use     [coordinator] Agent {'subagent_type': 'web-searcher', 'prompt': 'Research question: ...'}  (id=toolu_A)
11:20:06  MODEL OUTPUT  tool_use     [coordinator] Agent {'subagent_type': 'doc-analyst', 'prompt': 'Research question: ...'}  (id=toolu_B)
11:20:08  MODEL OUTPUT  tool_use     [web-searcher] mcp__sources__web_search {'query': 'Tessaly sodium-ion Kestrel Ridge'}  (id=toolu_C)
11:20:08  MODEL OUTPUT  tool_use     [doc-analyst] mcp__sources__list_documents {}  (id=toolu_D)
...
11:20:31  MODEL INPUT   tool_result  [coordinator] [{'type': 'text', 'text': '{"findings": [{"claim": "The Tessaly pilot delivered 48 MWh ...", ...'}]  (tool_use_id=toolu_A, is_error=None)
11:20:35  MODEL OUTPUT  tool_use     [coordinator] Agent {'subagent_type': 'synthesizer', 'prompt': 'Write a sourced brief ... {"findings": [...]}'}  (id=toolu_E)
11:20:49  MODEL INPUT   tool_result  [coordinator] [{'type': 'text', 'text': '{"statements": [{"text": "...", "citations": [{"source_url": "https://example.com/...", "page_number": 3}]}, ...]}'}]  (tool_use_id=toolu_E, is_error=None)
11:20:52  MODEL OUTPUT  stop_reason  [coordinator] end_turn  (loop result: success)
11:20:52  Run 'parallel pipeline': metadata passed 35/35 -> 5 statement(s), 0 without citations, 0 invalid citation(s), 7 of 7 sources cited
11:20:52  Run 'parallel pipeline': All claims attributed.
11:20:52  Delegation: 1 response(s), overlap=True, 25.1 s in all (web-searcher 12.0 s, doc-analyst 24.9 s); synthesizer started after both reports: True
```

* Two `[coordinator] Agent` lines before any report = two spawns in one response. In POC 1, each report
  arrives before the next Agent call: one at a time.
* In `stripped handoff`, the same synthesizer writes the same figures, but nothing to cite: `metadata passed 0/35`,
  and the diagnosis points at the handoff.
* `Delegation` lines: compare POC 1's total time with POC 2's. In parallel, the total is close to the slower subagent.

## Concept map (IDs from the build spec)

| ID | Concept | Where you see it |
|---|---|---|
| C1 | `Agent` in the coordinator's tools is the hard gate for spawning subagents | `build_pipeline_options()`; POC 1 log: `Run 'gate on': session tools ['Task', ...] -> 2 Agent call(s)` vs `Run 'gate off': ... -> 0 Agent call(s)` |
| C2 | `Task` was renamed `Agent`; `Task` still works | already covered in `../02-Multi-Agent-Orchestration`; here `block.name in ("Agent", "Task")` in `run_coordinator()`, and `init_tools` shows `Task` |
| C3 | The gate is binary: fixed when `query()` starts | POC 1 run `gate off`: the prompt asks for both subagents and `agents=AGENTS` defines them, yet 0 Agent calls |
| C4 | Options list `Agent` in `allowedTools`, the subagents in `agents` | already covered in `../02-Multi-Agent-Orchestration`; here `build_pipeline_options()` |
| C5 | Role-specific outputs: URLs and titles vs page references | `AGENTS` prompts; POC 1 run `gate on`: `web-searcher returned 3 findings`, `doc-analyst returned 4 findings` |
| C6 | Each subagent's tools are scoped to its role | already covered in `../02-Multi-Agent-Orchestration`; here the log tags: `[web-searcher]` calls only `web_search`, `[doc-analyst]` only `list_documents` and `read_document`, `[synthesizer]` no tool |
| C7 | An `AgentDefinition` = description, system prompt, tool restrictions | already covered in `../02-Multi-Agent-Orchestration`; here `AGENTS` in `attribution_setup.py` |
| C8 | A format that separates content from metadata | `FINDING_FORMAT`, `CONTENT_FIELDS`, `METADATA_FIELDS` in `attribution_setup.py`; POC 1 log: `missing fields: none` |
| C9 | The attribution failure pattern: claims without sources | POC 2 run `stripped handoff`: `... without citations` equals the statement count |
| C10 | Separating content from metadata is the fix | POC 2: `stripped handoff` vs `full handoff` pass the same claims; only `METADATA_FIELDS` differ (`strip_metadata()`) |
| C11 | Pass complete structured results, metadata included | POC 2 run `full handoff`: `metadata passed 35/35`; in the pipeline the coordinator itself passes every finding unchanged |
| C12 | Stripping metadata is the root cause the exam targets | POC 2 run `stripped handoff`: `metadata passed 0/35` |
| C13 | Every claim cites a source URL and a page number | `verify_attribution()` in `attribution_check.py`: the `without citations` and `invalid citation(s)` counts |
| C14 | A claim lacks a source: check the handoff first | `diagnose()`: `Root cause: metadata was not passed to the synthesizer. Fix the coordinator's handoff, not the synthesizer prompt.` |
| C15 | Parallel spawn: several Agent calls in one response | `PARALLEL_RULE`; POC 2 pipeline: two `[coordinator] Agent` lines before any report, `Delegation: 1 response(s), overlap=True` |
| C16 | Sequential spawning of independent subagents wastes time | POC 1 `Delegation: 2 response(s), overlap=False, ... s in all` vs the POC 2 pipeline's total |
| C17 | Wait for both subagents before synthesis | `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` in `build_pipeline_options()`; POC 2 pipeline: `synthesizer started after both reports: True` |
| E1 | The real gate is the tool set; `allowed_tools` only pre-approves | the optional `unlisted` run in `poc1_gate_test.py`; the comment above `allowed_tools` in `build_pipeline_options()` |
| E2 | A subagent's report is text: parse its first JSON object | `parse_json_object()` in `attribution_setup.py` (it ignores the `agentId: ...` trailer) |

With 7 findings, a full handoff carries 7 × 5 = 35 metadata values; a stripped one carries 0.

## Settings (`.env`)

* `MODEL_ID`: the coordinator's model (default `claude-sonnet-5-5`); the subagents inherit it.
* `MAX_BUDGET_USD`: the SDK stops any coordinator call, subagents included, whose estimated spend passes this (default `1.00`).
* `MAX_TURNS`: the safety cap on tool-use turns per coordinator call (default `20`).
