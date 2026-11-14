"""
POC 2a - Watch the automated side   (offline: no API call, free)
================================================================
One production day: 1,100 extractions, including 100 invoices from a new supplier, Brightline Packaging, whose
dates the model misreads with HIGH confidence (0.96). Those invoices are automated, so no reviewer ever sees them.

Two ways to keep checking quality:

    low-confidence only   check the review queue: the items that weren't automated
    stratified sample     a seeded random sample from every (document type, confidence band) stratum, the automated
                          high-confidence stratum included, in proportion to volume with a minimum per type

Only the stratified sample sees Brightline, and its error rate in the automated stratum raises a drift alert.

Run:  python poc2_sampling.py
"""

import random
import sys

from calibration_setup import (BANDS, TYPES, VALIDATION_PLAN, band_of, calibration_curve, has_error, is_automated,
                               make_extractions, production_day, raw_min, thresholds)

SAMPLE_SIZE = 50
MIN_PER_TYPE = 3
SEED = 2026  # the one random draw is seeded, so every run is the same
DRIFT_FACTOR = 2  # alert when a stratum's sampled error rate is above twice its validated rate


def strata(extractions: list[dict]) -> dict[tuple, list[dict]]:
    """Extractions keyed by (doc_type, band of the weakest field), in production order."""
    groups: dict[tuple, list[dict]] = {}
    for e in extractions:
        groups.setdefault((e["doc_type"], band_of(raw_min(e))), []).append(e)
    return groups


def allocate(groups: dict[tuple, list[dict]]) -> dict[tuple, int]:
    """Each type gets its share of the volume, but at least MIN_PER_TYPE; its strata split that by largest
    remainder, ties going to the lower band (C15)."""
    total = sum(len(items) for items in groups.values())
    allocation = {}
    for doc_type in TYPES:
        keys = [key for key in sorted(groups) if key[0] == doc_type]
        volume = sum(len(groups[key]) for key in keys)
        quota = max(MIN_PER_TYPE, round(SAMPLE_SIZE * volume / total))
        exact = {key: quota * len(groups[key]) / volume for key in keys}
        allocation.update({key: int(share) for key, share in exact.items()})
        leftover = quota - sum(allocation[key] for key in keys)
        for key in sorted(keys, key=lambda k: (-(exact[k] - int(exact[k])), k[1]))[:leftover]:
            allocation[key] += 1
    return allocation


def draw(groups: dict[tuple, list[dict]], allocation: dict[tuple, int], seed: int) -> list[dict]:
    """A random sample of each stratum, the automated ones included (C13)."""
    rng = random.Random(seed)
    sample = []
    for doc_type in TYPES:
        for band in range(len(BANDS)):
            if allocation.get((doc_type, band)):
                sample += rng.sample(groups[(doc_type, band)], allocation[(doc_type, band)])
    return sample


def stratum_error_rates(extractions: list[dict], labels: dict) -> dict[tuple, tuple[int, int]]:
    """(extractions with an error, extractions) per stratum."""
    return {key: (sum(has_error(e, labels) for e in items), len(items)) for key, items in strata(extractions).items()}


def main() -> int:
    validation, validation_labels = make_extractions(VALIDATION_PLAN, "V")
    th = thresholds(calibration_curve(validation, validation_labels))  # POC 1's thresholds, rebuilt
    day, labels = production_day()
    automated = [e for e in day if is_automated(e, th)]
    print(f"Production day: {len(day)} extractions, {len(automated)} automated, {len(day) - len(automated)} queued "
          "for human review\n")

    groups = strata(day)
    allocation = allocate(groups)
    sample = draw(groups, allocation, SEED)
    picked = {e["id"] for e in sample}
    print(f"Stratified sample (seed {SEED}): {len(sample)} extractions (C13, C15)")
    for doc_type in TYPES:
        volume = sum(len(items) for key, items in groups.items() if key[0] == doc_type)
        cells = [f"{BANDS[band][0]:.1f}-{BANDS[band][1]:.1f}: {len(groups[(doc_type, band)])} -> "
                 f"{allocation[(doc_type, band)]}" for band in range(len(BANDS)) if (doc_type, band) in groups]
        drawn = sum(e["doc_type"] == doc_type for e in sample)
        print(f"   {doc_type:<20} volume {volume:>4} ({100 * volume / len(day):4.1f}%), sample {drawn:>2} "
              f"({100 * drawn / len(sample):4.1f}%)   " + ", ".join(cells))
    top = ("standard_invoice", 4)
    print(f"   {sum(e['id'] in picked for e in groups[top])} of the {len(sample)} come from the automated stratum "
          f"(standard_invoice, 0.9-1.0), which no reviewer would otherwise see\n")

    print("Two verification plans on the same day (C14)")
    for plan, checked in (("low-confidence only", [e for e in day if not is_automated(e, th)]),
                          ("stratified sample", sample)):
        brightline = [e for e in checked if e["id"].startswith("P-BRL-")]
        print(f"   {plan:<20} checks {len(checked):>3} items: {len(brightline)} Brightline invoices, "
              f"{sum(has_error(e, labels) for e in brightline)} Brightline errors found")

    validated = stratum_error_rates(validation, validation_labels)
    print(f"\nDrift check: each sampled stratum's error rate against its validated rate (alert above "
          f"{DRIFT_FACTOR}x)")
    for key in sorted(allocation, key=lambda k: (TYPES.index(k[0]), k[1])):
        drawn = [e for e in sample if (e["doc_type"], band_of(raw_min(e))) == key]
        if not drawn:
            continue
        errors, (base_errors, base_n) = sum(has_error(e, labels) for e in drawn), validated[key]
        alert = errors / len(drawn) > DRIFT_FACTOR * base_errors / base_n
        print(f"   {key[0]:<20} {BANDS[key[1]][0]:.1f}-{BANDS[key[1]][1]:.1f}: sampled {errors}/{len(drawn)} = "
              f"{100 * errors / len(drawn):5.1f}%, validated {base_errors}/{base_n} = "
              f"{100 * base_errors / base_n:5.1f}%"
              + ("   ALERT: a new error pattern among the automated extractions" if alert else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
