---
name: poc-to-article
description: Write a developer-friendly article (<script>-article.md, next to the script) that explains one POC script for the Claude Certified Architect – Foundations exam — its end-to-end execution flow, the significance of every code snippet and agentic AI concept, a turn-by-turn trace built from a REAL run log of the logging version, an exam lens (objectives from the curriculum raw file, raw Messages API equivalent, scenario questions with answers, cheat sheet) — then presents it verbatim as a styled HTML Artifact from the skill's article-template.html. Requires BOTH the POC path and its log file(s); refuses to run without either. Use when the user runs /poc-to-article <POC .py file or folder> <log file(s)> or asks to explain a POC as an article.
argument-hint: <POC script or folder> <log file(s)> (both required), e.g. raw-poc/01-Agentic-Architecture-Orchestration/01-Agentic-Loops/poc2_agent_loop.py 01-Agentic-Architecture-Orchestration/01-Agentic-Loops/logs/poc2_agent_loop_20261026_191138.log
---

# poc-to-article

Explain the POC at `$ARGUMENTS` as a Claude architect expert writing for developers: what runs, in what order, why each snippet exists, which agentic concept it shows, what a real run printed, and how the exam tests it.

**Reference result:** `raw-poc/01-Agentic-Architecture-Orchestration/01-Agentic-Loops/poc2_agent_loop-article.md` (written 2026-10-28). Read it first and match its structure, depth and tone.

Project root: `/mnt/CC0E50740E505992/claude-cert/ccar-f`.

## 0. Scope

- **Both arguments are mandatory: the POC path AND the log file(s).** If either is missing, do NOT run: read nothing, write nothing, and reply only with the usage line `/poc-to-article <POC script or folder> <log file(s)>` and what is missing. Never search for a log yourself and never fall back to an "expected" trace.
- `$ARGUMENTS` = first token: one `.py` script, or a POC folder. A folder → one article per entry-point script (`poc*.py` with `if __name__ == "__main__"`); list them and the article names before writing.
- Remaining tokens = the **log file(s)** for the real run. Paths are relative to the project root or absolute. Match each log to its script by the `<script stem>_` filename prefix. For a folder, every entry-point script needs a log: list script → log pairs and stop if any script has none. A path or log that doesn't exist, or a log whose prefix matches no script → stop and say which.
- Output: `<script stem>-article.md` in the **same folder** as the script (e.g. `poc2_agent_loop.py` → `poc2_agent_loop-article.md`). If it exists, say so and ask before overwriting.
- Also publish the article as a styled HTML Artifact (section 5).
- Edit nothing else. Never run the POC (it calls the paid API) unless the user asks.

## 1. Gather (read, don't guess)

1. The script, whole.
2. Every local module it imports (`common.py`, `tools.py`, …) — the article explains the parts the script depends on (options, tools, settings).
3. Sibling scripts it references (e.g. an offline demo named in its docstring) and the folder `README.md`.
4. `.env`: key NAMES only — print it with values masked (`sed 's/=.*/=<redacted>/'`); never read or quote values. Also `requirements.txt` for the SDK version.
5. **Curriculum objectives:** `curriculum/<domain>/<NN>-raw-<Topic>.md` (and the `-revised-` file) for this topic. Map the POC folder name to it (`01-Agentic-Architecture-Orchestration/01-Agentic-Loops` → `curriculum/01-Agentic-Architecture-&-Orchestration/01-raw-Agentic-Loops.md`). These "Why:" lines are what the exam tests — the exam section is built from them.
6. **Real run log:** the log file the user passed in `$ARGUMENTS` (mandatory, see step 0). Before reading, check size and grep for secrets (`grep -ciE 'sk-ant|api_key'`); if a hit, stop and tell the user. A `raw-poc/` script has no logging; its logged twin is the same path without `raw-poc/`. Read the twin's `log_model_io()` (usually in `common.py`) so you know which message class and field each log line tag comes from.

## 2. Verify claims against the real log

The log beats your expectation. Before writing a trace, compare each step you would predict with the log. Example from the reference: the expected trace said the tool never ran when `max_turns=1` fired; the log showed the handler DID run and the result was produced, the run ended with `subtype=error_max_turns`, `stop_reason=tool_use`. Write what the log shows, and fix every other section that said otherwise.

Only cite fields the log contains. Do not invent `num_turns`, cost, session ids, thinking text or `SystemMessage` content that wasn't logged — say they exist in the stream but the log records only model I/O.

## 3. Article structure (in this order)

Header block: file, domain → topic, SDK version.

1. **What this POC proves** — table: idea → where in the code. Plus a one-line diagram of the loop/pattern.
2. **The files involved** — tree + one line per file on its responsibility (configuration / capabilities / orchestration).
3. **End-to-end execution flow**
   - 3.1 ASCII call-path diagram from `python <script>` through every function, into the SDK-owned part (box it, label it "SDK-owned"), back to how the result is read.
   - 3.2 The message stream for the most interesting run, **from the real log**: a table "log line tag → message class → field", then the stream with real values (ids, inputs, results, `is_error`), then "What to notice in the real data" bullets (id pairing, data flowing between tools, absent/present narration, …).
