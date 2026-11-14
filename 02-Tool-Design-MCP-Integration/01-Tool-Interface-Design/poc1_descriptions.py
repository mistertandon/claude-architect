"""
POC 1a - The anatomy of a tool description   (offline: no API call, free)
=========================================================================
Prints both versions of the two tool descriptions, sentence by sentence, and checks each for the five elements of
a production-grade description:

    purpose      the first sentence says what the tool returns
    formats      the accepted identifier formats (CUST-..., ORD-...)
    examples     quoted example queries
    edge_cases   a sentence that starts with "If "
    boundary     "Do NOT use" plus the other tool's name

Then it compares every field of the two tool versions: only the description strings differ, so POC 1b's change in
selection accuracy can only come from them.

Run:  python poc1_descriptions.py
"""

import re
import sys

from routing_setup import DESCRIPTIONS, compare_versions, sentence_count


def check_description(name: str, text: str) -> dict[str, bool]:
    """The five elements, each True or False (C7)."""
    other = "lookup_order" if name == "get_customer" else "get_customer"
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())  # the same rule as sentence_count()
    return {
        "purpose": "returns" in sentences[0],
        "formats": re.search(r"\b(CUST|ORD)-", text) is not None,
        "examples": re.search(r'"[^"]+"', text) is not None,
        "edge_cases": any(sentence.startswith("If ") for sentence in sentences),
        "boundary": any("Do NOT use" in sentence and other in sentence for sentence in sentences),
    }


def main() -> int:
    for version, tools in DESCRIPTIONS.items():
        for name, text in tools.items():
            elements = check_description(name, text)
            print(f"\n{version} {name}: {sentence_count(text)} sentence(s); "
                  + ", ".join(f"{element} {'✅' if ok else '❌'}" for element, ok in elements.items()))
            for n, sentence in enumerate(re.split(r"(?<=[.!?])\s+", text.strip()), 1):
                print(f"   {n}. {sentence}")
    print(f"\nFields that differ between the minimal and the improved tools: {compare_versions()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
