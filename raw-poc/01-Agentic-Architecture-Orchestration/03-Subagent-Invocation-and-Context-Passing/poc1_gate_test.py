"""
POC 1 - The Agent tool is the gate; subagents return content + metadata
========================================================================
The same coordinator, the same subagent definitions and the same request, run twice:

    gate on:   tools=["Agent"]  -> web-searcher, then doc-analyst (one after the other, as SEQUENTIAL_RULE says)
    gate off:  tools=[]         -> no subagent can start, although the prompt asks for them by role

Each research subagent answers with JSON findings that keep content (claim, analysis) apart from metadata
(source_url, document_name, page_number, confidence, retrieved_by). Per run the code checks the session's tools
and the Agent calls, the findings per subagent, and the timing of the round.

Run:  python poc1_gate_test.py     (2 runs; an optional third is commented out)
"""

import asyncio
import sys

from claude_agent_sdk import ClaudeSDKError

from attribution_check import delegation_timing
from attribution_setup import CONTENT_FIELDS, METADATA_FIELDS, QUESTION, build_pipeline_options, parse_findings
from common import load_settings
from coordinator import run_coordinator

RESEARCH_PROMPT = (
    "Research this question with both research subagents, then reply with one line saying both reports are in. "
    f"Do not call the synthesizer. Question: {QUESTION}"
)

RUNS = [  # (name, switches for build_pipeline_options())
    ("gate on", {}),  # Agent in tools and in allowed_tools: the sequential research round
    ("gate off", {"agent_tool": False}),  # Agent removed from the tool set: no subagent can run
    # ("unlisted", {"approve_agent": False}),  # optional (E1): Agent in tools but NOT in allowed_tools: still spawns
]


async def main() -> int:
    try:
        settings = load_settings()
    except (OSError, RuntimeError):
        return 1

    for name, switches in RUNS:
        try:
            result = await run_coordinator(RESEARCH_PROMPT, build_pipeline_options(settings, **switches))
        except ClaudeSDKError:  # Claude Code not found, its process crashed, ...
            return 1
        # The gate is the session's tool set, fixed when query() starts ("Task" is the Agent tool's init name).
        session_tools, agent_call_count = result["init_tools"], len(result["agent_calls"])
        for call in result["agent_calls"]:
            try:
                findings = parse_findings(call["report"] or "")
            except ValueError:
                continue
            missing = sorted({key for f in findings for key in CONTENT_FIELDS + METADATA_FIELDS if key not in f})
        if result["agent_calls"]:  # compare with POC 2's parallel round (C16)
            timing = delegation_timing(result["agent_calls"])
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
