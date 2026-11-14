# Structured Output with Tool Use: beginner POCs (Claude Agent SDK + Messages API, Python)

Hands-on POCs for **Prompt Engineering & Structured Output → Structured Output with Tool Use** (Claude Certified Architect – Foundations).
Build spec: `curriculum/04-Prompt-Engineering-Structured-Output/03-revised-Structured-Output-with-Tool-Use.md`.

## The idea in 30 seconds

```
POC 1 (Agent SDK, output_format = structured output through the StructuredOutput tool):
   5 invoices ──► naive schema    (every field required, no null)      ──► absent fields get INVENTED values
              └─► nullable schema (3 required, 3 nullable, unclear/other) ──► absent fields come back null

POC 2 (Messages API, 3 extraction tools, 4 inbox documents):
   tool_choice auto    ──► a tool call ... or a text reply   (no guarantee)
   tool_choice any     ──► always a tool call, Claude picks which one
   tool_choice tool    ──► always extract_metadata, even for an obvious invoice
```

* **Schema design prevents fabrication:** a required field with no `null` leaves Claude two choices when the
  document is silent, invent or fail. Optional, nullable fields allow the honest answer.
* **`unclear` and `other`** (with a detail field) stop a closed category list from forcing a wrong category.
* **`auto` doesn't guarantee structured output; `any` does; a forced tool guarantees one specific step.**
  `strict: true` makes the guaranteed call schema-valid too.
* **The Agent SDK has no `tool_choice`:** its tool calls are always `auto`, and its guarantee is `output_format`.
  Opus 5.5, Sonnet 5.5 and Fable 5.1 reject `any` and `tool` with a 400 error, so POC 2 uses `claude-haiku-5-5`.

## Files

| File | What it is | Calls the API? |
|---|---|---|
| `extraction_setup.py` | the documents and `TRUTH`, `INVOICE_SCHEMA` and `NAIVE_SCHEMA`, `build_extract_options()`, `extract()` and `score()` | – |
| `poc1_schema_design.py` | **POC 1**: the same 5 invoices with the naive and the nullable schema (Agent SDK) | Yes, 2 runs (5 calls each) |
| `poc2_tool_choice.py` | **POC 2**: `auto`, `any` and a forced tool on 4 inbox documents (Messages API, `claude-haiku-5-5`) | Yes, 3 runs (4 calls each) |
| `common.py` | reads `.env`, sets up logging, logs the model's input and output (SDK messages and Messages API responses) | – |

The documents: D1–D3 are complete invoices; **D4** has no invoice number and no date; **D5** has no invoice number,
no tax, and doesn't say what was bought (`unclear`); D3 is pest control (`other`). POC 2 adds a café receipt (R1) and
a supplier newsletter (N1).

## Setup (once)

```bash
cd "04-Prompt-Engineering-Structured-Output/03-Structured-Output-with-Tool-Use"
python3 -m venv .venv && source .venv/bin/activate   # Python 3.10+
pip install -r requirements.txt                      # the Agent SDK (bundles Claude Code) and anthropic for POC 2
cp .env.example .env                                 # then put your API key in .env
```

If `python3 -m venv` says *ensurepip is not available* (Debian/Ubuntu), install the venv package for your
Python version first, e.g. `sudo apt install python3.14-venv`. You can also copy the `.env` from an earlier POC folder.

## Run (in this order)

```bash
python poc1_schema_design.py   # 2 runs: the naive schema, then the nullable schema (5 invoices each)
python poc2_tool_choice.py     # 3 runs: auto, any, forced (4 inbox documents each)
```

## Reading the log

The log shows only what goes **into** the model and what comes **out** of it. In POC 1, `structured` is the JSON
Claude hands in through the `StructuredOutput` tool; in POC 2, `tool_use` is the extraction tool Claude called and
`stop_reason ... (Messages API)` closes each response. Each run is also saved to `logs/<script>_<date>_<time>.log`.

Example lines (illustrative: your values will differ):

```
22:01:12  naive    D4: vendor_name=correct total_amount=correct category=correct invoice_number=invented('N/A') invoice_date=invented('2026-09-30') tax_amount=correct
22:01:30  naive    totals: 4 of 4 absent fields invented, 2 of 5 categories wrong
22:01:51  nullable D4: vendor_name=correct total_amount=correct category=correct invoice_number=null invoice_date=null tax_amount=correct category_detail=correct
22:01:58  nullable totals: 0 of 4 absent fields invented, 0 of 5 categories wrong
22:03:04  MODEL OUTPUT  text         This is a Kestrel Supply newsletter about their autumn catalogue; nothing to pay.
22:03:04  MODEL OUTPUT  stop_reason  end_turn  (Messages API)
22:03:04  auto   3/4 called a tool [...]; text only: ['N1']; schema problems: 0
22:03:09  any    4/4 called a tool [..., 'N1->extract_metadata']; text only: none; schema problems: 0
```

