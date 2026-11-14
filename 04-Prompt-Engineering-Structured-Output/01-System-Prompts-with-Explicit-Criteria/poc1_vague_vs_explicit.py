"""
POC 1 - Vague words against explicit criteria
==============================================
Three system prompts review the same 5 snippets. Nothing else changes: same model, schema, snippets, options.

    vague      "Be conservative and only flag important issues."     -> no decision boundary
    criteria   REPORT bugs/security/contradicting comments, SKIP style and local patterns, severities in prose
    examples   the same criteria, severities defined by CODE examples instead of prose

The snippets hold 9 real defects (R1-R9) and 7 decoys (D1-D7): style, local patterns and harmless comments that a
precise reviewer must NOT report. Each review is scored against that answer key.

Besides model I/O, the log shows per review its false positives and every spot's verdict, then one comparison line
per prompt: false-positive rate, inconsistency (wrong verdicts), stable spots and severity accuracy.

Run:  python poc1_vague_vs_explicit.py     (3 runs, 1 query() call each; 3 optional repeats)
"""

import asyncio
import sys
from collections import defaultdict

from claude_agent_sdk import ClaudeSDKError

from common import load_settings, log, setup_logging
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


def verdict_line(verdicts: dict[str, str]) -> str:
    """R6=minor!major means: reported as minor, but it is a major defect."""
    parts = []
    for spot in PLANTED:
        verdict = verdicts[spot["id"]]
        wrong_severity = spot["kind"] == "real" and verdict not in ("missed", spot["severity"])
        parts.append(f"{spot['id']}={verdict}" + (f"!{spot['severity']}" if wrong_severity else ""))
    return " ".join(parts)


async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc1_vague_vs_explicit")
        files = load_snippets()
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    runs = defaultdict(list)
    for label, system_prompt in PROMPTS:
        log.info("MODEL INPUT   system       %s", system_prompt)  # the system prompt is what this POC varies
        try:
            findings = await review(settings, system_prompt, files)
        except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
            log.error("SDK error: %s", exc)
            return 1
        if findings is None:
            log.error("%s: no structured review", label)
            continue
        scored = score_run(findings, files)
        runs[label].append(scored)
        log.info("%s: %d finding(s), %d false positive(s): %s", label, scored["total"], scored["fp"], scored["fp_spots"])
        log.info("%s verdicts: %s", label, verdict_line(scored["verdicts"]))
        wrong = sum(not is_right(s, scored["verdicts"][s["id"]]) for s in PLANTED)
        log.info("%s: %d of %d verdicts wrong", label, wrong, len(PLANTED))

    for label, label_runs in runs.items():  # the evidence, side by side (C12)
        s = summarize(label_runs)
        wrong, verdicts = s["inconsistency"]
        log.info("%-8s runs=%d  false positives=%.0f%%  inconsistency=%d/%d=%.0f%%  stable=%s  severity accuracy=%.0f%%",
                 label, len(label_runs), 100 * s["fp_rate"], wrong, verdicts, 100 * wrong / verdicts,
                 "n/a (1 run)" if s["stable"] is None else f"{s['stable']}/{len(PLANTED)}", 100 * s["severity_accuracy"])
    log.info("Same model, schema, snippets and options: only the system prompt changed")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
