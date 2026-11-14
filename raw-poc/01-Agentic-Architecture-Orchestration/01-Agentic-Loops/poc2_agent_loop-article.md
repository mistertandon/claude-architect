# POC 2b: The Agent Loop, Its End Signal and Its Safety Cap

> **File:** `poc2_agent_loop.py` (with `common.py` and `tools.py`)
> **Domain:** 01 Agentic Architecture & Orchestration → 01 Agentic Loops
> **SDK:** Claude Agent SDK for Python (`claude-agent-sdk >=0.2.174,<0.3`)

---

## 1. What this POC proves

This POC is built around three ideas that come up a lot when you build agents:

| # | Idea | Where it shows up in the code |
|---|------|------------------------------|
| 1 | **The SDK runs the agent loop, not your code.** There is no `while` loop and no hard-coded tool order. Claude picks which tool to call and when. | `async for message in query(...)` |
| 2 | **"Done" comes from a structured signal, not from text.** The run is finished only when a `ResultMessage` arrives with `subtype == "success"` and `stop_reason == "end_turn"`. | The `isinstance(message, ResultMessage)` check |
| 3 | **`max_turns` is a safety net.** If the loop runs out of turns, the run ends with `subtype = "error_max_turns"` and no answer. | `RUNS[2]` with `max_turns=1`, plus `except ResultError` |

The loop that the SDK repeats looks like this:

```
Claude ──tool_use──▶ SDK runs your handler ──tool_result──▶ Claude ──▶ ... ──▶ final text (end_turn)
```

---

## 2. The files involved

```
01-Agentic-Loops/
├── .env                  ← API key, MODEL_ID, MAX_TURNS, MAX_BUDGET_USD
├── common.py             ← load_settings(): reads .env into a frozen Settings object
├── tools.py              ← the 2 tools (calculator, web_search) + build_options()
└── poc2_agent_loop.py    ← entry point: 3 runs through run_agent()
```

`poc2_agent_loop.py` is short because the setup lives in the other two files:
- `common.py` covers **configuration** (which model, how many turns, how much money).
- `tools.py` covers **capabilities** (what the agent can do) and **guardrails** (what it may not do).
- `poc2_agent_loop.py` covers **orchestration** (run a task, read the result).

---

## 3. End-to-end execution flow

### 3.1 The big picture

```
python poc2_agent_loop.py
        │
        ▼
asyncio.run(main())
        │
        ├─▶ load_settings()                           [common.py]
        │      ├─ check .env exists
        │      ├─ load_dotenv(override=True)
        │      ├─ check ANTHROPIC_API_KEY is set
        │      └─ return Settings(model_id, max_turns, max_budget_usd)
        │
        └─▶ for (prompt, max_turns) in RUNS:          (3 runs, one after another)
               │
               ├─▶ build_options(settings, max_turns) [tools.py]
               │      └─ ClaudeAgentOptions(model, system_prompt, mcp_servers,
               │                            tools=[], allowed_tools, setting_sources=[],
               │                            env, thinking, max_turns, max_budget_usd)
               │
               └─▶ run_agent(prompt, options)
                      │
                      └─▶ async for message in query(prompt, options):
                             │
                             │   ┌──────────── SDK-owned agent loop ─────────────┐
                             │   │ starts the Claude Code process                 │
                             │   │ sends prompt + system prompt + tool schemas    │
                             │   │ ┌─▶ Claude responds                            │
                             │   │ │     ├─ tool_use?  → SDK calls your handler   │
                             │   │ │     │              → tool_result back to     │
                             │   │ └─────┘                Claude (next turn)      │
                             │   │       └─ no tool_use → stop_reason=end_turn    │
                             │   │ yields ResultMessage (success / error_*)      │
                             │   └────────────────────────────────────────────────┘
                             │
                             ├─ ResultMessage(success, end_turn) → answer = message.result
                             └─ ResultError raised (e.g. error_max_turns) → answer stays None
```

### 3.2 Messages your `async for` receives (Run 2, real output)

The values below come from a real run on 2026-10-26, recorded in `01-Agentic-Architecture-Orchestration/01-Agentic-Loops/logs/poc2_agent_loop_20261026_191138.log`. That log was written by the **logging version** of this POC (the same code plus a `log_model_io(message)` call inside the `async for`). Each log line is one field of one message from the stream:

| Log line tag | Message class yielded by `query()` | Field logged |
|--------------|------------------------------------|--------------|
| `MODEL INPUT prompt` | *(none: it's the `user_prompt` you passed in)* | `user_prompt` |
| `MODEL OUTPUT text` | `AssistantMessage` → `TextBlock` | `block.text` |
| `MODEL OUTPUT tool_use` | `AssistantMessage` → `ToolUseBlock` | `block.name`, `block.input`, `block.id` |
| `MODEL INPUT tool_result` | `UserMessage` → `ToolResultBlock` | `block.content`, `block.tool_use_id`, `block.is_error` |
| `MODEL OUTPUT stop_reason` | `ResultMessage` | `message.stop_reason`, `message.subtype` |

Run 2 as it really streamed, in order, inside the **one** `async for` loop:

```
19:11:43  (input)           user_prompt = "How much would 37 shares of Nimbus Robotics cost ... 1.5% brokerage fee?"
19:11:46  AssistantMessage  ToolUseBlock    name  = "mcp__poc__web_search"
                                            input = {'query': 'Nimbus Robotics stock price'}
                                            id    = "toolu_01M9rExQrfnVBvwRKVtGtFvE"
19:11:46  UserMessage       ToolResultBlock content     = [{'type': 'text', 'text': 'Nimbus Robotics shares last traded at $187.42.'}]
                                            tool_use_id = "toolu_01M9rExQrfnVBvwRKVtGtFvE"   ← same id as the request
                                            is_error    = None                              ← handler succeeded
19:11:47  AssistantMessage  ToolUseBlock    name  = "mcp__poc__calculator"
                                            input = {'expression': '37 * 187.42 * 1.015'}    ← $187.42 copied from the search result
                                            id    = "toolu_01QnLHfgy2gARs9QE4EJFnLM"
19:11:47  UserMessage       ToolResultBlock content     = [{'type': 'text', 'text': '7038.5581'}]
                                            tool_use_id = "toolu_01QnLHfgy2gARs9QE4EJFnLM"
                                            is_error    = None
19:11:49  AssistantMessage  TextBlock       text = "37 shares of Nimbus Robotics would cost about **$7,038.56** including the fee. ..."
19:11:49  ResultMessage                     subtype = "success", stop_reason = "end_turn"
```

What to notice in the real data:
- **`tool_use_id` pairing.** Every `ToolResultBlock.tool_use_id` equals the `ToolUseBlock.id` it answers (`toolu_01M9r...` → `toolu_01M9r...`). That's how Claude knows which result belongs to which call.
- **`is_error = None`.** The handler returned no `is_error` key, which means success. A failure would show `True` (see `tools.py`).
- **Data flows between tools.** `187.42` appears in the search result and then inside the calculator's `input`. Claude wired the two tools together; no code did.
- **No narration this time.** Claude went straight to `tool_use` with no "Let me look that up" text. Sometimes it writes narration, sometimes it doesn't, which is one more reason never to use text as a control signal.
- **Not shown:** the `SystemMessage` (session init) and thinking blocks also arrive in the stream, but this log records only model input and output, so they don't appear here.

> The `UserMessage` items are **not** typed by a human. They carry the tool results that the SDK sends back to Claude for you. In the Messages API, tool results go to the model in the `user` role.

---

## 4. Code walkthrough

### 4.1 Module docstring: the contract

```python
"""
One query() call runs the whole agent loop. The SDK repeats the turn

    Claude -> tool_use -> your handler -> tool_result -> Claude

until Claude answers without asking for a tool (stop_reason=end_turn).
...
"""
```

**Why it matters:** the docstring states the model for the whole file. You don't write the loop; you consume it. Compare this with a hand-written Messages-API agent, where you write the `while stop_reason == "tool_use":` loop, run tools, and append `tool_result` blocks yourself. The Agent SDK does all of that inside `query()`.

---

### 4.2 Imports

```python
import asyncio
import sys

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKError, ResultError, ResultMessage, query

from common import load_settings
from tools import build_options
```

| Import | Role |
|--------|------|
| `query` | The one-shot entry point. It runs the full agent loop for a single prompt and **streams** every message as an async iterator. |
| `ClaudeAgentOptions` | The config object: model, tools, permissions, limits. |
| `ResultMessage` | The final message of every run. It holds the **deterministic end signal** (`subtype`, `stop_reason`, `result`, `num_turns`, cost and so on). |
| `ResultError` | Raised by `query()` **after** it has yielded an error `ResultMessage`, for example when the turn cap is hit. |
| `ClaudeSDKError` | Base class for infrastructure failures, such as the Claude Code binary missing or its process crashing. |
| `asyncio` | The SDK is async because tool calls and streaming are I/O-bound. |

**Agentic concept:** there are two kinds of errors. A `ResultError` means *the agent ran but did not succeed* (a business-level outcome). A `ClaudeSDKError` means *the agent could not run at all* (an infrastructure failure). Handling them separately is a key design choice in agent systems.

---

### 4.3 The task prompts

```python
SEQUENTIAL_PROMPT = (
    "How much would 37 shares of Nimbus Robotics cost at the current price, including a 1.5% brokerage fee?"
)
```

**Why this prompt?** It is built to force a **sequential, dependent tool chain**:
1. Claude can't know the price, because Nimbus Robotics is made up. So it **must** call `web_search`.
2. Only after it has the price can it compute `187.42 × 37 × 1.015`, and the system prompt tells it to use the `calculator` for every arithmetic step.

The output of tool 1 is the input of tool 2. That makes a multi-turn loop happen naturally. Nothing in the code says "search first, then calculate"; **Claude plans the order itself.**

---

### 4.4 The run table: three experiments

```python
# (prompt, max_turns); None = MAX_TURNS from .env
RUNS = [
    ("In one sentence, what is an API?", None),  # no tool needed: the loop ends after one turn
    (SEQUENTIAL_PROMPT, None),  # web_search, then calculator: the search result feeds the calculation
    (SEQUENTIAL_PROMPT, 1),  # the same task with max_turns=1: the safety cap cuts the loop off
    # ("What is 12 times 7, and what is 99 divided by 3?", None),  # optional: two tool calls in ONE response
]
```

The table is data-driven: each tuple is one experiment, and the code that runs them is the same.

| Run | Prompt | Cap | What happens | Outcome |
|-----|--------|-----|--------------|---------|
| 1 | "What is an API?" | `.env` value | Claude answers from its own knowledge. No `tool_use`, so the loop finishes after **1 turn**. | `success` / `end_turn`, answer set |
| 2 | Nimbus shares | `.env` value | Turn 1: `web_search`. Turn 2: `calculator`. Turn 3: final text. | `success` / `end_turn`, answer set |
| 3 | Nimbus shares | **1** | Turn 1: Claude asks for `web_search` and the SDK runs it. Sending the result back to Claude would start turn 2, which goes over the cap. | `error_max_turns`, `ResultError`, answer `None` |
| (4) | Two independent sums | `.env` value | *Optional:* Claude can put **two `tool_use` blocks in one response** (parallel tool calls). That's allowed because the tools are marked `readOnlyHint=True`. | `success` |

**Agentic concept:** Runs 1 and 2 show that **the number of turns is decided at runtime by the model**, not by the developer. Run 3 shows why you still need a hard upper bound.

---

### 4.5 `run_agent()`: the heart of the POC

```python
async def run_agent(user_prompt: str, options: ClaudeAgentOptions) -> str | None:
    """Run one agent task. Returns the final answer, or None if the loop didn't finish."""
    answer = None
```

The return type `str | None` says it directly: a run either produces an answer or it doesn't. `None` is a valid outcome, not an exception.

#### a) Consuming the loop

```python
    try:
        async for message in query(prompt=user_prompt, options=options):  # every turn of the loop runs in here
```

- `query()` starts the bundled Claude Code process, sends the prompt, the system prompt and the tool schemas, and then **drives the whole tool-use loop**.
- Each `AssistantMessage`, tool-result `UserMessage`, `SystemMessage` and the final `ResultMessage` is **yielded** to you as it happens. This is streaming, so you could show progress live.
- Your tool handlers in `tools.py` are called **by the SDK** while this `for` is suspended between yields. You never call them yourself.

#### b) The stop signal

```python
            # The stop signal: success + end_turn means Claude finished. Never check the text instead.
            if isinstance(message, ResultMessage) and message.subtype == "success" and message.stop_reason == "end_turn":
                answer = message.result
```

This line is the main lesson of the POC. There are three checks, and each has a purpose:

| Check | Why |
|-------|-----|
| `isinstance(message, ResultMessage)` | Only the `ResultMessage` marks the end of the run. Text in an `AssistantMessage` can show up in **any** turn, including narration such as *"Before I give my final answer, let me calculate..."*. |
| `subtype == "success"` | The run finished normally. It didn't hit `error_max_turns`, `error_max_budget_usd` or `error_during_execution`. |
| `stop_reason == "end_turn"` | Claude **chose** to stop: its last response had no `tool_use`. This is the model's own "I'm done" signal. |

`message.result` holds the final answer text, so you don't need to dig through `AssistantMessage` blocks.

**Anti-patterns this replaces** (shown offline in `poc2_exit_signal.py`):
- ❌ "The first `TextBlock` is the answer." That grabs the narration from turn 1.
- ❌ "Text containing *final answer* is the answer." That grabs text written *before* the real calculation.
- ✅ Read `ResultMessage` + `subtype` + `stop_reason`. This works every time.

#### c) No `break`

```python
            # No `break`: a few system events can still arrive after the ResultMessage.
```

**Why it matters:** if you `break` out of an async generator early, the SDK's cleanup (closing the subprocess, flushing trailing events) may not run cleanly. Letting the stream finish keeps the lifecycle clean. The answer is already saved in `answer`, so nothing is lost.

#### d) Handling a run that didn't finish

```python
    except ResultError:
        # A single-shot query() raises AFTER it yielded an error ResultMessage,
        # e.g. error_max_turns (the safety cap), error_max_budget_usd, error_during_execution, an invalid API key.
        pass
    return answer
```

- In Run 3 the SDK first **yields** a `ResultMessage(subtype="error_max_turns")`. In the real log it carried `stop_reason="tool_use"`: Claude still wanted to continue. Your `if` ignores it because the subtype isn't `"success"`. Then the SDK **raises** `ResultError`.
- Catching it here turns "the agent gave up" into a plain `None` return value. The caller then decides what to do: retry with a bigger cap, escalate to a human, and so on.
- `pass` is deliberate. In this stripped-down `raw-poc` version all logging was removed, so the outcome is held only in `answer`.

**Agentic concept: graceful degradation.** A production agent must tell apart *"finished with an answer"*, *"stopped by a guardrail"* and *"crashed"*. This function covers the first two. `main()` covers the third.

---

### 4.6 `main()`: orchestration and failure boundaries

```python
async def main() -> int:
    try:
        settings = load_settings()
    except (OSError, RuntimeError):
        return 1
```

`load_settings()` (in `common.py`) **fails fast** before any API call when:
- `.env` is missing (`RuntimeError`),
- `ANTHROPIC_API_KEY` is empty or still the placeholder (`RuntimeError`),
- `MAX_TURNS` or `MAX_BUDGET_USD` aren't numbers (`ValueError`, re-raised as `RuntimeError`).

It returns a **frozen** dataclass, so no code can change the settings partway through a run.

```python
    for prompt, max_turns in RUNS:
        try:
            await run_agent(prompt, build_options(settings, max_turns=max_turns or settings.max_turns))
        except ClaudeSDKError:  # Claude Code not found, its process crashed, ...
            return 1
    return 0
```

- `max_turns or settings.max_turns`: `None` in the table means "use the `.env` default", and Run 3 overrides it with `1`.
- `build_options(...)` is called **once per run**, so every run starts from a clean config and a **fresh session** (no shared conversation history between runs).
- `ClaudeSDKError` is the infrastructure boundary. If the agent runtime itself is broken, carrying on with the other runs makes no sense, so the script exits with code `1`.
- The return value of `run_agent()` is not used here. The logging-free `raw-poc` copy keeps the check (`answer`) but doesn't print it.

```python
if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

`asyncio.run` starts the event loop, and `sys.exit` passes `0` or `1` to the shell, which is handy in CI.

---

### 4.7 `build_options()`: each option is a decision (from `tools.py`)

The loop file is small because **all agent behaviour is set in one place**:

```python
def build_options(settings: Settings, max_turns: int | None = None) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=settings.model_id,
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={SERVER_NAME: create_sdk_mcp_server(name=SERVER_NAME, tools=[calculator, web_search])},
        tools=[],
        allowed_tools=[CALCULATOR, WEB_SEARCH],
        setting_sources=[],
        env={"ENABLE_TOOL_SEARCH": "false"},
        thinking={"type": "adaptive", "display": "summarized"},
        max_turns=max_turns,
        max_budget_usd=settings.max_budget_usd,
    )
