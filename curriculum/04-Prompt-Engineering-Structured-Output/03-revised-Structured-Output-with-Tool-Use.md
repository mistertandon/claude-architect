# Structured Output with Tool Use: Revised POC Requirements (5 steps → 2 POCs, Claude Agent SDK)

> **Source:** `03-raw-Structured-Output-with-Tool-Use.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Prompt Engineering & Structured Output → Structured Output with Tool Use · **Build with:** Claude Agent SDK for Python (`claude_agent_sdk`), plus one short Messages API script for `tool_choice` (see the verdict)

---

## 1. Verdict: 2 POCs

The 5 raw steps are not 5 separate concepts. Steps 1 and 5 are about **what the schema allows**: step 1 designs it and step 5 tests it on documents with missing data. Steps 2–4 are about **whether a tool call happens at all**: the three `tool_choice` modes on the same extraction tool.

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: A schema that lets Claude say "not there"** | **Schema design prevents fabrication:** the same 5 invoices (3 complete, 2 with missing fields) are extracted twice through `output_format`, once with every field required and no `null` allowed, once with 3 required fields, 3 nullable ones and a category enum with `unclear` and `other`. The first schema forces invented values; the second returns `null` | 1, 5 |
| **POC 2: `auto`, `any` and a forced tool** | **Who decides whether a tool is called:** one Messages API script sends 4 inbox documents (2 invoices, a receipt, a newsletter) with three extraction tools, once per `tool_choice` mode, and shows text replies under `auto`, a guaranteed and schema-valid call under `any`, and the named tool every time when forced | 2, 3, 4 |

**What changes with the Agent SDK:** in the SDK, structured output with tool use is `output_format`. Claude Code adds a `StructuredOutput` tool whose input schema is your schema, Claude calls it to return its answer, and the SDK validates that input against the schema and re-prompts on a mismatch. The validated JSON arrives in `ResultMessage.structured_output`, and if validation keeps failing the run ends with `error_max_structured_output_retries`. So POC 1 teaches schema design with the SDK's own mechanism. `tool_choice` is different: `ClaudeAgentOptions` has no such field (02/03 E1), so every SDK tool call is effectively `auto`. On the Messages API, Claude Opus 5.5, Sonnet 5.5 and Fable 5.1 answer `any` and `tool` with a 400 error, while Claude Haiku 5.5 accepts them (tool-use docs, checked 2026-10-27). POC 2 therefore uses the `anthropic` package with `claude-haiku-5-5` (E1), and adds `strict: true` to every tool so that a guaranteed call also has schema-valid inputs (E2). Whether Claude invents a value or writes `null` can only be observed, not coded: the POCs compare every field with known values.

- **Why not 1 POC:** the two halves test different things with different runtimes. POC 1 needs a call that always returns JSON, so the only variable is the schema; POC 2 varies whether a call happens at all. Mixing them would let a missing tool call look like a schema failure.
- **Why not 3 or more:** steps 2–4 are one tool set run three times with one parameter changed, and step 5 only tests step 1's schema. Splitting them would rebuild the documents and the schemas for one parameter each.

**Applies to both POCs:** Python 3.10+, `pip install claude-agent-sdk` (a recent 0.2.x; it bundles the Claude Code binary), plus `pip install anthropic` for `poc2_tool_choice.py` only. `ANTHROPIC_API_KEY` is set in the environment (never hard-coded), with mock data only and beginner-friendly code (small, commented scripts). The documents are supplier invoices sent to Fernway Outfitters, the made-up store of `06-revised-Task-Decomposition-Strategies.md`. Both POCs import their schemas and documents from `extraction_setup.py`:

```python
MODEL = "claude-opus-5-5"
CATEGORIES = ["equipment", "software", "office_supplies", "travel"]

INVOICE_SCHEMA = {  # 3 required fields, 3 optional nullable fields, an enum with unclear and other, and a detail field (C1)
    "type": "object",
    "properties": {
        "vendor_name": {"type": "string", "description": "The company that issued the invoice, as written."},
        "total_amount": {"type": "number", "description": "The total amount due."},
        "category": {"type": "string", "enum": CATEGORIES + ["unclear", "other"],
                     "description": "What was bought. unclear: the document doesn't say. other: no listed category "
                                    "fits; describe it in category_detail."},
        "category_detail": {"type": ["string", "null"], "description": "Only when category is other: what was bought. Otherwise null."},
        "invoice_number": {"type": ["string", "null"], "description": "Exactly as printed, or null if the document has none."},
        "invoice_date": {"type": ["string", "null"], "description": "YYYY-MM-DD, or null if the document has none."},
        "tax_amount": {"type": ["number", "null"], "description": "As printed, or null if the document shows no tax."},
    },
    "required": ["vendor_name", "total_amount", "category"],   # only the 3 fields every invoice has
    "additionalProperties": False,                             # required by strict tool use (E2)
}

