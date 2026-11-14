"""
POC 1 - Vague words against explicit criteria
==============================================
Three system prompts review the same 5 snippets. Nothing else changes: same model, schema, snippets, options.

    vague      "Be conservative and only flag important issues."     -> no decision boundary
    criteria   REPORT bugs/security/contradicting comments, SKIP style and local patterns, severities in prose
    examples   the same criteria, severities defined by CODE examples instead of prose

The snippets hold 9 real defects (R1-R9) and 7 decoys (D1-D7): style, local patterns and harmless comments that a
precise reviewer must NOT report. Each review is scored against that answer key.

The code scores each review (false positives, every spot's verdict), then summarizes each prompt: false-positive
rate, inconsistency (wrong verdicts), stable spots and severity accuracy.

Run:  python poc1_vague_vs_explicit.py     (3 runs, 1 query() call each; 3 optional repeats)
"""

import asyncio
import sys
from collections import defaultdict

from claude_agent_sdk import ClaudeSDKError

from common import load_settings
from criteria_setup import (
    CRITERIA_PROMPT,
    EXAMPLES_PROMPT,
    PLANTED,
    VAGUE_PROMPT,
    is_right,
    load_snippets,
    review,
    score_run,
    summarize,
)

PROMPTS = [
    ("vague", VAGUE_PROMPT),  # step 1: the baseline
    ("criteria", CRITERIA_PROMPT),  # step 2: explicit categories
    ("examples", EXAMPLES_PROMPT),  # step 3: plus code examples per severity
    # ("vague", VAGUE_PROMPT),  # optional: a second run of each prompt shows run-to-run drift (C6, C14)
    # ("criteria", CRITERIA_PROMPT),  # optional
    # ("examples", EXAMPLES_PROMPT),  # optional
]


async def main() -> int:
    try:
        settings = load_settings()
        files = load_snippets()
    except (OSError, RuntimeError):
        return 1

    runs = defaultdict(list)
    for label, system_prompt in PROMPTS:
        try:
            findings = await review(settings, system_prompt, files)
        except ClaudeSDKError:  # Claude Code not found, its process crashed, ...
            return 1
        if findings is None:
            continue
        scored = score_run(findings, files)
        runs[label].append(scored)
        wrong = sum(not is_right(s, scored["verdicts"][s["id"]]) for s in PLANTED)

    for label, label_runs in runs.items():  # the evidence, side by side (C12)
        s = summarize(label_runs)  # same model, schema, snippets and options: only the system prompt changed
        wrong, verdicts = s["inconsistency"]
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
