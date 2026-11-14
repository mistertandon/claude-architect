"""
POC 2 - Trust recovery, one category at a time
==============================================
A production reviewer is precise except for ONE loosely written rule ("flag any comment that is outdated, ... including
TODOs"), so one category is noisy. A developer who sees false positives stops trusting EVERY category.

    1. per-category false-positive rate of the production prompt
    2. any category above 25% is switched OFF: a filter in code over the same findings
    3. what the developer sees before and after, and the real defects the switch hides (the price)
    4. the refinement it needs, and the re-enablement plan with a target rate
    5. one run of the refined rule: re-enable or not

Run:  python poc2_trust_recovery.py     (2 runs, 1 query() call each; 1 optional repeat)
"""

import asyncio
import sys

from claude_agent_sdk import ClaudeSDKError

from common import load_settings
from criteria_setup import COMMENT_RULE, EXAMPLES_PROMPT, PLANTED, is_false_positive, load_snippets, match, review

LOOSE_COMMENT_RULE = "any comment that is outdated, incomplete or could be clearer, including TODOs."
PRODUCTION_PROMPT = EXAMPLES_PROMPT.replace(COMMENT_RULE, LOOSE_COMMENT_RULE)  # one loosely written rule (E2)
COMMENT_EXAMPLES = (" For example, flag `// returns the price in dollars` above `return priceCents;`, but skip "
                    "`// TODO: cache this` and `// limits from the 2024 policy`.")
REFINED_PROMPT = EXAMPLES_PROMPT.replace(COMMENT_RULE, COMMENT_RULE + COMMENT_EXAMPLES)  # the refinement (C17)

THRESHOLD = 0.25  # a category above this false-positive rate is disabled (C15)
TARGET_FP = 0.10  # ... and re-enabled only at or below this (C18)
REFINEMENTS = {"comment_mismatch": "Use the contradiction-only rule and add code examples of comments to flag and to "
                                   "skip (TODOs, dated notes)."}

RUNS = [
    ("production", PRODUCTION_PROMPT),
    # ("production", PRODUCTION_PROMPT),  # optional: a second production run, pooled into the same table
    ("refined", REFINED_PROMPT),
]


def category_table(findings: list[dict], files: list) -> dict[str, dict]:
    """Per reported category: findings, false positives and rate."""
    table = {}
    for finding in findings:
        row = table.setdefault(finding["category"], {"findings": 0, "fp": 0})
        row["findings"] += 1
        row["fp"] += is_false_positive(finding, files)
    for row in table.values():
        row["rate"] = row["fp"] / row["findings"]
    return table


def visible(findings: list[dict], disabled: list[str]) -> list[dict]:
    """The switch: findings of a disabled category never reach the developer."""
    return [f for f in findings if f["category"] not in disabled]


def real_spots(findings: list[dict], files: list) -> set[str]:
    return {spot["id"] for f in findings if (spot := match(f, files)) and spot["kind"] == "real"}


async def main() -> int:
    try:
        settings = load_settings()
        files = load_snippets()
    except (OSError, RuntimeError):
        return 1

    production_runs, refined = [], None
    for label, system_prompt in RUNS:
        try:
            findings = await review(settings, system_prompt, files)
        except ClaudeSDKError:  # Claude Code not found, its process crashed, ...
            return 1
        if findings is None:
            return 1
        if label == "production":
            production_runs.append(findings)
        else:
            refined = findings

    pooled = [f for run in production_runs for f in run]
    table = category_table(pooled, files)
    disabled = [c for c, row in table.items() if row["rate"] > THRESHOLD]

    shown = visible(pooled, disabled)  # trust recovery: the developer sees only trusted categories (C16)
    before = sum(is_false_positive(f, files) for f in pooled)
    after = sum(is_false_positive(f, files) for f in shown)
    runs_with_fp = sum(any(is_false_positive(f, files) for f in visible(run, disabled)) for run in production_runs)
    collateral = sorted(real_spots(pooled, files) - real_spots(shown, files))  # real defects hidden while disabled

    for category in disabled:  # the refinement and the re-enablement plan (C17, C18)
        fps = sorted({spot["id"] if (spot := match(f, files)) else "unmatched"
                      for f in pooled if f["category"] == category and is_false_positive(f, files)})
        refinement = REFINEMENTS.get(category, "add code examples of its edge cases.")
        # Plan: re-enable when the refined criteria score at most TARGET_FP false positives in this category
        # and still find its real defects.
        if refined is not None:
            row = category_table(refined, files).get(category, {"findings": 0, "fp": 0, "rate": 0.0})
            reals = {s["id"] for s in PLANTED if s["kind"] == "real"} & real_spots(refined, files)
            re_enable = row["rate"] <= TARGET_FP
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
