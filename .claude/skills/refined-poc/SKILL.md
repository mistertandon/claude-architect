---
name: refined-poc
description: Turn a raw curriculum topic file (curriculum/<domain>/<NN>-raw-<Topic>.md) for the Claude Certified Architect – Foundations exam into a revised POC requirements file (<NN>-revised-<Topic>.md) with the fewest beginner-friendly POCs that still cover every listed concept, built with the Claude Agent SDK for Python. It checks all earlier revised files so new POCs focus on new concepts and reuse earlier POC code. Use when the user runs /refined-poc <path> or asks to refine/revise a raw POC file.
argument-hint: <path to NN-raw-Topic.md>
---

# refined-poc

Convert a raw topic file into a revised POC requirements file. The output is a build spec: the user later gives it to Claude to build the POCs, so every requirement must be concrete and testable.

Reference output: `curriculum/01-Agentic-Architecture-&-Orchestration/01-revised-Agentic-Loops.md`. Read it before writing and match its structure and level of detail.

## Input and output

- **Input:** `$ARGUMENTS`, the path to a raw file named `<NN>-raw-<Topic>.md`. If no path is given, ask for one. If the file doesn't exist, list the matching `*-raw-*.md` files in the same folder and ask which one was meant.
- **Output:** the same folder, with `-raw-` replaced by `-revised-` (for example `01-raw-Agentic-Loops.md` → `01-revised-Agentic-Loops.md`).
- If the output file already has content, read it and tell the user before you replace it.

## Steps

1. **Read the raw file completely.** Each step usually has an instruction, a "Why" and a "You should see".
2. **Extract every concept.** Number them `C1…Cn`, in raw-step order. Take concepts from all three parts of each step: exam rationale and anti-patterns in the "Why" text count too. Nothing listed may be dropped; this is an exam-prep file.

   Then mark each concept that is about **using a Claude Code terminal command** rather than a programming concept: a `claude` CLI invocation or flag (for example `claude -p`, `--output-format`, `--resume`), a slash command (for example `/memory`, `/agents`, `/compact`) or a keyboard shortcut. These get no POC work. Record them in the "Terminal commands" table instead (see the template) with the command name and its important arguments; the user will build a separate terminal tutorial from these tables later. If a concept has both a programming part and a command part, split it: the programming part goes in a POC, and the command part goes in the table as `C<k> (command)`.
3. **Check all previous revised files.** Find every existing `*-revised-*.md` under `curriculum/` (all domain folders, in domain and number order), except the output file itself. Read each one completely and note:
   - the concepts it already teaches, with their file and ID (for example `01-revised-Agentic-Loops.md` C8),
   - the files, functions and setup it already builds (for example `tools.py`, `build_options()`, the mock tools), which later POCs can reuse,
   - the terminal commands it already records, so the same command isn't listed twice.

   Then label each new concept:
   - **New:** not taught before. The new POCs focus on these.
   - **Builds on:** a previous concept used in a new way. Write a requirement for the new part only, and cite the earlier file and ID.
   - **Already covered:** taught before, essentially the same. Don't build POC work for it again. List it in the "Already covered" table with the earlier file and ID, plus a one-line check that it still holds when the new POC uses it. It still counts toward coverage, so no concept is lost.

   Terminal-command concepts get the same labels: a command already recorded earlier goes in the "Already covered" table, and new arguments of an earlier command go in the "Terminal commands" table as **Builds on**, listing only the new arguments.

   If a previous file contradicts what this topic needs (for example an SDK option that has since changed), say so in the report rather than editing the earlier file.
4. **Decide the POC count.** Count only the **New** and **Builds on** programming concepts; terminal-command concepts never add a POC. Group them by the mental model they build, not by raw step. Use the fewest POCs that keep each one beginner-friendly. Raw steps that are only tests of earlier steps, or small additions to them, merge into the POC they test. Reuse previous POC code (by file name) instead of rebuilding it. Usually 1–3 POCs. If every concept was already covered or is a terminal command, the file says so and has no new POC.
5. **Align with the Claude Agent SDK (Python, `claude_agent_sdk`).** The POCs are built with it, not with the raw `anthropic` Messages API.
   - The SDK runs the agent loop itself. Where a raw concept describes something the SDK does internally (calling the model, appending `tool_use`/`tool_result`, checking `stop_reason`), teach it by **making it visible and checking it** in the message stream, and say so in the verdict.
   - Verify every SDK class, option, field and value you use against the current docs (`https://code.claude.com/docs/en/agent-sdk/...`, for example `python`, `agent-loop`, `custom-tools`) or the SDK source (`https://raw.githubusercontent.com/anthropics/claude-agent-sdk-python/main/src/claude_agent_sdk/types.py`). Don't write SDK names from memory.
   - Defaults that keep a POC reproducible (reuse them unless the topic needs otherwise): `tools=[]` (no built-in tools), `setting_sources=[]` (ignore user/project settings), `env={"ENABLE_TOOL_SEARCH": "false"}` (no `ToolSearch` calls), an explicit `system_prompt` (the SDK sends an empty one otherwise), custom tools via `@tool` + `create_sdk_mcp_server` with full names `mcp__<server>__<tool>` in `allowed_tools`, and `try/except` around single-shot `query()` when an error result is expected (it raises after yielding it).
   - Model: `claude-opus-5-5` unless the user names another.
   - Verify every terminal command, flag and argument against the current Claude Code docs (for example `https://code.claude.com/docs/en/cli-reference` and `https://code.claude.com/docs/en/slash-commands`). Don't write command names or flags from memory; if the raw file names one that no longer exists, record the current equivalent and say so in the report.
