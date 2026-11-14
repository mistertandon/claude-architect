# Validation, Retry and Feedback Loops: beginner POCs (Claude Agent SDK, Python)

Hands-on POCs for **Prompt Engineering & Structured Output → Validation, Retry and Feedback Loops** (Claude Certified Architect – Foundations).
Build spec: `curriculum/04-Prompt-Engineering-Structured-Output/04-revised-Validation-Retry-and-Feedback-Loops.md`.

## The idea in 30 seconds

```
POC 1, the retry loop (one document, seconds):
   extract (output_format: syntax guaranteed) ──► validate() in Python (semantics) ──► no errors ──► accepted
                                                        ├─ absent information ───────────────► human review, no retry
                                                        └─ fixable ──► retry: document + failed JSON + the errors

POC 2, the feedback loop (many documents, weeks):
   each finding's detected_pattern + reviewer decisions ──► dismissal rate per pattern ──► which prompt rule to fix next
```

* **Tool use fixes syntax, not meaning:** `output_format` guarantees valid JSON, but only your own checks see a wrong
  sum, swapped dates or a missing value.
* **A retry needs the error:** the retry message carries the document, the failed extraction and the specific
  errors, so Claude can fix exactly what is wrong.
* **The boundary:** retries fix format and structure; they can't create information the document doesn't have.
  Those documents go to a human, without a retry.
* **Dismissal data ranks prompt fixes:** the pattern reviewers dismiss most is the next one to refine.

## Files

| File | What it is | Calls the API? |
|---|---|---|
| `validation_setup.py` | `EXTRACTION_SCHEMA` (self-check fields, `detected_pattern`), the 5 documents, `TRUTH`, `extract()` and `validate()` | – |
| `poc1_retry_loop.py` | **POC 1**: the loop over 2 fixable and 3 unfixable documents, plus one retry-anyway control | Yes, 3 runs (6 calls when each retry succeeds) |
| `poc2_pattern_priorities.py` | **POC 2**: dismissal rates per `detected_pattern` from a review log, and the refinement priorities | No |
| `common.py` | reads `.env`, sets up logging, logs the model's input and output | – |

The documents: **F1** and **F2** start from a recorded bad extraction (`SEEDED`: F1's dates swapped, F2's first
amount 145.00 instead of 135.00), because a live first attempt on these clean invoices is usually right and the
retry path would rarely run. **U1** has no due date, **U2** no invoice number, **U3** no printed total.

## Setup (once)

```bash
cd "04-Prompt-Engineering-Structured-Output/04-Validation-Retry-and-Feedback-Loops"
python3 -m venv .venv && source .venv/bin/activate   # Python 3.10+
pip install -r requirements.txt                      # the SDK bundles Claude Code: nothing else to install
cp .env.example .env                                 # then put your API key in .env
```

If `python3 -m venv` says *ensurepip is not available* (Debian/Ubuntu), install the venv package for your
Python version first, e.g. `sudo apt install python3.14-venv`. You can also copy the `.env` from an earlier POC folder.

## Run (in this order)

```bash
python poc1_retry_loop.py           # 3 runs: fixable (F1, F2), unfixable (U1-U3), retry-anyway (U1)
python poc2_pattern_priorities.py   # free: the dismissal table and the priority list
```

## Reading the log

The log shows only what goes **into** the model and what comes **out** of it, plus the loop's checks and decisions.
A retry's `MODEL INPUT prompt` holds the three parts: `<document>`, `<failed_extraction>` and `<validation_errors>`.
Each run is also saved to `logs/<script>_<date>_<time>.log`.

Example from POC 1 (illustrative: your values will differ):