4. **Code walkthrough** — one subsection per snippet in execution order (docstring, imports, constants/run table, each function, `main`, `__main__`), then the helper-module parts the script relies on (options builder: table option → effect → agentic concept; tools: description-as-prompt, schema, annotations, safe implementation, `is_error` results). For each: the code, **why it matters**, and an **Agentic concept:** line where one applies. Name anti-patterns the code avoids.
5. **Turn-by-turn trace of each run (real output)** — per run: the real log block, a table "variable / field → value" tied to the variables in the code (inputs, `message.*` fields, exceptions, returned value), a per-turn table for multi-tool runs (tool asked → handler code that ran → returned content), and "Lessons from the real data". End with a side-by-side table of all runs (config, tool calls, final subtype/stop_reason, exception, returned value, wall time from timestamps).
6. **Agentic AI concepts recap** — table concept → how this POC shows it.
7. **Common mistakes this POC helps you avoid** — numbered.
8. **Claude Architect exam lens**
   - 8.1 Table: each curriculum objective → what a correct answer looks like → where the POC shows it. Add an exam tip when the exam frames it differently from the POC (e.g. raw Messages API vs Agent SDK).
   - 8.2 When the POC uses the Agent SDK but the objectives describe the raw Messages API (or vice versa), show the equivalent code in the other form and a mapping table between the two.
   - 8.3 8–10 scenario questions: realistic production situation, 4 options (A–D), **Answer** with the reason, why the distractors are wrong when it teaches something, and a **POC link** to the code. Cover each objective at least once, plus its anti-patterns and the nearest edge cases.
   - 8.4 Quick-recall cheat sheet (code block).
9. **How to run it** — commands, which are free/offline vs paid, exit codes.

## 4. Style

- Developer-friendly: short sentences, tables over prose, every claim tied to a file/function. Code snippets copied exactly from the source (trimming with `...` is fine).
- Explain the SDK facts the code relies on, but only facts you saw in the code, its comments, or the log; no speculation about SDK internals beyond that.
- Say the scenario questions are written to match the objectives, not official exam questions.

## 5. Present the article as a styled HTML page

After the `.md` is written, turn it into a reading page and publish it as an Artifact (private by default).

**Rules:**
- **Verbatim content.** Never retype, reword, shorten or reorder the article. The page embeds the `.md` text unchanged and renders it in the browser (marked + highlight.js from cdnjs). The only extra words allowed are UI labels: "Contents", "Copy", "Reveal answer", the code-language label.
- **Use the template as-is:** `.claude/skills/poc-to-article/article-template.html` (built and approved 2026-10-28 for `poc2_agent_loop-article.md`). Don't redesign it per article. Change it only when the user asks, and then save the change back into the template.
- Build with a script so the embed is exact. Stop if the Markdown contains `</script`:

  ```bash
  python3 -c "
  import sys
  md=open(sys.argv[1],encoding='utf-8').read()
  assert '</script' not in md.lower()
  t=open(sys.argv[2],encoding='utf-8').read()
  open(sys.argv[3],'w',encoding='utf-8').write(t.replace('__MARKDOWN__',md))
  " <article.md> .claude/skills/poc-to-article/article-template.html <scratchpad>/<script stem>-article.html
  ```

- Load the `artifact-design` skill before publishing, then publish the built file with icon `code` and a one-sentence description. Put the built HTML in the session scratchpad, not in the project folder. When an article is re-run, republish to the same artifact URL if it's known.

**What the template does** (keep these features when you edit it):
- **Hero:** the `# H1` is split at its first `: ` into an eyebrow pill (`POC 2b:`) and a gradient title. The header blockquote (File / Domain / SDK) becomes three colour pills. A soft glow sits behind the hero, plus an orbiting-dot ornament (hidden on mobile).
- **One colour per `##` section,** cycling cobalt, violet, teal, rose, amber, green (light and dark tokens `--c1`…`--c6`). Each section uses its colour for the gradient bar above the heading, the pill around the section number, `###` number pills, `####` headings as pills, list markers, table headers and alternate-row shading, numbered lists drawn as pill counters, and the matching dot in the contents list.
- **No highlighter behind bold text.** The user had this removed; don't bring it back.
- **Inline `code` as pills, coloured by meaning:**
  - green: `end_turn` / `success`
  - rose: errors (`error_*`, `ResultError`, `ClaudeSDKError`, `None`, `max_tokens`, `is_error`)
  - amber: caps and config (`max_turns`, `max_budget_usd`, `tools=[]`, `allowed_tools`, …)
  - cobalt: tools (`tool_use`, `tool_result`, `mcp__*`, tool names)
  - violet: messages (`*Message`, `TextBlock`, `stop_reason`, `subtype`)
  - teal: functions (`query`, `run_agent`, `build_options`, …)
  
  When a new article brings new key terms, extend the regex table `kinds` in the template.
- **Code blocks** look like terminal windows in both themes: red, amber and green window dots, a language pill, a Copy button with a select-text fallback, and highlight.js for `python`/`bash`.
- **Tables** sit in horizontal-scroll wrappers. **Blockquotes** are amber callouts, with their first bold label (`Exam tip:`) as a pill.
- **Scenarios (8.3):** each `**Scenario N: …**` block, up to the next `---`, becomes a card with a "Scenario N:" pill. The A–D options are pill buttons: clicking one marks wrong in red and right in green and opens the answer. The `**Answer:**` paragraph sits behind "Reveal answer", with the label as a green pill.
- **Layout and reading aids:** a sticky contents list built from `##`/`###` that highlights the current section (it folds away at 1000px and below), a reading-progress bar, light and dark themes, and safe-area side gutters.

The template relies on the article structure in section 3: `# POC …: Title`, a `>` header blockquote, numbered `##`/`###` headings, `**Scenario N: …**` lines, `- A.` options, and `**Answer: X.**`. Keep the article in that shape so the page renders correctly.

## 6. Report

Reply with: the article path, the artifact link, a short section list, any claim the log corrected, which log file was used, and anything in the folder that looked off.
