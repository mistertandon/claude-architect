"""
POC 2a - A scratchpad against context degradation
=================================================
One explorer works through 6 modules, one fresh query() per module, and Python owns the history. After module 4,
the history is replaced by LOSSY_HISTORY, a fixed summary that keeps the story and loses every class name: the
attention shift of a long session, made certain. At the end the explorer must list all 18 classes with their paths,
without opening any file.

    no-scratchpad   only the history: modules 1-4 survive as "the typical layered pattern"
    scratchpad      the same, plus a Markdown file it writes (note) after each discovery and reads (read_notes)
                    at the start of every step, from step 1 on

Same modules, prompts and summary in both runs: only the scratchpad differs.

Besides model I/O, the log shows the scratchpad's entry count after each step, what the history and the scratchpad
hold right after the summarisation, each run's final score, and the scratchpad file itself.

Run:  python poc2_scratchpad.py     (2 runs, 7 query() calls each)
"""

import asyncio
import re
import sys

from claude_agent_sdk import ClaudeSDKError

from common import load_settings, log, setup_logging
from explore_setup import (CLASSES, FINAL_TASK, LOSSY_HISTORY, MODULE_PLAN, PHASES, SUMMARISE_AFTER, ExploreState,
                           build_explorer_options, build_step_prompt, explore_module, fresh_run_dir, read_sections,
                           run_agent)

RUNS = [("no-scratchpad", False), ("scratchpad", True)]
GROUPS = PHASES  # "phase 1: core modules" = modules 1-4 (summarised away), "phase 2: edge modules" = 5-6
MODULE_OF = {path: module for module, paths in MODULE_PLAN.items() for path in paths}


def score_listing(answer: str) -> dict[str, str]:
    """A class counts when ONE line of the answer holds both its name and its exact path (C15)."""
    lines = answer.splitlines()
    found = {name for name, path in CLASSES.items() if any(name in line and path in line for line in lines)}
    return {group: f"{sum(MODULE_OF[CLASSES[name]] in modules for name in found)}/{3 * len(modules)}"
            for group, modules in GROUPS.items()}


def generic_phrases(text: str) -> list[str]:
    """The degradation symptom: typical patterns where specific classes and paths should be (C16)."""
    return re.findall(r"\b(?:typical|usual|standard)\b|follows the [\w -]{0,40}?pattern", text, re.IGNORECASE)


async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc2_scratchpad")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    early = [name for name, path in CLASSES.items() if MODULE_OF[path] in PHASES["phase 1: core modules"]]
    for run_name, scratchpad in RUNS:
        state, history = ExploreState(fresh_run_dir(run_name)), []  # a new state and an empty work/<run>/
        notes = state.run_dir / "scratchpad.md"
        try:
            for n, module in enumerate(MODULE_PLAN, 1):
                await explore_module(settings, state, history, n, module, scratchpad)
                if scratchpad:  # the notes are on disk BEFORE the loss comes (C7)
                    log.info("Step %d (%s): scratchpad.md holds %d entries", n, module,
                             sum(len(lines) for lines in read_sections(notes).values()))
                if n == SUMMARISE_AFTER:
                    history[:] = [LOSSY_HISTORY]  # the context degrades: every name from modules 1-4 is gone (E3)
                    kept = notes.read_text(encoding="utf-8") if notes.is_file() else ""
                    log.info("After step %d the history holds %d of the %d module 1-4 class names; scratchpad.md holds "
                             "%s", n, sum(name in history[0] for name in early), len(early),
                             sum(name in kept for name in early) if scratchpad else "nothing (no file)")  # (C5)
            # The final question gets no Read tool: only the history, and the scratchpad if there is one (E4)
            final = await run_agent(build_step_prompt(history, FINAL_TASK),
                                    build_explorer_options(settings, state, scratchpad, final=True))
        except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
            log.error("SDK error: %s", exc)
            return 1

        answer = final["answer"] or ""
        log.info("Run %s: classes listed with their exact path %s; generic phrases %s; Read calls in the final step: "
                 "%d", run_name, score_listing(answer), generic_phrases(answer), final["tool_calls"].count("Read"))
        if scratchpad and notes.is_file():  # the file: exact names and paths, no summaries (C6)
            key_classes = read_sections(notes)["## Key classes"]
            exact = sum(any(name in entry and path in entry for name, path in CLASSES.items()) for entry in key_classes)
            log.info("scratchpad.md: %d of %d Key classes entries name a class with its exact file; generic phrases "
                     "%s\n%s", exact, len(key_classes), generic_phrases(notes.read_text(encoding="utf-8")),
                     notes.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
