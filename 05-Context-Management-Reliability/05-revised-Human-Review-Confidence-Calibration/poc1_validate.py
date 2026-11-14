"""
POC 1 - Validate before you automate   (offline: no API call, free)
====================================================================
1,000 labelled mock extractions: 4 document types x 3 fields, every field with its own confidence. In order:

    1. confidence profile    each type's scores: standard invoices high, international documents lowest
    2. accuracy table        types as rows, fields as columns: the aggregate looks excellent and hides the worst segment
    3. calibration curves    accuracy per confidence band, per type and field: the same score means different things
    4. lookup table          (type, field, raw confidence) -> the accuracy that score really predicts
    5. thresholds            per type and field: only standard invoices earn automation at 95%

Run:  python poc1_validate.py
"""

import sys

from calibration_setup import (BANDS, FIELDS, TARGET_ACCURACY, TYPES, VALIDATION_PLAN, band_of, build_lookup,
                               calibration_curve, expected_accuracy, make_extractions, thresholds)


def accuracy_table(extractions: list[dict], labels: dict) -> dict[str, dict[str, float]]:
    """Per document type, each field's accuracy and an all-fields value, plus an aggregate row (C5)."""
    groups = {doc_type: [e for e in extractions if e["doc_type"] == doc_type] for doc_type in TYPES}
    groups["aggregate"] = extractions
    table = {}
    for name, items in groups.items():
        row = {f: sum(e["fields"][f]["value"] == labels[e["id"]][f] for e in items) / len(items) for f in FIELDS}
        row["all fields"] = sum(row.values()) / len(FIELDS)
        table[name] = row
    return table


def print_accuracy_table(table: dict[str, dict[str, float]]) -> None:
    """Types as rows, fields as columns, and the aggregate at the bottom: the one number a dashboard shows (C8)."""
    print(f"   {'':<20}" + "".join(f"{column:>13}" for column in FIELDS + ["all fields"]))
    for name, row in table.items():
        print(f"   {name:<20}" + "".join(f"{100 * value:>12.1f}%" for value in row.values()))


def band_name(band: int) -> str:
    return f"{BANDS[band][0]:.1f}-{BANDS[band][1]:.1f}"


def main() -> int:
    extractions, labels = make_extractions(VALIDATION_PLAN, "V")  # the labelled validation set (C1, C4)

    print("1. Confidence profile per document type (share of field scores per band, and the mean) (C3)")
    for doc_type in TYPES:
        scores = [e["fields"][f]["confidence"] for e in extractions if e["doc_type"] == doc_type for f in FIELDS]
        shares = [sum(band_of(score) == band for score in scores) / len(scores) for band in range(len(BANDS))]
        print(f"   {doc_type:<20} " + "  ".join(f"{band_name(b)}: {100 * s:4.1f}%" for b, s in enumerate(shares))
              + f"   mean {sum(scores) / len(scores):.3f}")

    print("\n2. Accuracy by document type and field (C5, C7, C8)")
    table = accuracy_table(extractions, labels)
    print_accuracy_table(table)
    worst = min(((t, f) for t in TYPES for f in FIELDS), key=lambda segment: table[segment[0]][segment[1]])
    print(f"   The aggregate says {100 * table['aggregate']['all fields']:.1f}%; the worst segment, {worst[0]} "
          f"{worst[1]}, is at {100 * table[worst[0]][worst[1]]:.1f}%")
    volume = {t: sum(e["doc_type"] == t for e in extractions) for t in TYPES}
    others = [e for e in extractions if e["doc_type"] != "standard_invoice"]
    correct_others = sum(e["fields"][f]["value"] == labels[e["id"]][f] for e in others for f in FIELDS)
    correct_all = sum(e["fields"][f]["value"] == labels[e["id"]][f] for e in extractions for f in FIELDS)
    print(f"   Volume shares: " + ", ".join(f"{t} {100 * n / len(extractions):.1f}%" for t, n in volume.items()))
    invoice_share = (correct_all - correct_others) / correct_all
    print(f"   Everything except standard invoices: {correct_others}/{3 * len(others)} = "
          f"{100 * correct_others / (3 * len(others)):.1f}%, yet {correct_all - correct_others} of the aggregate's "
          f"{correct_all} correct fields ({100 * invoice_share:.1f}%) are standard-invoice fields: validate every "
          "segment before automating any (C6)")

    print("\n3. Calibration curves: actual accuracy per confidence band (C10, C11)")
    curve = calibration_curve(extractions, labels)
    for doc_type in TYPES:
        for field in FIELDS:
            cells = [curve.get((doc_type, field, band)) for band in range(len(BANDS))]
            print(f"   {doc_type:<20} {field:<12}" + "".join(
                f"{band_name(b)}: {100 * c[1] / c[0]:5.1f}%  " if c else f"{band_name(b)}:     –   "
                for b, c in enumerate(cells)))
    print("   One band, many meanings: date at 0.8-0.9 is " + ", ".join(
        f"{100 * curve[(t, 'date', 3)][1] / curve[(t, 'date', 3)][0]:.1f}% on {t}" for t in TYPES))
    print("   scanned_pdf at 0.9-1.0: " + ", ".join(
        f"{f} {curve[('scanned_pdf', f, 4)][1]}/{curve[('scanned_pdf', f, 4)][0]} = "
        f"{100 * curve[('scanned_pdf', f, 4)][1] / curve[('scanned_pdf', f, 4)][0]:.1f}%" for f in FIELDS))

    print("\n4. The lookup table: a raw score in, the expected accuracy out (C12)")
    lookup = build_lookup(curve)
    for doc_type, field, confidence in (("international", "date", 0.85), ("standard_invoice", "date", 0.75),
                                        ("scanned_pdf", "amount", 0.93), ("international", "date", 0.95)):
        accuracy = expected_accuracy(lookup, doc_type, field, confidence)
        print(f"   {doc_type}, {field}, {confidence} -> "
              + (f"{accuracy:.3f}" if accuracy is not None else "None (never seen: uncalibrated, never automated)"))

    print(f"\n5. Automation thresholds at {100 * TARGET_ACCURACY:.0f}% calibrated accuracy (C9)")
    for (doc_type, field), threshold in thresholds(curve).items():
        print(f"   {doc_type:<20} {field:<12} {threshold if threshold is not None else 'None: always human review'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