```
22:30:01  F2 attempt 1: seeded (a recorded bad extraction)
22:30:01  F2: schema valid; stated_total 285.0, calculated_total 295.0, total_discrepancy True; 2 semantic error(s)
22:30:01  F2   numeric: line 1 'Inventory sync licence' amount 145.00 != quantity 3 x unit_price 45.00 = 135.00.
22:30:01  F2   numeric: calculated_total 295.00 != stated_total 285.00 (difference 10.00).
22:30:01  F2 -> retry 1 with the document, the failed JSON and 2 error(s)
22:30:09  F2 -> accepted; line items: Inventory sync licence -> table_row; Onboarding session -> table_row; conflict_detected=False
22:30:09  F2 fields the feedback retry changed: ['calculated_total: 295.0 -> 285.0', 'total_discrepancy: True -> False', 'line 1 amount: 145.0 -> 135.0']
22:30:15  U1 -> human review: information the document doesn't have; no retry
22:30:40  U1 retry anyway: due_date = None (in the document: False): no real information appeared
22:30:40  review queue: ['U1 (due_date)', 'U2 (invoice_number)', 'U3 (stated_total)']
```

* `schema valid` and `2 semantic error(s)` on the same line is the whole point of validation: the JSON was perfect.
* The first line of the log compares the feedback retry with a naive one: the naive message has no failed JSON and
  no errors, so Claude would get the same input as a first attempt, with nothing pointing at line 1.
* The retry-anyway line: either `None` again (a wasted call) or a value that is not in the document (an invention).

## Concept map (IDs from the build spec)

| ID | Concept | Where you see it |
|---|---|---|
| C1 | `calculated_total`/`stated_total`, `total_discrepancy`, `conflict_detected`, `detected_pattern` per finding | `EXTRACTION_SCHEMA` and `LINE_ITEM` in `validation_setup.py` |
| C2 | Self-correction fields detect a discrepancy without external logic | line `<doc>: schema valid; stated_total ..., calculated_total ..., total_discrepancy ...` |
| C3 | `conflict_detected` and `detected_pattern` are the data for prompt improvement | line `<doc> -> accepted; line items: <item> -> <pattern>; conflict_detected=...`; POC 2 reads such data |
| C4 | Validation: completeness, numeric consistency, enum validity, date ordering | `validate()` in `validation_setup.py`; the `<doc>   <check>: ...` lines |
| C5 | Tool use removes syntax errors; semantic errors need validation and retries | `output_format` in `build_extract_options()`; the words `schema valid; ... semantic error(s)` |
| C6 | Specific, actionable errors: expected against found | the error messages, e.g. `amount 145.00 != quantity 3 x unit_price 45.00 = 135.00` |
| C7 | The retry message: original document + failed extraction + specific errors | `RETRY_TEMPLATE` and `retry_message()` in `poc1_retry_loop.py`; a retry's `MODEL INPUT prompt` |
| C8 | Feedback retries beat naive retries | the first log line (feedback vs naive message) and `F2 fields the feedback retry changed: ...` |
| C9 | 2 fixable and 3 unfixable documents: retry only the fixable ones | `process()`: the `-> retry` and `-> human review ... no retry` decisions |
| C10 | The retry boundary: retries can't create information absent from the source | `fixable=False` for completeness in `validate()`; line `U1 retry anyway: ...` |
| C11 | Fixable documents pass after 1–2 retries; unfixable ones go to human review | the `-> accepted` lines for F1 and F2; line `review queue: [...]` |
| C12 | Log `detected_pattern` per finding and analyse dismissals | POC 1's `line items: ... -> <pattern>`; `REVIEW_LOG` in `poc2_pattern_priorities.py` |
| C13 | A pattern reviewers keep dismissing needs a prompt refinement | POC 2's priority list with each pattern's entry in `REFINEMENTS` |
| C14 | The table: pattern, frequency, dismissal rate, prioritized highest first | POC 2 output: `pattern_report()` rows, then `Prompt refinement priorities` |
| E1 | The fixable cases start from a recorded bad extraction | `SEEDED` in `poc1_retry_loop.py`; line `F1 attempt 1: seeded (a recorded bad extraction)` |

## Settings (`.env`)

* `MODEL_ID`: the model for every extraction and retry (default `claude-sonnet-5-5`).
* `MAX_BUDGET_USD`: the SDK stops any single extraction call whose estimated spend passes this (default `0.50`).
* `MAX_TURNS`: the safety cap on turns per extraction call (default `10`).
