"""
POC 1 - Confidence routing, checked by an independent instance
==============================================================
06's multi-pass review (one fresh session per file, then one integration pass) now scores every finding:

    review    each finding gets confidence 0.0-1.0 and a reason; a threshold routes it to the developer
              (direct_report) or to a human queue (human_review); the answer key shows how well the raw scores
              are calibrated
    verify    the findings are judged twice:
                self-review   resume=<the reviewer's session>: it sees its own reasoning ("I chose this because")
                independent   a NEW session: only the code and the findings, no scores, no reasons
              the independent verdicts become the calibration dataset, and they move the threshold

Besides model I/O, the log shows each finding's route, the calibration tables, the self vs independent comparison,
the overturned findings and the old and new threshold.

Run:  python poc1_confidence_routing.py     (2 runs: 3 per-file + 1 integration call, then 3 + 3 verify calls)
"""

import asyncio
import json
import sys

from claude_agent_sdk import ClaudeSDKError

from common import load_settings, log, setup_logging
from confidence_setup import (
    FILE_REVIEW_SCHEMA,
    INTEGRATION_SCHEMA,
    ROUTE_THRESHOLD,
    SUBSET,
    TARGET_PRECISION,
    VERIFIER_PROMPT,
    VERIFY_SCHEMA,
    build_review_options,
    format_file,
    label,
    load_repo,
    run_review,
)

FILE_PROMPT = "Review this one file from a {n}-file codebase. You can see only this file.\n\n{listing}"  # from 06
INTEGRATION_PROMPT = (  # 06's integration prompt, now with the per-file findings and the contradiction check (C6)
    "These are the per-file summaries and findings of one TypeScript codebase; the code itself is not included. Find "
    "cross-file issues only: data flow problems between modules, inconsistent API usage (a caller's assumptions that "
    "contradict the callee's contract), and patterns or conventions used differently across files. Name every file "
    "each issue involves. Also list contradictions: places where the per-file findings judge the same code pattern "
    "differently.\n\n")
SELF_CHECK_PROMPT = ("Re-check each issue you reported in this file: is it a real defect? Answer confirmed or rejected "
                     "for each, with a confidence (0.0 to 1.0) and a one-sentence reason. Issue ids: {ids}")
BUCKETS = [(0.0, 0.5), (0.5, 0.8), (0.8, 0.9), (0.9, 1.01)]

RUNS = ["review", "verify"]


def route(item: dict, threshold: float = ROUTE_THRESHOLD) -> str:
    """Clear-cut findings go straight to the developer; uncertain ones to a human (C10)."""
    return "direct_report" if item["confidence"] >= threshold else "human_review"


def calibration_table(rows: list[dict], key: str) -> None:
    for low, high in BUCKETS:
        picked = [r for r in rows if low <= r["confidence"] < high]
        hits = sum(r[key] in ("correct", "confirmed") for r in picked)
        log.info("calibration %-11s confidence %.1f-%.1f: %d finding(s), %d %s", key, low, min(high, 1.0), len(picked),
                 hits, "correct" if key == "label" else "confirmed")


def adjust_threshold(rows: list[dict]) -> float:
    """The lowest threshold whose findings the independent instance confirmed at TARGET_PRECISION or better (C15)."""
    for t in (0.5, 0.8, 0.9):
        above = [r for r in rows if r["confidence"] >= t]
        if above and sum(r["independent"] == "confirmed" for r in above) / len(above) >= TARGET_PRECISION:
            return t
    return 1.01  # nothing is trustworthy enough: everything goes to human review


