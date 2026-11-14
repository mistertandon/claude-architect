"""
POC 1 - Case facts that survive summarisation
==============================================
One support conversation of 6 customer turns. Python owns the history: each turn is a fresh query(), and
build_prompt() writes the whole prompt, top to bottom:

    === CASE FACTS ===            exact values the PostToolUse hook copied from RAW tool results (never summarised)
    === CONVERSATION SUMMARY ===  from turn 5 on: a lossy summary that replaced turns 1-4
    === RECENT TURNS ===          the latest turns, word for word
    === CUSTOMER MESSAGE ===      what Claude answers now

Turns 5-6 run twice from the same summary: with the CASE FACTS block and without it. Same summary, model, tools and
hook: only the block differs, and only that version can still quote RF-0001, $247.83, ORD-8891 and the order date.

Besides model I/O, the log shows one line on the trim (turns 1-4's prompt sizes, with and without it) and one line
per version of turns 5-6: which of the 4 exact values its replies quoted.

Run:  python poc1_case_facts.py     (3 runs: turns 1-4, then turns 5-6 with and without the block: 8 query() calls)
"""

import asyncio
import copy
import json
import re
import sys

from claude_agent_sdk import ClaudeSDKError

from common import Settings, load_settings, log, setup_logging
from context_setup import LOOKUP_ORDER, CaseState, build_case_options, run_agent

FACTS_HEADER = "=== CASE FACTS (exact values from tool results; never summarised) ==="
SUMMARY_HEADER = "=== CONVERSATION SUMMARY (turns 1-4) ==="
RECENT_HEADER = "=== RECENT TURNS ==="
MESSAGE_HEADER = "=== CUSTOMER MESSAGE ==="

SUMMARISE_AFTER = 4
# Fixed text, the same in both versions, with no digit in it (E2): the story survives, the numbers don't.
# A live summariser might keep the numbers in one version and not the other, and the test would pass by luck.
LOSSY_SUMMARY = (
    "The customer contacted us about a lamp from a recent order that arrived damaged. The agent looked the order up, "
    "confirmed it could be returned and refunded it in full to the customer's card. The customer then asked how long "
    "the refund takes and whether the lamp has to be sent back, and the agent explained the usual timing and the "
    "emailed return label."
)
PROBES = {  # the exact values the replies of turns 5-6 should still quote (C13)
    "RF-0001": r"RF-0001",
    "247.83": r"247\.83",
    "8891": r"8891",
    "March 3": r"2026-03-03|March 3(?!\d)|3(?:rd)? March",
}

TURNS = [  # the customer's 6 messages
    "Hi, this is Dana Reyes (customer CUST-1042). The floor lamp from order ORD-8891 arrived with a cracked base. "
    "Can I return it?",  # lookup_order: the case facts now hold 5 values
    "Yes please, refund it to my card.",  # process_refund: 9 values
    "How long until the money shows up?",  # no tool: the refund record says 5-7 business days
    "Do I need to send the lamp back first?",  # no tool. Then the summary replaces turns 1-4
    "What's my refund reference number, and has the refund actually gone through?",  # probe: RF-0001
    "Before I go, can you confirm the refund amount, my order number and the date I placed that order?",  # 3 probes
]
ARMS = [("with-facts", True), ("without-facts", False)]  # runs 2 and 3: turns 5-6, after the summary


def render_history(turns: list[dict]) -> str:
    """Turn records as text: the customer, each tool result exactly as Claude received it, and the reply."""
    blocks = []
    for turn in turns:
        lines = [f"Turn {turn['n']}", f"Customer: {turn['customer']}"]
        lines += [f"Tool {name}: {text}" for name, text in turn["tools"]]
        blocks.append("\n".join(lines + [f"Agent: {turn['agent']}"]))
    return "\n\n".join(blocks)


