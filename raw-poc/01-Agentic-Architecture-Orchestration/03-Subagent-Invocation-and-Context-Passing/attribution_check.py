"""
attribution_check.py - what crossed each handoff: the metadata the synthesizer received, which of its claims
have a real source, and whether the research subagents ran at the same time.
"""

from typing import Any

from attribution_setup import CONTENT_FIELDS, METADATA_FIELDS, parse_json_object


def strip_metadata(findings: list[dict]) -> list[dict]:
    """The exam's failure pattern (C12): pass only the content, drop where it came from."""
    return [{key: finding[key] for key in CONTENT_FIELDS} for finding in findings]


def check_metadata_passed(agent_prompt: str, findings: list[dict]) -> tuple[int, int]:
    """How many metadata values of the findings reached the agent unchanged: (passed, total)."""
    sent = {item.get("claim"): item for item in parse_json_object(agent_prompt).get("findings", [])}
    passed = sum(
        1 for finding in findings for key in METADATA_FIELDS
        if key in sent.get(finding["claim"], {}) and sent[finding["claim"]][key] == finding[key]
    )
    return passed, len(findings) * len(METADATA_FIELDS)


def verify_attribution(statements: list[dict], findings: list[dict]) -> dict[str, Any]:
    """Every claim must cite a real (source_url, page_number) pair from the findings (C13)."""
    real = {(finding["source_url"], finding["page_number"]) for finding in findings}
    orphaned = [s for s in statements if not s.get("citations")]  # a claim without any source
    cited = [(c.get("source_url"), c.get("page_number")) for s in statements for c in s.get("citations", [])]
    return {"statements": len(statements), "orphaned": orphaned,
            "invalid": [pair for pair in cited if pair not in real],  # an invented or garbled source
            "cited": {pair for pair in cited if pair in real}}


def diagnose(passed: int, total: int, attribution: dict[str, Any]) -> str:
    """A claim without a source? Check the handoff first, not the synthesizer (C14)."""
    if not (attribution["orphaned"] or attribution["invalid"]):
        return "All claims attributed."
    if passed < total:
        return "Root cause: metadata was not passed to the synthesizer. Fix the coordinator's handoff, not the synthesizer prompt."
    return "Metadata reached the synthesizer: now review its prompt."


def delegation_timing(agent_calls: list[dict], names: tuple[str, ...] = ("web-searcher", "doc-analyst")) -> dict:
    """Were the research subagents spawned in one response, and did they run at the same time? (C15, C16)"""
    calls = [call for call in agent_calls if call["subagent_type"] in names and call["finished"] is not None]
    return {
        "responses": len({call["message_id"] for call in calls}),  # 1 = all spawned in one coordinator response
        "overlap": len(calls) > 1 and all(c["started"] < d["finished"] for c in calls for d in calls if c is not d),
        "delegation_seconds": max(c["finished"] for c in calls) - min(c["started"] for c in calls) if calls else 0.0,
        "durations": {call["subagent_type"]: call["finished"] - call["started"] for call in calls},
    }
