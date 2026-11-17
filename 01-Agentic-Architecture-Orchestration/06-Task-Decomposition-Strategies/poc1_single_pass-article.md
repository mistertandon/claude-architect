# POC 1: One Request for the Whole Codebase

> **File:** `poc1_single_pass.py` (with `review_setup.py` and `common.py`)
> **Domain:** 01 Agentic Architecture & Orchestration → 06 Task Decomposition Strategies
> **SDK:** Claude Agent SDK for Python (`claude-agent-sdk >=0.2.174,<0.3`; 0.2.181 in the folder's `.venv`)
> **Page:** https://claude.ai/artifact/9aHnhpY44cFFcsskN1AYC9

---

## 1. What this POC proves

A code review agent reads every file of a small order service and reviews them all in **one** request. This is the baseline the exam warns about: at real scale, attention spreads thin across many files. POC 2 replaces it with per-file passes and an integration pass. Every claim below is checked against one real run: `logs/poc1_single_pass_20261113_214420.log`.

| # | Idea | Where it shows up in the code |
|---|------|------------------------------|
| 1 | **The single-pass architecture:** every file in one prompt, one structured answer with a review per file plus the cross-file issues. | `SINGLE_PASS_PROMPT`, `SINGLE_PASS_SCHEMA`; one `run_review()` call |
| 2 | **Structured per-file feedback:** bug count, severity, line numbers, plus each file's interface (`exports`, `uses`). | `FILE_REVIEW` in `review_setup.py` |
| 3 | **A planted answer key makes depth measurable:** one local bug per file, two cross-file bugs, one pattern copied into two files. | `PLANTED`, `CROSS_FILE`, `PATTERN_FILES`, `log_scores()` |
| 4 | **Same model, prompt and schema as POC 2,** so any difference comes from the structure. | `REVIEWER_PROMPT`, `build_review_options()`, `format_file()` |
| 5 | **At 3 files, the single pass does well.** The docstring says so, and the real run confirms it: 3 of 3 planted bugs, 2 of 2 cross-file issues. The POC shows the structure to replace, not the dilution symptom. | the five score lines at the end of the log |

The pattern in one line:

```
[ checkout.ts + inventory.ts + pricing.ts ] ──▶ ONE review call ──▶ { files: [3 reviews], cross_file_issues: [...] }
```

---

## 2. The files involved

```
06-Task-Decomposition-Strategies/
├── .env / .env.example       ← ANTHROPIC_API_KEY, MODEL_ID, MAX_TURNS, MAX_BUDGET_USD
├── requirements.txt          ← claude-agent-sdk >=0.2.174,<0.3 and python-dotenv
├── common.py                 ← Settings, load_settings(), setup_logging(), log_model_io()
├── review_setup.py           ← load_repo(), format_file(), REVIEWER_PROMPT, schemas, options, run_review(), answer key
├── sample_repo/              ← the mock order service, with planted defects
│   ├── checkout.ts           (31 lines)
│   ├── inventory.ts          (26 lines)
│   └── pricing.ts            (40 lines)
├── poc1_single_pass.py       ← entry point: every file in one request
├── poc2_multi_pass.py        ← POC 2: per-file passes + an integration pass (not covered here)
└── logs/
    └── poc1_single_pass_20261113_214420.log   ← the real run used in sections 3.2 and 5
```

Every snippet in this article is copied from these files, logging statements included. Each logging statement is named with the log line it writes.

The responsibilities split like this:
- `common.py` covers **configuration and observability**: defaults for a review call, and one log line per model input or output (including `structured` for the JSON review).
- `review_setup.py` covers **what both architectures share**: reading the repo, the numbered listing, the one reviewer prompt, the one per-file schema, the options, the review call, and the **answer key** that scores any review.
- `poc1_single_pass.py` covers **the single-pass architecture**: one prompt with every file, one call.

---

## 3. End-to-end execution flow

### 3.1 The big picture

```
python poc1_single_pass.py
        │
        ▼
asyncio.run(main())                                                     [poc1_single_pass.py]
        │
        ├─▶ load_settings(), setup_logging("poc1_single_pass")          [common.py]
        ├─▶ files = load_repo()                                         [review_setup.py]
        │       sample_repo/*.ts, sorted by name: checkout, inventory, pricing (the review order)
        │
        ├─▶ prompt = SINGLE_PASS_PROMPT.format(n=3) + format_file(f) for every file
        │       one header + numbered lines per file, all in ONE prompt
        │
        └─▶ for trial in RUNS:                                          ("trial 1"; 2 more are commented out)
               ├─▶ review = run_review(prompt, build_review_options(settings, SINGLE_PASS_SCHEMA))  → one query()
               ├─▶ reviews = {file name: its review}
               └─▶ log_scores(reviews, files, review["cross_file_issues"])   [review_setup.py]
                       per file: issues, planted bug flagged?   pattern verdicts   cross-file issues found
```

Inside `run_review()`. The right-hand column names the log line each step writes.

```
run_review(prompt, options)                                                          [review_setup.py]
   │
   ├─ log.info("MODEL INPUT   prompt ...")                                         → log: prompt (with all the code)
   └─▶ async for message in query(prompt=prompt, options=options):
          │
          │   ┌──────────────────────── SDK-owned: one review session ─────────────────────┐
          │   │ system prompt = REVIEWER_PROMPT; no tools except the built-in              │
          │   │ StructuredOutput that output_format adds                                   │
          │   │ Claude reads the whole prompt and calls StructuredOutput {files, cross...} │  → log: structured
          │   │ the JSON is checked against SINGLE_PASS_SCHEMA → accepted                  │  → log: tool_result
          │   │ yields ResultMessage (success, stop_reason = tool_use)                     │  → log: stop_reason
          │   └────────────────────────────────────────────────────────────────────────────┘
          │
          ├─ log_model_io(message)
          ├─ ResultMessage success → output = message.structured_output
          └─ ResultError → log.error("The review failed: %s")                         → log: (none in this run)
```

### 3.2 Messages your `async for` receives (the one review call, real output)

The values below come from the real run on 2026-11-13, recorded in `logs/poc1_single_pass_20261113_214420.log`. Each log line comes from one statement in the code:

| Log line tag | Message class yielded by `query()` | Field logged | Written by |
|--------------|------------------------------------|--------------|------------|
| `MODEL INPUT   prompt` | *(none: the `prompt` passed to `run_review()`)* | `prompt`: the instructions and every numbered file | `log.info("MODEL INPUT   prompt ...")` in `run_review()` (`review_setup.py`) |
| `MODEL OUTPUT  structured` | `AssistantMessage` → `ToolUseBlock` named `StructuredOutput` | `block.input`, `block.id` | `log_model_io()` (`common.py`) |
| `MODEL INPUT   tool_result` | `UserMessage` → `ToolResultBlock` | `block.content`, `block.tool_use_id`, `block.is_error` | `log_model_io()` |
| `MODEL OUTPUT  stop_reason` | `ResultMessage` | `message.stop_reason`, `message.subtype` | `log_model_io()` |
| `MODEL OUTPUT  thinking` / `text` / `tool_use` | `AssistantMessage` blocks | as named | `log_model_io()`. None in this log |
| `#n <file>: k issue(s), planted bug flagged: ...` | *(none: Python scores)* | `review["issues"]`, `flagged()` | `log.info(...)` in `log_scores()` |
| `forEach + nested find, identical in both files: {...} -> ...` | *(none)* | `flagged()` for both copies | `log.info(...)` in `log_scores()` |
| `Cross-file issues found: [...] (k of 2)` | *(none)* | `cross_file_issues` vs `CROSS_FILE` | `log.info(...)` in `log_scores()` |
| `<trial>: no structured review`, `The review failed: ...`, `SDK error: ...` | *(none)* | the failure | `main()` and `run_review()`. None in this log |

The call as it really streamed:

```
21:44:20  (input)                                                              log: prompt
            prompt = Review all 3 files of this codebase in one pass. Return one review per file, in
                       the order given, then every cross-file issue: data flow between modules,
                       inconsistent API usage, and patterns used differently across files. Name every
                       file each cross-file issue involves.

                     === checkout.ts (31 lines) ===
                        1 | // checkout.ts - the checkout flow of the Fernway Outfitters order service
                        ...
                       27 |   if (order.status = "paid") {
                        ...
                     === inventory.ts (26 lines) ===
                        ...
                     === pricing.ts (40 lines) ===
                        ...                                        ← 97 numbered lines of code in one prompt

21:44:33  AssistantMessage › ToolUseBlock                                      log: structured
            name  = "StructuredOutput"
            input = {'files': [ ...3 reviews: checkout.ts, inventory.ts, pricing.ts... ],
                     'cross_file_issues': [ ...4 issues... ]}
            id    = "toolu_01K5gjmQCTS36z6d7P6TScLm"
21:44:33  UserMessage › ToolResultBlock                                        log: tool_result
            content     = Structured output provided successfully             ← a plain string
            tool_use_id = "toolu_01K5gjmQCTS36z6d7P6TScLm", is_error = None
21:44:33  ResultMessage                                                        log: stop_reason
            stop_reason = "tool_use", subtype = "success"

21:44:34  #1 checkout.ts: 3 issue(s), planted bug flagged: True               ← log_scores()
21:44:34  #2 inventory.ts: 3 issue(s), planted bug flagged: True
21:44:34  #3 pricing.ts: 4 issue(s), planted bug flagged: True
21:44:34  forEach + nested find, identical in both files: {'pricing.ts': False, 'inventory.ts': False} -> consistent
21:44:34  Cross-file issues found: ['cents vs dollars', 'false vs throw'] (2 of 2)
```

What to notice in the real data:
- **One request, one answer.** The whole repo went in one prompt (the `MODEL INPUT prompt` entry spans 104 lines in the log file), and one `StructuredOutput` call came back 13 s later with all three reviews and the cross-file issues.
- **`success` with `stop_reason = "tool_use"`.** With `output_format`, Claude hands in the JSON by calling `StructuredOutput`, and the run ends right after it's accepted. `run_review()` checks only `subtype`, so this counts as done.
- **No sign of dilution at this size.** The last file got the most issues (4), and every planted bug was flagged. The docstring predicts this: "expect a good review here".
- **No narration and no thinking.** The only model output is the `structured` line.
- **Not shown:** the `SystemMessage`, cost and turn counts are in the stream but not in the log.

---

## 4. Code walkthrough

The snippets follow the order in which the code runs: the script first, then the module functions it calls. Where a snippet writes log lines, they're shown under it, copied from the real log (long values trimmed with `...`).

### 4.1 Module docstring: the baseline, and what to expect from it

```python
"""
POC 1 - The single-pass review: every file in ONE request
==========================================================
The baseline the exam warns about: one call reviews the whole codebase at once and returns one structured review
per file plus the cross-file issues.

At real scale (the exam's example: 14 files) attention is spread thin: the first files get detailed feedback, the
last ones shallow or none, and identical code gets different verdicts. This repo has only 3 short files, so expect a
good review here: the POC shows the STRUCTURE you are going to replace, not the symptom.

Besides model I/O, the log shows per file the issue count and whether its planted bug was flagged, whether the
code copied into two files got the same verdict, and which cross-file issues were found.

Run:  python poc1_single_pass.py     (1 API run; 2 optional repeat trials)
"""
```

**Why it matters:** the docstring states the exam's symptoms (early files detailed, late files shallow, identical code judged differently) and, honestly, that this 3-file repo won't show them. Read this POC for the architecture; the scores are a baseline for POC 2, not a demonstration of dilution.

---

### 4.2 Imports

```python
import asyncio
import sys
from pathlib import Path

from claude_agent_sdk import ClaudeSDKError

from common import load_settings, log, setup_logging
from review_setup import SINGLE_PASS_SCHEMA, build_review_options, format_file, load_repo, log_scores, run_review
```

| Import | What it brings in | Why this file needs it |
| --- | --- | --- |
| `Path` | Path handling | Normalizes the file names in the model's answer (`Path(r["file"]).name.lower()`) |
| `ClaudeSDKError` | The SDK's base error | Stops the script on an SDK runtime failure |
| `SINGLE_PASS_SCHEMA` | From `review_setup` | The answer's shape: every file's review plus the cross-file issues |
| `build_review_options` | From `review_setup` | Options shared with POC 2, with this schema |
| `format_file`, `load_repo` | From `review_setup` | Read the repo; turn each file into a numbered listing |
| `log_scores` | From `review_setup` | Scores a review against the planted answer key |
| `run_review` | From `review_setup` | One review call in a new session |

---

### 4.3 The single-pass prompt and the trials

```python
SINGLE_PASS_PROMPT = (
    "Review all {n} files of this codebase in one pass. Return one review per file, in the order given, then every "
    "cross-file issue: data flow between modules, inconsistent API usage, and patterns used differently across "
    "files. Name every file each cross-file issue involves.\n\n"
)

RUNS = [
    "trial 1",
    # "trial 2",  # optional: attention effects vary from run to run
    # "trial 3",  # optional
]
```

**Why it matters:**
- **One instruction for everything:** review every file, in order, *and* find the cross-file issues. All of it competes for attention in one response.
- **The three cross-file categories** (data flow, API usage, pattern consistency) are the exam's list; POC 2's integration pass asks for the same three.
- **One trial runs.** The comment says attention effects vary from run to run; the other two trials are commented out, so this log has one review.

---

### 4.4 `main()`: build one prompt, make one call, score it

```python
async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc1_single_pass")
        files = load_repo()
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    # ONE request holds every file: the whole codebase competes for the same attention.
    prompt = SINGLE_PASS_PROMPT.format(n=len(files)) + "\n\n".join(format_file(f) for f in files)
    for trial in RUNS:
        try:
            review = await run_review(prompt, build_review_options(settings, SINGLE_PASS_SCHEMA))
        except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
            log.error("SDK error: %s", exc)
            return 1
        if review is None:
            log.error("%s: no structured review", trial)
            continue
        reviews = {Path(r["file"]).name.lower(): r for r in review["files"]}  # a file with no review counts as missed
        log_scores(reviews, files, review["cross_file_issues"])
    return 0
```

**Why it matters:**
- **`load_repo()` is part of setup.** A missing or empty `sample_repo/` raises `ValueError`, caught with the other setup errors.
- **The prompt is built once,** from the instructions and every file's numbered listing, joined by blank lines. This is the line that defines "single pass".
- **`review is None` is a failed review,** logged and skipped (no `structured_output`, or a `ResultError`).
- **Reviews are keyed by file name.** A file the model forgot gets no entry, and `log_scores()` then scores it as an empty review: "a file with no review counts as missed".

The `MODEL INPUT   prompt` line this produced holds the whole codebase:

```
21:44:20  MODEL INPUT   prompt       Review all 3 files of this codebase in one pass. Return one review per file, in the order given, then every cross-file issue: data flow between modules, inconsistent API usage, and patterns used differently across files. Name every file each cross-file issue involves.
```

It continues for 103 more lines without timestamps: a blank line, then `=== checkout.ts (31 lines) ===` and its numbered code, then `inventory.ts` and `pricing.ts`.

---

### 4.5 `__main__`

```python
if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

---

### 4.6 `load_repo()` and `format_file()`: one view of the code (from `review_setup.py`)

```python
def load_repo(path: Path = REPO_DIR) -> list[dict[str, Any]]:
    """Read every source file in the folder, sorted by name: that is the review order (C1)."""
    files = [(p.name, p.read_text(encoding="utf-8")) for p in sorted(path.iterdir()) if p.suffix in SOURCE_EXTENSIONS]
    if not files:
        raise ValueError(f"no {SOURCE_EXTENSIONS} files in {path}")
    return [{"index": i, "name": name, "text": text, "lines": len(text.splitlines())}
            for i, (name, text) in enumerate(files, 1)]


def format_file(f: dict[str, Any]) -> str:
    """The ONLY way code enters a prompt: a header and numbered lines, the same in both POCs (E1)."""
    numbered = [f"{i:>4} | {line}" for i, line in enumerate(f["text"].splitlines(), 1)]
    return f"=== {f['name']} ({f['lines']} lines) ===\n" + "\n".join(numbered)
```

**Why it matters:**
- **Sorted by name = the review order:** `checkout.ts` (#1), `inventory.ts` (#2), `pricing.ts` (#3). At scale, that order decides which files get the thin end of the attention.
- **Numbered lines** let the model cite exact lines, and let `flagged()` check them.
- **The same listing in both POCs.** Any difference between POC 1 and POC 2 can't come from how the code was shown.
- `SOURCE_EXTENSIONS` is `.ts`, `.tsx`, `.js`, `.jsx`: the agent reviews TypeScript and JavaScript.

---

### 4.7 One reviewer prompt, one schema (from `review_setup.py`)

```python
REVIEWER_PROMPT = (
    "You are a senior TypeScript reviewer for the Fernway Outfitters order service. Find real defects: logic errors, "
    "unhandled edge cases, security problems and performance problems. Give every file the same depth of review, "
    "from the first file to the last. For each issue, give the exact line number from the numbered listing, a "
    "severity (critical, major or minor) and a one-sentence description, and set bug_count to the number of issues. "
    "For each file, also record its interface for later cross-file checks: exports (each export's signature, units "
    "and error behavior) and uses (each call into another module: what it passes and what it assumes about the result)."
)

FILE_REVIEW = {  # structured per-file feedback: bug count, severities, line references (C6)
    "type": "object",
    "properties": {
        "file": {"type": "string"},
        "bug_count": {"type": "integer"},
        "issues": {"type": "array", "items": {
            "type": "object",
            "properties": {"line": {"type": "integer"},
                           "severity": {"type": "string", "enum": ["critical", "major", "minor"]},
                           "description": {"type": "string"}},
            "required": ["line", "severity", "description"]}},
        "exports": {"type": "array", "items": {"type": "string"}},  # the interface: what the integration pass reads
        "uses": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["file", "bug_count", "issues", "exports", "uses"],
}
CROSS_FILE_ISSUES = {"type": "array", "items": {
    "type": "object",
    "properties": {"files": {"type": "array", "items": {"type": "string"}},
                   "kind": {"type": "string", "enum": ["data_flow", "api_consistency", "pattern_consistency"]},
                   "description": {"type": "string"}},
    "required": ["files", "kind", "description"]}}

SINGLE_PASS_SCHEMA = {"type": "object", "properties": {"files": {"type": "array", "items": FILE_REVIEW},
                                                       "cross_file_issues": CROSS_FILE_ISSUES},
                      "required": ["files", "cross_file_issues"]}
```

**Why it matters:**
- **The prompt already asks for equal depth:** "Give every file the same depth of review, from the first file to the last." If a prompt could fix dilution, this one would. The exam's point is that it can't at scale; the fix is structural.
- **`FILE_REVIEW` is the structured per-file feedback** the exam asks for: `bug_count`, and per issue a `line`, a `severity` from an enum, and a `description`.
- **`exports` and `uses` record each file's interface.** The single pass doesn't need them (it sees all the code), but POC 2's integration pass reads only these.
- **`SINGLE_PASS_SCHEMA`** wraps a list of `FILE_REVIEW`s and the `CROSS_FILE_ISSUES` in one object: one answer for everything.

> **A schema checks shape, not agreement.** In the real run, `pricing.ts` came back with `bug_count: 3` and four `issues`. Both are valid against the schema; they just disagree. `log_scores()` counts `len(issues)`, so the log says `4 issue(s)`.

---

### 4.8 `build_review_options()` and `run_review()` (from `review_setup.py`)

```python
def build_review_options(settings: Settings, schema: dict[str, Any]) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=settings.model_id,  # one model for every pass (C11)
        system_prompt=REVIEWER_PROMPT,  # one reviewer prompt for every pass, with the equal-depth rule (C7)
        output_format={"type": "json_schema", "schema": schema},  # validated JSON in ResultMessage.structured_output
        tools=[],  # no built-in tools: the code is in the prompt, and no pass can open another file
        setting_sources=[],  # ignore ~/.claude settings, CLAUDE.md and hooks: the same run on any machine
        env={"ENABLE_TOOL_SEARCH": "false"},  # no ToolSearch calls
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=settings.max_turns,  # safety cap (01 C16); a review needs only a few turns
        max_budget_usd=settings.max_budget_usd,  # cost guard per review call
    )


async def run_review(prompt: str, options: ClaudeAgentOptions) -> dict[str, Any] | None:
    """One review call = one NEW session with an empty history. Returns the validated JSON, or None on failure."""
    log.info("MODEL INPUT   prompt       %s", prompt)
    output = None
    try:
        async for message in query(prompt=prompt, options=options):
            log_model_io(message)
            if isinstance(message, ResultMessage) and message.subtype == "success":
                output = message.structured_output  # None here means no structured output: treat it as a failure
            # No `break`: a few system events can still arrive after the ResultMessage.
    except ResultError as exc:  # raised AFTER the error ResultMessage, e.g. error_max_structured_output_retries
        log.error("The review failed: %s", exc)
    return output
```

| Option | What it does | Agentic concept |
|--------|--------------|-----------------|
| `model` | One model for every pass in both POCs | Holds the model constant: only structure changes |
| `system_prompt=REVIEWER_PROMPT` | The same reviewer and equal-depth rule everywhere | Holds the prompt constant |
| `output_format` | JSON validated against the schema, in `structured_output` | Structured, machine-scorable output |
| `tools=[]` | No built-in tools: the code is in the prompt | A pass can't open other files; what it sees is what it reviews |
| `thinking` | Summarized reasoning | None was logged in this run |
| `max_turns`, `max_budget_usd` | Defaults `10` and `0.50` | Guards per review call |

**Why it matters:**
- **`run_review()` = one new session.** Every call starts with an empty history. In POC 1 that's the only call; in POC 2 it's what isolates each file.
- **`subtype == "success"` is the completion check,** not `stop_reason`, because a structured run ends on the `StructuredOutput` tool call.
- **`None` means no usable review,** whether the run failed or returned no structured output.

The three lines the review call wrote after the prompt:

```
21:44:33  MODEL INPUT   tool_result  Structured output provided successfully  (tool_use_id=toolu_01K5gjmQCTS36z6d7P6TScLm, is_error=None)
21:44:33  MODEL OUTPUT  stop_reason  tool_use  (loop result: success)
```

(plus the `structured` line just before them, pretty-printed in section 5.)

---

### 4.9 The answer key and `log_scores()` (from `review_setup.py`)

```python
PLANTED = {  # one local bug per file: a piece of its line
    "checkout.ts": 'if (order.status = "paid")',  # assignment instead of comparison
    "inventory.ts": "units * unitFee === invoiced",  # exact equality between computed decimals
    "pricing.ts": "i <= tiers.length",  # off by one: reads past the last tier
}
CROSS_FILE = {  # each side looks right on its own: only the two files together show the bug
    "cents vs dollars": ("pricing.ts", "checkout.ts"),  # orderTotal() returns cents; checkout formats it as dollars
    "false vs throw": ("inventory.ts", "checkout.ts"),  # reserveStock() returns false; checkout waits for a throw
}
PATTERN_FILES, PATTERN_LINE = ("pricing.ts", "inventory.ts"), "lookup.find("  # the same forEach + nested find, twice


def flagged(review: dict, f: dict[str, Any], fragment: str) -> bool:
    """Does any issue point within 2 lines of the line that holds fragment?"""
    line = next(i for i, text in enumerate(f["text"].splitlines(), 1) if fragment in text)
    return any(abs(issue["line"] - line) <= 2 for issue in review.get("issues", []))


def log_scores(reviews: dict[str, dict], files: list[dict[str, Any]], cross_file_issues: list[dict]) -> None:
    """The lesson lines: depth per file, the same code judged the same way, and the cross-file layer."""
    by_name = {f["name"]: f for f in files}
    for f in files:
        review = reviews.get(f["name"], {})
        log.info("#%d %s: %d issue(s), planted bug flagged: %s",
                 f["index"], f["name"], len(review.get("issues", [])), flagged(review, f, PLANTED[f["name"]]))
    verdicts = {name: flagged(reviews.get(name, {}), by_name[name], PATTERN_LINE) for name in PATTERN_FILES}
    log.info("forEach + nested find, identical in both files: %s -> %s", verdicts,
             "consistent" if len(set(verdicts.values())) == 1 else "CONTRADICTION")
    named = [{Path(name).name.lower() for name in issue["files"]} for issue in cross_file_issues]
    found = [label for label, pair in CROSS_FILE.items() if any(set(pair) <= files_named for files_named in named)]
    log.info("Cross-file issues found: %s (%d of %d)", found, len(found), len(CROSS_FILE))
```

| Line | Measures | Exam symptom it would show |
|------|----------|----------------------------|
| `#n <file>: k issue(s), planted bug flagged: ...` | Depth per file, in review order | Late files with fewer issues or a missed planted bug |
| `forEach + nested find, identical in both files: ... -> consistent / CONTRADICTION` | Whether identical code got the same verdict | One copy flagged, the other approved |
| `Cross-file issues found: [...] (k of 2)` | Whether the two-file bugs were seen | Cross-cutting issues missed |

**Why it matters:**
- **Planted ground truth makes the comparison objective.** Both POCs run the same `log_scores()` on the same key.
- **`flagged()` allows ±2 lines,** because a model may point at the line before or after the bug.
- **A cross-file issue counts only if it names both files** of the pair.

The five lines it wrote:

```
21:44:34  #1 checkout.ts: 3 issue(s), planted bug flagged: True
21:44:34  #2 inventory.ts: 3 issue(s), planted bug flagged: True
21:44:34  #3 pricing.ts: 4 issue(s), planted bug flagged: True
21:44:34  forEach + nested find, identical in both files: {'pricing.ts': False, 'inventory.ts': False} -> consistent
21:44:34  Cross-file issues found: ['cents vs dollars', 'false vs throw'] (2 of 2)
```

> **The pattern line undercounts.** It says neither copy was flagged, but the review flagged both: inventory.ts line 19 ("O(n*m) linear find per row ... duplicated verbatim as pricedNames") and pricing.ts line 33 (the same, the other way round). Both point at the function's first line; the `find` is 3 lines lower (22 and 36), just outside `flagged()`'s ±2 window. So "consistent" is right, but for the wrong reason: both copies *were* flagged, the same way.

---

### 4.10 `common.py`: settings and a single-agent log

This topic's `common.py` follows the earlier ones, with two differences:
- **Defaults** for a review call: `max_turns` `10`, `max_budget_usd` `0.50`, model `claude-sonnet-5-5`.
- **A `structured` branch,** for the JSON review `output_format` hands in:

```python
            elif isinstance(block, ToolUseBlock) and block.name == "StructuredOutput":
                # output_format at work: Claude hands in its JSON review through this built-in tool
                log.info("MODEL OUTPUT  structured   %s  (id=%s)", block.input, block.id)
```

| `log_model_io()` branch | Log line tag | Lines in this log |
|-------------------------|--------------|-------------------|
| `ToolUseBlock` named `StructuredOutput` | `MODEL OUTPUT  structured` | 1 |
| `ToolResultBlock` | `MODEL INPUT   tool_result` | 1 (`Structured output provided successfully`) |
| `ResultMessage` | `MODEL OUTPUT  stop_reason` | 1 |
| `ThinkingBlock`, `TextBlock`, other `ToolUseBlock` | `thinking`, `text`, `tool_use` | 0 |

---

## 5. Turn-by-turn trace of the run (real output)

The trace below is the real run from `logs/poc1_single_pass_20261113_214420.log` (2026-11-13, 21:44:20 to 21:44:34: 14 seconds for the one `query()` call and the scoring). Each log line points back to the statement that wrote it (section 3.2's table).

How to read the log block:
- In the log file, every entry is one line. Here, the entry's header stays on its first line, and its payload is pretty-printed underneath: one key or list item per line.
- Long text wraps onto a deeper-indented line.
- `...` marks text that was cut.

### 5.1 `trial 1`: the whole repo in one call

**Real log (the prompt is shortened; section 4.4 describes it):**

```
21:44:20  MODEL INPUT   prompt
          Review all 3 files of this codebase in one pass. ... Name every file each cross-file
            issue involves.

          === checkout.ts (31 lines) === ... === inventory.ts (26 lines) === ...
          === pricing.ts (40 lines) === ...

21:44:33  MODEL OUTPUT  structured
          {'files': [
              {'file': 'checkout.ts', 'bug_count': 3,
               'issues': [
                   {'line': 16, 'severity': 'critical', 'description': 'reserveStock returns false
                       and never throws, so the try/catch never fires and out-of-stock items are
                       silently accepted and charged.'},
                   {'line': 21, 'severity': 'critical', 'description': 'orderTotal returns integer
                       cents but the value is named amountDollars and formatted with toFixed(2) as
                       dollars, overcharging/misreporting by 100x.'},
                   {'line': 27, 'severity': 'major', 'description': 'Assignment `=` instead of
                       comparison `===` in the condition: it overwrites order.status with "paid"
                       and always takes the paid branch.'}],
               'exports': ['interface Order { ... }', 'checkout(order: Order, prices: PriceEntry[]):
                   string - ...', 'receiptHeading(order: Order): string - returns heading; mutates
                   order.status'],
               'uses': ['inventory.reserveStock(item.sku, item.quantity) - assumes it throws on
                   shortage, but it returns boolean false', 'pricing.orderTotal(order.items, prices)
                   - assumes dollars, actually returns integer cents', ...]},
              {'file': 'inventory.ts', 'bug_count': 3,
               'issues': [
                   {'line': 3, 'severity': 'major', 'description': 'The stock map is never populated
                       and no function adds stock, so every reservation fails (available is always
                       0).'},
                   {'line': 15, 'severity': 'major', 'description': 'Exact === comparison of units *
                       unitFee against invoiced uses floating-point money values, which can fail on
                       rounding (e.g. 0.1*3); ...'},
                   {'line': 19, 'severity': 'minor', 'description': 'backorderedNames does an O(n*m)
                       linear find per row; build a Map for lookup. It is also duplicated verbatim as
                       pricedNames in pricing.ts.'}],
               'exports': [...3 exports...], 'uses': []},
              {'file': 'pricing.ts', 'bug_count': 3,
               'issues': [
                   {'line': 26, 'severity': 'major', 'description': 'Loop bound i <= tiers.length
                       reads tiers[tiers.length] (undefined); ... should be i < tiers.length.'},
                   {'line': 27, 'severity': 'major', 'description': 'Assumes tiers are sorted
                       ascending; ...'},
                   {'line': 18, 'severity': 'major', 'description': 'Missing SKU price silently
                       defaults to 0, so unknown items are charged nothing ...'},
                   {'line': 33, 'severity': 'minor', 'description': 'pricedNames is O(n*m) with
                       linear find per row and duplicates backorderedNames from inventory.ts.'}],
               'exports': [...5 exports...], 'uses': []}
          ],
           'cross_file_issues': [
              {'files': ['checkout.ts', 'inventory.ts'], 'kind': 'api_consistency',
               'description': 'checkout wraps reserveStock in try/catch expecting a throw on
                   shortage, but reserveStock returns false and never throws, ...'},
              {'files': ['checkout.ts', 'pricing.ts'], 'kind': 'data_flow',
               'description': 'orderTotal returns integer cents, but checkout treats it as dollars
                   (amountDollars, toFixed(2)), producing a 100x wrong charge message.'},
              {'files': ['inventory.ts', 'pricing.ts'], 'kind': 'pattern_consistency',
               'description': 'backorderedNames and pricedNames are duplicated lookup-by-id
                   implementations with the same O(n*m) find; ...'},
              {'files': ['checkout.ts', 'inventory.ts', 'pricing.ts'], 'kind': 'pattern_consistency',
               'description': "Inconsistent error handling and money units: ..."}
          ]}
          (id=toolu_01K5gjmQCTS36z6d7P6TScLm)
21:44:33  MODEL INPUT   tool_result
          Structured output provided successfully
          (tool_use_id=toolu_01K5gjmQCTS36z6d7P6TScLm, is_error=None)
21:44:33  MODEL OUTPUT  stop_reason  tool_use  (loop result: success)

21:44:34  #1 checkout.ts: 3 issue(s), planted bug flagged: True
21:44:34  #2 inventory.ts: 3 issue(s), planted bug flagged: True
21:44:34  #3 pricing.ts: 4 issue(s), planted bug flagged: True
21:44:34  forEach + nested find, identical in both files: {'pricing.ts': False, 'inventory.ts':
            False} -> consistent
21:44:34  Cross-file issues found: ['cents vs dollars', 'false vs throw'] (2 of 2)
```

**The review against the answer key:**

| Planted defect | Where | Flagged? | By which issue |
|----------------|-------|----------|----------------|
| `if (order.status = "paid")` | checkout.ts:27 | yes | line 27, major |
| `units * unitFee === invoiced` | inventory.ts:15 | yes | line 15, major |
| `i <= tiers.length` | pricing.ts:26 | yes | line 26, major |
| cents vs dollars | pricing.ts → checkout.ts | yes | cross-file `data_flow`, and checkout.ts line 21 |
| false vs throw | inventory.ts → checkout.ts | yes | cross-file `api_consistency`, and checkout.ts line 16 |
| `forEach` + nested `find`, twice | inventory.ts:21–22, pricing.ts:35–36 | yes, both (at lines 19 and 33) | scored `False`/`False` by `flagged()`: outside ±2 lines |

**Issues beyond the key** (real problems the reviewer found that no one planted): the `stock` map is never filled (inventory.ts:3), a missing price silently counts as 0 (pricing.ts:18), and tiers are assumed sorted (pricing.ts:27).

**Variable values:**

| Variable / field | Value |
|------------------|-------|
| `files` | 3 dicts: `checkout.ts` (#1, 31 lines), `inventory.ts` (#2, 26), `pricing.ts` (#3, 40) |
| `prompt` | `SINGLE_PASS_PROMPT` + 3 numbered listings |
| `review` | the `structured` JSON above (`message.structured_output`) |
| `reviews` | keys `checkout.ts`, `inventory.ts`, `pricing.ts` |
| `bug_count` vs `len(issues)` | 3/3, 3/3, **3/4** (pricing.ts) |
| `verdicts` | `{'pricing.ts': False, 'inventory.ts': False}` → `consistent` |
| `found` | `['cents vs dollars', 'false vs throw']` |
| `message.subtype` / `stop_reason` | `"success"` / `"tool_use"` |

**Lessons from the real data:**
- **At 3 files, one pass is enough.** Every planted bug, both cross-file bugs, and three real extras. The last file got the most issues, not the fewest.
- **Cross-file issues are easy when all the code is in view.** The single pass saw both sides of each mismatch, and recorded them twice: as local issues in `checkout.ts` and as cross-file issues.
- **The structure is what POC 2 changes.** At the exam's 14 files, this same call would have to cover almost five times as many files in one response; that's where depth falls off for the late files and identical code gets different verdicts.
- **The scorer has limits.** `flagged()`'s ±2-line window missed the pattern findings that pointed at the function's first line, and the schema accepted a `bug_count` that disagreed with the issue list. Both are details of this POC's checking, not of the review.

### 5.2 The run at a glance

| | `trial 1` |
|-|-----------|
| Files in the request | 3 (97 numbered lines) |
| `query()` calls | 1 |
| Issues per file (#1, #2, #3) | 3, 3, 4 |
| Planted bugs flagged | 3 of 3 |
| Cross-file issues found (of the 2 planted) | 2 of 2 (plus 2 more pattern issues) |
| Pattern verdict | `consistent` (both scored `False`; both actually flagged) |
| Final `subtype` / `stop_reason` | `success` / `tool_use` |
| `thinking` lines | 0 |
| Wall time (from log) | about 13 s (prompt to answer) |

The log has no `SDK error:`, `no structured review` or `The review failed:` line, so `main()` returned `0`. Compare these five score lines with POC 2's.

---

## 6. Agentic AI concepts recap

| Concept | How this POC shows it |
|---------|-----------------------|
| **Single-pass review** | Every file in one prompt, one structured answer: the baseline architecture. |
| **Attention dilution** | Not visible at 3 files; the docstring and README explain it appears from about 10 files up. |
| **Structured per-file feedback** | `FILE_REVIEW`: `bug_count`, issues with `line`, `severity` (enum) and `description`. |
| **Interfaces for later integration** | `exports` and `uses` per file: unused here, read by POC 2's integration pass. |
| **Controlled comparison** | Same model, `REVIEWER_PROMPT`, `FILE_REVIEW` and `format_file()` in both POCs. |
| **A prompt can't fix structure** | `REVIEWER_PROMPT` already demands equal depth "from the first file to the last". |
| **Ground truth scoring** | `PLANTED`, `CROSS_FILE`, `PATTERN_FILES` and `log_scores()`. |
| **Structured output** | `output_format` → `StructuredOutput` → `structured_output`; `stop_reason` `tool_use` on success. |
| **Fresh sessions** | `run_review()`: every call starts with an empty history. |

---

## 7. Common mistakes this POC helps you avoid

1. **Judging an architecture on a toy repo.** At 3 files the single pass looks perfect; dilution shows from about 10 files.
2. **Trying to fix dilution with a stronger prompt.** This prompt already asks for equal depth; at scale it isn't enough. Change the structure.
3. **Assuming a bigger context window solves it.** The whole repo fits easily here; fitting isn't the problem, spreading attention is.
4. **Free-text reviews.** Without a schema you can't count issues per file or compare runs.
5. **Trusting `bug_count`.** A schema checks types, not agreement; count the issues yourself.
6. **Scoring line matches too tightly.** A finding can point at the function, not the exact line; size the window to what you're checking.
7. **Comparing architectures with different prompts or models.** Hold everything constant but the structure.
8. **Reading `stop_reason == "tool_use"` as unfinished.** With `output_format`, a successful run ends on the `StructuredOutput` call.

---

## 8. Claude Architect exam lens

### 8.1 What the exam tests on this topic

The objectives come from `curriculum/01-Agentic-Architecture-&-Orchestration/06-raw-Task-Decomposition-Strategies.md`. POC 1 covers objectives 1 and 2 and the single-pass side of 5 and 6; POC 2 covers 3 and 4 and the multi-pass side.

| Exam objective | What a correct answer looks like | Where this POC shows it |
|----------------|----------------------------------|-------------------------|
| 1. A review agent over a directory of 10+ source files | Reads every TS/JS file and prepares it for analysis; 10+ files is where dilution becomes observable (the exam's example: 14). | `load_repo()`, `format_file()`. This POC uses 3 files on purpose, to stay cheap and readable |
| 2. A single-pass review of all files at once | The baseline. Symptoms at scale: early files detailed, late files shallow or missing, contradictory verdicts on identical code. | `poc1_single_pass.py`; the score lines. At 3 files the symptoms don't appear |
| 5. Compare single-pass with multi-pass | The same model does better with a better structure: consistent depth, more issues, cross-file issues from the integration pass. | The five `log_scores()` lines, to compare with POC 2's |
| 6. Record contradictory pattern verdicts | Identical code flagged in one file and approved in another is the clearest dilution artifact. | The `forEach + nested find` line: `consistent` here |

> **Exam tip:** when a question describes a long review where the first files get detailed feedback and the last ones get a line each, or the same pattern is flagged once and approved later, the answer is **decomposition**: per-file passes plus a cross-file integration pass. Not a better prompt, not a bigger context window, not a bigger model.

### 8.2 The same single pass with the raw Messages API

A single pass is one `messages.create()` call with every file in the user message. Structured outputs give you the same JSON shape.

```python
import json

import anthropic

client = anthropic.Anthropic()
# MODEL_ID, REVIEWER_PROMPT, SINGLE_PASS_PROMPT, SINGLE_PASS_SCHEMA, load_repo() and format_file() are as in the POC.

files = load_repo()
prompt = SINGLE_PASS_PROMPT.format(n=len(files)) + "\n\n".join(format_file(f) for f in files)
response = client.messages.create(
    model=MODEL_ID, max_tokens=16000, system=REVIEWER_PROMPT,
    messages=[{"role": "user", "content": prompt}],
    # structured outputs: every object in the schema needs "additionalProperties": False
    output_config={"format": {"type": "json_schema", "schema": SINGLE_PASS_SCHEMA}},
)
review = json.loads(response.content[0].text)
```

| Raw Messages API (you write it) | Agent SDK (`poc1_single_pass.py`) |
|---------------------------------|-----------------------------------|
| One `messages.create()` call | One `query()` call in `run_review()` |
| `system=REVIEWER_PROMPT` | `system_prompt=REVIEWER_PROMPT` |
| `output_config` with a JSON schema; the reply text is the JSON | `output_format`; Claude calls `StructuredOutput`; read `structured_output` |
| `stop_reason` is `end_turn` | final `stop_reason` is `tool_use` (the accepted `StructuredOutput` call) |
| No tools in the request | `tools=[]` |

The architecture is the same in both: one request, one answer, the whole codebase competing for one response.

### 8.3 Scenario questions

Try each one before reading the answer. These questions were written for this article to match the curriculum objectives above. They are not official exam questions.

---

**Scenario 1: Late files get one line**

A code review agent reviews 14 files in one request. The first files get several issues with line numbers; the last few get a single generic comment each. What is the best fix?

- A. Add "review every file with the same depth" to the system prompt.
- B. Switch to a model with a larger context window.
- C. Review each file in its own pass, then run a separate integration pass for cross-file issues.
- D. Ask the model to review the files in reverse order.

**Answer: C.** This is attention dilution, an architectural problem: decompose into per-file passes plus an integration pass. A is already in many prompts (it's in this POC's) and doesn't hold at scale; B doesn't change how attention spreads; D moves the problem to other files. *POC link:* `REVIEWER_PROMPT` already says "Give every file the same depth of review, from the first file to the last"; POC 2's `multi_pass()` is the fix.

---

**Scenario 2: The same code, two verdicts**

In a single-pass review of a large repo, an inefficient loop is flagged in file 3, while an identical loop in file 11 is approved without comment. What does this most likely indicate?

- A. The two files use different coding standards.
- B. An attention dilution artifact: in one long request, later files get less scrutiny.
- C. The loop is only slow in file 3.
- D. The model was randomly sampled at high temperature.

**Answer: B.** Contradictory verdicts on identical code are the clearest symptom the exam names. *POC link:* `PATTERN_FILES` and the `forEach + nested find ... -> consistent / CONTRADICTION` line in `log_scores()`.

---

**Scenario 3: A clean pilot**

A team tests a single-pass reviewer on a 3-file sample and every planted bug is found. They plan to use it on 40-file repositories. What should the architect say?

- A. Ship it: it found every bug.
- B. The sample is too small to show attention dilution. Test at the target scale, and plan per-file passes plus an integration pass.
- C. Add more planted bugs to the 3 files.
- D. Use the same approach but split the 40 files into two requests of 20.

**Answer: B.** At 3 files the single pass does well, as this POC's real run shows; dilution appears from about 10 files. D still overloads each request and loses cross-file issues between the halves. *POC link:* the docstring ("expect a good review here: the POC shows the STRUCTURE you are going to replace") and the real scores: 3 of 3, 2 of 2.

---

**Scenario 4: Making depth measurable**

A team wants to compare two review architectures objectively. What should the test setup include?

- A. A senior engineer's opinion of each review.
- B. The same model, prompt, schema and code listing for both, plus planted defects (local, cross-file, and a duplicated pattern) scored automatically per file.
- C. Different prompts tuned for each architecture.
- D. A count of the words in each review.

**Answer: B.** Hold everything constant except the structure, and measure against ground truth. *POC link:* `build_review_options()`, `REVIEWER_PROMPT`, `FILE_REVIEW`, `format_file()` shared by both POCs; `PLANTED`, `CROSS_FILE`, `PATTERN_FILES` and `log_scores()`.

---

**Scenario 5: Structured per-file feedback**

What should each per-file review contain so results can be compared across files and runs?

- A. A paragraph of free-text comments.
- B. A bug count and, for each issue, the line number, a severity from a fixed set, and a short description, returned as schema-validated JSON.
- C. A pass/fail flag.
- D. The full corrected file.

**Answer: B.** Structure makes depth countable and line references checkable. *POC link:* `FILE_REVIEW` in `review_setup.py`: `bug_count`, and `issues` with `line`, `severity` (`critical`, `major`, `minor`) and `description`.

---

**Scenario 6: Counts that disagree**

A structured review returns `"bug_count": 3` for a file, with four entries in its `issues` list. The JSON passed schema validation. What should the scoring code do?

- A. Trust `bug_count`; it's the summary field.
- B. Count the issues itself and treat the mismatch as a data-quality signal; a schema checks types, not agreement between fields.
- C. Reject the whole review.
- D. Ask the model to recount.

**Answer: B.** Derived numbers should be computed, not trusted. *POC link:* the real run: `pricing.ts` had `bug_count: 3` and 4 issues; `log_scores()` uses `len(review.get("issues", []))` and logged `4 issue(s)`.

---

**Scenario 7: Fits in the context window**

A colleague argues: "The whole 14-file repo fits in the context window, so a single pass is fine." What is the flaw?

- A. None: if it fits, it works.
- B. Fitting in the window isn't the issue; spreading one response's attention across many files is. Detail drops for later files regardless of window size.
- C. The repo won't fit once comments are added.
- D. Context windows can't hold code.

**Answer: B.** The exam frames dilution as architectural, not a capacity limit. *POC link:* the 3-file repo here is 97 lines in one prompt, far below any window, and the README notes dilution shows from about 10 files.

---

**Scenario 8: The structured run that "didn't finish"**

A reviewer's code requires `stop_reason == "end_turn"` before reading the result. With the Agent SDK's `output_format`, every review is discarded, although `structured_output` is filled. Why?

- A. The schema is invalid.
- B. With `output_format`, Claude hands in the JSON through the `StructuredOutput` tool, so a successful run ends with `stop_reason == "tool_use"`. Check `subtype == "success"`.
- C. Reviews always need two turns.
- D. `structured_output` is only set on errors.

**Answer: B.** *POC link:* the real log: `stop_reason  tool_use  (loop result: success)`, and `run_review()` checks only `message.subtype == "success"`.

---

### 8.4 Quick-recall cheat sheet

```
single pass            → every file in ONE request; one answer for all files + cross-file issues
dilution symptoms      → early files detailed, late files shallow/missing, identical code judged differently
where it shows         → from ~10 files (exam: 14); a 3-file repo looks fine
not the fix            → a stronger prompt, a bigger context window, a bigger model, reversing the order
the fix (POC 2)        → one pass per file (full attention each) + one cross-file integration pass
per-file feedback      → bug_count + issues {line, severity (enum), description}, schema-validated
interfaces             → exports / uses per file: what the integration pass reads
fair comparison        → same model, prompt, schema, listing; planted ground truth; score per file
structured output      → output_format → StructuredOutput → structured_output; stop_reason "tool_use" = success
check derived numbers  → count issues yourself; bug_count can disagree
```

---

## 9. How to run it

```bash
cd 01-Agentic-Architecture-Orchestration/06-Task-Decomposition-Strategies
source .venv/bin/activate        # the folder's venv (claude-agent-sdk 0.2.181)
python poc1_single_pass.py       # paid: 1 call (all files), uses ANTHROPIC_API_KEY from .env
python poc2_multi_pass.py        # paid: POC 2, 3 per-file calls + 1 integration call
```

- Both scripts call the API. This folder has no free offline demo.
- `.env` needs `ANTHROPIC_API_KEY`; copy `.env.example` and fill it in. `MODEL_ID`, `MAX_TURNS` and `MAX_BUDGET_USD` fall back to `claude-sonnet-5-5`, `10` and `0.50`.
- To repeat the single pass, uncomment `"trial 2"` and `"trial 3"` in `RUNS`; each adds a paid call. To see dilution itself, `sample_repo/` would need about 10+ files of real size.
- The prompt with all the code, the structured review and the five score lines go to the console and to `logs/poc1_single_pass_<date>_<time>.log`.
- The exit code is `0` when the trials finish (a trial without a structured review is logged and skipped). It's `1` on a setup failure (including an empty `sample_repo/`) or an SDK runtime failure (`ClaudeSDKError`).
