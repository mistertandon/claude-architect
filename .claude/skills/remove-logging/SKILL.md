---
name: remove-logging
description: Copy every POC folder under a given path (POCs built by /requirement-to-poc for the Claude Certified Architect – Foundations exam) into raw-poc/ and remove all logging and console output from the copy, so a developer reads only the agentic code. The source stays untouched. Removes setup_logging/log_model_io/log.* calls, print(), logs/ folders, the .gitignore entry and README/docstring log mentions; keeps every concept check, with its result held in a variable or returned. Use when the user runs /remove-logging <path> or asks to strip logging from POCs.
argument-hint: <path containing POC folders, e.g. 01-Agentic-Architecture-Orchestration/03-Subagent-Invocation-and-Context-Passing>
---

# remove-logging

Make a logging-free copy of every POC under `$ARGUMENTS`, so the code shows only the agentic concept. Nothing else in the logic changes.

**Output always goes to `/mnt/CC0E50740E505992/claude-cert/ccar-f/raw-poc/`** (the user's rule). The source path is never edited.

**Reference result:** `raw-poc/` was stripped this way on 2026-10-28; read a folder there (e.g. `raw-poc/01-Agentic-Architecture-Orchestration/03-Subagent-Invocation-and-Context-Passing/`) to match the style.

## 0. Scope, copy and safety

- `$ARGUMENTS` is the source path (relative to the project root `/mnt/CC0E50740E505992/claude-cert/ccar-f`, or absolute). If it is empty or doesn't exist, ask for it. If it is already inside `raw-poc/`, ask: that would strip a copy in place.
- Target = `raw-poc/<source path relative to the project root>`, e.g. `01-Agentic-Architecture-Orchestration/05-Agent-SDK-Hooks` → `raw-poc/01-Agentic-Architecture-Orchestration/05-Agent-SDK-Hooks`; a domain folder maps to its domain folder, and every POC folder under it is copied.
- A POC folder is any folder that holds a `common.py` (or `.py` files that use `log.` / `print(`).
- Before copying, list the POC folders found, their targets, and how many log/print lines each has (one `grep -c` table).
- **A target that already exists in `raw-poc/`**: list which ones and ask before replacing them, because they may hold edits. On yes, replace each target folder whole (delete it, then copy).
- Copy with `rsync -a --exclude .venv --exclude __pycache__ --exclude logs --exclude .env <src>/ <target>/` (or `cp -a` and then delete those). Never copy `.env`: it holds the API key. The README's `cp .env.example .env` step covers it. Say so in the report.
- Work ONLY in the target from here on. The untouched source is the base for the final diff.
- Never touch `.env.example`, `requirements.txt`, prompts, schemas, tool handlers, options, sample data (`sample_repo/`, `snippets/`), or the `/requirement-to-poc` skill.

## 1. The mechanical pass (script)

Run the bundled helper on every `.py` file under the **target**:

```bash
python3 -I .claude/skills/remove-logging/strip_common.py <all .py files under the target>
```

It strips `common.py` down to `load_settings()` / `Settings` / `POC_DIR`, removes `setup_logging(...)` + the "Setup failed" print, one-line `log.error/warning` in `except` blocks, `MODEL INPUT` lines, `log_model_io(...)` calls, and the `from common import log, ...` names, and adds `pass` to an emptied `except`. A file whose result would not parse is reported `SKIPPED` and left unchanged: handle it in step 2.

## 2. The manual pass (one folder at a time)

Read each remaining hit in the target (`grep -nE "\blog\b|log\.|log_|print\(|logging"`) in context and apply these rules:

| What | Do |
|---|---|
| A `log.*` / `print()` line that only reports | delete it |
| A block left empty (`if`, `else`, `except`, loop) | delete the branch if it did nothing else; keep `return` / `continue`; an `except` that must still swallow the error gets `pass` |
| A value computed inside the log call that is a **concept check** (scores, verdicts, coverage, counts, routing, timing, diagnosis) | keep it: assign it to a named variable (`missing = ...`, `diagnosis = diagnose(...)`) |
| A helper that only logged its results (e.g. `log_scores()`, a `report()` that logs a table) | keep its computations, make it **return** them (dict/list/tuple), rename away from `log_` (`log_scores` → `score_review`), update callers to `x = f(...)` |
| A pure display helper (formats a string for a log line: `verdict_line()`, `log_model_io()`'s agent tags `agent_names`) | delete it and its callers |
| A sentence in a log message that teaches something ("Plan for the 24-hour maximum ...") | turn it into a short comment next to the code |
| `print()` in an offline demo | delete it; keep the calls it printed results of |
| A branch split only to log different messages (`if exc.subtype == ...: warning else: error`) | collapse to one `except ...: pass` with a comment naming the cases |
| Data that only has "log" in its name (`REVIEW_LOG`, `pattern_report(log)`, "audit log" in a prompt) | not logging: keep |
| An import used only by removed code (`math`, `FIRST_MAX_TOKENS`, `missing_categories` if its call went) | delete the import, never the definition if a kept check still uses it |
| A loop variable now unused (`for name, ... in RUNS`) | leave it |

Never change a function's control flow, return value or signature except to make a log-only helper return what it used to log.

## 3. Docs and files

- Delete `logs/` folders and the `logs/` line in each `.gitignore`. `sed -i` fails on this NTFS mount ("preserving permissions"): edit with Python or Edit.
- Module docstrings: drop "Besides model I/O, the log shows ..."; when it described what the code checks, rephrase to "The code checks/computes ...". Replace `MODEL INPUT/OUTPUT` example blocks with plain descriptions.
- `README.md`:
  - delete the `## Reading the log` section; when its bullets teach the concept, keep them as a short `## What to compare` section that names variables/functions instead of log lines;
  - `common.py` row → "reads `.env`";
  - every concept-map cell citing a log line (`line \`...\``, `POC 1 log: ...`, `log tags`, `the ... lines`, `warning ...`) → point at the function or variable that holds that result now;
  - Run-section comments promising output ("free: the table and the list") → describe what the script does.

## 4. Verify (offline, no API calls)

1. `python3 -m py_compile` every `.py` (catches empty blocks).
2. `grep -rnE "logging|\blog\.|log_model_io|setup_logging|log_scores|print\(|logs/|MODEL (INPUT|OUTPUT)|Reading the log"` over `.py`, `.md`, `.gitignore`: expect nothing.
3. Unused imports and undefined names: pyflakes is not installed here, so run a small `ast` check (imported-but-unreferenced names; loaded-but-never-bound names, ignoring `__file__`). An issue that already exists in the source is not yours: leave it and mention it.
4. Run the scripts that need no API key and no SDK (e.g. `poc1_batch_planning.py`, `poc2_pattern_priorities.py`) with `python3 -I`: exit 0, no output. Scripts that import `claude_agent_sdk` can't run here (not installed): say so.
5. Delete every `__pycache__` folder under the target (py_compile creates them).
6. Run `diff -r -x .venv -x __pycache__ -x logs -x .env <source> <target>` and skim it. Only log/print lines, log-only helpers and doc text may differ. Then confirm the source is unchanged: `ls` it and check that its `logs/` and `.env` are still there.

## 5. Report

Per folder, one line: what was deleted and anything beyond deletion (a helper made to return, a renamed function, a kept variable). Then the verification results, what could not be run, the target path(s) in `raw-poc/`, and that `.env` was not copied. Don't print the diff.