```

| Option | What it does | Agentic concept |
|--------|--------------|-----------------|
| `model` | Which Claude model reasons in the loop. | Model selection is config, not code. |
| `system_prompt` | *"Use web_search for facts you don't know, use the calculator for every arithmetic step."* | **Steers tool choice** without hard-coding the order. Without it, the SDK sends an empty system prompt. |
| `mcp_servers` | Registers the two Python tools as an **in-process MCP server** named `poc`. | Custom tools reach Claude through MCP. Their full names become `mcp__poc__calculator` and `mcp__poc__web_search`. |
| `tools=[]` | Removes **all** built-in Claude Code tools (Bash, Read, WebSearch and so on). | **Least privilege.** The agent can only do what you gave it. |
| `allowed_tools` | Lets the two tools run with no permission prompt. | **Permission model.** Listing a tool here pre-approves it. |
| `setting_sources=[]` | Ignores `~/.claude` settings, `CLAUDE.md` and hooks. | **Reproducibility.** The same run gives the same behaviour on any machine. |
| `ENABLE_TOOL_SEARCH=false` | Sends both tool schemas up front. | No extra `ToolSearch` turns that would skew the turn count. |
| `thinking` | Adaptive thinking with summarized reasoning text. | Lets you see *why* Claude picked a tool. |
| `max_turns` | Hard cap on loop iterations. | **Safety net** against runaway loops (Run 3). |
| `max_budget_usd` | Stops the run when the estimated spend goes over this amount. | **Cost guardrail.** It's a second, independent stop condition. |

---

### 4.8 The tools Claude can call (from `tools.py`)

Each tool has four parts: **name + description + JSON Schema + async handler**. Claude sees only the first three. The SDK runs the fourth.

```python
@tool(
    "calculator",
    "Evaluate an arithmetic expression and return the exact result. ... Use it for EVERY arithmetic step ...",
    {"type": "object", "properties": {"expression": {"type": "string", ...}}, "required": ["expression"]},
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def calculator(args): ...
```

Key points:
- **The description is a prompt.** "Use it for EVERY arithmetic step" is what makes Claude call it instead of doing the maths in its head.
- **`readOnlyHint=True`** tells the SDK the tool has no side effects, so it may run several calls **in parallel** (the optional Run 4).
- **Safe evaluation:** `_evaluate()` walks the `ast` tree and allows only numbers, `+ - * /` and parentheses. There is no `eval()`, so a model-supplied string can never run arbitrary code.
- **Errors are results, not exceptions:**

  ```python
  return {"content": [{"type": "text", "text": message}], "is_error": True}
  ```

  A failed tool still returns a `tool_result`, with `is_error=True` and a hint (*"write a power as repeated multiplication"*). Claude reads it and **recovers on the next turn**. If the handler raised an exception instead, the loop would have no useful feedback to pass on.

```python
def _search_backend(search_text: str) -> str:
    if "nimbus" in search_text.lower():
        return "Nimbus Robotics shares last traded at $187.42."
    return f"No results found for '{search_text}'."
```

- `web_search` is a **stub** that stands in for a real search API. Using a made-up company means Claude **can't** answer from its training data, so the tool call is guaranteed.

---

## 5. Turn-by-turn trace of each run (real output)

Each trace below is the real run from `logs/poc2_agent_loop_20261026_191138.log` (2026-10-26, 19:11:38 to 19:11:54, about 16 seconds for all three runs), with each logged value tied to the variable in `run_agent()` that held it.

### Run 1: no tools, one turn

**Real log:**

```
19:11:38  MODEL INPUT   prompt       In one sentence, what is an API?
19:11:42  MODEL OUTPUT  text         An API (Application Programming Interface) is a set of rules and endpoints that lets
                                     one piece of software request data or services from another without needing to know
                                     how it works internally.
19:11:42  MODEL OUTPUT  stop_reason  end_turn  (loop result: success)
```

**Variable values inside `run_agent()`:**

| Variable / field | Value |
|------------------|-------|
| `user_prompt` | `"In one sentence, what is an API?"` |
| `options.max_turns` | `MAX_TURNS` from `.env` (Run 1 passes `None`, so the default is used) |
| `message` (1st relevant) | `AssistantMessage` with one `TextBlock`, and **no** `ToolUseBlock` |
| `message` (last) | `ResultMessage` |
| `message.subtype` | `"success"` |
| `message.stop_reason` | `"end_turn"` |
| `message.result` | `"An API (Application Programming Interface) is a set of rules and endpoints ..."` |
| `answer` (returned) | the same text as `message.result` |

**Lesson:** about 4 seconds, no `tool_use`, done. An agent loop with zero tool calls is still an agent loop. Claude decided no tool was needed, and the loop ended after the first response.

### Run 2: sequential tool chain

**Real log:**

```
19:11:43  MODEL INPUT   prompt       How much would 37 shares of Nimbus Robotics cost at the current price, including a 1.5% brokerage fee?
19:11:46  MODEL OUTPUT  tool_use     mcp__poc__web_search {'query': 'Nimbus Robotics stock price'}  (id=toolu_01M9rExQrfnVBvwRKVtGtFvE)
19:11:46  MODEL INPUT   tool_result  [{'type': 'text', 'text': 'Nimbus Robotics shares last traded at $187.42.'}]  (tool_use_id=toolu_01M9rExQrfnVBvwRKVtGtFvE, is_error=None)
19:11:47  MODEL OUTPUT  tool_use     mcp__poc__calculator {'expression': '37 * 187.42 * 1.015'}  (id=toolu_01QnLHfgy2gARs9QE4EJFnLM)
19:11:47  MODEL INPUT   tool_result  [{'type': 'text', 'text': '7038.5581'}]  (tool_use_id=toolu_01QnLHfgy2gARs9QE4EJFnLM, is_error=None)
19:11:49  MODEL OUTPUT  text         37 shares of Nimbus Robotics would cost about **$7,038.56** including the fee.

                                     - The last traded price was $187.42 per share.
                                     - 37 shares at that price come to $6,934.54.
                                     - The 1.5% brokerage fee adds about $104.02.

                                     The price may have changed since the last trade, so the final cost could differ a little.
19:11:49  MODEL OUTPUT  stop_reason  end_turn  (loop result: success)
```

**What each turn did and which code ran:**

| Turn | Claude asked for (`ToolUseBlock`) | Code the SDK ran | Value returned (`ToolResultBlock.content`) |
|------|-----------------------------------|------------------|-------------------------------------------|
| 1 | `web_search`, `input={'query': 'Nimbus Robotics stock price'}` | `web_search()` → `_search_backend()` matched `"nimbus"` | `"Nimbus Robotics shares last traded at $187.42."` |
| 2 | `calculator`, `input={'expression': '37 * 187.42 * 1.015'}` | `calculator()` → `_evaluate(ast.parse(...))` → `7038.558100...` → `round(value, 6)` | `"7038.5581"` |
| 3 | *(no tool)*: final `TextBlock` | none | none. `stop_reason="end_turn"` |

**Variable values at the end of the run:**

| Variable / field | Value |
|------------------|-------|
| `message.subtype` | `"success"` |
| `message.stop_reason` | `"end_turn"` |
| `message.result` | `"37 shares of Nimbus Robotics would cost about **$7,038.56** including the fee. ..."` |
| `answer` (returned) | the same text as `message.result` |

**Lessons from the real data:**
- The model **read the output of one tool and used it to build the input of the next**: `$187.42` went from the search result into the calculator expression. That reasoning between steps is what separates an agent from a fixed pipeline.
- Claude obeyed the system prompt ("use the calculator for every arithmetic step"). It did the multiplication in **one** calculator call, `37 * 187.42 * 1.015`. The breakdown in the final text (`$6,934.54` + `$104.02`) is Claude explaining the result, not extra tool calls.
- The calculator returned `7038.5581`, and Claude rounded it to `$7,038.56` for the user. Tools give exact values; the model formats them.

### Run 3: safety cap fires (`max_turns=1`)

**Real log:**

```
19:11:50  MODEL INPUT   prompt       How much would 37 shares of Nimbus Robotics cost at the current price, including a 1.5% brokerage fee?
19:11:53  MODEL OUTPUT  tool_use     mcp__poc__web_search {'query': 'Nimbus Robotics stock price'}  (id=toolu_01Fnb4FAxzShmPVTBg39ZHy6)
19:11:53  MODEL INPUT   tool_result  [{'type': 'text', 'text': 'Nimbus Robotics shares last traded at $187.42.'}]  (tool_use_id=toolu_01Fnb4FAxzShmPVTBg39ZHy6, is_error=None)
19:11:53  MODEL OUTPUT  stop_reason  tool_use  (loop result: error_max_turns)
19:11:54  Safety cap hit: max_turns=1 was used up before Claude finished. No answer.
```

**What happened, step by step:**

1. Turn 1: Claude asked for `web_search`, exactly as in Run 2. The ID is different (`toolu_01Fnb...`) because every call gets a new one.
2. The SDK **did run the handler** and got the price. The tool result exists.
3. Sending that result back to Claude would start **turn 2**, but `max_turns=1` is used up. The SDK stops the loop.
4. The SDK yields `ResultMessage(subtype="error_max_turns", stop_reason="tool_use")`, then raises `ResultError`.

**Variable values inside `run_agent()`:**

| Variable / field | Value | Effect in the code |
|------------------|-------|--------------------|
| `options.max_turns` | `1` | from `RUNS[2] = (SEQUENTIAL_PROMPT, 1)` |
| `message.subtype` | `"error_max_turns"` | the `if` is **False**, so `answer` is not set |
| `message.stop_reason` | `"tool_use"` | Claude **still wanted to continue** when it was cut off |
| exception | `ResultError` | caught by `except ResultError: pass` |
| `answer` (returned) | `None` | the run gave no answer |

(The last log line, *"Safety cap hit ..."*, comes from the logging version's `except ResultError` branch, which checks `exc.subtype == "error_max_turns"`. The `raw-poc` version just does `pass`.)

**Lessons from the real data:**
- **`stop_reason="tool_use"` in a final `ResultMessage` is a red flag.** It shows the loop was stopped from outside while Claude was mid-task. A healthy run always ends on `end_turn`.
- **The work done before the cap is thrown away.** The price `$187.42` was fetched, but the user gets nothing. Set `max_turns` high enough for real tasks (Run 2 needed 3 model responses), and treat hitting the cap as a failure to handle, not a result.
- **Same prompt, different outcome.** Runs 2 and 3 started identically. Only the `options` changed. Guardrails live in configuration, not in the prompt.

### 5.4 The three runs side by side

| | Run 1 | Run 2 | Run 3 |
|-|-------|-------|-------|
| `max_turns` | `.env` default | `.env` default | `1` |
| Tool calls | 0 | 2 (`web_search` → `calculator`) | 1 (`web_search`) |
| Final `message.subtype` | `success` | `success` | `error_max_turns` |
| Final `message.stop_reason` | `end_turn` | `end_turn` | `tool_use` |
| `ResultError` raised? | no | no | **yes** |
| `answer` returned | API definition text | `"...about **$7,038.56**..."` | `None` |
| Wall time (from log) | about 4 s | about 6 s | about 4 s |

---

## 6. Agentic AI concepts recap

| Concept | How this POC shows it |
|---------|-----------------------|
| **Agent loop** | `query()` repeats *model → tool_use → handler → tool_result → model* until `end_turn`. |
| **Model-driven control flow** | No `while`, no `if tool == ...`, no fixed order. Claude decides. |
| **Deterministic termination** | Only `ResultMessage.subtype` + `stop_reason` decide "done", never text. |
| **Stop reasons** | `tool_use` means the loop continues (internal to the SDK). `end_turn` means Claude finished. |
| **Result subtypes** | `success`, `error_max_turns`, `error_max_budget_usd`, `error_during_execution`. |
| **Guardrails** | `max_turns` (iterations), `max_budget_usd` (cost), `tools=[]` + `allowed_tools` (capabilities). |
| **Tool design** | Clear description (acts as a prompt), strict JSON Schema, safe implementation, `is_error` results. |
| **Parallel tool calls** | `readOnlyHint=True` lets several `tool_use` blocks in one response run at the same time. |
| **Error taxonomy** | `ResultError` = the agent ran but didn't succeed. `ClaudeSDKError` = the runtime is broken. |
| **Reproducibility** | `setting_sources=[]`, no tool search, a fresh session per run. |

---

## 7. Common mistakes this POC helps you avoid

1. **Writing your own `while` loop around `query()`.** The SDK already loops. Wrapping it just repeats the whole task.
2. **Parsing Claude's text to decide it's finished.** Narration can appear in any turn. Use `ResultMessage`.
3. **`break`ing right after the first `ResultMessage`.** Let the stream finish so the SDK can clean up.
4. **Treating `max_turns` as a target.** It's a ceiling. Hitting it means failure, with no answer.
5. **Raising exceptions from tool handlers.** Return `is_error=True` with a helpful message so Claude can recover.
6. **Leaving built-in tools on.** Without `tools=[]`, the agent could also reach for Bash, file access or the web.
7. **Catching every exception the same way.** Keep the agent outcome (`ResultError`) separate from infrastructure failure (`ClaudeSDKError`).

---

## 8. Claude Architect exam lens

### 8.1 What the exam tests on this topic

| Exam objective | What a correct answer looks like | Where this POC shows it |
|----------------|----------------------------------|-------------------------|
| Register several tools with JSON Schema | Each tool has a `name`, a `description` and an input schema. Claude picks the tool from the description. | `@tool(...)` in `tools.py` |
| Decide the next step from `stop_reason` | Branch on `tool_use` vs `end_turn`. **Never** branch on content type or phrases. | The `ResultMessage` / `stop_reason` check |
| Handle `tool_use` correctly | Run the tool, then send a `tool_result` with the matching `tool_use_id` in the **next user message**, after the assistant message has been added to the history. | Done by the SDK inside `query()` (see 8.2 for the manual version) |
| Handle `end_turn` | Leave the loop and return the final text. | `answer = message.result` |
| Sequential tool calls | The loop keeps going until the result of the first tool has fed into the second. | Run 2 (search, then calculate) |
| Safety cap | A fallback (for example 20 iterations) that **should never fire in normal use** and logs a warning when it does. It is not the primary way the loop stops. | `max_turns`, Run 3 |

> **Exam tip:** questions are often written against the **raw Messages API** (`client.messages.create()` in a loop). The Agent SDK hides that loop, so you need to recognise both forms and know they mean the same thing.

### 8.2 The same loop with the raw Messages API

This is what `query()` does for you. Learn this shape, because exam answer options are usually variants of it with one thing wrong.

```python
import anthropic

client = anthropic.Anthropic()
MAX_ITERATIONS = 20  # safety cap: a fallback, NOT the stop mechanism


def run_agent(prompt: str) -> str | None:
    messages = [{"role": "user", "content": prompt}]
    for _ in range(MAX_ITERATIONS):
        response = client.messages.create(
            model=MODEL_ID, max_tokens=1024, system=SYSTEM_PROMPT, tools=TOOLS, messages=messages,
        )
        # 1. ALWAYS keep the assistant turn (it holds the tool_use blocks)
        messages.append({"role": "assistant", "content": response.content})

        # 2. Decide from stop_reason, never from the text
        if response.stop_reason == "end_turn":
            return "".join(block.text for block in response.content if block.type == "text")

        if response.stop_reason == "tool_use":
            results = []
            for block in response.content:  # there can be SEVERAL tool_use blocks (parallel calls)
                if block.type == "tool_use":
                    output, failed = run_tool(block.name, block.input)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,  # must match the request
                        "content": output,
                        "is_error": failed,  # a failure is still a result
                    })
            # 3. ALL results go back in ONE user message
            messages.append({"role": "user", "content": results})
            continue

        # max_tokens and similar: the answer was cut off, so this is NOT "done"
        raise RuntimeError(f"unexpected stop_reason: {response.stop_reason}")

    log.warning("safety cap of %d iterations hit: investigate, don't just raise the cap", MAX_ITERATIONS)
    return None
