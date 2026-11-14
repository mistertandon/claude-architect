"""
POC 1 - Provenance from source to synthesis
===========================================
A claim is only as good as its trail. Three calls:

    1. research    a coordinator sends market-analyst and policy-analyst to the library; each returns claim-source
                   mappings (claim, sourceUrl, documentName, relevantExcerpt, publicationDate), checked in Python
                   against the sources, word for word
    2. plain       the mappings -> "You write short research briefs": fluent prose nobody can trace
    3. traceable   the SAME mappings -> every fact sentence ends with [Mn], plus a References section

Same model, same findings: only the synthesis instruction differs.

Besides model I/O (tagged [coordinator] or [<analyst>]), the log shows each analyst's mappings and validation
errors, and each brief's traceability: body sentences, sentences with a valid marker, findings cited, and complete
reference lines.

Run:  python poc1_provenance.py     (3 runs, 1 query() call each; the research call runs 2 subagents)
"""

import asyncio
import json
import re
import sys

from claude_agent_sdk import ClaudeSDKError

from common import Settings, load_settings, log, setup_logging
from coordinator import run_coordinator
from provenance_setup import (AGENTS, PLAIN_PROMPT, SYNTH_TASK, TRACEABLE_PROMPT, build_research_options,
                              build_synth_options, markers, sentences, validate_mapping, with_ids)

RESEARCH_PROMPT = ("Research this question with both analysts, then reply with one line saying both reports are in. "
                   "Question: What is the state of sodium-ion grid storage in 2026?")
RUNS = [("plain", PLAIN_PROMPT), ("traceable", TRACEABLE_PROMPT)]  # runs 2 and 3, after the research round


def parse_json_object(text: str):
    """A subagent's report is TEXT: take its first JSON object and ignore what follows, such as 'agentId: ...'."""
    if "{" not in text:
        raise ValueError("the report holds no JSON object")
    value, _ = json.JSONDecoder().raw_decode(text[text.index("{"):])
    return value


async def research_round(settings: Settings) -> dict:
    """Run 1: the analysts' mappings, each validated against the library before any synthesis (C4, C5)."""
    result = await run_coordinator(RESEARCH_PROMPT, options=build_research_options(settings))
    mappings, errors, by_agent = [], [], {}
    for name in AGENTS:  # market-analyst's findings first, so their ids come first
        found = []
        for call in (c for c in result["agent_calls"] if c["subagent_type"] == name):
            try:
                found += parse_json_object(call["report"] or "")["findings"]
            except (ValueError, KeyError, TypeError) as exc:  # prose instead of mappings: an error, never summarised
                errors.append(f"{name}: no findings array ({exc})")
        valid = [mapping for mapping in found if not validate_mapping(mapping)]
        errors += [f"{name}: {problem}" for mapping in found for problem in validate_mapping(mapping)]
        by_agent[name] = len(valid)
        mappings += valid
    return {"mappings": mappings, "errors": errors, "by_agent": by_agent}


async def synthesize(settings: Settings, system_prompt: str, mappings: list[dict]) -> tuple[str, int]:
    """One synthesis session with no tools: the numbered mappings are all it has (C7). Returns (brief, tool calls)."""
    prompt = SYNTH_TASK + json.dumps(with_ids(mappings), indent=2, ensure_ascii=False)
    result = await run_coordinator(prompt, options=build_synth_options(settings, system_prompt))
    return str(result["output"] or ""), len(result["research_calls"]) + len(result["agent_calls"])


def traceability(brief: str, mappings: list[dict]) -> dict[str, int]:
    """Can a reader trace each fact? Body sentences, those with a valid marker, distinct findings cited, and reference
    lines that hold their finding's exact documentName, sourceUrl and publicationDate (C9)."""
    ids = {item["id"]: item for item in with_ids(mappings)}
    parts = re.split(r"^\W*References\W*$", brief, maxsplit=1, flags=re.M | re.I)  # the body, then the references
    body, references = parts[0], parts[1] if len(parts) > 1 else ""
    body = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))  # headings aren't facts
    body_sentences = sentences(body)
    cited = [s for s in body_sentences if any(found in ids for found in markers(s))]
    complete = [line for line in references.splitlines() if markers(line) and markers(line)[0] in ids
                and all(ids[markers(line)[0]][key] in line for key in ("documentName", "sourceUrl", "publicationDate"))]
    return {"body sentences": len(body_sentences), "with a valid marker": len(cited),
            "findings cited": len({found for s in body_sentences for found in markers(s) if found in ids}),
            "complete reference lines": len(complete)}


async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc1_provenance")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    try:
        research = await research_round(settings)  # run 1
        for name, count in research["by_agent"].items():
            log.info("%s: %d valid claim-source mappings", name, count)
        log.info("Validation errors: %s", research["errors"] or "none: every excerpt is word for word in its source")
        if not research["mappings"]:
            log.error("No valid mappings: nothing to synthesize")
            return 1
        for name, system_prompt in RUNS:  # runs 2 and 3: the same mappings, two instructions (C8)
            brief, tool_calls = await synthesize(settings, system_prompt, research["mappings"])
            log.info("Synthesis %s, from %d mappings with %d tool calls: %s", name, len(research["mappings"]),
                     tool_calls, traceability(brief, research["mappings"]))
    except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
        log.error("SDK error: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
