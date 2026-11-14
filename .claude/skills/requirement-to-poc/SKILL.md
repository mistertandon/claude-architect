---
name: requirement-to-poc
description: Build the runnable POC code for one revised POC requirements file (curriculum/<domain>/<NN>-revised-<Topic>.md, written by /refined-poc) for the Claude Certified Architect – Foundations exam, with the Claude Agent SDK for Python. It produces a self-contained folder <domain>/<NN>-<Topic>/ with short beginner-friendly scripts, settings in .env, logging of only model input and model output, at most 3 runs per script, and a README, and checks the code offline without calling the API. Use when the user runs /requirement-to-poc <path> or asks to implement, build or code the POCs of a revised file.
argument-hint: <path to NN-revised-Topic.md>
---

# requirement-to-poc

Build the POCs that a revised requirements file specifies. The reader is a developer preparing for the exam: the code must show each concept in the simplest practical way, and the log of one paid run must be enough to study it without paying for another.

**Reference implementation:** `01-Agentic-Architecture-&-Orchestration/01-Agentic-Loops/`, built from `curriculum/01-Agentic-Architecture-&-Orchestration/01-revised-Agentic-Loops.md`. Read its `.py` files, `README.md`, `requirements.txt` and `.gitignore` before writing (never its `.env`), and match their structure, naming, comment density and size. For multi-agent topics, hooks and structured output, `02-` to `06-` in the same domain folder show the same rules applied (built 2026-10-27). The rules below must not change. Where a spec disagrees with them, the rules win (see "Keep it simple" and "Translating the spec").

## Input and output

- **Input:** `$ARGUMENTS`, the path to a spec file named `<NN>-revised-<Topic>.md`. A spec with another label that the user names, such as `-preview-`, works the same way.
  - No path given: ask for one.
  - File doesn't exist: list the `*-revised-*.md` files in that folder and ask which one was meant.
  - A `-raw-` file: tell the user to run `/refined-poc` on it first.
  - An empty file (a placeholder): say so and stop.
- **Output folder:** `<project root>/<domain folder>/<NN>-<Topic>/`.
  - The project root is the folder that contains `curriculum/`.
  - The domain folder has the same name as the spec's parent folder.
  - `<NN>-<Topic>` is the spec's file name without the label and without `.md`.
  - For example, `curriculum/01-Agentic-Architecture-&-Orchestration/02-revised-Multi-Agent-Orchestration.md` → `01-Agentic-Architecture-&-Orchestration/02-Multi-Agent-Orchestration/`.
  - Never write inside `curriculum/`.
- If the output folder already has files, list them and ask whether to update them, replace them or stop.

## Steps

1. **Read the spec completely.** That means the verdict (POC count, shared constraints, the options code block), each POC's **Build** line, every row's Requirement and Acceptance, the "Terminal commands" table and the "Already covered" table. List every C and E ID.
2. **Collect the code the spec reuses.** The spec may cite an earlier file or function, for example "reuses `coordinator.py`" or "`run_agent()` from 01, extended". For each one, open the earlier topic's POC folder (same naming rule) and read that file.
   - Every POC folder runs on its own. Copy the file into the new folder and apply only the change the spec describes.
   - Never import from another POC folder, and never edit one.
   - If the earlier topic has no POC folder yet, ask the user whether to build that topic first (recommended) or to build only the reused piece here, from the earlier spec.
3. **Verify every SDK name you use:** class, option, field, value, hook event and environment variable.
   - Check against the current docs (`https://code.claude.com/docs/en/agent-sdk/...`, for example `python`, `agent-loop`, `custom-tools`, `subagents`, `hooks`) or the SDK source (`https://raw.githubusercontent.com/anthropics/claude-agent-sdk-python/main/src/claude_agent_sdk/types.py`).
   - Don't write SDK names from memory.
   - If the spec is outdated, follow the SDK and say so in the report.
4. **Plan the files.**
   - Use the spec's function, class, constant and prompt names exactly, because later specs copy and extend them.
   - Merge the spec's modules as "Keep it simple" says. Keep a spec file name only when a later spec reuses that file by name (grep the later revised files, including other domains, for it).
   - For each ID, decide where it lives in the code and where the developer sees it: a log line or a code location.
   - Apply "Translating the spec".
5. **Write the files** by the conventions below.
6. **Verify offline** (see "Offline verification"). Never call the API.
7. **Check before reporting:**
   - Every C and E ID of the spec appears in the README's concept map (grep for each one).
   - Every `log.` and `print(` call is one of the allowed lines (grep and review each).
   - No script has more than 3 runs, and every `query()` stream is inside `try/except`.
   - No file outside the new folder changed, apart from scratchpad files.
