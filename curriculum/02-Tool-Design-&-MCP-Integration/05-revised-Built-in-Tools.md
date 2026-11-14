# Built-in Tools: Revised POC Requirements (5 steps → 2 POCs, Claude Agent SDK)

> **Source:** `05-raw-Built-in-Tools.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Tool Design & MCP Integration → Built-in Tools · **Build with:** Claude Agent SDK for Python (`claude_agent_sdk`)

---

## 1. Verdict: 2 POCs

The 5 raw steps are not 5 separate concepts. They are **one refactoring task**, migrating every caller of a deprecated function, done in two halves. Steps 1–3 investigate without changing anything: Grep finds the callers, Glob finds their tests, and Read examines only the files Grep found. Steps 4–5 change files: Edit replaces each call, and step 5 handles Edit's one failure mode. What you need to learn splits into reading and writing:

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: Find before you read** | **Content versus path, then incremental reading:** `Grep` searches file contents for the callers, `Glob` matches file paths for their tests, and `Read` opens only the files Grep pointed at. A run with only `Glob` and `Read` shows the alternative: no way to search contents, so Claude has to read every file | 1, 2, 3 |
| **POC 2: Edit first** | **Targeted changes and their one failure:** `Edit` replaces exact text and sends a fraction of the file, where `Read` + `Write` sends all of it. A non-unique `old_string` fails safely; widening it changes exactly one occurrence, and `replace_all` changes every occurrence at once | 4, 5 |

**What changes with the Agent SDK:** `Grep`, `Glob`, `Read`, `Edit` and `Write` are Claude Code's built-in tools. The SDK runs them for you: Claude asks for one, Claude Code executes it on the files in the session's `cwd`, and the result comes back as a `ToolResultBlock`. You can't call them from code, so every POC sets up a repository, gives Claude a task, and checks two things: which tools Claude called, in what order and with what input (from the stream), and what changed on disk (from Python, against ground truth computed from the files). One platform detail decides the setup. On Linux, macOS and WSL, Claude Code leaves `Glob` and `Grep` out of the default tool set and searches with `grep` and `find` through `Bash` instead. Naming them in `tools` brings them back, and leaving `Bash` out keeps every search on the dedicated tools (E1). One thing can only be observed, not coded: the wording of Claude Code's tool results, such as Edit's non-unique error. The checks rely on `is_error` and on the files, not on that text.

- **Why not 1 POC:** POC 1 never changes a file, so its runs can be compared with each other, and its ground truth (6 call sites in 4 files) is what POC 2's edits are checked against. POC 2 changes files, and each of its runs needs its own fresh copy. If the two halves were mixed, a wrong edit could come from a wrong search, and you couldn't tell which.
- **Why not 3 or more:** step 2 only uses step 1's results (the caller names), and step 3 only reads the files that step 1 found. Step 5 is what happens when step 4's tool meets a repeated line, so it needs step 4's setup.

**Applies to both POCs:** Python 3.10+, `pip install claude-agent-sdk` (a recent 0.2.x; it bundles the Claude Code binary), `ANTHROPIC_API_KEY` set in the environment (never hard-coded), mock data only, and beginner-friendly code (small, commented scripts). Every run goes through `run_agent()` from `01-revised-Agentic-Loops.md` (`poc2_agent_loop.py`), as extended in `05-revised-Agent-SDK-Hooks.md` (`options=`, `tool_results`), and its `tool_results` give each call's name, input and result.

**The mock repo `legacy_repo/`** is a TypeScript service for Lumen Home, the made-up store of `01-revised-Tool-Interface-Design.md`. It has 16 files and is never compiled or run. Its deprecated function is `processLegacyOrder(orderId)`; the new API is `processOrder(orderId, { validate: true })`.

| # | File | Role | `processLegacyOrder` in it |
|---|---|---|---|
| 1 | `src/legacy/orders.ts` | defines the deprecated function | its definition, `export async function processLegacyOrder(orderId: string)` |
| 2 | `src/legacy/index.ts` | the wrapper module | a re-export, `export { processLegacyOrder } from "./orders";` |
| 3 | `src/orders/processOrder.ts` | the new API, `processOrder(orderId, options)` | none |
| 4 | `src/OrderProcessor.ts` | caller: imports from `./legacy/orders`, ignores the return value | line 42: `  await processLegacyOrder(orderId);` |
| 5 | `src/RefundHandler.ts` | caller: imports from `./legacy/orders`, uses the return value | `  const receipt = await processLegacyOrder(orderId);`, then `return receipt.status === "ok";` |
| 6 | `src/BulkImporter.ts` | caller: imports through the wrapper, `from "./legacy"`, with a different argument | `    results.push(await processLegacyOrder(row.orderId));` |
| 7 | `src/RetryQueue.ts` | caller: the same line in 3 functions | `  await processLegacyOrder(orderId);` in `retryFailedOrder()`, `replayOrder()` and `resumeOrder()`, preceded by `  logRetry(orderId);`, `  markReplayed(orderId);` and `  clearHold(orderId);` |
| 8–11 | `src/Inventory.ts`, `src/Shipping.ts`, `src/Customers.ts`, `src/components/OrderSummary.tsx` | unrelated code | none |
| 12–15 | `src/OrderProcessor.test.tsx`, `src/RefundHandler.test.tsx`, `src/BulkImporter.test.tsx`, `src/RetryQueue.test.tsx` | the callers' tests | none: the tests exercise their caller, so a search for the function name can't find them |
| 16 | `src/components/OrderSummary.test.tsx` | a test of unrelated code | none |

**Rules for the mock files:**
- Files 4–7 are 50–70 lines and at least 1,500 characters each. The other files are 20–60 lines.
- The 3 lines in `RetryQueue.ts` are byte-for-byte identical, including the 2-space indentation, so an Edit of that line alone matches 3 places.
- No comment mentions `processLegacyOrder`, so every match is real code.

**Ground truth**, computed by Python in `builtin_setup.py` and never hard-coded:
- `CALL_SITES`: every line matching `processLegacyOrder\(` except the definition. That is 6 sites in 4 files (files 4–7), with `OrderProcessor.ts` at line 42.
- `CALLERS`: the 4 files of `CALL_SITES`.
- `GREP_FILES`: every file that contains the name at all, so `CALLERS` plus files 1 and 2, 6 files in total.
- `TESTS`: `<caller stem>.test.tsx` next to each caller, 4 files.
- `UNRELATED`: files 3 and 8–11. File 3 is the new API, which no step needs to read.

Every run gets its options from `builtin_setup.py`:

```python
REPO_DIR = Path(__file__).resolve().parent / "legacy_repo"
SEARCH_TOOLS = ["Grep", "Glob", "Read"]
EDIT_TOOLS = SEARCH_TOOLS + ["Edit", "Write"]
SYSTEM_PROMPT = ("You are a careful TypeScript maintainer working in the repository in your working directory. "
                 "Look things up with your tools; never guess a file name, a line number or a call.")

def fresh_copy(run_name):
    # Each run gets its own copy, so edits never leak into the next run (E2)
    target = REPO_DIR.parent / "work" / run_name
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(REPO_DIR, target)
    return target

def build_builtin_options(workdir, tools):
    return ClaudeAgentOptions(
        model="claude-opus-5-5",
        system_prompt=SYSTEM_PROMPT,
        cwd=str(workdir),                 # the fresh copy: Claude Code's tools work on these files
        tools=tools,                      # only these built-ins; naming Grep and Glob brings them back on Linux and macOS (E1)
        allowed_tools=tools,              # Edit and Write need approval: pre-approve them, so no run waits on a prompt
        setting_sources=[],               # ignore ~/.claude and project settings, CLAUDE.md and hooks
        max_turns=30,                     # safety cap (01 C16); a migration needs about 15 turns
    )
```

---

## 2. Concepts and POC requirements

All 14 concepts in the raw file (C1–C14) are covered: all 14 are new and are taught below, none is a terminal command, and none was already covered by an earlier revised file (see the end of this section).
Previous revised files checked: `01-revised-Agentic-Loops.md`, `02-revised-Multi-Agent-Orchestration.md`, `03-revised-Subagent-Invocation-and-Context-Passing.md`, `04-revised-Workflow-Enforcement-and-Handoff.md`, `05-revised-Agent-SDK-Hooks.md`, `06-revised-Task-Decomposition-Strategies.md`, `01-revised-Tool-Interface-Design.md`, `02-revised-Structured-Error-Responses.md`, `03-revised-Tool-Distribution-&-Tool-Choice.md`, `04-revised-MCP-Server-Integration.md`. None of them used Claude Code's file tools: `06-revised-Task-Decomposition-Strategies.md` C5 only checked that its passes had none.
Raw step → concepts: **1** → C1–C3 · **2** → C4–C6 · **3** → C7–C8 · **4** → C9–C10 · **5** → C11–C14.
Rows marked **E** are extras that are not in the raw file. Without them, the POC breaks or gives misleading results.

### POC 1: Find before you read

**Build:**
- **`legacy_repo/`:** the 16 files above.
- **`builtin_setup.py`:** `REPO_DIR`, `SEARCH_TOOLS`, `EDIT_TOOLS`, `SYSTEM_PROMPT`, `fresh_copy()` and `build_builtin_options()` (code above). It also defines the ground truth (`CALL_SITES`, `CALLERS`, `GREP_FILES`, `TESTS` and `UNRELATED`) and `chars_read(tool_results, workdir)`, which sums the size of each distinct file that `Read` returned. POC 2 reuses it. `python builtin_setup.py` runs an offline self-check that makes no API calls.
- **`poc1_find_then_read.py`:** two runs, each on its own fresh copy, with `INVESTIGATE_PROMPT`.

`INVESTIGATE_PROMPT = "In this repository: 1) find every call site of processLegacyOrder and list each one as path:line: code; 2) find the test file of each file that calls it; 3) for each calling file, explain how it calls processLegacyOrder: the argument, how the return value is used, and whether the function is imported directly or through a wrapper module."`

| Run | `tools` |
|---|---|
| `grep-glob-read` | `SEARCH_TOOLS` |
| `glob-only` | `["Glob", "Read"]` |

For each run, print every tool call in order: the name and the key input (`pattern`, `output_mode`, `glob` or `file_path`). Then print the number of Read calls, `chars_read()` and the answer.

No file changes here: editing is POC 2.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| E1 | Name `Grep` and `Glob` in `tools`, and leave `Bash` out | On Linux, macOS and WSL, Claude Code leaves `Glob` and `Grep` out of the default tool set, and Claude searches with `grep` and `find` through `Bash` instead. A run with the defaults would show `Bash` calls, not the tools this topic is about. `tools=SEARCH_TOOLS` makes exactly those tools available, and without `Bash`, every search goes through them | No run makes a `Bash` call. The `grep-glob-read` run's tool calls include `Grep` and `Glob` |
| E2 | Every run works on a fresh copy of the repo | `fresh_copy(run_name)` copies `legacy_repo/` to `work/<run_name>/`, and the run's `cwd` is that copy. POC 2 changes files, and each run must start from the same 16 files. The checks read the copy, never the original | After all runs, `legacy_repo/` is unchanged: its 6 call sites are still there |
| E3 | Ground truth computed from the files | The self-check prints `CALL_SITES`, `CALLERS`, `GREP_FILES`, `TESTS` and `UNRELATED`, computed by regular expressions and file-name rules (above). Every acceptance check compares Claude's calls and the files on disk with these sets, never with Claude's own report | The self-check prints 6 call sites in 4 files, including `src/OrderProcessor.ts:42`; 6 `GREP_FILES`; 4 `TESTS`; and 5 `UNRELATED` files |
| C1 | Use Grep to search the codebase for every caller of a target function, `processLegacyOrder` (**New**) | Run `grep-glob-read` | The first search call is `Grep`, with a `pattern` that contains `processLegacyOrder`. No `Read` call comes before it |
| C3 | Grep's output for this task: file paths with line numbers and the matching lines, the exact call sites, such as `src/OrderProcessor.ts:42: await processLegacyOrder(orderId)` (**New**) | Print each Grep call's `output_mode` and the first lines of its result. Grep's default mode, `files_with_matches`, returns paths only; `content` returns `path:line:text`, the exact call sites | Typically one Grep call uses `output_mode: "content"`, and its result contains `src/OrderProcessor.ts:42:` followed by the call. The answer lists the 6 `CALL_SITES` in the 4 `CALLERS`, typically all 6 |
| C2 | Grep searches file contents, so it is the right tool for finding callers; Glob would fail, because it matches file paths, not contents. The exam penalises confusing the two (**New**) | The self-check runs `Path(workdir).glob("**/*processLegacyOrder*")` next to a Python content search of every file. Then run `glob-only`, where Claude has `Glob` and `Read` but no `Grep` | Self-check: the path glob returns `[]`, because no file is named after the function, while the content search finds the 6 call sites. `glob-only`: Claude can't search contents, so it typically lists the files with `Glob` and reads them one by one. Typically at least 11 Read calls (every non-test file) |
| C4 | Use Glob to find the test files that match the caller file names, such as `**/*.test.tsx` (**New**) | Same `grep-glob-read` run. Print each Glob call's `pattern` and its result | At least one `Glob` call, with a pattern such as `**/*.test.tsx` or a caller-specific one such as `**/RetryQueue.test.tsx`. Its result includes the 4 `TESTS` |
| C5 | Glob matches file paths by naming pattern, so it is the right tool for finding test files by extension or naming convention (**New**) | Note in a code comment that the 4 `TESTS` don't contain `processLegacyOrder` (repo rules above), so no content search can find them: only their names connect them to the callers | Self-check: a content search for `processLegacyOrder` returns 0 of the 4 `TESTS`, and the path pattern `**/*.test.tsx` returns all 5 test files |
| C6 | The Grep-then-Glob pattern: a content search finds the callers, then path matching finds their tests (**New**) | Print the order of the first `Grep` and the first `Glob`, and compare the test files in the answer with `TESTS` | The first `Grep` comes before the first `Glob`. The answer names the 4 `TESTS` and not `src/components/OrderSummary.test.tsx`, whose source file is not a caller |
| C7 | Use Read on each caller file to understand how it uses the function: the argument, how the return value is used, and whether the function is imported directly or through a wrapper module (**New**) | Print the `file_path` of every `Read` call, and the answer's part 3 | Each of the 4 `CALLERS` is read. The answer typically says that `OrderProcessor.ts` ignores the return value, that `RefundHandler.ts` uses `receipt.status`, that `BulkImporter.ts` passes `row.orderId` and imports through the wrapper `./legacy` (`src/legacy/index.ts`), and that `RetryQueue.ts` calls it in 3 functions |
| C8 | Read incrementally, only after Grep has found the files that matter: reading every source file upfront is a context-budget killer that the exam penalises, and each Read should be justified by the previous step (**New**) | Compare both runs: the set of files read, the Read count and `chars_read()`, and check the Reads of `grep-glob-read` against `GREP_FILES` and `UNRELATED` | `grep-glob-read`: every Read is in `GREP_FILES` (at most 6 Reads), and typically 0 Reads of `UNRELATED` files. `glob-only`: typically every non-test file is read, and `chars_read()` is typically more than twice that of `grep-glob-read` |

### POC 2: Edit first

**Build:** `poc2_edit_first.py`, reusing `builtin_setup.py` and `run_agent()`. Each run uses `fresh_copy(<run>)` and `build_builtin_options(workdir, EDIT_TOOLS)`.

The prompts:
- `MIGRATE_PROMPT = "Migrate src/OrderProcessor.ts, src/RefundHandler.ts and src/BulkImporter.ts from the deprecated processLegacyOrder to the new API: replace each call processLegacyOrder(<arg>) with processOrder(<arg>, { validate: true }), and import processOrder from \"./orders/processOrder\" instead of importing processLegacyOrder. Don't change any other file."`
- `NON_UNIQUE_PROMPT = "Controlled Edit test on src/RetryQueue.ts. Make your first Edit call with old_string exactly \"  await processLegacyOrder(orderId);\" (two leading spaces) and new_string \"  await processOrder(orderId, { validate: true });\", even if you expect it to fail. The goal is to change only the call inside retryFailedOrder(). If an Edit fails, recover using the Edit tool."`
- `REPLACE_ALL_PROMPT = "In src/RetryQueue.ts, replace every processLegacyOrder(orderId) call with processOrder(orderId, { validate: true }). Leave the import line as it is."`

| Run | Prompt |
|---|---|
| `migrate` | `MIGRATE_PROMPT` |
| `non-unique` | `NON_UNIQUE_PROMPT` |
| `replace-all` | `REPLACE_ALL_PROMPT` |

After each run, the script prints:
- every `Edit` and `Write` call, with its `old_string` or the length of its `content`, its `replace_all` value, and its result's `is_error` and text;
- `count_calls(file)`, which returns the number of old calls (`processLegacyOrder(`) and new calls (`processOrder(…, { validate: true })`) in a file of the copy;
- `edit_cost(call, workdir)`, which compares the characters an Edit sent (`len(old_string) + len(new_string)`) with the characters a Read + Write of the same file would move: the whole file twice, once read and once written back.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C9 | Use Edit to replace the deprecated call with the new API in each caller file, such as `processLegacyOrder(orderId)` → `processOrder(orderId, { validate: true })`, with Edit confirming each replacement (**New**) | Run `migrate`. Then check the 3 files in the copy with `count_calls()`, and check `RetryQueue.ts` too, which was out of scope | In each of the 3 files: 0 old calls, 1 new call and an import of `processOrder` from `./orders/processOrder`. `BulkImporter.ts` now reads `processOrder(row.orderId, { validate: true })`, so the argument was kept. `RetryQueue.ts` still has its 3 old calls. Typically 6 Edit calls (an import and a call per file), each result not `is_error`, with text that typically confirms the file was updated |
| C10 | Edit is the preferred modification tool: it targets specific text and uses less context than Read + Write. Defaulting to Read + Write for every change is penalised: always try Edit first (**New**) | Count the `Write` calls across all three runs, and print `edit_cost()` for every successful Edit | 0 `Write` calls in all three runs. An Edit of one call sends 86 characters for the bare line (36 old + 50 new) and 128 with one extra line of context, which is under 10% of a 1,500-character caller file. A Read + Write of the same file moves at least 2 × 1,500 = 3,000 characters |
| C11 | Edit fails when `old_string` matches more than one location: a safety mechanism, not a bug (**New**) | Run `non-unique`. Print the first Edit call's `old_string` and its result | The first Edit's `old_string` is the bare line, and its result has `is_error=True`. Its text typically says that the string matched more than once, for example `Found 3 matches`. `RetryQueue.ts` is unchanged after that call: Edit refused to guess which of the 3 places was meant |
| C12 | Recovery 1: widen `old_string` with the surrounding lines (the function name, or a unique adjacent line) until it pins down one location, and the retry changes exactly one occurrence (**New**) | Same run. Print the next Edit's `old_string`, then `count_calls("src/RetryQueue.ts")`, and check which function changed | The retry's `old_string` is longer than the bare line and contains a unique anchor, such as `logRetry(orderId);` or the `retryFailedOrder` signature, and its result is not `is_error`. After the run: 1 new call (inside `retryFailedOrder()`) and 2 old calls (inside `replayOrder()` and `resumeOrder()`) |
| C13 | Recovery 2: `replace_all: true` when every occurrence should change, updated atomically (**New**) | Run `replace-all`. Print each Edit's `replace_all` and the file's counts | Typically 1 Edit with `replace_all: true` and a result that is not `is_error`. After the run: 0 old calls and 3 new calls in `RetryQueue.ts`, all changed by that one call, and the import line is untouched |
| C14 | Read + Write is the last resort: it loads the whole file for what is usually a one-line change (the practice answer). On the exam, the guide names Read + Write as the fallback when Edit can't pin down its target, so answer that (**New**) | After the three runs, print the fallback order: 1) widen `old_string`, 2) `replace_all: true`, 3) Read + Write. Print it with each option's measured cost for `RetryQueue.ts`, from `edit_cost()` and the file's length, and then the line `Exam answer: when Edit can't find a unique match, fall back to Read + Write` | No run needed Read + Write: both Edit recoveries succeeded at 86–128 characters per call, against at least 3,000 characters for a Read + Write of `RetryQueue.ts`. The exam line is printed once |

### Terminal commands (for the later tutorial)

None: every concept in this topic is a programming concept (the built-in tools are tools Claude calls, not commands you type).

### Already covered by earlier POCs

None: every concept in this topic is new.
