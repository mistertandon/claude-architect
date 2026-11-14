# Validation, Retry and Feedback Loops: Revised POC Requirements (5 steps → 2 POCs, Claude Agent SDK)

> **Source:** `04-raw-Validation-Retry-and-Feedback-Loops.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Prompt Engineering & Structured Output → Validation, Retry and Feedback Loops · **Build with:** Claude Agent SDK for Python (`claude_agent_sdk`)

---

## 1. Verdict: 2 POCs

The 5 raw steps are not 5 separate concepts. Steps 1–4 build and test **one retry loop around one document**: step 1 adds the fields the loop checks, step 2 the checks, step 3 the retry, and step 4 tests where retrying stops working. Step 5 is **a second loop across many documents**: dismissal data from reviewers decides which prompt rule to fix next.

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: Validate, then retry with the error** | **The retry loop and its boundary:** an extraction with self-check fields, a validator that returns "expected X, found Y" errors, and a retry whose message carries the document, the failed JSON and those errors. Two documents with fixable errors pass after a retry; three with absent information go to human review without one | 1, 2, 3, 4 |
| **POC 2: Dismissal data sets the next prompt fix** | **The feedback loop:** each extracted line item records the `detected_pattern` that produced it, and an offline report over a reviewer dismissal log ranks the patterns by dismissal rate, so the worst pattern gets the next prompt refinement | 5 |

**What changes with the Agent SDK:** `output_format` already guarantees the syntax: Claude returns its JSON through the `StructuredOutput` tool, and the SDK validates it against the schema and re-prompts until it fits (`02-revised-Multi-Agent-Orchestration.md` E4). It can't know that a total is wrong or that two dates are swapped: semantic validation is Python code that runs on `ResultMessage.structured_output`. Every `query()` call is a new session, so a retry is a new call whose prompt must carry the document, the failed extraction and the errors. That is exactly the message the raw file asks for, and the log shows all three parts. Whether Claude fixes a named error, or invents a value it can't find, can only be observed, not coded: the POC checks the result against known values.

- **Why not 1 POC:** POC 1's loop decides about one document at run time, in seconds. POC 2's loop decides about the prompt over many reviewed documents, and needs a dismissal history that one run can't produce. Mixing them would hide that the second loop works on a different time scale and needs no API call.
- **Why not 3 or more:** step 1's fields exist for step 2's checks, step 3's retry only runs when step 2 fails, and step 4 only tests steps 1–3 on 5 documents. Splitting them would rebuild the documents and the extractor for one function each.

**Applies to both POCs:** Python 3.10+, `pip install claude-agent-sdk` (a recent 0.2.x; it bundles the Claude Code binary), `ANTHROPIC_API_KEY` set in the environment (never hard-coded), mock data only, and beginner-friendly code (small, commented scripts). The documents are supplier invoices sent to Fernway Outfitters, as in `03-revised-Structured-Output-with-Tool-Use.md`. Every extraction gets its options from `validation_setup.py`:

```python
MODEL = "claude-opus-5-5"
CURRENCIES = ["USD", "EUR", "GBP", "CAD"]   # checked in Python (enum validity), not in the schema
PATTERNS = ["table_row", "prose_sentence", "summary_row", "adjustment_row", "other"]

LINE_ITEM = {"type": "object", "additionalProperties": False,
             "required": ["description", "quantity", "unit_price", "amount", "detected_pattern"],
             "properties": {
                 "description": {"type": "string"}, "quantity": {"type": "number"},
                 "unit_price": {"type": "number"}, "amount": {"type": "number"},
                 "detected_pattern": {"type": "string", "enum": PATTERNS,   # which construct produced this finding (C1)
                                      "description": "Where this item was read from: a table row, a sentence, a "
                                                     "subtotal/tax/shipping row, a discount or credit row, or other."}}}

