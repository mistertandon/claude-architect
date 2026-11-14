# Few-Shot Prompting: Revised POC Requirements (5 steps → 1 POC, Claude Agent SDK)

> **Source:** `02-raw-Few-Shot-Prompting.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Prompt Engineering & Structured Output → Few-Shot Prompting · **Build with:** Claude Agent SDK for Python (`claude_agent_sdk`)

---

## 1. Verdict: 1 POC

The 5 raw steps are not 5 separate concepts. They are **one A/B experiment on one set of 5 documents**: step 1 runs the baseline, step 2 reads its failures, step 3 writes the examples those failures call for, step 4 reruns the same documents, and step 5 sorts the problems into "fixed by examples" and "needs another technique".

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: Diagnose, then show, don't tell** | **Examples fix what instructions can't:** the same detailed extraction prompt runs three ways over a table, narrative and mixed document set (no examples; 3 examples as input/output pairs; the same 3 examples with reasoning), a failure table per document type comes first, and a decision matrix ends it by naming the problems examples don't fix | 1, 2, 3, 4, 5 |

**What changes with the Agent SDK:** nothing about few-shot itself: examples are text in the `system_prompt` string, which the SDK sends as the whole system prompt. Two SDK facts shape the experiment. Each `query()` call is a new session with an empty history, so every document is extracted on its own and the only examples Claude sees are the ones in the prompt. And `output_format` returns validated JSON in `ResultMessage.structured_output`, so JSON syntax never varies between the arms (E1). `ClaudeAgentOptions` has no `temperature` or `seed`, so run-to-run format drift is measured by running each arm twice (`RUNS = 2`). How Claude generalizes from an example can only be observed, not coded: the POC scores it field by field against known values.

- **Why 1 POC is enough:** steps 1–2 and steps 3–5 are the two halves of one comparison on the same documents, the same schema and the same scorer. Splitting them would need the baseline results handed from one script to another, or the baseline paid for twice.
- **Why not more POCs:** step 2 only reads step 1's scores, step 4 only reruns step 1 with a longer prompt, and step 5 only reads step 4's numbers. None of them needs its own setup.

**Applies to the POC:** Python 3.10+, `pip install claude-agent-sdk` (a recent 0.2.x; it bundles the Claude Code binary), `ANTHROPIC_API_KEY` set in the environment (never hard-coded), mock data only, and beginner-friendly code (small, commented scripts). The documents are supplier invoices sent to Fernway Outfitters, the made-up store of `06-revised-Task-Decomposition-Strategies.md`. Every extraction gets its options from `fewshot_setup.py`:

```python
MODEL = "claude-opus-5-5"
RUNS = 2  # no temperature or seed in ClaudeAgentOptions: format drift is measured by running each arm twice

EXTRACTION_SCHEMA = {  # every field required and none nullable: the design before topic 03 (E2)
    "type": "object",
    "properties": {
        "vendor_name": {"type": "string"},
        "invoice_date": {"type": "string"},
        "due_date": {"type": "string"},
        "total_amount": {"type": "number"},
        "line_items": {"type": "array", "items": {
            "type": "object",
            "properties": {"description": {"type": "string"}, "quantity": {"type": "number"},
                           "unit_price": {"type": "number"}},
            "required": ["description", "quantity", "unit_price"]}},
    },
    "required": ["vendor_name", "invoice_date", "due_date", "total_amount", "line_items"],
}

BASE_PROMPT = (  # detailed instructions, no examples (C1)
    "You extract invoice data for the accounts-payable team of Fernway Outfitters, an outdoor-gear store. Fill every "
    "field from the document: vendor_name is the company that issued the invoice, as written; invoice_date is the "
    "date the invoice was issued and due_date the date payment is due, both as YYYY-MM-DD; total_amount is the total "
    "amount due, as a number without a currency symbol; line_items has one entry per billed product or service, with "
    "its description, quantity and unit_price as numbers. Use only information in the document.")

def build_extract_options(system_prompt):
    return ClaudeAgentOptions(
        model=MODEL,                                                        # one model for every arm
        system_prompt=system_prompt,                                        # the ONLY thing that changes between arms
        output_format={"type": "json_schema", "schema": EXTRACTION_SCHEMA}, # validated JSON: syntax never varies (E1)
        tools=[],                                                           # no built-in tools: the document is in the prompt
        setting_sources=[],                                                 # ignore ~/.claude and project settings, CLAUDE.md and hooks
        env={"ENABLE_TOOL_SEARCH": "false"},                                # no ToolSearch calls
        max_turns=5,                                                        # safety cap (01 C16)
    )
