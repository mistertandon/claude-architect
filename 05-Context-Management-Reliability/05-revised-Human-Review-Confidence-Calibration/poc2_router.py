"""
POC 2b - Review the uncertain side first   (offline: no API call, free)
=======================================================================
The 275 extractions that weren't automated arrive for review in 5 waves of 55. After each wave, reviewers A and B
take turns on 20 items, so only 100 of the 275 get reviewed. Who gets reviewed is decided by a priority queue that
re-orders itself as items arrive, under three policies:

    fifo         arrival order: what most review tools do
    raw          the weakest field's RAW confidence, lowest first
    calibrated   the weakest field's CALIBRATED accuracy (POC 1's lookup), lowest first

A raw 0.80 on an international document is less reliable than a raw 0.70 on a standard invoice, and only the
calibrated policy knows it.

Run:  python poc2_router.py
"""

import heapq
import sys

from calibration_setup import (TYPES, VALIDATION_PLAN, band_of, build_lookup, calibrated_min, calibration_curve,
                               has_error, is_automated, make_extractions, production_day, raw_min, thresholds)

WAVES = 5
REVIEWS_PER_WAVE = 20  # reviewers A and B, 10 each


class ReviewQueue:
    """A priority queue (heapq): the most uncertain item first, re-ordered by every arrival (C16)."""

    def __init__(self, priority):
        self.priority = priority  # item -> a sort key; lower = more uncertain = reviewed sooner
        self.heap: list[tuple] = []

    def add(self, items: list[tuple[int, dict]]) -> None:
        for arrival, item in items:
            heapq.heappush(self.heap, (self.priority(item), arrival, item["id"], item))

    def next_item(self) -> tuple[int, dict]:
        _, arrival, _, item = heapq.heappop(self.heap)
        return arrival, item

    def head(self) -> str:
        return self.heap[0][2] if self.heap else "-"


def arrival_order(items: list[dict]) -> list[dict]:
    """Within each type, the item at position j of m arrives at ((j * 37) % m + 0.5) / m of the day: shuffled and
    spread through the day (37 shares no factor with 75, 80, 70 or 50)."""
    timed = []
    for type_order, doc_type in enumerate(TYPES):
        of_type = sorted((e for e in items if e["doc_type"] == doc_type), key=lambda e: e["id"])
        timed += [(((j * 37) % len(of_type) + 0.5) / len(of_type), type_order, j, e) for j, e in enumerate(of_type)]
    return [e for *_, e in sorted(timed, key=lambda entry: entry[:3])]


def simulate(policy: str, queued: list[dict], labels: dict, lookup: dict, verbose: bool = False) -> list[dict]:
    """Serve 100 of the queued items under one policy; returns the items served, in order."""
    priority = {"fifo": lambda e: (), "raw": lambda e: (raw_min(e),),
                "calibrated": lambda e: (calibrated_min(e, lookup), raw_min(e))}[policy]  # (C18)
    arrivals = list(enumerate(arrival_order(queued)))
    queue, served, not_oldest = ReviewQueue(priority), [], 0
    wave_size = len(arrivals) // WAVES
    for wave in range(WAVES):
        before = queue.head()
        queue.add(arrivals[wave * wave_size:(wave + 1) * wave_size])  # new extractions arrive: the order is rebuilt
        if verbose:
            print(f"   wave {wave + 1}: queue head {before} -> {queue.head()}")
        for turn in range(REVIEWS_PER_WAVE):
            oldest = min(arrival for _, arrival, _, _ in queue.heap)
            arrival, item = queue.next_item()
            not_oldest += arrival != oldest
            served.append(item)
            if verbose and len(served) <= 6:
                print(f"      reviewer {'AB'[turn % 2]} gets {item['id']} "
                      f"(calibrated {calibrated_min(item, lookup):.3f}, raw {raw_min(item):.3f})")
    if verbose:
        print(f"   {not_oldest} of the {len(served)} items served were not the oldest one waiting")
    return served


def main() -> int:
    validation, validation_labels = make_extractions(VALIDATION_PLAN, "V")
    curve = calibration_curve(validation, validation_labels)
    lookup, th = build_lookup(curve), thresholds(curve)  # POC 1's lookup and thresholds, rebuilt
    day, labels = production_day()
    queued = [e for e in day if not is_automated(e, th)]
    errors = sum(has_error(e, labels) for e in queued)
    print(f"Review queue: {len(queued)} extractions with {errors} errors; "
          f"capacity {WAVES * REVIEWS_PER_WAVE} reviews\n")

    print("Raw against calibrated confidence (C18)")
    for doc_type, band in (("international", 3), ("standard_invoice", 2)):
        group = [e for e in queued if e["doc_type"] == doc_type and band_of(raw_min(e)) == band]
        values = sorted({round(calibrated_min(e, lookup), 3) for e in group})
        print(f"   {doc_type:<17} weakest raw score in {band / 10 + 0.5:.1f}-{band / 10 + 0.6:.1f}: {len(group)} "
              f"documents, calibrated {values}, {sum(has_error(e, labels) for e in group)} with an error")

    print("\nThe calibrated queue, wave by wave (C16)")
    results = {"calibrated": simulate("calibrated", queued, labels, lookup, verbose=True)}
    results.update({policy: simulate(policy, queued, labels, lookup) for policy in ("fifo", "raw")})

    print("\nErrors caught with capacity for 100 reviews (C16, C17, C18)")
    for policy in ("fifo", "raw", "calibrated"):
        served = results[policy]
        per_type = " / ".join(str(sum(e["doc_type"] == doc_type for e in served)) for doc_type in TYPES)
        print(f"   {policy:<11} {sum(has_error(e, labels) for e in served):>3} of {errors}   served per type "
              f"(invoices / receipts / scanned / international): {per_type}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
