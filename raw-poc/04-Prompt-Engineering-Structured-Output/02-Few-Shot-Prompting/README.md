# Few-Shot Prompting: beginner POC (Claude Agent SDK, Python)

Hands-on POC for **Prompt Engineering & Structured Output → Few-Shot Prompting** (Claude Certified Architect – Foundations).
Build spec: `curriculum/04-Prompt-Engineering-Structured-Output/02-revised-Few-Shot-Prompting.md`.

## The idea in 30 seconds

```
5 invoices: 2 tables, 2 letters, 1 mixed ──► the same detailed instructions, 3 ways ──► one extraction per document
                                              base      no examples
                                              pairs     + 3 examples (document -> extraction)
                                              few-shot  + the same 3 examples WITH their reasoning
then:  failure table by structure (diagnose)  ──►  comparison  ──►  decision matrix (what examples can't fix)
```

* **Diagnose before you prescribe:** the base arm's failures, by field and document structure, say what the
  examples must show (dates and numbers in words, free items, items in notes, DD/MM dates, relative due dates).
* **Examples beat more instructions** for consistency across varied structures, and **examples with reasoning**
  teach the rule behind each decision, not just its surface.
* **Examples can't fix everything:** a missing value (the schema has no `null`), a sum that is wrong in the source,
  and malformed JSON each need another technique (topics 03 and 04).

## Files

| File | What it is | Calls the API? |
|---|---|---|
| `fewshot_setup.py` | the 5 documents and `TRUTH`, `EXTRACTION_SCHEMA`, `BASE_PROMPT`, the 3 `EXAMPLES`, the arm prompts, `extract()` and `score()` | – |
| `poc1_few_shot.py` | **POC 1**: the 3 arms, the failure table, the comparison and the decision matrix | Yes, 3 runs (5 calls each) |
| `common.py` | reads `.env` | – |

The test documents (`DOCUMENTS` in `fewshot_setup.py`):

| Id | Structure | What makes it hard |
|---|---|---|
| T1 | table | nothing: the control |
| T2 | table | the supplier's total (455.00) is 10.00 more than its line items (445.00) |
| N1 | narrative | numbers in words, a "free of charge" item, a due date "within thirty days of the invoice date" |
| N2 | narrative | **no due date anywhere**: the schema has no `null`, so any answer is wrong (the fabrication probe) |
| M1 | mixed | a DD/MM/YYYY date, a billed item in a note under the table, a due date "15 days after the issue date" |

## Setup (once)

```bash
cd "04-Prompt-Engineering-Structured-Output/02-Few-Shot-Prompting"
python3 -m venv .venv && source .venv/bin/activate   # Python 3.10+
pip install -r requirements.txt                      # the SDK bundles Claude Code: nothing else to install
cp .env.example .env                                 # then put your API key in .env
```

If `python3 -m venv` says *ensurepip is not available* (Debian/Ubuntu), install the venv package for your
Python version first, e.g. `sudo apt install python3.14-venv`. You can also copy the `.env` from an earlier POC folder.

## Run

```bash
python poc1_few_shot.py   # 3 runs (base, pairs, few-shot), each extracting the 5 documents: 15 calls
```

Optional extras are commented out in `ARMS`: a second run of each arm. **One run per arm can't show format drift
between runs** (C4's "different output formats across runs"): the SDK has no temperature or seed, so drift only
shows when the same arm runs again, in the `changed between runs` column. With a strong model the base arm may
already be close to 100% on these short documents; the failure table then shows which few cells still fail.

## What to compare

`main_report()` returns the lesson as data: `failure_table`, `diagnosis`, `comparison`, `unseen_patterns`, `matrix`.

* Compare each `base` score with its `few-shot` one: the gain is in the narrative and mixed documents.
* For N2's due date, an empty value and an invented date are both wrong: N2 has no due date, and the schema leaves
  no honest answer.
* The `malformed JSON` matrix row is 0 in every arm because `output_format` already sends the JSON through a tool.

## Concept map (IDs from the build spec)

| ID | Concept | Where you see it |
|---|---|---|
| C1 | A base prompt with detailed instructions and no examples | `BASE_PROMPT` in `fewshot_setup.py`; the `base` arm |
| C2 | A test set of 5 documents: tables, narrative paragraphs, mixed formats | `DOCUMENTS`, `DOC_TYPES` and `TRUTH` in `fewshot_setup.py` |
| C3 | Instructions alone are inconsistent across structures: the trigger for few-shot | `comparison["base"]["by_structure"]` in `main_report()` |
| C4 | Symptoms: right from tables, empty or wrong from narrative, formats drifting between runs | the `base` scores; `iso_dates` and `changed_between_runs` (needs the optional repeat) |
| C5 | Record which fields fail on which structure | `failure_table` in `main_report()` |
| C6 | Diagnose before prescribing: the failures say what the examples must show | `diagnosis` in `main_report()`; each example's reasoning in `EXAMPLES` |
| C7 | 3 examples targeting the failing patterns: table, narrative, mixed | `EXAMPLES` in `fewshot_setup.py` (invoices that are not in the test set) |
| C8 | Each example includes its reasoning | `<reasoning>` in `examples_block(True)`, i.e. `FEWSHOT_PROMPT` |
| C9 | Reasoning generalizes; input/output pairs only match surfaces | the `pairs` arm; `unseen_patterns` in `main_report()` |
| C10 | Re-run the same documents and compare empty fields, format and accuracy | `comparison` per arm: `empty`, `iso_dates`, `accuracy` |
| C11 | Few-shot is the first-choice fix for consistency, ahead of more instructions | every arm prompt starts with `BASE_PROMPT` |
| C12 | Fewer empty fields, better formats, higher accuracy, biggest gain where it failed | `comparison` and `by_structure`: `few-shot` against `base` |
| C13 | A decision matrix: what examples fix and what needs another technique | `matrix` in `main_report()` |
| C14 | Malformed JSON → tool use; fabrication → nullable schema; sum errors → validation loops | the technique in each `matrix` entry |
| C15 | Narrative and format improve; fabrication of missing data does not | `matrix["missing data (N2 due)"]`: empty or invented in every arm |
| E1 | All arms return schema-validated JSON | `output_format` in `build_extract_options()`; returned as `ResultMessage.structured_output` |
| E2 | The schema has no nullable field (the design before topic 03) | `EXTRACTION_SCHEMA`: every field required, no `"null"` type |

## Settings (`.env`)

* `MODEL_ID`: the model for every extraction in every arm (default `claude-sonnet-5-5`).
* `MAX_BUDGET_USD`: the SDK stops any single extraction call whose estimated spend passes this (default `0.50`).
* `MAX_TURNS`: the safety cap on turns per extraction call (default `5`).
