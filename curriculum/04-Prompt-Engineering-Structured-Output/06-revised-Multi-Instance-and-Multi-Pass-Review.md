# Multi-Instance and Multi-Pass Review: Revised POC Requirements (5 steps → 1 POC, Claude Agent SDK)

> **Source:** `06-raw-Multi-Instance-and-Multi-Pass-Review.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Prompt Engineering & Structured Output → Multi-Instance and Multi-Pass Review · **Build with:** Claude Agent SDK for Python (`claude_agent_sdk`)

---

## 1. Verdict: 1 POC

The 5 raw steps are not 5 new concepts. Steps 1–3, the single-pass baseline, the per-file passes and the integration pass, are already built and measured in `06-revised-Task-Decomposition-Strategies.md` (domain 01), on a 14-file repo with planted defects. What is new is steps 4–5: **how far to trust each finding**, scored by the reviewer itself and then checked by a second instance.

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: Confidence routing, checked by an independent instance** | **A self-reported confidence is a claim, not a probability:** the multi-pass review of 06 now scores every finding from 0.0 to 1.0 with a reason, a threshold routes each one to the developer or to a human queue, a labelled answer key shows how well the raw scores are calibrated, and a fresh session with no prior context re-judges a subset next to the original reviewer re-checking its own work. Its verdicts move the threshold | 3 (the integration pass reads the findings), 4, 5 |

**What changes with the Agent SDK:** in the SDK, an "instance" is a session. Every `query()` call without `resume` starts a new session with an empty history, so a verifier started that way sees only the code and the findings it is given: no reasoning, no confidence, no "I chose this because". Passing `resume=<session_id>` (from `ResultMessage.session_id`) continues the original reviewer's session with all of that in context. So "independent instance" against "self-review" is a one-option difference in `ClaudeAgentOptions`. A confidence score is whatever the model writes, and nothing in the SDK calibrates it: the POC measures calibration against 06's answer key (a labelled set) and against the independent verdicts. Whether the verifier overturns a finding can only be observed, not coded.

- **Why 1 POC is enough:** routing, labelled calibration and independent verification are one chain over the same findings: the verification needs the review's findings and its session ids in the same process. A second POC would have to rerun the 15 review calls, or receive them through a file.
- **Why not more POCs:** steps 1–3 are already covered (see the end of this section), and step 4's routing has no lesson without step 5's check of the scores it routes on.

**Applies to the POC:** Python 3.10+, `pip install claude-agent-sdk` (a recent 0.2.x; it bundles the Claude Code binary), `ANTHROPIC_API_KEY` set in the environment (never hard-coded), mock data only, and beginner-friendly code (small, commented scripts). The POC reuses from `06-revised-Task-Decomposition-Strategies.md`: `sample_repo/` (the 14-file Fernway Outfitters order service, above the raw file's 10-file PR), `load_repo()`, `format_file()`, `REVIEWER_PROMPT`, the `FILE_REVIEW` item schema, `run_review()` and the answer key (`PLANTED`, `CROSS_FILE`, `REPEATED`, `locate()` and its ±2-line matching rule, 06 E2). Every call gets its options from `confidence_setup.py`:

```python
MODEL = "claude-opus-5-5"
ROUTE_THRESHOLD = 0.8      # raw confidence at or above this goes straight to the developer (C10)
TARGET_PRECISION = 0.9     # a calibrated threshold keeps at least 90% of the findings above it confirmed (C15)
SUBSET = ["checkout.ts", "inventory.ts", "pricing.ts", "users.ts"]  # the files the second instance re-judges

CONFIDENCE_RULE = (" For each issue, also give confidence, a number from 0.0 to 1.0 for how sure you are that it is a "
                   "real defect, and confidence_reason, one sentence on why.")

CONFIDENT_ISSUE = {"type": "object",   # 06's issue item, plus a score and its reason (C9)
                   "required": ["line", "severity", "description", "confidence", "confidence_reason"],
                   "properties": {"line": {"type": "integer"},
                                  "severity": {"type": "string", "enum": ["critical", "major", "minor"]},
                                  "description": {"type": "string"},
                                  "confidence": {"type": "number"},          # range checked in Python
                                  "confidence_reason": {"type": "string"}}}

