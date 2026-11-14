"""
POC 1b - Descriptions drive tool selection
==========================================
The same 10 queries run against the same two tools twice: first with one vague sentence per description, then with
five sentences (purpose, formats, examples, an edge case, a boundary). Names, schema, handlers, system prompt, model
and options never change, so a change in accuracy can only come from the description text.

Each query is scored on Claude's FIRST tool-calling response, never on the answer: after a misroute, the handler's
"No ... matches" error usually sends Claude to the other tool, and the final answer can be right anyway.

Besides model I/O, the log shows one line per query (expected tool, first tools, correct or MISROUTED), the accuracy
of each pass, and one closing line with the queries the new descriptions fixed.

Run (after the free demo: python poc1_descriptions.py):
    python poc1_selection_test.py     (2 runs, 10 query() calls each)
"""

import asyncio
import sys

from claude_agent_sdk import ClaudeSDKError

from common import Settings, load_settings, log, setup_logging
from routing_setup import QUERIES, build_routing_options, compare_versions, run_agent

OVERLAP = {3, 4, 5, 6, 8, 9}  # the queries both minimal descriptions seem to answer; 1, 2, 7 and 10 are controls (C3)

RUNS = [
    "minimal",  # typically 6-8 of 10 correct: the misroutes are overlap queries (C6)
    "improved",  # typically 9-10 of 10 (C10)
]


def accuracy(rows: list[dict]) -> int:
    return sum(row["correct"] for row in rows)


async def evaluate(settings: Settings, version: str) -> list[dict]:
    """Run the 10 QUERIES with one description version. One row per query (C4)."""
    rows = []
    for n, (query_text, expected) in enumerate(QUERIES, 1):
        run = await run_agent(query_text, build_routing_options(settings, version))
        first_tools = [name.split("__")[-1] for name in run["first_response_tools"]]
        # Score ONLY the first choice: calling both tools at once (a hedge) or no tool counts as wrong (E1)
        correct = run["first_response_tools"] == [f"mcp__lumen__{expected}"]
        log.info("[%s] #%d expected %s, first response called %s -> %s", version, n, expected, first_tools or "no tool",
                 "correct" if correct else f"MISROUTED ({'overlap' if n in OVERLAP else 'control'} query)")
        rows.append({"n": n, "query": query_text, "expected": expected, "first_tools": first_tools, "correct": correct,
                     "tool_calls": run["tool_calls"], "answer": run["answer"]})
    log.info("Selection accuracy (%s): %d/10", version, accuracy(rows))  # (C5)
    return rows


async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc1_selection_test")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    rows = {}
    for version in RUNS:
        try:
            rows[version] = await evaluate(settings, version)
        except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
            log.error("SDK error: %s", exc)
            return 1

    # Wrong with the vague descriptions, right with the new ones: fixed by a text edit alone (C8, C10, C11)
    fixed = [old["n"] for old, new in zip(rows["minimal"], rows["improved"]) if not old["correct"] and new["correct"]]
    log.info("Accuracy %d/10 -> %d/10, fixed queries %s. Changed: %d description strings; no code, schema, handler, "
             "prompt or model", accuracy(rows["minimal"]), accuracy(rows["improved"]), fixed, len(compare_versions()))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
