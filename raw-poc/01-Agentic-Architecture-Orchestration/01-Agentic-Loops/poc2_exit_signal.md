"""
POC 2a - Which message tells you the agent is DONE?   (offline: no API call, free)
==================================================================================
Replays a recorded message stream of the task "37 shares of Nimbus Robotics plus a 1.5% fee",
built from the SDK's own classes, and tries 3 ways to find the final answer.

Claude writes text for humans at any point in the loop, even the words "final answer" before
it is done. Only the ResultMessage is a reliable end signal, so only answer_from_result() works.

Run:  python poc2_exit_signal.py
"""

import sys
from typing import Any

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolResultBlock, ToolUseBlock, UserMessage

MODEL = "claude-sonnet-5-5"  # only a label inside the recording
FINAL_TEXT = "37 shares would cost $7,038.56 including the 1.5% fee."  # message 7: the real answer


def recorded_stream() -> list[Any]:
    """The stream as the SDK yields it: one content block per message."""
    price = [{"type": "text", "text": "Nimbus Robotics shares last traded at $187.42."}]
    return [
        # 1-2  narration, then the same response asks for the search tool
        AssistantMessage(content=[TextBlock("I'll look up the current share price first.")], model=MODEL),
        AssistantMessage(
            content=[ToolUseBlock("toolu_01", "mcp__poc__web_search", {"query": "Nimbus Robotics share price"})],
            model=MODEL,
        ),
        # 3  the SDK feeds the tool result back to Claude
        UserMessage(content=[ToolResultBlock(tool_use_id="toolu_01", content=price)]),
        # 4-5  narration that happens to contain "final answer", then the calculator call
        AssistantMessage(content=[TextBlock("Before I give my final answer, let me calculate the total.")], model=MODEL),
        AssistantMessage(
            content=[ToolUseBlock("toolu_02", "mcp__poc__calculator", {"expression": "187.42 * 37 * 1.015"})],
            model=MODEL,
        ),
        # 6
        UserMessage(content=[ToolResultBlock(tool_use_id="toolu_02", content=[{"type": "text", "text": "7038.5581"}])]),
        # 7  the real final answer
        AssistantMessage(content=[TextBlock(FINAL_TEXT)], model=MODEL),
        # 8  the end signal (the timing and session fields are required, so they get dummy values)
        ResultMessage(
            subtype="success", duration_ms=0, duration_api_ms=0, is_error=False, num_turns=3,
            session_id="recorded-session", stop_reason="end_turn", result=FINAL_TEXT,
        ),
    ]


def answer_from_first_text(messages: list[Any]) -> str | None:
    """Anti-pattern 1 (content-type check): the first message that contains text is the answer."""
    for message in messages:
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    return block.text
    return None


def answer_from_phrase(messages: list[Any]) -> str | None:
    """Anti-pattern 2 (natural-language parsing): the first text that says "final answer"."""
    for message in messages:
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock) and "final answer" in block.text.lower():
                    return block.text
    return None


def answer_from_result(messages: list[Any]) -> str | None:
    """Correct: the ResultMessage is the loop's deterministic end signal."""
    for message in messages:
        if isinstance(message, ResultMessage) and message.subtype == "success" and message.stop_reason == "end_turn":
            return message.result
    return None


def main() -> int:
    try:
        messages = recorded_stream()
    except TypeError:  # a newer SDK may rename a field of these message classes
        return 1

    for strategy in (answer_from_first_text, answer_from_phrase, answer_from_result):
        answer = strategy(messages)  # only answer_from_result() returns FINAL_TEXT
    return 0


if __name__ == "__main__":
    sys.exit(main())