EXTRACTION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["vendor_name", "currency", "line_items", "calculated_total", "total_discrepancy", "conflict_detected"],
    "properties": {
        "vendor_name": {"type": "string"},
        "invoice_number": {"type": ["string", "null"]},              # nullable: absent stays null (topic 03)
        "invoice_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
        "due_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
        "currency": {"type": "string", "description": "ISO 4217 code, such as USD."},
        "line_items": {"type": "array", "items": LINE_ITEM},
        "stated_total": {"type": ["number", "null"], "description": "The total printed on the document."},
        "calculated_total": {"type": "number", "description": "Your own sum of the line item amounts."},
        "total_discrepancy": {"type": "boolean", "description": "True when calculated_total differs from stated_total."},
        "conflict_detected": {"type": "boolean", "description": "True when the document itself states conflicting values."},
    },
}

EXTRACT_PROMPT = ("You extract supplier invoices for the accounts-payable team of Fernway Outfitters. Use only the "
                  "document. Use null for a field the document doesn't contain. Compute calculated_total yourself and "
                  "compare it with the printed total.")

def build_extract_options():
    return ClaudeAgentOptions(
        model=MODEL,
        system_prompt=EXTRACT_PROMPT,
        output_format={"type": "json_schema", "schema": EXTRACTION_SCHEMA},  # syntax is guaranteed here (C5)
        tools=[],                                                             # no built-in tools: the document is in the prompt
        setting_sources=[],                                                   # ignore ~/.claude and project settings, CLAUDE.md and hooks
        env={"ENABLE_TOOL_SEARCH": "false"},                                  # no ToolSearch calls
        max_turns=10,                                                         # safety cap (01 C16)
    )
```

**The 5 test documents** (`DOCUMENTS`), each with its known values in `TRUTH`. All amounts are USD:

| Id | Kind | Document (abridged) | The point |
|---|---|---|---|
| F1 | fixable: misplaced values | `RIDGEWAY SHELVING CO. · Invoice RS-20502 · Invoice date: 2026-10-14 · Due date: 2026-11-13` · rows `Steel shelving unit, 5-tier \| 2 \| 310.00 \| 620.00`, `Shelf divider \| 6 \| 12.50 \| 75.00` · `Total due: 695.00` | its seeded first attempt has the two dates swapped |
| F2 | fixable: wrong totals | `CLOUDNEST SOFTWARE · Invoice CN-88407 · Issued: 2026-10-01 · Due: 2026-10-31` · rows `Inventory sync licence \| 3 \| 45.00 \| 135.00`, `Onboarding session \| 1 \| 150.00 \| 150.00` · `Total due: 285.00` | its seeded first attempt records the first amount as 145.00 and totals 295.00 |
| U1 | unfixable: absent information | `HOLLIS PEST CONTROL · Invoice HPC-5590 · Issued: 2026-10-02` · row `Quarterly warehouse treatment \| 1 \| 280.00 \| 280.00` · `Total: 280.00` | no due date and no payment terms anywhere |
| U2 | unfixable: absent information | `Marta's Taxi Service · Statement date: 2026-10-01 · Pay by: 2026-10-15` · row `Rides, Bend store to airport \| 14 \| 25.00 \| 350.00` · `Total: 350.00` | no invoice number |
| U3 | unfixable: absent information | `KESTREL RIDGE HOLDINGS · Invoice KRH-118 · Date: 2026-10-05 · Due: 2026-11-04` · rows `Storage bay rental, October \| 1 \| 1,800.00 \| 1,800.00`, `Forklift hire, 3 days \| 3 \| 200.00 \| 600.00` · `Total: see the attached statement.` | no stated total (the calculated total is 2,400.00) |

---

## 2. Concepts and POC requirements

All 14 concepts in the raw file (C1–C14) are covered: all 14 are new or build on earlier POCs and are taught below, none is a terminal command, and none was already covered by an earlier revised file (see the end of this section).
Previous revised files checked: `01-revised-Agentic-Loops.md`, `02-revised-Multi-Agent-Orchestration.md`, `03-revised-Subagent-Invocation-and-Context-Passing.md`, `04-revised-Workflow-Enforcement-and-Handoff.md`, `05-revised-Agent-SDK-Hooks.md`, `06-revised-Task-Decomposition-Strategies.md`, `01-revised-Tool-Interface-Design.md`, `02-revised-Structured-Error-Responses.md`, `03-revised-Tool-Distribution-&-Tool-Choice.md`, `04-revised-MCP-Server-Integration.md`, `05-revised-Built-in-Tools.md`, `01-revised-System-Prompts-with-Explicit-Criteria.md`, `02-revised-Few-Shot-Prompting.md`, `03-revised-Structured-Output-with-Tool-Use.md`.
Raw step → concepts: **1** → C1–C3 · **2** → C4–C6 · **3** → C7–C8 · **4** → C9–C11 · **5** → C12–C14.
Rows marked **E** are extras that are not in the raw file. Without them, the POC breaks or gives misleading results.

