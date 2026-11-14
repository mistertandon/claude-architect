"""
POC 1 - Diagnose, then show, don't tell
=======================================
The same detailed extraction prompt runs three ways over 5 invoices in 3 structures (table, narrative, mixed):

    base       detailed instructions, no examples
    pairs      + 3 worked examples as input/output pairs
    few-shot   + the same 3 examples, each with the reasoning behind its extraction

First the base arm's failures are tabulated by document structure (diagnose before prescribing). Then the arms are
compared, and a decision matrix names the problems examples fix and the ones that need another technique.

Run:  python poc1_few_shot.py     (3 runs, 5 query() calls each; 3 optional repeats)
"""

import asyncio
import sys
from collections import defaultdict

from claude_agent_sdk import ClaudeSDKError

from common import Settings, load_settings
from fewshot_setup import BASE_PROMPT, DOC_TYPES, DOCUMENTS, FEWSHOT_PROMPT, FIELDS, PAIRS_PROMPT, extract, score

ARMS = [
    ("base", BASE_PROMPT),  # step 1: no examples
    ("pairs", PAIRS_PROMPT),  # the examples without their reasoning (C9)
    ("few-shot", FEWSHOT_PROMPT),  # step 3: the examples with their reasoning
    # ("base", BASE_PROMPT),  # optional: a second run of each arm shows format drift between runs (C4)
    # ("pairs", PAIRS_PROMPT),  # optional
    # ("few-shot", FEWSHOT_PROMPT),  # optional
]
STRUCTURES = ["table", "narrative", "mixed"]
TARGETS = {"table": "the table example", "narrative": "the narrative example", "mixed": "the mixed example"}


async def run_arm(settings: Settings, label: str, system_prompt: str) -> dict[str, dict | None]:
    """Extract every document with one system prompt (the examples live in it); score each document."""
    run = {}
    for doc_id in DOCUMENTS:
        data = await extract(settings, system_prompt, doc_id)
        run[doc_id] = score(doc_id, data) if data is not None else None
    return run


def cells(runs: list[dict]) -> list[tuple[str, str, str]]:
    """(doc, field, verdict) of every scored field; N2's due_date is the probe, so it is left out."""
    return [(d, f, v) for run in runs for d, s in run.items() if s for f, v in s["verdicts"].items()
            if not v.startswith("probe")]


def correct(runs: list[dict], docs: list[str] | None = None, fields: list[str] | None = None) -> tuple[int, int]:
    picked = [v for d, f, v in cells(runs) if (docs is None or d in docs) and (fields is None or f in fields)]
    return sum(v == "correct" for v in picked), len(picked)


def iso_dates(runs: list[dict]) -> tuple[int, int]:
    iso = [ok for run in runs for s in run.values() if s for ok in s["iso"]]
    return sum(iso), len(iso)


def accuracy(runs: list[dict], docs: list[str] | None = None, fields: list[str] | None = None) -> str:
    return "%d/%d" % correct(runs, docs, fields)


def main_report(scores: dict[str, list[dict]]) -> dict:
    base = scores["base"]
    failure_table = {}
    for field in FIELDS:  # the failure table: which fields fail on which structure (C5)
        row = {}
        for structure in STRUCTURES:
            docs = [d for d in DOCUMENTS if DOC_TYPES[d] == structure]
            picked = [v for d, f, v in cells(base) if f == field and d in docs]
            row[structure] = (sum(v != "correct" for v in picked), len(picked))
        failure_table[field] = row
    failing = sorted({DOC_TYPES[d] for d, f, v in cells(base) if v != "correct"}, key=STRUCTURES.index)
    diagnosis = {s: TARGETS[s] for s in failing}  # each failing structure -> the example that targets it

    comparison = {}
    for label, runs in scores.items():  # the comparison (C10, C12)
        picked = cells(runs)
        changed = None  # needs 2 runs
        if len(runs) > 1:
            changed = sum(runs[0][d]["data"].get(f) != runs[1][d]["data"].get(f) for d in DOCUMENTS for f in FIELDS
                          if runs[0][d] and runs[1][d])
        comparison[label] = {
            "empty": (sum(v == "empty" for _, _, v in picked), len(picked)), "iso_dates": iso_dates(runs),
            "accuracy": accuracy(runs), "changed_between_runs": changed,
            "by_structure": {s: accuracy(runs, [d for d in DOCUMENTS if DOC_TYPES[d] == s]) for s in STRUCTURES},
        }
    # Same instructions in every arm: only the examples changed (every prompt starts with BASE_PROMPT, C11).
    # Reasoning vs pairs on patterns no example shows (N1 line items, N2, T2 total):
    unseen_patterns = {a: (accuracy(scores[a], ["N1"], ["line_items"]), accuracy(scores[a], ["N2"]),
                           accuracy(scores[a], ["T2"], ["total_amount"])) for a in ("pairs", "few-shot")}

    def first(arm: str, doc: str) -> dict:
        return next((run[doc] for run in scores[arm] if run.get(doc)), {"verdicts": {}, "data": {}})

    shot = scores["few-shot"]
    rows = [  # the decision matrix (C13): problem, base, few-shot, fixed by examples?, technique (C14)
        ("narrative extraction", correct(base, ["N1", "N2"]), correct(shot, ["N1", "N2"])),
        ("mixed formats", correct(base, ["M1"]), correct(shot, ["M1"])),
        ("format consistency", iso_dates(base), iso_dates(shot)),  # ISO dates among the non-empty dates
    ]
    matrix = {}  # problem -> (base, few-shot, fixed by examples?, technique)
    for problem, (b_ok, b_n), (s_ok, s_n) in rows:
        fixed = "already fine" if b_ok == b_n else ("yes" if s_ok / max(s_n, 1) > b_ok / max(b_n, 1) else "no")
        matrix[problem] = ((b_ok, b_n), (s_ok, s_n), fixed, "few-shot examples")
    matrix["missing data (N2 due)"] = (  # empty or invented: the schema has no null (C15)
        first("base", "N2")["verdicts"].get("due_date"), first("few-shot", "N2")["verdicts"].get("due_date"),
        "no", "nullable schema fields (topic 03)")
    sums = [round(sum(i["quantity"] * i["unit_price"] for i in first(a, "T2")["data"].get("line_items", [])), 2)
            for a in ("base", "few-shot")]
    matrix["sum discrepancy (T2)"] = (  # line items vs stated total
        (sums[0], first("base", "T2")["data"].get("total_amount")),
        (sums[1], first("few-shot", "T2")["data"].get("total_amount")), "no", "validation and retry loop (topic 04)")
    matrix["malformed JSON"] = (  # calls without structured output
        *(sum(s is None for run in scores[a] for s in run.values()) for a in ("base", "few-shot")),
        "no", "tool use / output_format (topic 03)")
    return {"failure_table": failure_table, "diagnosis": diagnosis, "comparison": comparison,
            "unseen_patterns": unseen_patterns, "matrix": matrix}


async def main() -> int:
    try:
        settings = load_settings()
    except (OSError, RuntimeError):
        return 1

    scores = defaultdict(list)
    for label, system_prompt in ARMS:
        try:
            scores[label].append(await run_arm(settings, label, system_prompt))
        except ClaudeSDKError:  # Claude Code not found, its process crashed, ...
            return 1
    report = main_report(scores)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
