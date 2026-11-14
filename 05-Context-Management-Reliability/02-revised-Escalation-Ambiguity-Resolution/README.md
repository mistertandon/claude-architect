# Escalation and Ambiguity Resolution: beginner POCs (Claude Agent SDK, Python)

Hands-on POCs for **Context Management & Reliability → Escalation and Ambiguity Resolution** (Claude Certified Architect – Foundations).
Build spec: `curriculum/05-Context-Management-Reliability/02-revised-Escalation-Ambiguity-Resolution.md`.

## The idea in 30 seconds

```
customer message ──► support agent ──┬── resolve    frustrated but simple? answer it. A documented "no"? give it
                                     ├── escalate   escalate_to_human(trigger): an explicit human request (at once,
                                     │              before any lookup), a policy gap, or no progress
                                     └── ask        2+ customers share the name? find_customer returns no account
                                                    data: ask for an email, phone number, order number or postcode

where each rule lives:   escalation = in the PROMPT (criteria + 3 examples): a judgment call, calibrated first
                         ambiguity  = in CODE (match_customer()): no prompt and no heuristic can open an account
```

* **Escalate on triggers, not feelings:** an explicit human request, a policy gap, or no progress. Frustration and
  the agent's own low confidence are named anti-patterns.
* **Gap or violation:** the policy is silent → escalate; a policy rule says no → give that documented answer.
* **Prompt first, infrastructure later:** the A/B changes only the system prompt. No classifier, no sentiment model,
  no confidence threshold.
* **Two absolute rules:** never investigate before honouring a request for a human; never pick one of several
  matching customers.

## Files

| File | What it is | Calls the API? |
|---|---|---|
| `escalation_setup.py` | Lumen Home's 4 customers (2 named Alex Morgan) and 4 orders, `match_customer()`, `EscalationSession`, the 3 tools, `NAIVE_PROMPT` and `ESCALATION_PROMPT` (policy, criteria, identity rule, 3 examples), `build_escalation_options()` and `run_agent()` | – |
| `poc1_heuristics.py` | **POC 1a**: the account "most recent" and "most active" would open for each Alex Morgan, and how `match_customer()` asks instead | No |
| `poc1_escalation.py` | **POC 1b**: 5 scenarios with the naive and with the escalation prompt, then 5 stress phrasings of the absolute rules | Yes, 3 runs (5 calls each) |
| `common.py` | reads `.env`, sets up logging, logs the model's input and output | – |

