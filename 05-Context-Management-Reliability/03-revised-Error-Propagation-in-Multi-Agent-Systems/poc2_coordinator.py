"""
POC 2 - The coordinator recovers and annotates coverage
=======================================================
One coordinator call. The coordinator hands the 7 topics of the Helios brief to researcher subagents (all at once,
query '<topic> 2026', parameters {}), reads each JSON report, and recovers by failure type:

    transient    3+ partial sources: proceed and mark the topic limited; fewer: re-delegate with the narrower query
    validation   re-delegate with the parameters fixed as the error says
    business     escalate_to_human, no retry
    permission   alert_admin, no retry

The brief comes back as structured output: findings per topic, and a SEPARATE coverage section that names every
gap and its cause. Then Python checks each recovery and each coverage entry, and runs two anti-pattern coordinators
(suppress, terminate) over the same first-round reports.

Besides model I/O (tagged [coordinator] or [researcher]), the log shows: the hop check, one line per topic (first
report, actions taken, expected action), the three policies, the coverage check and the brief as a reader sees it.

Run (after the free demo: python poc1_subagent_errors.py):
    python poc2_coordinator.py     (1 run: 1 coordinator call with about 9 researcher subagents)
"""

import asyncio
import re
import sys

from claude_agent_sdk import ClaudeSDKError

from common import load_settings, log, setup_logging
from coordinator import run_coordinator
from propagation_setup import PropagationState, build_propagation_options, parse_json_object, validate_report

TOPICS = ["solar", "wind", "geothermal", "tidal", "hydropower", "biomass", "fusion"]
BRIEF_PROMPT = ("Write the Helios Institute 2026 renewables brief on these topics: solar, wind, geothermal, tidal, "
                "hydropower, biomass, fusion.")
EXPECTED = {  # topic -> (recovery action, coverage status, sources_used)
    "solar": ("none", "well_supported", 3),
    "wind": ("none", "well_supported", 3),  # its 2 failed attempts never left the subagent (POC 1, C11)
    "geothermal": ("proceed", "limited", 3),  # transient, 3 partial sources: enough to proceed (C17)
    "tidal": ("redelegate", "well_supported", 3),  # transient, 1 partial source: retry with the narrower query
    "hydropower": ("redelegate", "well_supported", 3),  # validation: retry with a region
    "biomass": ("escalate", "unavailable", 0),  # business: a human approves the licence, no retry
    "fusion": ("alert", "unavailable", 0),  # permission: an administrator grants the scope, no retry
}


def prompt_line(prompt: str, name: str) -> str:
    """One line of the three-line Agent prompt: 'topic: ...', 'query: ...' or 'parameters: ...'."""
    match = re.search(rf"^{name}:\s*(.*)$", prompt, re.MULTILINE)
    return match.group(1).strip() if match else ""


def received_reports(result: dict, state: PropagationState) -> list[dict]:
    """What crossed the hop: per Agent call, its topic and order, the report the researcher relayed (parsed and
    validated), and whether it equals the report the tool built for that call (C2, C3)."""
    received, seen = [], {}
    for call in result["agent_calls"]:
        topic = prompt_line(call["prompt"], "topic").lower()
        seen[topic] = seen.get(topic, 0) + 1
        built = [report for report in state.reports if report["topic"] == topic]
        try:
            report = parse_json_object(call["report"] or "")
            errors = validate_report(report)
        except ValueError as exc:  # no JSON at all: a bare message crossed the hop
            report, errors = None, [str(exc)]
        received.append({"topic": topic, "order": seen[topic], "call": call, "report": report, "errors": errors,
                         "same_as_tool": len(built) >= seen[topic] and built[seen[topic] - 1] == report})
    return received


def decisions(received: list[dict], state: PropagationState) -> dict[str, list[str]]:
    """Each topic's recovery, read from what the coordinator DID: later Agent calls, escalations, alerts (C14)."""
    actions = {topic: [] for topic in TOPICS}
    for item in received:
        if item["order"] > 1 and item["topic"] in actions:
            actions[item["topic"]].append("redelegate")
    for kind, records in (("escalate", state.escalations), ("alert", state.alerts)):
        for record in records:
            topic = str(record["topic"]).strip().lower()
            if topic in actions:
                actions[topic].append(kind)
    for topic in TOPICS:  # no action: proceeding after a failure report, or nothing to do after a success
        first = next((item["report"] for item in received if item["topic"] == topic), None)
        if not actions[topic]:
            actions[topic] = ["proceed" if first and first["status"] != "success" else "none"]
    return actions


def suppress(reports: dict[str, dict]) -> dict[str, list[str]]:
    """ANTI-PATTERN 1: keep the successes, drop every failure without a trace (C15)."""
    ok = [topic for topic in TOPICS if reports.get(topic, {}).get("status") == "success"]
    return {"findings": ok, "annotated": [], "missing": [topic for topic in TOPICS if topic not in ok]}


def terminate(reports: dict[str, dict]) -> dict[str, list[str]]:
    """ANTI-PATTERN 2: stop at the first failure and deliver no brief at all (C15)."""
    if all(reports.get(topic, {}).get("status") == "success" for topic in TOPICS):
        return {"findings": TOPICS, "annotated": [], "missing": []}
    return {"findings": [], "annotated": [], "missing": TOPICS}


