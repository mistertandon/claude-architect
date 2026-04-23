"""
ANTI-PATTERN #2: Using an arbitrary iteration cap as the PRIMARY stop mechanism.

This approach sets MAX_ITERATIONS and relies on it to end the loop.

Why this is wrong:
- An iteration cap is a SAFETY NET, not a control flow mechanism.
- Setting it too low (e.g., 3) silently truncates complex tasks that
  need 4+ tool calls — the user gets an incomplete answer with no error.
- Setting it too high (e.g., 100) provides no real protection.
- The correct signal (stop_reason == "end_turn") already exists.
  The cap should be a fallback for runaway loops, not the primary exit.
"""

import os
import json
import anthropic
from tools import TOOLS, execute_tool
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic()

# Arbitrary cap chosen by the developer. Any number is wrong:
# - Too low: truncates legitimate multi-step tasks
# - Too high: doesn't protect against anything meaningful
MAX_ITERATIONS = 3


def run_iteration_cap(user_message: str):
    print(f"\n{'='*60}")
    print(f"ANTI-PATTERN: Iteration cap as primary stop (max={MAX_ITERATIONS})")
    print(f"{'='*60}")
    print(f"User: {user_message}\n")

    messages = [{"role": "user", "content": user_message}]

    # BUG: The loop condition is the iteration count, not stop_reason.
    # stop_reason is checked inside but the cap dominates termination.
    for iteration in range(1, MAX_ITERATIONS + 1):
        response = client.messages.create(
            model=os.getenv("MODEL_ID", "claude-sonnet-4-6"),
            max_tokens=1024,
            tools=TOOLS,
            messages=messages,
        )

        print(f"\nModel response {response}")
        print(f"  [Iteration {iteration}/{MAX_ITERATIONS} | stop_reason: {response.stop_reason}]")

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"\nAssistant: {block.text}")
            return  # Correct exit, but only if we get here before the cap

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

    # PROBLEM: We hit the cap. The model may have been mid-task — it called
    # a tool in iteration 3, got a result, but never got a chance to use it.
    # The user gets a silently incomplete answer.
    print(f"\n  >>> HIT ITERATION CAP ({MAX_ITERATIONS}) — loop terminated <<<")
    print(f"  The model may not have finished its task.")
    print(f"  Last stop_reason was: {response.stop_reason}")


if __name__ == "__main__":
    print("\n" + "#"*60)
    print("# This task needs ~4 iterations (balance + txns + transfer + summary)")
    print("# but the cap is 3 — the transfer may never execute.")
    print("#"*60)
    run_iteration_cap(
        "Check my balance on ACC-001, show recent transactions, "
        "then transfer $100 to ACC-002."
    )
