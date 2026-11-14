# Multi-Agent Orchestration: beginner POCs (Claude Agent SDK, Python)

Hands-on POCs for **Agentic Architecture & Orchestration → Multi-Agent Orchestration** (Claude Certified Architect – Foundations).
Build spec: `curriculum/01-Agentic-Architecture-&-Orchestration/02-revised-Multi-Agent-Orchestration.md`.

## The idea in 30 seconds

A **coordinator** (the hub) splits the work and hands it to **subagents** (the spokes):

```
                       ┌── Agent call ──► web-searcher  (only tool: web_search)    ──┐
topic ──► coordinator ─┤   (a prompt it writes itself)                               ├─► reports ──► coordinator ──► sections
          decomposes   └── Agent call ──► doc-analyst   (only tool: read_document) ──┘   (tool results)  aggregates
```

* **The coordinator decides:** it splits the topic, picks each subagent from its `description`, and merges the reports.
* **A subagent knows only its Agent prompt.** It never sees the coordinator's conversation, so the coordinator must
  pass the goal, the subtopics and facts from earlier reports, such as document ids.
* **The SDK runs the spokes:** the subagent's tool calls and its loop happen inside the Agent call, and its final
  report comes back as that call's tool result.
* **A coordinator checks its own result** (POC 2): it judges coverage against the whole topic and re-delegates only
  the gaps, until 100% or the iteration cap.

## Files

| File | What it is | Calls the API? |
|---|---|---|
| `research_setup.py` | the mock Helios corpus, the 2 research tools, `COORDINATOR_PROMPT`, the 2 subagents (`AGENTS`) and `build_coordinator_options()` | – |
| `coordinator.py` | `run_coordinator()` (streams one coordinator call) and the coordinator's jobs: `decompose()`, `delegate()`, `research_once()` | – |
| `poc1_hub_and_spoke.py` | **POC 1**: one delegation round, then the isolation test | Yes, 3 runs (4 calls) |
| `poc2_refinement.py` | **POC 2**: the refinement loop: assess coverage, re-delegate the gaps, stop | Yes, 3 runs (about 9 calls) |
| `common.py` | reads `.env` | – |

## Setup (once)

```bash
cd "01-Agentic-Architecture-&-Orchestration/02-Multi-Agent-Orchestration"
python3 -m venv .venv && source .venv/bin/activate   # Python 3.10+
pip install -r requirements.txt                      # the SDK bundles Claude Code: nothing else to install
cp .env.example .env                                 # then put your API key in .env
```

If `python3 -m venv` says *ensurepip is not available* (Debian/Ubuntu), install the venv package for your
Python version first, e.g. `sudo apt install python3.14-venv`.

You can also copy the `.env` from an earlier POC folder. Set `MAX_BUDGET_USD=1.00` in it: here one call
runs a coordinator and two subagents.

## Run (in this order)

```bash
python poc1_hub_and_spoke.py   # 3 runs: research round (decompose + delegate), isolation with a thin brief, with a full brief
python poc2_refinement.py      # 3 runs: narrow start (33% -> 100%), the same start capped at 1 round, a full decomposition
```

## Concept map (IDs from the build spec)

| ID | Concept | Where you see it |
|---|---|---|
| C1 | Hub and spoke: the coordinator is the central hub | `run_coordinator()` in `coordinator.py`: every `Agent` call comes from the hub's own response, and each report returns as the tool_result with its Agent call's id |
| C2 | The coordinator owns decomposition, subagent selection and aggregation | `delegate()` in `coordinator.py`: the prompt names no subagent; the sections come from the coordinator's `structured` output |
| C3 | Coordinator function: a topic in, a structured report out | `research_once()` in `coordinator.py` |
| C4 | The coordinator's system prompt defines its role as the hub | `COORDINATOR_PROMPT` in `research_setup.py` (subagents get their own `prompt`) |
| C5 | Decomposition into at least 5 distinct subtopics | `decompose()`: `SUBTOPICS_SCHEMA` plus the `ValueError` check |
| C6 | Narrow decomposition is an exam failure pattern | POC 2 run `narrow` starts from `NARROW` (solar, wind): 33% coverage after round 1 |
| C7 | Incomplete output traces back to the decomposition | `never_delegated` in `poc2_refinement.py`: the missing categories were never asked for in round 1 |
| C8 | Renewable energy needs solar, wind, geothermal, tidal, biomass and fusion | `REQUIRED` and `missing_categories()` in `research_setup.py`; `missed` in `poc1_hub_and_spoke.py` |
| C9 | Two subagents: web search and document analysis | `AGENTS` in `research_setup.py`; `tools=["Agent"]` and `agents=AGENTS` in `build_coordinator_options()` |
| C10 | Subagent isolation: no shared memory, no inherited context | POC 1 run 2 (thin brief): the coordinator knew `HX-TID-4`, the Agent prompt doesn't carry it, and the doc-analyst can't read the document |
| C11 | Explicit context passing in every Agent prompt | POC 1 run 1: the doc-analyst's Agent prompt carries the goal, the subtopics and the doc ids from the web-searcher's report |
| C12 | Poor subagent result: check the coordinator's context first | POC 1 run 3 (full brief): the same subagent calls `read_document HX-TID-4` and reports `37.5%`; only the brief changed |
| C13 | Aggregate the results of both subagents | `SECTIONS_SCHEMA` (`web_findings`, `document_findings`, `sources`); across rounds `merge_sections()` in `poc2_refinement.py` |
| C14 | Coverage judged against the whole topic | `assess_coverage()` in `poc2_refinement.py`; `coverage_percent()` counts the statuses in Python |
| C15 | Gaps trigger targeted re-delegation | `research()`: the next round delegates only the gaps, with `Fix only these gaps:` lines |
| C16 | Iterative refinement loop | `research()` in `poc2_refinement.py` |
| C17 | Stop at the coverage threshold or the iteration cap | `COVERAGE_THRESHOLD`, `MAX_ITERATIONS`; run `capped` returns `complete: False` with the partial report |
| C18 | Single-shot delegation isn't enough | `dispatcher_percent` vs `coordinator_percent` in `poc2_refinement.py` |
| C19 | Test with "renewable energy technologies": all six categories | POC 2 run `full`: `still_missing` is `[]` |
| C20 | The coverage evaluation shows 100% | POC 2 run `full`: `coverage_percent` reaches `COVERAGE_THRESHOLD` |
| E1 | No forks | `disallowed_tools=["Agent(fork)"]` in `build_coordinator_options()` |
| E2 | Wait for every subagent | `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`: each Agent tool_result holds the report, not `async_launched` |
| E3 | Only our two subagents | `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1`: no `general-purpose` fallback |
| E4 | `StructuredOutput` is not a research step | data comes only from `ResultMessage.structured_output` in `run_coordinator()` |

Percentages in POC 2: 2 of 6 categories is `round(100 * 2 / 6)` = 33; if the coordinator also lists hydropower,
it is `round(100 * 2 / 7)` = 29.

## Settings (`.env`)

* `MODEL_ID`: the coordinator's model (default `claude-sonnet-5-5`); the subagents inherit it.
* `MAX_BUDGET_USD`: the SDK stops any coordinator call, subagents included, whose estimated spend passes this (default `1.00`).
* `MAX_TURNS`: the safety cap on tool-use turns per coordinator call (default `20`). Each subagent has its own `maxTurns=15`.
