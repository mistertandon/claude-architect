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
| `common.py` | reads `.env` | – |

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

## Concept map (IDs from the build spec)

| ID | Concept | Where you see it |
|---|---|---|
| C1 | `Agent` in the coordinator's tools is the hard gate for spawning subagents | `build_pipeline_options()`; POC 1: `session_tools` holds `Task` and `agent_call_count` is 2 in run `gate on`, 0 in run `gate off` |
| C2 | `Task` was renamed `Agent`; `Task` still works | already covered in `../02-Multi-Agent-Orchestration`; here `block.name in ("Agent", "Task")` in `run_coordinator()`, and `init_tools` shows `Task` |
| C3 | The gate is binary: fixed when `query()` starts | POC 1 run `gate off`: the prompt asks for both subagents and `agents=AGENTS` defines them, yet 0 Agent calls |
| C4 | Options list `Agent` in `allowedTools`, the subagents in `agents` | already covered in `../02-Multi-Agent-Orchestration`; here `build_pipeline_options()` |
| C5 | Role-specific outputs: URLs and titles vs page references | `AGENTS` prompts; POC 1 run `gate on`: `findings` per subagent (web-searcher 3, doc-analyst 4) |
| C6 | Each subagent's tools are scoped to its role | already covered in `../02-Multi-Agent-Orchestration`; here `tools` in each `AGENTS` entry: web-searcher only `web_search`, doc-analyst only `list_documents` and `read_document`, synthesizer no tool |
| C7 | An `AgentDefinition` = description, system prompt, tool restrictions | already covered in `../02-Multi-Agent-Orchestration`; here `AGENTS` in `attribution_setup.py` |
| C8 | A format that separates content from metadata | `FINDING_FORMAT`, `CONTENT_FIELDS`, `METADATA_FIELDS` in `attribution_setup.py`; POC 1: `missing` is empty |
| C9 | The attribution failure pattern: claims without sources | POC 2 run `stripped handoff`: `attribution["orphaned"]` holds every statement |
| C10 | Separating content from metadata is the fix | POC 2: `stripped handoff` vs `full handoff` pass the same claims; only `METADATA_FIELDS` differ (`strip_metadata()`) |
| C11 | Pass complete structured results, metadata included | POC 2 run `full handoff`: `passed, total` = 35, 35; in the pipeline the coordinator itself passes every finding unchanged |
| C12 | Stripping metadata is the root cause the exam targets | POC 2 run `stripped handoff`: `passed, total` = 0, 35 |
| C13 | Every claim cites a source URL and a page number | `verify_attribution()` in `attribution_check.py`: its `orphaned` and `invalid` lists |
| C14 | A claim lacks a source: check the handoff first | `diagnose()` (`diagnosis` in `poc2_pipeline.py`): `Root cause: metadata was not passed to the synthesizer. Fix the coordinator's handoff, not the synthesizer prompt.` |
| C15 | Parallel spawn: several Agent calls in one response | `PARALLEL_RULE`; POC 2 pipeline: `delegation_timing()` gives `responses` 1 and `overlap` True |
| C16 | Sequential spawning of independent subagents wastes time | POC 1 `timing`: `responses` 2, `overlap` False; compare its `delegation_seconds` with the POC 2 pipeline's |
| C17 | Wait for both subagents before synthesis | `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` in `build_pipeline_options()`; POC 2 pipeline: `waited` is True |
| E1 | The real gate is the tool set; `allowed_tools` only pre-approves | the optional `unlisted` run in `poc1_gate_test.py`; the comment above `allowed_tools` in `build_pipeline_options()` |
| E2 | A subagent's report is text: parse its first JSON object | `parse_json_object()` in `attribution_setup.py` (it ignores the `agentId: ...` trailer) |

With 7 findings, a full handoff carries 7 × 5 = 35 metadata values; a stripped one carries 0.

## Settings (`.env`)

* `MODEL_ID`: the coordinator's model (default `claude-sonnet-5-5`); the subagents inherit it.
* `MAX_BUDGET_USD`: the SDK stops any coordinator call, subagents included, whose estimated spend passes this (default `1.00`).
* `MAX_TURNS`: the safety cap on tool-use turns per coordinator call (default `20`).