* With the naive schema the absent fields are filled **by construction**: the SDK's validator rejects `null`, so
  Claude writes a placeholder or a plausible value. Either one looks like data downstream.
* Under `auto`, a document Claude finds no tool for gets a text reply: nothing to store. Under `any`, every
  document gets a tool call; the `first block tool_use` part shows the API prefilled the call (no text before it).
* Under `forced`, D1 (plainly an invoice) still gets `extract_metadata`: no flexibility, by design.

## Concept map (IDs from the build spec)

| ID | Concept | Where you see it |
|---|---|---|
| C1 | An extraction tool with a JSON schema: 3 required, 3 nullable, an enum with `unclear`/`other`, a detail field | `INVOICE_SCHEMA` in `extraction_setup.py` (POC 1's `output_format`; POC 2's `extract_invoice`) |
| C2 | Schema design prevents fabrication: the root-cause fix | POC 1 totals lines, then `Same documents, prompt, model and options: only the schema changed` |
| C3 | Required fields pressure the model to invent absent values | `NAIVE_SCHEMA`; POC 1 lines `naive D4/D5: ... invented(...)` |
| C4 | Nullable optional fields allow honest `null`; `required` lists only the always-present fields | `INVOICE_SCHEMA` `required` and `["string", "null"]` types; lines `nullable D4/D5: ... null` |
| C5 | An enum with `unclear` and `other`, plus a detail field for `other` | `category` and `category_detail` in `INVOICE_SCHEMA`; D3 `other`, D5 `unclear` in the nullable lines |
| C6 | The exam tests `auto` vs `any` vs forced (already covered) | `03-revised-Tool-Distribution-&-Tool-Choice.md` C8 (domain 02, no POC folder yet); here the 3 summary lines of POC 2 side by side |
| C7 | `auto` may reply in text: no guaranteed structured output | POC 2 line `auto ... text only: ['N1']` and its `MODEL OUTPUT text` line |
| C8 | `any` guarantees a call and lets Claude pick the tool: right when the type is unknown | POC 2 line `any 4/4 called a tool [...]` with a different tool per document type |
| C9 | Every `any` response: `stop_reason tool_use`, a schema-valid call, no text first | `any` lines: `first block tool_use, schema problems none`; `stop_reason tool_use (Messages API)` |
| C10 | A forced tool makes a mandatory first step run (already covered) | `03-revised-Tool-Distribution-&-Tool-Choice.md` C9; here every `forced` call is `extract_metadata` |
| C11 | A forced tool is called even when another fits better | POC 2 line `forced D1: extract_metadata` (D1 is plainly an invoice) |
| C12 | 5 documents, 2 with missing fields: nullable fields return `null`, not invented values | POC 1 `nullable D4` and `nullable D5` lines: `null` where the document is silent |
| C13 | Complete documents fully correct; no invented dates, amounts or identifiers | POC 1 `nullable D1`–`D3` lines all `correct`; `nullable totals: 0 of 4 absent fields invented` |
| E1 | No `tool_choice` in the Agent SDK; Opus/Sonnet 5.5 and Fable 5.1 reject `any`/`tool` | `FORCED_MODEL = "claude-haiku-5-5"` and the `anthropic` client in `poc2_tool_choice.py` |
| E2 | `strict: true` makes a guaranteed call schema-valid | `"strict": True` on every tool in `TOOLS`; `check_input()`; `additionalProperties: False` in the schemas |

## Settings (`.env`)

* `MODEL_ID`: the model for POC 1's extractions (default `claude-sonnet-5-5`). POC 2 always uses `claude-haiku-5-5`,
  set in `poc2_tool_choice.py` as `FORCED_MODEL`, because the 5.5 Opus/Sonnet models reject forced tool use.
* `MAX_BUDGET_USD`: the SDK stops any single POC 1 call whose estimated spend passes this (default `0.50`).
* `MAX_TURNS`: the safety cap on turns per POC 1 call, with room for schema retries (default `10`).
