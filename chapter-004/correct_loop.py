"""
CORRECT agentic loop: uses stop_reason as the SOLE termination signal.

The API's stop_reason is a structured, machine-readable field that the model
sets deliberately. It is the ONLY reliable way to know if the model is done.
"""

import os
import json
import anthropic
from tools import TOOLS, execute_tool
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic()


def run_correct(user_message: str):
    print(f"\n{'='*60}")
    print(f"CORRECT: stop_reason-based loop")
    print(f"{'='*60}")
    print(f"User: {user_message}\n")

    messages = [{"role": "user", "content": user_message}]
    iteration = 0

    while True:
        iteration += 1
        response = client.messages.create(
            model=os.getenv("MODEL_ID", "claude-sonnet-4-6"),
            max_tokens=1024,
            tools=TOOLS,
            messages=messages,
        )

        print(f"\nModel response {response}")
        print(f"  [Iteration {iteration} | stop_reason: {response.stop_reason}]")

        # stop_reason is an enum, not free text. "end_turn" and "tool_use"
        # are the only two values we need to handle. This is a protocol-level
        # signal — deterministic, unambiguous, impossible to misinterpret.
        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"\nAssistant: {block.text}")
            break

        # "tool_use" means the model explicitly chose to call a tool.
        # No guessing, no parsing — the model told us through the API contract.
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
    print("# Scenario 1: Multi-step task (balance + transactions + transfer)")
    print("#"*60)
    run_correct(
        "Check my balance on ACC-001, show recent transactions, "
        "then transfer $100 to ACC-002."
    )

    print("\n" + "#"*60)
    print("# Scenario 2: Single-step task")
    print("#"*60)
    run_correct("What's the balance on ACC-003?")
