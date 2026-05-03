import json

from config import client, MODEL
from prompts import EXTRACTION_SYSTEM


def extract_facts(user_message: str) -> dict:
    response = client.messages.create(
        model=MODEL,
        max_tokens=2512,
        thinking={"type": "disabled"},
        system=EXTRACTION_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )
    print(f"\nModel response {response}")
    text = next(b.text for b in response.content if b.type == "text")
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        return {}
