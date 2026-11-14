"""
POC 2a - Audit a system prompt for keyword conflicts   (offline: no API call, free)
===================================================================================
A system prompt is the second routing signal. A sentence that ties a trigger word ("always", "first", ...) to one
tool's vocabulary ("customer details", "order information", ...) can pull Claude to that tool even when the tool
descriptions are good. audit_prompt() flags every such sentence:

    BASE_PROMPT       0 findings: POC 1's results came from the descriptions alone
    CONFLICT_PROMPT   2 findings, both pulling toward get_customer
    FIXED_PROMPT      0 findings: each sentence rewritten with a precise condition

Run:  python poc2_prompt_audit.py
"""

import re
import sys

from routing_setup import BASE_PROMPT, CONFLICT_PROMPT, FIXED_PROMPT, REWRITES

TRIGGERS = r"\b(always|first|every|before|whenever|must)\b"
TOOL_KEYWORDS = {  # the vocabulary of each tool's minimal description
    "get_customer": r"\bcustomer (details|information|info|data|record|profile)\b",
    "lookup_order": r"\border (details|information|info|data|record)\b",
}


def audit_prompt(prompt: str) -> list[dict]:
    """One finding per sentence that holds both a trigger word and a tool's vocabulary (C12)."""
    findings = []
    for sentence in re.split(r"(?<=[.!?])\s+", prompt.strip()):  # the same rule as sentence_count()
        trigger = re.search(TRIGGERS, sentence, re.IGNORECASE)  # the first trigger is reported
        for tool_name, keywords in TOOL_KEYWORDS.items():
            phrase = re.search(keywords, sentence, re.IGNORECASE)
            if trigger and phrase:
                findings.append({"sentence": sentence, "trigger": trigger.group(0), "phrase": phrase.group(0),
                                 "tool": tool_name})
    return findings


def main() -> int:
    prompts = {"BASE_PROMPT": BASE_PROMPT, "CONFLICT_PROMPT": CONFLICT_PROMPT, "FIXED_PROMPT": FIXED_PROMPT}
    for name, prompt in prompts.items():
        findings = audit_prompt(prompt)
        print(f"\n{name}: {len(findings)} finding(s)")
        for finding in findings:  # the phrase, the tool it pulls toward, and its rewrite (C14)
            print(f"   \"{finding['trigger']}\" + \"{finding['phrase']}\" -> {finding['tool']}")
            print(f"      sentence: {finding['sentence']}")
            print(f"      rewrite:  {REWRITES.get(finding['sentence'], '(none)')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