### POC 1: Validate, then retry with the error

**Build:** `validation_setup.py` (`MODEL`, `CURRENCIES`, `PATTERNS`, the schemas, `EXTRACT_PROMPT`, `build_extract_options()`, `DOCUMENTS`, `TRUTH`, `extract()` and `validate()`) and `poc1_retry_loop.py`.
- `async def extract(prompt)` makes one `query()`, streamed inside `try/except` (a single-shot `query()` raises after yielding an error result), and returns `structured_output`, or `None`.
- `validate(data)` returns a list of `{"check", "message", "fixable"}`, each message stating what was expected and what was found (C6).
- `poc1_retry_loop.py` defines `SEEDED`, `MAX_RETRIES = 2`, `RETRY_TEMPLATE`, `NAIVE_RETRY`, `retry_message(doc_id, failed, errors)` and `async def process(doc_id)`, which returns `{"doc", "status", "attempts", "errors"}` with `status` `accepted` or `human_review`. It runs F1 and F2, then U1–U3, then one retry-anyway control (C10). That is typically 6 calls: 1 retry each for F1 and F2, 1 extraction each for U1–U3, and the control.

```python
RETRY_TEMPLATE = ("Your extraction of this document failed validation. Correct it.\n\n"
                  "<document>\n{document}\n</document>\n\n"
                  "<failed_extraction>\n{failed}\n</failed_extraction>\n\n"
                  "<validation_errors>\n{errors}\n</validation_errors>\n\n"
                  "Fix what the errors name, using the document as the only source.")
NAIVE_RETRY = ("Your extraction of this document failed validation. Extract it again.\n\n"
               "<document>\n{document}\n</document>")
```

The checks in `validate()`, in this order:

| `check` | Rule | Example message | `fixable` |
|---|---|---|---|
| `completeness` | `invoice_number`, `invoice_date`, `due_date` and `stated_total` are not `null` | `completeness: due_date is null. Expected the payment due date (YYYY-MM-DD); found none.` | False |
| `conflict` | `conflict_detected` is false | `conflict: the extraction reports conflicting values in the document itself.` | False |
| `numeric` | each line's `amount` is `quantity × unit_price` (±0.01); `calculated_total` is the sum of the amounts; `calculated_total` equals `stated_total` when that is not `null` | `numeric: line 1 'Inventory sync licence' amount 145.00 != quantity 3 × unit_price 45.00 = 135.00.` · `numeric: calculated_total 295.00 != stated_total 285.00 (difference 10.00).` | True |
| `enum` | `currency` is in `CURRENCIES` | `enum: currency 'US$' is not one of USD, EUR, GBP, CAD.` | True |
| `date_order` | `due_date` is on or after `invoice_date` when both are set | `date_order: due_date 2026-10-14 is before invoice_date 2026-11-13. Expected due_date on or after invoice_date.` | True |

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C1 | An extraction tool with separate `calculated_total` and `stated_total` number fields, `total_discrepancy` and `conflict_detected` booleans, and a `detected_pattern` field on each finding in `line_items` (**Builds on** `03-revised-Structured-Output-with-Tool-Use.md` C1) | `EXTRACTION_SCHEMA` and `LINE_ITEM` (code above). New compared with 03 C1: fields in which Claude checks its own work, and a per-item field that records which document construct produced it | The schema has both totals as numbers (`stated_total` nullable), both booleans, and `detected_pattern` (enum `PATTERNS`) required on every line item |
| C2 | Self-correction fields such as `calculated_total` against `stated_total` let a discrepancy be detected automatically, without external logic (**New**) | For every extraction, print `stated_total`, `calculated_total` and `total_discrepancy`. `validate()` also recomputes the sum, so the flag is checked rather than trusted | F2's seeded attempt has `total_discrepancy: true`, so the discrepancy is visible in the extraction itself. In the live extractions of F1, F2 and U1, `total_discrepancy` is typically false, with the two totals equal |
| C3 | `conflict_detected` and `detected_pattern` build the data foundation for systematic prompt improvement (**New**) | After each accepted or reviewed document, print one line per line item: `description -> detected_pattern`, plus `conflict_detected`. These are the fields POC 2's report groups by | Every line item of every live extraction has a `detected_pattern` from `PATTERNS`, typically `table_row` for these table documents. `conflict_detected` is typically false |
| C4 | Validation logic that checks field completeness, numerical consistency (the calculated sum matches the stated total), enum validity and date ordering (**Builds on** `06-revised-Task-Decomposition-Strategies.md` C6) | `validate()` runs the checks in the table above. New compared with 06 C6: the rules compare values from several fields (amount against quantity × price, due date against invoice date), not only counts | Offline: the seeded F1 gives exactly 1 error (`date_order`), the seeded F2 exactly 2 (`numeric`: the line, and the totals), and F2's `TRUTH` gives `[]` |
| C5 | Semantic validation catches errors that tool use can't: tool use (`output_format`) eliminates schema syntax errors, while wrong sums and misplaced values need validation logic and retries (**Builds on** `02-revised-Multi-Agent-Orchestration.md` E4) | Print, per extraction, two lines: `schema: valid` (every `structured_output` already passed the SDK's check) and `semantic: <n> error(s)`. New compared with 02 E4: there the SDK's retry fixed the syntax; here the errors that remain are the ones only Python can see | Both seeded attempts are schema-valid JSON, yet fail `validate()`: syntax was never the problem |
| C6 | The validator returns specific, actionable error messages that state what was expected and what was found, not just that validation failed (**Builds on** `02-revised-Structured-Error-Responses.md` C7) | Every message names the field and both values, in the forms of the table above. New compared with 02's C7: the errors describe the model's output, not a tool failure, and they become the next prompt | Each printed error contains the field name, the found value and the expected value or rule. No message is a bare `invalid` |
| E1 | The fixable cases start from a recorded bad extraction | `SEEDED` holds F1's first attempt (`TRUTH` with the two dates swapped) and F2's (`TRUTH` with the first amount 145.00, `calculated_total` 295.00 and `total_discrepancy` true). A live first attempt on these clean documents is usually right, so without seeding, the retry path would rarely run. U1–U3 start with a live extraction, because their failure, absent information, is real | The log marks F1's and F2's first attempt as `seeded`, and U1–U3's as live |
| C7 | The retry loop: on a validation failure, send a follow-up message that contains the original document, the failed extraction and the specific validation errors (**Builds on** `02-revised-Structured-Error-Responses.md` C15) | `retry_message()` fills `RETRY_TEMPLATE` with the document, `json.dumps(failed, indent=2)` and one error message per line, and `process()` sends it with `extract()`. New compared with 02's C15: Python runs the loop and builds the feedback, and the message carries the failed output so Claude can see what to change | Each retry prompt in the log contains `<document>`, `<failed_extraction>` and `<validation_errors>`, with the document text, the failed JSON and every error message |
| C8 | Retry with error feedback is far more effective than a naive retry: without the specific error, the model has no guidance and typically repeats the same mistake (**New**) | Print, for F2's seeded failure, the lengths of `retry_message()` and of `NAIVE_RETRY` filled with the same document, and whether each contains the failed JSON and the errors. Then print which fields changed between F2's failed attempt and its corrected one | The naive message has no failed extraction and no error text: Claude would see the same input as a first attempt, so nothing points at line 1. The feedback retry changes typically exactly the fields the errors name: line 1's `amount` (to 135.00), `calculated_total` (to 285.00) and `total_discrepancy` (to false) |
| C9 | Test with 5 documents, 2 with fixable errors (misplaced values, wrong totals) and 3 with unfixable ones (absent information), and check that the loop retries only the fixable ones (**New**) | `process()`: validate attempt 1. No errors: `accepted`. Any error with `fixable` False: `human_review` at once, with no retry. Otherwise retry, at most `MAX_RETRIES = 2` times; still failing after that: `human_review`. Print one line per document: status, attempts, errors | F1 and F2: `accepted`, typically after 1 retry. U1, U2 and U3: `human_review` after 1 attempt, with 0 retries |
| C10 | The retry boundary, the concept the exam tests hardest: retries fix format mismatches and structural errors, but can't create information that isn't in the source (**Builds on** `02-revised-Structured-Error-Responses.md` C9) | The retry-anyway control: send U1's `retry_message()` once, although its only error is not fixable, and print U1's `due_date` after it with `in_document`: whether that value appears in U1's text. New compared with 02's C9: the boundary is about missing information, not a non-retryable tool error | The retried `due_date` is `null` again, or a date that is not in U1's text (an invention). Either way no real information appeared: a wasted call, or worse, a fabricated value |
| C11 | Fixable documents succeed after 1–2 retries with corrected totals or field placements; unfixable ones are identified as missing information and flagged for human review rather than retried (**New**) | After the 5 documents, print the review queue: each `human_review` document with the fields it lacks | The queue holds U1 (`due_date`), U2 (`invoice_number`) and U3 (`stated_total`). F1's accepted extraction has `invoice_date` 2026-10-14 and `due_date` 2026-11-13; F2's has line 1 `amount` 135.00 and `calculated_total` 285.00 |

