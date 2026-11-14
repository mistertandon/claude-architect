"""
explore_setup.py - the mock repo's ground truth (computed from the files, never hard-coded); POC 1's three explorer
subagents, coordinator and options; POC 2's explorer: its scratchpad and checkpoint tools, the step driver, and
run_agent() (01's, as extended in 05-Agent-SDK-Hooks).

The SDK doesn't carry knowledge across sessions: each query() starts fresh. A Phase 1 summary, a scratchpad and a
manifest are all YOUR code, written here.
"""

import json
import re
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultError,
    ResultMessage,
    ToolAnnotations,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_sdk_mcp_server,
    query,
    tool,
)

from common import POC_DIR, Settings, log, log_model_io

REPO_DIR = POC_DIR / "explore_repo"
FILE_TOOLS = ["Read", "Grep", "Glob"]  # read-only built-ins; on Linux, Grep and Glob exist only when named

# ---------------------------------------------------------------- the ground truth, computed from the files

FILES = sorted(path.relative_to(REPO_DIR).as_posix() for path in REPO_DIR.rglob("*.ts"))


def source(path: str) -> str:
    return (REPO_DIR / path).read_text(encoding="utf-8")


def imported(path: str) -> set[str]:
    """The names a file imports with import { A, B } from "..."."""
    return {name.strip() for group in re.findall(r"import \{([^}]*)\}", source(path)) for name in group.split(",")}


CLASSES = {name: path for path in FILES for name in re.findall(r"export class (\w+)", source(path))}
USES = {name: sorted(imported(path) & set(CLASSES)) for name, path in CLASSES.items()}
TESTED = sorted({name for path in FILES if path.startswith("tests/") for name in imported(path) & set(CLASSES)})
CLIENTS = sorted(name for name, path in CLASSES.items() if path.startswith("src/clients/"))
UNTESTED_INTEGRATIONS = sorted(name for name, path in CLASSES.items() if path.startswith("src/services/")
                               and set(USES[name]) & set(CLIENTS) and name not in TESTED)
UNHANDLED = sorted(path for name, path in CLASSES.items() if path.startswith("src/services/")
                   and set(USES[name]) & set(CLIENTS) and not re.search(r"\btry\s*\{", source(path)))


def repo_path(path: str) -> str:
    """A path as the repo knows it (src/...), whether the agent passed it absolute or relative."""
    full, root = (REPO_DIR / path).resolve(), REPO_DIR.resolve()
    return full.relative_to(root).as_posix() if full.is_relative_to(root) else path


def chars_read(calls: list[dict]) -> int:
    """The on-disk size of the distinct files that Read opened: what reading them put into a context."""
    paths = {repo_path(call["input"]["file_path"]) for call in calls
             if call["name"] == "Read" and (call["input"] or {}).get("file_path")}
    return sum(len(source(path)) for path in paths if (REPO_DIR / path).is_file())


def sentence_count(text: str) -> int:
    """Copied from 02-Tool-Design-MCP-Integration/01-Tool-Interface-Design: a ? inside quotes ends no sentence."""
    return len(re.split(r"(?<=[.!?])\s+", text.strip()))


def parse_json_object(text: str) -> Any:
    """A subagent's report is TEXT: take its first JSON object and ignore what follows, such as 'agentId: ...'."""
    if "{" not in text:
        raise ValueError("the report holds no JSON object")
    value, _ = json.JSONDecoder().raw_decode(text[text.index("{"):])
    return value


# ---------------------------------------------------------------- POC 1: a coordinator and three explorers

REPORT_FORMAT = (
    'Your final message must be only a JSON object {"task": "<task id>", "classes": [{"name": "...", "file": "..."}], '
    '"facts": ["..."]}. classes: every class your answer involves, with its exact file path. facts: one line per '
    'finding, such as "CheckoutController (src/http/checkout.ts) -> OrderService (src/services/order.ts)". '
    "Never paste file contents.")

PHASE1_TASKS = {
    "tests": "Find every test file and the class each one tests.",
    "dependencies": ("Trace every dependency chain from an entry point (an HTTP controller, or a service that no "
                     "other class uses) down to repositories and external clients."),
    "integrations": ("Identify every class that calls an outside service, which service it calls, and which classes "
                     "use it."),
}
PHASE2_TASKS = {
    "payment_errors": "Find where an error thrown by the PayFlux client can reach a caller without being handled.",
    "untested_integrations": "List every service that uses an external client but has no test file.",
}


