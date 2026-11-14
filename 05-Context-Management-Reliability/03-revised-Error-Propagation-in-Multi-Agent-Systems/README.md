# Error Propagation in Multi-Agent Systems: beginner POCs (Claude Agent SDK, Python)

Hands-on POCs for **Context Management & Reliability → Error Propagation in Multi-Agent Systems** (Claude Certified Architect – Foundations).
Build spec: `curriculum/05-Context-Management-Reliability/03-revised-Error-Propagation-in-Multi-Agent-Systems.md`.

## The idea in 30 seconds

```
              ┌──────────────────────── researcher subagent ────────────────────────┐
coordinator   │ search_sources: try/except ─► up to 3 local retries (wait 1, 2, 4 s) │──► ONE report: status, shouldRetry,
 ──Agent──►   │ ─► keep every source that arrived ─► build_report()                  │    results, error {failureType,
              └──────────────────────────────────────────────────────────────────────┘    attemptedAction, partialResults,
                                                                                             alternativeApproaches}
coordinator recovers by failureType ◄────────────────────────────────────────────────────────┘
   transient   3+ partial sources: proceed (limited)   fewer: re-delegate with the narrower query
   validation  re-delegate with the parameters fixed
   business    escalate_to_human                       permission  alert_admin
   ─► the brief: findings + a SEPARATE coverage section (well_supported / limited / unavailable, each with its reason)
```

* **Fix locally what can be fixed:** timeouts are retried inside the subagent's tool. Only failures that persist
  after the retries leave the subagent, and they leave as one complete report.
* **An empty result is an answer:** "the query ran and found nothing" (`success`, `shouldRetry: false`) is not
  "the query didn't run" (`transient`, `shouldRetry: true`). Conflating them hides failures or wastes retries.
* **Write the outcome into the report:** a tool's `is_error` reaches only the subagent; the coordinator gets only
  the subagent's final message.
* **Different failures, different recoveries:** never suppress a failure, never kill the whole brief over one, and
  name every gap in the coverage section.

## Files

| File | What it is | Calls the API? |
|---|---|---|
| `propagation_setup.py` | the source library with planted failures, `search_once()`, `search_with_retry()`, `build_report()`, `REPORT_SCHEMA`, `validate_report()`, `parse_json_object()`; POC 2's two tool servers, `RECOVERY_POLICY`, `COORDINATOR_PROMPT`, the `researcher` subagent, `BRIEF_SCHEMA` and `build_propagation_options()` | – |
| `coordinator.py` | `run_coordinator()`, copied from `01-Agentic-Architecture-Orchestration/03-Subagent-Invocation-and-Context-Passing/` | – |
| `poc1_subagent_errors.py` | **POC 1**: the search layer on 8 topics: attempts, waits and reports, the suppressing anti-pattern, the backoff and the local-retry counts | No (about 17 s of real waits) |
| `poc2_coordinator.py` | **POC 2**: one coordinator run over 7 topics: recovery per failure type, coverage annotations, and the suppress and terminate anti-patterns | Yes, 1 run (1 coordinator call, about 9 subagents) |
| `common.py` | reads `.env`, sets up logging, logs the model's input and output tagged with its agent | – |

## Setup (once)

```bash
cd "05-Context-Management-Reliability/03-revised-Error-Propagation-in-Multi-Agent-Systems"
python3 -m venv .venv && source .venv/bin/activate   # Python 3.10+
pip install -r requirements.txt                      # the SDK bundles Claude Code: nothing else to install
cp .env.example .env                                 # then put your API key in .env (POC 2 only)
```

If `python3 -m venv` says *ensurepip is not available* (Debian/Ubuntu), install the venv package for your
Python version first, e.g. `sudo apt install python3.14-venv`. You can also copy the `.env` from an earlier POC folder.

## Run (in this order)

```bash
python poc1_subagent_errors.py   # free, about 17 s: 16 attempts, 13 failed, 8 local retries, 5 failure reports
python poc2_coordinator.py       # 1 run: 7 researchers at once, 2 re-delegations, 1 escalation, 1 alert, the brief
```

What one run can't show: the failures are planted, so every branch runs every time; real failures come and go.
The recovery choices are model decisions: one run shows the typical result, all 7 topics `correct`. A `WRONG` line
points at the coordinator's prompt, not at the reports: POC 1 has already shown that every report says exactly
what happened.

## Reading the log

POC 1 prints its results (no log file). POC 2's log shows only what goes **into** each model and what comes **out**
of it, tagged `[coordinator]` or `[researcher]`, plus the lines that hold the lesson. Each run is also saved to
`logs/poc2_coordinator_<date>_<time>.log`, so you can re-read it without paying again.

Example from POC 2 (illustrative: your ids, timings and wording will differ):

```
13:02:11  MODEL OUTPUT  tool_use     [coordinator] Agent {'subagent_type': 'researcher', 'description': 'Research tidal', 'prompt': 'topic: tidal\nquery: tidal 2026\nparameters: {}'}  (id=toolu_C4)
13:02:12  MODEL OUTPUT  tool_use     [researcher] mcp__sources__search_sources {'topic': 'tidal', 'query': 'tidal 2026'}  (id=toolu_D4)
13:02:19  MODEL INPUT   tool_result  [researcher] [{'type': 'text', 'text': '{"topic": "tidal", "status": "partial_failure", "shouldRetry": true, ...}'}]  (tool_use_id=toolu_D4, is_error=True)
13:02:21  MODEL OUTPUT  text         [researcher] {"topic": "tidal", "status": "partial_failure", "shouldRetry": true, ...}
13:02:21  MODEL INPUT   tool_result  [coordinator] [{'type': 'text', 'text': '{"topic": "tidal", "status": "partial_failure", ...}'}, {'type': 'text', 'text': 'agentId: ...'}]  (tool_use_id=toolu_C4, is_error=None)
...
13:03:40  Hop check: 9 reports received, 9 valid, 9 identical to the tool's report; first round 7 Agent calls in 1 response(s), 7 with '<topic> 2026' and {}; searches by the coordinator itself: 0
13:03:40  tidal      first report partial_failure/transient, 1 partial; actions ['redelegate']; expected redelegate -> correct; retry with query 'tidal stream 2026', parameters {}, took 6.4 s
13:03:40  biomass    first report error/business, 0 partial; actions ['escalate']; expected escalate -> correct
13:03:40  Policy suppress         findings ['solar', 'wind']; annotated unavailable []; missing ['geothermal', 'tidal', 'hydropower', 'biomass', 'fusion']
```

