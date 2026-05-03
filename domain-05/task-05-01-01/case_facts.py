"""
Persistent Case Facts — POC
=============================

Demonstrates extracting transactional facts (amounts, dates, order numbers,
statuses) into a structured block that lives in the system prompt — OUTSIDE
the conversation history that gets summarized/compacted.

Problem: when a long customer-support conversation is summarized, the
summary might say "the customer mentioned an order issue" instead of
preserving the exact order number #ORD-9821, amount $149.99, and date
2025-01-15.  If the model later references "your order" without the
precise ID, trust collapses and downstream tool calls use wrong values.

Solution: after each user turn, extract any new transactional facts into
a structured "case facts" dict.  Inject this dict into the SYSTEM prompt
on every API call.  The system prompt is never summarized — facts survive
compaction intact.
"""

import json
from pathlib import Path

from config import client, MODEL
from data import create_initial_case_facts, SIMULATED_CONVERSATION
from extraction import extract_facts
from merge import merge_facts
from prompt_builder import build_system_prompt


def run_conversation() -> None:

    print("Persistent Case Facts — Conversation Demo")

    case_facts = create_initial_case_facts()
    conversation_history: list[dict] = []

    for turn in SIMULATED_CONVERSATION:
        turn_num = turn["turn"]
        user_msg = turn["user"]

        print(f"Turn {turn_num}")
        print(f"\n  Customer: {user_msg}...")

        new_facts = extract_facts(user_msg)
        print(f"\n  [Extracted facts]", new_facts)

        print(f"\n  Existing case facts", case_facts)
        case_facts = merge_facts(case_facts, new_facts)
        print(f"\n  [Merged facts]", case_facts)

        system = build_system_prompt(case_facts)

        print(f"\n  [Case facts block in system prompt]")
        print(f"    Orders:   {len(case_facts['orders'])}")
        print(f"    Payments: {len(case_facts['payments'])}")
        print(f"    Customer: {case_facts['customer'].get('name', '—')}")

        conversation_history.append({"role": "user", "content": user_msg})

        response = client.messages.create(
            model=MODEL,
            max_tokens=2512,
            thinking={"type": "disabled"},
            system=system,
            messages=conversation_history,
        )
        print(f"\nModel response {response}")
        assistant_msg = next(
            b.text for b in response.content if b.type == "text"
        )

        print(f"\n  Agent: {assistant_msg}")
        conversation_history.append({
            "role": "assistant",
            "content": assistant_msg,
        })

    print(f"\n Conversation history {conversation_history}")

    print(f"\n{'=' * 60}")
    print("Final Case Facts (survives any conversation compaction)")
    print(f"{'=' * 60}")
    print(json.dumps(case_facts, indent=2))

    print(f"\n{'=' * 60}")
    print("Why This Matters")
    print(f"{'=' * 60}")
    print("""
  If the conversation history were compacted/summarized after turn 2,
  a summary might read:

    "Customer Jane contacted about a missing keyboard order and
     confirmed payment was made."

  LOST:  order #ORD-9821, $149.99, Jan 15, PAY-4410, credit card.

  With case facts in the system prompt, those exact values persist
  verbatim — the model can NEVER hallucinate "$150" or "ORD-9812"
  because the authoritative data is in the system prompt on every turn.
""")

    out = Path(__file__).parent / "output.json"
    out.write_text(json.dumps({
        "case_facts": case_facts,
        "system_prompt": build_system_prompt(case_facts),
        "turns_processed": len(SIMULATED_CONVERSATION),
    }, indent=2))
    print(f"Full results → {out}")


def main() -> None:
    run_conversation()


if __name__ == "__main__":
    main()
