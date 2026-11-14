"""
POC 2b - System-prompt keyword conflicts
========================================
The 4 order queries of POC 1 (2, 4, 5 and 6) run with the IMPROVED descriptions, the ones that routed 9-10 of 10
correctly, under two system prompts:

    conflict   "Always check customer details before ..." / "... retrieve the customer information first."
    fixed      the same intent, rewritten with precise conditions (see python poc2_prompt_audit.py)

Every order row already says who placed the order, so no query needs get_customer. The descriptions are the same
in both arms: extra get_customer calls in the conflict arm can only come from the system prompt.

Besides model I/O, the log shows one line per query (first tools, and whether get_customer was called at all) and
one count line per arm.

Run (after the free audit: python poc2_prompt_audit.py):
    python poc2_prompt_conflict.py     (2 runs, 4 query() calls each)
"""

import asyncio
import sys

from claude_agent_sdk import ClaudeSDKError

from common import Settings, load_settings, log, setup_logging
from routing_setup import (CONFLICT_PROMPT, FIXED_PROMPT, GET_CUSTOMER, LOOKUP_ORDER, QUERIES, build_routing_options,
                           run_agent)

ORDER_QUERIES = [(n, query_text) for n, (query_text, expected) in enumerate(QUERIES, 1) if expected == "lookup_order"]

RUNS = [
    ("conflict", CONFLICT_PROMPT),  # typically 2 or more of 4 call get_customer, first or as an extra round trip
    ("fixed", FIXED_PROMPT),  # typically 0 of 4: every first choice is lookup_order, as in POC 1
]


async def compare_prompts(settings: Settings, arm: str, system_prompt: str) -> None:
    """Run the 4 order queries under one system prompt, always with the improved descriptions (C13)."""
    extra_calls = misroutes = 0
    for n, query_text in ORDER_QUERIES:
        run = await run_agent(query_text, build_routing_options(settings, "improved", system_prompt))
        called_customer = GET_CUSTOMER in run["tool_calls"]  # anywhere: first (a misroute) or later (a wasted trip)
        misrouted = run["first_response_tools"] != [LOOKUP_ORDER]
        extra_calls += called_customer
        misroutes += misrouted
        log.info("[%s] #%d first response called %s; get_customer called: %s", arm, n,
                 [name.split("__")[-1] for name in run["first_response_tools"]] or "no tool", called_customer)
    log.info("Arm %s: %d of 4 order queries called get_customer; %d first-tool misroutes", arm, extra_calls, misroutes)


async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc2_prompt_conflict")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    for arm, system_prompt in RUNS:
        try:
            await compare_prompts(settings, arm, system_prompt)
        except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
            log.error("SDK error: %s", exc)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