```

| Raw Messages API (you write it) | Agent SDK (`poc2_agent_loop.py`) |
|---------------------------------|----------------------------------|
| `for`/`while` loop around `client.messages.create()` | One `async for message in query(...)` |
| `if response.stop_reason == "tool_use"` → run tools | The SDK calls your `@tool` handlers |
| Append the assistant message + a user message of `tool_result` blocks | The SDK keeps the history. You see these as `AssistantMessage` / `UserMessage` items |
| `if response.stop_reason == "end_turn"` → return the text | `ResultMessage.subtype == "success"` and `stop_reason == "end_turn"` → `message.result` |
| `MAX_ITERATIONS` counter + warning | `max_turns` → `error_max_turns` + `ResultError` |
| Manual cost tracking | `max_budget_usd` → `error_max_budget_usd` |

### 8.3 Scenario questions

Try each one before reading the answer.

---

**Scenario 1: The agent answers too early**

A support agent sometimes replies *"Let me check your order status..."* and then stops without checking. The loop exits with:

```python
if response.content[0].type == "text":
    return response.content[0].text
```

What is the root cause?

- A. The tool description is too vague.
- B. The loop treats the first text block as the final answer, but Claude often writes text **before** a `tool_use` block in the same response.
- C. `max_tokens` is too low.
- D. The system prompt doesn't tell Claude to use tools.

**Answer: B.** A content-type check is an anti-pattern. A response can hold text **and** `tool_use` together. Only `stop_reason == "tool_use"` / `"end_turn"` tells you what to do next. *POC link:* `answer_from_first_text()` in `poc2_exit_signal.py` fails for exactly this reason.

---

**Scenario 2: Detecting completion from a phrase**

A team tells Claude in the system prompt to end with `FINAL ANSWER:`, and the loop stops when that string appears. In production the agent sometimes returns before running its last calculation. What is the best fix?

- A. Make the marker more unusual, like `<<<DONE>>>`.
- B. Add few-shot examples showing when to write the marker.
- C. Stop when `stop_reason == "end_turn"` (in the SDK: a `ResultMessage` with `subtype == "success"`), and ignore the text when deciding termination.
- D. Lower the temperature.

**Answer: C.** Parsing natural language is probabilistic. Claude may say *"before my final answer..."* in a middle turn. `stop_reason` is a **deterministic, structured** signal. Options A, B and D only make the wrong approach fail less often. *POC link:* `answer_from_phrase()` in `poc2_exit_signal.py`.

---

**Scenario 3: The safety cap keeps firing**

Logs show a research agent hitting its 20-iteration cap on about 15% of tasks. A reviewer suggests lowering the cap to 8 "so failures are cheaper". What should the architect do?

- A. Lower it to 8 as suggested.
- B. Raise it to 100 so tasks can finish.
- C. Treat the cap as a fallback. Investigate why the loop isn't reaching `end_turn` (repeated tool errors, vague tool descriptions, tool results without the data Claude needs) and fix that.
- D. Remove the cap and depend on `max_tokens`.

**Answer: C.** A safety cap should **never** fire in normal use. If it does, that's a symptom. Changing its value in either direction treats the symptom, not the cause. Removing it (D) leaves runaway loops unbounded. *POC link:* Run 3 shows that a cap hit gives **no answer**, so it's a failure you have to handle.

---

**Scenario 4: The API rejects the second request**

After Claude returns `stop_reason: "tool_use"`, a developer runs the tool and sends:

```python
messages.append({"role": "user", "content": f"The tool returned: {result}"})
```

The API returns an error. Why?

- A. The tool result must be sent in the `system` parameter.
- B. The assistant message with the `tool_use` block was never added to the history, and the result must be a `tool_result` block whose `tool_use_id` matches the request.
- C. Tool results must be sent with `role: "tool"`.
- D. The tool must be called again by the API.

**Answer: B.** The handoff has two parts: (1) add the assistant response, including the `tool_use` block, to the history; (2) send a **user** message containing `{"type": "tool_result", "tool_use_id": <id>, "content": ...}`. There is no `"tool"` role in the Claude Messages API. *POC link:* the `UserMessage` / `ToolResultBlock` pairs in section 3.2 are what the SDK sends for you.

---

**Scenario 5: Parallel tool calls**

Claude returns **two** `tool_use` blocks in one response (`12*7` and `99/3`). How should the results go back?

- A. Two separate user messages, one per result.
- B. One user message with two `tool_result` blocks, each with its own `tool_use_id`.
- C. Only the first result. Claude will ask for the second one again.
- D. Combine both into one text string.

**Answer: B.** Every `tool_use` in a response needs a matching `tool_result`, and all of them go back together in the next user message. *POC link:* the commented-out Run 4. `readOnlyHint=True` tells the SDK these calls are safe to run in parallel.

---

**Scenario 6: A tool fails**

The search API times out. The handler raises an exception and the whole agent run aborts. What is the better design?

- A. Retry the search forever inside the handler.
- B. Return a `tool_result` with `is_error: true` and a clear message, so Claude can retry, rephrase or explain the limit to the user.
- C. Return an empty string so Claude carries on.
- D. Restart the conversation from scratch.

**Answer: B.** A failed tool is still a **result**. A structured error lets the model recover on the next turn. An empty result (C) hides the failure and invites made-up answers. *POC link:* the `except` branches in `calculator()` and `web_search()` in `tools.py`.

---

**Scenario 7: Hard-coding the tool order**

To "make it reliable", a developer changes the code to always call `web_search` first and then `calculator`, and only then calls Claude to word the answer. What is lost?

- A. Nothing. It's strictly better.
- B. Model-driven decision-making. The agent can no longer skip tools it doesn't need (Run 1), change the order, or react to what a tool returned.
- C. Only some performance.
- D. Prompt caching.

**Answer: B.** In an agentic loop **Claude decides which tool to call next**, based on context. A fixed pipeline is the right choice only when a step **must** happen for business or compliance reasons. That's a different pattern (workflow enforcement in code or hooks), covered in topic 01-04. *POC link:* `poc2_agent_loop.py` has no `if tool == ...` and no tool order.

---

**Scenario 8: The Agent SDK end signal**

Using `claude_agent_sdk.query()`, which condition reliably marks a successfully completed agent run?

- A. The last `AssistantMessage` contains a `TextBlock`.
- B. The iterator stops yielding.
- C. A `ResultMessage` with `subtype == "success"` (and `stop_reason == "end_turn"`).
- D. A `UserMessage` with no `ToolResultBlock`.

**Answer: C.** The iterator also stops after an **error** run (B), and text can come from any turn (A). The `ResultMessage` holds the structured outcome: `subtype`, `stop_reason`, `result`, `num_turns` and cost. *POC link:* the `if` in `run_agent()`.

---

**Scenario 9: `stop_reason == "max_tokens"`**

A loop handles `tool_use` and treats **every other** `stop_reason` as done. Users get answers that are cut off mid-sentence. What is wrong?

- A. Nothing. Any stop reason other than `tool_use` means done.
- B. `max_tokens` means the response was **cut off**, not that it's complete. It must be handled on its own (raise the limit, continue, or report an error), not returned as the final answer.
- C. The tool schema is invalid.
- D. The safety cap is too low.

**Answer: B.** Only `end_turn` means *"Claude finished its turn"*. Branch on the exact value and treat unexpected stop reasons explicitly. *POC link:* the SDK version checks `stop_reason == "end_turn"` exactly, never "not `tool_use`".

---

**Scenario 10: Least privilege for an agent's tools**

A finance Q&A agent built on the Agent SDK should only use `calculator` and `web_search`, but in testing it runs a Bash command. Which configuration fixes this?

- A. Add "never use Bash" to the system prompt.
- B. Remove the built-in tools (`tools=[]`), expose only the custom MCP tools, and pre-approve them with `allowed_tools`.
- C. Lower `max_turns`.
- D. Set `max_budget_usd`.

**Answer: B.** Capabilities should be limited by **configuration**, not by instructions to the model. A prompt is guidance. A tool that isn't available can't be called. *POC link:* `tools=[]` and `allowed_tools` in `build_options()`.

---

### 8.4 Quick-recall cheat sheet

```
stop_reason == "tool_use"   → run tool(s), send tool_result(s) in ONE user message, loop again
stop_reason == "end_turn"   → done: return the final text
stop_reason == "max_tokens" → NOT done: cut off, handle explicitly
text / phrases / content[0] → never a termination signal
safety cap (e.g. 20)        → fallback only; when it fires: log a warning + investigate
tool failure                → tool_result with is_error=true, never an exception or empty text
Agent SDK "done"            → ResultMessage.subtype == "success" (+ stop_reason == "end_turn")
Agent SDK cap hit           → subtype "error_max_turns", then ResultError, no answer
```

---

## 9. How to run it

```bash
python poc2_exit_signal.py   # free, offline: shows why text-based "done" detection fails
python poc2_agent_loop.py    # 3 short API runs (uses ANTHROPIC_API_KEY from .env)
```

The exit code is `0` when all runs complete (including Run 3's expected cap), and `1` on a settings or SDK-runtime failure.
