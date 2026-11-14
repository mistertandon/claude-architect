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
| `common.py` | reads `.env`, sets up logging, logs the model's input and output | – |

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

## Reading the log

The log shows only what goes **into** the model and what comes **out** of it. `MODEL INPUT system` is the system
prompt under test (logged once per run), `MODEL INPUT prompt` the 5 numbered listings, and `structured` the findings
Claude hands in. Each run is also saved to `logs/<script>_<date>_<time>.log`.

Example from POC 1 (illustrative: your findings and numbers will differ):

```
21:10:02  MODEL INPUT   system       You are a code reviewer ... Be conservative and only flag important issues. ...
21:10:31  MODEL OUTPUT  structured   {'findings': [{'file': 'shipping.ts', 'line': 13, 'category': 'style', ...}, ...]}  (id=toolu_A)
21:10:31  MODEL OUTPUT  stop_reason  end_turn  (loop result: success)
21:10:31  vague: 9 finding(s), 2 false positive(s): ['D5', 'D2']
21:10:31  vague verdicts: R1=critical R2=critical R3=critical D2=flagged R4=major R5=critical!major ... R7=missed ... D5=flagged R9=missed
21:10:31  vague: 6 of 16 verdicts wrong
...
21:11:40  vague    runs=1  false positives=22%  inconsistency=6/16=38%  stable=n/a (1 run)  severity accuracy=86%
21:11:40  examples runs=1  false positives=0%  inconsistency=1/16=6%  stable=n/a (1 run)  severity accuracy=100%
21:11:40  Same model, schema, snippets and options: only the system prompt changed
```

* `R5=critical!major` means reported as critical but planted as major; `missed` and `flagged` are the other two
  ways to be wrong. The vague prompt typically goes wrong both ways at once.
* In POC 2, read the `category ... -> DISABLED` line, then the `developer sees: before ... after ...` line: the
  false-positive rate the developer sees drops to about zero, and `collateral` names the real defect the switch hides.
* The last POC 2 line (`re-enable comment_mismatch: yes/no`) is the plan's check: the refined rule's own rate.

## Concept map (IDs from the build spec)

| ID | Concept | Where you see it |
|---|---|---|
| C1 | A vague system prompt: "be conservative", "only flag important issues" | `VAGUE_PROMPT` in `criteria_setup.py`; POC 1 run `vague` |
| C2 | A test set of 5 snippets with known bugs, security issues and style nitpicks | `snippets/` and `PLANTED` (9 real, 7 decoys); `locate()` finds each line from its text |
| C3 | The vague baseline shows the false-positive problem | POC 1 line `vague: n finding(s), k false positive(s): [...]` |
| C4 | "Be conservative" gives no decision boundary: evidence, not intuition | POC 1 line `vague verdicts: ...`: decoys `flagged` and real defects `missed` in the same run |
| C5 | Style flagged as critical, bugs missed or marked minor | the `verdicts` line: `missed`, `flagged` and `!<true severity>` marks |
| C6 | Different results when the same snippets run twice | optional repeats in `PROMPTS`; the `stable` column (needs 2 runs) |
| C7 | Explicit categories: report bugs and security, skip style and local patterns | `criteria_prompt()`: the REPORT and SKIP lists |
| C8 | Flag a comment only when it contradicts the code | `COMMENT_RULE`; the `verdicts` line: R8 reported, D4 and D6 `skipped` |
| C9 | Concrete categories remove the ambiguity behind false positives | comparison lines: `false positives=` for vague against criteria |
| C10 | Code examples for each severity level, not prose | `SEVERITY_EXAMPLES` (2 per level); `EXAMPLES_PROMPT = criteria_prompt(SEVERITY_EXAMPLES)` |
| C11 | Code examples calibrate severity better than prose | comparison lines: `severity accuracy=` for criteria against examples |
| C12 | Compare false-positive rates on the same test set; say which is more consistent | the 3 comparison lines from `summarize()` |
| C13 | Articulate with data: only the system prompt changed | the line `Same model, schema, snippets and options: only the system prompt changed`; `build_review_options()` |
| C14 | Vague 30–50% inconsistency, explicit below 15%, stable across runs | the `inconsistency=` and `stable=` columns (uncomment the repeats for 2 runs per prompt) |
| C15 | Disable any category above 25% false positives | POC 2 `category_table()`, `THRESHOLD`, `visible()`; line `category ... -> DISABLED` |
| C16 | Trust recovery: one noisy category costs trust in all; disabling restores it | POC 2 line `developer sees: before ... after ...` and the `collateral` line |
| C17 | The refinements needed before re-enabling | POC 2 report line `Refinement: ...` (`REFINEMENTS`, `REFINED_PROMPT`) |
| C18 | A re-enablement plan with a target false-positive rate | the `Plan:` text and `TARGET_FP`; line `re-enable comment_mismatch: yes/no` |
| E1 | One schema for every prompt, whose categories include `style` and `other` | `REVIEW_SCHEMA` in `criteria_setup.py` |
| E2 | A production prompt with one loosely written rule, so one category is noisy | `LOOSE_COMMENT_RULE` and `PRODUCTION_PROMPT` in `poc2_trust_recovery.py` |

## Settings (`.env`)

* `MODEL_ID`: the model for every review in both POCs (default `claude-sonnet-5-5`).
* `MAX_BUDGET_USD`: the SDK stops any single review call whose estimated spend passes this (default `0.50`).
* `MAX_TURNS`: the safety cap on turns per review call (default `10`).
