# Codebase Exploration and Context Degradation: Revised POC Requirements (5 steps → 2 POCs, Claude Agent SDK)

> **Source:** `04-raw-Codebase-Exploration-Context-Degradation.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Context Management & Reliability → Codebase Exploration and Context Degradation · **Build with:** Claude Agent SDK for Python (`claude_agent_sdk`)

---

## 1. Verdict: 2 POCs

The 5 raw steps are not 5 separate concepts. They are four ways to carry what an exploration has learned across a boundary that would otherwise lose it, plus a test of one of them. Two boundaries lie **between agents**: step 1 turns a subagent's verbose exploration into a short structured report for the coordinator, and step 3 turns Phase 1 into a summary injected into Phase 2. The other two lie **across time**: step 2's scratchpad file keeps knowledge through a lossy history, and step 4's manifest keeps progress through a crash. Step 5 tests the scratchpad.

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: Delegate, then hand Phase 1 to Phase 2** | **Only structured summaries cross between agents:** a coordinator that can't read files delegates 3 focused exploration tasks to subagents with read-only tools. Its context grows by 3 short JSON reports, while a single agent doing the same work carries every file it read. Its Phase 1 summary is then injected into each Phase 2 subagent's prompt, and the same Phase 2 tasks without it start cold and repeat Phase 1's searches | 1, 3 |
| **POC 2: Write it down: a scratchpad and a manifest** | **What must outlive the context goes to a file:** an explorer works through 6 modules. With a scratchpad, it writes exact class names and paths as it goes and reads them back before each step, so it still lists all 18 classes after its history has been summarised. Without one, it falls back to "the typical layered pattern". A manifest checkpointed after every module lets a crashed run resume at module 4 instead of starting again | 2, 4, 5 |

**What changes with the Agent SDK:** delegation and isolation are built in. A subagent defined with `AgentDefinition` runs in its own conversation, and "intermediate tool calls and results stay inside the subagent; only its final message returns to the parent". The stream still shows a subagent's tool calls (with `parent_tool_use_id` set), but the coordinator model never sees them: its context grows only by each Agent result. Claude Code's built-in `Explore` subagent is made for this job ("A fast, read-only agent optimized for searching and analyzing codebases"). But it is one-shot and returns free text, so POC 1 defines three subagents with a report format instead.

What the SDK doesn't do is carry knowledge across sessions. Each `query()` "starts fresh with no memory of previous interactions", and nothing in the SDK hands a Phase 1 summary to Phase 2, keeps a scratchpad, or checkpoints progress: those are your code. The SDK can `resume` a session by its `session_id`, but that restores the whole conversation, the same context that degraded or ran out; the manifest instead restarts from compact structured state in a fresh session.

Context degradation itself can only be observed, not coded. A strong model doesn't lose the names from 6 small modules inside one context, so POC 2 simulates the loss as `01-revised-Context-Window-Management.md` did: after module 4, Python replaces the history with a fixed lossy summary. That summary is the generic end state the exam describes.

- **Why not 1 POC:** POC 1 is about several agents at one moment (who sees what), and POC 2 is about one agent over time (what survives a loss). They need different harnesses: POC 1 needs a coordinator with subagents and a single-agent baseline, while POC 2 needs a step-by-step driver that owns the history, summarises it and crashes on purpose. In one POC, a missing class name could come from a subagent's report, a lossy summary or a crash, and you couldn't tell which.
- **Why not 3 or more:** step 3's injection needs step 1's reports to summarise, so they share one pipeline. Step 5 only tests step 2. Step 4's manifest is written by the same explorer, after the same steps, with the same kind of file tool as the scratchpad, so a separate POC would rebuild the repo, the explorer and the driver for one more file.

**Applies to both POCs:**
- **Setup:** Python 3.10+, `pip install claude-agent-sdk` (a recent 0.2.x; it bundles the Claude Code binary), and `ANTHROPIC_API_KEY` set in the environment (never hard-coded). Mock data only, and beginner-friendly code (small, commented scripts).
- **Runners:** POC 1 runs through `run_coordinator()` from `02-revised-Multi-Agent-Orchestration.md` (`coordinator.py`), as extended in `03-revised-Subagent-Invocation-and-Context-Passing.md` and `06-revised-Task-Decomposition-Strategies.md` (`options=`, `research_calls` from any tool, `prompt_tokens`), and extended once more in POC 1's Build. POC 2 runs through `run_agent()` from `01-revised-Agentic-Loops.md` (`poc2_agent_loop.py`), as extended in `05-revised-Agent-SDK-Hooks.md` (`options=`, `tool_results`).
- **Parsing:** reports are parsed with `parse_json_object()`, copied from `03-revised-Subagent-Invocation-and-Context-Passing.md` (E2).
- **Tools:** the custom tools follow `tools.py` from `01-revised-Agentic-Loops.md` (C2–C3).

**The mock repo** (`explore_repo/`) is a TypeScript service of Lumen Home, the made-up store of `01-revised-Tool-Interface-Design.md`. It is never compiled or run. It has 23 files: 18 classes in 18 files, `src/repos/base.ts` (`interface Repository<T>`), and 4 tests:

| Module | File | Class | What it is |
|---|---|---|---|
| orders | `src/repos/order.ts` | `OrderRepository` | implements `Repository<Order>` |
| orders | `src/services/order.ts` | `OrderService` | uses `OrderRepository`, `StockKeeper` and `PaymentLedger` |
| orders | `src/http/checkout.ts` | `CheckoutController` | an HTTP entry point; uses `OrderService` |
| payments | `src/repos/payment.ts` | `PaymentLedger` | implements `Repository<Payment>` |
| payments | `src/services/refund.ts` | `RefundDesk` | uses `PaymentLedger` and `PayFluxClient`; `issueRefund()` awaits `this.payflux.refund(...)` with no try/catch |
| payments | `src/clients/payflux.ts` | `PayFluxClient` | calls the PayFlux payments API |
| inventory | `src/repos/stock.ts` | `StockKeeper` | implements `Repository<StockItem>` |
| inventory | `src/services/reorder.ts` | `ReorderPlanner` | uses `StockKeeper` and `SupplierBridge` |
| inventory | `src/clients/supplier.ts` | `SupplierBridge` | calls the Kestrel Supply EDI feed |
| shipping | `src/repos/shipment.ts` | `ShipmentStore` | implements `Repository<Shipment>` |
| shipping | `src/services/dispatch.ts` | `DispatchService` | uses `ShipmentStore`, `ParcelHubClient` and `OrderRepository` |
| shipping | `src/clients/parcelhub.ts` | `ParcelHubClient` | calls the ParcelHub carrier API |
| notifications | `src/repos/notice.ts` | `NoticeQueue` | implements `Repository<Notice>` |
| notifications | `src/services/notify.ts` | `NotifyService` | uses `NoticeQueue` and `MailRelay` |
| notifications | `src/clients/mailrelay.ts` | `MailRelay` | calls the Postwick email API |
| customers | `src/repos/customer.ts` | `CustomerDirectory` | implements `Repository<Customer>` |
| customers | `src/services/profile.ts` | `ProfileService` | uses `CustomerDirectory` |
| customers | `src/http/account.ts` | `AccountController` | an HTTP entry point; uses `ProfileService` |

The tests are `tests/order.test.ts` (`OrderService`), `tests/refund.test.ts` (`RefundDesk`), `tests/dispatch.test.ts` (`DispatchService`) and `tests/profile.test.ts` (`ProfileService`). Rules for the mock files:
- Most class names are not the "typical" ones. `PaymentLedger`, `RefundDesk`, `StockKeeper`, `ReorderPlanner`, `SupplierBridge`, `ShipmentStore`, `ParcelHubClient`, `NoticeQueue`, `MailRelay` and `CustomerDirectory` can't be guessed from a pattern such as "`<Noun>Repository` in `src/repos/<noun>.ts`".
- Every client call except the one in `RefundDesk.issueRefund()` sits inside a `try` block.
- Each source file is 60–100 lines (doc comments, types and helpers), so reading one costs a few thousand characters.
- No comment states a finding (no "untested", no "TODO").

The ground truth is computed by regular expressions in `explore_setup.py`, never hard-coded:
- `CLASSES`: each class with its file;
- `USES`: the classes each one imports;
- `TESTED`: the classes a test imports;
- `CLIENTS`: the classes in `src/clients/`;
- `UNTESTED_INTEGRATIONS`: services that import a client and that no test imports, which gives `ReorderPlanner` and `NotifyService`;
- `UNHANDLED`: service files that call a client and contain no `try`, which gives `src/services/refund.ts`.

**POC 1's agents and options**, in `explore_setup.py`:

```python
MODEL = "claude-opus-5-5"
REPO_DIR = Path(__file__).resolve().parent / "explore_repo"
FILE_TOOLS = ["Read", "Grep", "Glob"]   # read-only built-ins; on Linux, Grep and Glob must be named (02-05 E1)

