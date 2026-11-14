# Batch Processing Strategies: Revised POC Requirements (5 steps → 2 POCs, Message Batches API)

> **Source:** `05-raw-Batch-Processing-Strategies.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Prompt Engineering & Structured Output → Batch Processing Strategies · **Build with:** the `anthropic` Python package (Message Batches API), because the Claude Agent SDK has no batch interface (see the verdict)

---

## 1. Verdict: 2 POCs

The 5 raw steps are not 5 separate concepts. Steps 1 and 4 decide **whether and when to batch**: which workflows may wait up to 24 hours, and how often to submit so a deadline still holds. Steps 5, 2 and 3 are **one batch run, in that order**: refine the prompt on a sample, submit the full batch, then resubmit only what failed.

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: When to batch, and when to submit** | **The matching rule and the SLA math, offline:** 5 workflows sorted into synchronous and batch-eligible by one rule (does something wait, and is the deadline longer than the 24-hour window?), the manager's "batch everything" plan checked against it, and the submission cadence that keeps a 30-hour SLA | 1, 4 |
| **POC 2: Sample, batch, retry the failures** | **A batch run that pays once:** the extraction prompt refined on 5 sample documents with synchronous calls, 20 documents submitted as one batch with a `custom_id` each, results matched by `custom_id`, and a retry batch holding only the 2 failed documents with a larger `max_tokens` | 2, 3, 5 |

**What changes with the Agent SDK:** the Agent SDK has no batch interface: batching belongs to the Messages API (`client.messages.batches`), so POC 2 uses the `anthropic` package, and POC 1 makes no API call at all. This is the second topic after `03-revised-Tool-Distribution-&-Tool-Choice.md` (`tool_choice`) that needs the Messages API. A batch entry is `{"custom_id", "params"}`, where `params` is exactly a Messages API request body, so the sample calls use the same `params` dicts through `client.messages.create(**params)` (E1). Facts from the batch docs (checked 2026-10-27): a batch holds up to 100,000 requests or 256 MB; most batches finish within 1 hour, and a batch that isn't done within 24 hours expires; results are kept for 29 days; results can come back in any order, so they must be matched by `custom_id`; each `params` object is validated only during processing; and batch usage costs 50% of the standard price. When a batch finishes can only be observed (by polling `processing_status`), never set.

- **Why not 1 POC:** POC 1 is a decision table and a few lines of arithmetic, free and deterministic. A learner shouldn't have to pay for and wait on a batch to learn which workflows may use one.
- **Why not 3 or more:** the sample run produces the prompt the batch uses, and the failure handler reads that batch's results. Each step needs the previous one's output in the same process.

**Applies to both POCs:** Python 3.10+. POC 2 needs `pip install anthropic` and `ANTHROPIC_API_KEY` set in the environment (never hard-coded). Mock data only and beginner-friendly code (small, commented scripts). The documents are supplier invoices sent to Fernway Outfitters, the made-up store of `06-revised-Task-Decomposition-Strategies.md`. Every request in POC 2 is built by one function in `batch_setup.py`:

```python
MODEL = "claude-opus-5-5"
FIRST_MAX_TOKENS = 1024   # enough for a 2-3 item invoice plus thinking; the 2 outliers overflow it (E2)
RETRY_MAX_TOKENS = 8192   # the targeted change for the retry batch (C6)

BATCH_SCHEMA = {  # JSON outputs: every object needs additionalProperties: false
    "type": "object", "additionalProperties": False,
    "required": ["vendor_name", "invoice_date", "total_amount", "line_items"],
    "properties": {
        "vendor_name": {"type": "string"}, "invoice_date": {"type": "string"}, "total_amount": {"type": "number"},
        "line_items": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["description", "quantity", "unit_price"],
            "properties": {"description": {"type": "string"}, "quantity": {"type": "number"},
                           "unit_price": {"type": "number"}}}},
    },
}

def build_params(doc, system_prompt, max_tokens=FIRST_MAX_TOKENS):
    # One Messages API request body: the same dict for a synchronous sample call and for a batch entry (E1)
    return {
        "model": MODEL,
        "max_tokens": max_tokens,                                                   # includes thinking tokens (E2)
        "system": system_prompt,
        "messages": [{"role": "user", "content": doc["text"]}],
        "output_config": {"format": {"type": "json_schema", "schema": BATCH_SCHEMA}},  # the JSON arrives as the text block
    }
