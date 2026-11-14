# Context Window Management: beginner POCs (Claude Agent SDK, Python)

Hands-on POCs for **Context Management & Reliability → Context Window Management** (Claude Certified Architect – Foundations).
Build spec: `curriculum/05-Context-Management-Reliability/01-revised-Context-Window-Management.md`.

## The idea in 30 seconds

```
POC 1, what a long conversation keeps:
   lookup_order ──► 42 fields, 1,341 chars ──► PostToolUse hook ──► 1) copy the facts into CASE FACTS (from the RAW result)
                                                                   2) hand Claude 5 fields, 157 chars (88.3% smaller)

   every prompt, written by Python:   === CASE FACTS ===            exact values, never summarised
                                      === CONVERSATION SUMMARY ===  after turn 4: replaces turns 1-4, keeps no number
                                      === RECENT TURNS ===
                                      === CUSTOMER MESSAGE ===

POC 2, where a finding sits:
   plain:       details 1-4 │ 5 Payments: CB-4471 │ details 6-9             ──► CB-4471 49% of the way in
   structured:  ## Key Findings Summary (CB-4471 in bullet 5) ## Detailed Results ──► CB-4471  8% of the way in
```

* **Facts go in a block, not in the history:** summarisation keeps the story ("refunded in full") and loses the
  amounts, dates and IDs. A block of exact values on top of every prompt is never summarised, so they survive.
* **Extract, then trim, before the result enters the context:** one `PostToolUse` hook copies the facts out of the
  raw result, then replaces it with the 5 fields the task needs. Every later prompt resends the history, so an
  untrimmed result would cost its 1,184 extra characters again on every turn.
* **Python owns the history here:** each turn is a fresh `query()`, so the code decides what the summary replaces.
  In a continued session the SDK compacts on its own when the window fills up (a `PreCompact` hook fires, and a
  `SystemMessage` with subtype `compact_boundary` marks it), and which values survive is then up to the model.
* **Key findings first:** the fix for lost-in-the-middle is the layout. A note asking the model to read everything
  moves nothing.

## Files

| File | What it is | Calls the API? |
|---|---|---|
| `context_setup.py` | Lumen Home's 42-field order, `lookup_order` and `process_refund`, `CaseState`, the `PostToolUse` hook (`extract_case_facts()`, `trim_result()`), `build_case_options()` and `run_agent()` | – |
| `poc1_case_facts.py` | **POC 1**: 6 customer turns, the lossy summary after turn 4, turns 5-6 with and without the CASE FACTS block | Yes, 3 runs (8 calls) |
| `poc2_key_findings.py` | **POC 2**: 9 sources in a plain and a key-findings-first layout, where CB-4471 sits, one review per layout | Yes, 2 runs (1 call each) |
| `common.py` | reads `.env`, sets up logging, logs the model's input and output | – |

## Setup (once)

```bash
cd "05-Context-Management-Reliability/01-revised-Context-Window-Management"
python3 -m venv .venv && source .venv/bin/activate   # Python 3.10+
pip install -r requirements.txt                      # the SDK bundles Claude Code: nothing else to install
cp .env.example .env                                 # then put your API key in .env
```

If `python3 -m venv` says *ensurepip is not available* (Debian/Ubuntu), install the venv package for your
Python version first, e.g. `sudo apt install python3.14-venv`. You can also copy the `.env` from an earlier POC folder.

## Run (in this order)

```bash
python poc1_case_facts.py     # 3 runs: turns 1-4 (4 calls), then turns 5-6 with the block and without it (2 calls each)
python poc2_key_findings.py   # where CB-4471 sits in 3 layouts (no API), then 2 reviews: plain and structured
```

Optional extra, commented out in `poc2_key_findings.py`: a third review of the plain layout with the "read
everything" note on top.

What one run can't show:
* **POC 1** shows the typical result, 4 of 4 values with the block and 0 of 4 without it. If a without-facts reply
  quotes a value anyway, look at its turn in the log: a new `lookup_order` call, or an invented value.
* **POC 2:** the input is only about 4,700 characters, so a strong model typically reads all of it and holds the
  refund in both layouts. The position is certain, the miss is not: record either result. Misses show up in real
  aggregations of dozens of sources and tens of thousands of characters, where key findings first still puts the
  blocking finding in the first few percent.

## Reading the log

The log shows only what goes **into** the model and what comes **out** of it, plus the lines that hold the lesson.
Each run is also saved to `logs/<script>_<date>_<time>.log`, so you can re-read it without paying again.

Example from POC 1 (illustrative: your ids, timings, wording and sizes will differ):

