"""
POC 1 - The Agent tool is the gate; subagents return content + metadata
========================================================================
The same coordinator, the same subagent definitions and the same request, run twice:

    gate on:   tools=["Agent"]  -> web-searcher, then doc-analyst (one after the other, as SEQUENTIAL_RULE says)
    gate off:  tools=[]         -> no subagent can start, although the prompt asks for them by role

Each research subagent answers with JSON findings that keep content (claim, analysis) apart from metadata
(source_url, document_name, page_number, confidence, retrieved_by). Besides model I/O, the log shows per run:
the session's tools and the Agent calls, the findings per subagent, and the timing of the round.

Run:  python poc1_gate_test.py     (2 runs; an optional third is commented out)
"""

import asyncio
import sys

from claude_agent_sdk import ClaudeSDKError

from attribution_check import delegation_timing
from attribution_setup import CONTENT_FIELDS, METADATA_FIELDS, QUESTION, build_pipeline_options, parse_findings
from common import load_settings, log, setup_logging
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
        setup_logging("poc1_gate_test")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    for name, switches in RUNS:
        try:
            result = await run_coordinator(RESEARCH_PROMPT, build_pipeline_options(settings, **switches))
        except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
            log.error("SDK error: %s", exc)
            return 1
        # The gate is the session's tool set, fixed when query() starts ("Task" is the Agent tool's init name).
        log.info("Run '%s': session tools %s -> %d Agent call(s)", name, result["init_tools"], len(result["agent_calls"]))
        for call in result["agent_calls"]:
            try:
                findings = parse_findings(call["report"] or "")
            except ValueError as exc:
                log.error("%s's report: %s", call["subagent_type"], exc)
                continue
            missing = sorted({key for f in findings for key in CONTENT_FIELDS + METADATA_FIELDS if key not in f})
            log.info("%s returned %d findings, missing fields: %s", call["subagent_type"], len(findings), missing or "none")
        if result["agent_calls"]:  # compare with POC 2's parallel round (C16)
            timing = delegation_timing(result["agent_calls"])
            log.info("Delegation: %d response(s), overlap=%s, %.1f s in all (%s)",
                     timing["responses"], timing["overlap"], timing["delegation_seconds"],
                     ", ".join(f"{agent} {seconds:.1f} s" for agent, seconds in timing["durations"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
