"""
POC 2 - Decompose the review: per-file passes, then one integration pass
=========================================================================
Python decides the split, so it is the same every time (prompt chaining):

    layer 1:  one NEW session per file   -> the file gets the whole attention budget; its review also records
              (pricing, checkout, ...)      its interface: what it exports and what it assumes about other files
    layer 2:  one session over the per-file summaries only (no code)  -> data flow, API and pattern mismatches

Same model, same reviewer prompt and same per-file schema as POC 1: only the structure changed. A per-file pass
sees one file, so it can never report a two-file issue; the integration pass exists for exactly those.

score_review() scores it the same way as POC 1: compare the two.

Run:  python poc2_multi_pass.py     (1 run: 3 per-file calls + 1 integration call)
"""

import asyncio
import json
import sys
from typing import Any

from claude_agent_sdk import ClaudeSDKError

from common import Settings, load_settings
from review_setup import (
    FILE_REVIEW_SCHEMA,
    INTEGRATION_SCHEMA,
    build_review_options,
    format_file,
    load_repo,
    run_review,
    score_review,
)

FILE_PROMPT = "Review this one file from a {n}-file codebase. You can see only this file.\n\n{listing}"
INTEGRATION_PROMPT = (
    "These are the per-file summaries of one TypeScript codebase; the code itself is not included. Find cross-file "
    "issues only: data flow problems between modules, inconsistent API usage (a caller's assumptions that contradict "
    "the callee's contract), and patterns or conventions used differently across files. Name every file each issue "
    "involves. Do not repeat single-file issues.\n\n"
)

RUNS = ["multi-pass"]


async def multi_pass(settings: Settings, files: list[dict[str, Any]]) -> tuple[dict[str, dict], list[dict]]:
    reviews = {}
    for f in files:  # layer 1: a plain loop, each call a fresh session that holds ONE file (C5)
        review = await run_review(FILE_PROMPT.format(n=len(files), listing=format_file(f)),
                                  build_review_options(settings, FILE_REVIEW_SCHEMA))
        if review is None:
            raise RuntimeError(f"no review for {f['name']}")
        reviews[f["name"]] = review
    # layer 2: the interfaces only, no code and no local issues (C8)
    summaries = [{"file": name, "exports": r["exports"], "uses": r["uses"]} for name, r in reviews.items()]
    integration = await run_review(INTEGRATION_PROMPT + json.dumps(summaries, indent=2),
                                   build_review_options(settings, INTEGRATION_SCHEMA))
    if integration is None:
        raise RuntimeError("no integration review")
    return reviews, integration["cross_file_issues"]


async def main() -> int:
    try:
        settings = load_settings()
        files = load_repo()
    except (OSError, RuntimeError, ValueError):
        return 1

    for name in RUNS:
        try:
            reviews, cross_file_issues = await multi_pass(settings, files)
        except RuntimeError:  # a pass returned no structured review
            return 1
        except ClaudeSDKError:  # Claude Code not found, its process crashed, ...
            return 1
        scores = score_review(reviews, files, cross_file_issues)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
