"""
coordinator.py - run_coordinator() streams one coordinator call: 02's runner, extended with when each Agent call
started and finished, which tools the session had, and every research tool call.

The coordinator spawns a subagent by calling the built-in Agent tool. The SDK runs that subagent in a fresh
context that holds ONLY the Agent call's prompt, and returns its final message as the Agent call's tool result.
"""

import time
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultError,
    ResultMessage,
    SystemMessage,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)


def text_of(content: Any) -> str:
    """A tool result's text: content is a string or a list of {"type": "text", "text": ...} blocks."""
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content or ""


async def run_coordinator(prompt: str, options: ClaudeAgentOptions) -> dict[str, Any]:
    """Stream one coordinator query(). Returns {"output", "agent_calls", "research_calls", "init_tools", "subtype"}.

    agent_calls: one {"id", "subagent_type", "prompt", "report", "message_id", "started", "finished"} per Agent
        call. started/finished: seconds since this call began, when the call and its report arrived.
    research_calls: one {"name", "input", "parent_tool_use_id"} per other tool call, from any agent.
    init_tools: the session's tool list from the system:init message (it names the Agent tool "Task").
    """
    begin = time.monotonic()
    agent_calls: dict[str, dict[str, Any]] = {}
    research_calls: list[dict[str, Any]] = []
    init_tools: list[str] = []
    output, subtype = None, None
    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, SystemMessage) and message.subtype == "init":
                init_tools = message.data.get("tools", [])
            elif isinstance(message, AssistantMessage):
                for block in message.content:
                    if not isinstance(block, ToolUseBlock) or block.name == "StructuredOutput":
                        continue
                    if block.name in ("Agent", "Task") and message.parent_tool_use_id is None:  # a spawn
                        agent_calls[block.id] = {
                            "id": block.id, "subagent_type": block.input.get("subagent_type"),
                            "prompt": block.input.get("prompt", ""), "report": None,
                            "message_id": message.message_id,  # Agent calls in ONE response share it (C15)
                            "started": time.monotonic() - begin, "finished": None,
                        }
                    else:
                        research_calls.append({"name": block.name, "input": block.input,
                                               "parent_tool_use_id": message.parent_tool_use_id})
            elif isinstance(message, UserMessage) and isinstance(message.content, list):
                for block in message.content:
                    # A subagent's report is the tool result of the Agent call that spawned it (same id).
                    if isinstance(block, ToolResultBlock) and block.tool_use_id in agent_calls:
                        agent_calls[block.tool_use_id]["report"] = text_of(block.content)
                        agent_calls[block.tool_use_id]["finished"] = time.monotonic() - begin
            elif isinstance(message, ResultMessage):
                subtype = message.subtype
                if message.subtype == "success":
                    output = message.structured_output if options.output_format else message.result
            # No `break`: a few system events can still arrive after the ResultMessage.
    except ResultError:  # raised AFTER the error ResultMessage, e.g. error_max_turns
        pass
    return {"output": output, "agent_calls": list(agent_calls.values()), "research_calls": research_calls,
            "init_tools": init_tools, "subtype": subtype}
