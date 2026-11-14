# System Prompts with Explicit Criteria: beginner POCs (Claude Agent SDK, Python)

Hands-on POCs for **Prompt Engineering & Structured Output → System Prompts with Explicit Criteria** (Claude Certified Architect – Foundations).
Build spec: `curriculum/04-Prompt-Engineering-Structured-Output/01-revised-System-Prompts-with-Explicit-Criteria.md`.

## The idea in 30 seconds

```
same 5 snippets, same model, same schema ──► system prompt A, B or C ──► findings ──► scored against the answer key
                                                                                       (9 real defects, 7 decoys)
  A vague      "Be conservative and only flag important issues."        no decision boundary
  B criteria   REPORT bug / security / contradicting comment; SKIP style and local patterns; severities in prose
  C examples   B, with severities defined by code examples instead of prose
```

* **Vague words give Claude no boundary:** "important" doesn't say which category or severity counts, so a reviewer
  flags some decoys, skips some real defects, and can answer differently on the next run.
* **Explicit categories are the fix the exam tests:** say what to report and what to skip, by name.
* **Code examples beat prose for severity:** "issues that could cause system failures" must be interpreted; a code
  pattern doesn't.
* **Trust recovery (POC 2):** one noisy category makes developers distrust every category, so switch that category
  off until its rule is fixed, then measure before you switch it back on.

## Files

| File | What it is | Calls the API? |
|---|---|---|
| `snippets/` | 5 TypeScript files of the Fernway Outfitters order service, with planted defects and decoys | – |
| `criteria_setup.py` | the answer key (`PLANTED`), `REVIEW_SCHEMA`, the 3 system prompts, `build_review_options()`, `review()` and the scorer | – |
| `poc1_vague_vs_explicit.py` | **POC 1**: the 3 prompts on the same snippets | Yes, 3 runs (1 call each) |
| `poc2_trust_recovery.py` | **POC 2**: per-category false-positive rates, the 25% switch, the re-enablement check | Yes, 2 runs (1 call each) |
| `common.py` | reads `.env` | – |

The answer key (`PLANTED` in `criteria_setup.py`):

| Spot | File | What | Must a precise reviewer report it? |
|---|---|---|---|
| R1, R2 | `payments.ts` | SQL built from input; the card number logged | yes, critical |
| R3 | `checkout.ts` | `if (order.status = "paid")`: every order ships | yes, critical |
| R4, R5, R6 | `checkout.ts`, `inventory.ts` | unchecked `find()`; a missing `await`; `i <= bins.length` | yes, major |
| R7, R8, R9 | `discounts.ts`, `shipping.ts` | zero-based month; a comment says "copy" but `sort()` mutates; "$50 or more" but `> 50` | yes, minor |
| D1, D3, D7 | | `var`, a nested ternary, a snake_case name | no: style |
| D2, D5 | | `void auditLog.write(...)`, `== null` | no: local patterns used on purpose |
| D4, D6 | | a TODO, a dated note | no: comments that contradict nothing |

## Setup (once)

```bash
cd "04-Prompt-Engineering-Structured-Output/01-System-Prompts-with-Explicit-Criteria"
python3 -m venv .venv && source .venv/bin/activate   # Python 3.10+
pip install -r requirements.txt                      # the SDK bundles Claude Code: nothing else to install
cp .env.example .env                                 # then put your API key in .env
```

If `python3 -m venv` says *ensurepip is not available* (Debian/Ubuntu), install the venv package for your
Python version first, e.g. `sudo apt install python3.14-venv`. You can also copy the `.env` from an earlier POC folder.

## Run (in this order)

```bash
python poc1_vague_vs_explicit.py   # 3 runs: vague, criteria, examples (each reviews all 5 snippets)
python poc2_trust_recovery.py      # 2 runs: the production prompt, then the refined comment rule
```

Optional extras are commented out at the top of each script: a second run of each prompt in POC 1, and a second
production run in POC 2. **One run can't show run-to-run drift** (C6, and "stable across runs" in C14): the SDK has
no temperature or seed, so variation only shows when you run the same prompt again. Uncomment the repeats to get the
`stable` column; the spec's numbers (vague 30–50% inconsistency, explicit below 15%) assume 2 runs per prompt.