`run_agent()` and its `first_response_tools` (the tools of Claude's first tool-calling response) are copied from
`02-Tool-Design-MCP-Integration/01-Tool-Interface-Design/routing_setup.py`.

## Setup (once)

```bash
cd "05-Context-Management-Reliability/02-revised-Escalation-Ambiguity-Resolution"
python3 -m venv .venv && source .venv/bin/activate   # Python 3.10+
pip install -r requirements.txt                      # the SDK bundles Claude Code: nothing else to install
cp .env.example .env                                 # then put your API key in .env
```

If `python3 -m venv` says *ensurepip is not available* (Debian/Ubuntu), install the venv package for your
Python version first, e.g. `sudo apt install python3.14-venv`. You can also copy the `.env` from an earlier POC folder.

## Run (in this order)

```bash
python poc1_heuristics.py    # free: each heuristic opens someone else's account for one caller; one identifier is enough
python poc1_escalation.py    # 3 runs: S1-S4 + V with the naive prompt, the same with the escalation prompt, H1-H4 + A1
```

What one run can't show:
* **Rule 1 lives in the prompt**, so a run can only show that it held on the phrasings tried: 5 here. A `CRITICAL`
  line there calls for better examples or criteria wording, not a classifier.
* **Rule 2 lives in the matching function**, so no account data can leave an ambiguous search under either prompt.
  If Claude asks for an identifier before it searches at all, S4 or A1 shows `move resolve` with no account opened:
  the rule held but the matcher wasn't exercised, so rerun once.
* The naive arm varies from run to run: typically 2-4 of 5 correct, most often failing S1 (and S3 when it looks the
  order up first).

## Reading the log

The log shows only what goes **into** the model and what comes **out** of it, plus one score line per message.
Each run is also saved to `logs/<script>_<date>_<time>.log`, so you can re-read it without paying again.

Example (illustrative: your ids, timings and wording will differ):

```
10:14:02  MODEL INPUT   prompt       Hello. The Aurora desk lamp from order ORD-7731 arrived with a cracked shade. I'd like to speak to a human agent about it, please.
10:14:04  MODEL OUTPUT  thinking     The customer explicitly asks for a human agent: trigger 1, escalate now, before any lookup.
10:14:04  MODEL OUTPUT  tool_use     mcp__lumen__escalate_to_human {'trigger': 'explicit_human_request', 'reason': 'Customer asked for a human agent about a cracked shade on ORD-7731.'}  (id=toolu_B1)
10:14:04  MODEL INPUT   tool_result  [{'type': 'text', 'text': 'Escalation ESC-0001 queued: a human agent will take over this conversation.'}]  (tool_use_id=toolu_B1, is_error=None)
10:14:06  MODEL OUTPUT  text         Of course. I've passed you to a member of our team, who will take it from here.
10:14:06  MODEL OUTPUT  stop_reason  end_turn  (loop result: success)
10:14:06  S3 [escalation]: first response ['escalate_to_human']; move escalate/explicit_human_request after 0 call(s); accounts opened []; expected escalate/explicit_human_request -> correct
...
10:13:20  S1 [naive]: first response ['escalate_to_human']; move escalate/other after 0 call(s); accounts opened []; expected resolve -> WRONG
...
10:13:31  Arm naive: 3 of 5 correct moves; first-contact resolution 2/3; over-escalations 1; missed escalations 0
```

* S3: although P2 covers a cracked shade and `lookup_order` was available, the escalation is the first and only
  tool call. In the naive arm, a lookup before it gives a `CRITICAL S3 [naive]` line.
* S1 and H4 are both frustrated customers: only H4 asks for a person, so only H4 escalates.
* S4 and A1: `find_customer` returns `"status": "ambiguous"` with no account data, and the reply asks for an
  identifier. `accounts opened []` stays empty.

## Concept map (IDs from the build spec)

| ID | Concept | Where you see it |
|---|---|---|
| C1 | Explicit criteria covering the three valid triggers | `CRITERIA` in `escalation_setup.py`; the `trigger` enum of `escalate_to_human` (the 3 triggers + `other`) |
| C2 | Criteria in the prompt come before classifiers or sentiment analysis | `RUNS` in `poc1_escalation.py`: only `system_prompt` changes; `Arm naive: k of 5` against `Arm escalation: 5 of 5` |
| C3 | The two anti-patterns, sentiment and confidence, listed to avoid | the `NEVER escalate` list in `CRITERIA`; `NAIVE_RULE` writes them as the rule; naive S1 escalates with trigger `other` |
| C4 | A numbered list: trigger, description and action for each | `CRITERIA` items `1.`-`3.`, each with `Description:` and `Action:` |
| C5 | Policy gaps escalate; violations have documented answers | trigger 2 of `CRITERIA`, P3 and P4 of `POLICY`; log lines S2 (`escalate/policy_gap`) and V (`resolve` after `lookup_order` shows `final_sale: true`) |
| C6 | Three few-shot examples: human request, frustrated but simple, policy gap | `EXAMPLES` and `examples_block()` at the end of `ESCALATION_PROMPT` |
| C7 | Examples fix poor first-contact resolution | the `Arm ...: first-contact resolution k/3; over-escalations; missed escalations` lines |
| C8 | Each example shows the message, the reasoning and the action (already covered) | `<reasoning>` between `<customer>` and `<action>` in each example; taught in `04-Prompt-Engineering-Structured-Output/02-Few-Shot-Prompting` |
| C9 | The frustrated example acknowledges the frustration and resolves directly | example 2 of `EXAMPLES`; S1's reply: an apology, tracking `LH-55120988` and the new estimate |
| C10 | Frustrated with a simple issue → resolve; asks for a human → escalate | log lines `S1 [escalation]` (first response `lookup_order`) and `H4 [stress]` (first response `escalate_to_human`) |
| C11 | Ambiguous matching asks for identifiers instead of picking | `match_customer()`; `python poc1_heuristics.py`; S4 and A1 lines: `move ask; accounts opened []` |
| C12 | Heuristic selection (most recent, most active) risks privacy and wrong actions | `most_recent()` and `most_active()` in `poc1_heuristics.py`: 2 of 4 picks open another customer's account |
| C13 | Suggest identifier types and let the customer choose | `ask_for` in the ambiguous result and `IDENTITY_RULE`; `python poc1_heuristics.py`: each identifier alone gives one match |
| C14 | Four scenarios: frustrated, policy exception, human request, ambiguous match | `SCENARIOS` S1-S4 in `poc1_escalation.py`; one line per message |
| C15 | Scenario 3: escalate immediately, with no investigation and no "let me try first" | `check_human_request()`; `S3 [escalation]: first response ['escalate_to_human'] ... after 0 call(s)` |
| C16 | The frustrated scenario must NOT escalate | `S1 [escalation]: ... move resolve` against `S1 [naive]: ... move escalate/other` |
| C17 | The two absolute rules, with no exceptions | `CRITICAL` warnings; closing line `Absolute rules, escalation prompt: rule 1 (in the prompt) ... rule 2 (in the matching function) ...` |
| C18 | Several phrasings of a human request: escalate in the first response, zero investigation | `STRESS` H1-H4 and `check_human_request()`; their lines `first response ['escalate_to_human'] ... after 0 call(s)` |
| C19 | Ambiguous matches: always ask, even when one record seems likelier | A1 (Portland, last week: both point at CUST-3101) and `check_ambiguity()`: no escalation, no opened account, no guessed identifier |
| E1 | A policy-violation control | `V` in `SCENARIOS` |
| E2 | Tool search off, so the first tool call is a decision | `env={"ENABLE_TOOL_SEARCH": "false"}` in `build_escalation_options()` |

## Settings (`.env`)

* `MODEL_ID`: the model that runs the support agent (default `claude-sonnet-5-5`).
* `MAX_BUDGET_USD`: the SDK stops any single `query()` call whose estimated spend passes this (default `0.50`).
