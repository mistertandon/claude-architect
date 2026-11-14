"""
POC 2 - Parallel fan-out, metadata-preserving fan-in
=====================================================
Three runs of the same coordinator (with PARALLEL_RULE) and the same synthesizer:

    stripped handoff:  the synthesizer gets the 7 findings with content only  -> claims without sources
    full handoff:      the same 7 findings with all their metadata             -> every claim cites URL + page
    parallel pipeline: web-searcher and doc-analyst spawned in ONE response, both reports awaited, then the
                       synthesizer gets every finding unchanged

Only what the coordinator hands the synthesizer changes. Per run the code checks the metadata that reached the
synthesizer, the claims without a valid citation and the diagnosis, and for the pipeline the timing (compare it
with POC 1's sequential round).

Run:  python poc2_pipeline.py     (3 runs)
"""

import asyncio
import json
import sys

from claude_agent_sdk import ClaudeSDKError

from attribution_check import check_metadata_passed, delegation_timing, diagnose, strip_metadata, verify_attribution
from attribution_setup import FINDINGS, QUESTION, build_pipeline_options, parse_findings, parse_json_object
from common import load_settings
from coordinator import run_coordinator

# A controlled handoff: the coordinator must pass exactly the text in <<< >>>, so we decide what crosses it.
HANDOFF_TEST = (
    "Controlled handoff test. Call the synthesizer subagent once and pass it exactly the text between <<< and >>>, "
    "adding nothing: <<<Write a sourced brief answering the question below from these findings. "
    "Question: {question} Findings: {payload}>>> Then reply with its report unchanged."
)

RUNS = [
    ("stripped handoff", HANDOFF_TEST.format(question=QUESTION, payload=json.dumps({"findings": strip_metadata(FINDINGS)}))),
    ("full handoff", HANDOFF_TEST.format(question=QUESTION, payload=json.dumps({"findings": FINDINGS}))),
    ("parallel pipeline", f"Write a sourced brief answering: {QUESTION}"),  # the coordinator does it all itself
]


async def main() -> int:
    try:
        settings = load_settings()
    except (OSError, RuntimeError):
        return 1

    for name, prompt in RUNS:
        try:
            result = await run_coordinator(prompt, build_pipeline_options(settings, parallel=True))
        except ClaudeSDKError:  # Claude Code not found, its process crashed, ...
            return 1
        researchers = [c for c in result["agent_calls"] if c["subagent_type"] in ("web-searcher", "doc-analyst")]
        synthesizer = next((c for c in result["agent_calls"] if c["subagent_type"] == "synthesizer" and c["report"]), None)
        if synthesizer is None:
            continue
        try:
            # What should have crossed the handoff: the researchers' findings (pipeline), else the fixed 7.
            expected = [f for call in researchers for f in parse_findings(call["report"] or "")] or FINDINGS
            passed, total = check_metadata_passed(synthesizer["prompt"], expected)
            attribution = verify_attribution(parse_json_object(synthesizer["report"])["statements"], FINDINGS)
        except (ValueError, KeyError):  # a report or prompt without the expected JSON
            continue
        diagnosis = diagnose(passed, total, attribution)
        if researchers:  # the pipeline: one response spawned both, and the synthesizer waited for both (C15-C17)
            timing = delegation_timing(result["agent_calls"])
            waited = synthesizer["started"] > max(call["finished"] or 0.0 for call in researchers)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