NAIVE_SCHEMA = {  # the anti-pattern: every field required, no null, and no way out of the category list (C3)
    "type": "object",
    "properties": {
        "vendor_name": {"type": "string"}, "total_amount": {"type": "number"},
        "category": {"type": "string", "enum": CATEGORIES},
        "invoice_number": {"type": "string"}, "invoice_date": {"type": "string"}, "tax_amount": {"type": "number"},
    },
    "required": ["vendor_name", "total_amount", "category", "invoice_number", "invoice_date", "tax_amount"],
    "additionalProperties": False,
}

EXTRACT_PROMPT = ("You extract supplier invoices for the accounts-payable team of Fernway Outfitters. "
                  "Fill the fields from the document only.")

def build_extract_options(schema):
    return ClaudeAgentOptions(
        model=MODEL,
        system_prompt=EXTRACT_PROMPT,                                  # the same prompt for both schemas
        output_format={"type": "json_schema", "schema": schema},       # structured output via the StructuredOutput tool
        tools=[],                                                      # no built-in tools: the document is in the prompt
        setting_sources=[],                                            # ignore ~/.claude and project settings, CLAUDE.md and hooks
        env={"ENABLE_TOOL_SEARCH": "false"},                           # no ToolSearch calls
        max_turns=10,                                                  # safety cap (01 C16), room for schema retries
    )
```

**The documents** (`INVOICES`, `RECEIPTS`, `OTHER`), with the known values in `TRUTH`:

| Id | Document (abridged; the full text is in `extraction_setup.py`) | `TRUTH` (vendor · total · category · number · date · tax) |
|---|---|---|
| D1 | `RIDGEWAY SHELVING CO. · Invoice RS-20417 · Date: 2026-09-14 · 4 × steel warehouse shelving unit @ $460.00 = $1,840.00 · Sales tax (8%): $147.20 · Total due: $1,987.20` | Ridgeway Shelving Co. · 1987.20 · equipment · RS-20417 · 2026-09-14 · 147.20 |
| D2 | `CLOUDNEST SOFTWARE · Invoice CN-88213 · Issued 2026-10-01 · Inventory sync subscription, October 2026: $450.00 · Tax: $36.00 · Amount due: $486.00` | Cloudnest Software · 486.00 · software · CN-88213 · 2026-10-01 · 36.00 |
| D3 | `HOLLIS PEST CONTROL · Invoice HPC-5521 · 2026-09-30 · Quarterly warehouse pest treatment: $280.00 · Tax: $22.40 · Total: $302.40` | Hollis Pest Control · 302.40 · other (detail mentions pest control) · HPC-5521 · 2026-09-30 · 22.40 |
| D4 | `Marta's Taxi Service · Monthly statement for the Fernway Outfitters sales team · 14 rides between your Bend store and the airport · Fares: $351.36 · GST: $35.14 · Please pay: $386.50 · Thank you!` | Marta's Taxi Service · 386.50 · travel · **none** · **none** · 35.14 |
| D5 | `KESTREL RIDGE HOLDINGS · Date: 2026-10-05 · For: as agreed · Amount due: $2,400.00 · Payment within 30 days.` | Kestrel Ridge Holdings · 2400.00 · unclear · **none** · 2026-10-05 · **none** |
| R1 | `TRAILSIDE CAFÉ · 2026-10-12 08:41 · 2 × flat white $4.50 · 1 × breakfast burrito $9.75 · Total $18.75 · Paid: Visa ****4417` | a receipt (POC 2 only) |
| N1 | `Kestrel Supply newsletter: our autumn catalogue is out! New insulated jackets, and 20% off tents until 31 October. Visit kestrelsupply.example to browse.` | neither an invoice nor a receipt (POC 2 only) |

