# Agentic Loops: Revised POC Requirements (6 steps → 2 POCs, Claude Agent SDK)

> **Source:** `01-raw-Agentic-Loops.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Agentic Architecture & Orchestration → Agentic Loops · **Build with:** Claude Agent SDK for Python (`claude_agent_sdk`)

---

## 1. Verdict: 2 POCs

The 6 raw steps are not 6 separate concepts. They are 6 build steps of **one small agent**: step 5 tests steps 1–4, and step 6 adds one limit. What you need to learn splits into two mental models:

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: Custom tools and one tool round-trip** | **The message protocol, as the SDK runs it:** how tools are defined and registered, Claude's `ToolUseBlock`, your handler's result coming back as a `ToolResultBlock` with the same id, and the final `ResultMessage` | 1, 3, 4 |
| **POC 2: The agent loop, its end signal and its cap** | **The control flow:** a multi-step task that loops until `stop_reason == "end_turn"`, why only the `ResultMessage` marks completion (never text), and `max_turns=20` as a safety net | 2, 5, 6 (reuses 3, 4) |

**What changes with the Agent SDK:** the SDK runs the agentic loop for you. It calls the model, runs your tool handler when Claude asks for a tool, adds the `tool_use` and the `tool_result` to the session history, and repeats until Claude stops with `end_turn`. Your code defines the tools, sets the limits and reads the stream of messages. So instead of hand-writing `client.messages.create()` calls, the POCs teach each raw-file concept by **making the SDK's loop visible** (POC 1) and by **checking and limiting how it ends** (POC 2).

- **Why not 1 POC:** in POC 1, every run makes at most one tool call, so the message stream is short enough to read line by line. POC 2 adds multi-step runs, the completion signal and the cap once that protocol is familiar.
- **Why not 3 or more:** steps 3 and 4 only make sense together, step 5 only tests steps 1–4, and step 6 is one option plus a warning. More POCs would add setup, not understanding.

**Applies to both POCs:** Python 3.10+, `pip install claude-agent-sdk` (0.2.x; it bundles the Claude Code binary), `ANTHROPIC_API_KEY` set in the environment (never hard-coded), mock tools only, and beginner-friendly code (small, commented scripts). Both POCs get their options from one shared function in `tools.py`:

```python
SYSTEM_PROMPT = ("You are a helpful assistant. Use web_search to look up facts you don't know, "
                 "and use the calculator for every arithmetic step.")

def build_options(max_turns=None):
    return ClaudeAgentOptions(
        model="claude-opus-5-5",
        system_prompt=SYSTEM_PROMPT,         # without it, the SDK sends an empty system prompt
        mcp_servers={"poc": poc_server},     # the two custom tools (C2)
        tools=[],                            # remove ALL built-in tools (WebSearch, Bash, ...): Claude can use only ours
        allowed_tools=["mcp__poc__calculator", "mcp__poc__web_search"],  # run without permission prompts
        setting_sources=[],                  # ignore ~/.claude and project settings, CLAUDE.md and hooks
        env={"ENABLE_TOOL_SEARCH": "false"}, # load both tool schemas upfront: no ToolSearch calls in the stream
        max_turns=max_turns,                 # safety cap: POC 2 passes 20 (C16)
    )