6. **Add extras only when needed.** List an item as `E1…En` only if it isn't in the raw file but the POC would break or mislead without it. Mark it as an extra.
7. **Write the output file** with exactly the two sections below. No setup guides, starter-code walkthroughs, check-yourself questions, cheat sheets or "real projects" sections; the user removed those on purpose.
8. **Verify before reporting:**
   - Every `C` and `E` ID appears in a POC table, the "Terminal commands" table or the "Already covered" table (grep for each ID).
   - Every "Already covered" or "Builds on" citation points to a file and ID that really exist.
   - No new POC re-teaches something marked "Already covered".
   - Only the two `##` sections exist.
   - Every SDK name, terminal command and flag used was checked in step 5.
   - Any expected numeric value in an Acceptance cell is computed, not guessed (run the arithmetic).
9. **Report briefly:** the POC count and why, how many concepts were new, built on earlier ones, terminal commands or already covered (and by which files), where the file was written, what you verified, and any concept the SDK hides that the user can only observe, not code.

## Output template

```markdown
# <Topic>: Revised POC Requirements (<N> steps → <M> POCs, Claude Agent SDK)

> **Source:** `<NN>-raw-<Topic>.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** <Domain> → <Topic> · **Build with:** Claude Agent SDK for Python (`claude_agent_sdk`)

---

## 1. Verdict: <M> POCs

<Why the raw steps are not <N> separate concepts, in 1–2 sentences.>

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: <name>** | **<mental model>:** <one line> | <steps> |

**What changes with the Agent SDK:** <what the SDK does for you, and how the POCs teach those concepts anyway>

- **Why not fewer POCs:** <reason>
- **Why not more POCs:** <reason>

**Applies to all POCs:** Python 3.10+, `pip install claude-agent-sdk`, `ANTHROPIC_API_KEY` from the environment, mock tools/data only, beginner-friendly code. <Shared `build_options()` code block, with a one-line comment per option.>

---

## 2. Concepts and POC requirements

All <n> concepts in the raw file (C1–C<n>) are covered: <a> new or building on earlier POCs, taught below, <c> terminal commands recorded for the tutorial, and <b> already covered by earlier revised files (see the end of this section).
Previous revised files checked: `<file>`, `<file>`.
Raw step → concepts: **1** → C1–C… · **2** → …
Rows marked **E** are extras that are not in the raw file.

### POC 1: <name>

**Build:** <files, main function signature, return shape, what NOT to include>

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C1 | <concept> (**New**, or **Builds on** `<earlier file>` C<k>) | <exactly what to build: names, prompts, values, SDK calls; reuse earlier files by name> | <observable, checkable result> |

### Terminal commands (for the later tutorial)

| ID | Concept | Command | Important arguments |
|---|---|---|---|
| C<k> | <concept> (**New**, or **Builds on** `<earlier file>` C<j>) | `<command name>`, for example `claude -p` or `/compact` | `<arg>`: <what it does, one line> · `<arg>`: <…> |

### Already covered by earlier POCs

| ID | Concept | Covered in | Check when reused |
|---|---|---|---|
| C<k> | <concept> | `<earlier revised file>` C<j> | <one-line check that it still holds in this topic's POC> |
```

## Writing rules for the tables

- **Requirement:** say exactly what to build: file and function names, SDK options, exact test prompts, mock data. Use made-up entities (like "Nimbus Robotics") when Claude must use a tool rather than answer from memory.
- **Acceptance:** something a builder can check: printed output, an assert, an exact value or an ordering. Use hedged wording ("typically", "such as") only where model output can vary, and never make a test depend on Claude's exact wording.
- When a concept is reused in a later POC, give the row a suffix such as `C6 (in loop)` instead of a new ID.
- Keep the source file's exam vocabulary ("Why", anti-patterns, "deterministic" vs "unreliable").
- If no concept is already covered, keep the "Already covered" heading with the line "None: every concept in this topic is new."
- If no concept is a terminal command, keep the "Terminal commands" heading with the line "None: every concept in this topic is a programming concept."
- **Terminal commands table:** list only the arguments the topic needs or the exam is likely to test, not every flag. Give each argument a one-line meaning and its accepted values where they matter (for example `--output-format`: `text`, `json`, `stream-json`). No tutorial steps yet; those come later.
- Order rows in build order. IDs keep their raw-file order, so they may appear out of sequence.