`ABSENT = {"D4": ["invoice_number", "invoice_date"], "D5": ["invoice_number", "tax_amount"]}`: 4 absent fields in all. D3 needs `other` and D5 needs `unclear`, so 2 of the 5 categories fall outside `CATEGORIES`.

---

## 2. Concepts and POC requirements

All 13 concepts in the raw file (C1–C13) are covered: 11 are new or build on earlier POCs and are taught below, none is a terminal command, and 2 are already covered by `03-revised-Tool-Distribution-&-Tool-Choice.md` (see the end of this section).
Previous revised files checked: `01-revised-Agentic-Loops.md`, `02-revised-Multi-Agent-Orchestration.md`, `03-revised-Subagent-Invocation-and-Context-Passing.md`, `04-revised-Workflow-Enforcement-and-Handoff.md`, `05-revised-Agent-SDK-Hooks.md`, `06-revised-Task-Decomposition-Strategies.md`, `01-revised-Tool-Interface-Design.md`, `02-revised-Structured-Error-Responses.md`, `03-revised-Tool-Distribution-&-Tool-Choice.md`, `04-revised-MCP-Server-Integration.md`, `05-revised-Built-in-Tools.md`, `01-revised-System-Prompts-with-Explicit-Criteria.md`, `02-revised-Few-Shot-Prompting.md`.
Raw step → concepts: **1** → C1–C5 · **2** → C6–C7 · **3** → C8–C9 · **4** → C10–C11 · **5** → C12–C13 (its "Why" repeats C2–C4).
Rows marked **E** are extras that are not in the raw file. Without them, the POC breaks or gives misleading results.

### POC 1: A schema that lets Claude say "not there"

**Build:** `extraction_setup.py` (the documents, `TRUTH`, `ABSENT`, both schemas, `EXTRACT_PROMPT` and `build_extract_options()`, code above, plus `extract()` and `score()`; POC 2 reuses it) and `poc1_schema_design.py`.
- `async def extract(doc_id, schema)` makes one `query()` with the prompt `"Extract this invoice.\n\n<document>\n{text}\n</document>"`, streamed inside `try/except` (a single-shot `query()` raises after yielding an error result). It returns `{"data", "subtype"}`: `data` is `structured_output`, or `None` when the run ended without one.
- `score(doc_id, data)` returns one verdict per field: `correct`, `null` (the field is `None` or missing) or `wrong`. For an absent field, `null` is right and any value is `invented`.
- `poc1_schema_design.py` extracts D1–D5 with `NAIVE_SCHEMA` and then with `INVOICE_SCHEMA` (10 calls) and prints one line per document and schema, then the totals.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C1 | An extraction tool defined by a JSON schema: 3 required fields, 3 optional/nullable fields, an enum with `unclear` and `other`, and a detail string for `other` (**Builds on** `01-revised-Agentic-Loops.md` C2) | `INVOICE_SCHEMA` (code above). In POC 1 it is the input schema of the SDK's `StructuredOutput` tool, through `output_format`; in POC 2 it is the `input_schema` of the `extract_invoice` tool. New compared with 01 C2: the schema is designed for honesty, with fields that may legitimately be empty | `required` is exactly `["vendor_name", "total_amount", "category"]`, `invoice_number`, `invoice_date`, `tax_amount` and `category_detail` each allow `"null"`, and the `category` enum ends with `unclear` and `other` |
| C4 | Optional, nullable fields allow honest `null` responses: `required` lists only the fields every document has (**New**) | `invoice_number`, `invoice_date` and `tax_amount` are left out of `required` and typed `["string", "null"]` or `["number", "null"]`. Each description says when to answer `null`. `score()` treats a missing key like `null` | On D4 and D5 with `INVOICE_SCHEMA`, the 4 `ABSENT` fields typically come back `null` (or missing), never a value |
| C5 | An enum with `unclear` and `other` beside the standard categories, plus a detail string for `other` (**New**) | `category` lists the 4 business categories plus `unclear` and `other`. `category_detail` is filled only for `other`. Print each document's category, and the detail when there is one | With `INVOICE_SCHEMA`: D3 is typically `other` with a detail mentioning pest control, and D5 `unclear`. D1, D2 and D4 get `equipment`, `software` and `travel` |
| C3 | Required fields pressure the model to invent values when the information is absent (**New**) | Run D1–D5 with `NAIVE_SCHEMA`. It requires all 6 fields and allows no `null`, and its enum has no way out, so the SDK's validator rejects any honest "nothing here" and re-prompts until Claude supplies a value. For each `ABSENT` field, print the value Claude gave | By construction, all 4 absent fields come back with a value: typically placeholders such as `""` or `N/A`, or plausible inventions such as `tax_amount: 0` for D5 or a September date for D4. D3 and D5 get one of the 4 listed categories, so both are wrong by construction. If a run ends with `error_max_structured_output_retries`, record it: the schema left no valid honest answer, so the run failed instead |
| C2 | Schema design directly prevents fabrication: it is the root-cause fix for hallucinated extraction data (**New**) | Print one totals line per schema: invented values out of 4 absent fields, and wrong categories out of 5. Both runs used the same documents, prompt, model and options; only the schema differs | `NAIVE_SCHEMA`: 4 of 4 absent fields filled and 2 of 5 categories wrong. `INVOICE_SCHEMA`: typically 0 of 4 and 0 of 5 |
| C12 | Process 5 documents, 3 complete and 2 with missing fields, and check that nullable fields return `null` rather than fabricated values (**New**) | Run D1–D5 with `INVOICE_SCHEMA`. `score()` marks every non-null value in an `ABSENT` field as `invented` | D4: `invoice_number` and `invoice_date` are `null`. D5: `invoice_number` and `tax_amount` are `null`. Typically 0 `invented` |
| C13 | The complete documents get every field right, and the incomplete ones get no invented dates, amounts or identifiers (**New**) | For D1–D3, print every field with its verdict against `TRUTH`. Totals and taxes match within 0.01; dates and invoice numbers must be equal strings | D1–D3 typically score 7 of 7 fields `correct` (with `category_detail` `null` for D1 and D2). D4's tax (35.14) and D5's date (2026-10-05) are present in the documents and are extracted, so null is used only where the document is silent |

