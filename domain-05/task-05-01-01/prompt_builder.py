import json

from prompts import BASE_SYSTEM


def build_system_prompt(facts: dict) -> str:
    facts_block = json.dumps(facts, indent=2)
    return (
        f"{BASE_SYSTEM}\n\n"
        f"## CASE FACTS (authoritative — do not contradict)\n"
        f"```json\n{facts_block}\n```\n\n"
        f"When answering, cite specific values from CASE FACTS. "
        f"If a fact is not in CASE FACTS, say you don't have that information."
    )
