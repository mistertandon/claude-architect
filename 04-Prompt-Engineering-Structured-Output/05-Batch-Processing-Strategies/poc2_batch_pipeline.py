"""
POC 2 - Sample, batch, retry the failures (Message Batches API)
===============================================================
One batch run that pays once:

    sample   refine the prompt on 5 documents with synchronous calls (the SAME request dicts a batch will carry)
    batch    20 documents in one batch, one custom_id each; poll until it ends; match results by custom_id
    retry    a second batch with ONLY the failed documents, and a larger max_tokens

The batch id is saved to batch_state.json first: a restarted script polls the same batch instead of paying twice.
Delete that file to start a new run.

Besides model I/O, the log shows the sample scores, the batch status while it runs, each result's verdict, and the
cost arithmetic. A batch typically ends within an hour; one that isn't done in 24 hours expires.

Run:  python poc2_batch_pipeline.py     (3 runs: up to 15 sample calls, a 20-request batch, a small retry batch)
"""

import asyncio
import json
import re
import sys

import anthropic

from batch_setup import (
    FIRST_MAX_TOKENS,
    PROMPTS,
    RETRY_MAX_TOKENS,
    SAMPLE,
    build_params,
    is_correct,
    make_documents,
    parse_output,
)
from common import POC_DIR, Settings, load_settings, log, log_model_io, setup_logging

STATE_FILE = POC_DIR / "batch_state.json"  # E3
CUSTOM_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")  # the API's rule for custom_id

RUNS = ["sample", "batch", "retry"]


async def refine_on_sample(client: anthropic.AsyncAnthropic, settings: Settings, docs: dict) -> str:
    """Try each prompt version on the sample; stop at the first that gets all 5 right (C10)."""
    best, best_score = PROMPTS[0], -1
    for version, prompt in enumerate(PROMPTS, 1):
        correct, failed = 0, []
        for doc_id in SAMPLE:
            params = build_params(settings.model_id, docs[doc_id], prompt)
            log.info("MODEL INPUT   prompt       [%s] %s", doc_id, docs[doc_id]["text"])
            message = await client.messages.create(**params)  # the exact dict a batch entry will carry (E1)
            log_model_io(message, doc_id)
            data = parse_output(message)
            if data is not None and is_correct(docs[doc_id], data):
                correct += 1
            else:
                failed.append(doc_id)
        log.info("sample v%d: %d/%d correct; failed: %s", version, correct, len(SAMPLE), failed or "none")
        if correct > best_score:
            best, best_score = prompt, correct
        if correct == len(SAMPLE):
            break
    return best


async def run_batch(client: anthropic.AsyncAnthropic, settings: Settings, requests: list[dict], key: str) -> dict:
    """Submit (or resume) a batch, poll until it ends, and return its results keyed by custom_id (C4, C5)."""
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.is_file() else {}
    if key in state:
        batch_id = state[key]
        log.info("resuming %s", batch_id)
    else:
        if len({r["custom_id"] for r in requests}) != len(requests) or not all(
                CUSTOM_ID.match(r["custom_id"]) for r in requests):  # the only link from a result back to its document
            raise ValueError("every custom_id must be unique and match ^[a-zA-Z0-9_-]{1,64}$")
        for r in requests:
            log.info("MODEL INPUT   prompt       [%s] max_tokens=%d %s", r["custom_id"], r["params"]["max_tokens"],
                     r["params"]["messages"][0]["content"])
        batch = await client.messages.batches.create(requests=requests)
        batch_id = batch.id
        STATE_FILE.write_text(json.dumps({**state, key: batch_id}))  # saved BEFORE the long wait (E3)
    while True:
        batch = await client.messages.batches.retrieve(batch_id)
        log.info("batch %s: %s %s", batch_id, batch.processing_status, batch.request_counts)
        if batch.processing_status == "ended":
            break
        await asyncio.sleep(settings.poll_seconds)
    results = {}
    async for result in await client.messages.batches.results(batch_id):  # any order: match by custom_id
        results[result.custom_id] = result
        if result.result.type == "succeeded":
            log_model_io(result.result.message, result.custom_id)
        else:
            log.info("MODEL OUTPUT  result       [%s] %s", result.custom_id, result.result.type)
    log.info("results arrived in this order: %s", list(results))
    return results


def failed_ids(results: dict) -> list[str]:
    """Not succeeded (errored, canceled, expired), or cut off at max_tokens, or not valid JSON (C6)."""
    return sorted(cid for cid, r in results.items()
                  if r.result.type != "succeeded" or parse_output(r.result.message) is None)


async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc2_batch_pipeline")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    client = anthropic.AsyncAnthropic()
    docs = {d["id"]: d for d in make_documents()}
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.is_file() else {}
    prompt, results = state.get("prompt"), {}
    try:
        for run in RUNS:
            if run == "sample" and prompt is None:
                prompt = await refine_on_sample(client, settings, docs)
                STATE_FILE.write_text(json.dumps({**state, "prompt": prompt}))
                state = json.loads(STATE_FILE.read_text())
            elif run == "batch":
                log.info("batch prompt: %s", prompt)
                requests = [{"custom_id": d["id"], "params": build_params(settings.model_id, d, prompt)}
                            for d in docs.values()]
                results = await run_batch(client, settings, requests, "batch_id")
                first_pass = {cid: ("failed" if cid in failed_ids(results) else
                                    "correct" if is_correct(docs[cid], parse_output(r.result.message)) else "incorrect")
                              for cid, r in results.items()}
                log.info("first pass: %s", " ".join(f"{cid}={v}" for cid, v in sorted(first_pass.items())))
                good = sum(v == "correct" for v in first_pass.values())
                log.info("first-pass success %d/%d = %.0f%%; resubmissions needed: %d", good, len(docs),
                         100 * good / len(docs), len(docs) - good)
                log.info("cost of a weak prompt: 90%% first pass -> %d retries, 60%% -> %d retries: %.1fx the "
                         "resubmissions", round(20 * (1 - 0.9)), round(20 * (1 - 0.6)),
                         round(20 * (1 - 0.6)) / round(20 * (1 - 0.9)))  # (C11)
            elif run == "retry":
                retry = failed_ids(results)
                log.info("retry batch: %d request(s) %s with max_tokens %d (a full resubmission would send %d, paying "
                         "again for %d documents that already succeeded)", len(retry), retry, RETRY_MAX_TOKENS,
                         len(docs), len(docs) - len(retry))  # (C7)
                if not retry:
                    continue
                requests = [{"custom_id": cid, "params": build_params(settings.model_id, docs[cid], prompt,
                                                                      RETRY_MAX_TOKENS)} for cid in retry]
                retried = await run_batch(client, settings, requests, "retry_batch_id")
                fixed = [cid for cid in retry if cid in retried and retried[cid].result.type == "succeeded"
                         and (data := parse_output(retried[cid].result.message)) is not None and is_correct(docs[cid], data)]
                log.info("after the retry: %d/%d fixed %s (first batch max_tokens %d)", len(fixed), len(retry), fixed,
                         FIRST_MAX_TOKENS)
    except anthropic.APIError as exc:  # an invalid key, a network failure, a rejected batch, ...
        log.error("API error: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