def build_prompt(case_facts: dict | None, summary: str | None, recent: list[dict], message: str) -> str:
    """The case facts block on top, then the summarised history, then the recent turns, then the new message (C5)."""
    sections = []
    if case_facts is not None:  # structured data, OUTSIDE the history: no summary can touch it (C4, C6)
        sections.append(f"{FACTS_HEADER}\n{json.dumps(case_facts, indent=2)}")
    if summary:
        sections.append(f"{SUMMARY_HEADER}\n{summary}")
    if recent:
        sections.append(f"{RECENT_HEADER}\n{render_history(recent)}")
    sections.append(f"{MESSAGE_HEADER}\n{message}")
    return "\n\n".join(sections)


def summarise(turns: list[dict]) -> str:
    """Stands in for a summariser model call (C11). It gets the turn records only, never state.case_facts (C3)."""
    return LOSSY_SUMMARY


def quoted(text: str) -> dict[str, bool]:
    """Which of the 4 exact values a reply quotes (C13)."""
    return {name: re.search(pattern, text) is not None for name, pattern in PROBES.items()}


async def run_turn(settings: Settings, n: int, message: str, state: CaseState, summary: str | None,
                   recent: list[dict], with_facts: bool) -> dict:
    """One customer turn = one fresh query(): the prompt Python writes is ALL the history Claude sees (E1)."""
    # The block is rebuilt from state.case_facts on every turn, so it is never part of the history (C4)
    prompt = build_prompt(state.case_facts if with_facts else None, summary, recent, message)
    run = await run_agent(prompt, build_case_options(settings, state))
    return {
        "n": n,
        "customer": message,
        "tools": [(result["name"].split("__")[-1], result["text"]) for result in run["tool_results"]],
        "agent": run["answer"] or "(no answer)",
        "prompt_chars": len(prompt),
        "lookups": sum(name == "lookup_order" for turn in recent for name, _ in turn["tools"]),  # in this history
    }


async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc1_case_facts")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    state, recent = CaseState(), []
    try:  # run 1: turns 1-4, every prompt starts with the block
        for n in range(1, SUMMARISE_AFTER + 1):
            recent.append(await run_turn(settings, n, TURNS[n - 1], state, None, recent, with_facts=True))
    except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
        log.error("SDK error: %s", exc)
        return 1

    # The saving the model I/O can't show: Claude never saw the raw lookup, and every later prompt resends the
    # history, so an untrimmed lookup would cost its extra characters again in each of them (C8, C10)
    lookup = next((size for size in state.sizes if size[0] == LOOKUP_ORDER), None)
    if lookup:
        _, raw_chars, sent_chars = lookup
        log.info("PostToolUse trim: lookup_order %d -> %d chars (%.1f%% smaller). Prompt chars of turns 1-4: %s; "
                 "with the untrimmed lookup in their history: %s", raw_chars, sent_chars,
                 100 * (1 - sent_chars / raw_chars), [turn["prompt_chars"] for turn in recent],
                 [turn["prompt_chars"] + turn["lookups"] * (raw_chars - sent_chars) for turn in recent])

    summary = summarise(recent)  # the summary replaces turns 1-4; state.case_facts never passes through it (C3)

    for arm, with_facts in ARMS:  # same summary, model, tools and hook: only the CASE FACTS block differs (C12, C14)
        arm_state, arm_recent = copy.deepcopy(state), []
        try:
            for n in range(SUMMARISE_AFTER + 1, len(TURNS) + 1):
                arm_recent.append(await run_turn(settings, n, TURNS[n - 1], arm_state, summary, arm_recent, with_facts))
        except ClaudeSDKError as exc:
            log.error("SDK error: %s", exc)
            return 1
        found = quoted("\n".join(turn["agent"] for turn in arm_recent))
        log.info("Turns 5-6 %s: prompt chars %s; quoted %d of 4 exact values: %s", arm,
                 [turn["prompt_chars"] for turn in arm_recent], sum(found.values()),
                 ", ".join(f"{name} {'yes' if ok else 'NO'}" for name, ok in found.items()))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