```

---

## 2. Concepts and POC requirements

All 17 concepts in the raw file (C1–C17) are covered. Each concept has one main POC; POC 2 reuses POC 1's pieces inside the loop.
Raw step → concepts: **1** → C1–C4 · **2** → C5–C7 · **3** → C8–C11 · **4** → C12–C13 · **5** → C14–C15 · **6** → C16–C17.
Rows marked **E** are extras that are not in the raw file. Without them, the POC breaks or gives misleading results.

### POC 1: Custom tools and one tool round-trip

**Build:** `tools.py` (the two tools, their MCP server and `build_options`; POC 2 reuses it) and `poc1_round_trip.py` with `async def run(prompt)`, which streams one `query()` call and prints every message. No turn cap is needed here, because each prompt needs at most one tool call.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C1 | Claude client (an Agent SDK session) | Run each prompt with `query(prompt=prompt, options=build_options())`, consumed with `async for` and started from `asyncio.run(...)` | The first run reaches a `ResultMessage` |
| C2 | A tool definition is `name` + `description` + JSON Schema input, registered with Claude | Define `calculator` and `web_search` with `@tool(name, description, input_schema)`, passing a **full JSON Schema** dict, e.g. `{"type": "object", "properties": {"expression": {"type": "string", "description": "..."}}, "required": ["expression"]}` (the property is `query` for `web_search`). Each description says what the tool does **and when to use it**. Add `annotations=ToolAnnotations(readOnlyHint=True)`, since neither tool has side effects (E1 relies on this). Bundle both with `create_sdk_mcp_server(name="poc", version="1.0.0", tools=[calculator, web_search])` and register it under the key `"poc"`, so Claude sees `mcp__poc__calculator` and `mcp__poc__web_search` | A `python tools.py` self-check (no API call) prints each tool's `name` and its `required` fields |
| C3 | Two tools: a calculator (expression → result) and a web-search stub (query → mock results) | Async handlers take `args` and return `{"content": [{"type": "text", "text": ...}]}`. `calculator` evaluates `+ - * /` and parentheses **without `eval()`** (for example via `ast`) and ignores thousands separators. `web_search` returns `Nimbus Robotics shares last traded at $187.42.` for any query containing "nimbus" (case-insensitive), and a "No results found" message for anything else. Nimbus Robotics is made up, so Claude can't know the price and has to search | The self-check calls the handlers directly, e.g. `asyncio.run(calculator.handler({"expression": "1234 * 5678"}))` returns the text `7006652`; a Nimbus query returns the snippet; `2 ** 10` returns a result with `is_error: True` (E4) |
| C6 | Inspect `stop_reason` on every response (the deterministic signal) | `run()` prints one line per streamed message with its type. For an `AssistantMessage`, also print its `message_id`, block types and `stop_reason` (this may be `None` on blocks streamed before the response finished). For the `ResultMessage`, print its `subtype`, `stop_reason` and `num_turns` | Every message is printed, and the last one shows `subtype=success stop_reason=end_turn` |
| C8 | Claude's `tool_use` request | For each `ToolUseBlock`, print its `id`, `name` and `input` | For the math prompt, a line such as `mcp__poc__calculator {'expression': '1234 * 5678'}` |
| C9 | Run the matching function (the SDK does this) | Never call a tool from inside `run()`: the SDK calls the handler when Claude asks. Each handler prints one line, such as `[handler] calculator('1234 * 5678') -> 7006652`, to prove it ran | The handler line appears between the `ToolUseBlock` line and the `ToolResultBlock` line |
| C10 | The result goes back as a `tool_result` with the matching `tool_use_id` | Your handler's return dict becomes the tool result. For each `UserMessage`, print each `ToolResultBlock`'s `tool_use_id`, `is_error` and `content` | The `tool_use_id` equals the preceding `ToolUseBlock.id`, and the content contains `7006652` |
| C11 | Both turns are appended to the history (the API is stateless) | Write no history code: the SDK keeps the session history and resends it on every turn. Add a comment that says so | The log order is `AssistantMessage` (`ToolUseBlock` id X) → `UserMessage` (`ToolResultBlock` for X) → `AssistantMessage` (text) → `ResultMessage` |
| C12 | `end_turn` means Claude has finished | Treat the `ResultMessage` as the end of the loop: the task is done when `subtype == "success"` and `stop_reason == "end_turn"`. Keep iterating to the end of the stream; don't `break` on the `ResultMessage`, because a few system events can follow it | For `In one sentence, what is an API?`, the stream has no `ToolUseBlock` and ends with `success` / `end_turn` |
| C13 | Extract and return the final text | Return `ResultMessage.result` (it's only present on `success`) | For `What is 1,234 multiplied by 5,678?`, the result contains `7,006,652` |
| C4 | Model-driven tool selection: Claude picks the tool (or none) from context | Run the same `run()` on 3 prompts and print which tool(s) Claude called: `What is 1,234 multiplied by 5,678?` · `What is Nimbus Robotics' share price right now?` · `In one sentence, what is an API?`. Put no tool-choosing logic in the code | Claude chooses `calculator` · `web_search` · no tool |
| E3 | Read blocks by type, not by position | Use `isinstance` checks (`TextBlock`, `ThinkingBlock`, `ToolUseBlock`, `ToolResultBlock`), and never assume `content[0]` is text. Expect one block per `AssistantMessage`, with the blocks of one model response sharing a `message_id` | Any `ThinkingBlock`s print as `thinking`, and nothing breaks |
| E4 | A failed tool still returns a result | For unsupported input, `calculator` returns `{"content": [...], "is_error": True}` with a helpful message instead of raising. Test prompt: `Use the calculator to evaluate exactly this expression: 2 ** 10` | A `ToolResultBlock` with `is_error=True` is printed, and the run still ends with a `ResultMessage` (Claude retries or explains) |

### POC 2: The agent loop, its end signal and its cap

