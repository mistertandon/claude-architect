# Human Review and Confidence Calibration: Revised POC Requirements (5 steps → 2 POCs, offline Python)

> **Source:** `05-raw-Human-Review-Confidence-Calibration.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Context Management & Reliability → Human Review and Confidence Calibration · **Build with:** plain Python, offline: the raw file asks for a mock extraction system, so no model is called (see the verdict)

---

## 1. Verdict: 2 POCs

The 5 raw steps are not 5 separate concepts. Steps 1–3 are **one measurement of one labelled validation set**: step 1 produces the extractions with their confidence scores, step 2 measures their accuracy per segment, and step 3 measures what each confidence band really means. Steps 4–5 are **one production day that runs on that measurement**: step 4 keeps checking the automated side, and step 5 orders the human side.

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: Validate before you automate** | **Measured, not reported:** 1,000 labelled mock extractions (4 document types and 3 fields, each field with its own confidence) look 92.1% accurate in aggregate, while international dates are 40% accurate. Confidence bands per document type and field show that the same score means different things, and a lookup table turns a raw score into the accuracy it really predicts. Only standard invoices earn an automation threshold | 1, 2, 3 |
| **POC 2: Watch the automated side, review the uncertain side first** | **Calibrated scores drive both queues:** a stratified random sample covers the automated high-confidence invoices too, so it catches a new supplier's misread dates that reviewing low-confidence items never sees. A priority queue that reorders as items arrive gives two reviewers the most uncertain extraction next, by calibrated confidence: it catches 80 of the day's 136 errors, against 73 by raw confidence and 43 in arrival order | 4, 5 |

**What changes with the Agent SDK:** nothing runs on it here, on purpose. The raw file asks for a mock extraction system, and every lesson needs volume with known truth. Per-segment accuracy, calibration curves and drift detection need hundreds of labelled extractions with planted error rates, and a live model can't produce those reproducibly or cheaply. In a real pipeline, the extractor is a `query()` with `output_format` that returns each field's value and confidence. That is the pattern `06-revised-Multi-Instance-and-Multi-Pass-Review.md` already used for live self-reported confidence (`CONFIDENT_ISSUE`). Everything this topic adds sits downstream of that call: measuring, calibrating, sampling and routing are plain Python, and they wouldn't change if the scores came from Claude. So the mock returns exactly that shape (`{field: {"value", "confidence"}}`), and both POCs run offline and deterministically, as POC 1 of `05-revised-Batch-Processing-Strategies.md` did. One thing remains something you observe rather than code, even here: what a model's confidence means. The POCs learn it the only way possible, by counting against labels.

- **Why not 1 POC:** POC 2 automates, samples and routes with POC 1's thresholds and lookup. POC 1 must first show that the calibration is right, segment by segment. Then a missed error in POC 2 can only come from sampling or routing, not from a wrong threshold. The halves also answer different questions: can this score be trusted (POC 1), and what happens to the items every day (POC 2).
- **Why not 3 or more:** steps 1–3 are one pipeline over one validation set: the extractions, their accuracy and their calibration. Steps 4 and 5 consume the same production day and the same calibrated scores. Separate POCs would rebuild the day and the lookup for one function each.

**Applies to both POCs:** Python 3.10+ and the standard library only (`random`, `heapq`, `math`, `collections`). There are no API calls and no `ANTHROPIC_API_KEY`. Beginner-friendly code (small, commented scripts). Everything is deterministic: the mock uses no random numbers, and the one random draw (step 4's sample) uses a fixed seed. The data is supplier documents processed by an accounts-payable team. `calibration_setup.py` holds the mock:

```python
TYPES = ["standard_invoice", "handwritten_receipt", "scanned_pdf", "international"]
CODES = {"standard_invoice": "INV", "handwritten_receipt": "RCT", "scanned_pdf": "SCN", "international": "INT"}
FIELDS = ["vendor_name", "date", "amount"]
BANDS = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0)]
TARGET_ACCURACY = 0.95   # a field is automated only where its calibrated accuracy reaches this (C9)

