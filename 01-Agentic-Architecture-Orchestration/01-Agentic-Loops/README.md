# Agentic Loops: beginner POCs (Claude Agent SDK, Python)

Hands-on POCs for **Agentic Architecture & Orchestration → Agentic Loops** (Claude Certified Architect – Foundations).
Build spec: `curriculum/01-Agentic-Architecture-&-Orchestration/01-revised-Agentic-Loops.md`.

## The idea in 30 seconds

An **agent** is Claude working in a loop:

```
your prompt ──► Claude ──"I need a tool"──► tool_use ──► the SDK runs YOUR function ──► tool_result ──┐
                  ▲                                                                                     │
                  └───────────────────────── result added to the conversation ◄─────────────────────────┘

                Claude ──"I'm done"──► final text ──► ResultMessage (subtype=success, stop_reason=end_turn)
```

* **Claude decides** which tool to call, in which order, and when to stop.
* **The Agent SDK runs the loop**: it calls Claude, runs your tool, feeds the result back, and repeats.
* **Your code** defines the tools, sets the limits, and reads the stream of messages.
* **"Done" is a signal, not text**: only the `ResultMessage` tells you the loop has ended.

## Files

| File | What it is | Calls the API? |
|---|---|---|
| `tools.py` | the 2 tools (calculator, web_search stub) and `build_options()` | – |
| `poc1_round_trip.py` | **POC 1**: one tool round-trip per prompt | Yes, 3 short runs |
| `poc2_exit_signal.py` | **POC 2a**: why text can't tell you the agent is done (replays a recorded stream) | No |
| `poc2_agent_loop.py` | **POC 2b**: a multi-step loop, its end signal and its safety cap | Yes, 3 short runs |
| `common.py` | reads `.env`, sets up logging, logs the model's input and output | – |

## Setup (once)

```bash
cd "01-Agentic-Architecture-&-Orchestration/01-Agentic-Loops"
python3 -m venv .venv && source .venv/bin/activate   # Python 3.10+
pip install -r requirements.txt                      # the SDK bundles Claude Code: nothing else to install
cp .env.example .env                                 # then put your API key in .env
```

If `python3 -m venv` says *ensurepip is not available* (Debian/Ubuntu), install the venv package for your
Python version first, e.g. `sudo apt install python3.14-venv`.

## Run (in this order)

```bash
python poc1_round_trip.py     # 3 runs: math → calculator, share price → web_search, definition → no tool
python poc2_exit_signal.py    # free: first text ❌, "final answer" phrase ❌, ResultMessage ✅
python poc2_agent_loop.py     # 3 runs: no tool, search → calculate, the same task with max_turns=1
```

Optional extras are commented out at the top of each script: a failing tool call (`is_error=True`) in
`poc1_round_trip.py`, and two tool calls in one response in `poc2_agent_loop.py`.

## Reading the log

The log shows only what goes **into** the model and what comes **out** of it. The code shows the rest of the
flow. Each run is also saved to `logs/<script>_<date>_<time>.log`, so you can re-read it without paying again.

Example from POC 1 (illustrative: your ids, timings and wording will differ):

```
17:20:01  MODEL INPUT   prompt       What is 1,234 multiplied by 5,678?
17:20:04  MODEL OUTPUT  thinking     The user wants 1,234 × 5,678. I'll use the calculator.
17:20:04  MODEL OUTPUT  tool_use     mcp__poc__calculator {'expression': '1234 * 5678'}  (id=toolu_A1)
17:20:04  MODEL INPUT   tool_result  [{'type': 'text', 'text': '7006652'}]  (tool_use_id=toolu_A1, is_error=None)
17:20:06  MODEL OUTPUT  text         1,234 × 5,678 = **7,006,652**.
17:20:06  MODEL OUTPUT  stop_reason  end_turn  (loop result: success)
```

* The `tool_use` id comes back as the `tool_result`'s `tool_use_id`: your handler ran in between.
* The tool result is the model's next **input**: that is the loop.
* The capped run in POC 2 ends with `stop_reason tool_use (loop result: error_max_turns)` and a
  `Safety cap hit` warning: Claude still wanted a tool, but the loop was stopped.

## Concept map (IDs from the build spec)

| ID | Concept | Where you see it |
|---|---|---|
| C1 | An Agent SDK session: `query()` + `async for` + `asyncio.run()` | `run()` in `poc1_round_trip.py` |
| C2 | A tool = name + description + JSON Schema, registered with Claude | `@tool(...)` and `create_sdk_mcp_server` in `tools.py` |
| C3 | Calculator + web-search stub | `calculator` and `web_search` in `tools.py` |
| C4 | Claude picks the tool (or none) | POC 1 log: `tool_use` calculator / web_search / none; no tool-choosing code exists |
| C5 | The agent loop, run by the SDK | `run_agent()`: one `query()` call, no `while` |
| C6 | `stop_reason` is the deterministic signal | log line `MODEL OUTPUT  stop_reason  end_turn` |
| C7 | Text is an unreliable completion signal | `python poc2_exit_signal.py`: ❌ ❌ ✅ |
| C8 | Claude's `tool_use` request | log line `MODEL OUTPUT  tool_use … (id=X)` |
| C9 | The SDK runs your handler | the `tool_result` carries your handler's return value; no code in `run()` calls a tool |
| C10 | The result goes back with the same id | log line `MODEL INPUT  tool_result … (tool_use_id=X)` |
| C11 | The SDK keeps the history (the API is stateless) | no history code anywhere; see the `run()` docstring |
| C12 | `end_turn` means finished | `subtype == "success" and stop_reason == "end_turn"` in `run()` |
| C13 | Extract the final text | `run()` returns `ResultMessage.result` |
| C14 | Sequential calls: the search result feeds the calculation | POC 2 log: the calculator's input contains `187.42`, which only the search returned |
| C15 | Full lifecycle | POC 2 log: web_search → tool_result → calculator → tool_result → text → `end_turn` |
| C16 | Safety cap: a limit plus a warning | POC 2 capped run: `error_max_turns`, `Safety cap hit`, no answer |
| C17 | The cap is a fallback, never the main stop | POC 2: the normal run ends with `end_turn` long before `max_turns=20` |
| E1 | Several tool calls in one response | `readOnlyHint=True` in `tools.py`; optional prompt in `poc2_agent_loop.py` |
| E2 | Other endings | `run_agent()` returns `None` for anything but success + end_turn |
| E3 | Read blocks by type, not position | `isinstance` checks in `log_model_io()` (`common.py`) |
| E4 | A failed tool still returns a result | `is_error: True` in `calculator`; optional prompt in `poc1_round_trip.py` |

## Settings (`.env`)

* `MODEL_ID`: the model (default `claude-sonnet-5-5`).
* `MAX_BUDGET_USD`: the SDK stops any single run whose estimated spend passes this (default `0.50`).
* `MAX_TURNS`: POC 2's safety cap (default `20`).