```

**The 20 documents.** `make_documents()` returns 20 `{"id", "structure", "text", "truth"}`, with ids `doc-01` to `doc-20`, built from a `VENDORS` list (6 suppliers, such as Ridgeway Shelving Co. and Cloudnest Software) and a `CATALOG` of `(description, unit_price)` pairs, so `truth` is known by construction:
- `doc-01`–`doc-18` cycle through 3 structures, 6 of each. `table`: a table with 2 line items and a total row. `narrative`: a letter that gives the quantities in words, such as "six tents at $189.00 each", and mentions one extra item "included free of charge". `mixed`: a table with 1 line item plus a note that adds a second billed item. Quantities are 2–12, and every document has an issue date.
- `doc-19` and `doc-20` are the outliers: tables with 80 line items each.

`SAMPLE = ["doc-01", "doc-02", "doc-03", "doc-04", "doc-05"]`: 2 tables, 2 letters and 1 mixed document, covering every structure and both edge cases (a free item and a note item). The outliers are deliberately not in the sample: they are the rare documents a sample misses.

---

## 2. Concepts and POC requirements

All 12 concepts in the raw file (C1–C12) are covered: all 12 are new or build on earlier POCs and are taught below, none is a terminal command, and none was already covered by an earlier revised file (see the end of this section).
Previous revised files checked: `01-revised-Agentic-Loops.md`, `02-revised-Multi-Agent-Orchestration.md`, `03-revised-Subagent-Invocation-and-Context-Passing.md`, `04-revised-Workflow-Enforcement-and-Handoff.md`, `05-revised-Agent-SDK-Hooks.md`, `06-revised-Task-Decomposition-Strategies.md`, `01-revised-Tool-Interface-Design.md`, `02-revised-Structured-Error-Responses.md`, `03-revised-Tool-Distribution-&-Tool-Choice.md`, `04-revised-MCP-Server-Integration.md`, `05-revised-Built-in-Tools.md`, `01-revised-System-Prompts-with-Explicit-Criteria.md`, `02-revised-Few-Shot-Prompting.md`, `03-revised-Structured-Output-with-Tool-Use.md`, `04-revised-Validation-Retry-and-Feedback-Loops.md`. None uses the Message Batches API.
Raw step → concepts: **1** → C1–C3 · **2** → C4–C5 · **3** → C6–C7 · **4** → C8–C9 · **5** → C10–C12.
Rows marked **E** are extras that are not in the raw file. Without them, the POC breaks or gives misleading results.

### POC 1: When to batch, and when to submit

**Build:** `poc1_batch_planning.py`, offline: no API calls. It defines `BATCH_WINDOW_HOURS = 24`, `SLA_HOURS = 30`, `SAFETY_MARGIN_HOURS = 2`, `WORKFLOWS`, `categorize(workflow)`, `all_batch_check(workflows)` and `submission_plan(sla_hours, cadences=(4, 6, 8))`.

`WORKFLOWS` (5 entries `{"name", "waiting", "sla_hours", "why"}`):

| Workflow | `waiting` (who or what waits for the result) | `sla_hours` |
|---|---|---|
| Pre-merge review of a pull request | a developer and the CI pipeline | 0.25 |
| Reply drafts for live-chat agents | a customer in the chat | 0.01 |
| Stock-reorder suggestions for the 06:00 order run | `None`: nobody watches, but the run starts at 06:00 | 8 |
| Supplier-invoice extraction for the accounts-payable run | `None` | 30 |
| Weekly product-review sentiment report | `None` | 168 |

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C1 | List 5 workflows of a hypothetical organisation and categorise each as blocking (synchronous) or latency-tolerant (batch-eligible), with a justification (**New**) | `categorize(w)` returns `("batch", reason)` only when `w["waiting"] is None` and `w["sla_hours"] > BATCH_WINDOW_HOURS`; otherwise `("synchronous", reason)`. The reason names the waiting party, or compares the SLA with the 24-hour window. Print a table: workflow, category, reason | 3 synchronous (the pull request, the live chat, the stock reorder) and 2 batch (invoice extraction, the weekly report) |
| C3 | Blocking workflows have someone or something waiting for the result; batch-eligible workflows consume the results later, with no real-time dependency (**New**) | The two tests in `categorize()` are the two halves of this rule: a waiting party, or a deadline shorter than the window, which is "something waiting" in time | The stock-reorder row is synchronous although `waiting` is `None`: its reason says the 8-hour SLA is shorter than the 24-hour window |
| C2 | The matching rule is the most tested concept here: the exam's manager wants every workflow on the batch API for the cost saving, and you must name the ones that can't tolerate the 24-hour processing window (**New**) | `all_batch_check(WORKFLOWS)` prints, for the "batch everything" plan, each workflow that would break and why, then the line `Batch only latency-tolerant work: the 50% saving never justifies a missed real-time dependency` | 3 workflows break: the pull request (a developer and CI would wait up to 24 hours), the live chat and the stock reorder (its 8-hour SLA is shorter than the window) |
| C8 | The submission frequency that guarantees a 30-hour SLA under the 24-hour maximum processing window: 30 − 24 = 6 hours of buffer, the latest safe submission is 24 hours before the deadline, and a batch every 4 hours keeps a fresh batch always in flight (**New**) | `submission_plan(SLA_HOURS)` prints the buffer (`SLA_HOURS - BATCH_WINDOW_HOURS`) and the latest safe submission (`deadline − 24 h`, which is 6 hours after a document arrives). Then, for each cadence in `(4, 6, 8)`: the worst case (a document arrives just after a submission, so it waits a full cadence and then up to 24 hours), the margin left (`SLA_HOURS - worst case`) and whether the margin is at least `SAFETY_MARGIN_HOURS`. Finally, the chosen cadence and how many batches are in flight at once (`ceil(24 / cadence)`) | Buffer 6 hours. 4 hours: worst case 28 hours, margin 2, OK. 6 hours: 30, margin 0, not OK. 8 hours: 32, margin −2, a breach. Chosen: every 4 hours, with up to 6 batches in flight |
| C9 | Work backwards from the SLA deadline: the maximum processing time plus a safety margin, a direct exam test point (**New**) | The plan never assumes the typical 1-hour batch: every worst case uses the full 24-hour window. Print the line `Plan for the 24-hour maximum, not the typical hour` | The 6-hour cadence fails the check even though a typical batch finishes in about 1 hour |

### POC 2: Sample, batch, retry the failures

**Build:** `batch_setup.py` (`MODEL`, the token limits, `BATCH_SCHEMA`, `build_params()`, `VENDORS`, `CATALOG`, `make_documents()`, `SAMPLE`, `PROMPTS`, `parse_output(message)` and `is_correct(doc, data)`) and `poc2_batch_pipeline.py`.
- `PROMPTS` holds 3 versions, each extending the last:
  - v1: `Extract this supplier invoice: the vendor, the issue date as YYYY-MM-DD, the total amount due, and the line items.`
  - v2: v1 + ` Include every billed item wherever it appears: table rows, sentences and notes.`
  - v3: v2 + ` Items given free of charge are not billed: leave them out. Write every quantity in digits.`
- `parse_output(message)` returns the parsed JSON of the text block, or `None` when `stop_reason` is `max_tokens` or the text doesn't parse.
- `is_correct(doc, data)` is True when `invoice_date` and `total_amount` (within 0.01) match `truth`, and the `(quantity, unit_price)` pairs match in any order.
- `poc2_batch_pipeline.py` runs three stages: the sample refinement (C10), the full batch (C4, C5) and the retry batch (C6, C7).

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| E1 | The Agent SDK has no batch interface, and the sample must test the exact batch request | `client = anthropic.Anthropic()`. Batch params are validated only while the batch runs, and an error then costs a wait of up to 24 hours. So every sample call sends `client.messages.create(**build_params(doc, prompt))`: the identical dict a batch entry will carry | Code review: the sample stage and the batch stage both call `build_params()`, and nothing else builds a request |
| E2 | Opus 5.5 always thinks, and thinking counts toward `max_tokens` | On Claude Opus 5.5, adaptive thinking is always on and `thinking: {type: "disabled"}` is rejected, so a request's `max_tokens` must cover thinking plus the JSON. `FIRST_MAX_TOKENS = 1024` leaves that headroom for a 2–3 item invoice, while each outlier's 80 line items need about 80 × 25 = 2,000 output tokens for the JSON alone, so they overflow it however little Claude thinks | The outliers' first results have `stop_reason == "max_tokens"`, and no 2–3 item document's does (typically) |
| C10 | A 5-document sample covering the document types and edge cases, refined over 2–3 prompt iterations before the full batch of 20 (**Builds on** `02-revised-Few-Shot-Prompting.md` C10) | Run `PROMPTS` in order on `SAMPLE` with synchronous calls (5 per version), and stop at the first version that scores 5/5 with `is_correct()`, after 3 versions at most. Print one line per version: correct documents out of 5, and which ones failed. The best version becomes `BATCH_PROMPT`. New compared with 02's C10: the point of iterating is the cost of the bulk run that follows, not the comparison itself | Typically v1 misses a free item or a note item (4/5 or lower) and v2 or v3 reaches 5/5. If v1 already scores 5/5, the loop stops after 1 version: record it, because the sample has done its job (a clean first pass) |
| C4 | A batch submission for 20 documents in the Message Batches API format: each entry has a unique `custom_id`, the model, `max_tokens` and a `messages` array with the document (**New**) | `requests = [{"custom_id": d["id"], "params": build_params(d, BATCH_PROMPT)} for d in documents]`, sent with `client.messages.batches.create(requests=requests)`. Check before sending that the ids are unique and match `^[a-zA-Z0-9_-]{1,64}$`. Poll `client.messages.batches.retrieve(batch_id)` every 60 seconds until `processing_status == "ended"`, printing `request_counts` each time | 20 requests with 20 distinct ids, each with `model`, `max_tokens`, `system`, `messages` and `output_config`. The first poll shows `in_progress` with `processing` 20, and the last shows `ended` |
| E3 | Save the batch id before polling | Write `{"batch_id": ...}` to `batch_state.json` right after `create()`. If the script starts again and the file exists, it polls that batch instead of creating a second one. A batch can take up to 24 hours, and a crash during that wait would otherwise mean paying for the same 20 documents twice | After a run, `batch_state.json` holds the id the log printed, and a rerun prints `resuming <batch id>` |
| C5 | `custom_id` is how batch results are matched to their requests: without unique ids you can't tell which documents succeeded or failed, so failure handling is impossible (**New**) | Read the results with `client.messages.batches.results(batch_id)` into a dict keyed by `result.custom_id`, and join each one to its document by that key. Print the ids in the order the results arrived, next to the submission order | Every document has exactly one result. The arrival order typically differs from `doc-01`…`doc-20`: the docs say results can come back in any order, so position means nothing and only `custom_id` links a result to its document |
| C6 | Failure handling: parse the batch results, identify the failures by `custom_id`, look up the original documents, and build a retry batch that holds only the failed documents with a larger `max_tokens` (or chunked content) (**Builds on** `04-revised-Validation-Retry-and-Feedback-Loops.md` C9) | `failed_ids(results)` returns each `custom_id` whose `result.type` isn't `succeeded` (`errored`, `canceled` or `expired`), or whose message `parse_output()` returns `None` (cut off at `max_tokens`, or not valid JSON). Build the retry batch from the documents with those ids, with `build_params(d, BATCH_PROMPT, RETRY_MAX_TOKENS)`, then poll and read it the same way. New compared with 04's C9: the failures are found by id in asynchronous results, and the targeted change is a request parameter, not a feedback message | `failed_ids()` returns `["doc-19", "doc-20"]` (typically only those two). The retry batch has exactly 2 requests, both with `max_tokens` 8192, and both typically come back `succeeded` with 80 correct line items |
| C7 | Resubmitting only the failures, with a targeted change, is the correct batch failure pattern; resubmitting the whole batch pays again for documents that already succeeded (**New**) | Print the requests in the retry batch next to what a full resubmission would send, and the share of the batch spend that a full resubmission would have wasted | Typically 2 requests instead of 20: 18 documents that already succeeded are not paid for twice |
| C11 | Refining the prompt on a sample before batching is the most cost-effective strategy: a 90% first-pass success rate means 2 retries on 20 documents, and 60% means 8, four times the resubmission cost (**New**) | Print `round(20 × (1 − 0.9))` and `round(20 × (1 − 0.6))` and their ratio, then this run's own first-pass success rate: documents that were both usable and `is_correct()` on the first batch, out of 20 | `2`, `8` and `4.0`. This run: typically 18/20 = 90%, with the 2 outliers as the only failures, so 2 resubmissions |
| C12 | The full batch reaches a high first-pass success rate (**New**) | Print each of the 18 regular documents' first-pass verdict (`correct`, `incorrect` or `failed`), and the final count after the retry batch | Typically all 18 regular documents are `correct` on the first pass, and all 20 are correct after the retry |

### Terminal commands (for the later tutorial)

None: every concept in this topic is a programming concept.

### Already covered by earlier POCs

None: every concept in this topic is new or builds on an earlier POC (cited in its row).