```

**The 5 test documents** (`DOCUMENTS`, one string each) and their known values (`TRUTH`). Each `line_items` value lists `(quantity, unit_price)` pairs:

| Id | Structure | Document (abridged; the full text is in `fewshot_setup.py`) | `TRUTH` |
|---|---|---|---|
| T1 | table | `RIDGEWAY SHELVING CO.: INVOICE` · `Invoice date: 2026-09-14 \| Due date: 2026-10-14` · rows `Steel shelving unit, 5-tier \| 4 \| 310.00 \| 1,240.00` and `Corner bracket kit \| 4 \| 22.50 \| 90.00` · `Total due \| 1,330.00` | Ridgeway Shelving Co. · 2026-09-14 · 2026-10-14 · 1330.00 · (4, 310.00), (4, 22.50) |
| T2 | table | `CLOUDNEST SOFTWARE: INVOICE` · `Date: 2026-10-01 \| Payment due: 2026-10-31` · rows `Inventory sync licence (monthly) \| 3 \| 120.00 \| 360.00` and `Priority support add-on \| 1 \| 85.00 \| 85.00` · `Total due \| 455.00` (the supplier's own sum is 10.00 too high) | Cloudnest Software · 2026-10-01 · 2026-10-31 · 455.00 as stated · (3, 120.00), (1, 85.00), which sum to 445.00 |
| N1 | narrative | `Summit Tentworks. Dear Fernway team, this letter is our invoice, dated the third of September 2026. We delivered six Alpine two-person tents at one hundred eighty-nine dollars each, together with twelve packs of aluminium stakes at $7.50 a pack. As agreed, the replacement poles we sent last month remain free of charge. The total for this delivery is one thousand two hundred twenty-four dollars, payable within thirty days of the invoice date. Kind regards, Marta Ruiz` | Summit Tentworks · 2026-09-03 · 2026-10-03 · 1224.00 · (6, 189.00), (12, 7.50); the free poles are not billed |
| N2 | narrative | `Okafor Sign Works, note dated 18 September 2026. Hi Fernway, a quick note to bill you for the trail-signage job at your Bend store: our crew installed fourteen trail signs at $45 each and used two bags of mounting hardware at twenty-two dollars a bag. That makes $674 in total. Thanks, Dev Okafor` | Okafor Sign Works · 2026-09-18 · **no due date in the document** · 674.00 · (14, 45.00), (2, 22.00) |
| M1 | mixed | `HOLLIS PEST CONTROL: Invoice HPC-5521` · `Issued: 30/09/2026 (dates on this invoice are DD/MM/YYYY)` · row `Quarterly warehouse treatment \| 1 \| 260.00 \| 260.00` · `Notes: we also replaced 3 bait stations at $14.00 each; they are added to this invoice.` · `Terms: payment due 15 days after the issue date.` · `Total due: $302.00` | Hollis Pest Control · 2026-09-30 · 2026-10-15 · 302.00 · (1, 260.00), (3, 14.00) |

Each document has 5 fields. N2's `due_date` has no true value, so it is scored separately as the fabrication probe (C15), which leaves 24 scored fields per run and 48 per arm.

---

## 2. Concepts and POC requirements

All 15 concepts in the raw file (C1–C15) are covered: all 15 are new or build on earlier POCs and are taught below, none is a terminal command, and none was already covered by an earlier revised file (see the end of this section).
Previous revised files checked: `01-revised-Agentic-Loops.md`, `02-revised-Multi-Agent-Orchestration.md`, `03-revised-Subagent-Invocation-and-Context-Passing.md`, `04-revised-Workflow-Enforcement-and-Handoff.md`, `05-revised-Agent-SDK-Hooks.md`, `06-revised-Task-Decomposition-Strategies.md`, `01-revised-Tool-Interface-Design.md`, `02-revised-Structured-Error-Responses.md`, `03-revised-Tool-Distribution-&-Tool-Choice.md`, `04-revised-MCP-Server-Integration.md`, `05-revised-Built-in-Tools.md`, `01-revised-System-Prompts-with-Explicit-Criteria.md`. None uses examples in a prompt: `01-revised-System-Prompts-with-Explicit-Criteria.md` C10 uses code snippets to define severities, not worked input/output examples.
Raw step → concepts: **1** → C1–C4 · **2** → C5–C6 · **3** → C7–C9 · **4** → C10–C12 · **5** → C13–C15.
Rows marked **E** are extras that are not in the raw file. Without them, the POC breaks or gives misleading results.

### POC 1: Diagnose, then show, don't tell

**Build:** `fewshot_setup.py` and `poc1_few_shot.py`.

`fewshot_setup.py` holds `DOCUMENTS`, `DOC_TYPES` (`table`: T1, T2; `narrative`: N1, N2; `mixed`: M1), `TRUTH`, `EXTRACTION_SCHEMA`, `BASE_PROMPT`, `EXAMPLES`, `examples_block(with_reasoning)`, `PAIRS_PROMPT`, `FEWSHOT_PROMPT` and `build_extract_options()`, plus:
- `async def extract(system_prompt, doc_id)`: one `query()` with the prompt `"Extract the invoice below.\n\n<document>\n{text}\n</document>"`, streamed inside `try/except` (a single-shot `query()` raises after yielding an error result). It returns `structured_output`, or `None`;
- `score(doc_id, extraction)`: returns one verdict per field, `correct`, `empty` or `wrong`, plus `iso` (True when each non-empty date matches `^\d{4}-\d{2}-\d{2}$`). A field is `empty` when it is `""`, `[]` or a `total_amount` of 0. The rules for `correct`: `vendor_name` contains the true name (case-insensitive); dates are equal strings; `total_amount` is within 0.01; `line_items` holds the same `(quantity, unit_price)` pairs in any order. N2's `due_date` is reported as its raw value instead.

The examples (`EXAMPLES`, 3 entries `{"structure", "document", "reasoning", "extraction"}`) use 3 invoices that are not in the test set:

| Structure | Document (abridged) | Reasoning (as written in the prompt) | Extraction |
|---|---|---|---|
| table | `BRIGHTLINE PACKAGING: INVOICE` · `Invoice date: 2026-08-02 \| Due date: 2026-09-01` · rows `Shipping boxes, large \| 200 \| 1.15 \| 230.00`, `Packing tape, 6-pack \| 10 \| 8.40 \| 84.00` · `Total due \| 314.00` | `Each product row is a line item with its Qty and Unit price. The Total due row is the invoice total, not a line item. Both dates are already YYYY-MM-DD.` | Brightline Packaging · 2026-08-02 · 2026-09-01 · 314.00 · (200, 1.15), (10, 8.40) |
| narrative | `Juniper Lantern Co. Hello Fernway, please treat this letter as our invoice, dated the fifth of August 2026. We shipped eight brass camp lanterns at twenty-five dollars each and four replacement glass globes at $6.50 apiece. The carry bags we included are complimentary. The amount due is two hundred twenty-six dollars, payable within fourteen days of the invoice date.` | `This is a letter, so the facts are in sentences. "Dated the fifth of August 2026" is the invoice date, 2026-08-05. Numbers written as words become digits: eight lanterns at 25.00, four globes at 6.50. The carry bags are complimentary, so nothing is billed and they are not a line item. "Payable within fourteen days of the invoice date" gives the due date: 2026-08-05 plus 14 days is 2026-08-19. The total, 226.00, matches 8 × 25.00 + 4 × 6.50.` | Juniper Lantern Co. · 2026-08-05 · 2026-08-19 · 226.00 · (8, 25.00), (4, 6.50) |
| mixed | `CASCADE FILTERS LTD: Invoice CF-3307` · `Issued: 12/08/2026 (dates on this invoice are DD/MM/YYYY)` · row `Water filter cartridge \| 20 \| 18.00 \| 360.00` · `Notes: we also sent 5 spare O-ring kits at $3.00 each, added to this invoice.` · `Terms: payment due 21 days after the issue date.` · `Total due: $375.00` | `The header says the dates are DD/MM/YYYY, so 12/08/2026 is 12 August 2026: 2026-08-12. The table has one product, and the note adds a second billed item, 5 O-ring kits at 3.00. The terms give the due date: 2026-08-12 plus 21 days is 2026-09-02. The total, 375.00, matches 360.00 + 15.00.` | Cascade Filters Ltd · 2026-08-12 · 2026-09-02 · 375.00 · (20, 18.00), (5, 3.00) |

`examples_block(with_reasoning)` renders each example as `<example><document>…</document><reasoning>…</reasoning><extraction>{json}</extraction></example>`, leaving out the `<reasoning>` element when `with_reasoning` is False. `PAIRS_PROMPT = BASE_PROMPT + "\n\n" + examples_block(False)` and `FEWSHOT_PROMPT = BASE_PROMPT + "\n\n" + examples_block(True)`.

`poc1_few_shot.py` runs three arms, `base` (`BASE_PROMPT`), `pairs` (`PAIRS_PROMPT`) and `few-shot` (`FEWSHOT_PROMPT`), each over the 5 documents, `RUNS` times: 3 × 5 × 2 = 30 calls. It then prints the failure table (C5), the comparison (C10) and the decision matrix (C13).

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C2 | A test set of 5 documents with varied structures: tables, narrative paragraphs and mixed formats (**Builds on** `01-revised-System-Prompts-with-Explicit-Criteria.md` C2) | Write `DOCUMENTS`, `DOC_TYPES` and `TRUTH` as in the table above. New compared with that C2: the ground truth is field values, and the same facts appear in three structures (a table row, a sentence, a note under a table) | Arithmetic check: every document's line items sum to its total except T2 (445.00 against 455.00); N1's due date is 2026-09-03 + 30 days = 2026-10-03 and M1's is 2026-09-30 + 15 days = 2026-10-15 |
| E1 | All three arms return schema-validated JSON | Every arm uses `build_extract_options()` with `output_format`, so Claude returns its JSON through the `StructuredOutput` tool and the SDK validates it against `EXTRACTION_SCHEMA` (`02-revised-Multi-Agent-Orchestration.md` E4). A broken JSON reply would otherwise count as a failure of the examples, when it is a failure of the output channel | Code review: one `EXTRACTION_SCHEMA` and one options function, and `extract()` reads only `ResultMessage.structured_output` |
| E2 | The schema has no nullable field | Every field is required and typed without `null`, as in many first versions. This keeps the one problem few-shot can't fix visible: when a document has no due date, the schema leaves Claude no honest answer (C15). Topic 03 replaces it with nullable fields | Code review: `EXTRACTION_SCHEMA` has no `"null"` type, and `required` lists all 5 fields |
| C1 | A base extraction prompt with detailed instructions but no examples (**New**) | `BASE_PROMPT` (code above) defines every field, its format and its source, and contains no example. Run the `base` arm | 10 calls, each a `success` with `structured_output` set |
| C3 | Detailed instructions alone produce inconsistent output across varied document structures, the exact trigger for few-shot examples (**New**) | For the `base` arm, print the accuracy per document type: correct fields / scored fields, over both runs | Typically `table` close to 100% while `narrative` or `mixed` is lower. If every type is at 100%, record it: this model needs no examples for these documents, and the matrix will say so |
| C4 | The baseline symptoms: fields right from tables but empty or wrong from narrative, output formats that differ between runs, and edge cases handled differently each time (**New**) | For the `base` arm, print each field whose value differs between run 1 and run 2, each non-ISO date, and each `wrong` or `empty` field with its value | Typically at least one of: N1's free poles listed as a line item at 0.00; a due date given as text such as `30 days`, or left empty, instead of a computed date; M1's note item missing; N1 or M1 with different values in the two runs |
| C5 | Record which fields are consistently empty or inconsistent, by document structure (**New**) | `failure_table(scores)` prints one row per field and one column per structure: how many of that structure's (document, run) pairs scored `empty` or `wrong`, such as `due_date: table 0/4, narrative 2/2, mixed 1/2` | One row for each of the 5 fields, built from the `base` arm only |
| C6 | Diagnose before prescribing: the failure pattern says what the examples must demonstrate. Typically dates are right in tables but missed in narrative, amounts in words are inconsistent, and line items are empty when they sit in paragraphs (**New**) | Under the table, print the failing (field, structure) cells and, for each, the example that targets it: narrative cells → the narrative example; mixed cells → the mixed example; table cells → the table example | Every failing cell in the table maps to one of the 3 examples. The examples' reasoning covers the typical patterns: dates in words, numbers in words, free items, relative due dates, a DD/MM/YYYY date and an item in a note |
| C7 | Three few-shot examples that target the failing patterns, each with a different structure: table, narrative and mixed (**New**) | `EXAMPLES` (table above) uses 3 invoices that aren't in the test set, so a correct test answer can't be copied from an example | 3 examples with 3 structures. No test document's vendor or figures appear in `EXAMPLES` |
| C8 | Each example includes reasoning: how the data was located and why each extraction decision was made (**New**) | `FEWSHOT_PROMPT` includes each example's `<reasoning>`. Each reasoning names where each value came from and states the rule it applied | `FEWSHOT_PROMPT` contains 3 `<reasoning>` elements, and `PAIRS_PROMPT` contains none |
| C9 | Examples with reasoning teach the model to generalize to new patterns; input/output pairs alone teach surface pattern matching. The exam tests that reasoning-included examples outperform pairs (**New**) | Run the `pairs` arm next to `few-shot`: the same 3 examples, without their reasoning. Print both arms' accuracy on the parts of the test set that no example shows directly: N1's `per pack` pricing, N2 (a note, not a letter or a table) and T2's wrong total | Typically `few-shot` ≥ `pairs` overall, with any gap on N1 or N2. If the two arms tie, record it: on 5 short documents the gap can be small |
| C10 | Re-run the same 5 documents with the few-shot prompt and compare the empty-field rate, format consistency and extraction accuracy (**Builds on** `01-revised-System-Prompts-with-Explicit-Criteria.md` C12) | `compare(scores)` prints one row per arm: empty-field rate (empty fields / 48), format consistency (ISO dates / non-empty dates), accuracy (correct fields / 48) and the number of fields that changed between runs. Then one row per arm and structure with the accuracy. New compared with that C12: the measure is field accuracy and format consistency, not precision | 3 rows, all over the same 48 scored fields per arm |
| C11 | Few-shot examples are the first-choice technique for consistency problems and outperform more instructions for this class of problem (**New**) | Print the line `Same instructions in every arm: only the examples changed`, then the accuracy gain of `few-shot` over `base`. `BASE_PROMPT` is a prefix of both example prompts, so no arm has more instructions than another | `FEWSHOT_PROMPT.startswith(BASE_PROMPT)` and `PAIRS_PROMPT.startswith(BASE_PROMPT)` are both True |
| C12 | Expected: fewer empty fields (especially on narrative documents), better format consistency and higher accuracy, with the biggest gain on the document types that failed before (**New**) | No extra code: read the C10 rows | Typically `few-shot` has the lowest empty-field rate and the highest accuracy, its format consistency is 100% (every date ISO), and its largest per-structure gain is on `narrative` or `mixed` |
| C13 | Document which structural patterns benefit from few-shot examples and which need other techniques: a decision matrix (**New**) | `decision_matrix(scores)` prints 6 rows with the columns problem, measured on, `base`, `few-shot`, fixed by examples (yes/no) and technique: narrative extraction (N1, N2 fields), mixed formats (M1 fields), format consistency (ISO dates and run-to-run changes), missing data (N2's `due_date`), sum discrepancy (T2: line items against total) and malformed JSON (calls without structured output) | 6 rows. The first 3 compare the arms' numbers; the last 3 get their verdict from C14 and C15 |
| C14 | Match the technique to the problem: examples fix consistency and structural variety, but malformed JSON needs tool use, fabricated values need nullable schemas, and sum discrepancies need validation loops (**New**) | The technique column: `few-shot examples` for the first 3 rows; `nullable schema fields (topic 03)` for missing data; `validation and retry loop (topic 04)` for the sum discrepancy; `tool use / output_format (topic 03)` for malformed JSON | The malformed-JSON row shows 0 calls without structured output in every arm, because `output_format` already sends the JSON through a tool (E1). The sum row shows T2's line items summing to 445.00 against a total of 455.00 (or 445.00, if Claude "corrected" the total) in every arm: the source itself disagrees, so no example can fix it |
| C15 | Expected: narrative extraction and format consistency improve, while fabrication of missing data does not improve and needs a schema change (**New**) | The missing-data row prints N2's `due_date` from every run of both arms, labelled `empty` (`""`) or `invented` (any date or text). E2 makes both answers wrong: the schema has no way to say "not in the document" | N2's `due_date` is `empty` or `invented` in every run of every arm, typically a date such as 2026-10-18 (18 September + 30 days): the examples changed nothing here, and only a nullable field would let Claude answer null |

### Terminal commands (for the later tutorial)

None: every concept in this topic is a programming concept.

### Already covered by earlier POCs

None: every concept in this topic is new or builds on an earlier POC (cited in its row).