VALIDATION_PLAN = {  # per type and field: (wrong, total) in each band, 0.5-0.6 ... 0.9-1.0 (C1, C3)
    "standard_invoice": {"vendor_name": [(0, 0), (0, 0), (0, 5), (2, 35), (6, 760)],
                         "date":        [(0, 0), (0, 0), (1, 10), (3, 50), (12, 740)],
                         "amount":      [(0, 0), (0, 0), (2, 15), (6, 60), (16, 725)]},
    "handwritten_receipt": {"vendor_name": [(2, 4), (6, 16), (10, 34), (6, 26), (0, 0)],
                            "date":        [(3, 5), (9, 18), (12, 33), (8, 24), (0, 0)],
                            "amount":      [(4, 6), (10, 20), (16, 32), (10, 22), (0, 0)]},
    "scanned_pdf": {"vendor_name": [(0, 0), (0, 0), (2, 10), (3, 30), (2, 30)],
                    "date":        [(0, 0), (0, 0), (3, 13), (4, 40), (1, 17)],
                    "amount":      [(0, 0), (0, 0), (5, 13), (6, 40), (3, 17)]},
    "international": {"vendor_name": [(4, 10), (5, 16), (3, 12), (3, 12), (0, 0)],
                      "date":        [(8, 10), (9, 16), (7, 12), (6, 12), (0, 0)],
                      "amount":      [(6, 10), (5, 16), (5, 12), (4, 12), (0, 0)]},
}

def band_of(confidence):
    # 0.5-0.6 -> 0 ... 0.9-1.0 -> 4. Rounding first keeps a score of exactly 0.9 in band 4.
    return min(4, int(round(confidence * 10, 6)) - 5)

def make_extractions(plan, prefix):
    extractions, labels = [], {}
    for doc_type in TYPES:
        columns = {}
        for field in FIELDS:  # one column per field: (confidence, correct), in rising confidence
            column = []
            for (low, _), (wrong, total) in zip(BANDS, plan[doc_type][field]):
                for j in range(total):
                    confidence = round(low + (j + 0.5) * 0.1 / total, 3)
                    correct = (j + 1) * wrong // total == j * wrong // total   # wrong items spread evenly in the band
                    column.append((confidence, correct))
            columns[field] = column
        for k in range(len(columns["vendor_name"])):  # document k takes item k of every column
            doc_id = f"{prefix}-{CODES[doc_type]}-{k:04d}"
            labels[doc_id] = {f: f"{f}-{k}" for f in FIELDS}
            extractions.append({"id": doc_id, "doc_type": doc_type, "fields": {
                f: {"value": f"{f}-{k}" if columns[f][k][1] else f"{f}-{k}-misread", "confidence": columns[f][k][0]}
                for f in FIELDS}})
    return extractions, labels