### POC 2: `auto`, `any` and a forced tool

**Build:** `poc2_tool_choice.py`, reusing `extraction_setup.py` (`INVOICES`, `RECEIPTS`, `OTHER`, `INVOICE_SCHEMA`). It uses the Messages API directly: `client = anthropic.Anthropic()` and `FORCED_MODEL = "claude-haiku-5-5"`. It defines `RECEIPT_SCHEMA`, `METADATA_SCHEMA`, `TOOLS`, `INBOX = ["D1", "D4", "R1", "N1"]`, `MODES` and `check_input(data, schema)`, which returns a list of problems: a missing required key, an unknown key, a value of the wrong type (allowing `null` only where the schema lists it) or a value outside an `enum`.

```python
RECEIPT_SCHEMA = {"type": "object", "additionalProperties": False,
                  "properties": {"merchant": {"type": "string"}, "total_amount": {"type": "number"},
                                 "payment_method": {"type": "string", "enum": ["card", "cash", "unclear", "other"]},
                                 "purchase_date": {"type": ["string", "null"]}},
                  "required": ["merchant", "total_amount", "payment_method"]}
METADATA_SCHEMA = {"type": "object", "additionalProperties": False,
                   "properties": {"document_type": {"type": "string", "enum": ["invoice", "receipt", "unclear", "other"]},
                                  "document_type_detail": {"type": ["string", "null"]},
                                  "sender": {"type": ["string", "null"]}},
                   "required": ["document_type"]}
TOOLS = [  # strict: True on every tool (E2)
    {"name": "extract_invoice", "strict": True, "input_schema": INVOICE_SCHEMA,
     "description": "Records a supplier invoice: a bill Fernway Outfitters must pay. Use it for invoices and statements that ask for payment."},
    {"name": "extract_receipt", "strict": True, "input_schema": RECEIPT_SCHEMA,
     "description": "Records a receipt for a purchase that was already paid at the point of sale."},
    {"name": "extract_metadata", "strict": True, "input_schema": METADATA_SCHEMA,
     "description": "Records a document's type and sender: the mandatory first step for every inbox document, before any type-specific extraction."},
]
MODES = {"auto": {"type": "auto"}, "any": {"type": "any"}, "forced": {"type": "tool", "name": "extract_metadata"}}
```