REPORT_FORMAT = (
    'Your final message must be only a JSON object {"task": "<task id>", "classes": [{"name": "...", "file": "..."}], '
    '"facts": ["..."]}. classes: every class your answer involves, with its exact file path. facts: one line per '
    'finding, such as "CheckoutController (src/http/checkout.ts) -> OrderService (src/services/order.ts)". '
    "Never paste file contents.")

PHASE1_TASKS = {
    "tests": "Find every test file and the class each one tests.",
    "dependencies": ("Trace every dependency chain from an entry point (an HTTP controller, or a service that no "
                     "other class uses) down to repositories and external clients."),
    "integrations": "Identify every class that calls an outside service, which service it calls, and which classes use it.",
}
PHASE2_TASKS = {
    "payment_errors": "Find where an error thrown by the PayFlux client can reach a caller without being handled.",
    "untested_integrations": "List every service that uses an external client but has no test file.",
}

def explorer(role, task_id):
    return AgentDefinition(
        description=f"{role} Use it for the '{task_id}' task.",
        prompt=f"You explore the Lumen Home TypeScript service in your working directory. {role} " + REPORT_FORMAT,
        tools=FILE_TOOLS,     # read-only: it can search and read, never edit
        model="inherit",
        maxTurns=15,          # a narrow task fits well inside this (C1)
    )

