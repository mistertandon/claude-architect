import os
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic()

tools = [
    {
        "name": "lookup_order",
        "description": "Look up an order by order ID and return its details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "The order ID to look up"}
            },
            "required": ["order_id"]
        }
    },
    {
        "name": "check_inventory",
        "description": "Check current inventory stock for a product.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "The product ID to check"}
            },
            "required": ["product_id"]
        }
    }
]

MOCK_ORDERS = {
    "ORD-101": {"product_id": "PROD-A", "qty": 2, "status": "pending_restock"},
    "ORD-102": {"product_id": "PROD-B", "qty": 1, "status": "shipped"},
}

MOCK_INVENTORY = {
    "PROD-A": {"stock": 0, "restock_date": "2026-04-25"},
    "PROD-B": {"stock": 45, "restock_date": None},
}


def execute_tool(name: str, inp: dict) -> str:
    if name == "lookup_order":
        return json.dumps(MOCK_ORDERS.get(inp["order_id"], {"error": "not found"}))
    if name == "check_inventory":
        return json.dumps(MOCK_INVENTORY.get(inp["product_id"], {"error": "not found"}))
    return json.dumps({"error": f"unknown tool: {name}"})


def run_agent(user_message: str):
    print(f"\n{'='*60}")
    print(f"User: {user_message}")
    print(f"{'='*60}")

    messages = [{"role": "user", "content": user_message}]
    iteration = 0

    while True:
        iteration += 1
        print(f"\n--- Iteration {iteration} ---")
        # The entire messages list is sent each call. This is how the model
        # "remembers" prior tool calls and their results — it has no state
        # between calls, so the history IS the model's working memory.
        print(f"  Messages in history: {len(messages)}")

        response = client.messages.create(
            model=os.getenv("MODEL_ID", "claude-sonnet-4-6"),
            max_tokens=1024,
            tools=tools,
            messages=messages,
        )

        print(f"\nModel response {response}")
        print(f"  stop_reason: {response.stop_reason}")

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"\nAssistant: {block.text}")
            break

        # --- The critical history-building section ---

        # Step 1: Append the assistant's full response as-is.
        # This preserves both text blocks (chain-of-thought) AND tool_use
        # blocks (call metadata). Omitting either would break the
        # alternating-role contract the API enforces.
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"  Tool call: {block.name}({json.dumps(block.input)})")
                result = execute_tool(block.name, block.input)
                print(f"  Result:    {result}")

                # Step 2: Each tool_result must reference tool_use_id so the
                # model can correlate which result answers which call — critical
                # when the model issues multiple parallel tool calls in one turn.
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        # Step 3: All tool results go in a single "user" message.
        # The API models tool results as user-role messages because from the
        # model's perspective, the external world (user side) is providing
        # the requested data back.
        messages.append({"role": "user", "content": tool_results})

    # --- Dump final conversation history for inspection ---
    print(f"\n{'='*60}")
    print("FINAL CONVERSATION HISTORY")
    print(f"{'='*60}")
    for i, msg in enumerate(messages):
        role = msg["role"]
        content = msg["content"]

        if isinstance(content, str):
            print(f"\n[{i}] {role}: {content[:80]}")
        elif isinstance(content, list):
            # SDK response content is a list of typed objects or dicts
            types = []
            for item in content:
                if isinstance(item, dict):
                    types.append(item.get("type", "?"))
                else:
                    types.append(getattr(item, "type", "?"))
            print(f"\n[{i}] {role}: [{', '.join(types)}]")
        else:
            # ContentBlock objects from SDK response
            types = [getattr(b, "type", "?") for b in content]
            print(f"\n[{i}] {role}: [{', '.join(types)}]")


if __name__ == "__main__":
    # This prompt forces a multi-step reasoning chain:
    #   1. Model calls lookup_order to get order details (learns product_id)
    #   2. Model uses product_id from step 1 to call check_inventory
    #   3. Model synthesizes both results into a final answer
    # Without proper history appending, step 2 is impossible — the model
    # wouldn't know which product_id to look up.
    run_agent(
        "My order ORD-101 is delayed. Can you check the order and tell me "
        "when the item will be back in stock?"
    )
