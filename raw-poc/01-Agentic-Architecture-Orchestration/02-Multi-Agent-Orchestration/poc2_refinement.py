"""
POC 2 - The coordinator's refinement loop
==========================================
One delegation round can miss whole categories. A coordinator checks its own result and repairs it:

    delegate -> merge sections -> assess coverage -> 100%?  stop
                    ^                                 no:   re-delegate ONLY the gaps, each with its reason
                    +---------------------------------------+   (at most MAX_ITERATIONS rounds)

Claude judges the coverage (assess_coverage). Python counts it and runs the loop, so the threshold and the
iteration cap are deterministic.

Run:  python poc2_refinement.py     (3 runs, about 9 query() calls)
"""

import asyncio
import json
import sys
from typing import Any

from claude_agent_sdk import ClaudeSDKError

from common import Settings, load_settings
from coordinator import decompose, delegate, run_coordinator
from research_setup import REQUIRED, build_coordinator_options, missing_categories

TOPIC = "renewable energy technologies"
COVERAGE_THRESHOLD = 100  # the primary stop: every category well covered
MAX_ITERATIONS = 3  # the fallback stop: delegation rounds, not the SDK's tool turns (01 C16)
NARROW = ["solar power", "wind power"]  # plays a coordinator that decomposed too narrowly (C6)

# (name, starting subtopics or None = decompose first, max iterations)
RUNS = [
    ("narrow", NARROW, MAX_ITERATIONS),  # 33% after round 1, then the gaps get re-delegated
    ("capped", NARROW, 1),  # the same start, but the cap stops the loop: a partial report
    ("full", None, MAX_ITERATIONS),  # a real decomposition: typically 100% after round 1
]

COVERAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "coverage": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subtopic": {"type": "string"},
                    "status": {"type": "string", "enum": ["well_covered", "partial", "missing"]},
                    "reason": {"type": "string"},
                },
                "required": ["subtopic", "status", "reason"],
            },
        }
    },
    "required": ["coverage"],
}


async def assess_coverage(settings: Settings, topic: str, sections: list[dict], must_cover: list[str]) -> list[dict]:
    """The coordinator judges the report against the WHOLE topic, not against the sections it has (C14)."""
    prompt = (
        f"Topic: {topic}. Must cover at least: {must_cover}. Report sections so far: {json.dumps(sections)}. "
        "List every category this topic needs (each must-cover item plus any other major category of the topic) "
        "and rate each one: well_covered = a section with web findings, document findings and a source id; "
        "partial = a section missing one of these; missing = no section. Give a one-line reason for each."
    )
    result = await run_coordinator(prompt, build_coordinator_options(settings, COVERAGE_SCHEMA, with_agents=False))
    if result["output"] is None:
        raise RuntimeError("assess_coverage() returned no coverage")
    return result["output"]["coverage"]


def coverage_percent(coverage: list[dict]) -> int:
    """Counted in Python from the statuses, never parsed from Claude's prose (01 C7)."""
    return round(100 * sum(c["status"] == "well_covered" for c in coverage) / len(coverage))


def merge_sections(report_sections: list[dict], new_sections: list[dict]) -> list[dict]:
    """Keep every round's results: a re-delegated subtopic's new section replaces its old one (C13)."""
    merged = {section["subtopic"].lower(): section for section in report_sections}
    merged.update({section["subtopic"].lower(): section for section in new_sections})
    return list(merged.values())


async def research(settings: Settings, topic: str, max_iterations: int, subtopics: list[str] | None = None) -> dict:
    """The refinement loop (C16): delegate, assess, then stop or re-delegate the gaps."""
    subtopics = subtopics or await decompose(settings, topic)
    sections: list[dict] = []
    gap_notes: dict[str, str] | None = None
    history: list[dict[str, Any]] = []
    for iteration in range(1, max_iterations + 1):
        round_result = await delegate(settings, topic, subtopics, gap_notes)
        sections = merge_sections(sections, round_result["sections"])
        coverage = await assess_coverage(settings, topic, sections, REQUIRED)
        percent = coverage_percent(coverage)
        gaps = [c for c in coverage if c["status"] != "well_covered"]
        history.append({"agent_calls": round_result["agent_calls"], "coverage_percent": percent})
        if percent >= COVERAGE_THRESHOLD:  # the primary stop: a quality threshold (C17)
            return {"sections": sections, "coverage_percent": percent, "complete": True, "history": history}
        # Targeted follow-ups: only the gaps, each with the reason the assessment gave (C15)
        subtopics = [g["subtopic"] for g in gaps]
        gap_notes = {g["subtopic"]: g["reason"] for g in gaps}
    # The fallback stop: the cap, with the partial report (C17)
    return {"sections": sections, "coverage_percent": percent, "complete": False, "history": history}


async def main() -> int:
    try:
        settings = load_settings()
    except (OSError, RuntimeError):
        return 1

    for name, subtopics, max_iterations in RUNS:
        try:
            report = await research(settings, TOPIC, max_iterations, subtopics)
        except (RuntimeError, ValueError):  # a coordinator step returned nothing usable: next run
            continue
        except ClaudeSDKError:  # Claude Code not found, its process crashed, ...
            return 1
        first_round = report["history"][0]
        # The subagents did all they were asked: these categories were never asked for.
        # Root cause: the coordinator's decomposition, not the subagents (C7)
        never_delegated = missing_categories([call["prompt"] for call in first_round["agent_calls"]])
        # A single-shot dispatcher would have stopped after round 1 (C18): compare its coverage with the final one.
        dispatcher_percent, coordinator_percent = first_round["coverage_percent"], report["coverage_percent"]
        still_missing = missing_categories([section["subtopic"] for section in report["sections"]])
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
