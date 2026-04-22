"""
ANTI-PATTERN #3: Checking for the presence of assistant text as a completion signal.

This approach assumes: "if the model produced text, it must be done."

Why this is wrong:
- The model often emits text AND tool calls in the same response.
  Example: "Let me check your balance..." [text] + get_account_balance [tool_use]
- Text presence tells you the model had something to SAY, not that it's
  DONE. These are fundamentally different signals.
- Only stop_reason distinguishes "text that accompanies a tool call"
  from "text that is the final answer."
"""

import os
import json
import anthropic
from tools import TOOLS, execute_tool

client = anthropic.Anthropic()


def has_text_content(response) -> bool:
    """Check if the response contains any text blocks."""
    return any(hasattr(block, "text") and block.text.strip() for block in response.content)


def run_text_presence(user_message: str):
    print(f"\n{'='*60}")
    print(f"ANTI-PATTERN: Text presence as completion signal")
    print(f"{'='*60}")
    print(f"User: {user_message}\n")

    messages = [{"role": "user", "content": user_message}]
    iteration = 0

    while True:
        iteration += 1
        response = client.messages.create(
            model=os.getenv("MODEL_ID", "claude-sonnet-4-20250514"),
            max_tokens=1024,
            tools=TOOLS,
            messages=messages,
        )

        print(f"  [Iteration {iteration} | stop_reason: {response.stop_reason}]")

        # Log what content types are present — this is what makes the bug visible.
        content_types = [getattr(b, "type", "?") for b in response.content]
        print(f"  Content blocks: {content_types}")

        # BUG: "Has text" ≠ "Is done". The model frequently produces text
        # alongside tool_use blocks — e.g., "I'll look that up for you..."
        # followed by a tool call. This check exits before the tool runs.
        if has_text_content(response):
            print(f"  >>> Text detected — assuming completion <<<")
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"\nAssistant: {block.text}")
            # PROBLEM: Any tool_use blocks in this response are silently
            # dropped. The model wanted to act, but we stopped it.
            tool_calls_dropped = [b.name for b in response.content if b.type == "tool_use"]
            if tool_calls_dropped:
                print(f"\n  !!! DROPPED TOOL CALLS: {tool_calls_dropped} !!!")
            break

        # This branch rarely executes because the model almost always
        # includes explanatory text with its tool calls.
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  Tool: {block.name}({json.dumps(block.input)})")
                    result = execute_tool(block.name, block.input)
                    print(f"  Result: {result}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})

    print(f"  Total iterations: {iteration}")


if __name__ == "__main__":
    print("\n" + "#"*60)
    print("# The model will likely say 'Let me check...' AND call a tool.")
    print("# The text-presence check fires on the text → tool call is dropped.")
    print("#"*60)
    run_text_presence(
        "Check my balance on ACC-001, show recent transactions, "
        "then transfer $100 to ACC-002."
    )
