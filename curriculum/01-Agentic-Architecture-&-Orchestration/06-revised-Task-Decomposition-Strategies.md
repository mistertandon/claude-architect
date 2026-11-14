# Task Decomposition Strategies: Revised POC Requirements (6 steps → 2 POCs, Claude Agent SDK)

> **Source:** `06-raw-Task-Decomposition-Strategies.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Agentic Architecture & Orchestration → Task Decomposition Strategies · **Build with:** Claude Agent SDK for Python (`claude_agent_sdk`)

---

## 1. Verdict: 2 POCs

The 6 raw steps are not 6 separate concepts. They are **one experiment on one code review**: steps 1–2 build the single-pass baseline, steps 3–4 build the multi-pass fix, step 5 compares the two, and step 6 runs one check on both. What you need to learn splits into the problem and its structural fix:

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: The single-pass baseline and its symptoms** | **Attention dilution, measured:** 14 files reviewed in one request and scored against planted defects show thorough early files, shallow late files, and identical code judged differently | 1, 2, 3 (format), 6 (single pass) |
| **POC 2: Per-file passes plus a cross-file integration pass** | **Structural decomposition:** one fresh pass per file with the same prompt and model, then one pass over the per-file summaries for data flow, API consistency and pattern consistency. An offline comparison shows that the fix is structural | 3, 4, 5, 6 (multi-pass) |

**What changes with the Agent SDK:** the SDK runs each review as one session: you send a prompt, and validated JSON comes back in `ResultMessage.structured_output` (`output_format`, `02-revised-Multi-Agent-Orchestration.md` C3). The decomposition is yours. Python reads the files, puts numbered code into each prompt, and decides the passes: 1 call for the single pass, and 14 per-file calls plus 1 integration call for the multi-pass, a fixed pipeline (prompt chaining). Each `query()` call starts a new session with no memory of earlier calls, so a per-file pass's context holds exactly one file: that is the "full attention budget" in SDK terms. With `tools=[]`, no pass can open another file. Claude Code adds a `StructuredOutput` tool that Claude calls to return the JSON (`run_coordinator()` leaves it out of the logs, 02 E4), and the `system:init` tool list should show it and no file tool (C5 checks this). A coordinator with the `Agent` tool (02–03) could fan per-file reviewers out too, but then Claude would decide how to split the work and could batch files; this topic needs the split to be deterministic, so Python makes it. One thing can only be observed, not coded: attention itself. The POCs measure its symptoms against planted ground truth (planted bugs found by file position, issue counts, description length, identical code judged differently). Those symptoms vary from run to run, so the single pass runs 3 trials.

- **Why not 1 POC:** POC 1 builds the measuring stick (the planted repo and its scorers, checked offline) and freezes the baseline in `single_pass.json`. If the multi-pass were built in the same POC, a surprising number could come from the repo, the scorers or the architecture, and you couldn't tell which. With the baseline fixed first, every difference in POC 2 comes from the architecture.
- **Why not 3 or more:** step 4's integration pass reads step 3's summaries and has no input without them, step 5 is an offline comparison of runs that already exist, and step 6 runs one detector on both architectures. More POCs would rebuild the repo, the runner and the scorers for one function each.

**Applies to both POCs:** Python 3.10+, `pip install claude-agent-sdk` (a recent 0.2.x; it bundles the Claude Code binary), `ANTHROPIC_API_KEY` set in the environment (never hard-coded), mock data only, and beginner-friendly code (small, commented scripts). Every Claude call goes through `run_review()` in `review_setup.py` (code below). It wraps `run_coordinator()` from `02-revised-Multi-Agent-Orchestration.md` (`coordinator.py`, already extended in `03-revised-Subagent-Invocation-and-Context-Passing.md` and extended again in POC 1's Build).

**The mock repo.** `sample_repo/` is the order service of the made-up outdoor-gear store "Fernway Outfitters": 14 TypeScript files, the size of the exam's example. Claude reviews the code in its prompt, so the made-up name only keeps the code from matching a public project. The files sorted by name, which is the review order:

| # | File | Role | Cross-file side | Repeated pattern |
|---|---|---|---|---|
| 1 | `auth.ts` | logins and sessions | X3: reads `usersByEmail` with the email as typed | — |
| 2 | `cart.ts` | adding and removing cart items | X2: calls `reserveStock()` inside `try/catch` | P2 |
| 3 | `catalog.ts` | product listing and search | — | P1 |
| 4 | `checkout.ts` | the checkout flow | X1: treats `orderTotal()` as dollars | — |
| 5 | `discounts.ts` | promo codes | — | P3 |
| 6 | `inventory.ts` | stock levels | X2: `reserveStock()` returns `false` when stock is short | — |
| 7 | `notifications.ts` | order emails | — | — |
| 8 | `orders.ts` | order records | — | — |
| 9 | `payments.ts` | card charges and refunds | — | — |
| 10 | `pricing.ts` | totals and tax | X1: `orderTotal()` returns integer cents | — |
| 11 | `reports.ts` | sales reports | — | P1 |
| 12 | `reviews.ts` | product reviews | — | P2 |
| 13 | `shipping.ts` | shipping quotes | — | P3 |
| 14 | `users.ts` | user accounts | X3: keys `usersByEmail` by the trimmed, lowercased email | — |

**Planted local bugs.** Every file has exactly 2, and files k and k + 7 share the same 2 kinds. The early half (#1–7) and the late half (#8–14) therefore hold the same 14 kinds, and only their position differs (28 bugs in all):

| Files (k and k + 7) | First kind (example) | Second kind (example) |
|---|---|---|
| `auth.ts`, `orders.ts` | `off_by_one`: `i <= list.length` as a loop bound | `missing_await`: `if (isLocked(user))` where `isLocked` is `async`, so the Promise is always truthy |
| `cart.ts`, `payments.ts` | `unchecked_find`: a `find()` result used without an `undefined` check | `boundary`: the doc comment says "or more", but the code uses `>` |
| `catalog.ts`, `pricing.ts` | `sort_no_comparator`: `values.sort()` on numbers, which sorts them as strings | `mutates_input`: documented as returning a copy, but changes its argument |
| `checkout.ts`, `reports.ts` | `assign_in_condition`: `if (order.status = "paid")` | `month_zero_based`: `getMonth()` used as a month from 1 to 12 |
| `discounts.ts`, `reviews.ts` | `nan_unchecked`: a `parseInt(value, 10)` result used without a `Number.isNaN` check | `sql_concat`: user input concatenated into an SQL string |
| `inventory.ts`, `shipping.ts` | `float_equality`: `===` between computed decimal amounts | `unbounded_retry`: a retry loop with no attempt limit |
| `notifications.ts`, `users.ts` | `secret_logged`: a password or API key written to a log | `unanchored_regex`: a validation regex without `^` and `$` |

**Cross-file mismatches.** Each side looks correct on its own, and neither file states the other's rule:
- **X1** (`data_flow`): `pricing.ts` exports `orderTotal(items)`, documented as returning integer cents. `checkout.ts` treats its result as dollars: it formats it with `$` and `toFixed(2)` and passes it on as `amountDollars`.
- **X2** (`api_consistency`): `inventory.ts` exports `reserveStock(sku, qty)`, which returns `false` when stock is short and never throws. `cart.ts` calls it inside `try/catch`, expecting a throw, and ignores the returned boolean.
- **X3** (`pattern_consistency`): `users.ts` keys `usersByEmail` by the trimmed, lowercased email. `auth.ts` reads it with the email exactly as the user typed it.

**Repeated patterns.** Each snippet appears byte for byte, with the same indentation, in an early file and a late file, inside code where it is the only problem:
- **P1** `forEach` with a nested `find`, an O(n × m) lookup (the exam's example), in `catalog.ts` (#3) and `reports.ts` (#11):
  ```ts
    rows.forEach((row) => {
      const match = lookup.find((entry) => entry.id === row.id);
      if (match) names.push(match.name);
    });
  ```
- **P2** independent requests awaited one at a time, in `cart.ts` (#2) and `reviews.ts` (#12):
  ```ts
    for (const id of ids) {
      results.push(await fetchById(id));
    }
  ```
- **P3** an error logged and then swallowed, in `discounts.ts` (#5) and `shipping.ts` (#13):
  ```ts
    } catch (err) {
      console.log(err);
      return null;
    }
  ```

**Rules for the mock files:**
- 14 `.ts` files directly in `sample_repo/`, each 80–120 lines of plausible TypeScript (it is never compiled or run) that imports from the others with `./<module>`.
- Only the defects above: 2 local bugs per file, X1–X3 and P1–P3. Every other cross-module call agrees on units, return values and error handling, and no comment hints at a defect (no `// BUG`, `// TODO` or `// FIXME`).
- In each file, every marked line (a planted bug or one side of an X) and every snippet is at least 6 lines from the others, so one issue can match only one of them (E2).

