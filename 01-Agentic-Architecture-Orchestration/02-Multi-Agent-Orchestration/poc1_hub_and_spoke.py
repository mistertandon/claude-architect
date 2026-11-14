"""
POC 1 - Hub and spokes: one delegation round
=============================================
The coordinator (the hub) decomposes a topic, briefs two subagents (the spokes) through the Agent tool,
and merges their reports. Every log line names the agent it belongs to:

    MODEL INPUT   prompt       [coordinator] the task
    MODEL OUTPUT  tool_use     [coordinator] Agent {'subagent_type': 'web-searcher', 'prompt': ...}  (id=A)
    MODEL OUTPUT  tool_use     [web-searcher] mcp__research__web_search {...}  (id=B)
    MODEL INPUT   tool_result  [web-searcher] ...  (tool_use_id=B)
    MODEL INPUT   tool_result  [coordinator] the subagent's report  (tool_use_id=A)

Runs 2 and 3 test isolation: a subagent knows ONLY what the coordinator writes into the Agent prompt.

Run:  python poc1_hub_and_spoke.py     (3 runs, 4 query() calls)
"""

import asyncio
import sys

from claude_agent_sdk import ClaudeSDKError

from common import load_settings, log, setup_logging
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
        setup_logging("poc1_hub_and_spoke")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    try:
        # Run 1 (2 query() calls): decompose -> delegate to both spokes -> aggregate into sections.
        report = await research_once(settings, TOPIC)
        log.info("Categories the decomposition missed: %s", missing_categories(report["subtopics"]))  # [] expected

        # Runs 2-3: the same doc-analyst, briefed thin and then full. Poor result? Check the coordinator's brief first.
        for brief in BRIEFS:
            await run_coordinator(ISOLATION_TEST.format(brief=brief), build_coordinator_options(settings))
    except (RuntimeError, ValueError) as exc:  # a coordinator step returned nothing usable
        log.error("Stopped: %s", exc)
        return 1
    except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
        log.error("SDK error: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