**Build:** `poc2_exit_signal.py` (offline, no API calls) and `poc2_agent_loop.py`. The loop script reuses `tools.py`, defines `MAX_TURNS = 20`, and defines `async def run_agent(user_prompt, max_turns=MAX_TURNS)`, which returns `{"answer", "subtype", "stop_reason", "num_turns", "tool_calls"}`. `tool_calls` lists the full tool names in the order Claude requested them.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C7 | Content-type checks and natural-language parsing are unreliable completion signals | In `poc2_exit_signal.py`, build a recorded stream for the sequential task from real SDK dataclasses, one block per message: **1** `AssistantMessage[TextBlock("I'll look up the current share price first.")]` · **2** `AssistantMessage[ToolUseBlock(mcp__poc__web_search)]` · **3** `UserMessage[ToolResultBlock("Nimbus Robotics shares last traded at $187.42.")]` · **4** `AssistantMessage[TextBlock("Before I give my final answer, let me calculate the total.")]` · **5** `AssistantMessage[ToolUseBlock(mcp__poc__calculator, "187.42 * 37 * 1.015")]` · **6** `UserMessage[ToolResultBlock("7038.5581")]` · **7** `AssistantMessage[TextBlock("37 shares would cost $7,038.56 including the 1.5% fee.")]` · **8** `ResultMessage(subtype="success", stop_reason="end_turn", result=<text 7>)`, filling its other required fields (`duration_ms`, `duration_api_ms`, `is_error`, `num_turns`, `session_id`) with dummy values. Write 3 "find the final answer" functions: `answer_from_first_text` (the first `TextBlock`), `answer_from_phrase` (the first text containing "final answer") and `answer_from_result` (the `.result` of the `success` `ResultMessage`). Print each function's answer with ✅/❌ against message 7 | `first text` ❌ (narration) · `phrase` ❌ (picks message 4) · `result` ✅ |
| C5 | The agentic loop (run by the SDK) | `run_agent()` consumes `query(prompt=user_prompt, options=build_options(max_turns))` with `async for`. Write no `while` loop and no `messages.create()`: every turn (model call → tool run → result fed back) happens inside the SDK | One `run_agent()` call completes a multi-step task |
| C6 (in loop) | Completion is decided by the stop signal, never by text | Log each turn: the tools requested in each model response (group `AssistantMessage`s by `message_id`) and each `ToolResultBlock`. Decide the outcome **only** from the `ResultMessage`'s `subtype` and `stop_reason`, with no text or phrase checks anywhere | The log shows every turn, and the code has no text-based exit |
| C8–C11 (in loop) | Tool round-trips, reused from POC 1 | Append every `ToolUseBlock.name` to `tool_calls`, and check that every `ToolUseBlock.id` gets a `ToolResultBlock` with the same `tool_use_id` | Covered by the tests below |
| C12–C13 (in loop) | `end_turn` exit, reused from POC 1 | Set `answer` to `ResultMessage.result` when `subtype == "success"` and `stop_reason == "end_turn"`, and iterate to the end of the stream | `In one sentence, what is an API?` returns `success`, `end_turn` and `tool_calls == []` |
| C14 | Sequential tool calls: the search result feeds the calculation | Test prompt: `How much would 37 shares of Nimbus Robotics cost at the current price, including a 1.5% brokerage fee?` | The calculator's input contains `187.42`, a value that exists only in the `web_search` result in the history. The answer is about `$7,038.56` |
| C15 | Full lifecycle: tool → result → reason → next tool → `end_turn` | For that test, assert that `subtype == "success"`, `stop_reason == "end_turn"`, `len(tool_calls) >= 2`, and `mcp__poc__web_search` comes before `mcp__poc__calculator` | Typical log: turn 1 `web_search` → turn 2 `calculator` → final text |
| C4 (in loop) | Claude decides the tool order | Nothing in the code says "search, then calculate". If Claude skips the calculator, improve the tool description or system prompt, not the code | Code review finds no tool order anywhere |
| C16 | Safety cap: a limit, a counter and a warning | Pass `max_turns` (the SDK counts tool-use round trips). If `subtype == "error_max_turns"`, call `logging.warning(...)` and return `answer=None`. Wrap the `async for` in `try/except`: a single-shot `query()` raises *after* yielding an error result (for example "Reached maximum number of turns"), so record the `ResultMessage` before the exception | Running the sequential prompt with `max_turns=1` logs a `WARNING` and returns `subtype == "error_max_turns"` and `answer is None`. `stop_reason` is typically `tool_use`, because Claude still wanted a tool |
| C17 | The cap is a fallback, never the primary stop | The primary end is `success` / `end_turn`. The cap must not fire in normal runs | The sequential test ends with `success` and `num_turns` far below 20. The cap test shows how a cap used as the main stop cuts a task off |
| E1 | Claude may ask for several tools in one response | Both tools carry `readOnlyHint=True` (C2), so the SDK may run them concurrently. The SDK returns all the results before Claude's next turn | Optional test: `What is 12 times 7, and what is 99 divided by 3?` gives two calculator `ToolUseBlock`s that share one `message_id` |
| E2 | Other endings | For any other result (`error_max_budget_usd`, `error_during_execution`, `error_max_structured_output_retries`, or a `stop_reason` such as `max_tokens` or `refusal`), call `logging.warning(...)` and return `answer=None` | Code review: only `success` + `end_turn` produces an answer |