VERIFY_SCHEMA = {"type": "object", "required": ["verdicts"], "properties": {"verdicts": {"type": "array", "items": {
    "type": "object", "required": ["finding_id", "verdict", "confidence", "reason"],
    "properties": {"finding_id": {"type": "string"}, "verdict": {"type": "string", "enum": ["confirmed", "rejected"]},
                   "confidence": {"type": "number"}, "reason": {"type": "string"}}}}}}

def build_review_options(schema, system_prompt=REVIEWER_PROMPT + CONFIDENCE_RULE, resume=None):
    return ClaudeAgentOptions(
        model=MODEL,                                               # one model for every pass and both verifiers
        system_prompt=system_prompt,                               # the reviewer's prompt, or the verifier's
        output_format={"type": "json_schema", "schema": schema},   # validated JSON in ResultMessage.structured_output
        resume=resume,                                             # None: a fresh session; a session_id: the same reviewer again (C14)
        tools=[],                                                  # no built-in tools: the code is in the prompt
        setting_sources=[],                                        # ignore ~/.claude and project settings, CLAUDE.md and hooks
        env={"ENABLE_TOOL_SEARCH": "false"},                       # no ToolSearch calls
        max_turns=10,                                              # safety cap (01 C16)
    )
```

The confidence buckets used by every table are `[0.0, 0.5)`, `[0.5, 0.8)`, `[0.8, 0.9)` and `[0.9, 1.0]`.

---

## 2. Concepts and POC requirements

All 16 concepts in the raw file (C1–C16) are covered: 9 are new or build on earlier POCs and are taught below, none is a terminal command, and 7 are already covered by `06-revised-Task-Decomposition-Strategies.md` (see the end of this section).
Previous revised files checked: `01-revised-Agentic-Loops.md`, `02-revised-Multi-Agent-Orchestration.md`, `03-revised-Subagent-Invocation-and-Context-Passing.md`, `04-revised-Workflow-Enforcement-and-Handoff.md`, `05-revised-Agent-SDK-Hooks.md`, `06-revised-Task-Decomposition-Strategies.md`, `01-revised-Tool-Interface-Design.md`, `02-revised-Structured-Error-Responses.md`, `03-revised-Tool-Distribution-&-Tool-Choice.md`, `04-revised-MCP-Server-Integration.md`, `05-revised-Built-in-Tools.md`, `01-revised-System-Prompts-with-Explicit-Criteria.md`, `02-revised-Few-Shot-Prompting.md`, `03-revised-Structured-Output-with-Tool-Use.md`, `04-revised-Validation-Retry-and-Feedback-Loops.md`, `05-revised-Batch-Processing-Strategies.md`.
Raw step → concepts: **1** → C1–C3 · **2** → C4–C5 · **3** → C6–C8 · **4** → C9–C12 · **5** → C13–C16.
This topic needs no extras (**E** rows): every row below comes from the raw file.

### POC 1: Confidence routing, checked by an independent instance

**Build:** `confidence_setup.py` and `poc1_confidence_routing.py`.

`confidence_setup.py` copies from 06 `sample_repo/`, `load_repo()`, `format_file()`, `REVIEWER_PROMPT`, the answer key and `run_review()`, and adds the code above plus:
- `run_review()` extended to return `{"output", "session_id"}`, with `session_id` taken from the `ResultMessage` (it is set on every result);
- `FILE_REVIEW_SCHEMA` (06's `FILE_REVIEW` with `issues` made of `CONFIDENT_ISSUE`) and `INTEGRATION_SCHEMA` (06's `cross_file_issues`, each with `confidence` and `confidence_reason`, plus `contradictions`, an array of `{"files", "description"}`);
- `label(item)`: `correct` when a per-file issue lies within 2 lines of a `PLANTED` bug or an X side in its file (06 E2), or within a `REPEATED` snippet ±1 line, or when a cross-file issue names both files of an X pair; `incorrect` otherwise.

`poc1_confidence_routing.py` makes 14 per-file calls and 1 integration call (15), then 4 independent and 4 self-review calls for `SUBSET` (8): 23 calls in all. Each finding gets an id, `<file>#<n>` (n counts from 1 within its file), or `X#<n>` for an integration finding.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C9 | A confidence score from 0.0 to 1.0 on each finding, with the reasoning behind the score (**New**) | Review each file with `build_review_options(FILE_REVIEW_SCHEMA)` and 06's `FILE_PROMPT`. `CONFIDENCE_RULE` asks for both fields, and `CONFIDENT_ISSUE` requires them. Structured outputs don't support `minimum`/`maximum`, so `check_confidence(item)` flags a value outside 0.0–1.0 in Python, as 06 C6 checks line numbers. Print every finding: id, confidence, reason | Every finding has a `confidence` within 0.0–1.0 and a non-empty `confidence_reason`. `check_confidence()` returns no flags (typically) |
| C6 | The cross-file integration pass receives all per-file findings and checks data-flow inconsistencies, contradictory findings across files and API-contract violations (**Builds on** `06-revised-Task-Decomposition-Strategies.md` C8) | `integration_input(reviews)` is 06's per-file summaries plus every file's issues (`line`, `severity`, `description`, `confidence`). The integration prompt is 06's `INTEGRATION_PROMPT` plus `Also list contradictions: places where the per-file findings judge the same code pattern differently.` New compared with 06 C8: the pass also reads the findings, so it can catch two per-file reviews disagreeing | The cross-file issues typically name the pairs of X1 (`pricing.ts`, `checkout.ts`), X2 (`inventory.ts`, `cart.ts`) and X3 (`users.ts`, `auth.ts`). `contradictions` lists any repeated pattern (P1–P3) flagged in only one of its two files, typically none |
| C10 | Routing: high-confidence findings go straight to the developer (`direct_report`), low-confidence ones to a human review queue (`human_review`), and the threshold separates clear-cut findings from uncertain ones (**New**) | `route(item, threshold=ROUTE_THRESHOLD)` returns `direct_report` when `confidence >= threshold`, else `human_review`. Print each finding's route next to its confidence and reason | Every finding has exactly one route, and each route matches its confidence against 0.8 |
| C11 | Confidence-based routing spends limited human reviewer attention on the findings that need it most (**New**) | Print the size of both queues, then the `human_review` queue sorted by confidence, least certain first | The human queue is typically a minority of all findings, so a reviewer reads only the uncertain ones, least certain first |
| C12 | Raw, uncalibrated confidence is not the same as a calibrated threshold validated against a labelled set (**New**) | `calibration_table(items)` prints, per bucket: findings, `correct` by `label()`, and precision. Then print the label precision of the `direct_report` queue | Typically the top buckets are not 100% correct: some findings scored 0.8 or more are not in the answer key. The scores rank findings, but 0.9 doesn't mean "right 9 times in 10" until a labelled set says so |
| C13 | A separate Claude instance (a fresh session with no prior context) reviews a subset of the findings, and its assessment is compared with the original confidence scores (**Builds on** `02-revised-Multi-Agent-Orchestration.md` C10) | `verify_independent(f, items)`, once per `SUBSET` file: a new `query()` (no `resume`) with `system_prompt=VERIFIER_PROMPT` (`You are an independent code reviewer. Another reviewer reported the issues below. For each one, decide from the code alone whether it is a real defect: confirmed or rejected, with your own confidence (0.0 to 1.0) and a one-sentence reason.`), the file's `format_file()` listing and its findings as `id`, `line`, `severity` and `description`, without confidence or reasons. New compared with 02 C10: isolation is used on purpose, so that the verifier can't inherit the reviewer's view | 4 calls, one verdict per finding of the 4 files. The verifier's prompt contains no `confidence` value and no `confidence_reason` |
| C14 | An independent instance approaches the output fresh, without the bias of "I chose this because" reasoning: the limit of self-review (**New**) | `verify_self(f, items)`, once per `SUBSET` file: `resume=<that file's review session_id>` with the prompt `Re-check each issue you reported in this file: is it a real defect? Answer confirmed or rejected for each, with a confidence (0.0 to 1.0) and a one-sentence reason.` and `VERIFY_SCHEMA`. The resumed session holds the reviewer's own reasoning and scores. Print, per arm, the label-incorrect findings it rejected and the label-correct ones it confirmed | The self-review typically confirms its own findings, including incorrect ones, more often than the independent instance does. The independent instance typically rejects more of the label-incorrect findings. If the two arms agree everywhere, record it: on these short files the self-bias may not show |
| C15 | Calibrate confidence thresholds by comparing self-reported confidence with an independent assessment: the method the exam identifies as correct (**New**) | `adjust_threshold(rows)` tries 0.5, 0.8 and 0.9 and returns the lowest one at which at least `TARGET_PRECISION` of the subset's findings scored at or above it were confirmed by the independent instance, or 1.01 (everything to human review) if none qualifies. Print the old and new threshold, and the label precision of the findings above each | One new threshold is printed. Typically it rises above 0.8 when the independent instance overturned findings in the top buckets, and the label precision above it is at least that above 0.8 |
| C16 | The result: a calibration dataset relating reported confidence to independent verification, where some high-confidence findings may be overturned, revealing calibration gaps that move the routing threshold (**New**) | Print the dataset, one row per verified finding: id, reported confidence, self verdict, independent verdict and label. Then the bucket table with the independently confirmed rate per bucket, and `overturned`: findings scored 0.8 or more that the independent instance rejected | Typically at least 1 finding in `overturned`, usually one that `label()` marks incorrect. If none is overturned, record that the top bucket held up at this size, and keep the threshold at 0.8 |

