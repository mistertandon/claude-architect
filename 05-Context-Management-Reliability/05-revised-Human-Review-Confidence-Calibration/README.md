# Human Review and Confidence Calibration: beginner POCs (offline Python)

Hands-on POCs for **Context Management & Reliability → Human Review and Confidence Calibration** (Claude Certified Architect – Foundations).
Build spec: `curriculum/05-Context-Management-Reliability/05-revised-Human-Review-Confidence-Calibration.md`.

These POCs make **no API call**: the raw file asks for a mock extraction system, and every lesson needs volume with
known truth (hundreds of labelled extractions with planted error rates), which a live model can't produce
reproducibly or cheaply. In a real pipeline, the extractor is a `query()` with `output_format` that returns each
field's value and confidence; the mock returns exactly that shape, `{field: {"value", "confidence"}}`. Everything
these POCs teach sits downstream of that call and wouldn't change if the scores came from Claude.

## The idea in 30 seconds

```
POC 1, validate before you automate (1,000 labelled extractions):
   aggregate accuracy 92.1%  ── hides ──►  international dates at 40.0%
   reported 0.9-1.0 on scanned PDFs means 93.3% (vendor), 94.1% (date), 82.4% (amount)
   lookup table: (type, field, raw score) ──► the accuracy that score really predicts
   thresholds at 95%: only standard invoices (0.9) may be automated; 9 segments: always a human

POC 2, one production day (1,100 extractions):
   automated (825) ──► a stratified random sample still checks them ──► catches a new supplier's misread dates
   queued (275) ──► a priority queue by CALIBRATED confidence ──► 2 reviewers catch 80 of 136 errors (fifo: 43)
```

* **Validate per segment, not in aggregate:** standard invoices dominate the volume, so the aggregate looks
  excellent while whole document types fail.
* **Calibrate before you route:** a raw score means different accuracies for different fields and document types.
  A labelled validation set turns it into a lookup table and per-segment thresholds.
* **Keep watching the automated side:** a novel error pattern among high-confidence items never reaches a reviewer.
  Only a sample of every stratum, the automated one included, catches it.
* **Spend reviewers on uncertainty:** serve the most uncertain item next, by calibrated confidence, never in
  arrival order.

## Files

| File | What it is | Calls the API? |
|---|---|---|
| `calibration_setup.py` | the mock extractor (`VALIDATION_PLAN`, `make_extractions()`), the production day with the Brightline drift, and the shared calibration functions: `calibration_curve()`, `build_lookup()`, `expected_accuracy()`, `thresholds()`, `is_automated()`, `raw_min()`, `calibrated_min()` | No |
| `poc1_validate.py` | **POC 1**: confidence profiles, the accuracy table, calibration curves, the lookup table, the thresholds | No |
| `poc2_sampling.py` | **POC 2a**: the stratified sample, two verification plans, the drift alert | No |
| `poc2_router.py` | **POC 2b**: the review priority queue under fifo, raw and calibrated priority | No |

Standard library only (`random`, `heapq`): there is nothing to install, and no `.env` or API key.

## Setup (once)

```bash
cd "05-Context-Management-Reliability/05-revised-Human-Review-Confidence-Calibration"
python3 --version   # 3.10 or newer; no venv or packages needed
```

## Run (in this order)

```bash
python3 poc1_validate.py    # aggregate 92.1% against 40.0%; the 12 calibration curves; thresholds: 3 x 0.9, 9 x None
python3 poc2_sampling.py    # 51 sampled, 37 from the automated stratum: 8 Brightline errors, a drift alert
python3 poc2_router.py      # errors caught by 100 reviews: fifo 43, raw 73, calibrated 80 (of 136)
```

Everything is deterministic: the mock uses no random numbers, and the one random draw (the sample) uses
`SEED = 2026`. With another seed, a 37-item draw from the automated stratum holds about 4.5 Brightline invoices on
average, and at least 1 in 99.25% of draws. Real validation sets are larger, and real drift is subtler than "every
date from one supplier", but the mechanics are the same.

## Reading the output

The scripts print their results (there is no model I/O to log, and no log file). What to notice:

* **POC 1, section 2:** the `aggregate` row is the only number a one-metric dashboard shows; the `international`
  row is why you can't trust it.
