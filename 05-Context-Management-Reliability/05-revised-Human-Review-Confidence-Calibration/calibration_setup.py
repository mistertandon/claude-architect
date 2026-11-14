"""
calibration_setup.py - a deterministic mock extraction system (no model call), its labelled validation set and one
production day, and the calibration functions both POCs share: calibration curves, the lookup table, thresholds.

In a real pipeline, the extractor is a query() with output_format that returns each field's value and confidence,
in exactly this shape: {field: {"value", "confidence"}}. Everything here sits downstream of that call: measuring,
calibrating, sampling and routing are plain Python, and they wouldn't change if the scores came from Claude.
"""

TYPES = ["standard_invoice", "handwritten_receipt", "scanned_pdf", "international"]
CODES = {"standard_invoice": "INV", "handwritten_receipt": "RCT", "scanned_pdf": "SCN", "international": "INT"}
FIELDS = ["vendor_name", "date", "amount"]
BANDS = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0)]
TARGET_ACCURACY = 0.95  # a field is automated only where its calibrated accuracy reaches this (C9)

VALIDATION_PLAN = {  # per type and field: (wrong, total) in each band, 0.5-0.6 ... 0.9-1.0 (C1, C3)
    "standard_invoice": {"vendor_name": [(0, 0), (0, 0), (0, 5), (2, 35), (6, 760)],
                         "date": [(0, 0), (0, 0), (1, 10), (3, 50), (12, 740)],
                         "amount": [(0, 0), (0, 0), (2, 15), (6, 60), (16, 725)]},
    "handwritten_receipt": {"vendor_name": [(2, 4), (6, 16), (10, 34), (6, 26), (0, 0)],
                            "date": [(3, 5), (9, 18), (12, 33), (8, 24), (0, 0)],
                            "amount": [(4, 6), (10, 20), (16, 32), (10, 22), (0, 0)]},
    "scanned_pdf": {"vendor_name": [(0, 0), (0, 0), (2, 10), (3, 30), (2, 30)],
                    "date": [(0, 0), (0, 0), (3, 13), (4, 40), (1, 17)],
                    "amount": [(0, 0), (0, 0), (5, 13), (6, 40), (3, 17)]},
    "international": {"vendor_name": [(4, 10), (5, 16), (3, 12), (3, 12), (0, 0)],
                      "date": [(8, 10), (9, 16), (7, 12), (6, 12), (0, 0)],
                      "amount": [(6, 10), (5, 16), (5, 12), (4, 12), (0, 0)]},
}


def band_of(confidence: float) -> int:
    """0.5-0.6 -> 0 ... 0.9-1.0 -> 4. Rounding first keeps a score of exactly 0.9 in band 4."""
    return min(4, int(round(confidence * 10, 6)) - 5)


def make_extractions(plan: dict, prefix: str) -> tuple[list[dict], dict]:
    """The mock extractor: every field is {"value", "confidence"}, and labels hold each field's truth (C1, C4)."""
    extractions, labels = [], {}
    for doc_type in TYPES:
        columns = {}
        for field in FIELDS:  # one column per field: (confidence, correct), in rising confidence
            column = []
            for (low, _), (wrong, total) in zip(BANDS, plan[doc_type][field]):
                for j in range(total):
                    confidence = round(low + (j + 0.5) * 0.1 / total, 3)
                    correct = (j + 1) * wrong // total == j * wrong // total  # wrong items spread evenly in the band
                    column.append((confidence, correct))
            columns[field] = column
        for k in range(len(columns["vendor_name"])):  # document k takes item k of every column
            doc_id = f"{prefix}-{CODES[doc_type]}-{k:04d}"
            labels[doc_id] = {f: f"{f}-{k}" for f in FIELDS}
            extractions.append({"id": doc_id, "doc_type": doc_type, "fields": {
                f: {"value": f"{f}-{k}" if columns[f][k][1] else f"{f}-{k}-misread", "confidence": columns[f][k][0]}
                for f in FIELDS}})
    return extractions, labels