def explorer(role: str, task_id: str) -> AgentDefinition:
    return AgentDefinition(
        description=f"{role} Use it for the '{task_id}' task.",
        prompt=f"You explore the Lumen Home TypeScript service in your working directory. {role} " + REPORT_FORMAT,
        tools=FILE_TOOLS,  # read-only: it can search and read, never edit
        model="inherit",
        maxTurns=15,  # a narrow task fits well inside this (C1)
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
        "phase2_objectives": {"type": "array", "items": {
            "type": "object", "required": ["task", "objective"],
            "properties": {"task": {"type": "string", "enum": list(PHASE2_TASKS)}, "objective": {"type": "string"}}}},
    },
}


async def coordinator_scope(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
    """PreToolUse on the file tools: a call without agent_id was made by the coordinator itself, so deny it (E1)."""
    if input_data.get("agent_id"):  # set only inside a subagent
        return {}
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": "The coordinator never reads files: delegate with "
                                                               "the Agent tool."}}


def build_phase1_options(settings: Settings) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=settings.model_id,
        system_prompt=COORDINATOR_PROMPT,
        output_format={"type": "json_schema", "schema": PHASE1_SCHEMA},  # the summary as validated JSON
        cwd=str(REPO_DIR),  # the subagents' file tools work on the mock repo
        tools=["Agent"] + FILE_TOOLS,  # file tools must be in the session for the subagents to use them
        agents=AGENTS,  # the three explorers
        allowed_tools=["Agent"] + FILE_TOOLS,  # no permission prompts
        disallowed_tools=["Agent(fork)"],  # no forks: a fork inherits the coordinator's context (01-02 E1)
        hooks={"PreToolUse": [HookMatcher(matcher="Read|Grep|Glob", hooks=[coordinator_scope])]},  # (E1)
        setting_sources=[],  # ignore ~/.claude settings, CLAUDE.md and hooks: the same run on any machine
        env={
            "ENABLE_TOOL_SEARCH": "false",  # send all tool schemas up front: no ToolSearch calls
            "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",  # each Agent result holds the report (01-02 E2)
            "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",  # no built-in Explore: only our three (01-02 E3)
        },
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=20,  # safety cap (01 C16)
        max_budget_usd=settings.max_budget_usd,  # cost guard per call, subagents included
    )


def build_solo_options(settings: Settings, system_prompt: str, schema: dict | None = None) -> ClaudeAgentOptions:
    """ONE agent with the file tools and no subagents: POC 1's baseline, and each Phase 2 task."""
    return ClaudeAgentOptions(
        model=settings.model_id,
        system_prompt=system_prompt,
        output_format={"type": "json_schema", "schema": schema} if schema else None,
        cwd=str(REPO_DIR),
        tools=FILE_TOOLS,
        allowed_tools=FILE_TOOLS,
        setting_sources=[],
        env={"ENABLE_TOOL_SEARCH": "false"},
        thinking={"type": "adaptive", "display": "summarized"},
        max_turns=30,
        max_budget_usd=settings.max_budget_usd,
    )


# ---------------------------------------------------------------- POC 2: one explorer, a scratchpad and a manifest

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
SUMMARISE_AFTER = 4  # after module 4, Python replaces the history with LOSSY_HISTORY (E3)
CRASH_AFTER = 3  # the crash-resume run dies after module 3 (C12)

EXPLORER_PROMPT = (
    "You explore the Lumen Home TypeScript service in your working directory, one module per step, in this order: "
    "orders, payments, inventory, shipping, notifications, customers. Each message starts with what is known from "
    "earlier steps. Read only the files the step names.")
SCRATCHPAD_RULE = (  # in the prompt from the very FIRST step: a strategy, not a fallback (C7)
    " Keep a scratchpad from the very first step: call read_notes at the start of every step, and after each "
    "discovery call note with exact entries, such as 'OrderRepository — src/repos/order.ts — implements "
    "Repository<Order>'. Never write a summary such as 'follows the usual pattern'.")
CHECKPOINT_RULE = (  # after EVERY step, not at the end of a phase (C13)
    " At the end of every step, call checkpoint with the files you explored, your key findings and the modules "
    "still to explore, so the exploration can resume after a crash.")

STEP_TASK = ("Explore the {module} module: {files}. For each class, give its exact name, its file, what it implements "
             "or extends, and what it depends on. End with one line per class: ClassName — path — relation.")
FINAL_TASK = ("List every class you discovered in this exploration, across all modules, one per line as "
              "ClassName — path. Don't open any source file.")
# Fixed text with no class name and no path: it keeps the story and loses the names, like a degraded context (E3)
LOSSY_HISTORY = ("Steps 1-4 explored the orders, payments, inventory and shipping modules. Each one follows the "
                 "typical layered pattern: a repository for data access, a service with the business logic, and in "
                 "some modules a client for an outside service.")