```

A document's three confidences rise together with `k`, as they do when a poor scan lowers every field. Each field still errs on its own: its column sets which of its items are wrong.

**POC 2's production day**, also in `calibration_setup.py`:
- **`make_drift()`:** 100 standard invoices from a new supplier, Brightline Packaging, with ids `P-BRL-0000`–`P-BRL-0099` and labels `f"{field}-B{k}"`. The supplier prints dates as `04.11.2026`, which the model misreads with high confidence: `vendor_name` at 0.97 (right), `date` at 0.96 (misread, value `date-B<k>-misread`) and `amount` at 0.97 (right).
- **`production_day()`:** `make_extractions(VALIDATION_PLAN, "P")` plus `make_drift()`, with their labels: 1,100 extractions. The day follows the validated distribution, plus one novel error pattern.
- **`is_automated(e, th)`:** True when every field's confidence is at or above its segment's threshold, and never when that threshold is `None`.
- **Helpers:** `has_error(e, labels)`, `raw_min(e)` (the lowest of the 3 field confidences) and `calibrated_min(e, lookup)` (the lowest `expected_accuracy()` of the 3 fields).

Both POC 2 scripts rebuild the same lookup and thresholds from `make_extractions(VALIDATION_PLAN, "V")`. The mock is deterministic, so no file has to pass between the POCs. The expected split is 825 automated extractions (725 standard invoices with all 3 fields at 0.9 or above, plus the 100 Brightline invoices) and 275 for review: 75 standard invoices, 80 receipts, 70 scanned PDFs and 50 international documents.

---

## 2. Concepts and POC requirements

All 18 concepts in the raw file (C1–C18) are covered: 16 are new or build on earlier POCs and are taught below, none is a terminal command, and 2 are already covered by `06-revised-Multi-Instance-and-Multi-Pass-Review.md` (see the end of this section).
Previous revised files checked: `01-revised-Agentic-Loops.md`, `02-revised-Multi-Agent-Orchestration.md`, `03-revised-Subagent-Invocation-and-Context-Passing.md`, `04-revised-Workflow-Enforcement-and-Handoff.md`, `05-revised-Agent-SDK-Hooks.md`, `06-revised-Task-Decomposition-Strategies.md`, `01-revised-Tool-Interface-Design.md`, `02-revised-Structured-Error-Responses.md`, `03-revised-Tool-Distribution-&-Tool-Choice.md`, `04-revised-MCP-Server-Integration.md`, `05-revised-Built-in-Tools.md`, `01-revised-System-Prompts-with-Explicit-Criteria.md`, `02-revised-Few-Shot-Prompting.md`, `03-revised-Structured-Output-with-Tool-Use.md`, `04-revised-Validation-Retry-and-Feedback-Loops.md`, `05-revised-Batch-Processing-Strategies.md`, `06-revised-Multi-Instance-and-Multi-Pass-Review.md`, `01-revised-Context-Window-Management.md`, `02-revised-Escalation-Ambiguity-Resolution.md`, `03-revised-Error-Propagation-in-Multi-Agent-Systems.md`, `04-revised-Codebase-Exploration-Context-Degradation.md`. The closest earlier work: `06-revised-Multi-Instance-and-Multi-Pass-Review.md` routed live findings by self-reported confidence and calibrated one threshold, and `02-revised-Few-Shot-Prompting.md` broke accuracy down by document structure to diagnose a prompt.
Raw step → concepts: **1** → C1–C4 · **2** → C5–C8 · **3** → C9–C12 · **4** → C13–C15 · **5** → C16–C18. Each step adds a Nudge and a Guidance, so concepts come from all five parts.
This topic needs no extras (**E** rows): every row below comes from the raw file.

### POC 1: Validate before you automate

**Build:** `calibration_setup.py` (the code above, plus the functions below; POC 2 reuses it) and `poc1_validate.py`. The functions:
- `accuracy_table(extractions, labels)`: per document type, each field's accuracy (a value equal to its label) and an all-fields value, plus an `aggregate` row over every extraction;
- `print_accuracy_table(table)` (C8);
- `calibration_curve(extractions, labels)`: `(n, correct)` per `(doc_type, field, band)`;
- `build_lookup(curve)` and `expected_accuracy(lookup, doc_type, field, confidence)` (C12);
- `thresholds(curve, target=TARGET_ACCURACY)` (C9).

`poc1_validate.py` runs `make_extractions(VALIDATION_PLAN, "V")` and prints, in order: the confidence profile per type (C3), the accuracy table and its comparisons (C5–C8), the calibration curves (C10, C11), the lookup examples (C12) and the thresholds (C9).

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C1 | A mock extraction system that outputs field-level confidence scores (0.0 to 1.0) for at least 4 document types (standard invoices, handwritten receipts, scanned PDFs, international documents), with noticeably different confidence distributions per type (**Builds on** `06-revised-Multi-Instance-and-Multi-Pass-Review.md` C9) | `make_extractions(VALIDATION_PLAN, "V")` (code above) returns the 1,000 validation extractions and their labels. Every field is `{"value", "confidence"}`, the shape a live extractor's structured output would have, and `labels` holds each field's truth. `VALIDATION_PLAN` fixes, per type and field, how many items fall in each confidence band and how many of them are wrong, so every later number is known in advance. New compared with 04-06 C9: the scores are per field and per document type, and they come with ground truth, which a live review never has | 1,000 extractions: 800 `standard_invoice`, 80 `handwritten_receipt`, 70 `scanned_pdf` and 50 `international`. Every confidence lies in 0.5–1.0, and every field has a label |
| C4 | At least 3 fields per extraction (vendor name, date, amount), each with its own confidence score (**New**) | Each field has its own row in `VALIDATION_PLAN`, so its confidences and its errors are set independently of the other fields, and a document can be right on one field and wrong on another. Inside each band, the wrong items are spread evenly, not packed at the band's low end. So errors don't pile up on the same documents, which would make a document's weakest field a poor guide to whether it is wrong | Every extraction has exactly the 3 fields. For example, `V-RCT-0005` has `vendor_name` at 0.609 (right), `date` at 0.603 (right) and `amount` at 0.592 (misread) |
| C3 | Realistic confidence distributions: high on standard invoices, lower on handwritten receipts and scanned PDFs, lowest on international documents (**New**) | For each document type, print the share of its field scores in each band and its mean confidence | Mean confidence: `standard_invoice` 0.941, `scanned_pdf` 0.863, `handwritten_receipt` 0.745 and `international` 0.702. 92.7% of standard-invoice scores are 0.9 or above, and no international score is |
| C5 | Accuracy tracking broken down by document type and field segment, not just one aggregate metric (**Builds on** `02-revised-Few-Shot-Prompting.md` C5) | `accuracy_table(extractions, labels)` (Build). New compared with 04-02 C5, which counted failures per document structure to choose few-shot examples: here the breakdown decides whether a segment may be automated at all | 12 segment accuracies, 4 all-fields values and 1 aggregate row, all computed from the labels |
| C8 | Display the results with document types as rows and fields as columns, and an aggregate row at the bottom that shows how it masks the problems (**New**) | `print_accuracy_table(table)`: rows in `TYPES` order, then `aggregate`; columns `vendor_name`, `date`, `amount` and `all fields`, as percentages with one decimal | The last row is `aggregate`: the only number a one-metric dashboard would show |
| C7 | Expected: standard invoices at 95% or more, handwritten receipts and international documents at 40–70%, and an aggregate that still looks excellent (90%+). The revealing comparison is the aggregate against the worst-performing segment (**New**) | Read the table, then print the aggregate next to the worst segment | `standard_invoice`: 99.0% / 98.0% / 97.0% (98.0% overall). `handwritten_receipt`: 70.0% / 60.0% / 50.0% (60.0%). `scanned_pdf`: 90.0% / 88.6% / 80.0% (86.2%). `international`: 70.0% / 40.0% / 60.0% (56.7%). `aggregate`: 94.6% / 91.4% / 90.2% (92.1%). The worst segment, `international` `date`, is at 40.0%, against the 92.1% aggregate |
| C6 | Trusting aggregate metrics is the most dangerous misconception in production extraction: a high overall accuracy can hide catastrophic failure rates on specific document types, because standard invoices dominate the volume. The exam tests that you validate by document type AND field before automating (**New**) | Print each type's share of the volume, the accuracy of everything except standard invoices, and the line `The aggregate is mostly standard invoices: validate every segment before automating any` | Volume shares: 80.0% / 8.0% / 7.0% / 5.0%. The other 200 documents together score 410/600 = 68.3%, yet the aggregate stays at 92.1%, because 2,352 of its 2,762 correct fields (85.2%) are standard-invoice fields |
| C10 | Raw model confidence is not calibrated: a reported 0.90 may be right 94% of the time on dates but only 82% on amounts. Calibration with a labelled validation set is required before confidence can drive automated routing (**Builds on** `06-revised-Multi-Instance-and-Multi-Pass-Review.md` C12) | Print the 0.9–1.0 band of `scanned_pdf` for each field: items, correct and accuracy. New compared with 04-06 C12, which found a gap between reported and confirmed confidence in general: here the same reported band means different accuracies for different fields of one document type | `scanned_pdf` at 0.9–1.0: `vendor_name` 28/30 = 93.3%, `date` 16/17 = 94.1%, and `amount` 14/17 = 82.4% |
| C11 | A calibration curve for each field type per document type: group extractions into confidence bands (0.5–0.6, 0.6–0.7, …) and compute the actual accuracy in each band. The curves show that the same score means different things for different field and document combinations (**New**) | `calibration_curve(extractions, labels)` counts `(n, correct)` per `(doc_type, field, band_of(confidence))`. Print the 12 curves, one line each, with `–` for an empty band. Then print one band across all segments: `date` at 0.8–0.9 | `date` at 0.8–0.9 means 94.0% on standard invoices, 90.0% on scanned PDFs, 66.7% on handwritten receipts and 50.0% on international documents. A curve can even fall as confidence rises: `scanned_pdf` `amount` goes from 85.0% at 0.8–0.9 to 82.4% at 0.9–1.0 |
| C12 | The calibration output is a lookup table: given the document type, the field type and the reported confidence, the actual expected accuracy (**New**) | `build_lookup(curve)` maps each non-empty `(doc_type, field, band)` to its accuracy. `expected_accuracy(lookup, doc_type, field, confidence)` returns that accuracy, or `None` for a band the validation set never saw: the score is then uncalibrated, and nothing may be automated on it | `international`, `date`, 0.85 gives 0.5. `standard_invoice`, `date`, 0.75 gives 0.9. `scanned_pdf`, `amount`, 0.93 gives about 0.824. `international`, `date`, 0.95 gives `None` |
| C9 | A calibration module that takes a labelled validation set (ground truth) and produces calibrated confidence thresholds per field type per document type (**Builds on** `06-revised-Multi-Instance-and-Multi-Pass-Review.md` C15) | `thresholds(curve, target=TARGET_ACCURACY)` returns, per `(doc_type, field)`, the lower edge of the lowest band from which every non-empty band upward reaches 95%. It returns `None` when even the top band misses that: that field is never automated. Print the 12 thresholds. New compared with 04-06 C15, which moved one shared threshold using an independent verifier: here each segment gets its own threshold, from labels | The 3 `standard_invoice` fields get 0.9, because their 0.8–0.9 bands reach only 94.3%, 94.0% and 90.0%. The other 9 segments get `None`: even `scanned_pdf`'s best band reaches only 93.3%, 94.1% and 82.4% |

### POC 2: Watch the automated side, review the uncertain side first

**Build:** `poc2_sampling.py` and `poc2_router.py`, reusing `calibration_setup.py`. Each script calls `production_day()` and rebuilds the lookup and thresholds from the validation set.

`poc2_sampling.py` defines `SAMPLE_SIZE = 50`, `MIN_PER_TYPE = 3`, `SEED = 2026` and `DRIFT_FACTOR = 2`, and these functions:
- `strata(extractions)`: the production extractions keyed by `(doc_type, band_of(raw_min(e)))`, so each extraction's weakest field decides its band. Items keep their production order;
- `allocate(strata)` (C15);
- `draw(strata, allocation, seed)` (C13);
- `stratum_error_rates(extractions, labels)`: the share of extractions with an error, per stratum.

`poc2_router.py` defines `WAVES = 5` and `REVIEWS_PER_WAVE = 20` (reviewers A and B, 10 each), and these pieces:
- `ReviewQueue` (C16);
- `arrival_order(items)`. Within each type, the queued items in id order get positions j = 0 … m − 1, and arrive at `((j * 37) % m + 0.5) / m` of the day. 37 shares no factor with 75, 80, 70 or 50, so each type's items arrive shuffled and spread through the day. All items are sorted by arrival time, then type order, then j;
- `simulate(policy)`.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C13 | Stratified random sampling that selects high-confidence extractions for ongoing verification, proportionally across all document types: a representative subset of each stratum (document type and confidence band), the high-confidence automated extractions included (**New**) | `draw()` makes one `random.Random(SEED)`, walks the strata in `TYPES` order and then band order, and takes `rng.sample(items, k)` from each stratum. Print each stratum's volume, allocation and draw. The sampling frame is every extraction of the day, automated or not | 51 extractions. `standard_invoice` gets 41: 1 at 0.7–0.8, 3 at 0.8–0.9 and 37 at 0.9–1.0. `handwritten_receipt` gets 4 (0 / 1 / 2 / 1 for 0.5–0.9), `scanned_pdf` 3 (0 / 2 / 1 for 0.7–1.0) and `international` 3 (0 / 1 / 1 / 1 for 0.5–0.9). 37 of the 51 come from the automated stratum `(standard_invoice, 0.9–1.0)`, which no reviewer would otherwise see. Three small strata (6, 10 and 13 items) round to 0 samples at this sample size. A larger sample, or a minimum per stratum, would cover them |
| C15 | Sample proportionally across all document types (80% of the volume means 80% of the sample) while giving every type a minimum representation (**New**) | `allocate(strata)` gives each type `max(MIN_PER_TYPE, round(SAMPLE_SIZE * volume / total))` samples and splits them across its strata by largest remainder, with ties going to the lower band. Print each type's volume share and sample share | Volumes 900 / 80 / 70 / 50 of 1,100 (81.8% / 7.3% / 6.4% / 4.5%) give 41 / 4 / 3 / 2. The minimum raises `international` from 2 to 3, so the sample has 51 items, 80.4% of them standard invoices |
| C14 | High-confidence extractions are automated and never reviewed. If the model develops a novel error pattern among them, only stratified sampling catches it; sampling only low-confidence items, which already go to human review, leaves systematic errors in the automated extractions unseen (**New**) | Compare two verification plans on the same day:<br>• `low-confidence only` checks just the review queue, the items that aren't automated;<br>• `stratified` checks C13's sample.<br>For each plan, print the Brightline items it saw and the errors it found. Then compare each sampled stratum's error rate (`has_error()`) with its validated rate from `stratum_error_rates()` on the validation set. Raise an alert when the sampled rate is above `DRIFT_FACTOR` times the validated rate | `low-confidence only`: 0 of the 100 Brightline invoices, all of which were automated. `stratified`, with `SEED = 2026`: 8 Brightline invoices among the 37 drawn from `(standard_invoice, 0.9–1.0)`. That stratum's sampled error rate is 8/37 = 21.6%, against a validated 32/725 = 4.4%, so it raises an alert. With any seed, a draw holds about 4.5 Brightline invoices on average, and at least 1 in 99.25% of draws |
| C16 | A review router that spends limited reviewer capacity on the highest-uncertainty items: a priority queue ordered by uncertainty (lowest confidence first) that reorders itself as new extractions arrive and serves each available reviewer the next most uncertain item, never in chronological order (**Builds on** `06-revised-Multi-Instance-and-Multi-Pass-Review.md` C11) | `ReviewQueue` wraps `heapq`: `add(items)` pushes `(priority, arrival, id)` entries, and `next_item()` pops the smallest. The 275 queued extractions arrive in 5 waves of 55 (`arrival_order()`). After each wave, reviewers A and B take turns, 20 items in all, so 100 of the 275 get reviewed. `simulate(policy)` runs three policies:<br>• `fifo`: arrival order;<br>• `raw`: `raw_min()`, then arrival;<br>• `calibrated`: see C18.<br>Print the queue's head before and after each wave, the first 6 assignments, and the errors caught per policy. New compared with 04-06 C11, which sorted one finished list: items keep arriving, so the order is rebuilt with every arrival | Errors caught, of the 136 in the queue: `fifo` 43, `raw` 73, `calibrated` 80. In the calibrated run, each of waves 2–5 brings a just-arrived extraction to the head: after wave 2, `P-INT-0003` replaces `P-INT-0042`. 99 of the 100 items served were not the oldest one waiting. The first two assignments are A: `P-INT-0000` and B: `P-INT-0007`, both at calibrated 0.2 |
| C18 | Prioritise by calibrated confidence (step 3) rather than raw: a raw 0.80 on an international document is less reliable than a raw 0.70 on a standard invoice (**New**) | The `calibrated` policy orders by `calibrated_min()`, then `raw_min()`, then arrival. Print two groups side by side: the queued international documents whose weakest raw score is in 0.8–0.9, and the queued standard invoices whose weakest raw score is in 0.7–0.8. For each group, print the count, the calibrated value and the documents with an error. Then print each policy's served items per type | International at raw 0.8–0.9: 12 documents, calibrated 0.5, 8 with an error. Standard invoices at raw 0.7–0.8: 15 documents, calibrated 0.867, 3 with an error. `raw` serves the invoices first, while `calibrated` serves the international documents first. Served per type (invoices / receipts / scanned / international): `raw` 9 / 48 / 9 / 34, and `calibrated` 0 / 58 / 0 / 42. That shift is how calibrated priority catches 7 more errors |

### Terminal commands (for the later tutorial)

None: every concept in this topic is a programming concept.

### Already covered by earlier POCs

| ID | Concept | Covered in | Check when reused |
|---|---|---|---|
| C2 | Field-level confidence scores are the foundation of intelligent review routing, and raw model confidence is not calibrated: it must be validated against ground truth before use | `06-revised-Multi-Instance-and-Multi-Pass-Review.md` C12 (and C10 for routing) | POC 2 automates and routes only with thresholds and a lookup that POC 1 built from the labelled validation set. No raw score ever decides automation |
| C17 | Human reviewers are expensive and limited: spreading their capacity evenly wastes it on high-confidence items and leaves too little for the uncertain ones that need human judgement | `06-revised-Multi-Instance-and-Multi-Pass-Review.md` C11 | With capacity for 100 of the 275 queued items, the priority queue catches 80 errors, against 43 in arrival order (C16) |
