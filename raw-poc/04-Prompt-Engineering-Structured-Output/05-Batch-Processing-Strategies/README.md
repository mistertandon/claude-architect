# Batch Processing Strategies: beginner POCs (Message Batches API, Python)

Hands-on POCs for **Prompt Engineering & Structured Output → Batch Processing Strategies** (Claude Certified Architect – Foundations).
Build spec: `curriculum/04-Prompt-Engineering-Structured-Output/05-revised-Batch-Processing-Strategies.md`.

**No Agent SDK here:** batching is a Messages API feature (`client.messages.batches`), and the Claude Agent SDK has
no batch interface. POC 2 uses the `anthropic` package; POC 1 makes no API call at all.

## The idea in 30 seconds

```
POC 1 (free):  does something wait for the result?  is the deadline longer than the 24 h window?
                    yes / no ──► synchronous API              no / yes ──► batch API (50% cheaper)
               SLA 30 h - 24 h maximum processing = 6 h buffer ──► submit every 4 h (worst case 28 h)

POC 2:  sample (5 docs, synchronous) ──► refine the prompt ──► batch (20 docs, custom_id each) ──► poll
                                                                    ──► results by custom_id ──► retry ONLY the failures
```

* **The matching rule:** batch only work whose results are used later, never a workflow someone or something waits
  on. "Batch everything for the 50% saving" breaks the blocking ones.
* **Plan for the 24-hour maximum**, not the typical hour: work backwards from the SLA, with a safety margin.
* **`custom_id` is the only link** from a result back to its document: results come back in any order.
* **Refine on a sample, then batch, then retry only the failures:** every point of first-pass success saves a
  resubmission, and resubmitting the whole batch pays twice for documents that already succeeded.

## Files

| File | What it is | Calls the API? |
|---|---|---|
| `poc1_batch_planning.py` | **POC 1**: the 5 workflows and the matching rule, the "batch everything" check, the SLA cadence | No |
| `batch_setup.py` | the 20 generated invoices and their truth, `BATCH_SCHEMA`, the 3 prompt versions, `build_params()`, `parse_output()`, `is_correct()` | – |
| `poc2_batch_pipeline.py` | **POC 2**: sample refinement, the 20-document batch, the retry batch | Yes, 3 runs (up to 15 sample calls, a 20-request batch, a 2-request batch) |
| `common.py` | reads `.env` | – |

`doc-01`–`doc-18` cycle through a table, a letter (quantities in words, one item "free of charge") and a mixed
document (one item in a note); `doc-19` and `doc-20` are 120-line outliers. The sample is `doc-01`–`doc-05`: every
structure and both edge cases, but no outlier: the outliers are the rare documents a sample misses.

## Setup (once)

```bash
cd "04-Prompt-Engineering-Structured-Output/05-Batch-Processing-Strategies"
python3 -m venv .venv && source .venv/bin/activate   # Python 3.10+
pip install -r requirements.txt                      # anthropic and python-dotenv (no Agent SDK needed)
cp .env.example .env                                 # then put your API key in .env
```

If `python3 -m venv` says *ensurepip is not available* (Debian/Ubuntu), install the venv package for your
Python version first, e.g. `sudo apt install python3.14-venv`. You can also copy the `.env` from an earlier POC folder.

## Run (in this order)

```bash
python poc1_batch_planning.py    # free: categorizes the workflows, checks the manager's plan, picks the cadence
python poc2_batch_pipeline.py    # 3 runs: sample (synchronous), the batch, the retry batch
```

POC 2 waits while the batch runs (typically under an hour; a batch not done in 24 hours expires), checking every
`POLL_SECONDS`. It saves the prompt and the batch ids to `batch_state.json` before waiting: if you stop it, run it
again and it resumes the same batch instead of paying for a new one. **Delete `batch_state.json` to start a new run.**

## What to compare

* `succeeded` in the batch counts doesn't mean usable: the outliers "succeeded" but stopped at `max_tokens` with
  incomplete JSON. `failed_ids()` checks both.
* Results arrive in any order, not `doc-01`…`doc-20`: only `custom_id` ties a result to its document.

## Concept map (IDs from the build spec)

| ID | Concept | Where you see it |
|---|---|---|
| C1 | 5 workflows, each blocking (synchronous) or latency-tolerant (batch), with a justification | `WORKFLOWS` and `categorize()` in `poc1_batch_planning.py`; `categories` in `main()` |
| C2 | The matching rule; the manager's "everything on batch" plan | `all_batch_check()`: the 3 workflows it would break |
| C3 | Blocking = someone or something waits; batch = results used later | the two tests in `categorize()`; the stock-reorder row (nobody waits, but an 8 h SLA) |
| C4 | A batch of 20: unique `custom_id`, model, `max_tokens`, messages | `requests` in the `batch` run and `run_batch()`; `messages.batches.create()` |
| C5 | `custom_id` correlates requests and results | `results[result.custom_id]` in `run_batch()`: results arrive in any order |
| C6 | Failure handling: find failures by `custom_id`, retry only them with a larger `max_tokens` | `failed_ids()`; the `retry` run with `RETRY_MAX_TOKENS` |
| C7 | Resubmit only the failures, never the whole batch | `retry = failed_ids(results)` in `main()`: only the failed `custom_id`s go into the retry batch |
| C8 | 30 h SLA − 24 h window = 6 h buffer; submit every 4 h | `submission_plan()`: the cadence loop returns 4 |
| C9 | Work backwards from the deadline with the maximum processing time and a margin | `SAFETY_MARGIN_HOURS`; `worst = cadence + BATCH_WINDOW_HOURS` in `submission_plan()` |
| C10 | A 5-document sample and 2–3 prompt iterations before the full batch | `refine_on_sample()` with `PROMPTS` v1–v3; it stops at the first version with all 5 correct |
| C11 | 90% first pass → 2 retries, 60% → 8: four times the resubmission cost | the `(C11)` comment in `main()`, and this run's `resubmissions_needed` |
| C12 | The full batch reaches a high first-pass success rate | `first_pass` and `good` in `main()` |
| E1 | No batch interface in the Agent SDK; the sample tests the exact batch request | `anthropic.AsyncAnthropic()`; `build_params()` feeds both `messages.create(**params)` and the batch entries |
| E2 | The models always think, and thinking counts toward `max_tokens` | `FIRST_MAX_TOKENS` and `OUTLIER_ITEMS` in `batch_setup.py` (see the note on the spec's limits) |
| E3 | Save the batch id before polling | `STATE_FILE` (`batch_state.json`) in `run_batch()`; a restarted run resumes from `state[key]` |

**Note on the limits:** the spec says `max_tokens` 1024 and 80-item outliers. Because the default `MODEL_ID` (and
Opus 5.5) always think, and thinking counts toward `max_tokens`, this build doubles both: 2048 for the first batch
(room to think on a 2–3 item invoice) and 120-item outliers (about 3,000 output tokens of JSON, so they still
overflow), with 16000 for the retry.

## Settings (`.env`)

* `MODEL_ID`: the model for the sample calls and every batch request (default `claude-sonnet-5-5`).
* `POLL_SECONDS`: how often a running batch is checked (default `60`).
* There is no `MAX_BUDGET_USD`: it is an Agent SDK guard, and this topic calls the Messages API directly. The whole
  run is about 37 small requests, 22 of them at the 50% batch price.