Every review call gets its options and its runner from `review_setup.py`:

```python
MODEL = "claude-opus-5-5"

REVIEWER_PROMPT = (
    "You are a senior TypeScript reviewer for the Fernway Outfitters order service. Find real defects: logic errors, "
    "unhandled edge cases, security problems and performance problems. Give every file the same depth of review, "
    "from the first file to the last. For each issue, give the exact line number from the numbered listing, a "
    "severity (critical, major or minor) and a one-sentence description, and set bug_count to the number of issues. "
    "For each file, also record its interface for later cross-file checks: exports (each export's signature, units "
    "and error behavior), uses (each call into another module: what it passes and what it assumes about the result) "
    "and conventions (units, rounding, timestamps, text normalization and error handling)."
)

def build_review_options(schema):
    return ClaudeAgentOptions(
        model=MODEL,                                              # one model for every pass (C11)
        system_prompt=REVIEWER_PROMPT,                            # one reviewer prompt for every pass, with the equal-depth rule (C7)
        output_format={"type": "json_schema", "schema": schema},  # validated JSON in ResultMessage.structured_output (C6)
        tools=[],                                                 # no built-in tools: the code is in the prompt, and no pass can open another file
        setting_sources=[],                                       # ignore ~/.claude and project settings, CLAUDE.md and hooks
        env={"ENABLE_TOOL_SEARCH": "false"},                      # no ToolSearch calls
        max_turns=10,                                             # safety cap (01 C16); a review needs only a few turns
    )

async def run_review(prompt, schema):
    # One call = one new session with an empty history. run_coordinator() is 02's runner, extended in POC 1.
    result = await run_coordinator(prompt, schema, options=build_review_options(schema))
    return {key: result[key] for key in ("output", "models", "prompt_tokens", "init_tools")}
```