def make_drift() -> tuple[list[dict], dict]:
    """100 standard invoices from a new supplier, Brightline Packaging. It prints dates as 04.11.2026, which the
    model misreads with HIGH confidence: a novel error pattern the validation set never saw (C14)."""
    extractions, labels = [], {}
    for k in range(100):
        doc_id = f"P-BRL-{k:04d}"
        labels[doc_id] = {f: f"{f}-B{k}" for f in FIELDS}
        extractions.append({"id": doc_id, "doc_type": "standard_invoice", "fields": {
            "vendor_name": {"value": f"vendor_name-B{k}", "confidence": 0.97},
            "date": {"value": f"date-B{k}-misread", "confidence": 0.96},
            "amount": {"value": f"amount-B{k}", "confidence": 0.97}}})
    return extractions, labels


def production_day() -> tuple[list[dict], dict]:
    """1,100 extractions: the validated distribution, plus one novel error pattern."""
    extractions, labels = make_extractions(VALIDATION_PLAN, "P")
    drift, drift_labels = make_drift()
    return extractions + drift, {**labels, **drift_labels}


# ---------------------------------------------------------------- calibration: shared by both POCs

def calibration_curve(extractions: list[dict], labels: dict) -> dict[tuple, tuple[int, int]]:
    """(n, correct) per (doc_type, field, band): what each reported confidence band really delivers (C11)."""
    curve: dict[tuple, tuple[int, int]] = {}
    for e in extractions:
        for f in FIELDS:
            key = (e["doc_type"], f, band_of(e["fields"][f]["confidence"]))
            n, correct = curve.get(key, (0, 0))
            curve[key] = (n + 1, correct + (e["fields"][f]["value"] == labels[e["id"]][f]))
    return curve


def build_lookup(curve: dict) -> dict[tuple, float]:
    """The calibration output: (doc_type, field, band) -> the accuracy that band really has (C12)."""
    return {key: correct / n for key, (n, correct) in curve.items() if n}


def expected_accuracy(lookup: dict, doc_type: str, field: str, confidence: float) -> float | None:
    """A raw score, translated into expected accuracy. None: the validation set never saw this band, so the score
    is uncalibrated and nothing may be automated on it."""
    return lookup.get((doc_type, field, band_of(confidence)))


def thresholds(curve: dict, target: float = TARGET_ACCURACY) -> dict[tuple, float | None]:
    """Per (doc_type, field): the lower edge of the lowest band from which every non-empty band upward reaches the
    target, or None when even the top band misses it: that field is never automated (C9)."""
    result = {}
    for doc_type in TYPES:
        for field in FIELDS:
            threshold = None
            for band in reversed(range(len(BANDS))):  # walk down from 0.9-1.0 while the bands keep passing
                n, correct = curve.get((doc_type, field, band), (0, 0))
                if not n:
                    continue
                if correct / n < target:
                    break
                threshold = BANDS[band][0]
            result[(doc_type, field)] = threshold
    return result


def is_automated(e: dict, th: dict) -> bool:
    """Every field at or above its segment's threshold, and never on a segment without one."""
    return all(th[(e["doc_type"], f)] is not None and e["fields"][f]["confidence"] >= th[(e["doc_type"], f)]
               for f in FIELDS)


def has_error(e: dict, labels: dict) -> bool:
    return any(e["fields"][f]["value"] != labels[e["id"]][f] for f in FIELDS)


def raw_min(e: dict) -> float:
    """The weakest field's raw confidence."""
    return min(e["fields"][f]["confidence"] for f in FIELDS)


def calibrated_min(e: dict, lookup: dict) -> float:
    """The weakest field's calibrated accuracy. An uncalibrated band counts as 0.0: the least trustworthy."""
    return min(expected_accuracy(lookup, e["doc_type"], f, e["fields"][f]["confidence"]) or 0.0 for f in FIELDS)
