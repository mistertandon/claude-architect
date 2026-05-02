"""
COORDINATOR AGENT: Analyzes the user's query and dynamically selects which
subagents to invoke — rather than always routing through every specialist.

This is the correct multi-agent pattern. The coordinator is itself an agentic
loop whose "tools" are subagent invocations. It reasons about WHICH specialists
are needed based on the query, invokes only those, then synthesizes results.
"""

import os
import json
from urllib import response
from dotenv import load_dotenv

load_dotenv()

import anthropic
from subagents import SUBAGENT_REGISTRY, run_subagent

client = anthropic.Anthropic()

# The coordinator's tools are "delegate_to_subagent" calls.
# Each subagent appears as a tool so the coordinator can select them
# the same way any agentic loop selects tools — via model reasoning.
COORDINATOR_TOOLS = [
    {
        "name": "delegate_to_subagent",
        "description": (
            "Delegate a specific task to a specialist subagent. "
            "Available subagents:\n"
            + "\n".join(
                f"- {name}: {cfg['description']} (capabilities: {', '.join(cfg['capabilities'])})"
                for name, cfg in SUBAGENT_REGISTRY.items()
            )
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "enum": list(SUBAGENT_REGISTRY.keys()),
                    "description": "Which subagent to invoke"
                },
                "task": {
                    "type": "string",
                    "description": (
                        "The specific task to delegate. Should be a focused, "
                        "self-contained instruction — not the raw user query."
                    )
                }
            },
            "required": ["agent_name", "task"]
        }
    }
]

COORDINATOR_SYSTEM = """You are a technical coordinator agent. Your job is to:

1. ANALYZE the user's query to understand what expertise is needed
2. SELECT only the relevant subagents — do NOT invoke all of them every time
3. CRAFT a focused task for each selected subagent
4. SYNTHESIZE the results into a coherent answer

Key principles:
- If the query only needs one specialist, invoke only one.
- If the query spans multiple domains, invoke multiple subagents — but only those that are relevant.
- The task you delegate should be SPECIFIC and SELF-CONTAINED. Don't pass the raw user query — extract and reformulate what each specialist needs to know.
- After receiving subagent results, synthesize them into a unified response for the user.
"""


def run_coordinator(user_message: str):
    print(f"\n{'='*60}")
    print(f"COORDINATOR AGENT")
    print(f"{'='*60}")
    print(f"User: {user_message}")

    messages = [{"role": "user", "content": user_message}]
    iteration = 0

    # The coordinator runs its own agentic loop. Its "tool calls" are
    # subagent delegations. The model decides how many and which ones.
    while True:
        iteration += 1
        response = client.messages.create(
            model=os.getenv("MODEL_ID", "claude-sonnet-4-20250514"),
            max_tokens=2048,
            system=COORDINATOR_SYSTEM,
            tools=COORDINATOR_TOOLS,
            messages=messages,
        )
        print(f"\nModel response {response}")
        print(f"\n  [Coordinator iteration {iteration} | stop_reason: {response.stop_reason}]")

        # Print any reasoning the coordinator shares before delegating.
        for block in response.content:
            if hasattr(block, "text") and block.text.strip():
                print(f"  Coordinator thinking: {block.text[:120]}...")

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"\n{'='*60}")
                    print(f"FINAL ANSWER:")
                    print(f"{'='*60}")
                    print(block.text)
            break

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    agent_name = block.input["agent_name"]
                    task = block.input["task"]

                    print(f"\n  Coordinator delegating to [{agent_name}]:")
                    print(f"  Task: {task[:100]}...")

                    # Run the subagent's independent agentic loop.
                    # The coordinator doesn't control the subagent's tool
                    # choices — it just receives the final result.
                    subagent_result = run_subagent(agent_name, task)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        # The subagent's full output becomes the tool result.
                        # The coordinator then reasons about it alongside
                        # results from other subagents.
                        "content": subagent_result,
                    })

            messages.append({"role": "user", "content": tool_results})


if __name__ == "__main__":

    # -----------------------------------------------------------------------
    # Scenario 1: Single-domain query → coordinator should invoke ONE subagent
    # -----------------------------------------------------------------------
    print("\n" + "#"*60)
    print("# SCENARIO 1: Pure DB query — only db_analyst needed")
    print("# The coordinator should NOT invoke code_reviewer or api_designer")
    print("#"*60)
    run_coordinator(
        "This query is slow: SELECT * FROM users WHERE age > 25 ORDER BY name. "
        "The users table has 2M rows. How can I optimize it?"
    )

    # -----------------------------------------------------------------------
    # Scenario 2: Multi-domain query → coordinator selects relevant subset
    # -----------------------------------------------------------------------
    print("\n" + "#"*60)
    print("# SCENARIO 2: Code + API — needs code_reviewer AND api_designer")
    print("# The coordinator should NOT invoke db_analyst (no DB aspect)")
    print("#"*60)
    run_coordinator(
        "I'm building a user registration endpoint. Here's my handler code:\n"
        "def register(request):\n"
        "    query = f\"INSERT INTO users VALUES ('{request.name}', '{request.email}')\"\n"
        "    db.execute(query)\n"
        "    return {'status': 'ok'}\n\n"
        "Review this code for security issues and also generate a proper "
        "OpenAPI spec for a POST /users endpoint."
    )

    # -----------------------------------------------------------------------
    # Scenario 3: All three domains
    # -----------------------------------------------------------------------
    print("\n" + "#"*60)
    print("# SCENARIO 3: Full stack review — all subagents relevant")
    print("#"*60)
    run_coordinator(
        "We're launching a new /search endpoint. Review this handler:\n"
        "def search(q):\n"
        "    return db.execute(f\"SELECT * FROM products WHERE name LIKE '%{q}%'\")\n\n"
        "Also optimize the underlying SQL query (products table has 500K rows) "
        "and generate an OpenAPI spec for GET /search?q=term."
    )
