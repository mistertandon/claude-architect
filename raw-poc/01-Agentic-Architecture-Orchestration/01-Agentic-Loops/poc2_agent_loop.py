"""
POC 2b - The agent loop, its end signal and its safety cap
===========================================================
One query() call runs the whole agent loop. The SDK repeats the turn

    Claude -> tool_use -> your handler -> tool_result -> Claude

until Claude answers without asking for a tool (stop_reason=end_turn).

  * This code has no while-loop and no tool order: Claude decides what to call and when.
  * "Done" is decided ONLY from the ResultMessage (subtype + stop_reason), never from text.
    poc2_exit_signal.py shows why.
  * max_turns is a safety net. When it fires, the run ends with subtype=error_max_turns and no answer.

Run (after the free demo: python poc2_exit_signal.py):
    python poc2_agent_loop.py     (3 short API runs)
"""

import asyncio
import sys

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKError, ResultError, ResultMessage, query

from common import load_settings
from tools import build_options

SEQUENTIAL_PROMPT = (
    "How much would 37 shares of Nimbus Robotics cost at the current price, including a 1.5% brokerage fee?"
)

# (prompt, max_turns); None = MAX_TURNS from .env
RUNS = [
    ("In one sentence, what is an API?", None),  # no tool needed: the loop ends after one turn
    (SEQUENTIAL_PROMPT, None),  # web_search, then calculator: the search result feeds the calculation
    (SEQUENTIAL_PROMPT, 1),  # the same task with max_turns=1: the safety cap cuts the loop off
    # ("What is 12 times 7, and what is 99 divided by 3?", None),  # optional: two tool calls in ONE response
]


async def run_agent(user_prompt: str, options: ClaudeAgentOptions) -> str | None:
    """Run one agent task. Returns the final answer, or None if the loop didn't finish."""
    answer = None
    try:
        async for message in query(prompt=user_prompt, options=options):  # every turn of the loop runs in here
            # The stop signal: success + end_turn means Claude finished. Never check the text instead.
            if isinstance(message, ResultMessage) and message.subtype == "success" and message.stop_reason == "end_turn":
                answer = message.result
            # No `break`: a few system events can still arrive after the ResultMessage.
    except ResultError:
        # A single-shot query() raises AFTER it yielded an error ResultMessage,
        # e.g. error_max_turns (the safety cap), error_max_budget_usd, error_during_execution, an invalid API key.
        pass
    return answer


async def main() -> int:
    try:
        settings = load_settings()
    except (OSError, RuntimeError):
        return 1

    for prompt, max_turns in RUNS:
        try:
            await run_agent(prompt, build_options(settings, max_turns=max_turns or settings.max_turns))
        except ClaudeSDKError:  # Claude Code not found, its process crashed, ...
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