@dataclass
class ExploreState:
    """One per run. The scratchpad and the manifest live as files in run_dir, never only in memory."""

    run_dir: Path  # work/<run>/: scratchpad.md and manifest.json
    exploration_id: str = field(default_factory=lambda: uuid.uuid4().hex)  # the manifest's sessionId
    phase: str = ""  # set by the driver before each step
    checkpoints: int = 0


def fresh_run_dir(name: str) -> Path:
    """An empty work/<run>/ for one run."""
    run_dir = POC_DIR / "work" / name
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True)
    return run_dir


def text_result(text: str, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": is_error}


SECTIONS = {"key_classes": "## Key classes", "dependency_chains": "## Dependency chains",
            "critical_findings": "## Critical findings"}  # the scratchpad's fixed Markdown sections (C6)


def read_sections(path: Path) -> dict[str, list[str]]:
    sections, current = {heading: [] for heading in SECTIONS.values()}, None
    for line in (path.read_text(encoding="utf-8").splitlines() if path.is_file() else []):
        if line in sections:
            current = line
        elif current and line.startswith("- "):
            sections[current].append(line[2:])
    return sections


def build_notes_server(state: ExploreState) -> Any:
    """The scratchpad: a known file (work/<run>/scratchpad.md), so the agent never has to remember where it is (C4)."""
    path = state.run_dir / "scratchpad.md"

    @tool("note", "Adds entries to your scratchpad file under one section. Write exact facts, one per entry: a class "
          "name, its file path and a relation.",
          {"type": "object", "properties": {"section": {"type": "string", "enum": list(SECTIONS)},
                                            "entries": {"type": "array", "items": {"type": "string"}}},
           "required": ["section", "entries"]})
    async def note(args: dict[str, Any]) -> dict[str, Any]:
        entries = [str(entry).strip() for entry in args.get("entries") or [] if str(entry).strip()]
        if args.get("section") not in SECTIONS or not entries:
            return text_result("Give a section (key_classes, dependency_chains or critical_findings) and at least "
                               "one entry.", is_error=True)
        sections = read_sections(path)
        sections[SECTIONS[args["section"]]] += entries
        path.write_text("# Exploration scratchpad\n" + "".join(
            f"\n{heading}\n" + "".join(f"- {entry}\n" for entry in lines) for heading, lines in sections.items()),
            encoding="utf-8")
        return text_result(f"Noted {len(entries)} entries under {args['section']}.")

    @tool("read_notes", "Returns your whole scratchpad file. Call it at the start of every step.",
          {"type": "object", "properties": {}}, annotations=ToolAnnotations(readOnlyHint=True))
    async def read_notes(args: dict[str, Any]) -> dict[str, Any]:
        return text_result(path.read_text(encoding="utf-8") if path.is_file() else "The scratchpad is empty.")

    return create_sdk_mcp_server(name="notes", version="1.0.0", tools=[note, read_notes])


def build_progress_server(state: ExploreState) -> Any:
    """The manifest: structured state a crashed run resumes from (C11)."""
    path = state.run_dir / "manifest.json"

    @tool("checkpoint", "Saves the exploration's progress so a crashed run can resume: the files explored in this "
          "step, its key findings, and the modules still to explore, in order.",
          {"type": "object", "properties": {
              "explored_paths": {"type": "array", "items": {"type": "string"}},
              "key_findings": {"type": "array", "items": {"type": "string"}},
              "next_steps": {"type": "array", "items": {"type": "string", "enum": list(MODULE_PLAN)}}},
           "required": ["explored_paths", "key_findings", "next_steps"]})
    async def checkpoint(args: dict[str, Any]) -> dict[str, Any]:
        manifest = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {
            "sessionId": state.exploration_id, "phase": "", "exploredPaths": [], "keyFindings": [], "nextSteps": []}
        manifest["phase"] = state.phase
        manifest["exploredPaths"] = sorted(set(manifest["exploredPaths"])
                                           | {repo_path(str(p)) for p in args.get("explored_paths") or []})
        manifest["keyFindings"] += [str(finding) for finding in args.get("key_findings") or []]
        manifest["nextSteps"] = [m for m in args.get("next_steps") or [] if m in MODULE_PLAN]  # replaced (C14)
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        state.checkpoints += 1
        return text_result(f"Checkpoint {state.checkpoints} saved.")

    return create_sdk_mcp_server(name="progress", version="1.0.0", tools=[checkpoint])


def build_explorer_options(settings: Settings, state: ExploreState, scratchpad: bool = False,
                           checkpoints: bool = False, final: bool = False) -> ClaudeAgentOptions:
    servers, allowed = {}, ([] if final else ["Read"])
    if scratchpad:
        servers["notes"] = build_notes_server(state)
        allowed += ["mcp__notes__note", "mcp__notes__read_notes"]
    if checkpoints and not final:
        servers["progress"] = build_progress_server(state)
        allowed += ["mcp__progress__checkpoint"]
    return ClaudeAgentOptions(
        model=settings.model_id,
        system_prompt=(EXPLORER_PROMPT + (SCRATCHPAD_RULE if scratchpad else "")
                       + (CHECKPOINT_RULE if checkpoints else "")),
        cwd=str(REPO_DIR),
        tools=[] if final else ["Read"],  # a step names its files, so Read is enough; the final question gets none (E4)
        mcp_servers=servers,  # the scratchpad and checkpoint tools, bound to this run's files
        allowed_tools=allowed,  # no permission prompts
        setting_sources=[],  # ignore ~/.claude settings, CLAUDE.md and hooks: the same run on any machine
        env={"ENABLE_TOOL_SEARCH": "false"},  # send all tool schemas up front: no ToolSearch calls
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=12,  # safety cap (01 C16); a step needs about 6 turns
        max_budget_usd=settings.max_budget_usd,  # cost guard per step
    )


def build_step_prompt(history: list[str], task: str) -> str:
    """Python owns the history: this prompt is ALL Claude knows about earlier steps (E2)."""
    earlier = "\n\n".join(history) if history else "none"
    return f"=== EARLIER STEPS ===\n{earlier}\n\n=== THIS STEP ===\n{task}"


async def explore_module(settings: Settings, state: ExploreState, history: list[str], n: int, module: str,
                         scratchpad: bool, checkpoints: bool = False) -> dict[str, Any]:
    """One module step = one fresh query(): no resume, no continue_conversation (E2)."""
    state.phase = next(phase for phase, modules in PHASES.items() if module in modules)
    task = STEP_TASK.format(module=module, files=", ".join(MODULE_PLAN[module]))
    run = await run_agent(build_step_prompt(history, task),
                          build_explorer_options(settings, state, scratchpad, checkpoints))
    history.append(f"Step {n} ({module}): {run['answer'] or '(no answer)'}")
    return run


def response_text(tool_response: Any) -> str:
    """A tool result's text: a string, a list of {"type": "text", ...} blocks, or a dict holding that list."""
    if isinstance(tool_response, dict):
        tool_response = tool_response.get("content", [])
    if isinstance(tool_response, list):
        return "".join(block.get("text", "") for block in tool_response if isinstance(block, dict))
    return str(tool_response or "")


async def run_agent(user_prompt: str, options: ClaudeAgentOptions) -> dict[str, Any]:
    """01's run_agent(), extended with options= and tool_results: what Claude actually received for each call.

    Returns {"answer", "subtype", "stop_reason", "num_turns", "tool_calls", "tool_results"}; each tool_results item
    is {"tool_use_id", "name", "input", "is_error", "text"}.
    """
    log.info("MODEL INPUT   prompt       %s", user_prompt)
    run: dict[str, Any] = {"answer": None, "subtype": None, "stop_reason": None, "num_turns": 0,
                           "tool_calls": [], "tool_results": []}
    uses: dict[str, tuple[str, dict]] = {}  # tool_use id -> (name, input)
    try:
        async for message in query(prompt=user_prompt, options=options):
            log_model_io(message)
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        run["tool_calls"].append(block.name)
                        uses[block.id] = (block.name, block.input)
            elif isinstance(message, UserMessage) and isinstance(message.content, list):
                for block in message.content:
                    if isinstance(block, ToolResultBlock):
                        name, tool_input = uses.get(block.tool_use_id, (None, None))
                        run["tool_results"].append({"tool_use_id": block.tool_use_id, "name": name, "input": tool_input,
                                                    "is_error": block.is_error, "text": response_text(block.content)})
            elif isinstance(message, ResultMessage):
                run.update(subtype=message.subtype, stop_reason=message.stop_reason, num_turns=message.num_turns)
                if message.subtype == "success" and message.stop_reason == "end_turn":
                    run["answer"] = message.result
            # No `break`: a few system events can still arrive after the ResultMessage.
    except ResultError as exc:  # raised AFTER the error ResultMessage (already logged)
        if exc.subtype == "error_max_turns":
            log.warning("Safety cap hit: max_turns=%s was used up before Claude finished. No answer.", options.max_turns)
        else:  # e.g. error_max_budget_usd, error_during_execution, an invalid API key
            log.error("The run failed: %s", exc)
    return run