### POC 2: Dismissal data sets the next prompt fix

**Build:** `poc2_pattern_priorities.py`, offline: no API calls. It defines `HISTORY`, `REVIEW_LOG`, `PRIORITY_THRESHOLD = 0.25`, `REFINEMENTS` and `pattern_report(log)`.

`HISTORY` is a mock dismissal log of 40 line items extracted in earlier runs, as `{pattern: (findings, dismissed)}`: `table_row` (18, 1), `prose_sentence` (8, 3), `summary_row` (6, 5), `adjustment_row` (4, 2), `other` (4, 0). `REVIEW_LOG` expands it into 40 entries `{"pattern", "dismissed"}`, the shape a real log of POC 1's findings and reviewer decisions would have. 11 of the 40 were dismissed (27.5%).

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C12 | Log the `detected_pattern` of each finding, and analyse which patterns are most often dismissed (**New**) | POC 1 logs each line item's pattern (C3). `REVIEW_LOG` is the same data after review: one entry per finding, with the reviewer's decision | `len(REVIEW_LOG) == 40`, and each entry's pattern is in `PATTERNS` |
| C14 | The result: a table of each `detected_pattern` with its frequency and dismissal rate, and a prioritized list of patterns that need refinement, with the highest dismissal rates at the top (**New**) | `pattern_report(REVIEW_LOG)` returns rows `{"pattern", "findings", "dismissed", "rate"}`, sorted by rate, highest first (frequency breaks ties). Print the table, then the priority list: the patterns whose rate is above `PRIORITY_THRESHOLD` | Order and rates: `summary_row` 5/6 = 83.3%, `adjustment_row` 2/4 = 50.0%, `prose_sentence` 3/8 = 37.5%, `table_row` 1/18 = 5.6%, `other` 0/4 = 0.0%. The priority list is `summary_row`, `adjustment_row`, `prose_sentence` |
| C13 | When reviewers keep dismissing findings from one pattern, that pattern needs a prompt refinement: dismissal data becomes prompt-improvement priorities (**Builds on** `01-revised-System-Prompts-with-Explicit-Criteria.md` C15, C17) | Print each priority with its entry in `REFINEMENTS`: `summary_row`: `Add an example whose reasoning says Subtotal, Tax and Shipping rows are totals, not line items.`; `adjustment_row`: `Add an example where a discount row is recorded as a negative adjustment, not a product.`; `prose_sentence`: `Add an example of a sentence that mentions an item that is not billed.` New compared with 01's C15 and C17: the unit is a document construct, not a review category, and the remedy is a new few-shot example (`02-revised-Few-Shot-Prompting.md`), not a switch | 3 lines, in priority order, each naming its pattern, its rate and its refinement |

### Terminal commands (for the later tutorial)

None: every concept in this topic is a programming concept.

### Already covered by earlier POCs

None: every concept in this topic is new or builds on an earlier POC (cited in its row).