## What to compare

* A verdict is wrong in three ways: `missed`, `flagged` (a decoy reported), or a real defect reported with the wrong
  severity. The vague prompt typically goes wrong both ways at once.
* In POC 2, `disabled` lists the noisy categories; `before` vs `after` is the false-positive count the developer
  sees, and `collateral` names the real defect the switch hides.
* `re_enable` in POC 2 is the plan's check: the refined rule's own rate.

## Concept map (IDs from the build spec)

| ID | Concept | Where you see it |
|---|---|---|
| C1 | A vague system prompt: "be conservative", "only flag important issues" | `VAGUE_PROMPT` in `criteria_setup.py`; POC 1 run `vague` |
| C2 | A test set of 5 snippets with known bugs, security issues and style nitpicks | `snippets/` and `PLANTED` (9 real, 7 decoys); `locate()` finds each line from its text |
| C3 | The vague baseline shows the false-positive problem | POC 1 run `vague`: `scored["fp"]` and `scored["fp_spots"]` from `score_run()` |
| C4 | "Be conservative" gives no decision boundary: evidence, not intuition | POC 1 run `vague`: `scored["verdicts"]` holds decoys `flagged` and real defects `missed` in the same run |
| C5 | Style flagged as critical, bugs missed or marked minor | `scored["verdicts"]`: `missed`, `flagged`, or a severity that differs from the planted one |
| C6 | Different results when the same snippets run twice | optional repeats in `PROMPTS`; the `stable` column (needs 2 runs) |
| C7 | Explicit categories: report bugs and security, skip style and local patterns | `criteria_prompt()`: the REPORT and SKIP lists |
| C8 | Flag a comment only when it contradicts the code | `COMMENT_RULE`; `scored["verdicts"]`: R8 reported, D4 and D6 `skipped` |
| C9 | Concrete categories remove the ambiguity behind false positives | `summarize()`: `fp_rate` for vague against criteria |
| C10 | Code examples for each severity level, not prose | `SEVERITY_EXAMPLES` (2 per level); `EXAMPLES_PROMPT = criteria_prompt(SEVERITY_EXAMPLES)` |
| C11 | Code examples calibrate severity better than prose | `summarize()`: `severity_accuracy` for criteria against examples |
| C12 | Compare false-positive rates on the same test set; say which is more consistent | `summarize()` per prompt in `poc1_vague_vs_explicit.py` |
| C13 | Articulate with data: only the system prompt changed | `PROMPTS` is the only thing that varies; `build_review_options()` |
| C14 | Vague 30–50% inconsistency, explicit below 15%, stable across runs | the `inconsistency=` and `stable=` columns (uncomment the repeats for 2 runs per prompt) |
| C15 | Disable any category above 25% false positives | POC 2 `category_table()`, `THRESHOLD`, `visible()`; `disabled` |
| C16 | Trust recovery: one noisy category costs trust in all; disabling restores it | POC 2 `before`, `after`, `runs_with_fp` and `collateral` |
| C17 | The refinements needed before re-enabling | POC 2 `refinement` (`REFINEMENTS`, `REFINED_PROMPT`) |
| C18 | A re-enablement plan with a target false-positive rate | the `Plan:` comment and `TARGET_FP`; `re_enable` |
| E1 | One schema for every prompt, whose categories include `style` and `other` | `REVIEW_SCHEMA` in `criteria_setup.py` |
| E2 | A production prompt with one loosely written rule, so one category is noisy | `LOOSE_COMMENT_RULE` and `PRODUCTION_PROMPT` in `poc2_trust_recovery.py` |

## Settings (`.env`)

* `MODEL_ID`: the model for every review in both POCs (default `claude-sonnet-5-5`).
* `MAX_BUDGET_USD`: the SDK stops any single review call whose estimated spend passes this (default `0.50`).
* `MAX_TURNS`: the safety cap on turns per review call (default `10`).