* The researcher's `tool_result` has `is_error=True`, but the coordinator's has `is_error=None`: the failure reached
  the coordinator only because it is written into the report the researcher relayed.
* Wind's report is a plain `success` with 3 sources: its 2 failed attempts never left the subagent (see POC 1).
* The brief ends with a `## Coverage` section; biomass and fusion appear only there, with their causes.

## Concept map (IDs from the build spec)

| ID | Concept | Where you see it |
|---|---|---|
| C1 | A structured error schema: failureType, attemptedAction, partialResults, alternativeApproaches, each described | `REPORT_SCHEMA` and `ERROR_SCHEMA` in `propagation_setup.py`; POC 1 prints the geothermal report in full |
| C2 | Structured error context enables intelligent recovery | POC 2: `Hop check: ... 9 identical to the tool's report`; tidal's retry uses the narrower query and hydropower's the region the reports named |
| C3 | Generic error messages prevent informed recovery (already covered) | taught in `02-revised-Structured-Error-Responses.md` (no POC folder yet); here `validate_report()` rejects a bare message and `search_once()` lets no exception escape |
| C4 | The four failure types map to different recoveries (already covered) | taught in `02-revised-Structured-Error-Responses.md` (no POC folder yet); here `RECOVERY_POLICY` in `propagation_setup.py` |
| C5 | A status field separates complete failure from partial success | `build_report()`; POC 1 report lines: `success`, `partial_failure` (geothermal, tidal), `error` (hydropower, biomass, fusion) |
| C6 | The subagent tells access failures from valid empty results | POC 1: ocean thermal (`success`, 0 results, `shouldRetry False`) against geothermal (`partial_failure`, transient) |
| C7 | Conflating the two is a critical error | `suppressing_search()` in `poc1_subagent_errors.py`: its geothermal report equals ocean thermal's, and GEO-1 and GEO-2 are lost |
| C8 | try/except separates infrastructure errors from empty results | `search_once()` in `propagation_setup.py`; POC 1: wind attempt 1 `TimeoutError`, attempt 2 `ConnectionError` |
| C9 | A `shouldRetry` flag on every report | `build_report()` and `validate_report()`; POC 1: only geothermal and tidal have `shouldRetry True` |
| C10 | Local retries: 3 with exponential backoff before propagating | `search_with_retry()`; POC 1: attempts 1, 3, 4, 4, 1, 1, 1, 1 per topic |
| C11 | Only failures that persist after local retry propagate | POC 1 last line: 13 failed attempts and 8 local retries stay inside; 5 failure reports leave |
| C12 | Exponential backoff: the delay doubles | `BASE_DELAY * 2 ** (attempt - 1)` in `search_with_retry()`; POC 1: `[1, 2, 4] = 7 s` against a fixed `[1, 1, 1] = 3 s` |
| C13 | Partial results kept and accumulated across retries | `retrieved` in `search_with_retry()`; POC 1: geothermal attempts bring GEO-1, GEO-2, then GEO-3: `partialResults` holds all 3 |
| C14 | The coordinator decides: retry modified, alternative, or proceed with partial results | `RECOVERY_POLICY` in `COORDINATOR_PROMPT`; `decisions()` in `poc2_coordinator.py`; one log line per topic |
| C15 | Avoid both silent suppression and workflow termination | `suppress()` and `terminate()` in `poc2_coordinator.py`; the three `Policy ...` log lines |
| C16 | Each failure type handled differently, none suppressed | POC 2 topic lines: tidal re-delegated narrower, hydropower re-delegated with a region, biomass escalated, fusion alerted |
| C17 | Partial results: proceed, or retry for the extra latency | `SUFFICIENT_SOURCES = 3`; geothermal (3 partial) `proceed`; tidal (1 partial) `redelegate` with `took ... s` |
| C18 | Coverage annotations name every gap | `BRIEF_SCHEMA`'s `coverage`; `check_coverage()`; log line `Coverage check: ...` |
| C19 | Without annotations a gap looks irrelevant, not unavailable | last log line: the topics that would look complete or vanish without the section; their reasons in `## Coverage` |
| C20 | The coverage section is separate from the findings | `sections` and `coverage` are separate keys of `BRIEF_SCHEMA`; `render_brief()` ends with `## Coverage` |
| E1 | The first round sends fixed inputs | `COORDINATOR_PROMPT` ("First, delegate every topic at once ... '<topic> 2026' and parameters {}"); `Hop check: ... 7 with '<topic> 2026' and {}` |

## Settings (`.env`)

* `MODEL_ID`: the model that runs the coordinator; the researcher subagents inherit it (default `claude-sonnet-5-5`).
* `MAX_BUDGET_USD`: the SDK stops a coordinator call, its subagents included, whose estimated spend passes this (default `1.00`).
