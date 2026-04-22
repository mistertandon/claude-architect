"""
PRE-CONFIGURED approach: The developer hardcodes the tool sequence.
Every query runs the same pipeline regardless of what the user actually needs.

This is the ANTI-PATTERN for agentic systems. Included here to contrast with
the model-driven approach and show why it's inferior.
"""

import os
import json
import anthropic
from tools import TOOLS, execute_tool

client = anthropic.Anthropic()


def run_preconfigured(user_message: str):
    print(f"\n{'='*60}")
    print(f"PRE-CONFIGURED PIPELINE")
    print(f"{'='*60}")
    print(f"User: {user_message}\n")

    # The developer has decided the sequence upfront. The model is reduced
    # to a slot-filler — extracting parameters, not making decisions.
    pipeline = [
        {"tool": "search_products", "extract_prompt": (
            "Extract the product search keyword from this user message. "
            "Respond with ONLY a JSON object: {\"query\": \"...\"}"
        )},
        {"tool": "check_inventory", "extract_prompt": (
            "From the search results, pick the first product ID. "
            "Respond with ONLY a JSON object: {\"product_id\": \"...\"}"
        )},
        {"tool": "get_shipping_estimate", "extract_prompt": (
            "Extract the product_id from the previous step and the destination "
            "city from the user message. "
            "Respond with ONLY a JSON object: {\"product_id\": \"...\", \"destination\": \"...\"}"
        )},
    ]

    context = f"User request: {user_message}\n"

    for i, step in enumerate(pipeline):
        print(f"  [Step {i+1}: FORCED call to {step['tool']}]")

        # The model isn't choosing to call this tool — we are forcing it.
        # We use the model only to extract parameters, wasting its reasoning ability.
        extraction = client.messages.create(
            model=os.getenv("MODEL_ID", "claude-sonnet-4-20250514"),
            max_tokens=256,
            messages=[{"role": "user", "content": context + "\n" + step["extract_prompt"]}],
        )

        try:
            params = json.loads(extraction.content[0].text.strip())
        except (json.JSONDecodeError, IndexError):
            print(f"  Failed to extract params, skipping step")
            continue

        print(f"  Extracted params: {json.dumps(params)}")
        result = execute_tool(step["tool"], params)
        print(f"  Result: {result}")

        # Accumulate context as a string — no structured message history,
        # no tool_use_id correlation. The model can't reason about the
        # relationship between calls.
        context += f"\n{step['tool']} result: {result}\n"

    # Final summary call — the model sees a blob of text, not a structured
    # conversation it participated in.
    print(f"\n  [Final: summarize results]")
    summary = client.messages.create(
        model=os.getenv("MODEL_ID", "claude-sonnet-4-20250514"),
        max_tokens=512,
        messages=[{"role": "user", "content": (
            context + "\nSummarize these results for the user in a helpful way."
        )}],
    )
    print(f"\nAssistant: {summary.content[0].text}")


if __name__ == "__main__":
    # Same scenarios as model_driven.py — watch how the pipeline fails to adapt.

    print("\n" + "#"*60)
    print("# SCENARIO 1: Open-ended product inquiry")
    print("# Problem: Pipeline runs all 3 steps even though the user also")
    print("# wants a discount applied — but that's not in the pipeline.")
    print("#"*60)
    run_preconfigured(
        "I'm looking for a laptop I can get delivered to Seattle quickly. "
        "I also have a discount code SAVE10."
    )

    # Problem: This only needs check_inventory, but the pipeline forces
    # search_products first (wasteful) and shipping estimate (irrelevant).
    print("\n" + "#"*60)
    print("# SCENARIO 2: Direct inventory question")
    print("# Problem: Pipeline wastes 2 unnecessary API calls and tool")
    print("# executions because the sequence is hardcoded.")
    print("#"*60)
    run_preconfigured("Is product HP-1 in stock?")
