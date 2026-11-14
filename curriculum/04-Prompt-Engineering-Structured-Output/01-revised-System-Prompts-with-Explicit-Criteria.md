# System Prompts with Explicit Criteria: Revised POC Requirements (5 steps → 2 POCs, Claude Agent SDK)

> **Source:** `01-raw-System-Prompts-with-Explicit-Criteria.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Prompt Engineering & Structured Output → System Prompts with Explicit Criteria · **Build with:** Claude Agent SDK for Python (`claude_agent_sdk`)

---

## 1. Verdict: 2 POCs

The 5 raw steps are not 5 separate concepts. Steps 1–4 are **one before/after experiment** on one test set: step 1 runs the vague prompt, steps 2 and 3 write two explicit versions, and step 4 scores all three. Step 5 is **a different decision**: what to do when one category of an otherwise precise reviewer is still noisy.

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: Vague words against explicit criteria** | **Precision is written into the prompt, not hoped for:** three system prompts (vague; explicit categories with prose severities; explicit categories with code-example severities) review the same 5 snippets twice, and planted ground truth scores false positives, misses, severities and run-to-run stability | 1, 2, 3, 4 |
| **POC 2: Trust recovery, one category at a time** | **One noisy category costs trust in every category:** per-category false-positive rates of a production prompt, a 25% switch that disables a category, the false-positive rate a developer sees before and after, and the refinement and re-enablement plan | 5 |

**What changes with the Agent SDK:** the SDK sends a plain-string `system_prompt` as the whole system prompt, and `output_format` returns the findings as validated JSON in `ResultMessage.structured_output`. With the model, the schema, the user prompt and the options fixed, the system prompt is the only variable. `ClaudeAgentOptions` has no `temperature`, `top_p` or `seed`, so run-to-run variation can't be switched off: the POCs measure it by running every prompt twice (`RUNS = 2`). Where Claude draws the line between "report" and "skip" can only be observed, not coded: the POCs read it from the findings, scored against planted ground truth. Disabling a category is code: a filter over the findings, so the before/after comparison uses the same findings.

- **Why not 1 POC:** POC 2 starts from POC 1's most precise prompt and loosens one rule. POC 1 must first show that the explicit prompt is precise. Otherwise a noisy category in POC 2 could come from the whole prompt rather than from that one rule, and you couldn't tell which.
- **Why not 3 or more:** steps 2 and 3 are two strings in the same experiment, and step 4 is the scoring of steps 1–3. A POC per prompt would rebuild the snippets, the schema and the scorer three times.

**Applies to both POCs:** Python 3.10+, `pip install claude-agent-sdk` (a recent 0.2.x; it bundles the Claude Code binary), `ANTHROPIC_API_KEY` set in the environment (never hard-coded), mock data only, and beginner-friendly code (small, commented scripts). A review is one `query()` call, streamed like `run_review()` in `06-revised-Task-Decomposition-Strategies.md`, and code enters a prompt only through that file's `format_file()` (a header plus numbered lines, 06 E1).

**The test set.** `snippets/` holds 5 TypeScript files from the order service of Fernway Outfitters, the made-up store of `06-revised-Task-Decomposition-Strategies.md`. Each file is 15–25 lines, its planted spots are at least 5 lines apart, and it has no other defect. `contains` is a substring that appears on exactly one line of its file:

| Spot | File | `contains` | Kind | What it is |
|---|---|---|---|---|
| R1 | `payments.ts` | `WHERE order_id = '" + orderId` | real · security · critical | an SQL string built from user input |
| D1 | `payments.ts` | `var attempts = 0;` | decoy · style | `var` instead of `let` |
| R2 | `payments.ts` | `card.number` | real · security · critical | `console.log("charging card", card.number, amountCents)` logs the card number |
| R3 | `checkout.ts` | `order.status = "paid"` | real · bug · critical | assignment inside `if`: every order counts as paid and ships |
| D2 | `checkout.ts` | `void auditLog.write` | decoy · local pattern | fire-and-forget audit write, on purpose |
| R4 | `checkout.ts` | `line.quantity += qty` | real · bug · major | the line above is an unchecked `cart.lines.find(...)`: crashes for a SKU not in the cart |
| R5 | `inventory.ts` | `if (isReserved(sku))` | real · bug · major | `isReserved` is `async`, so the Promise is always truthy |
| D3 | `inventory.ts` | `units < 5 ? "low"` | decoy · style | a nested ternary |
| R6 | `inventory.ts` | `i <= bins.length` | real · bug · major | off by one: reads `bins[bins.length].count` and throws |
| R7 | `discounts.ts` | `getMonth()` | real · bug · minor | the zero-based month is shown as `Promo for month 9` in October |
| R8 | `discounts.ts` | `return codes.sort();` | real · comment mismatch · minor | the comment above says `Returns a sorted copy; the input array is not modified.` |
| D4 | `discounts.ts` | `TODO: load promo codes` | decoy · comment | a TODO that contradicts nothing |
| D6 | `shipping.ts` | `2025 carrier contract` | decoy · comment | `// Rates from the 2025 carrier contract.`: dated, but contradicts nothing |
| D7 | `shipping.ts` | `function calc_rate` | decoy · style | a snake_case function name |
| D5 | `shipping.ts` | `zone == null` | decoy · local pattern | `== null` tests null and undefined together, on purpose |
| R9 | `shipping.ts` | `subtotal > 50` | real · bug · minor | the comment above says `Orders of $50 or more ship free.`, so exactly $50 is charged |

