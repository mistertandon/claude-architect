"""
POC 2 - Conflicts and content-appropriate rendering
===================================================
One structured synthesis of the 13 gold mappings (a fixed input, so a miss can only come from the synthesis). They
hold 2 planted conflicts, the same measure with different values:

    K1  growth rate         12% [M1] (Helios, 2025-03-10)           vs  18% [M3] (Kestrel Analytics, 2026-02-20)
    K2  installed capacity  4.2 GWh [M9] (grid-connected only)      vs  5.1 GWh [M11] (with behind-the-meter)

The synthesizer must keep both values with their sources and a possibleExplanation, and never pick one. Then
render() shapes each section by its content type (financial: a table, news: prose, technical: a list), and every
line keeps its [Mn] citation.

Besides model I/O, the log shows the conflict check, K1 without and with its dates, what picking one value would
drop, the content-type check, the rendering check, and both renderings (by content type, then uniform bullets).

Run:  python poc2_conflicts_rendering.py     (1 run, 1 query() call)
"""

import asyncio
import json
import re
import sys
from datetime import date

from claude_agent_sdk import ClaudeSDKError

from common import load_settings, log, setup_logging
from coordinator import run_coordinator
from provenance_setup import (BRIEF_PROMPT, BRIEF_SCHEMA, CONFLICTS, KIND, SYNTH_TASK, build_synth_options,
                              gold_mappings, markers, sentences, with_ids)

GOLD = with_ids(gold_mappings())  # M1-M13: what a perfect research round returns (E1)
BY_ID = {mapping["id"]: mapping for mapping in GOLD}


def ids_of(citations: list[str]) -> list[str]:
    """Citations as the model wrote them ("M3" or "[M3]") -> finding ids."""
    return [found for citation in citations for found in re.findall(r"M\d+", str(citation))]


def check_conflicts(brief: dict) -> tuple[dict, list]:
    """Each planted pair must appear as ONE conflict that cites exactly that pair, with both values (C10)."""
    found = {}
    for key, (first, second, _) in CONFLICTS.items():
        conflict = next((c for c in brief["conflicts"]
                         if sorted(ids_of([v["citation"] for v in c["values"]])) == sorted([first, second])), None)
        both = conflict is not None and len(conflict["values"]) == 2 and all(str(v["value"]).strip()
                                                                             for v in conflict["values"])
        found[key] = conflict if both else None
    extra = [c for c in brief["conflicts"] if all(c is not f for f in found.values())]
    return found, extra


def pick_one(conflict: dict) -> tuple[dict, list[dict]]:
    """THE ANTI-PATTERN (C11): keep the value of the latest source and silently drop the rest."""
    ranked = sorted(conflict["values"], reverse=True,
                    key=lambda value: BY_ID[ids_of([value["citation"]])[0]]["publicationDate"])
    return ranked[0], ranked[1:]


def section_kinds(brief: dict) -> list[str]:
    """Every cited finding should sit in a section of its own content type (C15)."""
    return [f"{found} ({KIND.get(found)}) in a {section['content_type']} section" for section in brief["sections"]
            for entry in section["entries"] for found in ids_of(entry["citations"])
            if KIND.get(found) != section["content_type"]]


def cite(citations: list[str]) -> str:
    return "".join(f"[{found}]" for found in ids_of(citations))


def conflicts_and_references(brief: dict) -> list[str]:
    """Both values of each conflict, with the attribution taken from the mappings, then the full references."""
    lines = ["## Conflicting figures"]
    for conflict in brief["conflicts"]:
        sides = [f"{v['value']} {cite([v['citation']])} ({BY_ID[ids_of([v['citation']])[0]]['documentName']}, "
                 f"{BY_ID[ids_of([v['citation']])[0]]['publicationDate']})"
                 for v in conflict["values"] if ids_of([v["citation"]]) and ids_of([v["citation"]])[0] in BY_ID]
        lines.append(f"{conflict['measure']}: {' vs '.join(sides)}. Possible explanation: "
                     f"{conflict['possibleExplanation']}")
    cited = {found for section in brief["sections"] for entry in section["entries"]
             for found in ids_of(entry["citations"]) if found in BY_ID}
    lines += ["", "## References"]
    for found in sorted(cited, key=lambda finding: int(finding[1:])):
        m = BY_ID[found]
        lines.append(f"[{found}] {m['claim']} — {m['documentName']} — {m['sourceUrl']} — "
                     f"{m['publicationDate']} — \"{m['relevantExcerpt']}\"")
    return lines


def render(brief: dict) -> str:
    """Each section in the shape its content needs; the citations are the same in every shape (C13, C16)."""
    lines = []
    for section in brief["sections"]:
        lines.append(f"## {section['title']}")
        if section["content_type"] == "financial":  # figures to compare: a table with year, value and source
            lines += ["| Measure | Year | Value | Source |", "|---|---|---|---|"]
            lines += [f"| {e.get('measure') or e['text']} | {e.get('year') or ''} | {e.get('value') or ''} | "
                      f"{cite(e['citations'])} |" for e in section["entries"]]
        elif section["content_type"] == "news":  # events: one prose paragraph
            lines.append(" ".join(f"{e['text']} {cite(e['citations'])}" for e in section["entries"]))
        else:  # specifications: a bulleted list
            lines += [f"- {e['text']} {cite(e['citations'])}" for e in section["entries"]]
        lines.append("")
    return "\n".join(lines + conflicts_and_references(brief))