8. **Report briefly:**
   - The folder and its files.
   - Per POC, its scripts and how many `query()` calls each one makes.
   - Where you departed from the spec and why: translation rules, outdated SDK names.
   - What the offline check covered.
   - That no live run was made, so the user's first run is the first live test.
   - How to start: `cp .env.example .env`, add the key, then run the scripts in README order.

## Conventions

### Keep it simple

The user's rule since 2026-10-27: a POC holds just enough code for a developer to understand the agentic concept. The specs are heavier than that (checker modules, many trials, big mock projects), so build their concepts, not their test machinery:

- **Files:** `common.py`, one setup module, and one script per POC. Keep another module only if both POCs use it or a later spec reuses it by name (for example `coordinator.py`, `attribution_check.py`). A helper that only one POC uses (its hooks, its checkers) lives in that POC's script. Aim for 4–6 `.py` files of about 70–150 lines each.
- **Concepts, not a test harness:** drop spec code that only scores or checks the build (✅/❌ tables, census functions, trace tuples, self-checks, JSON files passed between scripts, comparison scripts). A value computed in Python stays only when it *is* the lesson, as one log line.
- **One run per mode:** the spec's "N trials" become 1 run, plus `# optional:` repeats. The README explains what one run can't show (for example, a 92% rule needs about 12 runs to fail once).
- **Small mock data:** only what a concept needs. A mock project the code reads (a repo to review, a document library) gets the fewest and shortest files that still show the concept, and the README says what a real-scale run would show.
- **Coverage stays complete:** every C and E ID is still in the README's concept map. An ID with no code points to a comment or a README note.

### Folder layout

| File | Contents |
|---|---|
| `common.py` | `load_settings()`, `setup_logging()` and `log_model_io()`. Copy 01's file. Change only `log_model_io()`, and only when the topic adds a new kind of model I/O (see "Logging") |
| the spec's setup module (`tools.py`, `research_setup.py`, ...) | mock data, tools, prompts, `build_options()`, and the streaming runner when both POCs share it (04: `run_support()`) |
| `poc<N>_<name>.py` | one script per POC, with the helpers only it uses. A POC with a free offline part gets a second script with the same number (01: `poc2_exit_signal.py` and `poc2_agent_loop.py`) |
| `.env.example`, `requirements.txt`, `.gitignore`, `README.md` | copy `requirements.txt` and `.gitignore` from 01. Raise the SDK minimum only for a feature the topic needs |

Don't add:
- a tests folder
- `__init__.py`
- command-line arguments
- self-check blocks (an `if __name__ == "__main__":` that tests a module)

### Logging: model input and model output only

The user rejected the first version of 01, which logged the whole flow: "Due to too much logging I am unable to read the code". The log shows what goes into the model and what comes out of it. The code shows the rest.

- **`log_model_io(message)`** in `common.py` is the only place that logs model I/O.
  - Before each `query()`, log one `MODEL INPUT   prompt` line.
  - Then call `log_model_io()` once per streamed message.

  ```
  MODEL INPUT   prompt       <prompt>
  MODEL OUTPUT  thinking     <summarized reasoning>
  MODEL OUTPUT  tool_use     <tool name> <input>  (id=<id>)
  MODEL INPUT   tool_result  <content>  (tool_use_id=<id>, is_error=<flag>)
  MODEL OUTPUT  text         <text>
  MODEL OUTPUT  stop_reason  <stop_reason>  (loop result: <subtype>)
  ```
- **Several agents:** tag each line with its agent, for example `MODEL OUTPUT  tool_use     [doc-analyst] mcp__research__read_document ...`.
  - A message's `parent_tool_use_id` is the `id` of the `Agent` call that started its subagent. `None` means the main agent.
  - Keep a dict from each `Agent` call's `id` to its `input["subagent_type"]`: `log_model_io(message, agent_names)` fills it (02's `common.py`).
- **Structured output:** with `output_format`, Claude returns its JSON by calling the built-in `StructuredOutput` tool. Log that call as `MODEL OUTPUT  structured   <json>  (id=...)`, not as a `tool_use` step, and read the data only from `ResultMessage.structured_output` (`None` on a `success` result counts as a failure).
- **Multi-turn sessions:** log each new user message as another `MODEL INPUT   prompt` line.
- **Other allowed lines,** one line each:
  - `log.error` for a caught failure.
  - `log.warning` when the concept is a guard firing (01: `Safety cap hit: max_turns=1 ...`).
  - A value computed in Python that is itself the lesson and can't be seen in the model I/O, for example the categories a decomposition missed, or the continue/stop decision of a Python-controlled loop.