For each mode and each `INBOX` document (3 × 4 = 12 calls), it calls `client.messages.create(model=FORCED_MODEL, max_tokens=2048, system="You are the inbox assistant of the Fernway Outfitters accounts-payable team.", tools=TOOLS, tool_choice=MODES[mode], messages=[{"role": "user", "content": f"New document in the accounts inbox:\n\n{text}"}])` and prints the mode, the document, `stop_reason`, the content block types in order, and for a `tool_use` block its name and `check_input()` result. It sends no `tool_result` back: each call is one response.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| E1 | The Agent SDK has no `tool_choice`, and Opus 5.5, Sonnet 5.5 and Fable 5.1 reject `any` and `tool` | The same constraint as `03-revised-Tool-Distribution-&-Tool-Choice.md` E1: `ClaudeAgentOptions` has no `tool_choice` field, and the Messages API answers `any` and `tool` with a 400 error on those models. So `poc2_tool_choice.py` uses the `anthropic` package and `FORCED_MODEL = "claude-haiku-5-5"`, which accepts all four modes. Haiku 5.5 thinks by default, and a forced call skips thinking | Code review: no `tool_choice` in any SDK code, and every POC 2 call uses `FORCED_MODEL` |
| E2 | `strict: true` makes a guaranteed call schema-valid as well | `any` guarantees that a tool is called, not that its input fits the schema. `strict: True` on each tool turns on grammar-constrained sampling for tool inputs, which needs `additionalProperties: False` on every object. The 3 schemas together have 7 optional parameters and 7 nullable (union-type) parameters, within the documented limits of 24 and 16 | Every `tool_use` input in all 12 calls gets `check_input() == []` |
| C7 | `tool_choice: auto` lets the model reply conversationally instead of calling a tool, so it gives no guaranteed structured output and is unsuitable when you need it (**Builds on** `03-revised-Tool-Distribution-&-Tool-Choice.md` C8) | Run the `auto` mode over the 4 documents and print, for each, whether the response contains a `tool_use` block or only `text` (and `thinking`) blocks. New compared with 02/03 C8: here the pipeline *needs* a record for every document, so a text reply is a failure, not a valid answer | Typically at least 1 of 4 responses has no `tool_use` block and `stop_reason == "end_turn"`: almost always N1, which Claude describes in text. That response gives the pipeline nothing to store |
| C8 | `tool_choice: any` guarantees a tool call but lets the model choose which tool: the right setting when the document type is unknown (**Builds on** `03-revised-Tool-Distribution-&-Tool-Choice.md` C8) | Run the `any` mode. Print which tool each document got. New compared with 02/03 C8: three extraction schemas compete, one per document type, and the inbox mixes the types | 4 of 4 responses call a tool. Typically D1 and D4 get `extract_invoice`, R1 gets `extract_receipt`, and N1 gets `extract_metadata` with `document_type` `other` |
| C9 | Every `any` response has `stop_reason` `tool_use` and a valid, schema-conforming tool call, with no text-only responses (**Builds on** `03-revised-Tool-Distribution-&-Tool-Choice.md` C8) | For the `any` mode, assert `stop_reason == "tool_use"`, that the first content block is a `tool_use` (the API prefills the tool call, so no text comes before it) and that `check_input()` returns `[]` against the chosen tool's schema | All 4 asserts pass. New compared with 02/03 C8: the check covers schema validity over a document set, with `strict` (E2) |
| C11 | A forced tool is always called, even when the content suggests another tool would fit better: the model has no flexibility in tool selection (**Builds on** `03-revised-Tool-Distribution-&-Tool-Choice.md` C8) | Run the `forced` mode. D1 is plainly an invoice and R1 plainly a receipt, yet only `extract_metadata` is allowed | 4 of 4 responses call `extract_metadata`, including D1 and R1, each with a `document_type` that typically names its true type |

### Terminal commands (for the later tutorial)

None: every concept in this topic is a programming concept.

### Already covered by earlier POCs

| ID | Concept | Covered in | Check when reused |
|---|---|---|---|
| C6 | The exam tests the distinction between `auto`, `any` and forced `tool_choice` | `03-revised-Tool-Distribution-&-Tool-Choice.md` C8 | POC 2 prints all three modes side by side for the same 4 documents: optional text (`auto`), any one tool (`any`) and the named tool (`forced`) |
| C10 | Forced selection makes a mandatory step run regardless of the model's decision, such as metadata extraction before enrichment | `03-revised-Tool-Distribution-&-Tool-Choice.md` C9 | In the `forced` run, every document's first and only call is `extract_metadata`, the step the tool description calls mandatory |