def render_uniform(brief: dict) -> str:
    """THE ANTI-PATTERN (C14): every entry as a bullet, whatever its content. The citations are the same, so its
    conflicts and references would be render()'s, unchanged: only the format of the sections differs."""
    lines = []
    for section in brief["sections"]:
        lines += [f"## {section['title']}"] + [f"- {e['text']} {cite(e['citations'])}" for e in section["entries"]]
        lines.append("")
    return "\n".join(lines)


def check_rendering(text: str, brief: dict) -> list[str]:
    """Shapes match the content types, every table row, bullet and news sentence carries a marker, and every
    marker has a complete reference line (C13, C16). The brief says which section is meant to be which type."""
    problems = []
    blocks = re.split(r"^## ", text, flags=re.MULTILINE)[1:]  # the sections come first, in brief order
    for section, block in zip(brief["sections"], blocks):
        title, _, content = block.partition("\n")
        rows = [line for line in content.splitlines() if line.strip()]
        if section["content_type"] == "financial":
            if not rows or not re.match(r"\|\s*Measure\s*\|\s*Year\s*\|\s*Value\s*\|\s*Source\s*\|", rows[0]):
                problems.append(f"{title}: not a Measure/Year/Value/Source table")
            to_cite = rows[2:]
        elif section["content_type"] == "technical":
            if not all(row.startswith("- ") for row in rows):
                problems.append(f"{title}: not a bulleted list")
            to_cite = rows
        else:
            if any(row.startswith(("- ", "|")) for row in rows):
                problems.append(f"{title}: news should be prose")
            to_cite = [s for row in rows for s in sentences(row)]
        problems += [f"{title}: no citation in {line[:40]!r}" for line in to_cite if not markers(line)]
    body, _, references = text.partition("## References")
    for found in sorted(set(markers(body)) - set(BY_ID)):
        problems.append(f"{found} cites no finding")
    for found in sorted(set(markers(body)) & set(BY_ID), key=lambda finding: int(finding[1:])):
        line = next((line for line in references.splitlines() if line.startswith(f"[{found}]")), "")
        if not all(str(BY_ID[found][key]) in line for key in BY_ID[found] if key != "id"):
            problems.append(f"{found}: no complete reference line")
    missing = sorted(set(BY_ID) - set(markers(body)), key=lambda finding: int(finding[1:]))
    return problems + ([f"never cited: {missing}"] if missing else [])


async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc2_conflicts_rendering")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    prompt = SYNTH_TASK + json.dumps(GOLD, indent=2, ensure_ascii=False)
    try:
        result = await run_coordinator(prompt, options=build_synth_options(settings, BRIEF_PROMPT, BRIEF_SCHEMA))
    except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
        log.error("SDK error: %s", exc)
        return 1
    brief = result["output"]
    if brief is None:  # an error result, or a success without structured output: both count as a failure
        log.error("No brief came back (loop result: %s)", result["subtype"])
        return 1

    found, extra = check_conflicts(brief)
    for key, (first, second, reason) in CONFLICTS.items():  # (C10, C12, C11)
        conflict = found[key]
        if conflict is None:
            log.info("%s (%s vs %s): NOT kept as one conflict with both values", key, first, second)
            continue
        values = [f"{v['value']} {cite([v['citation']])}" for v in conflict["values"]]
        log.info("%s kept both values %s; possibleExplanation (planted reason: %s): %s", key, values, reason,
                 conflict["possibleExplanation"])
        kept, dropped = pick_one(conflict)
        lost = [f"{v['value']} {cite([v['citation']])} ({BY_ID[ids_of([v['citation']])[0]]['documentName']}, "
                f"{BY_ID[ids_of([v['citation']])[0]]['publicationDate']})" for v in dropped]
        log.info("pick_one (latest source) on %s would keep %s %s and drop %s", key, kept["value"],
                 cite([kept["citation"]]), lost)
    log.info("Other conflicts listed: %s", [c["measure"] for c in extra] or "none (M2/M4 state their years: a trend)")

    first, second = BY_ID["M1"], BY_ID["M3"]  # (C3)
    days = (date.fromisoformat(second["publicationDate"]) - date.fromisoformat(first["publicationDate"])).days
    log.info("K1 without dates: 12%% [M1] vs 18%% [M3], a contradiction. With dates: 12%% (%s) vs 18%% (%s), %d days "
             "apart: a rate that rose within a year", first["publicationDate"], second["publicationDate"], days)

    log.info("Content types: %s", section_kinds(brief) or "every finding sits in a section of its own type")  # (C15)
    rendered = render(brief)
    log.info("Rendering check: %s", check_rendering(rendered, brief)
             or "tables, prose and lists as typed; every line cited; every finding referenced in full")
    log.info("The brief, rendered by content type:\n%s", rendered)  # (C13, C16)
    log.info("The same sections as uniform bullets (the anti-pattern):\n%s", render_uniform(brief))  # (C14)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
