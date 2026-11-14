"""
POC 1 - Custom tools and one tool round-trip
=============================================
For each prompt the log shows what goes INTO the model and what comes OUT of it:

    MODEL INPUT   prompt       your question
    MODEL OUTPUT  tool_use     Claude asks for a tool                   (id=X)
    MODEL INPUT   tool_result  the SDK ran your handler, fed it back    (tool_use_id=X)
    MODEL OUTPUT  text         Claude's answer
    MODEL OUTPUT  stop_reason  end_turn: Claude is done

The SDK runs this round-trip for you. Your code defines the tools (tools.py) and reads the stream.

Run:  python poc1_round_trip.py     (3 short API runs)
"""

import asyncio
import sys

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKError, ResultError, ResultMessage, query

from common import load_settings, log, log_model_io, setup_logging
from tools import build_options

# Claude picks the tool (or no tool) from each prompt. No code tells it which one.
PROMPTS = [
    "What is 1,234 multiplied by 5,678?",  # expect: calculator
    "What is Nimbus Robotics' share price right now?",  # expect: web_search
    "In one sentence, what is an API?",  # expect: no tool
    # "Use the calculator to evaluate exactly this expression: 2 ** 10",  # optional: a failing tool (is_error=True)
]


async def run(prompt: str, options: ClaudeAgentOptions) -> str | None:
    """Stream one query() call. Returns the final answer, or None if the loop didn't finish.

    No tool call, no history list and no loop here: the SDK calls Claude, runs our handler when
    Claude asks for a tool, appends tool_use + tool_result to the session history (the API is
    stateless, so the SDK resends that history every turn) and calls Claude again.
    """
    log.info("MODEL INPUT   prompt       %s", prompt)
    answer = None
    try:
        async for message in query(prompt=prompt, options=options):
            log_model_io(message)
            # The ResultMessage ends the loop. .result holds the final answer when Claude finished.
            if isinstance(message, ResultMessage) and message.subtype == "success" and message.stop_reason == "end_turn":
                answer = message.result
            # No `break`: a few system events can still arrive after the ResultMessage.
    except ResultError as exc:  # raised AFTER an error ResultMessage, e.g. an invalid API key or the cost guard
        log.error("The run failed: %s", exc)
    return answer


async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc1_round_trip")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    for prompt in PROMPTS:
        try:
            await run(prompt, build_options(settings))
        except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
            log.error("SDK error: %s", exc)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
