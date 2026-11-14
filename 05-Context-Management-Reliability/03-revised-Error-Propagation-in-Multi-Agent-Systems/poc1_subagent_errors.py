"""
POC 1 - The subagent reports precisely and retries locally   (offline: no API call, free; about 17 s of waits)
===============================================================================================================
The researcher's search layer, run on 8 topics with planted failures and the first-round input ('<topic> 2026',
no region):

    search_once()         try/except: an access failure (retry it), a refusal (don't), or ok, even with 0 sources
    search_with_retry()   3 local retries with a doubling wait (1, 2, 4 s), keeping every source that arrived
    build_report()        ONE report per topic: status, shouldRetry, results, and an error with failureType,
                          attemptedAction, partialResults and alternativeApproaches

Only what can't be fixed locally leaves the subagent, and it leaves complete. Then two comparisons: an anti-pattern
search that swallows every exception, and the doubling wait against a fixed one.

Run:  python poc1_subagent_errors.py
"""

import asyncio
import json
import sys

from propagation_setup import (BASE_DELAY, MAX_RETRIES, PropagationState, backend_stream, search_with_retry,
                               validate_report)

POC1_TOPICS = ["solar", "wind", "geothermal", "tidal", "hydropower", "biomass", "fusion", "ocean thermal"]


def suppressing_search(topic: str, query: str) -> dict:
    """THE ANTI-PATTERN (C7): every exception becomes an empty success, and what had arrived is thrown away."""
    results = []
    try:
        for source in backend_stream(topic, query, None, 1):
            results.append(source)
    except Exception:  # "the library was down" now looks exactly like "the library has nothing"
        results = []
    return {"topic": topic, "status": "success", "shouldRetry": False, "results": results, "error": None}


def summary(report: dict) -> str:
    """One line per report: what the coordinator will see."""
    if report["status"] == "success":
        return f"success, shouldRetry {report['shouldRetry']}, {len(report['results'])} result(s)"
    error = report["error"]
    return (f"{report['status']}, failureType {error['failureType']}, shouldRetry {report['shouldRetry']}, "
            f"partialResults {[s['id'] for s in error['partialResults']]}")


async def main() -> int:
    state = PropagationState()
    print(f"Searching {len(POC1_TOPICS)} topics with '<topic> 2026' and no region; the waits add about 17 s.\n")
    for topic in POC1_TOPICS:
        report = await search_with_retry(topic, f"{topic} 2026", None, state)
        for _, attempt, outcome, source_ids, wait, exception in [a for a in state.attempts if a[0] == topic]:
            print(f"{topic:<14} attempt {attempt}: {outcome}" + (f" ({exception})" if exception else "")
                  + f", received {source_ids}" + (f", then wait {wait} s" if wait else ""))
        print(f"{'':<14} report: {summary(report)}; validate_report: {validate_report(report) or 'valid'}\n")

    geothermal = next(report for report in state.reports if report["topic"] == "geothermal")
    print("The geothermal report, as the coordinator will receive it (C1, C13):")
    print(json.dumps(geothermal, indent=2, ensure_ascii=False), "\n")

    ocean = next(report for report in state.reports if report["topic"] == "ocean thermal")
    print("Access failure against valid empty result (C6, C7):")
    print(f"   ocean thermal, real report:          {json.dumps(ocean)}")
    print(f"   geothermal, suppressing_search():    {json.dumps(suppressing_search('geothermal', 'geothermal 2026'))}")
    print("   The same report for 'the library was down' and 'the library has nothing': nobody would retry\n"
          "   geothermal, and GEO-1 and GEO-2, which had already arrived, are lost.\n")

    waits = [a[4] for a in state.attempts if a[0] == "geothermal" and a[4]]
    print(f"Backoff (C12): geothermal waited {waits} = {sum(waits)} s, each wait double the one before; "
          f"a fixed {BASE_DELAY} s delay would give {[BASE_DELAY] * MAX_RETRIES} = {BASE_DELAY * MAX_RETRIES} s.")

    failed = [a for a in state.attempts if a[2] != "ok"]
    retries = [a for a in state.attempts if a[1] > 1]
    failure_reports = [report["topic"] for report in state.reports if report["status"] != "success"]
    print(f"Local handling (C11): {len(failed)} failed attempts and {len(retries)} local retries stayed inside the "
          f"subagent. The coordinator will see {len(failure_reports)} failure reports {failure_reports}, "
          f"not {len(failed)} failed attempts.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
