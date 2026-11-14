# Multi-Instance and Multi-Pass Review: beginner POC (Claude Agent SDK, Python)

Hands-on POC for **Prompt Engineering & Structured Output → Multi-Instance and Multi-Pass Review** (Claude Certified Architect – Foundations).
Build spec: `curriculum/04-Prompt-Engineering-Structured-Output/06-revised-Multi-Instance-and-Multi-Pass-Review.md`.

The single pass, the per-file passes and the integration pass (raw steps 1–3) are already built in
`01-Agentic-Architecture-Orchestration/06-Task-Decomposition-Strategies/`. This POC reuses that review and adds
what is new: **how far to trust each finding**.

## The idea in 30 seconds

```
review   checkout.ts ─► new session ─► findings + confidence 0.0-1.0 + reason ─┐
         inventory.ts ─► new session ─► ...                                      ├─► integration pass (also checks
         pricing.ts  ─► new session ─► ...                                       ┘   contradictions between findings)
route    confidence >= 0.8 ─► direct_report        below ─► human_review queue (least certain first)

verify   self-review:  resume=<the reviewer's session>  ─► sees its own "I chose this because"
         independent:  a NEW session, code + findings only ─► no scores, no reasons
         ──► calibration dataset ──► the routing threshold moves
```

* **A self-reported confidence is a claim, not a probability:** compare it with a labelled set (the answer key)
  before you trust a threshold.
* **Routing spends scarce human attention** on the uncertain findings; the clear-cut ones go straight through.
* **In the SDK, an "instance" is a session:** a new `query()` starts with an empty history; `resume=` continues one.
  That single option is the difference between an independent check and a self-review.
* **Independent verdicts calibrate the threshold:** high-confidence findings the second instance overturns are the
  calibration gap.

## Files

| File | What it is | Calls the API? |
|---|---|---|
| `sample_repo/` | 06's mock order service: `checkout.ts`, `inventory.ts`, `pricing.ts`, with planted defects | – |
| `confidence_setup.py` | 06's loader, listing, reviewer prompt and answer key; `CONFIDENCE_RULE`, the schemas, `build_review_options()` (with `resume`), `run_review()` (now also returns `session_id`) and `label()` | – |
| `poc1_confidence_routing.py` | **POC 1**: the scored review, routing, the labelled calibration, self vs independent verification, the new threshold | Yes, 2 runs (4 review calls, then 6 verify calls) |
| `common.py` | reads `.env` | – |

**This repo is small on purpose** (3 files): the POC shows the mechanism, not attention dilution. With 3 files and 2
cross-file defects, expect a handful of findings, and possibly no overturned one: at the spec's scale (06's 14-file
repo), more findings, and more wrong ones at high confidence, make the calibration gap easier to see.

## Setup (once)

```bash
cd "04-Prompt-Engineering-Structured-Output/06-Multi-Instance-and-Multi-Pass-Review"
python3 -m venv .venv && source .venv/bin/activate   # Python 3.10+
pip install -r requirements.txt                      # the SDK bundles Claude Code: nothing else to install
cp .env.example .env                                 # then put your API key in .env
```

If `python3 -m venv` says *ensurepip is not available* (Debian/Ubuntu), install the venv package for your
Python version first, e.g. `sudo apt install python3.14-venv`. You can also copy the `.env` from an earlier POC folder.

## Run

```bash
python poc1_confidence_routing.py   # 2 runs: review (3 files + integration), verify (independent + self per file)
```

## What to compare

* A self-review's prompt is short (`SELF_CHECK_PROMPT`): the rest of what it knows is already in the resumed session.
  An independent verifier's prompt holds the code and the findings, and no confidence or reason.
* A high-confidence finding that the answer key marks incorrect is the "raw, uncalibrated confidence" problem.
* `comparison["self"]` vs `comparison["independent"]` compares the two verifiers on the same findings: the
  self-review tends to confirm its own work, the fresh session doesn't share its reasoning.
* `ROUTE_THRESHOLD` → `new` is the calibration: the lowest threshold whose findings the independent instance
  confirmed at least 90% of the time.

## Concept map (IDs from the build spec)

| ID | Concept | Where you see it |
|---|---|---|
| C1 | Single-pass review of a 10+ file PR, recording the symptoms (already covered) | `01-Agentic-Architecture-Orchestration/06-Task-Decomposition-Strategies/` (`poc1_single_pass.py`) |
| C2 | The three symptoms of attention dilution (already covered) | 06's `poc1_single_pass.py` scores (`score_review()`); C6 here re-checks contradictions across per-file findings |
| C3 | Detailed first and last files, a missed middle bug, a contradiction (already covered) | 06's per-file scores (`score_review()["per_file"]`) |
| C4 | Per-file local analysis (already covered) | 06's `poc2_multi_pass.py`; here the `review` run: one new session per file |
| C5 | Per-file passes give every file consistent attention (already covered) | 06's `poc2_multi_pass.py`; here `findings` holds `<file>#n` ids for every file |
| C6 | The integration pass reads all per-file findings and checks contradictions too | `INTEGRATION_PROMPT` and the `summaries` list (each file's interface plus its findings); `contradictions` in `main()` |
| C7 | Per-file analysis misses cross-file concerns; integration is a separate call (already covered) | 06's `poc2_multi_pass.py`; here the separate integration `run_review()` and its `X#n` findings |
| C8 | The integration output names cross-file issues (already covered) | 06's `score_review()["cross_file_found"]`; here the `X#1`, `X#2` findings |
| C9 | A 0.0–1.0 confidence on each finding, with the reason | `CONFIDENCE_RULE` and `CONFIDENT_ISSUE` in `confidence_setup.py`; `in_range` (range checked in Python) |
| C10 | Routing: high confidence → `direct_report`, low → `human_review` | `route()` and `ROUTE_THRESHOLD`; each finding's `route(item)` |
| C11 | Routing spends limited human attention where it is needed | `queue` in `main()`: the human_review findings, least certain first |
| C12 | Raw confidence vs a threshold validated against a labelled set | `label()` and `ANSWER_KEY`; `raw_calibration` and `direct_precision` |
| C13 | A separate instance (fresh session, no prior context) re-judges a subset | the independent `run_review()` in the `verify` run: no `resume`, `VERIFIER_PROMPT`, findings without scores |
| C14 | An independent instance avoids the "I chose this because" bias of self-review | the self-review with `resume=sessions[name]`; `comparison["self"]` vs `comparison["independent"]` |
| C15 | Calibrate the threshold by comparing self-reported confidence with independent verdicts | `adjust_threshold()` and `TARGET_PRECISION`; `new` in `main()` |
| C16 | The calibration dataset; overturned high-confidence findings move the threshold | `rows`, `verified_calibration` and `overturned` in `main()` |

## Settings (`.env`)

* `MODEL_ID`: the model for every review pass and both verifiers (default `claude-sonnet-5-5`).
* `MAX_BUDGET_USD`: the SDK stops any single call whose estimated spend passes this (default `0.50`).
* `MAX_TURNS`: the safety cap on turns per call (default `10`).
