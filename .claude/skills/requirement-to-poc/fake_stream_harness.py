"""
fake_stream_harness.py - check a POC offline: replay fake SDK streams through one of its scripts.
No API call, no cost. Used by step 6 of /requirement-to-poc; never copy it into a POC folder.

The SCENARIOS section below is the worked example for 01-Agentic-Loops (poc1_round_trip.py and
poc2_agent_loop.py). For another POC, copy this file to the scratchpad and replace that section:
one scenario per prompt in the scripts, including every error path the code catches. A scenario is
`async def play(prompt, options)` and yields messages; parse the prompt when the fake answer depends on it.

Builders for the other cases (worked examples: 02- to 06- of domain 01, built 2026-10-27):
  structured()        output_format's StructuredOutput call (pair it with result(structured_output=...))
  subagent_call()     an Agent call, the subagent's round trips (parent_tool_use_id), and its report
  hook_round_trip()   one tool call through the POC's real PreToolUse / PostToolUse callbacks
  capture_handlers()  real handlers of tools defined inside a function (closures over a session)

Usage (scratchpad venv, on a COPY of the POC folder that has a dummy .env):
    python fake_stream_harness.py <poc copy dir> <script module>
    e.g. python fake_stream_harness.py /tmp/.../01-Agentic-Loops poc1_round_trip
Run one script per process: every main() adds its own log handlers.
"""

import asyncio
import importlib
import os
import re
import sys
from collections.abc import AsyncIterator, Callable
from typing import Any

if len(sys.argv) != 3:
    sys.exit(__doc__)
POC_DIR, MODULE = sys.argv[1], sys.argv[2]
sys.path.insert(0, POC_DIR)  # import the POC's own modules (common.py, tools.py, ...)

