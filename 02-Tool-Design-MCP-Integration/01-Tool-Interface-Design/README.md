# Tool Interface Design: beginner POCs (Claude Agent SDK, Python)

Hands-on POCs for **Tool Design & MCP Integration → Tool Interface Design** (Claude Certified Architect – Foundations).
Build spec: `curriculum/02-Tool-Design-&-MCP-Integration/01-revised-Tool-Interface-Design.md`.

## The idea in 30 seconds

```
With no built-in tools and tool search off, Claude picks a tool from two signals only:

   the tool descriptions ──┐
                           ├──► Claude's FIRST tool-calling response ──► get_customer or lookup_order
   the system prompt ──────┘

POC 1: change only the descriptions   "Retrieves customer information."  ──►  5 sentences: purpose, formats,
                                                                             examples, an edge case, a boundary
       the same 10 queries:           typically 6-8 of 10 routed right   ──►  typically 9-10 of 10
POC 2: change only the system prompt  "Always check customer details ..." pulls order questions to get_customer
```

* **Selection happens inside the model:** no code picks the tool, so it can only be measured: score Claude's first
  tool call against an expected tool.
* **A description is the tool's interface:** a vague one fails exactly where two tools seem to fit the question.
* **Rewriting two strings is the cheapest fix:** no code, schema, handler, prompt or model change.
* **The system prompt can undo it:** audit it for trigger words ("always", "first") tied to one tool's vocabulary.

## Files

| File | What it is | Calls the API? |
|---|---|---|
| `routing_setup.py` | Lumen Home's customers and orders, the 2 handlers, `DESCRIPTIONS` (minimal and improved), `build_tools()`, `compare_versions()`, `sentence_count()`, `QUERIES`, the 3 system prompts, `build_routing_options()` and `run_agent()` with `first_response_tools` | – |
| `poc1_descriptions.py` | **POC 1a**: both description versions sentence by sentence, their five elements, and what differs between the versions | No |
| `poc1_selection_test.py` | **POC 1b**: the 10 queries with the minimal, then the improved descriptions | Yes, 2 runs (10 calls each) |
| `poc2_prompt_audit.py` | **POC 2a**: the keyword-conflict audit of the 3 system prompts, with a rewrite per finding | No |
| `poc2_prompt_conflict.py` | **POC 2b**: the 4 order queries under the conflicting and the fixed system prompt | Yes, 2 runs (4 calls each) |
| `common.py` | reads `.env`, sets up logging, logs the model's input and output | – |

## Setup (once)

```bash
cd "02-Tool-Design-MCP-Integration/01-Tool-Interface-Design"
python3 -m venv .venv && source .venv/bin/activate   # Python 3.10+
pip install -r requirements.txt                      # the SDK bundles Claude Code: nothing else to install
cp .env.example .env                                 # then put your API key in .env
```

If `python3 -m venv` says *ensurepip is not available* (Debian/Ubuntu), install the venv package for your
Python version first, e.g. `sudo apt install python3.14-venv`. You can also copy the `.env` from an earlier POC folder.

## Run (in this order)

```bash
python poc1_descriptions.py      # free: 1 vs 5 sentences, 0 vs 5 elements, only the 2 description strings differ
python poc1_selection_test.py    # 2 runs: the 10 queries with the minimal, then the improved descriptions
python poc2_prompt_audit.py      # free: BASE_PROMPT 0 findings, CONFLICT_PROMPT 2, FIXED_PROMPT 0
python poc2_prompt_conflict.py   # 2 runs: the 4 order queries under the conflicting, then the fixed prompt
```

What one run can't show: tool selection varies from run to run. One pass shows the typical gap, but if fewer than 2
queries misroute with the minimal descriptions, rerun `poc1_selection_test.py` once. With dozens of overlapping
tools, as in real MCP setups, vague descriptions misroute far more often.

## Reading the log

The log shows only what goes **into** the model and what comes **out** of it, plus one score line per query.
Each run is also saved to `logs/<script>_<date>_<time>.log`, so you can re-read it without paying again.

Example from POC 1b, a misroute with the minimal descriptions (illustrative: your ids, timings and wording will differ):

