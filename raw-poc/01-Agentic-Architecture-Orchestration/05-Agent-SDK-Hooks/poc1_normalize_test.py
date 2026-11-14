"""
POC 1 - Normalizing tool results with a PostToolUse hook
=========================================================
Three order systems answer the same question in three formats:

    A: 1776686400, status 2      B: "2026-04-28", "delivered"      C: "04/05/2026", "P"

A PostToolUse hook runs AFTER a handler returns and BEFORE Claude sees the result, and replaces the result
(updatedToolOutput) with ISO 8601 dates and English statuses. Compare the two runs' tool results:

    baseline:    ... "order_date": "04/05/2026", "status": "P" ...
    normalized:  ... "order_date": "2026-05-04", "status": "pending" ...

Per run the code checks Claude's ORDERS summary against the truth.

Run:  python poc1_normalize_test.py     (2 short API runs)
"""

import asyncio
import json
import re
import sys
from datetime import date, datetime, timezone
from typing import Any

from claude_agent_sdk import ClaudeSDKError, HookMatcher

from common import load_settings
from hooks_setup import HookState, build_hook_options, response_text, run_agent

NUMERIC_STATUS = {0: "pending", 1: "processed", 2: "shipped", 3: "delivered", 9: "cancelled"}  # system A's codes
LETTER_STATUS = {"P": "pending", "R": "processed", "S": "shipped", "D": "delivered", "C": "cancelled"}  # system C's


def to_iso(value: int | str) -> str:
    if isinstance(value, int):  # A: Unix seconds. Pin UTC: in local time the same instant can be another day
        return datetime.fromtimestamp(value, tz=timezone.utc).date().isoformat()
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):  # C: DAY first. Read month-first, 04/05 would become April 5
        return datetime.strptime(value, "%d/%m/%Y").date().isoformat()
    return date.fromisoformat(value).isoformat()  # B: already ISO 8601 (raises on anything else)


def to_status(value: int | str) -> str:
    if isinstance(value, int):
        return NUMERIC_STATUS[value]
    return LETTER_STATUS[value] if len(value) == 1 else value.lower()  # "P" is pending, not processed (that's "R")


def normalize_record(record: dict) -> dict:
    return {**record, "order_date": to_iso(record["order_date"]), "status": to_status(record["status"])}


def same_shape(tool_response: Any, text: str) -> Any:
    """updatedToolOutput must have the shape of the tool's output, and MCP output isn't validated (E3)."""
    if isinstance(tool_response, dict):
        return {**tool_response, "content": [{"type": "text", "text": text}]}
    if isinstance(tool_response, list):
        return [{"type": "text", "text": text}]
    return text


async def normalize_output(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
    """PostToolUse: the handler has run (tool_response exists) and Claude hasn't seen the result yet (C3, C4)."""
    tool_response = input_data["tool_response"]
    try:
        data = json.loads(response_text(tool_response))
        data["orders"] = [normalize_record(record) for record in data["orders"]]
    except (ValueError, KeyError, TypeError):  # not an order list: leave the result alone
        return {}
    # updatedToolOutput goes INSIDE hookSpecificOutput, never at the top level (C6)
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                   "updatedToolOutput": same_shape(tool_response, json.dumps(data))}}


# PostToolUse, not PreToolUse: a PreToolUse hook runs before the handler, so there is no result yet to rewrite;
# it only sees tool_input (C7). "mcp__orders__.*" is a regex: every tool of the orders server.
NORMALIZE_HOOKS = {"PostToolUse": [HookMatcher(matcher="mcp__orders__.*", hooks=[normalize_output])]}

TEST_PROMPT = (
    "Customer CUST-3318 has one order in each of our order systems A, B and C. List the three orders oldest first, "
    "quoting each order's date and status exactly as the tools give them. End with one line in exactly this form: "
    "ORDERS: <order ids, oldest first> | PENDING: <ids of pending orders, or none>"
)
TRUTH = {"orders": ["LS-1042", "LS-2087", "LS-3150"], "pending": ["LS-3150"]}

RUNS = [  # (name, hooks)
    ("baseline", None),  # Claude decodes 3 date formats and 3 status forms itself (C2)
    ("normalized", NORMALIZE_HOOKS),  # Claude only ever sees ISO dates and English statuses (C10)
]


def parse_summary(answer: str) -> dict | None:
    """The ORDERS line Claude was asked to end with, as {"orders": [...], "pending": [...]} (C9)."""
    lines = [line for line in answer.splitlines() if "ORDERS:" in line and "PENDING:" in line]
    if not lines:
        return None
    orders_part, pending_part = lines[-1].split("PENDING:", 1)
    return {"orders": re.findall(r"LS-\d{4}", orders_part), "pending": re.findall(r"LS-\d{4}", pending_part)}


async def main() -> int:
    try:
        settings = load_settings()
    except (OSError, RuntimeError):
        return 1

    for name, hooks in RUNS:
        try:
            run = await run_agent(TEST_PROMPT, build_hook_options(settings, HookState(), "orders", hooks))
        except ClaudeSDKError:  # Claude Code not found, its process crashed, ...
            return 1
        summary = parse_summary(run["answer"] or "")
        matches_truth = summary == TRUTH
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
