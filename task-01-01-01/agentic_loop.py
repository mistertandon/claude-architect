import os
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic()

# Tools must be declared upfront so the model knows what capabilities it can invoke.
tools = [
    {
        "name": "get_weather",
        "description": "Get current weather for a given city.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name, e.g. 'San Francisco'"
                }
            },
            "required": ["city"]
        }
    }
]

MOCK_WEATHER_DATA = {
    "san francisco": {"temp_c": 15, "condition": "Foggy"},
    "new york": {"temp_c": 22, "condition": "Sunny"},
    "london": {"temp_c": 12, "condition": "Rainy"},
}


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Simulate tool execution. In production, this dispatches to real APIs."""
    if tool_name == "get_weather":
        city = tool_input["city"].lower()
        result = MOCK_WEATHER_DATA.get(city, {"temp_c": "unknown", "condition": "unknown"})
        return json.dumps(result)
    return json.dumps({"error": f"Unknown tool: {tool_name}"})


def run_agentic_loop(user_message: str):
    print(f"\n{'='*60}")
    print(f"User: {user_message}")
    print(f"{'='*60}")

    # Conversation history is the model's memory across loop iterations.
    messages = [{"role": "user", "content": user_message}]

    while True:
        response = client.messages.create(
            model=os.getenv("MODEL_ID", "claude-sonnet-4-6"),
            max_tokens=1024,
            tools=tools,
            messages=messages,
        )

        print(f"\n[stop_reason: {response.stop_reason}]")

        # stop_reason == "end_turn" means the model has finished — it has no more
        # tool calls to make and is ready to present its final answer.
        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"\nAssistant: {block.text}")
            break

        # stop_reason == "tool_use" means the model needs external data before it
        # can produce a final answer — the loop MUST continue.
        if response.stop_reason == "tool_use":
            # Append the full assistant response to preserve the model's chain of
            # thought and tool-call metadata — required by the API contract.
            messages.append({"role": "assistant", "content": response.content})

            # Collect all tool results in a single user message — the API expects
            # tool_result blocks grouped together, not sent as separate messages.
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  -> Calling tool: {block.name}({json.dumps(block.input)})")
                    result = execute_tool(block.name, block.input)
                    print(f"  <- Result: {result}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        # tool_use_id ties each result back to its call — without
                        # this the model can't match results to requests.
                        "content": result,
                    })

            messages.append({"role": "user", "content": tool_results})


if __name__ == "__main__":
    # Single-tool call: model calls get_weather once, gets result, responds.
    run_agentic_loop("What's the weather in San Francisco?")

    # Multi-tool call: model may call get_weather multiple times in one turn
    # or across multiple loop iterations to gather all data before responding.
    run_agentic_loop("Compare the weather in London and New York.")