```
12:40:26  MODEL INPUT   prompt       Who placed order ORD-8810?
12:40:28  MODEL OUTPUT  thinking     The user wants to know who placed an order: that is customer information.
12:40:28  MODEL OUTPUT  tool_use     mcp__lumen__get_customer {'identifier': 'ORD-8810'}  (id=toolu_A1)
12:40:28  MODEL INPUT   tool_result  [{'type': 'text', 'text': "No customer matches 'ORD-8810'."}]  (tool_use_id=toolu_A1, is_error=True)
12:40:30  MODEL OUTPUT  tool_use     mcp__lumen__lookup_order {'identifier': 'ORD-8810'}  (id=toolu_A2)
12:40:30  MODEL INPUT   tool_result  [{'type': 'text', 'text': '{"order_id": "ORD-8810", "customer_id": "CUST-2077", "customer_name": "Sam Okafor", ...}'}]  (tool_use_id=toolu_A2, is_error=None)
12:40:32  MODEL OUTPUT  text         Order ORD-8810 was placed by Sam Okafor (CUST-2077).
12:40:32  MODEL OUTPUT  stop_reason  end_turn  (loop result: success)
12:40:32  [minimal] #5 expected lookup_order, first response called ['get_customer'] -> MISROUTED (overlap query)
...
12:41:40  Accuracy 7/10 -> 10/10, fixed queries [4, 5, 9]. Changed: 2 description strings; no code, schema, handler, prompt or model
```

* A misroute costs a wasted round trip: the wrong tool's `No ... matches` error, then the right tool. The answer is
  still right, which is why only the first response is scored.
* Misroutes fall on overlap queries (3, 4, 5, 6, 8, 9). The controls (1, 2, 7, 10) stay correct in both passes.
* In POC 2b, compare the `get_customer called` values of the two arms: the descriptions are the same in both.

## Concept map (IDs from the build spec)

| ID | Concept | Where you see it |
|---|---|---|
| C1 | Two MCP tools with vague one-sentence descriptions and no formats, examples or boundaries | `DESCRIPTIONS["minimal"]`, `IDENTIFIER_SCHEMA` and `build_routing_server()` in `routing_setup.py`; `python poc1_descriptions.py` |
| C2 | Reproduce a misroute first-hand | POC 1b log, `minimal` pass: a wrong `tool_use`, its `No ... matches` error (`is_error=True`), then the right tool |
| C3 | Ambiguous descriptions are the root cause of selection errors | the `MISROUTED (overlap query)` lines: misroutes fall in `OVERLAP` (`poc1_selection_test.py`), never on a control |
| C4 | Test with 10 queries and log the tool chosen for each | `QUERIES` in `routing_setup.py`; one `[<version>] #n expected ..., first response called ...` line per query |
| C5 | Selection accuracy before and after, as numbers | log lines `Selection accuracy (minimal): k/10` and `Selection accuracy (improved): k/10` |
| C6 | The baseline shows at least 2-3 misroutes, in either direction | the `MISROUTED` lines of the `minimal` pass: order queries sent to `get_customer`, customer queries to `lookup_order` |
| C7 | Rewrite with five elements: purpose, formats, examples, edge cases, boundaries | `DESCRIPTIONS["improved"]`; `check_description()` in `poc1_descriptions.py`: all 5 ✅ for both tools |
| C8 | The rewrite is the lowest-effort, highest-leverage fix | closing log line `Changed: 2 description strings; no code, schema, handler, prompt or model` |
| C9 | Production shape: 3-5 sentences, formats, examples, a "Do NOT use ..." boundary | `python poc1_descriptions.py`: 5 sentences each; sentence 2 holds the formats, 3 the examples, 5 the boundary |
| C10 | Re-run the same 10 queries: 9-10 of 10, the misroutes fixed | `RUNS` in `poc1_selection_test.py`; closing log line `fixed queries [...]` |
| C11 | Same names, schema, handlers, prompt, model and options: the description is the root cause | `compare_versions()` returns `['get_customer.description', 'lookup_order.description']`; both passes use `build_routing_options()` |
| C12 | Review the system prompt for keyword-sensitive instructions | `audit_prompt()` in `poc2_prompt_audit.py`: 0, 2 and 0 findings |
| C13 | Prompt keywords can override well-written descriptions | POC 2b: `Arm conflict: k of 4 ... called get_customer` against `Arm fixed: 0 of 4`, with the same improved descriptions |
| C14 | Each flagged phrase, the tool it pulls toward, and a rewrite | `python poc2_prompt_audit.py`: phrase -> tool, the sentence and its rewrite (`REWRITES` in `routing_setup.py`) |
| E1 | Score the first tool choice, not the answer | `correct = run["first_response_tools"] == [...]` in `evaluate()`; `first_response_tools` in `run_agent()` |
| E2 | Tool search off, so the first tool call is a routing choice | `env={"ENABLE_TOOL_SEARCH": "false"}` in `build_routing_options()` |

## Settings (`.env`)

* `MODEL_ID`: the model that picks the tools (default `claude-sonnet-5-5`).
* `MAX_BUDGET_USD`: the SDK stops any single `query()` call whose estimated spend passes this (default `0.50`).
