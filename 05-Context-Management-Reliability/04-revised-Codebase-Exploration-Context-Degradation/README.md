# Codebase Exploration and Context Degradation: beginner POCs (Claude Agent SDK, Python)

Hands-on POCs for **Context Management & Reliability → Codebase Exploration and Context Degradation** (Claude Certified Architect – Foundations).
Build spec: `curriculum/05-Context-Management-Reliability/04-revised-Codebase-Exploration-Context-Degradation.md`.

## The idea in 30 seconds

```
POC 1, between agents:
   coordinator (can't read files) ──Agent x3──► test-finder · dependency-tracer · integration-scout (Read, Grep, Glob)
          ▲                                          │ each reads thousands of characters of code
          └──────────── 3 short JSON reports ◄───────┘ only a subagent's FINAL message crosses back
   Phase 1 summary ──► Python injects it at the top of each Phase 2 prompt ("warm"), or not ("cold")

POC 2, across time (one explorer, one fresh query() per module, Python owns the history):
   orders ► payments ► inventory ► shipping ► [history replaced by a lossy summary] ► notifications ► customers ► "list all 18"
   scratchpad.md   note() after each discovery, read_notes() at each step       survives the summary
   manifest.json   checkpoint() after each module                                survives a crash: resume at module 4
```

* **Delegate for context, not speed:** a subagent's file reads stay in the subagent. The coordinator's context grows
  by 3 short reports, while a single agent carries every file it read into each later request.
* **Hand a phase over as a document:** a short structured summary, injected into every Phase 2 prompt, saves Phase 2
  from rediscovering the structure (the cold-start problem).
* **Write it down:** what must outlive the context goes to a file the agent manages itself: a scratchpad survives a
  lossy history, and a manifest checkpointed after every step survives a crash.

## Files

| File | What it is | Calls the API? |
|---|---|---|
| `explore_repo/` | the mock Lumen Home TypeScript service: 23 files (18 classes, `base.ts`, 4 tests), never compiled or run | – |
| `explore_setup.py` | the ground truth computed from the repo, `chars_read()`, POC 1's 3 explorers, `COORDINATOR_PROMPT`, `PHASE1_SCHEMA`, `coordinator_scope` and options; POC 2's `MODULE_PLAN`, prompts, `LOSSY_HISTORY`, the `notes` and `progress` tools, `explore_module()` and `run_agent()` | – |
| `coordinator.py` | `run_coordinator()`, copied from `03-revised-Error-Propagation-in-Multi-Agent-Systems/`, plus `prompt_tokens` and `last_prompt_tokens` | – |
| `poc1_delegation.py` | **POC 1**: Phase 1 with 3 subagents, the single-agent baseline, Phase 2 warm and cold | Yes, 3 runs (6 calls) |
| `poc2_scratchpad.py` | **POC 2a**: 6 modules, the lossy summary after module 4, the final listing; without and with a scratchpad | Yes, 2 runs (7 calls each) |
| `poc2_crash_resume.py` | **POC 2b**: scratchpad + checkpoints, a simulated crash after module 3, resume from the manifest | Yes, 1 run (6 calls) |
| `common.py` | reads `.env`, sets up logging, logs the model's input and output (tagged with the agent in POC 1) | – |

POC 2 writes its files to `work/<run>/` (`scratchpad.md`, `manifest.json`), emptied at the start of each run and
ignored by git.

## Setup (once)

```bash
cd "05-Context-Management-Reliability/04-revised-Codebase-Exploration-Context-Degradation"
python3 -m venv .venv && source .venv/bin/activate   # Python 3.10+
pip install -r requirements.txt                      # the SDK bundles Claude Code: nothing else to install
cp .env.example .env                                 # then put your API key in .env
```

If `python3 -m venv` says *ensurepip is not available* (Debian/Ubuntu), install the venv package for your
Python version first, e.g. `sudo apt install python3.14-venv`. You can also copy the `.env` from an earlier POC folder.

## Run (in this order)

```bash
python poc1_delegation.py     # 3 runs: Phase 1 (coordinator + 3 subagents), the single-agent baseline, Phase 2 warm/cold
python poc2_scratchpad.py     # 2 runs: no-scratchpad, then scratchpad (7 calls each)
python poc2_crash_resume.py   # 1 run: 3 modules, a simulated crash, 3 resumed modules
```

What one run can't show:
* **Context degradation itself:** a strong model doesn't lose 6 small modules from one context, so POC 2 makes the
  loss certain: after module 4, Python replaces the history with `LOSSY_HISTORY`, the generic end state of a long
  session. What the run shows is which store survives it.
* **Real scale:** the mock files are 25-52 lines each (about 25,000 characters in all). Real services have
  hundreds of longer files, so the gap between the coordinator's context and a single agent's grows far larger.
* The subagents' and explorers' choices vary from run to run; one run shows the typical result.

## Reading the log

The log shows only what goes **into** each model and what comes **out** of it, plus the lines that hold the lesson.
In POC 1 every line is tagged with its agent; the baseline and Phase 2 runs are single agents, tagged
`[coordinator]` because they run through `run_coordinator()` too. Each run is also saved to
`logs/<script>_<date>_<time>.log`, so you can re-read it without paying again.

Example (illustrative: your ids, timings, wording and numbers will differ):

