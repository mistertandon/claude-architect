"""
POC 1 - When to batch, and when to submit (free: no API calls)
=============================================================
Two decisions you make before any batch exists:

    1. the matching rule: does someone or something wait for the result, and is the deadline longer than the
       24-hour batch window? Only then may a workflow use the batch API (50% cheaper).
    2. the submission cadence: work backwards from the SLA with the 24-hour MAXIMUM, never the typical hour.

Run:  python poc1_batch_planning.py     (no API calls)
"""

import math
import sys

BATCH_WINDOW_HOURS = 24  # a batch may take up to 24 hours; one that isn't done by then expires
SLA_HOURS = 30
SAFETY_MARGIN_HOURS = 2

WORKFLOWS = [  # who or what waits for the result, and the deadline in hours
    {"name": "Pre-merge review of a pull request", "waiting": "a developer and the CI pipeline", "sla_hours": 0.25},
    {"name": "Reply drafts for live-chat agents", "waiting": "a customer in the chat", "sla_hours": 0.01},
    {"name": "Stock-reorder suggestions for the 06:00 order run", "waiting": None, "sla_hours": 8},
    {"name": "Supplier-invoice extraction for the accounts-payable run", "waiting": None, "sla_hours": 30},
    {"name": "Weekly product-review sentiment report", "waiting": None, "sla_hours": 168},
]


def categorize(workflow: dict) -> tuple[str, str]:
    """The matching rule (C1, C3): batch only when nothing waits AND the deadline outlasts the 24-hour window."""
    if workflow["waiting"]:
        return "synchronous", f"{workflow['waiting']} waits for the result"
    if workflow["sla_hours"] <= BATCH_WINDOW_HOURS:
        return "synchronous", f"its {workflow['sla_hours']:g}-hour SLA is shorter than the 24-hour batch window"
    return "batch", f"results are used later; its {workflow['sla_hours']:g}-hour SLA outlasts the 24-hour window"


def all_batch_check(workflows: list[dict]) -> None:
    """The exam's manager: 'put everything on the batch API, it's half the price' (C2)."""
    print("\nThe 'batch everything' plan would break:")
    for w in workflows:
        category, reason = categorize(w)
        if category == "synchronous":
            print(f"  - {w['name']}: {reason}")
    print("Batch only latency-tolerant work: the 50% saving never justifies a missed real-time dependency")


def submission_plan(sla_hours: float, cadences: tuple[int, ...] = (4, 6, 8)) -> None:
    """Work backwards from the deadline with the 24-hour maximum (C8, C9)."""
    print(f"\nSLA {sla_hours:g} h - batch window {BATCH_WINDOW_HOURS} h = {sla_hours - BATCH_WINDOW_HOURS:g} h of buffer")
    print(f"Latest safe submission: {BATCH_WINDOW_HOURS} h before the deadline, i.e. at most "
          f"{sla_hours - BATCH_WINDOW_HOURS:g} h after a document arrives")
    chosen = None
    for cadence in cadences:
        worst = cadence + BATCH_WINDOW_HOURS  # arrives just after a submission: waits a full cadence, then 24 h
        margin = sla_hours - worst
        ok = margin >= SAFETY_MARGIN_HOURS
        chosen = chosen or (cadence if ok else None)
        print(f"  every {cadence} h: worst case {worst} h, margin {margin:+g} h -> {'OK' if ok else 'not safe'}")
    print(f"Chosen: submit every {chosen} h, so a fresh batch is always in flight "
          f"(up to {math.ceil(BATCH_WINDOW_HOURS / chosen)} batches at once)")
    print("Plan for the 24-hour maximum, not the typical hour")


def main() -> int:
    print("Workflow categories:")
    for w in WORKFLOWS:
        category, reason = categorize(w)
        print(f"  {category:<11} {w['name']}: {reason}")
    all_batch_check(WORKFLOWS)
    submission_plan(SLA_HOURS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