* **POC 1, section 3:** `date` at 0.8-0.9 is 94.0% on standard invoices and 50.0% on international documents, and
  `scanned_pdf` `amount` even falls from 85.0% to 82.4% as the reported confidence rises.
* **POC 2a:** `low-confidence only` never sees a Brightline invoice: they were all automated.
* **POC 2b:** the calibrated policy serves 0 standard invoices and 42 international documents: a raw 0.8 on an
  international document (calibrated 0.5) is riskier than a raw 0.7 on an invoice (calibrated 0.867).

## Concept map (IDs from the build spec)

| ID | Concept | Where you see it |
|---|---|---|
| C1 | A mock extraction system with field-level confidence for 4 document types | `make_extractions()` and `VALIDATION_PLAN` in `calibration_setup.py`: 1,000 labelled extractions |
| C2 | Field-level confidence drives routing, and raw confidence must be validated first (already covered) | taught in `04-Prompt-Engineering-Structured-Output/06-Multi-Instance-and-Multi-Pass-Review`; here POC 2 automates and routes only with POC 1's thresholds and lookup |
| C3 | Realistic confidence distributions per document type | `poc1_validate.py` section 1: means 0.941 / 0.745 / 0.863 / 0.702 |
| C4 | At least 3 fields, each with its own confidence | `FIELDS` and one `VALIDATION_PLAN` row per field; e.g. `V-RCT-0005` is right on two fields and misread on `amount` |
| C5 | Accuracy by document type and field, not one aggregate | `accuracy_table()` in `poc1_validate.py` |
| C6 | Trusting aggregate metrics is the most dangerous misconception | section 2: volume shares, 410/600 = 68.3% for the other types, 85.2% of the correct fields are invoice fields |
| C7 | Expected: invoices 95%+, receipts and international 40-70%, aggregate 90%+ | section 2: the table, and the line `The aggregate says 92.1%; the worst segment, international date, is at 40.0%` |
| C8 | Types as rows, fields as columns, the aggregate at the bottom | `print_accuracy_table()` in `poc1_validate.py` |
| C9 | A calibration module that produces thresholds per field per document type | `thresholds()` in `calibration_setup.py`; section 5 |
| C10 | Raw confidence is not calibrated | section 3: `scanned_pdf at 0.9-1.0: vendor_name 93.3%, date 94.1%, amount 82.4%` |
| C11 | Calibration curves per field per document type | `calibration_curve()`; section 3: the 12 curves and `date` at 0.8-0.9 across types |
| C12 | The calibration output is a lookup table | `build_lookup()` and `expected_accuracy()`; section 4 (an unseen band gives `None`) |
| C13 | Stratified random sampling that includes the automated high-confidence extractions | `strata()` and `draw()` in `poc2_sampling.py`; 37 of 51 from `(standard_invoice, 0.9-1.0)` |
| C14 | Only stratified sampling catches a novel error pattern among automated items | `poc2_sampling.py`: the two verification plans, and the drift `ALERT` at 8/37 = 21.6% against 4.4% |
| C15 | Proportional sampling with a minimum per type | `allocate()`: 41 / 4 / 3 / 3, the minimum raising `international` from 2 to 3 |
| C16 | A priority queue that serves the most uncertain item next and re-orders as items arrive | `ReviewQueue` and `simulate()` in `poc2_router.py`; the wave-by-wave queue heads; 99 of 100 not the oldest |
| C17 | Reviewers are expensive and limited: spend them on uncertainty (already covered) | taught in `04-Prompt-Engineering-Structured-Output/06-Multi-Instance-and-Multi-Pass-Review`; here 80 errors caught against 43 in arrival order |
| C18 | Prioritise by calibrated, not raw, confidence | the `calibrated` priority in `simulate()`; `poc2_router.py`: the two groups, and 80 against 73 errors caught |

## Settings

None: there is no model call, so no `.env`. The tunable values are constants at the top of each script:
`TARGET_ACCURACY` (`calibration_setup.py`), `SAMPLE_SIZE`, `MIN_PER_TYPE`, `SEED` and `DRIFT_FACTOR`
(`poc2_sampling.py`), and `WAVES` and `REVIEWS_PER_WAVE` (`poc2_router.py`).