AGENTS = {
    "test-finder": explorer("You find test files and the classes they test.", "tests"),
    "dependency-tracer": explorer("You trace which classes depend on which.", "dependencies"),
    "integration-scout": explorer("You find the classes that call outside services.", "integrations"),
}

COORDINATOR_PROMPT = (
    "You coordinate an exploration of the Lumen Home TypeScript service. You never read files yourself. Give each "
    "Phase 1 task to its subagent with the Agent tool, all three in one response, as 'task: <id>' plus the task "
    "text. When the three reports are in, write the Phase 1 summary from them only: the architecture in at most 5 "
    "sentences, every dependency chain, the key concerns, and, for each Phase 2 task, one specific objective that "
    "names the classes and files to start from. Keep it short: Phase 2 needs context, not the reports.")

PHASE1_SCHEMA = {  # the Phase 1 summary document (C10)
    "type": "object", "required": ["architecture", "dependency_chains", "key_concerns", "phase2_objectives"],
    "properties": {
        "architecture": {"type": "string"},
        "dependency_chains": {"type": "array", "items": {"type": "string"}},
        "key_concerns": {"type": "array", "items": {"type": "string"}},
        "phase2_objectives": {"type": "array", "items": {"type": "object", "required": ["task", "objective"],
            "properties": {"task": {"type": "string", "enum": list(PHASE2_TASKS)}, "objective": {"type": "string"}}}}}}

def build_phase1_options():
    return ClaudeAgentOptions(
        model=MODEL,
        system_prompt=COORDINATOR_PROMPT,
        output_format={"type": "json_schema", "schema": PHASE1_SCHEMA},  # the summary as validated JSON
        cwd=str(REPO_DIR),                                 # the subagents' file tools work on the mock repo
        tools=["Agent"] + FILE_TOOLS,                      # file tools must be in the session for subagents to use them
        agents=AGENTS,                                     # the three explorers
        allowed_tools=["Agent"] + FILE_TOOLS,              # no permission prompts
        disallowed_tools=["Agent(fork)"],                  # no forks: a fork inherits the coordinator's context (01-02 E1)
        hooks={"PreToolUse": [HookMatcher(matcher="Read|Grep|Glob", hooks=[coordinator_scope])]},  # E1
        setting_sources=[],                                # ignore ~/.claude and project settings, CLAUDE.md and hooks
        env={
            "ENABLE_TOOL_SEARCH": "false",                 # load tool schemas upfront: no ToolSearch calls
            "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",   # each Agent result holds the report (01-02 E2)
            "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",  # no built-in Explore or general-purpose: only our three (01-02 E3)
        },
        max_turns=20,                                      # safety cap (01 C16)
    )

def build_solo_options(system_prompt, schema=None):
    # One agent with the file tools and no subagents: POC 1's baseline and each Phase 2 task
    return ClaudeAgentOptions(
        model=MODEL, system_prompt=system_prompt, cwd=str(REPO_DIR),
        output_format={"type": "json_schema", "schema": schema} if schema else None,
        tools=FILE_TOOLS, allowed_tools=FILE_TOOLS, setting_sources=[],
        env={"ENABLE_TOOL_SEARCH": "false"}, max_turns=30,
    )
```

`coordinator_scope` follows the hook of the same name in `03-revised-Tool-Distribution-&-Tool-Choice.md` (`poc2_pipeline.py`). A file-tool call with no `agent_id` was made by the coordinator itself, so the hook denies it with `The coordinator never reads files: delegate with the Agent tool.`

**POC 2's explorer**, also in `explore_setup.py`:

```python
MODULE_PLAN = {  # module -> its 3 files, in exploration order
    "orders": ["src/repos/order.ts", "src/services/order.ts", "src/http/checkout.ts"],
    "payments": ["src/repos/payment.ts", "src/services/refund.ts", "src/clients/payflux.ts"],
    "inventory": ["src/repos/stock.ts", "src/services/reorder.ts", "src/clients/supplier.ts"],
    "shipping": ["src/repos/shipment.ts", "src/services/dispatch.ts", "src/clients/parcelhub.ts"],
    "notifications": ["src/repos/notice.ts", "src/services/notify.ts", "src/clients/mailrelay.ts"],
    "customers": ["src/repos/customer.ts", "src/services/profile.ts", "src/http/account.ts"],
}
PHASES = {"phase 1: core modules": ["orders", "payments", "inventory", "shipping"],
          "phase 2: edge modules": ["notifications", "customers"]}