- **Never add:**
  - turn headers, banners or legends
  - ✅/❌ per step
  - summaries, or cost or turn totals
  - tool-handler lines
  - `SystemMessage` or rate-limit lines
  - dumps of the options
- **Output destination:** `setup_logging()` writes to the console and to `logs/<script>_<date>_<time>.log`, so a paid run can be re-read. Handlers go on the named logger `poc`, never the root logger, because the SDK's MCP server logs at INFO.
- **Offline (free) scripts** `print` their result and write no log file.

### Settings: `.env`

- **`.env.example`** lists these, each with a one-line comment:
  - `ANTHROPIC_API_KEY=your-api-key-here`
  - `MODEL_ID=claude-sonnet-5-5`
  - `MAX_BUDGET_USD=0.50`
  - any setting the spec makes tunable (01: `MAX_TURNS=20`)
- **`MODEL_ID`** sets the main model. `claude-sonnet-5-5` is the user's choice for cost, even where the spec's code says `claude-opus-5-5`. Keep a per-subagent model when the spec teaches it (for example `model="inherit"`).
- **`load_settings()`** runs before `setup_logging()`, so a missing `.env` leaves no empty log file. It rejects a missing key or the placeholder key.
- Never hard-code the key, and never read, print or copy the user's `.env`.

### Code

- **Script shape:** Python 3.10+, `claude_agent_sdk` and `python-dotenv`. Each script reads top to bottom in one pass, in this order:
  1. A docstring: what the POC teaches, the log lines it produces, and a `Run:` line with its number of `query()` calls.
  2. Constants.
  3. A `PROMPTS` or `RUNS` list.
  4. One async function that streams `query()`.
  5. `main()`.
  6. `sys.exit(asyncio.run(main()))`.
- **At most 3 runs per script.** A run is one entry of the `PROMPTS`/`RUNS` list.
  - Spec prompts beyond that, and optional demos, go in the list as commented-out entries marked `# optional:`.
  - When the spec's design makes one run call `query()` several times (a coordinator, a Python-controlled loop), cap loops at 2–3 iterations.
- **try/except with specific exceptions:**
  - Setup (`OSError`, `RuntimeError`): print `Setup failed: ...` and return 1.
  - `ResultError` around each single-shot `query()` stream. It is raised after the error `ResultMessage` has been yielded.
  - `ClaudeSDKError` around each run in `main()`.
  - Inside every tool handler: return `is_error: True` with a recovery hint instead of raising.
- **"Done" comes only from the `ResultMessage`**, never from text.
  - Check `subtype == "success"`, plus `stop_reason == "end_turn"` where the loop matters.
  - Don't `break` on it, because events can still follow.
- **Options:** start from 01's `build_options()` and add what the spec requires, with one short "why" comment per option. 01's options are:
  - an explicit `system_prompt`
  - `tools=[]`
  - `allowed_tools` with full `mcp__<server>__<tool>` names
  - `setting_sources=[]`
  - `env={"ENABLE_TOOL_SEARCH": "false"}`
  - `thinking={"type": "adaptive", "display": "summarized"}`
  - `max_budget_usd`
- **Tools:**
  - Use `@tool` with a full JSON Schema dict.
  - Add `annotations=ToolAnnotations(readOnlyHint=True)` when the tool has no side effects.
  - Use mock data with made-up entities, so Claude has to call the tool.
  - No `eval()`.
- **Keep it simple:** add no class, helper or abstraction the spec doesn't ask for.
- **Comments** explain the concept on the line that shows it, as in 01. No comment restates the code.

### Translating the spec

The specs were written before the logging rule, so some rows ask for output the user doesn't want. Build the concept, not the printing:

| The spec asks for | Build |
|---|---|
| printing each streamed message, a trace, or a labeled flow (`[coordinator -> x] ...`) | the `MODEL INPUT`/`MODEL OUTPUT` lines, with agent tags when there are several agents |
| a handler print that proves the SDK ran a tool | nothing: the `tool_result` line carries the handler's return value |
| an offline self-check, asserts, or ✅/❌ prints that only test the build | nothing in the POC: check it yourself in step 6 |
| a printed value or comparison that is itself the lesson (01 C7: ❌ ❌ ✅ for three exit strategies) | keep it, one line per result. When it needs no API, put it in a free offline script like 01's `poc2_exit_signal.py` |
| `ANTHROPIC_API_KEY` from the environment; `claude-opus-5-5` | `.env` through `load_settings()`; `MODEL_ID` |
| a function signature or return shape that a later spec reuses | build it exactly as specified |
| a helper module that only one POC uses (checkers, a hooks module) | merge it into that POC's script |
| N trials per mode (`TRIALS = 3`, `TRIALS = 5`) | 1 run per mode, plus `# optional:` repeats; the README explains what one run can't show |
| a JSON file one script writes for another, or an offline comparison script | nothing: give the later POC fixed reference data, and let the README say which log lines to compare |
| a large mock project (14 files × 100 lines) | the fewest, shortest files that still show the concept; the README says what a real-scale run would show |

The Acceptance cells become your offline checks in step 6, and the "where you see it" column of the README's concept map.

### README.md

Use the same sections as 01's README:

1. The title, and the spec's path.
2. **The idea in 30 seconds:** a small ASCII diagram and 3–4 bullets.
3. **Files:** each file, what it is, and whether it calls the API (how many runs).
4. **Setup (once):** the same four commands and ensurepip note as 01.
   - Don't explain virtual environments; the user removed that section.
   - Say that the `.env` from an earlier POC folder can be copied.
5. **Run (in this order):** one comment per script naming its runs, plus the optional extras.
6. **Reading the log:** a sample marked illustrative, in the exact log format, and 2–3 bullets on what to notice.
7. **Concept map:** every C and E ID, with three columns: ID, concept, and where you see it (a log line, or a file and function).
   - "Already covered" IDs point to the earlier POC folder.
   - Terminal-command IDs say "terminal command: not in this POC".
8. **Settings (`.env`):** one bullet per setting.

## Offline verification

Before you start, tell the user in one line that you'll check the code offline in the scratchpad, without calling the API.

1. **Environment.**
   - Reuse a venv in the scratchpad if one exists. Otherwise run `python3 -m venv <scratchpad>/venv`.
   - If that fails because ensurepip is missing (Debian/Ubuntu), run `python3 -m venv --without-pip <scratchpad>/venv` instead. Then bootstrap pip with `get-pip.py` from `https://bootstrap.pypa.io/get-pip.py`, downloaded into its own scratchpad folder.
   - Install the POC's `requirements.txt` into the venv. Install nothing outside the scratchpad.
2. **Work on a copy.**
   - Copy the POC's `*.py` files and `requirements.txt` to the scratchpad. Never copy `.env`.
   - Write a dummy `.env` in the copy (`ANTHROPIC_API_KEY=sk-ant-dummy` plus the other settings).
   - Uncomment the optional entries in the copy.
   - Everything below runs on the copy, so the real folder gets no `logs/` or `__pycache__/`.
3. **Compile and run the free scripts.** Run `python -m py_compile` on every file, then run the offline scripts for real.
4. **Replay fake streams through every API script.**
   - Copy [fake_stream_harness.py](fake_stream_harness.py) (`"${CLAUDE_SKILL_DIR}/fake_stream_harness.py"`) to the scratchpad and replace its SCENARIOS section.
   - The harness swaps `query` in every POC module that imported it (the script, `coordinator.py`, a setup module) for an async generator that yields real SDK message objects in stream order, and it runs the POC's real tool handlers for each `tool_use`.
   - Give every prompt a scenario, and cover each error path the code catches. For example, `error_max_turns` is the error `ResultMessage` followed by `ResultError`.
   - Builders for the other cases: `subagent_call()` (an Agent call, the subagent's round trips with `parent_tool_use_id`, its report), `structured()` (the `StructuredOutput` call), `hook_round_trip()` (the POC's real `PreToolUse`/`PostToolUse` callbacks from `options.hooks` around the real handler), and `capture_handlers()` for tools defined inside a function (closures over a session).
   - Let the fake model build its answer from the real tool outputs where the lesson depends on them (coverage, attribution, normalized results).
   - Run one script per process: `python fake_stream_harness.py <copy dir> <script module>`.
5. **Check the output:**
   - Exit code 0 and no traceback.
   - The log reads top to bottom in execution order, and only the allowed lines appear.
   - Each `tool_use` id comes back as the matching `tool_use_id`.
   - The log file exists in the copy's `logs/`.
   - Every Acceptance cell that doesn't depend on live model behaviour holds: tool outputs, computed values, error results.
   - Fix and rerun until clean.