from claude_agent_sdk import (  # noqa: E402
    AssistantMessage,
    ResultError,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

MODEL = "claude-sonnet-5-5"  # only a label inside the fake messages
TOOL_RESPONSE_SHAPE = os.environ.get("SHAPE", "list")  # how hook_round_trip passes tool_response: list | dict | str

# ---------------------------------------------------------------- builders: messages as the SDK streams them


def init(tools: list[str]) -> SystemMessage:
    """The first message of every real stream."""
    return SystemMessage(subtype="init", data={"type": "system", "subtype": "init", "model": MODEL, "tools": tools})


def assistant(block: Any, message_id: str, parent_tool_use_id: str | None = None) -> AssistantMessage:
    """One content block per AssistantMessage. Set parent_tool_use_id for a subagent's messages."""
    return AssistantMessage(content=[block], model=MODEL, message_id=message_id, parent_tool_use_id=parent_tool_use_id)


async def round_trip(
    handlers: dict[str, Callable], tool_use_id: str, name: str, tool_input: dict[str, Any], message_id: str,
    parent_tool_use_id: str | None = None,
) -> AsyncIterator[Any]:
    """tool_use -> the POC's REAL handler runs, as the SDK would run it -> tool_result with the same id."""
    yield assistant(ToolUseBlock(id=tool_use_id, name=name, input=tool_input), message_id, parent_tool_use_id)
    output = await handlers[name](tool_input)
    yield UserMessage(
        content=[ToolResultBlock(tool_use_id=tool_use_id, content=output["content"], is_error=output.get("is_error"))],
        parent_tool_use_id=parent_tool_use_id,
    )


def result(
    text: str | None = None, subtype: str = "success", stop_reason: str = "end_turn", num_turns: int = 1, **fields: Any
) -> ResultMessage:
    """The end signal. The timing and session fields are required, so they get dummy values."""
    return ResultMessage(
        subtype=subtype, duration_ms=1000, duration_api_ms=900, is_error=subtype != "success", num_turns=num_turns,
        session_id="fake-session", stop_reason=stop_reason, total_cost_usd=0.01, result=text, **fields,
    )


def result_error(subtype: str, message: str) -> ResultError:
    """What a single-shot query() raises AFTER it has yielded the error ResultMessage."""
    return ResultError(
        f"Claude Code returned an error result: {message}",
        data={"subtype": subtype, "errors": [message], "session_id": "fake-session"},
        exit_code=1,
    )


async def structured(data: dict[str, Any], message_id: str, tool_use_id: str = "toolu_so") -> AsyncIterator[Any]:
    """output_format: Claude hands in its JSON through the built-in StructuredOutput tool."""
    yield assistant(ToolUseBlock(id=tool_use_id, name="StructuredOutput", input=data), message_id)
    yield UserMessage(content=[ToolResultBlock(
        tool_use_id=tool_use_id, content=[{"type": "text", "text": "Structured output provided successfully"}])])


async def subagent_call(
    handlers: dict[str, Callable], agent_id: str, subagent_type: str, prompt: str,
    calls: list[tuple[str, dict[str, Any]]], message_id: str, report: str | None = None,
) -> AsyncIterator[Any]:
    """The main agent's Agent call -> the subagent's round trips (parent_tool_use_id=agent_id) -> its report, which
    comes back as the Agent call's tool result with the agentId trailer. By default the report joins the tool texts.
    For a parallel spawn, yield two Agent tool_use blocks with the same message_id and interleave the round trips."""
    yield assistant(ToolUseBlock(id=agent_id, name="Agent", input={
        "subagent_type": subagent_type, "description": f"{subagent_type} task", "prompt": prompt}), message_id)
    texts = []
    for n, (name, tool_input) in enumerate(calls, 1):
        async for message in round_trip(handlers, f"{agent_id}_t{n}", name, tool_input, f"{agent_id}_m{n}", agent_id):
            if isinstance(message, UserMessage):
                texts.append(message.content[0].content[0]["text"])
            yield message
    yield UserMessage(content=[ToolResultBlock(tool_use_id=agent_id, content=[
        {"type": "text", "text": report if report is not None else "\n".join(texts)},
        {"type": "text", "text": "agentId: a0b1c2d3"}])])


def matches(matcher: str | None, tool_name: str) -> bool:
    """Claude Code's matcher rules: none, "" or "*" match all; only letters, digits, _ - space , | = exact names;
    anything else is an UNANCHORED regex ("mcp__orders__.*" = every tool of that server)."""
    if matcher in (None, "", "*"):
        return True
    if re.fullmatch(r"[A-Za-z0-9_\- ,|]+", matcher):
        return tool_name in [name.strip() for name in re.split(r"[|,]", matcher)]
    return re.search(matcher, tool_name) is not None


async def hook_round_trip(
    options: Any, handlers: dict[str, Callable], tool_use_id: str, name: str, tool_input: dict[str, Any], message_id: str,
) -> AsyncIterator[Any]:
    """One tool call through the hook pipeline, as Claude Code runs it: PreToolUse (a deny becomes the tool result
    and the handler never runs) -> the REAL handler -> PostToolUse (updatedToolOutput replaces the result; "block"
    only adds its reason; an error result skips PostToolUse, which fires PostToolUseFailure instead)."""
    yield assistant(ToolUseBlock(id=tool_use_id, name=name, input=tool_input), message_id)
    base = {"session_id": "fake-session", "cwd": POC_DIR, "transcript_path": "/dev/null",
            "tool_name": name, "tool_input": tool_input, "tool_use_id": tool_use_id}

    async def fire(event: str, input_data: dict) -> list[dict]:
        return [await callback({**base, **input_data, "hook_event_name": event}, tool_use_id, {"signal": None})
                for matcher in (options.hooks or {}).get(event, []) if matches(matcher.matcher, name)
                for callback in matcher.hooks]

    denials = [out["hookSpecificOutput"]["permissionDecisionReason"] for out in await fire("PreToolUse", {})
               if out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"]
    if denials:
        yield UserMessage(content=[ToolResultBlock(tool_use_id=tool_use_id, content=denials[0], is_error=True)])
        return
    output = await handlers[name](tool_input)
    content, is_error = output["content"], output.get("is_error") or None
    if not is_error:
        shaped = {"dict": {"content": content}, "str": "".join(c["text"] for c in content)}.get(TOOL_RESPONSE_SHAPE, content)
        for out in await fire("PostToolUse", {"tool_response": shaped}):
            replacement = out.get("hookSpecificOutput", {}).get("updatedToolOutput")
            if replacement is not None:
                content = replacement.get("content", []) if isinstance(replacement, dict) else (
                    [{"type": "text", "text": replacement}] if isinstance(replacement, str) else replacement)
            if out.get("decision") == "block":  # the reason goes NEXT TO the original output
                content = content + [{"type": "text", "text": out["reason"]}]
    yield UserMessage(content=[ToolResultBlock(tool_use_id=tool_use_id, content=content, is_error=is_error)])


def capture_handlers(setup_module: Any) -> None:
    """For tools defined inside a function (closures over a session, 04/05): wrap the module's create_sdk_mcp_server
    so each server config carries its real handlers under "_handlers". Call it before the POC builds its options;
    a scenario then reads next(iter(options.mcp_servers.values()))["_handlers"]."""
    real_create = setup_module.create_sdk_mcp_server

    def capturing(name: str, version: str = "1.0.0", tools: list | None = None) -> Any:
        config = real_create(name=name, version=version, tools=tools)
        config["_handlers"] = {f"mcp__{name}__{t.name}": t.handler for t in tools or []}
        return config

    setup_module.create_sdk_mcp_server = capturing


# ---------------------------------------------------------------- SCENARIOS (01-Agentic-Loops): replace per POC

from tools import CALCULATOR, WEB_SEARCH, calculator, web_search  # noqa: E402  (the POC's real tools)

HANDLERS = {CALCULATOR: calculator.handler, WEB_SEARCH: web_search.handler}
TOOLS = list(HANDLERS)


async def math(prompt: str, options: Any) -> AsyncIterator[Any]:
    yield assistant(ThinkingBlock(thinking="The user wants 1,234 x 5,678. I'll use the calculator.", signature="s"), "msg_1")
    async for message in round_trip(HANDLERS, "toolu_1", CALCULATOR, {"expression": "1234 * 5678"}, "msg_1"):
        yield message
    yield assistant(TextBlock("1,234 x 5,678 = 7,006,652."), "msg_2")
    yield result("1,234 x 5,678 = 7,006,652.", num_turns=2)


async def share_price(prompt: str, options: Any) -> AsyncIterator[Any]:
    yield assistant(ThinkingBlock(thinking="", signature="s"), "msg_1")  # thinking display omitted: empty text
    async for message in round_trip(HANDLERS, "toolu_1", WEB_SEARCH, {"query": "Nimbus Robotics share price"}, "msg_1"):
        yield message
    yield assistant(TextBlock("Nimbus Robotics last traded at $187.42."), "msg_2")
    yield result("Nimbus Robotics last traded at $187.42.", num_turns=2)


async def no_tool(prompt: str, options: Any) -> AsyncIterator[Any]:
    yield assistant(TextBlock("An API is a defined way for programs to talk to each other."), "msg_1")
    yield result("An API is a defined way for programs to talk to each other.")


async def failing_tool(prompt: str, options: Any) -> AsyncIterator[Any]:
    async for message in round_trip(HANDLERS, "toolu_1", CALCULATOR, {"expression": "2 ** 10"}, "msg_1"):
        yield message  # is_error=True: the handler rejects **
    async for message in round_trip(HANDLERS, "toolu_2", CALCULATOR, {"expression": "2*2*2*2*2*2*2*2*2*2"}, "msg_2"):
        yield message
    yield assistant(TextBlock("** isn't supported, so I multiplied: 2^10 = 1024."), "msg_3")
    yield result("2^10 = 1024", num_turns=3)


async def sequential(prompt: str, options: Any) -> AsyncIterator[Any]:
    yield assistant(ThinkingBlock(thinking="I need the price first, then the total with the fee.", signature="s"), "msg_1")
    async for message in round_trip(HANDLERS, "toolu_1", WEB_SEARCH, {"query": "Nimbus Robotics share price"}, "msg_1"):
        yield message
    if options.max_turns == 1:  # the cap fires while Claude still wants a tool: no answer
        yield result(subtype="error_max_turns", stop_reason="tool_use", num_turns=2,
                     errors=["Reached maximum number of turns (1)"])
        raise result_error("error_max_turns", "Reached maximum number of turns (1)")
    async for message in round_trip(HANDLERS, "toolu_2", CALCULATOR, {"expression": "187.42 * 37 * 1.015"}, "msg_2"):
        yield message
    yield assistant(TextBlock("37 shares would cost about $7,038.56 including the 1.5% fee."), "msg_3")
    yield result("37 shares would cost about $7,038.56 including the 1.5% fee.", num_turns=3)


async def parallel(prompt: str, options: Any) -> AsyncIterator[Any]:
    calls = [("toolu_1", {"expression": "12 * 7"}), ("toolu_2", {"expression": "99 / 3"})]
    for tool_use_id, tool_input in calls:  # two tool_use blocks in ONE response (same message_id)
        yield assistant(ToolUseBlock(id=tool_use_id, name=CALCULATOR, input=tool_input), "msg_1")
    for tool_use_id, tool_input in calls:
        output = await calculator.handler(tool_input)
        yield UserMessage(content=[ToolResultBlock(tool_use_id=tool_use_id, content=output["content"])])
    yield assistant(TextBlock("12 x 7 = 84 and 99 / 3 = 33."), "msg_2")
    yield result("12 x 7 = 84 and 99 / 3 = 33.", num_turns=2)


# prompt substring -> scenario (the first match wins)
SCENARIOS: dict[str, Callable[[str, Any], AsyncIterator[Any]]] = {
    "1,234": math,  # poc1: calculator
    "share price right now": share_price,  # poc1: web_search
    "what is an API": no_tool,  # poc1 and poc2: no tool
    "2 ** 10": failing_tool,  # poc1 optional: a failing tool call
    "37 shares": sequential,  # poc2: search -> calculate, and the max_turns=1 cap
    "12 times 7": parallel,  # poc2 optional: two tool calls in one response
}

# ---------------------------------------------------------------- the fake query() and the runner


async def fake_query(*, prompt: str, options: Any = None, **_: Any) -> AsyncIterator[Any]:
    """Stands in for claude_agent_sdk.query(): plays the scenario whose key appears in the prompt."""
    scenario = next((play for key, play in SCENARIOS.items() if key in prompt), None)
    if scenario is None:
        raise KeyError(f"no scenario for prompt {prompt[:60]!r}: add one to SCENARIOS")
    yield init(TOOLS)
    async for message in scenario(prompt, options):
        yield message
    yield SystemMessage(subtype="session_state_changed", data={})  # events can follow the ResultMessage


def main() -> int:
    module = importlib.import_module(MODULE)
    for loaded in list(sys.modules.values()):  # query() may be imported by the script, coordinator.py, a setup module
        if str(getattr(loaded, "__file__", "") or "").startswith(POC_DIR) and hasattr(loaded, "query"):
            loaded.query = fake_query
    code = asyncio.run(module.main())
    print(f"\n[harness] {MODULE}.main() returned {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