SUMMARISE_AFTER = 4   # after module 4, Python replaces the history with LOSSY_HISTORY (E3)
CRASH_AFTER = 3       # the crash-resume run dies after module 3 (C12)

EXPLORER_PROMPT = (
    "You explore the Lumen Home TypeScript service in your working directory, one module per step, in this order: "
    "orders, payments, inventory, shipping, notifications, customers. Each message starts with what is known from "
    "earlier steps. Read only the files the step names.")
SCRATCHPAD_RULE = (  # step 2: part of the prompt from the very first step (C7)
    " Keep a scratchpad from the very first step: call read_notes at the start of every step, and after each "
    "discovery call note with exact entries, such as 'OrderRepository — src/repos/order.ts — implements "
    "Repository<Order>'. Never write a summary such as 'follows the usual pattern'.")
CHECKPOINT_RULE = (  # step 4
    " At the end of every step, call checkpoint with the files you explored, your key findings and the modules "
    "still to explore, so the exploration can resume after a crash.")

STEP_TASK = ("Explore the {module} module: {files}. For each class, give its exact name, its file, what it implements "
             "or extends, and what it depends on. End with one line per class: ClassName — path — relation.")
FINAL_TASK = ("List every class you discovered in this exploration, across all modules, one per line as "
              "ClassName — path. Don't open any source file.")
LOSSY_HISTORY = ("Steps 1-4 explored the orders, payments, inventory and shipping modules. Each one follows the "
                 "typical layered pattern: a repository for data access, a service with the business logic, and in "
                 "some modules a client for an outside service.")

@dataclass
class ExploreState:  # one per run; the files live in run_dir
    run_dir: Path                                                          # work/<run>/: scratchpad.md and manifest.json
    exploration_id: str = field(default_factory=lambda: uuid.uuid4().hex)  # the manifest's sessionId
    phase: str = ""                                                        # set by the driver before each step
    checkpoints: int = 0

def build_explorer_options(state, scratchpad=False, checkpoints=False, final=False):
    servers, allowed = {}, ([] if final else ["Read"])
    if scratchpad:
        servers["notes"] = build_notes_server(state)
        allowed += ["mcp__notes__note", "mcp__notes__read_notes"]
    if checkpoints and not final:
        servers["progress"] = build_progress_server(state)
        allowed += ["mcp__progress__checkpoint"]
    return ClaudeAgentOptions(
        model=MODEL,
        system_prompt=EXPLORER_PROMPT + (SCRATCHPAD_RULE if scratchpad else "") + (CHECKPOINT_RULE if checkpoints else ""),
        cwd=str(REPO_DIR),
        tools=[] if final else ["Read"],   # each step names its files, so Read is enough; the final question gets none (E4)
        mcp_servers=servers,               # the scratchpad and checkpoint tools, bound to this run's files
        allowed_tools=allowed,             # no permission prompts
        setting_sources=[],                # ignore ~/.claude and project settings, CLAUDE.md and hooks
        env={"ENABLE_TOOL_SEARCH": "false"},
        max_turns=12,                      # safety cap (01 C16); a step needs about 6 turns
    )