### Terminal commands (for the later tutorial)

None: every concept in this topic is a programming concept.

### Already covered by earlier POCs

| ID | Concept | Covered in | Check when reused |
|---|---|---|---|
| C1 | A single-pass review prompt run against a mock PR of at least 10 files, recording inconsistent depth, missed issues and contradictory findings | `06-revised-Task-Decomposition-Strategies.md` C2, C3 | This POC reviews the same 14-file `sample_repo/` with the same `REVIEWER_PROMPT`, so 06's single-pass trials are the baseline for its per-file findings |
| C2 | The three symptoms of attention dilution: inconsistent depth across files, missed bugs in the middle of the review, and the same pattern judged differently in different files | `06-revised-Task-Decomposition-Strategies.md` C4, C12 | 06's depth table and pattern verdicts measure all three; C6 here checks the third again, across the per-file findings |
| C3 | The expected baseline: detailed feedback on some files (typically the first and last), superficial comments on others, an obvious bug missed in a middle file, and at least one contradictory finding | `06-revised-Task-Decomposition-Strategies.md` C4, C10, C12 | 06's per-position table shows where depth drops, including the middle positions (#5–#10 of 14) |
| C4 | Per-file local analysis: a focused review prompt for each file, examining only that file for bugs, security issues and logic errors | `06-revised-Task-Decomposition-Strategies.md` C5 | This POC's review stage is 06's per-file pass with `CONFIDENCE_RULE` added: one fresh session per file, 14 calls |
| C5 | Per-file passes give every file consistent attention, so bugs the single pass missed, especially in middle files, are caught | `06-revised-Task-Decomposition-Strategies.md` C5, C10 | `label()` shows each file's planted bugs found by this POC's per-file passes: typically 2 of 2 at every position |
| C7 | Per-file analysis misses cross-file concerns: the integration pass is a separate invocation that receives all the findings | `06-revised-Task-Decomposition-Strategies.md` C9 | The integration pass is its own `query()`, and no per-file review names a second file |
| C8 | The integration output names cross-file issues no single-file review can catch: incompatible formats between modules and API contracts violated across boundaries | `06-revised-Task-Decomposition-Strategies.md` C8 | The integration findings typically cover X1 (cents against dollars), X2 (`false` against a throw) and X3 (an email key normalized on one side only); contradictory findings are C6 above |
