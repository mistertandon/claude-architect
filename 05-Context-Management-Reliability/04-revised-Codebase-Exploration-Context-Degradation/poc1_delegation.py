"""
POC 1 - Delegate, then hand Phase 1 to Phase 2
==============================================
Phase 1: a coordinator that can't read files gives 3 narrow exploration tasks to 3 read-only subagents
(test-finder, dependency-tracer, integration-scout). Each subagent reads what it needs and returns a short JSON
report: only that report enters the coordinator's context. The coordinator then writes the Phase 1 summary.

Baseline: ONE agent does the same Phase 1 work itself, so every file it reads stays in its own context.

Phase 2: two follow-up tasks, each run warm (Python injects the Phase 1 summary at the top of the prompt) and cold
(the task alone). The cold runs repeat Phase 1's searches: the cold-start problem.

The saving is context, not speed: the coordinator would hold the same 3 reports if its subagents ran one at a time.

Besides model I/O (tagged [coordinator] or [<subagent>]), the log shows each report's size against what its subagent
read, the summary check, the context growth of the coordinator and of the single agent, and per Phase 2 run its
tool calls, discovery calls and files read.

Run:  python poc1_delegation.py     (3 runs: Phase 1, the baseline, Phase 2 warm and cold = 6 query() calls)
"""

import asyncio
import json
import re
import sys

from claude_agent_sdk import ClaudeSDKError

from common import load_settings, log, setup_logging
from coordinator import run_coordinator
from explore_setup import (CLASSES, FILE_TOOLS, PHASE1_SCHEMA, PHASE1_TASKS, PHASE2_TASKS, REPO_DIR, REPORT_FORMAT,
                           UNHANDLED, UNTESTED_INTEGRATIONS, build_phase1_options, build_solo_options, chars_read,
                           parse_json_object, repo_path, sentence_count)

TASK_LIST = ("Phase 1 tasks:\n" + "\n".join(f"- {task}: {text}" for task, text in PHASE1_TASKS.items())
             + "\nPhase 2 tasks, which you don't run:\n"
             + "\n".join(f"- {task}: {text}" for task, text in PHASE2_TASKS.items()))
PHASE1_PROMPT = "Run Phase 1 of the exploration, then write the Phase 1 summary.\n\n" + TASK_LIST
BASELINE_PROMPT = "Do the Phase 1 tasks yourself, then write the Phase 1 summary.\n\n" + TASK_LIST
SOLO_PROMPT = ("You explore the Lumen Home TypeScript service in your working directory. Do every task yourself, "
               "then write the Phase 1 summary.")
PHASE2_PROMPT = ("You explore the Lumen Home TypeScript service in your working directory. Do your task. "
                 + REPORT_FORMAT)

SOURCE_LINE = re.compile(r"\bimport \{|\bexport (class|interface|function)\b")  # pasted code, not a summary
EXPECTED = {  # what each Phase 2 answer must name, from the ground truth (C9)
    "payment_errors": [name for name, path in CLASSES.items() if path in UNHANDLED] + UNHANDLED,
    "untested_integrations": UNTESTED_INTEGRATIONS,
}


def check_report(text: str) -> list[str]:
    """A report must be a short structured summary: task, classes with exact files, facts, and no code (C3)."""
    try:
        report = parse_json_object(text)
    except ValueError as exc:
        return [str(exc)]
    problems = [f"no {key}" for key in ("task", "classes", "facts") if key not in report]
    for item in report.get("classes", []):
        name, file = item.get("name"), repo_path(str(item.get("file", "")))
        if not (REPO_DIR / file).is_file() or (name in CLASSES and CLASSES[name] != file):
            problems.append(f"wrong file for {name}: {item.get('file')}")
    return problems + (["contains source lines"] if SOURCE_LINE.search(text) else [])


def check_summary(summary: dict) -> list[str]:
    """Concise and structured: at most 5 sentences of architecture, chains with real classes, one objective per
    Phase 2 task naming a class and its file, and no code (C10)."""
    problems = [] if sentence_count(summary["architecture"]) <= 5 else ["architecture longer than 5 sentences"]
    if not any(name in chain for chain in summary["dependency_chains"] for name in CLASSES):
        problems.append("no dependency chain names a class")
    for task in PHASE2_TASKS:
        objective = next((o["objective"] for o in summary["phase2_objectives"] if o["task"] == task), "")
        if not any(name in objective and path in objective for name, path in CLASSES.items()):
            problems.append(f"the {task} objective names no class with its file")
    return problems + (["contains source lines"] if SOURCE_LINE.search(json.dumps(summary)) else [])