---

## 2. Concepts and POC requirements

All 13 concepts in the raw file (C1–C13) are covered: all 13 are new or build on earlier POCs and are taught below, none is a terminal command, and none was already covered by an earlier revised file (see the end of this section).
Previous revised files checked: `01-revised-Agentic-Loops.md`, `02-revised-Multi-Agent-Orchestration.md`, `03-revised-Subagent-Invocation-and-Context-Passing.md`, `04-revised-Workflow-Enforcement-and-Handoff.md`, `05-revised-Agent-SDK-Hooks.md` (`06-revised-Task-Decomposition-Strategies.md` is still empty).
Raw step → concepts: **1** → C1–C2 · **2** → C3–C4 · **3** → C5–C7 · **4** → C8–C9 · **5** → C10–C11 · **6** → C12–C13.
Rows marked **E** are extras that are not in the raw file. Without them, the POC breaks or gives misleading results.

### POC 1: The single-pass baseline and its symptoms

**Build:** five pieces of code and data.

- **`sample_repo/`:** the 14 mock files described above.
- **`review_setup.py`:** `REPO_DIR = "sample_repo"`, `MIN_FILES = 10`, `SOURCE_EXTENSIONS`, `load_repo()`, `format_file()`, `MODEL`, `REVIEWER_PROMPT`, the three task prompts (`SINGLE_PASS_PROMPT`, plus `FILE_PROMPT` and `INTEGRATION_PROMPT` for POC 2), the schemas (C6), `build_review_options()` and `run_review()` (code above). `python review_setup.py` runs an offline self-check.
- **`review_metrics.py`:** the ground truth (`BUG_KINDS`, `PLANTED`, `CROSS_FILE`, `REPEATED`) and the scorers: `locate()`, `snippet_lines()`, `planted_found()`, `depth_row()`, `halves()`, `validate_review()`, `pattern_flags()`, `contradictions()`, `cross_file_found()`, `split_batches()` and `pairs_in_one_batch()`. `python review_metrics.py` runs an offline self-check: first the ground truth against the repo, then each scorer on hand-built reviews.
- **An extension to `run_coordinator()` in `coordinator.py`** from `02-revised-Multi-Agent-Orchestration.md` (already extended in `03-revised-Subagent-Invocation-and-Context-Passing.md`). Add these without breaking 02's or 03's behavior:
  - `models`: the distinct `AssistantMessage.model` values of the top-level messages (`parent_tool_use_id is None`), sorted;
  - `prompt_tokens`: `input_tokens + cache_creation_input_tokens + cache_read_input_tokens` from the `usage` of the first top-level `AssistantMessage` (or `None` if it has no `usage`). That is the size of the request that holds the whole prompt. Per-step input counts are exact, but per-step output counts are placeholders, so don't use those;
  - a `ValueError` when a schema was given and a `success` result has `structured_output is None`: the docs say to treat that result as a failure.

  02's and 03's scripts must still run unchanged.