That is 9 real defects (3 critical, 3 major, 3 minor) and 7 decoys (3 style, 2 local pattern, 2 comment). Every review gets its options and prompts from `criteria_setup.py`:

```python
MODEL = "claude-opus-5-5"
RUNS = 2  # ClaudeAgentOptions has no temperature or seed: variation is measured by running each prompt twice

REVIEW_SCHEMA = {"type": "object", "required": ["findings"], "properties": {"findings": {"type": "array", "items": {
    "type": "object",
    "properties": {
        "file": {"type": "string"},
        "line": {"type": "integer"},
        "category": {"type": "string", "enum": ["bug", "security", "comment_mismatch", "style", "other"]},  # E1
        "severity": {"type": "string", "enum": ["critical", "major", "minor"]},
        "description": {"type": "string"},
    },
    "required": ["file", "line", "category", "severity", "description"]}}}}

def build_review_options(system_prompt):
    return ClaudeAgentOptions(
        model=MODEL,                                                    # one model for every prompt version
        system_prompt=system_prompt,                                    # the ONLY thing that changes between versions
        output_format={"type": "json_schema", "schema": REVIEW_SCHEMA}, # the same findings shape for every version (E1)
        tools=[],                                                       # no built-in tools: the code is in the prompt
        setting_sources=[],                                             # ignore ~/.claude and project settings, CLAUDE.md and hooks
        env={"ENABLE_TOOL_SEARCH": "false"},                            # no ToolSearch calls
        max_turns=10,                                                   # safety cap (01 C16)
    )
```

The prompts:

```python
VAGUE_PROMPT = ("You are a code reviewer for the Fernway Outfitters order service. Review the TypeScript files below. "
                "Be conservative and only flag important issues. For each issue, give the file, the line number from "
                "the numbered listing, a category, a severity and a one-sentence description.")

COMMENT_RULE = ("a comment whose claimed behaviour contradicts what the code actually does. Flag a comment only then; "
                "never a TODO, a note, or a comment that is merely out of date.")
SEVERITY_PROSE = ("Severity: critical means issues that could cause system failures, security breaches or wrong charges; "
                  "major means wrong behaviour or a crash on a common path; minor means wrong behaviour only in a rare "
                  "edge case.")
SEVERITY_EXAMPLES = (  # code patterns, not prose (C10); none of them is in the test set
    "Severity is defined by these code patterns:\n"
    '<example severity="critical">exec("convert " + req.query.file + " thumb.png");  // user input reaches a shell</example>\n'
    '<example severity="critical">logger.debug("session", { token: session.accessToken });  // a secret in the logs</example>\n'
    '<example severity="major">const total = lines.reduce((sum, l) => sum + l.price);  // throws on an empty cart</example>\n'
    '<example severity="major">const body = JSON.parse(req.body);  // throws on any malformed request</example>\n'
    '<example severity="minor">// Orders of 10 items or more get a free tote.\nif (items.length > 10) addTote(order);</example>\n'
    '<example severity="minor">const day = new Date().getDay();  // weekday 0-6, printed as the day of the month</example>')

def criteria_prompt(severity_rules):
    return ("You are a code reviewer for the Fernway Outfitters order service. Review the TypeScript files below.\n"
            "REPORT only these categories:\n"
            "- bug: code that does the wrong thing, crashes or loses data for some input.\n"
            "- security: input or logs that can expose or change data they shouldn't, such as injection or leaked secrets.\n"
            f"- comment_mismatch: {COMMENT_RULE}\n"
            "SKIP, never report:\n"
            "- style preferences: naming, var versus let, formatting, nested ternaries, line length.\n"
            "- local patterns this codebase uses on purpose: `== null` to test null and undefined together, and `void` "
            "before a fire-and-forget call such as an audit log write.\n"
            f"{severity_rules}\n"
            "For each issue, give the file, the line number from the numbered listing, the category, the severity and "
            "a one-sentence description.")

CRITERIA_PROMPT = criteria_prompt(SEVERITY_PROSE)      # step 2: explicit categories, prose severities
EXAMPLES_PROMPT = criteria_prompt(SEVERITY_EXAMPLES)   # step 3: the same, with code examples instead of prose
```

---

## 2. Concepts and POC requirements

All 18 concepts in the raw file (C1–C18) are covered: all 18 are new or build on earlier POCs and are taught below, none is a terminal command, and none was already covered by an earlier revised file (see the end of this section).
Previous revised files checked: `01-revised-Agentic-Loops.md`, `02-revised-Multi-Agent-Orchestration.md`, `03-revised-Subagent-Invocation-and-Context-Passing.md`, `04-revised-Workflow-Enforcement-and-Handoff.md`, `05-revised-Agent-SDK-Hooks.md`, `06-revised-Task-Decomposition-Strategies.md`, `01-revised-Tool-Interface-Design.md`, `02-revised-Structured-Error-Responses.md`, `03-revised-Tool-Distribution-&-Tool-Choice.md`, `04-revised-MCP-Server-Integration.md`, `05-revised-Built-in-Tools.md`. None teaches review criteria in a system prompt: 06 uses one fixed reviewer prompt, and `01-revised-Tool-Interface-Design.md` POC 2 varies a system prompt only for tool-routing keywords.
Raw step → concepts: **1** → C1–C6 · **2** → C7–C9 · **3** → C10–C11 · **4** → C12–C14 · **5** → C15–C18.
Rows marked **E** are extras that are not in the raw file. Without them, the POC breaks or gives misleading results.

### POC 1: Vague words against explicit criteria

**Build:** `snippets/` (the 5 files above), `criteria_setup.py` and `poc1_vague_vs_explicit.py`.

