"""
coordinator.py - the hub: run_coordinator() streams one coordinator call; decompose(), delegate() and
research_once() are the coordinator's jobs.

The coordinator never researches itself. It spawns a subagent by calling the built-in Agent tool. The SDK runs
that subagent in a fresh context that holds ONLY the Agent call's prompt, and returns the subagent's final
report as the Agent call's tool result. No subagent loop and no message passing in this code.
"""

import json
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultError,
    ResultMessage,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

from common import Settings, log, log_model_io
from research_setup import build_coordinator_options

SUBTOPICS_SCHEMA = {
    "type": "object",
    "properties": {"subtopics": {"type": "array", "items": {"type": "string"}}},
    "required": ["subtopics"],
}

SECTIONS_SCHEMA = {  # one section per subtopic, merged from both reports (C13)
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subtopic": {"type": "string"},
                    "web_findings": {"type": "string"},  # from web-searcher's report
                    "document_findings": {"type": "string"},  # from doc-analyst's report
                    "sources": {"type": "array", "items": {"type": "string"}},  # doc ids
                },
                "required": ["subtopic", "web_findings", "document_findings", "sources"],
            },
        }
    },
    "required": ["sections"],
}


def text_of(content: Any) -> str:
    """A tool result's text: content is a string or a list of {"type": "text", "text": ...} blocks."""
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content or ""


async def run_coordinator(prompt: str, options: ClaudeAgentOptions) -> dict[str, Any]:
    """Stream one coordinator query(). Returns {"output", "agent_calls", "subtype"}.

    output: ResultMessage.structured_output when the options ask for JSON, else the final text; None on failure.
    agent_calls: one {"id", "subagent_type", "prompt", "report"} per Agent call, in call order.
    """
    log.info("MODEL INPUT   prompt       [coordinator] %s", prompt)
    agent_names: dict[str, str] = {}  # Agent call id -> subagent name, for the log tags
    agent_calls: dict[str, dict[str, Any]] = {}
    output, subtype = None, None
    try:
        async for message in query(prompt=prompt, options=options):
            log_model_io(message, agent_names)
            if isinstance(message, AssistantMessage) and message.parent_tool_use_id is None:  # the hub's own response
                for block in message.content:
                    if isinstance(block, ToolUseBlock) and block.name in ("Agent", "Task"):  # "Task" on older versions
                        agent_calls[block.id] = {"id": block.id, "subagent_type": block.input.get("subagent_type"),
                                                 "prompt": block.input.get("prompt", ""), "report": None}
            elif isinstance(message, UserMessage) and isinstance(message.content, list):
                for block in message.content:
                    # A subagent's report is the tool result of the Agent call that spawned it (same id).
                    if isinstance(block, ToolResultBlock) and block.tool_use_id in agent_calls:
                        agent_calls[block.tool_use_id]["report"] = text_of(block.content)
            elif isinstance(message, ResultMessage):
                subtype = message.subtype
                if message.subtype == "success":  # JSON comes only from structured_output, never parsed from text
                    output = message.structured_output if options.output_format else message.result
            # No `break`: a few system events can still arrive after the ResultMessage.
    except ResultError as exc:  # raised AFTER the error ResultMessage (already logged), e.g. error_max_turns
        log.error("The coordinator call failed: %s", exc)
    return {"output": output, "agent_calls": list(agent_calls.values()), "subtype": subtype}


async def decompose(settings: Settings, topic: str) -> list[str]:
    """Job 1: split the topic into subtopics. One call with no tools: the coordinator only thinks (C5)."""
    prompt = f"Decompose this research topic into subtopics. Do not delegate yet. Topic: {topic}"
    result = await run_coordinator(prompt, build_coordinator_options(settings, SUBTOPICS_SCHEMA, with_agents=False))
    if result["output"] is None:
        raise RuntimeError("decompose() returned no subtopics")
    subtopics = result["output"]["subtopics"]
    # The breadth rule lives in COORDINATOR_PROMPT; Python checks the part it can check, deterministically.
    if len(subtopics) < 5 or len({s.lower() for s in subtopics}) < len(subtopics):
        raise ValueError(f"need at least 5 distinct subtopics, got {subtopics}")
    return subtopics


async def delegate(
    settings: Settings, topic: str, subtopics: list[str], gap_notes: dict[str, str] | None = None
) -> dict[str, Any]:
    """Jobs 2 and 3: brief both subagents, then merge their reports into one section per subtopic.

    The prompt names no subagent: Claude picks each one from its description (C2) and writes its prompt.
    """
    lines = [
        f'Research goal: a sourced overview of "{topic}" with key figures from Helios Institute sources.',
        f"Subtopics for this round (delegate only these, using these exact names): {json.dumps(subtopics)}",
    ]
    if gap_notes:  # a follow-up round: each gap with the reason it is a gap (POC 2)
        lines += ["Fix only these gaps:"] + [f"- {subtopic}: {reason}" for subtopic, reason in gap_notes.items()]
    lines.append("Delegate with one Agent call that finds sources for all of these subtopics, then one Agent call "
                 "that reads the documents those sources name. Return one section per subtopic.")
    result = await run_coordinator("\n".join(lines), build_coordinator_options(settings, SECTIONS_SCHEMA))
    if result["output"] is None:
        raise RuntimeError("delegate() returned no sections")
    return {"sections": result["output"]["sections"], "agent_calls": result["agent_calls"]}


async def research_once(settings: Settings, topic: str, subtopics: list[str] | None = None) -> dict[str, Any]:
    """The coordinator function (C3): a topic string in, a structured report out. One round, no loop."""
    subtopics = subtopics or await decompose(settings, topic)
    round_result = await delegate(settings, topic, subtopics)
    return {"topic": topic, "subtopics": subtopics, **round_result}