```
13:10:02  MODEL OUTPUT  tool_use     [coordinator] Agent {'subagent_type': 'integration-scout', 'description': 'Find integrations', 'prompt': 'task: integrations\n...'}  (id=toolu_E3)
13:10:05  MODEL OUTPUT  tool_use     [integration-scout] Grep {'pattern': 'fetch\\(', 'path': '...'}  (id=toolu_F1)
...
13:11:40  Report of integration-scout: 812 chars, against 9716 chars of files its subagent read (8%); valid
13:13:05  Context of the coordinator: 3412 -> 4120 input tokens (+708) over the run; files read in the run: 17673 chars
13:13:05  Context of the single agent: 2954 -> 10377 input tokens (+7423) over the run; files read in the run: 25492 chars
13:14:10  Phase 2 payment_errors, cold: 6 tool calls, 2 discovery calls (Glob, Grep), 3 files read (4123 chars); the answer names ['RefundDesk', 'src/services/refund.ts']: True
...
13:22:31  After step 4 the history holds 0 of the 12 module 1-4 class names; scratchpad.md holds 12
13:24:02  Run no-scratchpad: classes listed with their exact path {'phase 1: core modules': '1/12', 'phase 2: edge modules': '6/6'}; generic phrases ['typical']; Read calls in the final step: 0
```

* The subagents' `Read` results appear in the stream (tagged with the subagent), but the coordinator model never
  sees them: compare the two `Context of ...` lines.
* In the warm Phase 2 runs, the prompt starts with `=== PHASE 1 SUMMARY ===`; the cold runs start with `Glob`/`Grep`.
* In POC 2, compare the two final answers: exact `ClassName — path` lines against "the typical layered pattern".

## Concept map (IDs from the build spec)

| ID | Concept | Where you see it |
|---|---|---|
| C1 | A coordinator delegates 3-4 narrow exploration tasks to subagents | `AGENTS`, `PHASE1_TASKS` and `COORDINATOR_PROMPT` in `explore_setup.py`; Phase 1 log: 3 `Agent` calls in one response |
| C2 | Delegation is about context isolation, not parallelism | the two `Context of the coordinator / single agent` lines in POC 1 (`prompt_tokens` -> `last_prompt_tokens`) |
| C3 | Subagents return structured summaries, not file contents | `REPORT_FORMAT`; `check_report()` in `poc1_delegation.py`; the `Report of ...: N chars, against M chars ... read` lines |
| C4 | Scratchpad file management: write after each step, read before the next | `SCRATCHPAD_RULE` and `build_notes_server()` in `explore_setup.py`; POC 2a log: `read_notes` first, then `note` calls |
| C5 | Scratchpads keep knowledge outside the context, out of reach of the attention shift | POC 2a line `After step 4 the history holds 0 of the 12 ... scratchpad.md holds 12` |
| C6 | A Markdown file with sections for key classes, dependency chains and critical findings | `SECTIONS` and the `note` tool's enum; POC 2a prints `scratchpad.md` with its count of exact entries |
| C7 | A deliberate strategy from the start, not a fallback | `SCRATCHPAD_RULE` in every step's system prompt; the `Step n (...): scratchpad.md holds k entries` lines from step 1 |
| C8 | Summary injection into every Phase 2 prompt | `summary_block()` and `phase2_prompt()` in `poc1_delegation.py`; warm prompts start with `=== PHASE 1 SUMMARY ===` |
| C9 | Injection prevents the cold-start problem | the 4 `Phase 2 <task>, warm/cold` lines: discovery calls and files read, warm against cold |
| C10 | The Phase 1 summary: architecture, chains, concerns, one objective per Phase 2 task | `PHASE1_SCHEMA`; `check_summary()`; the line `Phase 1 summary: ...; blocks for Phase 2: ...` |
| C11 | Crash recovery through a JSON manifest the coordinator injects on resume | `CHECKPOINT_RULE`, `build_progress_server()`, `resume()` in `poc2_crash_resume.py`; `Manifest at the crash: keys [...]` |
| C12 | Without recovery, a crash loses all progress | `SimulatedCrash` warning; last line `Module steps run: 6, against 9 for a restart without a manifest` |
| C13 | Checkpoint after every significant step | `CHECKPOINT_RULE`; the line `Checkpoints before the crash: 3, so 0 steps lost. With one checkpoint per phase ... 3 steps` |
| C14 | `nextSteps` tells the resumed session exactly what to do | manifest `nextSteps` at the crash; `Resumed with ['shipping']; Read calls on files explored before the crash: 0` |
| C15 | Test degradation over 5+ modules, with and without scratchpads, ending in a full listing | `RUNS` in `poc2_scratchpad.py`; `score_listing()`; the two `Run ...: classes listed with their exact path` lines |
| C16 | The symptom: typical patterns instead of specific classes and paths | `generic_phrases()`; the no-scratchpad run's final answer and its `generic phrases [...]` |
| C17 | Expected: without scratchpads, misses after 4-5 modules; with them, specifics for the whole session | the two `Run ...` lines: typically 18/18 with the scratchpad, a few of 12 on modules 1-4 without it |
| E1 | The coordinator can't read files | `coordinator_scope` hook in `explore_setup.py`; `File-tool calls by the coordinator itself: 0` |
| E2 | Python owns the history: each step is a fresh `query()` | `explore_module()` and `build_step_prompt()`: no `resume`, `continue_conversation` or `ClaudeSDKClient` |
| E3 | The summarised history is fixed text with no class name or path | `LOSSY_HISTORY` in `explore_setup.py` |
| E4 | The final question can't open source files | `tools=[]` when `final=True` in `build_explorer_options()`; `Read calls in the final step: 0` |

## Settings (`.env`)

* `MODEL_ID`: the model for every agent; the explorer subagents inherit it (default `claude-sonnet-5-5`).
* `MAX_BUDGET_USD`: the SDK stops a single `query()` call, its subagents included, whose estimated spend passes this (default `1.00`).
