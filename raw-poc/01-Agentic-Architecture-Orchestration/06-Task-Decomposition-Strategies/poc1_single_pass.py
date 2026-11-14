"""
POC 1 - The single-pass review: every file in ONE request
==========================================================
The baseline the exam warns about: one call reviews the whole codebase at once and returns one structured review
per file plus the cross-file issues.

At real scale (the exam's example: 14 files) attention is spread thin: the first files get detailed feedback, the
last ones shallow or none, and identical code gets different verdicts. This repo has only 3 short files, so expect a
good review here: the POC shows the STRUCTURE you are going to replace, not the symptom.

score_review() checks per file the issue count and whether its planted bug was flagged, whether the code copied
into two files got the same verdict, and which cross-file issues were found.

Run:  python poc1_single_pass.py     (1 API run; 2 optional repeat trials)
"""

import asyncio
import sys
from pathlib import Path

from claude_agent_sdk import ClaudeSDKError

from common import load_settings
from review_setup import SINGLE_PASS_SCHEMA, build_review_options, format_file, load_repo, run_review, score_review

SINGLE_PASS_PROMPT = (
    "Review all {n} files of this codebase in one pass. Return one review per file, in the order given, then every "
    "cross-file issue: data flow between modules, inconsistent API usage, and patterns used differently across "
    "files. Name every file each cross-file issue involves.\n\n"
)

RUNS = [
    "trial 1",
    # "trial 2",  # optional: attention effects vary from run to run
    # "trial 3",  # optional
]


async def main() -> int:
    try:
        settings = load_settings()
        files = load_repo()
    except (OSError, RuntimeError, ValueError):
        return 1

    # ONE request holds every file: the whole codebase competes for the same attention.
    prompt = SINGLE_PASS_PROMPT.format(n=len(files)) + "\n\n".join(format_file(f) for f in files)
    for trial in RUNS:
        try:
            review = await run_review(prompt, build_review_options(settings, SINGLE_PASS_SCHEMA))
        except ClaudeSDKError:  # Claude Code not found, its process crashed, ...
            return 1
        if review is None:
            continue
        reviews = {Path(r["file"]).name.lower(): r for r in review["files"]}  # a file with no review counts as missed
        scores = score_review(reviews, files, review["cross_file_issues"])
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