`criteria_setup.py` holds everything both POCs share:
- `load_snippets()` (the 5 files, sorted by name) and `format_file()`, copied from 06;
- `PLANTED` (16 entries `{"id", "file", "contains", "kind", "severity"}`, where `kind` is `real` or `decoy`) and `locate(file, contains)`;
- `REVIEW_SCHEMA`, the prompts and `build_review_options()` (code above);
- `async def review(system_prompt)`: one `query()` with `REVIEW_TASK = "Review these 5 files of the order service.\n\n"` plus the 5 listings, streamed inside `try/except` (a single-shot `query()` raises after yielding an error result). It returns `structured_output["findings"]`, or `None` when there is no structured output;
- `score_run(findings)`: returns `{"fp", "total", "verdicts", "fp_spots"}`, using the matching rule of 06 E2: a finding matches a spot in the same file when its `line` is within 2 of the spot's line. A finding that matches a decoy, or no spot at all, is a false positive. `verdicts` maps each spot to its verdict: a real spot gets the reported severity or `missed`, and a decoy gets `flagged` or `skipped`;
- `summarize(runs)`: returns `{"fp_rate", "inconsistency", "stable", "severity_accuracy"}` for one prompt's runs.

`poc1_vague_vs_explicit.py` runs `review()` `RUNS` times for each of `VAGUE_PROMPT`, `CRITERIA_PROMPT` and `EXAMPLES_PROMPT` (6 calls), and prints the per-run verdicts and the comparison table. With `RUNS = 2` there are 16 × 2 = 32 verdicts per prompt.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C2 | A test set of 5 code snippets with known bugs, security issues and style nitpicks (**Builds on** `06-revised-Task-Decomposition-Strategies.md` E2) | Write `snippets/` and `PLANTED` as in the table above. `locate()` finds each spot's line from `contains`, so no line number is hard-coded (06 E2). New compared with 06 E2: 7 of the 16 spots are decoys, things a precise reviewer must **not** report | Every `contains` is on exactly 1 line of its file. `PLANTED` has 9 real spots (3 critical, 3 major, 3 minor) and 7 decoys (3 style, 2 local pattern, 2 comment), and in each file the spots are at least 5 lines apart, so a finding can match only one spot |
| E1 | Every prompt version fills the same schema, and its `category` enum includes `style` and `other` | All versions use `REVIEW_SCHEMA` (code above). Its enum lists `style` and `other`, so the vague prompt **can** report a style nitpick. If the schema left them out, the schema itself would filter the vague prompt's noise, and the comparison would measure the schema instead of the prompt | Code review: one `REVIEW_SCHEMA`, and `build_review_options()` takes only the system prompt |
| C1 | A system prompt with vague instructions: "be conservative", "only flag important issues" (**New**) | `VAGUE_PROMPT` (code above): a role, the two vague phrases and the output fields, with no category list and no severity definition. Run `review(VAGUE_PROMPT)` `RUNS` times | Both runs end with `success` and a `findings` list. `VAGUE_PROMPT` names no category and defines no severity |
| C3 | The vague baseline demonstrates the false-positive problem the exam tests (**New**) | For each vague run, print `score_run()`'s false-positive rate (`fp / total`) and each false positive with its spot id, or `unmatched` | Typically at least 1 false positive across the 2 runs, such as D5 (`== null` reported as a bug), D2 (`void` reported as an unhandled promise) or a style decoy, under category `style`, `bug` or `other` |
| C4 | Phrases like "be conservative" give the model no actionable decision boundary; you need empirical evidence of that (**New**) | For each vague run, print one line per spot with its verdict (`R6: major`, `R7: missed`, `D3: flagged`, ...). Nothing in "important" says which category or severity counts, so the verdicts are the only evidence of where Claude drew the line | The vague verdicts typically go wrong in both directions at once: at least one decoy `flagged` and at least one real defect `missed`, so no single "conservative" threshold explains them |
| C5 | Inconsistent classification across the snippets: style nitpicks flagged as critical, genuine bugs missed or marked minor (**New**) | For every prompt, print the real spots that were missed and those reported with a severity other than `PLANTED`'s, and any decoy reported as `critical` or `major` | Vague: typically 1 or more real defects missed (often a minor one, such as R7 or R8) or reported with the wrong severity |
| C6 | Different results when the same snippets run twice (**New**) | Run each prompt `RUNS = 2` times (the SDK has no setting that makes runs identical). `summarize()`'s `stable` counts the spots whose verdict is the same in both runs | Vague: typically at least 1 of the 16 spots changes its verdict between the two runs |
| C7 | Explicit categorical criteria: report bugs and security vulnerabilities, skip style preferences and local patterns (**New**) | `CRITERIA_PROMPT` (code above): a REPORT list (`bug`, `security`, `comment_mismatch`) and a SKIP list (style preferences, and the two local patterns by name) | The prompt has both lists. The criteria runs typically report no finding with category `style` or `other`, and skip D1, D2, D3, D5 and D7 |
| C8 | Flag a comment only when its claimed behaviour contradicts what the code actually does (**New**) | `COMMENT_RULE` is the definition of `comment_mismatch` in the REPORT list | Criteria runs: R8 is typically reported (as `comment_mismatch` or `bug`), while D4 and D6 are skipped |
| C9 | Explicit criteria are the correct approach tested on the exam: concrete categories remove the ambiguity that causes false positives (**New**) | Print the false-positive rate of the vague runs next to that of the criteria runs | Typically lower for the criteria runs, often 0 |
| C10 | Concrete code examples for each severity level (critical, major, minor), showing actual code patterns, not prose (**New**) | `SEVERITY_EXAMPLES` (code above) has 2 code examples per level, none of them copied from the test set. `EXAMPLES_PROMPT = criteria_prompt(SEVERITY_EXAMPLES)` replaces the prose severities and changes nothing else | `EXAMPLES_PROMPT` has at least 1 `<example severity="...">` per level, and `EXAMPLES_PROMPT.replace(SEVERITY_EXAMPLES, SEVERITY_PROSE) == CRITERIA_PROMPT` |
| C11 | Code examples outperform prose for severity calibration: prose like "issues that could cause system failures" forces the model to interpret, code removes the ambiguity (**New**) | Print `severity_accuracy` (real spots reported with `PLANTED`'s severity, divided by real spots reported) for the criteria runs and the examples runs, and list each real spot whose severity differs | Typically examples ≥ criteria, with any gap on the major/minor boundary, such as R9 or R6 rated one level off under the prose rules |
| C12 | Compare false-positive rates between the versions on the same test set, and document which one classifies more consistently (**Builds on** `01-revised-Tool-Interface-Design.md` C5) | `summarize()` gives, per prompt: `fp_rate` (false positives / findings over both runs), `inconsistency` (wrong verdicts / 32; a verdict is right when a real spot has its `PLANTED` severity and a decoy is `skipped`), `stable` (of 16) and `severity_accuracy`. Print one table with 3 rows. New compared with 01 C5: the measure is precision and run-to-run consistency, not tool-selection accuracy | 3 rows, all over the same 16 spots × 2 runs |
| C13 | Quantifying the improvement validates the approach: say why one version wins with data, not intuition (**Builds on** `01-revised-Tool-Interface-Design.md` C11) | Under the table, print `Same model, schema, snippets and options: only the system prompt changed`. New compared with 01 C11: the evidence is a precision table, not a selection count | The line is printed once, under the table |
| C14 | Expected numbers: vague 30–50% inconsistency, explicit below 15%, and stable across repeated runs (**New**) | No extra code: read the C12 table | Vague typically 10–16 of 32 verdicts wrong (30–50%). Examples typically at most 4 of 32 (12.5%; 5 would be 15.6%), with typically at least 14 of 16 spots stable. If the vague prompt already scores below 30%, record it: the false-positive and severity rows still show the direction |

### POC 2: Trust recovery, one category at a time

**Build:** `poc2_trust_recovery.py`, reusing `criteria_setup.py`. It defines `LOOSE_COMMENT_RULE`, `PRODUCTION_PROMPT`, `COMMENT_EXAMPLES`, `REFINED_PROMPT`, `THRESHOLD = 0.25`, `TARGET_FP = 0.10`, `REFINEMENTS`, `category_table(runs)`, `visible(findings, disabled)` and `report(table, disabled)`. It runs `review(PRODUCTION_PROMPT)` `RUNS` times and `review(REFINED_PROMPT)` once (3 calls).

```python
LOOSE_COMMENT_RULE = "any comment that is outdated, incomplete or could be clearer, including TODOs."
PRODUCTION_PROMPT = EXAMPLES_PROMPT.replace(COMMENT_RULE, LOOSE_COMMENT_RULE)   # E2: one loosely written rule
COMMENT_EXAMPLES = (" For example, flag `// returns the price in dollars` above `return priceCents;`, but skip "
                    "`// TODO: cache this` and `// limits from the 2024 policy`.")