async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc1_confidence_routing")
        files = load_repo()
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    findings, sessions = [], {}
    try:
        for run in RUNS:
            if run == "review":
                reviews = {}
                for f in files:  # layer 1: one NEW session per file (06 C5), now with scores
                    out = await run_review(FILE_PROMPT.format(n=len(files), listing=format_file(f)),
                                           build_review_options(settings, FILE_REVIEW_SCHEMA))
                    if out["output"] is None:
                        log.error("no review for %s", f["name"])
                        return 1
                    reviews[f["name"]], sessions[f["name"]] = out["output"], out["session_id"]
                    for n, issue in enumerate(out["output"]["issues"], 1):
                        findings.append({**issue, "id": f"{f['name']}#{n}", "file": f["name"]})
                summaries = [{"file": name, "exports": r["exports"], "uses": r["uses"],
                              "findings": [{k: i[k] for k in ("line", "severity", "description", "confidence")}
                                           for i in r["issues"]]} for name, r in reviews.items()]
                out = await run_review(INTEGRATION_PROMPT + json.dumps(summaries, indent=2),
                                       build_review_options(settings, INTEGRATION_SCHEMA))  # layer 2
                if out["output"] is None:
                    log.error("no integration review")
                    return 1
                for n, issue in enumerate(out["output"]["cross_file_issues"], 1):
                    findings.append({**issue, "id": f"X#{n}"})
                log.info("contradictions between per-file findings: %s", out["output"]["contradictions"] or "none")

                for item in findings:  # range check in Python, then the route (C9, C10)
                    item["label"] = label(item, files)
                    flag = "" if 0.0 <= item["confidence"] <= 1.0 else "  OUT OF RANGE"
                    log.info("route %-14s confidence %.2f -> %-13s (%s)%s", item["id"], item["confidence"], route(item),
                             item["confidence_reason"], flag)
                queue = sorted((i for i in findings if route(i) == "human_review"), key=lambda i: i["confidence"])
                log.info("queues: %d direct_report, %d human_review (least certain first: %s)",  # (C11)
                         len(findings) - len(queue), len(queue), [i["id"] for i in queue])
                calibration_table(findings, "label")  # raw confidence against the labelled set (C12)
                direct = [i for i in findings if route(i) == "direct_report"]
                log.info("direct_report precision against the answer key: %d/%d",
                         sum(i["label"] == "correct" for i in direct), len(direct))

            elif run == "verify":
                for name in SUBSET:
                    items = [i for i in findings if i.get("file") == name]
                    if not items:
                        continue
                    listing = format_file(next(f for f in files if f["name"] == name))
                    claims = json.dumps([{k: i[k] for k in ("id", "line", "severity", "description")} for i in items])
                    # independent: a NEW session that never saw the reviewer's scores or reasons (C13)
                    out = await run_review(f"{listing}\n\nReported issues:\n{claims}",
                                           build_review_options(settings, VERIFY_SCHEMA, VERIFIER_PROMPT))
                    independent = {v["finding_id"]: v["verdict"] for v in (out["output"] or {}).get("verdicts", [])}
                    # self-review: the SAME session, with its own "I chose this because" in context (C14)
                    out = await run_review(SELF_CHECK_PROMPT.format(ids=[i["id"] for i in items]),
                                           build_review_options(settings, VERIFY_SCHEMA, resume=sessions[name]))
                    own = {v["finding_id"]: v["verdict"] for v in (out["output"] or {}).get("verdicts", [])}
                    for item in items:
                        item["independent"] = independent.get(item["id"], "no verdict")
                        item["self"] = own.get(item["id"], "no verdict")
    except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
        log.error("SDK error: %s", exc)
        return 1

    rows = [i for i in findings if i.get("independent") in ("confirmed", "rejected")]  # the calibration dataset (C16)
    for r in rows:
        log.info("dataset %-14s confidence %.2f  self %-10s independent %-10s label %s", r["id"], r["confidence"],
                 r["self"], r["independent"], r["label"])
    calibration_table(rows, "independent")
    for arm in ("self", "independent"):  # who catches the reviewer's own mistakes? (C14)
        wrong = [r for r in rows if r["label"] == "incorrect"]
        right = [r for r in rows if r["label"] == "correct"]
        log.info("%-11s rejected %d/%d label-incorrect findings, confirmed %d/%d label-correct ones", arm,
                 sum(r[arm] == "rejected" for r in wrong), len(wrong), sum(r[arm] == "confirmed" for r in right), len(right))
    log.info("overturned (confidence >= %.1f, rejected by the independent instance): %s", ROUTE_THRESHOLD,
             [r["id"] for r in rows if r["confidence"] >= ROUTE_THRESHOLD and r["independent"] == "rejected"] or "none")
    new = adjust_threshold(rows)
    for t in (ROUTE_THRESHOLD, new):
        above = [r for r in rows if r["confidence"] >= t]
        log.info("threshold %.2f: %d finding(s) at or above it, %d correct by the answer key", t, len(above),
                 sum(r["label"] == "correct" for r in above))
    log.info("routing threshold: %.2f -> %.2f (calibrated against the independent verdicts)", ROUTE_THRESHOLD, new)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
