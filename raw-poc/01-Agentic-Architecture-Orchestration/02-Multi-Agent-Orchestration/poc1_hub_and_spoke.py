"""
POC 1 - Hub and spokes: one delegation round
=============================================
The coordinator (the hub) decomposes a topic, briefs two subagents (the spokes) through the Agent tool,
and merges their reports:

    coordinator   Agent {'subagent_type': 'web-searcher', 'prompt': ...}  (id=A)
    web-searcher  mcp__research__web_search {...}  (id=B)
    web-searcher  tool_result ...  (tool_use_id=B)
    coordinator   tool_result: the subagent's report  (tool_use_id=A)

Runs 2 and 3 test isolation: a subagent knows ONLY what the coordinator writes into the Agent prompt.

Run:  python poc1_hub_and_spoke.py     (3 runs, 4 query() calls)
"""

import asyncio
import sys

from claude_agent_sdk import ClaudeSDKError

from common import load_settings
from coordinator import research_once, run_coordinator
from research_setup import build_coordinator_options, missing_categories

TOPIC = "renewable energy technologies"

# The isolation test: the coordinator knows the doc id, but must pass the subagent exactly the brief in <<< >>>.
ISOLATION_TEST = (
    "Controlled isolation test. Your notes say the Helios document on tidal energy is HX-TID-4. "
    "Call the doc-analyst subagent once and pass it exactly the text between <<< and >>>, adding nothing: "
    "<<<{brief}>>> Then reply with its report unchanged."
)
BRIEFS = [
    # thin: no goal and no doc id. The subagent never saw the coordinator's notes, so it can't find the document.
    "Analyse the Helios document on tidal energy and report its key figures.",
    # full: the goal, the subtopic and the context a prior agent produced. Same subagent, only the brief changed.
    "Research goal: a sourced overview of renewable energy technologies. Subtopic: tidal energy. Context from the "
    "web-searcher: the Helios entry for tidal energy is document HX-TID-4. Read it and report its key figures.",
]


async def main() -> int:
    try:
        settings = load_settings()
    except (OSError, RuntimeError):
        return 1

    try:
        # Run 1 (2 query() calls): decompose -> delegate to both spokes -> aggregate into sections.
        report = await research_once(settings, TOPIC)
        missed = missing_categories(report["subtopics"])  # categories the decomposition missed: [] expected

        # Runs 2-3: the same doc-analyst, briefed thin and then full. Poor result? Check the coordinator's brief first.
        for brief in BRIEFS:
            await run_coordinator(ISOLATION_TEST.format(brief=brief), build_coordinator_options(settings))
    except (RuntimeError, ValueError):  # a coordinator step returned nothing usable
        return 1
    except ClaudeSDKError:  # Claude Code not found, its process crashed, ...
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
