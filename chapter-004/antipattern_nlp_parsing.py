"""
ANTI-PATTERN #1: Parsing natural language to detect loop termination.

This approach scans the model's TEXT output for phrases like "here is",
"I hope this helps", "in summary" to guess if the model is "done".

Why this is wrong:
- The model's text is for the USER, not for the orchestrator to parse.
- These phrases can appear mid-conversation (e.g., "Here is what I found
  so far, let me also check...") triggering premature termination.
- Different models, temperatures, and system prompts produce different
  phrasing — the heuristic is inherently brittle.
- stop_reason already provides this signal reliably; parsing text
  duplicates it badly.
"""

import os
import json
import anthropic
from tools import TOOLS, execute_tool

client = anthropic.Anthropic()

# Fragile heuristic: phrases that "probably" mean the model is done.
COMPLETION_PHRASES = [
    "here is", "here's your", "in summary", "to summarize",
    "i hope this helps", "let me know if", "is there anything else",
    "based on the information",
]


def looks_like_final_answer(response) -> bool:
    """Scan text blocks for completion-sounding phrases."""
    for block in response.content:
        if hasattr(block, "text"):
            lower = block.text.lower()
            for phrase in COMPLETION_PHRASES:
                if phrase in lower:
                    return True
    return False


def run_nlp_parsing(user_message: str):
    print(f"\n{'='*60}")
    print(f"ANTI-PATTERN: NLP-based termination")
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

        # BUG: Checking text content BEFORE checking stop_reason.
        # The model might say "Here is what I found so far" and THEN
        # call a tool in the same response. This exits prematurely.
        if looks_like_final_answer(response):
            print(f"  >>> NLP heuristic triggered — exiting loop <<<")
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"\nAssistant: {block.text}")
            # PROBLEM: We may be ignoring tool_use blocks in this same
            # response. The model wanted to call a tool, but we're
            # bailing out because we saw a "completion phrase" in the
            # accompanying text.
            break

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

        elif response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"\nAssistant: {block.text}")
            break

    print(f"  Total iterations: {iteration}")


if __name__ == "__main__":
    print("\n" + "#"*60)
    print("# Risk: model says 'Here is your balance...' while also calling")
    print("# a tool → NLP check fires first → remaining tools never execute")
    print("#"*60)
    run_nlp_parsing(
        "Check my balance on ACC-001, show recent transactions, "
        "then transfer $100 to ACC-002."
    )
