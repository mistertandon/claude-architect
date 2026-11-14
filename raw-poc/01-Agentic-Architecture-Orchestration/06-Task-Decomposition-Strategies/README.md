# Task Decomposition Strategies: beginner POCs (Claude Agent SDK, Python)

Hands-on POCs for **Agentic Architecture & Orchestration → Task Decomposition Strategies** (Claude Certified Architect – Foundations).
Build spec: `curriculum/01-Agentic-Architecture-&-Orchestration/06-revised-Task-Decomposition-Strategies.md`.

## The idea in 30 seconds

```
POC 1, single pass:   [ checkout.ts + inventory.ts + pricing.ts ] ──► 1 call ──► every review at once

POC 2, multi-pass:    checkout.ts  ──► call 1 ──► review + interface ─┐
                      inventory.ts ──► call 2 ──► review + interface ─┼─► call 4: the interfaces only (no code)
                      pricing.ts   ──► call 3 ──► review + interface ─┘           ──► cross-file issues
```

* **Attention dilution:** in one huge request, early files get detailed reviews and late files shallow ones, and
  identical code can get different verdicts. The exam's example is 14 files; it shows from about 10 files up.
* **The fix is structural:** one fresh session per file (each file gets the whole attention budget), then one
  integration pass over the files' interfaces for what no single file can show.
* **Same model, same prompt, same schema** in both POCs, so any difference comes from the structure.
* **Python decides the split** (a fixed pipeline), so the decomposition is the same on every run.

**This repo is small on purpose:** 3 files of 26–40 lines, so the POCs stay cheap and easy to read. At this size
the single pass will usually do well: the POCs show the two architectures and the cross-file layer, not the
dilution itself. To see dilution, the repo would need about 10+ files of real size.

## Files

| File | What it is | Calls the API? |
|---|---|---|
| `sample_repo/` | the mock order service: `checkout.ts`, `inventory.ts`, `pricing.ts`, with planted defects | – |
| `review_setup.py` | `load_repo()`, `format_file()`, `REVIEWER_PROMPT`, the schemas, `build_review_options()`, `run_review()`, and the answer key with `score_review()` | – |
| `poc1_single_pass.py` | **POC 1**: all files reviewed in one request | Yes, 1 run (1 call) |
| `poc2_multi_pass.py` | **POC 2**: one pass per file, then one integration pass | Yes, 1 run (4 calls) |
| `common.py` | reads `.env` | – |

The planted defects (the answer key in `review_setup.py`):

| Kind | Where | What |
|---|---|---|
| local bug | `checkout.ts` | `if (order.status = "paid")`: assignment instead of comparison |
| local bug | `inventory.ts` | `units * unitFee === invoiced`: exact equality between computed decimals |
| local bug | `pricing.ts` | `i <= tiers.length`: off by one |
| cross-file | `pricing.ts` + `checkout.ts` | `orderTotal()` returns integer cents; `checkout()` formats it as dollars |
| cross-file | `inventory.ts` + `checkout.ts` | `reserveStock()` returns `false` when stock is short; `checkout()` waits for a throw |
| same code twice | `pricing.ts` + `inventory.ts` | `forEach` with a nested `find` (O(n × m)): both copies should get the same verdict |

## Setup (once)

```bash
cd "01-Agentic-Architecture-&-Orchestration/06-Task-Decomposition-Strategies"
python3 -m venv .venv && source .venv/bin/activate   # Python 3.10+
pip install -r requirements.txt                      # the SDK bundles Claude Code: nothing else to install
cp .env.example .env                                 # then put your API key in .env
```

If `python3 -m venv` says *ensurepip is not available* (Debian/Ubuntu), install the venv package for your
Python version first, e.g. `sudo apt install python3.14-venv`. You can also copy the `.env` from an earlier POC folder.

## Run (in this order)

```bash
python poc1_single_pass.py   # 1 run: the 3 files in one request
python poc2_multi_pass.py    # 1 run: 3 per-file passes, then the integration pass
```

Optional extras, commented out in `poc1_single_pass.py`: two more single-pass trials (results vary from run to run).

## What to compare

* `score_review()` returns the same scores for both POCs: issues per file in order (#1 to #3), whether the pattern
  verdicts are consistent, and the cross-file issues found. At the exam's scale, the single pass's late files and
  pattern verdicts are where it breaks.
* The integration pass never saw code: it found the mismatches from the interfaces the per-file passes recorded
  (`exports`, `uses`). If one is missing, read those two summaries first: the integration pass knows only what they say.
* A per-file pass sees one file, so on its own it can never report a two-file issue: the integration pass is the
  layer that catches data flow and API mismatches.

## Concept map (IDs from the build spec)

| ID | Concept | Where you see it |
|---|---|---|
| C1 | A review agent that reads every TS/JS file of a folder | `load_repo()` in `review_setup.py` (sorted by name: the review order) |
| C2 | Attention dilution shows from about 10 files (the exam's 14-file example) | the note under "The idea in 30 seconds": this repo is 3 files on purpose |
| C3 | The single-pass review: the baseline | `poc1_single_pass.py`: one `run_review()` call with every file |
| C4 | The symptoms: thorough early files, shallow or missing late files | POC 1 lines `#n file: k issue(s), planted bug flagged: ...`, read from #1 to #3 |
| C5 | Per-file passes give each file the full attention budget | layer 1 of `multi_pass()` in `poc2_multi_pass.py`: a new session per file |
| C6 | Structured per-file feedback: bug count, severities, line references | `FILE_REVIEW` in `review_setup.py`, shared by both POCs; returned as `ResultMessage.structured_output` |
| C7 | Decomposition, not a better prompt or a bigger context window, is the fix | `REVIEWER_PROMPT` already demands equal depth; the single pass's whole repo fits easily in one request |
| C8 | A cross-file integration pass over the per-file summaries | layer 2 of `multi_pass()`: `INTEGRATION_PROMPT` plus each file's `exports` and `uses`, no code |
| C9 | Per-file passes alone miss cross-cutting issues | `FILE_PROMPT` shows one file per call; in POC 2 the cross-file issues come only from the integration pass |
| C10 | Compare the two architectures, especially depth across files | the same `score_review()` call at the end of both POCs |
| C11 | The same model does better with a better structure | `build_review_options()`: `MODEL_ID`, `REVIEWER_PROMPT` and `FILE_REVIEW` are shared by both POCs |
| C12 | Contradictory verdicts on identical code (the single pass's symptom) | POC 1: `score_review()["consistent"]` for the forEach + nested find in both files |
| C13 | The multi-pass review treats the same pattern consistently | the same `consistent` score in POC 2 |
| E1 | Both architectures see the same numbered listing | `format_file()`: the only way code enters a prompt |
| E2 | Planted ground truth, so depth and consistency can be measured | `PLANTED`, `CROSS_FILE`, `PATTERN_FILES` and `score_review()` in `review_setup.py`; the table above |

## Settings (`.env`)

* `MODEL_ID`: the model for every review pass in both POCs (default `claude-sonnet-5-5`).
* `MAX_BUDGET_USD`: the SDK stops any single review call whose estimated spend passes this (default `0.50`).
* `MAX_TURNS`: the safety cap on turns per review call (default `10`).