```
10:02:01  MODEL INPUT   prompt       === CASE FACTS (exact values from tool results; never summarised) ===
{}

=== CUSTOMER MESSAGE ===
Hi, this is Dana Reyes (customer CUST-1042). The floor lamp from order ORD-8891 arrived with a cracked base. Can I return it?
10:02:04  MODEL OUTPUT  tool_use     mcp__lumen__lookup_order {'order_id': 'ORD-8891'}  (id=toolu_A1)
10:02:04  MODEL INPUT   tool_result  [{'type': 'text', 'text': '{"order_id": "ORD-8891", "order_date": "2026-03-03", "total_amount": 247.83, "return_eligible": true, "item_description": "Aurora floor lamp, brushed brass"}'}]  (tool_use_id=toolu_A1, is_error=None)
10:02:07  MODEL OUTPUT  text         I'm sorry the lamp arrived cracked, Dana. Order ORD-8891 can be returned: would you like a full refund of $247.83?
10:02:07  MODEL OUTPUT  stop_reason  end_turn  (loop result: success)
...
10:02:40  PostToolUse trim: lookup_order 1341 -> 157 chars (88.3% smaller). Prompt chars of turns 1-4: [224, 861, 1693, 1954]; with the untrimmed lookup in their history: [224, 2045, 2877, 3138]
...
10:03:02  Turns 5-6 with-facts: prompt chars [830, 1102]; quoted 4 of 4 exact values: RF-0001 yes, 247.83 yes, 8891 yes, March 3 yes
...
10:03:25  Turns 5-6 without-facts: prompt chars [497, 876]; quoted 0 of 4 exact values: RF-0001 NO, 247.83 NO, 8891 NO, March 3 NO
```

* Turn 1's `tool_result` has only the 5 refund fields, yet turn 2's CASE FACTS block also holds `customer_id`
  and `order_status`: the hook took the facts from the raw result before it trimmed it.
* From turn 5 on, the prompt has a CONVERSATION SUMMARY with no number in it. Only the with-facts prompts still
  hold `247.83`, `ORD-8891` and `2026-03-03`, in the block above the summary.
* In POC 2, the three `Layout` lines come before any API call. Then compare where `CB-4471` appears in the two
  review prompts, and whether each `structured` decision's reason names it.

## Concept map (IDs from the build spec)

| ID | Concept | Where you see it |
|---|---|---|
| C1 | Case facts extractor: raw tool output in, only the transactional facts out | `extract_case_facts()` in `context_setup.py`; turn 2's CASE FACTS block |
| C2 | A fixed set of transactional field types (amounts, dates, references, statuses, customer IDs) | `FACT_FIELDS` in `context_setup.py`: 5 types, 9 fields; `tax_amount`, `tracking_number` and the notes stay out |
| C3 | The persistent case facts block is never summarised | `summarise()` gets only the turn records; turn 5's with-facts prompt: the block still holds `247.83`, the summary holds no digit |
| C4 | The block is prepended to every prompt, outside the summarised history | `run_turn()` rebuilds it from `state.case_facts` every turn; no turn record contains it |
| C5 | Prompt construction: facts, then summarised history, then the current turn, under section headers | `build_prompt()` and the 4 headers in `poc1_case_facts.py`; `AGENT_PROMPT` says how far to trust each section |
| C6 | Structured data at the top of the first user message of every API call | `json.dumps(case_facts, indent=2)` under `FACTS_HEADER`: the start of every with-facts `MODEL INPUT   prompt` |
| C7 | Trimmer: an order lookup from 42 fields to the 5 a return needs; the task decides | `trim_result()` and `TASK_FIELDS` in `context_setup.py` |
| C8 | Untrimmed results cost context again in every later turn | log line `PostToolUse trim: ...`: turns 2-4 would each be 1,184 chars longer, 3,552 in all |
| C9 | Trim in a `PostToolUse` hook, before the result enters the history | `case_hook` in `build_case_hooks()`: facts first, then `updatedToolOutput`; turn 1's `tool_result` holds 5 fields |
| C10 | The trimmed result is 80-90% smaller | log line `PostToolUse trim: lookup_order 1341 -> 157 chars (88.3% smaller)` |
| C11 | A 6-turn conversation with summarisation after turn 4 | `TURNS`, `SUMMARISE_AFTER = 4` and `summarise()` in `poc1_case_facts.py`; turn 5's prompts |
| C12 | Two versions, with and without the block | `ARMS` in `poc1_case_facts.py`: each starts from `copy.deepcopy(state)` and the same summary |
| C13 | Expected: with the block the agent quotes $247.83, #8891 and March 3rd; without it they are lost | log lines `Turns 5-6 with-facts ... quoted 4 of 4` and `Turns 5-6 without-facts ... quoted 0 of 4` (typical) |
| C14 | Verify empirically that summarisation destroys the numbers and the block fixes it | the two `Turns 5-6` lines: same summary, model, tools and hook; only the CASE FACTS block differed |
| C15 | Lost in the middle: findings buried mid-input may be missed | POC 2: the `plain` review (CB-4471 at 49%) next to the `structured` one; see "What one run can't show" |
| C16 | Aggregation with a Key Findings Summary on top, then detailed results under headers | `aggregate()` in `poc2_key_findings.py`; each bullet is a source's own `key_finding`, whose figures all appear in its details |
| C17 | The fix is structural, not a prompt | the 3 `Layout` lines: the note moves CB-4471 from 49.3% to 50.3%, key findings first moves it to 7.7% |
| E1 | Python owns the history: each turn is a fresh `query()` | `build_case_options()`: no `resume`, `continue_conversation` or `ClaudeSDKClient` anywhere; 8 `run_agent()` calls |
| E2 | The summary is fixed text with no digit, the same in both versions | `LOSSY_SUMMARY` in `poc1_case_facts.py` |

## Settings (`.env`)

* `MODEL_ID`: the model for the support agent and the reviewer (default `claude-sonnet-5-5`).
* `MAX_BUDGET_USD`: the SDK stops any single `query()` call whose estimated spend passes this (default `0.50`).