def check_coverage(brief: dict, state: PropagationState) -> list[str]:
    """Each topic has exactly one coverage entry with the expected status, a reason, and a source count that matches
    what the reports returned; no finding cites a source no report returned (C18)."""
    returned: dict[str, set] = {}
    for report in state.reports:
        sources = report["results"] + ((report["error"] or {}).get("partialResults") or [])
        returned.setdefault(report["topic"], set()).update(source["id"] for source in sources)
    problems = []
    for topic in TOPICS:
        entries = [entry for entry in brief["coverage"] if entry["topic"].strip().lower() == topic]
        if len(entries) != 1:
            problems.append(f"{topic}: {len(entries)} coverage entries")
            continue
        entry, sources_used = entries[0], len(returned.get(topic, set()))
        if entry["status"] != EXPECTED[topic][1]:
            problems.append(f"{topic}: status {entry['status']}, expected {EXPECTED[topic][1]}")
        if not entry["reason"].strip():
            problems.append(f"{topic}: empty reason")
        if entry["sources_used"] != sources_used:
            problems.append(f"{topic}: sources_used {entry['sources_used']}, the reports returned {sources_used}")
    all_ids = set().union(*returned.values()) if returned else set()
    invented = [source_id for section in brief["sections"] for finding in section["findings"]
                for source_id in finding["source_ids"] if source_id not in all_ids]
    return problems + ([f"cited ids no report returned: {invented}"] if invented else [])


def render_brief(brief: dict) -> str:
    """The brief as a reader sees it: the findings, then a separate Coverage section (C20)."""
    lines = []
    for section in brief["sections"]:
        lines.append(f"## {section['topic']}")
        lines += [f"- {finding['claim']} [{', '.join(finding['source_ids'])}]" for finding in section["findings"]]
    lines.append("## Coverage")
    lines += [f"- {entry['topic']}: {entry['status']}, {entry['sources_used']} source(s). {entry['reason']}"
              for entry in brief["coverage"]]
    return "\n".join(lines)


async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc2_coordinator")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    state = PropagationState()  # a new state per run: the handlers record every attempt, report and action here
    try:
        result = await run_coordinator(BRIEF_PROMPT, options=build_propagation_options(settings, state))
    except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
        log.error("SDK error: %s", exc)
        return 1
    brief = result["output"]
    if brief is None:  # an error result, or a success without structured output: both count as a failure
        log.error("No brief came back (loop result: %s)", result["subtype"])
        return 1

    received = received_reports(result, state)
    first_round = [item for item in received if item["order"] == 1]
    fixed_input = sum(prompt_line(item["call"]["prompt"], "query") == f"{item['topic']} 2026"
                      and prompt_line(item["call"]["prompt"], "parameters") == "{}" for item in first_round)
    self_searches = sum(call["name"] == "mcp__sources__search_sources" and call["parent_tool_use_id"] is None
                        for call in result["research_calls"])
    log.info("Hop check: %d reports received, %d valid, %d identical to the tool's report; first round %d Agent "
             "calls in %d response(s), %d with '<topic> 2026' and {}; searches by the coordinator itself: %d",
             len(received), sum(not item["errors"] for item in received),
             sum(item["same_as_tool"] for item in received), len(first_round),
             len({item["call"]["message_id"] for item in first_round}), fixed_input, self_searches)

    actions = decisions(received, state)
    first_reports = {item["topic"]: item["report"] or {} for item in first_round}
    for topic in TOPICS:  # one recovery per failure type (C14, C16), and the partial-results rule (C17)
        error = first_reports.get(topic, {}).get("error") or {}
        seen = first_reports.get(topic, {}).get("status", "no report")
        if error:
            seen += f"/{error['failureType']}, {len(error['partialResults'])} partial"
        retry = next((item["call"] for item in received if item["topic"] == topic and item["order"] == 2), None)
        retry_note = ""
        if retry and retry["finished"] is not None:  # what the retry changed, and the latency it cost (C2, C17)
            seconds = retry["finished"] - retry["started"]
            retry_note = (f"; retry with query {prompt_line(retry['prompt'], 'query')!r}, parameters "
                          f"{prompt_line(retry['prompt'], 'parameters')}, took {seconds:.1f} s")
        correct = actions[topic] == [EXPECTED[topic][0]]
        log.info("%-10s first report %s; actions %s; expected %s -> %s%s", topic, seen, actions[topic],
                 EXPECTED[topic][0], "correct" if correct else "WRONG", retry_note)

    live = {"findings": [section["topic"] for section in brief["sections"] if section["findings"]],
            "annotated": [entry["topic"] for entry in brief["coverage"] if entry["status"] == "unavailable"]}
    live["missing"] = [topic for topic in TOPICS if topic not in live["findings"] + live["annotated"]]
    for policy, delivered in (("suppress", suppress(first_reports)), ("terminate", terminate(first_reports)),
                              ("live coordinator", live)):  # C15
        log.info("Policy %-16s findings %s; annotated unavailable %s; missing %s", policy, delivered["findings"],
                 delivered["annotated"], delivered["missing"])

    problems = check_coverage(brief, state)
    log.info("Coverage check: %s", problems or "one entry per topic; statuses, reasons and source counts as expected")
    log.info("The brief as a reader sees it:\n%s", render_brief(brief))
    gaps = [entry["topic"] for entry in brief["coverage"] if entry["status"] != "well_supported"]
    log.info("Without the Coverage section, %s would look complete or simply not be there (C19)", gaps)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