def summary_block(summary: dict, task: str) -> str:
    """The Phase 1 summary for one Phase 2 task: the shared context, plus that task's own objective."""
    objective = next((o["objective"] for o in summary["phase2_objectives"] if o["task"] == task), "(none)")
    lines = ["=== PHASE 1 SUMMARY ===", f"Architecture: {summary['architecture']}", "Dependency chains:"]
    lines += [f"- {chain}" for chain in summary["dependency_chains"]]
    lines += ["Key concerns:"] + [f"- {concern}" for concern in summary["key_concerns"]]
    return "\n".join(lines + [f"Your Phase 2 objective: {objective}"])


def phase2_prompt(task: str, summary: dict | None) -> str:
    """Python injects the summary, so every warm Phase 2 agent gets the same document word for word (C8)."""
    if summary is None:
        return PHASE2_TASKS[task]  # cold: the task alone
    return f"{summary_block(summary, task)}\n\n=== YOUR TASK ===\n{PHASE2_TASKS[task]}"


async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc1_delegation")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    try:
        # Run 1, Phase 1: the coordinator delegates; each subagent's tool results stay in the subagent (C1, C2)
        phase1 = await run_coordinator(PHASE1_PROMPT, options=build_phase1_options(settings))
        summary = phase1["output"]
        if summary is None:  # an error result, or a success without structured output: both count as a failure
            log.error("Phase 1 returned no summary (loop result: %s)", phase1["subtype"])
            return 1
        for call in phase1["agent_calls"]:
            read = chars_read([c for c in phase1["research_calls"] if c["parent_tool_use_id"] == call["id"]])
            report = call["report"] or ""
            log.info("Report of %s: %d chars, against %d chars of files its subagent read (%.0f%%); %s",
                     call["subagent_type"], len(report), read, 100 * len(report) / max(read, 1),
                     check_report(report) or "valid")  # (C3)
        own_reads = [c for c in phase1["research_calls"] if c["name"] in FILE_TOOLS and c["parent_tool_use_id"] is None]
        log.info("File-tool calls by the coordinator itself: %d (E1). Phase 1 summary: %s; blocks for Phase 2: %s",
                 len(own_reads), check_summary(summary) or "4 parts, concise, no code",
                 {task: f"{len(summary_block(summary, task))} chars" for task in PHASE2_TASKS})  # (C10)

        # Run 2, the baseline: one agent does the same work, and keeps every file it read in its context (C2)
        baseline = await run_coordinator(BASELINE_PROMPT, options=build_solo_options(settings, SOLO_PROMPT,
                                                                                     PHASE1_SCHEMA))
        for name, run in (("coordinator", phase1), ("single agent", baseline)):
            first, last = run["prompt_tokens"] or 0, run["last_prompt_tokens"] or 0
            log.info("Context of the %s: %d -> %d input tokens (+%d) over the run; files read in the run: %d chars",
                     name, first, last, last - first, chars_read(run["research_calls"]))

        # Run 3, Phase 2: warm (summary injected) and cold (task alone) for each task (C8, C9)
        for task in PHASE2_TASKS:
            for arm, injected in (("warm", summary), ("cold", None)):
                run = await run_coordinator(phase2_prompt(task, injected),
                                            options=build_solo_options(settings, PHASE2_PROMPT))
                calls, answer = run["research_calls"], str(run["output"] or "")
                files = {repo_path(c["input"].get("file_path", "")) for c in calls if c["name"] == "Read"}
                log.info("Phase 2 %s, %s: %d tool calls, %d discovery calls (Glob, Grep), %d files read (%d chars); "
                         "the answer names %s: %s", task, arm, len(calls),
                         sum(c["name"] in ("Glob", "Grep") for c in calls), len(files), chars_read(calls),
                         EXPECTED[task], all(word in answer for word in EXPECTED[task]))
    except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
        log.error("SDK error: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