```

**POC 2's file tools**: each handler reads and writes a file in `state.run_dir`, so nothing lives only in memory:

| Tool | Description (what Claude reads) | Input | Behavior |
|---|---|---|---|
| `mcp__notes__note` | `"Adds entries to your scratchpad file under one section. Write exact facts, one per entry: a class name, its file path and a relation."` | `section` (enum `key_classes`, `dependency_chains`, `critical_findings`), `entries` (array of strings) | Appends one `- <entry>` line per entry under `## Key classes`, `## Dependency chains` or `## Critical findings` in `scratchpad.md`. The first call creates the file with a `# Exploration scratchpad` title and the 3 headings. Returns `Noted <n> entries under <section>.` |
| `mcp__notes__read_notes` (`readOnlyHint=True`) | `"Returns your whole scratchpad file. Call it at the start of every step."` | none | Returns the file's text, or `The scratchpad is empty.` |
| `mcp__progress__checkpoint` | `"Saves the exploration's progress so a crashed run can resume: the files explored in this step, its key findings, and the modules still to explore, in order."` | `explored_paths` and `key_findings` (arrays of strings), `next_steps` (array of module names, enum of `MODULE_PLAN`'s keys) | Merges the input into `manifest.json` and adds 1 to `state.checkpoints`. The manifest holds `sessionId` (`state.exploration_id`), `phase` (`state.phase`), `exploredPaths` (the union of all calls), `keyFindings` (appended) and `nextSteps` (replaced). Returns `Checkpoint <n> saved.` |

---

## 2. Concepts and POC requirements

All 17 concepts in the raw file (C1–C17) are covered: all 17 are new or build on earlier POCs and are taught below, none is a terminal command, and none was already covered by an earlier revised file (see the end of this section).
Previous revised files checked: `01-revised-Agentic-Loops.md`, `02-revised-Multi-Agent-Orchestration.md`, `03-revised-Subagent-Invocation-and-Context-Passing.md`, `04-revised-Workflow-Enforcement-and-Handoff.md`, `05-revised-Agent-SDK-Hooks.md`, `06-revised-Task-Decomposition-Strategies.md`, `01-revised-Tool-Interface-Design.md`, `02-revised-Structured-Error-Responses.md`, `03-revised-Tool-Distribution-&-Tool-Choice.md`, `04-revised-MCP-Server-Integration.md`, `05-revised-Built-in-Tools.md`, `01-revised-System-Prompts-with-Explicit-Criteria.md`, `02-revised-Few-Shot-Prompting.md`, `03-revised-Structured-Output-with-Tool-Use.md`, `04-revised-Validation-Retry-and-Feedback-Loops.md`, `05-revised-Batch-Processing-Strategies.md`, `06-revised-Multi-Instance-and-Multi-Pass-Review.md`, `01-revised-Context-Window-Management.md`, `02-revised-Escalation-Ambiguity-Resolution.md`, `03-revised-Error-Propagation-in-Multi-Agent-Systems.md`. The closest earlier work: `02-revised-Multi-Agent-Orchestration.md` and `03-revised-Subagent-Invocation-and-Context-Passing.md` pass context from the coordinator to a subagent, never back as a context saving. `01-revised-Context-Window-Management.md` keeps facts in a block that Python injects, not in a file the agent manages itself, and no earlier file checkpoints progress.
Raw step → concepts: **1** → C1–C3 · **2** → C4–C7 · **3** → C8–C10 · **4** → C11–C14 · **5** → C15–C17. Each step adds a Nudge and a Guidance, so concepts come from all five parts.
Rows marked **E** are extras that are not in the raw file. Without them, the POC breaks or gives misleading results.

### POC 1: Delegate, then hand Phase 1 to Phase 2

**Build:** `explore_repo/`, `explore_setup.py` and `poc1_delegation.py`.

`explore_setup.py` holds everything both POCs share:
- `REPO_DIR` and the ground truth;
- `chars_read(calls)`: the summed on-disk size of the distinct files that `Read` opened, like `chars_read()` in `05-revised-Built-in-Tools.md`;
- `sentence_count()`, copied from `01-revised-Tool-Interface-Design.md`, and `parse_json_object()`;
- the code above and `coordinator_scope`;
- POC 2's two servers.

`python explore_setup.py` runs an offline self-check of the ground truth: 23 files, 18 classes, `UNTESTED_INTEGRATIONS == ["NotifyService", "ReorderPlanner"]` (sorted), `UNHANDLED == ["src/services/refund.ts"]`, and 6 modules of 3 files each in `MODULE_PLAN`.

**An extension to `run_coordinator()`**: add `last_prompt_tokens`, the same sum as `prompt_tokens` (06's extension) but taken from the last top-level `AssistantMessage` that carries `usage`. It is the size of the coordinator's context at its last request. Earlier scripts must still run unchanged.

`poc1_delegation.py` makes 6 `query()` calls:
1. **Phase 1:** `run_coordinator(PHASE1_PROMPT, PHASE1_SCHEMA, options=build_phase1_options())`. `PHASE1_PROMPT` lists `PHASE1_TASKS` by id and text, then `PHASE2_TASKS`, labelled "Phase 2 tasks, which you don't run". The summary is saved to `phase1_summary.json`.
2. **The single-agent baseline:** `run_coordinator(BASELINE_PROMPT, PHASE1_SCHEMA, options=build_solo_options("You explore the Lumen Home TypeScript service in your working directory. Do every task yourself, then write the Phase 1 summary."))`, with the same task lists as `PHASE1_PROMPT`.
3. **Phase 2:** for each of the 2 `PHASE2_TASKS`, once `warm` (the summary injected, C8) and once `cold`, `run_coordinator(phase2_prompt(task, summary_or_None), options=build_solo_options("You explore the Lumen Home TypeScript service in your working directory. Do your task. " + REPORT_FORMAT))`.

`summary_block(summary, task)` renders `=== PHASE 1 SUMMARY ===`, then `Architecture: …`, the dependency chains and key concerns as `- ` lines, and `Your Phase 2 objective: <that task's objective>`. `phase2_prompt(task, summary)` puts that block above `=== YOUR TASK ===` and the task text, or gives the task text alone when `summary` is `None`.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C1 | A coordinator that delegates specific codebase exploration tasks to subagents (find test files, trace dependency chains, identify external integrations): 3–4 tasks, each narrow enough for one subagent to handle without filling its own context (**Builds on** `02-revised-Multi-Agent-Orchestration.md` C9) | `AGENTS` and `COORDINATOR_PROMPT` (code above): one subagent per `PHASE1_TASKS` entry, each with read-only `FILE_TOOLS` and `maxTurns=15`. New compared with 02 C9: the subagents use Claude Code's own file tools on a real directory (`cwd`), and the split rule is size. Each task is one question about the repo, so one subagent can answer it inside a small context | 3 Agent calls (`test-finder`, `dependency-tracer`, `integration-scout`), typically sharing one `message_id`. Every subagent ends with a report and stays well under 15 turns |
| E1 | The coordinator can't read files | `coordinator_scope` (above) denies any `Read`, `Grep` or `Glob` call that has no `agent_id`. The file tools have to be in the session's `tools` for the subagents to use them, so without the hook the coordinator could read a file itself. Its context would then grow for a reason that has nothing to do with delegation, and C2's measurement would mislead | Every `Read`, `Grep` and `Glob` call in the Phase 1 run has a `parent_tool_use_id` (it was made inside a subagent). Typically the hook denies nothing |
| C3 | Each subagent returns a structured summary (key findings, file paths, class names), not the raw file contents it read (**Builds on** `03-revised-Subagent-Invocation-and-Context-Passing.md` C8) | `REPORT_FORMAT` ends every subagent prompt. Parse each report with `parse_json_object()` and check four things: it has `task`, `classes` and `facts`; every class's `file` exists and matches `CLASSES`; no source line appears in it (no `import ` or `export class` text); and its length is small next to `chars_read()` of its subagent's `Read` calls. Print both numbers for each subagent. New compared with 03 C8: there the format kept metadata attached to content; here its job is compression, so a whole investigation crosses to the coordinator as a few hundred tokens | 3 valid reports, with every file path matching `CLASSES`. Each report is typically under 20% of the characters its subagent read |
| C2 | Subagent delegation is primarily about context isolation, not parallelisation: the coordinator's context stays free of verbose output (file contents, search results) for high-level coordination, which directly prevents context degradation (**Builds on** `02-revised-Multi-Agent-Orchestration.md` C10) | Print, for Phase 1 and the baseline, `prompt_tokens`, `last_prompt_tokens` and the growth between them: what the session accumulated. Then print `chars_read()` for both runs, and the line `The saving is context, not speed: the coordinator would hold the same 3 reports if the subagents had run one at a time`. New compared with 02 C10, where the subagent saw nothing of the coordinator: here, in the other direction, the coordinator sees nothing of the subagents' tool results | Both runs read a similar volume of files, yet the coordinator's growth is typically under a quarter of the single agent's. The single agent carries every file it read into each later request, while the coordinator carries 3 reports |
| C10 | The Phase 1 summary captures the architectural overview, the dependency chains discovered, the key concerns and the specific Phase 2 objective for each subagent. It is concise and structured: Phase 2 subagents need context, not the full verbose output (**New**) | `PHASE1_SCHEMA` (code above) makes the coordinator write the 4 parts. Check: `sentence_count(architecture) <= 5`; at least 1 dependency chain names a class from `CLASSES`; each Phase 2 task has an objective that names at least one class and its file; and no source line appears anywhere. Print `summary_block()` for each task, with its length | 4 parts present, with an objective for both Phase 2 tasks. Typically the `payment_errors` objective names `RefundDesk` or `PayFluxClient`, and the `untested_integrations` one names services and tests. Each block is typically under 3,000 characters |
| C8 | Summary injection logic: after Phase 1, summarise the findings and inject the summary into the initial prompt of every Phase 2 subagent (**Builds on** `02-revised-Multi-Agent-Orchestration.md` C11) | `phase2_prompt(task, summary)` puts `summary_block(summary, task)` at the top of each warm prompt. Python does the injection, so every Phase 2 subagent receives the same summary word for word, plus its own objective. New compared with 02 C11, where the coordinator wrote prior findings into each prompt itself: a whole phase is condensed into one document, which code injects | Each warm prompt starts with `=== PHASE 1 SUMMARY ===` and contains its block exactly. The cold prompts contain no summary |
| C9 | Summary injection prevents the cold-start problem, where Phase 2 subagents duplicate Phase 1's exploration because they weren't given its findings. It gives them the architectural understanding to ask the right questions without rediscovering the structure (**New**) | For each Phase 2 task and arm, print the tool calls, the discovery calls (`Glob` plus `Grep`), the files read and `chars_read()`. Check each answer against the ground truth: `payment_errors` must name `RefundDesk` in `src/services/refund.ts`, and `untested_integrations` must name `ReorderPlanner` and `NotifyService` | Warm: typically 0 discovery calls and the fewest tool calls; for `untested_integrations`, often none at all. Cold: typically 2 or more discovery calls per task, repeating Phase 1's searches, such as a `Glob` for tests or a `Grep` for client imports. Both arms typically reach the right answers: the cold start costs duplicated exploration, not correctness |

### POC 2: Write it down: a scratchpad and a manifest

**Build:** `poc2_scratchpad.py` and `poc2_crash_resume.py`, reusing `explore_setup.py` and `run_agent()`. Each run gets a new `ExploreState` and an empty `work/<run>/`. Both scripts share one driver:
- `build_step_prompt(history, task)` returns `=== EARLIER STEPS ===`, the history records joined by blank lines (or `none`), then `=== THIS STEP ===` and the task.
- After each step, the driver sets `state.phase` from `PHASES` and appends the record `Step <n> (<module>): <answer>` to the history.

`poc2_scratchpad.py` makes two runs, `no-scratchpad` and `scratchpad`, with 7 `query()` calls each:
- the 6 module steps, each `run_agent(build_step_prompt(history, STEP_TASK.format(...)), options=build_explorer_options(state, scratchpad))`;
- after step `SUMMARISE_AFTER`, `history = [LOSSY_HISTORY]`;
- the final question, `FINAL_TASK` with `final=True`.

It defines `score_listing(answer)`, which marks a class ✅ when one line of the answer holds both its name and its path, and counts the ✅ separately for modules 1–4 (12 classes) and modules 5–6 (6). It also defines `generic_phrases(answer)`: the matches for `typical`, `usual`, `standard` or `follows the ... pattern`.

`poc2_crash_resume.py` makes one run, `crash-resume`, with `scratchpad=True, checkpoints=True` and no summarisation. Steps 1–3 run, and then the driver raises `SimulatedCrash`: the in-memory history is lost. Its `resume()` then:
- loads `manifest.json` and makes `ExploreState(run_dir, exploration_id=manifest["sessionId"])`;
- starts the history with `RESUME_HEADER + json.dumps(manifest, indent=2)`, where `RESUME_HEADER = "Resumed from the last checkpoint of a crashed run. Don't re-read exploredPaths; continue with nextSteps.\n"`;
- runs the modules in `manifest["nextSteps"]`.

That is 6 `query()` calls. With the 14 of `poc2_scratchpad.py`, POC 2 makes 20.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| E2 | Python owns the history: each step is a fresh `query()` | Each step is one `run_agent()` call with no `resume` and no `continue_conversation`, so the only history Claude sees is what `build_step_prompt()` wrote. Python can then summarise it on purpose (E3) or lose it in a crash (C12). This is the pattern of `01-revised-Context-Window-Management.md` E1. In a continued session, the SDK keeps the history itself, and whether a name survives would be up to the model | Code review: no `resume`, `continue_conversation` or `ClaudeSDKClient` anywhere in POC 2 |
| E3 | The summarised history is fixed text with no class name or path | `LOSSY_HISTORY` (code above) replaces steps 1–4 in both arms, as `01-revised-Context-Window-Management.md` E2 replaced its turns 1–4. It stands in for the attention shift of a long session: it keeps the story and loses the names. A live summary might keep some names in one arm and lose them in the other | `re.search(r"[a-z][A-Z]\|src/", LOSSY_HISTORY) is None`: no CamelCase name and no path. From step 5 on, both arms see the same history text |
| C4 | Scratchpad file management: agents write key findings (class names, file paths, dependency chains) to a known file after each exploration step, and read it before each later step (**New**) | The scratchpad arm uses `SCRATCHPAD_RULE` and the `notes` server (above). The file's path is fixed by the tools (`work/<run>/scratchpad.md`), so the agent never has to remember where its notes are. For each step, print the tool calls in order and the number of entries added | In steps 2–6 and in the final question, the first tool call is typically `read_notes`. Every module step makes at least 1 `note` call. The no-scratchpad arm makes no `notes` calls (it has no such tools) |
| C6 | The scratchpad is a Markdown file with clear sections for key classes, dependency chains and critical findings, written after each major discovery. It holds specific class names, file paths and dependency chains, not summaries (**New**) | The `note` tool's `section` enum enforces the three headings. After the run, print `scratchpad.md` and its specificity: the share of `## Key classes` entries that contain both a class from `CLASSES` and its exact file. Also run `generic_phrases()` on the whole file | The file has the 3 headings, typically with all 18 classes under Key classes, at least 1 dependency chain, and `RefundDesk`'s missing try/catch under Critical findings. Specificity is typically 100%, with 0 generic phrases |
| C7 | A deliberate strategy, not a fallback: agents are told to maintain the scratchpad from the start of any extended exploration session (**New**) | `SCRATCHPAD_RULE` is in the system prompt of every step of the scratchpad arm, from step 1, not added once trouble appears. Print the scratchpad's entry count after each step | The file already holds module 1's 3 classes after step 1, and every module's classes before the summarisation at step 4. When the loss comes, the notes are already on disk |
| C5 | Scratchpad files are the primary mitigation for context degradation: they keep knowledge outside the conversation context, so the attention shift doesn't affect it. That shift is what makes the model cite typical patterns instead of the specific class names and paths it found earlier (**Builds on** `01-revised-Context-Window-Management.md` C3) | Right after the summarisation at step 4, count the module 1–4 class names in the history and in `scratchpad.md`. New compared with 05-01 C3: the store is a file that the agent writes and reads with its own tools, not a block that Python keeps and injects | History: 0 of the 12 module 1–4 class names (it holds only `LOSSY_HISTORY`). `scratchpad.md`: typically all 12 |
| C15 | Test context degradation with an extended exploration session across 5 or more modules, run with and without scratchpad files. At the end, ask the agent to list every class it discovered, with its file path (**Builds on** `01-revised-Context-Window-Management.md` C12) | Run `poc2_scratchpad.py`: the same 6 modules, step prompts, summarisation and final question in both arms. Only `SCRATCHPAD_RULE` and the `notes` server differ. Print `score_listing()` for each arm, per module group. New compared with 05-01 C12: the test measures recall of a whole exploration (18 classes and paths), and the agent manages the store that keeps it | 2 runs of 7 calls each. Each run ends with a final answer, and the final question makes no `Read` call (E4) |
| E4 | The final question can't open source files | The final step runs with `tools=[]`, so the only memory left is the history and, in the scratchpad arm, `read_notes`. With `Read` available, the no-scratchpad arm could re-read the 18 files and answer correctly. The test would then measure re-exploration instead of what the session kept | The final steps of both arms have 0 `Read` calls |
| C16 | The degradation symptom: the agent refers to typical patterns ("this follows the typical repository pattern") instead of specific classes and paths ("the OrderRepository class at src/repos/order.ts implements Repository<T>") (**New**) | Run `generic_phrases()` on both final answers, and print each arm's answer lines about the orders, payments, inventory and shipping modules | No scratchpad: typically 1 or more generic phrases, such as "follows the typical layered pattern", where specific classes should be. Scratchpad: typically 0, with lines such as `OrderRepository — src/repos/order.ts` |
| C17 | Expected: without scratchpad files, the agent misses or generalises after exploring 4–5 modules; with them, it keeps specific class names and paths for the whole session by reading the file. That validates the mitigation empirically (**Builds on** `01-revised-Context-Window-Management.md` C13, C14) | Print the score table, then `Same modules, prompts and summary in both runs: only the scratchpad differed`. New compared with 05-01 C13–C14: the missing details are an exploration's discoveries, and the agent kept them itself | Scratchpad: typically 18/18 (12/12 on modules 1–4). No scratchpad: typically at most 8/18, with 0–2 of 12 on modules 1–4 (only a guessable name such as `OrderRepository`) and up to 6 of 6 on modules 5–6, which are still in its history |
| C11 | Crash recovery: each agent exports structured state (explored paths, key findings, next steps) to a JSON manifest holding the session ID, the current phase, the explored paths, the key findings and the next steps. On resume, the coordinator loads the manifest and injects it into the agent's prompt, so the exploration continues from where it stopped (**New**) | `CHECKPOINT_RULE` and the `progress` server (above). After the crash, print `manifest.json` and check its keys. `resume()` (the coordinator role, played by the driver) injects the manifest into the first resumed prompt. Then check the resumed run's `Read` calls against the `exploredPaths` that the manifest held at the crash | At the crash: exactly the keys `sessionId`, `phase`, `exploredPaths`, `keyFindings` and `nextSteps`. `phase` is `phase 1: core modules`, and `exploredPaths` holds the 9 files of orders, payments and inventory. After resuming: 0 `Read` calls on those 9 files. The final manifest has the same `sessionId`, 18 `exploredPaths` and `nextSteps == []` |
| C13 | Update the manifest after every significant exploration step, not just at the end of a phase: frequent checkpointing minimises the work lost in a crash (**New**) | `CHECKPOINT_RULE` asks for a checkpoint at the end of every step. Print `state.checkpoints` at the crash, and the steps lost under two policies: one checkpoint per step, and one at the end of each phase (`PHASES`) | 3 checkpoints at the crash, so 0 steps are lost. With a checkpoint only at the end of a phase, the crash in phase 1, after 3 of its 4 modules, would lose all 3 steps |
| C14 | A `nextSteps` array lets the resumed session know exactly what to investigate next, without re-analysing the findings (**New**) | `next_steps` is an enum of module names, so the driver can run them as they are. Print the manifest's `nextSteps` at the crash, and the module of the first resumed step | `nextSteps == ["shipping", "notifications", "customers"]`, and the first resumed step explores `shipping` and reads only its 3 files |
| C12 | Extended exploration sessions can fail through crashes, network interruptions or context exhaustion, and without recovery all progress is lost. A manifest lets the coordinator resume from the last checkpoint instead of restarting from the beginning (**New**) | `SimulatedCrash` stands for any of the three: after it, the in-memory history is gone, as it would be after a real crash. Print the module steps the run needed, and the steps a restart without a manifest would have needed | 3 steps before the crash + 3 after = 6 module steps, against 3 lost + 6 again = 9 for a restart. The scratchpad survives the crash too, because it is on disk (C5) |

### Terminal commands (for the later tutorial)

None: every concept in this topic is a programming concept.

### Already covered by earlier POCs

None: every concept in this topic is new or builds on an earlier POC (cited in its row).