- **`poc1_single_pass.py`:** `async def single_pass(files)` and a `__main__` block that runs it `TRIALS = 3` times, prints the C4 and C12 tables, and writes `single_pass.json`, the fixed baseline for POC 2.

No per-file passes and no integration pass here: those are POC 2.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C1 | A code review agent whose function accepts a directory path, reads every TypeScript or JavaScript source file in it (at least 10) and prepares them for analysis (**New**) | `load_repo(path=REPO_DIR)` reads every file directly in `path` whose extension is in `SOURCE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")`, sorted by name: that is the review order. It returns one `{"index", "name", "text", "lines"}` per file (`index` counts from 1) and raises `ValueError` when it finds fewer than `MIN_FILES = 10`. `format_file(f)` prepares one file: a header `=== <name> (<lines> lines) ===`, then each line as `f"{i:>4} \| {line}"` (E1). The review passes themselves are C3 here and C5 in POC 2 | `python review_setup.py` (offline) prints the 14 names in order, from `auth.ts` to `users.ts`, with their line counts, and the first 3 lines of `format_file()` for `auth.ts`. A temporary folder holding only 9 of the files raises `ValueError` |
| E1 | Both architectures see the same numbered listing | Code enters a prompt only through `format_file()`: the same header and line numbers in the single pass and in every per-file pass, and no position such as "file 3 of 14". Without line numbers, the single pass would have to count lines through more than 1,000 lines of code, so a wrong line in a late file could come from counting rather than attention, and E2 would score it as a miss | Code review: `format_file()` is the only place where code is put into a prompt, in both POCs |
| C2 | The 10+ file threshold is where attention dilution becomes observable: the exam's 14-file example, where detailed feedback for early files degrades to superficial analysis for later files, so the setup must replicate this scale (**New**) | Build `sample_repo/` exactly as described above: 14 files, each 80–120 lines. `MIN_FILES` keeps every review at or above the threshold | The `review_metrics.py` self-check prints `14 files, <N> lines` with N ≥ 1,120 (14 × 80) |
| E2 | Planted ground truth, so depth and consistency can be measured | In `review_metrics.py`: `BUG_KINDS` (the 14 kinds above), `PLANTED` (28 entries `{"id", "file", "kind", "contains"}`, `B01`–`B28`, two per file in review order), `CROSS_FILE` (X1–X3, each with its `kind`, its two files and a `contains` per file) and `REPEATED` (P1–P3, each with its two files and its snippet). `contains` is a substring that appears on exactly one line of its file, so `locate(text, contains)` finds the line and no line number is hard-coded: clean code added later keeps the ground truth valid. `snippet_lines(text, snippet)` returns the snippet's first and last line. `planted_found(review, f)` returns the ids of `f`'s planted bugs that some issue matches; an issue matches when `abs(issue["line"] - planted_line) <= 2`. Without ground truth, depth could only be judged by issue and word counts, which reward verbosity, and identical-code verdicts couldn't be found | Self-check: every `contains` is on exactly 1 line; every file has 2 `PLANTED` entries; files k and k + 7 have the same 2 kinds; each snippet occurs exactly once in each of its 2 files; marked lines and snippets in one file are at least 6 lines apart. On hand-built reviews, issues on `auth.ts`'s 2 planted lines give 2 matches; an issue 2 lines off still matches, and one 3 lines off doesn't |
| C6 | Structured per-file feedback: bug count, severity ratings and specific line references (**Builds on** `02-revised-Multi-Agent-Orchestration.md` C3 and `03-revised-Subagent-Invocation-and-Context-Passing.md` C8) | In `review_setup.py`, `FILE_REVIEW` is an object whose keys are all required: `file` and `summary` (strings), `bug_count` (integer), `issues` (an array of objects, each requiring `line` (integer), `severity` (enum `critical`, `major`, `minor`) and `description` (string)), and three interface lists for POC 2's integration pass, `exports`, `uses` and `conventions` (arrays of strings). `CROSS_FILE_ISSUE` requires `files` (array of strings), `kind` (enum `data_flow`, `api_consistency`, `pattern_consistency`), `severity` and `description`. `SINGLE_PASS_SCHEMA` requires `files` (array of `FILE_REVIEW`) and `cross_file_issues` (array of `CROSS_FILE_ISSUE`); `FILE_REVIEW_SCHEMA` is one `FILE_REVIEW`; `INTEGRATION_SCHEMA` requires `cross_file_issues`. Use only types, `enum` and `required`, which structured outputs support; range rules such as "line ≥ 1" are checked in Python. `validate_review(review, f)` returns a list of errors: a `file` whose base name differs from `f["name"]`, `bug_count != len(issues)`, or a `line` outside 1 to `f["lines"]`. New compared with 02 C3 and 03 C8: one item schema serves both architectures, because the single pass returns 14 of the same items, so differences in POC 2 come from the architecture, not from the output format | Self-check: a valid hand-built review gives `[]`, `bug_count` 3 with 2 issues gives a `bug_count` error, and `line` 999 gives a line error |
| C3 | A single-pass review that processes all files at once, with its results recorded: the baseline that shows attention dilution (**New**) | `single_pass(files)` makes one `run_review()` call with `SINGLE_PASS_SCHEMA` and `SINGLE_PASS_PROMPT`: `f"Review all {len(files)} files of this codebase in one pass. Return one review per file, in the order given, then every cross-file issue: data flow between modules, inconsistent API usage, and patterns used differently across files. Name every file each cross-file issue involves.\n\n"` followed by every `format_file(f)` in review order, separated by blank lines. It keys `output["files"]` by lowercased base name. A file with no review gets an empty one (`issues == []`, marked `missing`), which counts as missing feedback. The `__main__` block runs `TRIALS = 3`, because attention effects vary from run to run, and writes `single_pass.json`: per trial, `reviews` (by file name), `cross_file_issues`, `contradictions` (C12), `models`, `prompt_tokens` and `init_tools` | Each trial is one `query()` call that ends with `success`, and its log shows no tool call (`run_coordinator()` skips the `StructuredOutput` call, 02 E4). `single_pass.json` holds 3 trials, each with an entry for all 14 files |
| C4 | The attention dilution symptoms the exam expects you to recognize: thorough analysis with line references and bug identification for early files, increasingly brief or missing feedback for later files, and contradictory pattern evaluation (C12) (**New**) | For each trial, print the depth table, one row per file in review order: `#`, file, `issues`, `found` (`len(planted_found())`, of 2), `words` (mean words per issue description, from `depth_row()`) and any `validate_review()` errors. Then print `halves()`: files #1–7 against #8–14, each with `found` (of 14), `issues` and `words`. Both halves hold the same 7 bug kinds (files k and k + 7), so a gap between them comes from position, not difficulty | Typically each trial shows a drop-off: late `found` below early `found`, fewer and shorter issues toward #14, and some late files with no issues at all. Trials differ. If no trial shows a gap, the model is holding up at this size: lengthen every file with more clean code (the `contains` markers keep the ground truth valid) and rerun |
| C12 | Contradictory pattern evaluation, the clearest symptom of attention dilution: the single pass flags a pattern in one file but approves identical code in another (the exam's forEach example: flagged as inefficient in File 3, approved without comment in File 11) (**New**) | `pattern_flags(reviews, files)` marks a `REPEATED` pattern as flagged in a file when any issue there has a line within the snippet's lines, ±1. `contradictions(flags)` returns each pattern that is flagged in exactly one of its two files. For each trial, print one line per pattern, such as `P1 forEach + nested find: catalog.ts (#3) flagged · reports.ts (#11) approved -> CONTRADICTION`, and save the contradictions in `single_pass.json` | Self-check: hand-built reviews that flag P1 only in `catalog.ts` give 1 contradiction, and reviews that flag it in both files give 0. Live: typically at least 1 contradiction across the 3 trials, usually with the later file approved, as in the exam's example. If none appears, run up to 3 more trials before you record that none was found |

### POC 2: Per-file passes plus a cross-file integration pass

**Build:** two scripts, reusing `review_setup.py`, `review_metrics.py` and the extended `run_coordinator()`.

- **`poc2_multi_pass.py`** defines `async def review_file(f, n)`, `def file_summaries(reviews)`, `async def integration_pass(reviews)` and `async def multi_pass(files)`. `multi_pass()` returns `{"reviews", "cross_file_issues", "calls"}`, where `calls` has one `{"name", "models", "prompt_tokens", "init_tools"}` per `query()` call (15 in all: 14 files plus the integration pass), and writes it to `multi_pass.json`. The script prints the same depth table and `halves()` as POC 1, then the integration findings.
- **`poc2_compare.py`** makes no API calls. It loads `single_pass.json` and `multi_pass.json` and prints, in order: the cross-file findings per layer and the batching check (C9), the comparison tables (C10), the pattern verdicts (C13), the prompt and request-size facts (C7), and the same-model check (C11).

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C5 | Per-file local analysis passes that give each file the full attention budget: the first layer of multi-pass architecture (**New**) | `review_file(f, n)` makes one `run_review()` call with `FILE_REVIEW_SCHEMA` and `FILE_PROMPT`: `f"Review this one file from a {n}-file codebase. You can see only this file.\n\n{format_file(f)}"`. Each call starts a new session with an empty history, so its context holds one file instead of 14: the isolation of `02-revised-Multi-Agent-Orchestration.md` C10, used here on purpose. `multi_pass(files)` calls it once per file, in review order, in a plain `for` loop (the passes are independent, so `asyncio.gather` would also work, `03-revised-Subagent-Invocation-and-Context-Passing.md` C16). It then prints the depth table and `halves()` exactly as POC 1 does | 14 calls, each `success`, and each `init_tools` lists `StructuredOutput` and no file tool such as `Read`, `Glob` or `Grep`. The two halves are typically within 2 `found` of each other, and the last file, `users.ts`, gets about as many issues and words as the first, `auth.ts`. No pass knows its position, so position can't change its depth |
| C6 (per file) | Each pass returns its file's structured review | Run `validate_review()` on each review and print any errors next to its row | Typically `[]` for all 14 files: every `bug_count` equals its issue count, and every `line` exists in its file |
| C8 | A cross-file integration pass: a separate analysis that takes the per-file summaries and checks data flow between modules, API consistency and pattern usage consistency (**New**) | `file_summaries(reviews)` keeps only `file`, `summary`, `exports`, `uses` and `conventions` from each review: no code and no local issues. `integration_pass(reviews)` makes one `run_review()` call with `INTEGRATION_SCHEMA` and `INTEGRATION_PROMPT`: `"These are the per-file summaries of one TypeScript codebase; the code itself is not included. Find cross-file issues only: data flow problems between modules, inconsistent API usage (a caller's assumptions that contradict the callee's contract), and patterns or conventions used differently across files. Name every file each issue involves. Do not repeat single-file issues.\n\n"` followed by `json.dumps(file_summaries(reviews), indent=2)`. Print each issue with its `kind` and `files`, then `cross_file_found()` | Typically `{"X1", "X2", "X3"}`: X1 names `pricing.ts` and `checkout.ts`, X2 names `inventory.ts` and `cart.ts`, and X3 names `users.ts` and `auth.ts`. The `kind` may differ; the two files decide the match. Its `prompt_tokens` (printed in C7) is smaller than the single pass's, because it never sees code. If an X is missing, read the two per-file summaries first: the integration pass knows only what they say (`03-revised-Subagent-Invocation-and-Context-Passing.md` C11) |
| C9 | Per-file passes catch local issues but miss cross-cutting concerns: batching without an integration pass still misses data flow issues and pattern inconsistencies across files, which the exam tests (**New**) | In `poc2_compare.py`, score a `per-file only` layer: the 14 per-file reviews without the integration pass. A per-file review names only its own file, so this layer can't report a two-file issue, and its cross-file score is 0 by construction. Then print `split_batches(files, BATCH_SIZE)` with `BATCH_SIZE = 4`, and `pairs_in_one_batch(files, BATCH_SIZE)`: the X ids whose two files share a batch | `per-file only`: 0 of 3. The batches are `#1–4`, `#5–8`, `#9–12` and `#13–14`, and `pairs_in_one_batch()` returns `[]` (X1 is in batches 1 and 3, X2 in 1 and 2, X3 in 1 and 4): a batched review without the integration pass couldn't see both sides of any planted mismatch |
| C10 | Compare results: which issues the single pass caught against the multi-pass approach, with special attention to consistent analysis depth across all files (**New**) | `poc2_compare.py` prints one table. Rows: `single-pass 1`, `single-pass 2`, `single-pass 3`, `per-file only` and `multi-pass` (per-file + integration). Columns: `issues` (every reported issue, local plus cross-file), `found` (planted bugs, of 28), `early` and `late` (of 14 each), `cross-file` (of 3) and `contradictions` (of 3). Then a per-position table: `#`, file, the issue count in each single-pass trial, and the multi-pass count. Then `caught only by the integration pass`: the X ids that `multi-pass` found and no single-pass trial found | Typically `multi-pass` has more `issues` and a higher `found` than every single-pass trial, its `early` and `late` are close while each single-pass `late` is lower, and its per-position counts show no drop-off toward #14. `per-file only` has 0 cross-file issues, and `multi-pass` typically 3. The "caught only by the integration pass" list is typically non-empty. The single pass saw both files of every pair, so it can catch an X too; that X is then left out of the list |
| C13 | The multi-pass review treats the same pattern consistently (**New**) | Run `pattern_flags()` and `contradictions()` on the multi-pass reviews, and print one line per pattern in the same format as POC 1, next to each single-pass trial's verdicts | 0 contradictions, and typically every pattern flagged in both of its files, such as P1 in `catalog.ts` and `reports.ts`: each copy of the identical code got a full-attention pass with the same prompt |
| C7 | Structural decomposition solves attention dilution, not better prompts or larger context windows (**New**) | Assert that `REVIEWER_PROMPT` contains `"Give every file the same depth of review"`: the single pass already had the "better prompt". Print each single-pass trial's `prompt_tokens`, the mean `prompt_tokens` of the 14 per-file passes and the integration pass's `prompt_tokens`, then the line `Same prompt, every file inside one request: only the structure changed` | The assert passes. Every single-pass trial ended with `success` with all 14 files in its first request, so nothing was cut off, and a larger context window would change nothing. Typically the depth gap of POC 1 appeared anyway, while the per-file passes, with the same prompt, show none (C5) |
| C11 | Attention dilution is an architectural problem, not a model capability problem: the same model produces better results with a multi-pass architecture, which proves the fix is structural (**New**) | Assert that every call in both JSON files reports the same single model in `models`, and that it starts with `MODEL`. Both POCs reach Claude only through `run_review()`, so they share `REVIEWER_PROMPT` and the `FILE_REVIEW` item schema (code review). Print `Same model (<id>), same prompt, same schema: the multi-pass gain is structural` | The asserts pass, and the C10 table shows the gain. The exam's fix for attention dilution is to restructure the review (per-file passes plus an integration pass), not to choose a bigger model |

### Terminal commands (for the later tutorial)

None: every concept in this topic is a programming concept.

### Already covered by earlier POCs

None: every concept in this topic is new or builds on an earlier POC (cited in its row).
