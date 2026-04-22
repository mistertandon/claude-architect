"""
MODEL-DRIVEN approach: Claude decides which tools to call, in what order,
and whether to call them at all — based on the user's intent and prior results.

This is the correct agentic pattern. The model acts as the reasoning engine;
the developer provides tools but does NOT dictate the sequence.
"""

import os
import json
import anthropic
from tools import TOOLS, execute_tool

client = anthropic.Anthropic()


def run_model_driven(user_message: str):
    print(f"\n{'='*60}")
    print(f"MODEL-DRIVEN AGENT")
    print(f"{'='*60}")
    print(f"User: {user_message}\n")

    messages = [{"role": "user", "content": user_message}]
    iteration = 0

    # The loop has NO knowledge of which tools exist or what order they should
    # run in. It simply relays the model's decisions and feeds back results.
    # This is intentional — the orchestration logic lives in the model, not here.
    while True:
        iteration += 1

        response = client.messages.create(
            model=os.getenv("MODEL_ID", "claude-sonnet-4-20250514"),
            max_tokens=1024,
            tools=TOOLS,
            # All tools are offered equally. The model picks based on the
            # conversation context, not because we told it to.
            messages=messages,
            system=(
                "You are a shopping assistant. Help the user find products, "
                "check availability, estimate shipping, and apply discounts. "
                "Use the tools available to you as needed."
                # Note: no instructions about tool ORDER — the model decides.
            ),
        )

        print(f"  [Iteration {iteration} | stop_reason: {response.stop_reason}]")

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"\nAssistant: {block.text}")
            break

        # We don't inspect WHICH tool was called or branch on it.
        # The loop is tool-agnostic — it just executes whatever the model chose.
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"  Model chose: {block.name}({json.dumps(block.input)})")
                result = execute_tool(block.name, block.input)
                print(f"  Result: {result}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        messages.append({"role": "user", "content": tool_results})

    return messages


if __name__ == "__main__":
    # Prompt 1: The model will likely search → check inventory → maybe shipping.
    # But we don't TELL it that order — it figures it out.
    print("\n" + "#"*60)
    print("# SCENARIO 1: Open-ended product inquiry")
    print("#"*60)
    run_model_driven(
        "I'm looking for a laptop I can get delivered to Seattle quickly. "
        "I also have a discount code SAVE10."
    )

    # Prompt 2: Different intent → model picks a completely different tool path.
    # Same code, same loop, but the model adapts its strategy.
    print("\n" + "#"*60)
    print("# SCENARIO 2: Direct inventory question (no search needed)")
    print("#"*60)
    run_model_driven("Is product HP-1 in stock?")
