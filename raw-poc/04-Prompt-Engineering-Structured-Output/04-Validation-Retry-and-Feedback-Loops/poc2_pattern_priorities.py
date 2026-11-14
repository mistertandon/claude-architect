"""
POC 2 - Dismissal data sets the next prompt fix (free: no API calls)
===================================================================
POC 1's extraction records, for every line item (a "finding"), the detected_pattern that produced it. Reviewers then
keep or dismiss each finding. Over many documents, that dismissal log says which construct the prompt handles badly:

    pattern -> findings, dismissed, dismissal rate  ──►  sorted, highest rate first  ──►  refine those first

REVIEW_LOG below is a mock log of 40 findings from earlier runs, in the shape a real log would have.

Run:  python poc2_pattern_priorities.py     (no API calls)
"""

import sys

HISTORY = {  # pattern -> (findings, dismissed by reviewers)
    "table_row": (18, 1),
    "prose_sentence": (8, 3),
    "summary_row": (6, 5),
    "adjustment_row": (4, 2),
    "other": (4, 0),
}
REVIEW_LOG = [{"pattern": p, "dismissed": n < dismissed} for p, (count, dismissed) in HISTORY.items() for n in range(count)]

PRIORITY_THRESHOLD = 0.25  # above this dismissal rate, a pattern needs a prompt refinement (topic 01's 25% rule)
REFINEMENTS = {
    "summary_row": "Add an example whose reasoning says Subtotal, Tax and Shipping rows are totals, not line items.",
    "adjustment_row": "Add an example where a discount row is recorded as a negative adjustment, not a product.",
    "prose_sentence": "Add an example of a sentence that mentions an item that is not billed.",
}


def pattern_report(log: list[dict]) -> list[dict]:
    """One row per pattern: findings, dismissed, rate; highest rate first, then the most frequent."""
    rows = {}
    for entry in log:
        row = rows.setdefault(entry["pattern"], {"pattern": entry["pattern"], "findings": 0, "dismissed": 0})
        row["findings"] += 1
        row["dismissed"] += entry["dismissed"]
    for row in rows.values():
        row["rate"] = row["dismissed"] / row["findings"]
    return sorted(rows.values(), key=lambda r: (-r["rate"], -r["findings"]))


def main() -> int:
    report = pattern_report(REVIEW_LOG)
    # Prompt refinement priorities (dismissal rate above 25%), highest rate first
    priorities = [(row["pattern"], REFINEMENTS.get(row["pattern"], "add an example of it."))
                  for row in report if row["rate"] > PRIORITY_THRESHOLD]
    return 0


if __name__ == "__main__":
    sys.exit(main())