REFINED_PROMPT = EXAMPLES_PROMPT.replace(COMMENT_RULE, COMMENT_RULE + COMMENT_EXAMPLES)  # the refinement (C17)
REFINEMENTS = {"comment_mismatch": "Use the contradiction-only rule and add code examples of comments to flag and to "
                                   "skip (TODOs, dated notes)."}
```

The worked example used in the acceptance cells: pooled over 2 runs, `bug` has 12 findings with 0 false positives, `security` 4 with 0, and `comment_mismatch` 6 with 4 (D4 and D6 in both runs): 4 / 6 = 66.7%.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| E2 | Step 5 needs a category above 25% | `PRODUCTION_PROMPT` (code above) is the scenario's production reviewer: `EXAMPLES_PROMPT` with one loosely written rule. Without it, POC 1's explicit prompt may leave every category under 25%, and step 5 would have nothing to disable | `PRODUCTION_PROMPT` differs from `EXAMPLES_PROMPT` only in the comment rule |
| C15 | Temporarily disable any category with a false-positive rate above 25% (**New**) | `category_table(runs)` pools the production runs and returns, per reported category, its findings, its false positives and its rate. `disabled = [c for c, row in table.items() if row["rate"] > THRESHOLD]`. `visible(findings, disabled)` drops the findings of disabled categories: the switch is a filter in code, so before and after use the same findings. Print the table and `disabled` | Worked example: `disabled == ["comment_mismatch"]`. Live: typically `comment_mismatch` is the only category above 25% (D4 and D6 flagged), and `bug` and `security` are typically at 0% |
| C16 | Trust recovery: high false-positive rates in one category destroy developer trust in all categories, and disabling that category restores system-wide trust while you iterate (**New**) | Print the false-positive rate of everything the developer sees, before and after `visible()`, and how many production runs showed the developer at least one false positive. Also print `collateral`: the real spots whose only matching findings were in a disabled category | Worked example: 4 / 22 = 18.2% before, 0 / 16 = 0.0% after. Live: typically 0 runs with a false positive after the switch. `collateral` typically lists R8: the price of the switch is a real defect that stays hidden until the category is re-enabled |
| C17 | Document the criteria refinements needed before re-enabling, such as code examples for edge cases (**New**) | `report(table, disabled)` prints, per disabled category: its rate, the spot ids of its false positives, and its entry in `REFINEMENTS` | One block per disabled category, typically only `comment_mismatch`, naming D4 and D6 and its refinement |
| C18 | A re-enablement plan with target false-positive rates (**New**) | `report()` ends each block with the plan: `re-enable when the refined criteria score at most 10% false positives in this category and still find its real defects`. Then run `review(REFINED_PROMPT)` once, compute that category's rate with `category_table()`, and print `re-enable comment_mismatch: yes` or `no` | Typically `yes`: 0 of the refined run's comment findings are false positives, and R8 is found |

### Terminal commands (for the later tutorial)

None: every concept in this topic is a programming concept.

### Already covered by earlier POCs

None: every concept in this topic is new or builds on an earlier POC (cited in its row).
