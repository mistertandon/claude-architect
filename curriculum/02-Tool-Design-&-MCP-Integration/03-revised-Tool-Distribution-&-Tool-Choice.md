# Tool Distribution & Tool Choice: Revised POC Requirements (5 steps → 2 POCs, Claude Agent SDK)

> **Source:** `03-raw-Tool-Distribution-&-Tool-Choice.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Tool Design & MCP Integration → Tool Distribution & Tool Choice · **Build with:** Claude Agent SDK for Python (`claude_agent_sdk`), plus one short Messages API script for `tool_choice` (see the verdict)

---

## 1. Verdict: 2 POCs

The 5 raw steps are not 5 separate concepts. Steps 1, 2 and 4 decide **which tools each agent gets**: three small role toolsets, one scoped cross-role tool added to one of them, and one generic tool replaced by a constrained one. Steps 3 and 5 decide **how the agents use them in a run**: a forced first step, then an end-to-end test that checks every call against its role. What you need to learn splits into distribution and control:

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: Scoped, least-privilege toolsets** | **Who may call what:** three roles with 4 tools each and no overlap; a `verify_fact` tool that handles simple single-source checks and sends anything bigger to the coordinator; a `load_document` that accepts only trusted library documents where `fetch_url` would fetch anything. Each role runs alone, and an overloaded synthesizer shows the misuse that scoping prevents | 1, 2, 4 (and step 5's misuse example) |
| **POC 2: Forced first step and the end-to-end run** | **What a run must do, and in which order:** the three `tool_choice` modes on the Messages API, a forced `extract_metadata` call followed by `auto`, the same ordering enforced in the SDK pipeline by a hook, and one research run checked call by call against the role toolsets, next to a run that sends every check through the coordinator | 3, 5 (and step 2's latency claim) |

**What changes with the Agent SDK:** in the SDK, tool distribution is configuration. Each subagent's `AgentDefinition.tools` lists exactly the tools it can see, so a tool outside its list doesn't exist for it, which is stronger than an instruction. In a single-agent run, a role is scoped by registering only its own MCP server (E3). `tool_choice` is different: it is a Messages API parameter that the Agent SDK doesn't expose (`ClaudeAgentOptions` has no such field). Also, per the tool-use docs (checked 2026-10-27), Claude Opus 5.5, Sonnet 5.5 and Fable 5.1 return a 400 error for the forced modes, `any` and `tool`, while Claude Haiku 5.5 and Opus 5 accept them. So POC 2 does two things:
- **Teaches the modes on the Messages API:** one short script with the `anthropic` package and `claude-haiku-5-5`;
- **Enforces the same ordering in the SDK pipeline:** a `PreToolUse` hook, the pattern of `05-revised-Agent-SDK-Hooks.md`, denies the doc-analyst's other document tools until `extract_metadata` has run.

The hook guarantees the order on any model; `tool_choice` guarantees it only on models that support forced tool use. Everything else is observed from the stream: which subagent called which tool (through `parent_tool_use_id`), in which order, and how long each delegation took.

- **Why not 1 POC:** POC 2's end-to-end log can prove "no cross-role misuse" only if each toolset was first shown to hold on its own. In POC 1, each role runs alone, so a violation in POC 2 points at the pipeline (the delegation prompts or the hook), not at a toolset. The `tool_choice` script also has to stand apart, because it uses another library and another model.
- **Why not 3 or more:** step 2's tool belongs to step 1's synthesis toolset, step 4 swaps one tool of step 1's document toolset, and step 5 only tests steps 1–4. Step 3 is one hook plus one short script that needs no pipeline.

**Applies to both POCs:** Python 3.10+, `pip install claude-agent-sdk` (a recent 0.2.x; it bundles the Claude Code binary), plus `pip install anthropic` for `poc2_tool_choice_api.py` only. `ANTHROPIC_API_KEY` is set in the environment (never hard-coded), with mock data only and beginner-friendly code (small, commented scripts). The pipeline runs through `run_coordinator()` from `02-revised-Multi-Agent-Orchestration.md` (`coordinator.py`), as extended in `03-revised-Subagent-Invocation-and-Context-Passing.md` (`options=`, per-call `message_id`/`started`/`finished`, `init_tools`, `research_calls` from any server) and in `06-revised-Task-Decomposition-Strategies.md`. Single-role runs go through `run_agent()` from `01-revised-Agentic-Loops.md`, as extended in `05-revised-Agent-SDK-Hooks.md` (`options=`, `tool_results`). The mock data is the made-up Tessaly sodium-ion pilot at Kestrel Ridge from `03-revised-Subagent-Invocation-and-Context-Passing.md`: its 7 rows (rows 1–3 are web sources, rows 4–7 pages of the two library documents) and the audit's figure-free cover page. Everything lives in `distribution_setup.py`, with one MCP server per role, so a tool's full name shows its role:

| Role (server) | Tool | What it returns (mock) |
|---|---|---|
| web-searcher (`web`) | `web_search(query)` | Rows 1–3 as JSON `[{"title", "url", "page", "snippet"}]` when the query contains "tessaly" (case-insensitive), else `No results for '<query>'.` |
| | `news_search(query)` | Row 3 with `"date": "2026-03-12"` when the query contains "tessaly" or "kestrel" |
| | `get_search_result(url)` | One of rows 1–3 in full, by exact URL; any other URL gives `is_error: True` |
| | `check_source_reputation(domain)` | `example.com`: primary source · `example.org`: industry tracker · `example.net`: company newsroom · anything else: unknown |
| doc-analyst (`docs`) | `extract_metadata(url)` | `{"title", "author", "date", "pages", "type"}`. The audit: Tessaly Pilot Safety Audit, Halden Safety Partners, 2026-02-10, 7 pages, audit report. The minutes: Kestrel Ridge Board Minutes, March 2026, Kestrel Ridge Utility, 2026-03-18, 4 pages, board minutes |
| | `load_document(url)` | 03's format: a `Title: … · URL: …` header, then one `[page N] <text>` line per page |
| | `find_figures(url)` | The `[page N]` lines of that document that state a figure (rows 4–7) |
| | `search_document(url, query)` | The `[page N]` lines that contain the query (case-insensitive) |
| synthesizer (`synth`) | `outline_report(topics)` | A numbered outline, one line per topic |
| | `format_citation(title, source_url, page)` | `<title>, p. <page>. <source_url>` |
| | `verify_fact(claim, source_url, page)` | The scoped cross-role check (C4, C6) |
| | `compile_report(title, sections, needs_coordinator)` | Stores the brief in `state.reports` and returns `Report RPT-0001 compiled: <n> sections.` |
| none (`generic`) | `fetch_url(url)` | The generic anti-pattern: appends any URL to `state.fetched` and returns `Fetched <url> (mock: 2,048 bytes).` |

All four `docs` tools check their `url` with `validate_document_url(url)` before anything else. It returns `(True, "")` or `(False, reason)`, and a rejection is an `is_error: True` result with that reason. The rules, in order:
1. The scheme must be `https`: `Rejected: only https URLs can be loaded (got http).`
2. The host must be in `TRUSTED_DOC_HOSTS = {"example.com"}`: `Rejected: <host> is not a trusted document host. Trusted: example.com.`
3. The path must start with `/library/` and end with `.pdf`, `.docx` or `.md`: `Rejected: <path> is not a library document. Allowed: /library/*.pdf, *.docx or *.md on example.com.`

A valid URL that is not one of the two library documents gives `Unknown document: <url>.`

Every run gets its tools and options from `distribution_setup.py`:

```python
WEB_TOOLS = ["mcp__web__web_search", "mcp__web__news_search", "mcp__web__get_search_result",
             "mcp__web__check_source_reputation"]
DOC_TOOLS = ["mcp__docs__extract_metadata", "mcp__docs__load_document", "mcp__docs__find_figures",
             "mcp__docs__search_document"]
SYNTH_TOOLS = ["mcp__synth__outline_report", "mcp__synth__format_citation", "mcp__synth__verify_fact",
               "mcp__synth__compile_report"]
ROLE_TOOLS = {"web-searcher": WEB_TOOLS, "doc-analyst": DOC_TOOLS, "synthesizer": SYNTH_TOOLS}  # 4 tools per role (C1)
ALL_TOOLS = WEB_TOOLS + DOC_TOOLS + SYNTH_TOOLS + ["mcp__generic__fetch_url"]  # 13: the "one agent gets everything" anti-pattern (C2)

@dataclass
class DistributionState:  # one per run (05's HookState pattern)
    fetched: list[str] = field(default_factory=list)            # every URL fetch_url accepted
    loaded: list[str] = field(default_factory=list)             # every URL a docs tool accepted
    verifications: list[dict] = field(default_factory=list)     # each verify_fact call and its result
    reports: list[dict] = field(default_factory=list)           # compile_report inputs
    doc_calls: list[tuple] = field(default_factory=list)        # (agent_id, tool, "allow" or "deny") from the metadata_first hook (POC 2)
    metadata_done: set = field(default_factory=set)             # agent_ids that have run extract_metadata (POC 2)

def build_role_options(state, role, tools=None, docs_loader="load_document"):
    # One role run alone (POC 1). Only the servers this toolset needs are registered (E3).
    tools = tools or ROLE_TOOLS[role]
    if docs_loader == "fetch_url":                              # step 4's "before": the generic tool in place of load_document
        tools = [t for t in tools if t != "mcp__docs__load_document"] + ["mcp__generic__fetch_url"]
    servers = {name: build_server(name, state) for name in {t.split("__")[1] for t in tools}}
    return ClaudeAgentOptions(
        model="claude-opus-5-5",
        system_prompt=AGENTS[role].prompt,                      # the role's own system prompt, as in the pipeline
        mcp_servers=servers,                                    # availability: tools of unregistered servers don't exist
        tools=[],                                               # no built-in tools
        allowed_tools=tools,                                    # permission: every available tool runs without a prompt
        setting_sources=[],                                     # ignore ~/.claude and project settings, CLAUDE.md and hooks
        env={"ENABLE_TOOL_SEARCH": "false"},                    # load tool schemas upfront: no ToolSearch calls
        max_turns=15,                                           # safety cap (01 C16)
    )

def build_pipeline_options(state, verify="scoped"):
    # The coordinator and three subagents (POC 2). verify="routed" removes verify_fact (C5).
    return ClaudeAgentOptions(
        model="claude-opus-5-5",
        system_prompt=coordinator_prompt(verify),
        tools=["Agent"],                                        # the coordinator's only built-in tool
        agents=build_agents(verify),                            # each AgentDefinition.tools is its role's list (C1)
        mcp_servers={name: build_server(name, state) for name in ("web", "docs", "synth")},  # used by the subagents
        allowed_tools=["Agent"] + WEB_TOOLS + DOC_TOOLS + synth_tools(verify),
        disallowed_tools=["Agent(fork)"],                       # no forks (02 E1)
        hooks=build_order_hooks(state),                         # metadata_first and coordinator_scope (C7, C15)
        setting_sources=[],
        env={
            "ENABLE_TOOL_SEARCH": "false",
            "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",        # wait for every report (02 E2)
            "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",     # only our three subagents (02 E3)
        },
        max_turns=30,                                           # safety cap per coordinator call (01 C16)
    )
```

The three `AgentDefinition`s, each with `model="inherit"`, `maxTurns=10` and `tools=ROLE_TOOLS[role]`:

| Agent | `description` | `prompt` (its system prompt) |
|---|---|---|
| `web-searcher` | Finds web sources and news on a research question. Returns findings with source URLs and pages. | `You are a web-search specialist. Use web_search and news_search for the question in your task, get_search_result for a result's full text, and check_source_reputation for an unfamiliar domain. Report one finding per result: claim, source_url and page. Use only what your tools return.` |
| `doc-analyst` | Analyses library documents at the exact URLs in its task. Returns key figures with page numbers. | `You are a document analyst. For each document URL in your task, call extract_metadata first, then load_document, find_figures or search_document as needed. Report one finding per figure: claim, document title, URL and page. Use only what your tools return.` |
| `synthesizer` | Writes the final brief from the findings in its task. Call it after both research reports. | `You are a synthesis writer with no search or document tools: use only the findings in your task. Before compiling, check each single-figure claim against its cited page with verify_fact. Put any claim that needs more than one source, and any topic the findings don't cover, under needs_coordinator; never research it yourself. Call compile_report once, then reply with its result and your needs_coordinator list.` |

---

## 2. Concepts and POC requirements

All 15 concepts in the raw file (C1–C15) are covered: all 15 are new or build on earlier POCs and are taught below, none is a terminal command, and none was already covered by an earlier revised file (see the end of this section).
Previous revised files checked: `01-revised-Agentic-Loops.md`, `02-revised-Multi-Agent-Orchestration.md`, `03-revised-Subagent-Invocation-and-Context-Passing.md`, `04-revised-Workflow-Enforcement-and-Handoff.md`, `05-revised-Agent-SDK-Hooks.md`, `06-revised-Task-Decomposition-Strategies.md`, `01-revised-Tool-Interface-Design.md`, `02-revised-Structured-Error-Responses.md` (the domain-02 files `04-` and `05-revised-…` are still empty).
Raw step → concepts: **1** → C1–C3 · **2** → C4–C6 · **3** → C7–C9 · **4** → C10–C12 · **5** → C13–C15.
Rows marked **E** are extras that are not in the raw file. Without them, the POC breaks or gives misleading results.

### POC 1: Scoped, least-privilege toolsets

**Build:** `distribution_setup.py` (the corpus, the 13 tools in four servers created by `build_server(name, state)`, `validate_document_url()`, `figures()`, `DistributionState`, the tool lists, `AGENTS`, `coordinator_prompt()`, `build_agents()`, `synth_tools()`, `build_role_options()` and `build_pipeline_options()`; POC 2 reuses it, and `python distribution_setup.py` runs an offline self-check that makes no API calls), `poc1_least_privilege.py` and `poc1_synthesis_scope.py`. Each run gets a new `DistributionState` and `run_agent(prompt, options=build_role_options(...))`.

The prompts:
- `LOAD_URLS`, in this order:
  1. `https://example.com/library/tessaly-safety-audit.pdf`
  2. `https://example.com/admin/users`
  3. `http://example.com/library/tessaly-safety-audit.pdf`
  4. `https://files.example-mirror.net/tessaly-safety-audit.pdf`
  5. `https://example.com/library/payroll-export.csv`
- `LOAD_PROMPT = "Get the content of each of these sources and say what each one is, or why you couldn't get it: " + ", ".join(LOAD_URLS)`
- `VERIFY_PROMPT` lists four draft claims and asks: `Check each claim with your tools before you compile the brief, and say which ones you checked yourself.` The claims:
  - **(a)** `The Tessaly pilot delivered 48 MWh of storage at peak demand in 2025.` [`https://example.com/tessaly/year-one-results`, p. 3]
  - **(b)** `Round-trip efficiency averaged 87.4%.` [`https://example.com/library/tessaly-safety-audit.pdf`, p. 5]
  - **(c)** `The board approved $42 million for phase two.` [`https://example.com/library/kestrel-ridge-board-minutes.pdf`, p. 4]
  - **(d)** `At $61 per kWh, the 48 MWh pilot's cells cost about $2.9 million.` [rows 1 and 2]
- `BRIEF_PROMPT = "Write a short brief on the Tessaly pilot that covers performance, cost, safety and future plans, from these findings: " + json.dumps(FINDINGS)`. `FINDINGS` are rows 1, 2, 4, 5, 6 and 7 as `{"claim", "source_url", "page"}`. Row 3, the only one about future plans, is left out on purpose.

`figures(claim)` returns the numbers in a claim, with 4-digit years (1900–2099) left out. `verify_fact` works in this order:
1. Fewer or more than 1 figure: it returns `{"status": "escalate", "reason": "verify_fact checks one figure against one cited page; this claim has <n>. Put it under needs_coordinator."}`.
2. An unknown `(source_url, page)` pair: it returns `escalate`.
3. Otherwise it compares the figure with the cited page's text (`$`, `,` and `%` removed from both) and returns `{"status": "verified"}` or `{"status": "not_supported"}`.

Every call is appended to `state.verifications`. These are normal results, not `is_error`: sending a claim on is the tool's designed behavior. Claim (d) has 3 figures: 61, 48 and 2.9. Its figure is right: 48 MWh = 48,000 kWh × $61 = $2,928,000, about $2.9 million. It still needs two sources and a calculation, so it is not a simple lookup.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C1 | Three agent roles (web search, document analysis, synthesis), each with a small set of tools scoped to its role: 4–5 in the exam guide's example (**Builds on** `02-revised-Multi-Agent-Orchestration.md` C9) | `ROLE_TOOLS` (code above) gives each role 4 tools, and `build_agents()` copies them into each `AgentDefinition.tools`. The self-check prints the table: role, server, tool count, tools. New compared with 02 C9: each role gets a working set of several tools instead of one, and the set's size is a design choice you can check | `web-searcher` 4, `doc-analyst` 4, `synthesizer` 4. `len(ALL_TOOLS) == 13`, the exam's "18" in miniature: 4 + 4 + 4 + 1 (`fetch_url`) |
| C3 | No tool appears in more than one role (except scoped cross-role tools added later), and tool names clearly show their purpose and scope (**New**) | The self-check computes every pair of roles' shared tools, and checks that each tool's server segment (`mcp__<server>__…`) is its role's server: `web`, `docs` or `synth`. `verify_fact` is the one cross-role tool: it lives in `synth` and does a narrow piece of the web role's job. Each name is a verb plus an object, such as `load_document` and `verify_fact`, never a bare verb like `fetch` | 0 shared tools across the 3 pairs. All 12 role tools sit under their role's server. The only tool outside a role is `mcp__generic__fetch_url` |
| E3 | Scoping is availability, not permission | `build_role_options()` registers only the servers of the role's tools. An MCP tool on a registered server stays visible to Claude even when it isn't in `allowed_tools`. Then Claude can try it, get a permission denial and waste a turn, and the run would test the permission layer, not the distribution. In the pipeline, `AgentDefinition.tools` does the same job for each subagent | Code review: every role run registers only its own servers. No `ToolResultBlock` in POC 1 is a permission denial |
| C10 | Replace a generic `fetch_url` tool with a constrained `load_document` that validates document URLs only (**New**) | `poc1_least_privilege.py` runs `LOAD_PROMPT` twice with the `doc-analyst` role: **before**, with `build_role_options(state, "doc-analyst", docs_loader="fetch_url")`, and **after**, with the default `load_document`. Print `state.fetched`, `state.loaded` and each `ToolResultBlock`'s `is_error` and text | Before: `state.fetched` typically holds all 5 URLs, including the admin page, the plain-http copy, the mirror and the payroll export. After: `state.loaded` holds only URL 1, and URLs 2–5 got `is_error=True` results with their reasons |
| C12 | The URL validation logic (trusted domain, library path and document extension) rejects non-document URLs with a clear error message (**New**) | The self-check runs `validate_document_url()` on the 5 `LOAD_URLS` and calls the `fetch_url` handler directly with the same 5 | `validate_document_url()`: URL 1 is accepted. URL 2 `/admin/users is not a library document`, URL 3 `only https URLs can be loaded (got http)`, URL 4 `files.example-mirror.net is not a trusted document host`, URL 5 `/library/payroll-export.csv is not a library document`. The `fetch_url` handler accepts all 5 |
| C11 | Least privilege in tool design: a generic `fetch_url` can fetch anything from anywhere, which enables misuse; a constrained tool keeps the agent from fetching arbitrary resources (**New**) | Print the before and after results side by side: what each run fetched, and what decided it | Before: the only limit was Claude's judgment, and the tool itself accepted every URL (the C12 self-check). After: the tool refused 4 of 5 URLs by construction, whatever Claude decided. If Claude skips some URLs in the before run on its own, record it: least privilege doesn't rely on that |
| C4 | A scoped `verify_fact` tool on the synthesis agent handles simple lookups directly (**New**) | `poc1_synthesis_scope.py` runs `VERIFY_PROMPT` with `build_role_options(state, "synthesizer")`. Print `state.verifications` and the final answer | `verify_fact` is called for (a), (b) and (c), each `verified`, with 0 calls to anything outside `SYNTH_TOOLS` (none exist in this run) |
| C6 | The scoped cross-role tool pattern: a constrained version of a capability for the simple (85%) case, whose description limits it to simple single-source lookups and sends complex multi-source verifications to the coordinator (**Builds on** `01-revised-Tool-Interface-Design.md` C9) | The `verify_fact` description: `Checks one claim that states exactly one figure against the one source page it cites, and returns verified, not_supported or escalate. Use it for simple single-source lookups, such as "Round-trip efficiency averaged 87.4%" cited to the safety audit, page 5. Do NOT use it for a claim that combines several sources or needs a calculation: list that claim under needs_coordinator, so the coordinator can send it to the research agents.` The handler enforces the same limit through `figures()`. New compared with 01's C9: the boundary sends the request to another agent, not to another tool, and the handler enforces what the description says | Claim (d) is never `verified`: either `verify_fact` returns `escalate` for it (3 figures), or the synthesizer doesn't call it, and (d) is listed under `needs_coordinator` in the answer or in `compile_report`'s input |
| C2 | Tool overload degrades selection reliability: giving one agent every tool (18 in the exam's example) is a known anti-pattern that causes misrouting (**New**) | Run `BRIEF_PROMPT` twice with the synthesizer's system prompt: **scoped** (`build_role_options(state, "synthesizer")`) and **overloaded** (`build_role_options(state, "synthesizer", tools=ALL_TOOLS)`, all 13 tools and all four servers). For each run, print every tool call and whether it belongs to `SYNTH_TOOLS` | Scoped: every call is in `SYNTH_TOOLS`. Overloaded: typically at least 1 call to a tool outside the synthesizer's job, such as `web_search`, `news_search`, `load_document` or `fetch_url`, chosen over finishing from the findings. The more tools an agent can see, the more ways it can pick the wrong one |
| C14 | Cross-role misuse, such as a synthesis agent running its own web searches instead of using the provided results, is a common failure that proper scoping prevents (**New**) | In the same two runs, look at "future plans", the one topic that `FINDINGS` doesn't cover | Overloaded: typically a `web_search` or `news_search` call for the plans, and the brief quotes `300 MWh` from row 3, a result the synthesizer was never given. Scoped: no search is possible, and "future plans" is listed under `needs_coordinator` for the coordinator to research |

### POC 2: Forced first step and the end-to-end run

**Build:** two scripts, reusing `distribution_setup.py`, `run_coordinator()` and `delegation_timing()` from `03-revised-Subagent-Invocation-and-Context-Passing.md` (`attribution_check.py`).

**`poc2_tool_choice_api.py`** uses the Messages API directly: `client = anthropic.Anthropic()` and `FORCED_MODEL = "claude-haiku-5-5"`, a model that accepts forced tool use. Its tools are the docs role's own definitions, `API_TOOLS = [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in build_docs_tools(state)]`. Each `tool_use` block runs through the same handler, `await t.handler(block.input)`, and its text goes back as a `tool_result` block with the same `tool_use_id` (`01-revised-Agentic-Loops.md` C10). It has three runs:
1. **`modes`:** three single calls with `MODES_PROMPT = "In one sentence, what does a document's metadata usually include?"`, with `tool_choice` `{"type": "auto"}`, `{"type": "any"}` and `{"type": "tool", "name": "extract_metadata"}`. For each, print `stop_reason` and the content block types in order.
2. **`forced-then-auto`:** a manual loop on `ANALYSE_PROMPT = "Analyse https://example.com/library/tessaly-safety-audit.pdf and list its key figures with page numbers."`. Call 1 uses `{"type": "tool", "name": "extract_metadata"}`, and every later call uses `{"type": "auto"}`. The loop stops at `stop_reason == "end_turn"` or after 6 calls. Print each call's `tool_choice`, `stop_reason` and tool names.
3. **Optional, `unsupported`:** call 1 of run 2 again, with `MODEL_ID` (`claude-opus-5-5` in this spec). Catch `anthropic.BadRequestError` and print its status code.

**`poc2_pipeline.py`** defines `build_order_hooks(state)`. It returns `{"PreToolUse": [HookMatcher(matcher="mcp__docs__.*", hooks=[metadata_first]), HookMatcher(matcher="mcp__.*", hooks=[coordinator_scope])]}`. Both are regex matchers (`05-revised-Agent-SDK-Hooks.md` E2), and both callbacks close over `state`:
- **`metadata_first`** keys on `input_data.get("agent_id")`, which the SDK fills in for tool calls made inside a subagent. If the tool is `extract_metadata`, it adds that `agent_id` to `state.metadata_done` and allows the call. Any other `docs` tool from an `agent_id` not in `metadata_done` is denied with `extract_metadata must run first: call it for a document URL in your task, then use the other document tools.` Every decision is appended to `state.doc_calls`.
- **`coordinator_scope`** denies any MCP tool call that has no `agent_id` (one made by the coordinator itself) with `The coordinator delegates with the Agent tool; it never calls research or writing tools itself.`

`async def run_pipeline(verify)` calls `run_coordinator(QUESTION, options=build_pipeline_options(state, verify))`, with `QUESTION = "What is known about the Tessaly sodium-ion grid battery pilot at Kestrel Ridge? Two library documents cover it: https://example.com/library/tessaly-safety-audit.pdf and https://example.com/library/kestrel-ridge-board-minutes.pdf."`. It maps each `research_calls` item to its subagent through `parent_tool_use_id` and returns `{"agent_calls", "calls_by_agent", "doc_calls", "verifications", "reports", "timing"}`. The script runs `verify="scoped"` and then `verify="routed"`.

`coordinator_prompt(verify)`:

`You are the coordinator of a research team. Delegate with the Agent tool; never call a research or writing tool yourself. web-searcher finds web sources for the question. doc-analyst analyses library documents: pass it their exact URLs. Call web-searcher and doc-analyst first, then call synthesizer once with every finding from both.`

It ends with one sentence that depends on `verify`:
- `scoped`: `synthesizer checks simple single-source facts itself with verify_fact; if its report lists claims under needs_coordinator, research them with web-searcher, then call synthesizer again with the new findings.`
- `routed`: `synthesizer has no verification tool: it lists every figure under needs_coordinator, so have web-searcher or doc-analyst re-check those figures, then call synthesizer again to finish.`

With `routed`, `synth_tools()` and the synthesizer's `AgentDefinition.tools` leave out `verify_fact`, and its prompt says to list every figure under `needs_coordinator`, unless its task says the figures were already checked.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| E1 | The Agent SDK has no `tool_choice`, and Opus 5.5 and Sonnet 5.5 reject forced tool use | `ClaudeAgentOptions` has no `tool_choice` field, and the Claude Code CLI has no such flag, so the SDK can't send one. On the Messages API, Opus 5.5, Sonnet 5.5 and Fable 5.1 answer `any` and `tool` with a 400 error. So the modes are shown with `FORCED_MODEL = "claude-haiku-5-5"` in `poc2_tool_choice_api.py`, and the pipeline enforces its order with a hook (C7). The optional `unsupported` run shows the 400 error | `unsupported` prints status code `400` for `MODEL_ID`. Code review: no `tool_choice` anywhere in the SDK code |
| C8 | The three `tool_choice` modes: `auto` lets the model choose freely, including no tool; `any` guarantees a tool call; forced selection, `{"type": "tool", "name": …}`, guarantees one specific tool call (**New**) | The `modes` run (above). Note in a comment that the API also has `{"type": "none"}`, which forbids tools. With `any` and `tool`, the API prefills the response, so no text or thinking comes before the `tool_use` block | `auto`: typically `stop_reason == "end_turn"` with a text block and no tool, because the question needs none. `any`: `stop_reason == "tool_use"`, and the first content block is a `tool_use` for one of the 4 docs tools. `tool`: `stop_reason == "tool_use"`, and the first block is a `tool_use` named `extract_metadata` |
| C9 | Forced selection enforces workflow ordering and keeps the model from skipping mandatory steps: the first API call uses `{"type": "tool", "name": "extract_metadata"}`, and later calls switch to `auto` for the remaining analysis steps (**New**) | The `forced-then-auto` run (above). Print the `tool_choice` used for each call next to the tool Claude chose | Call 1: `extract_metadata` for the audit URL, guaranteed by the mode. Calls 2 and later: `auto`, typically `load_document` or `find_figures`, then `end_turn`. The final text typically lists `1,200` (p. 2), `87.4%` (p. 5) and `3.1%` (p. 7) |
| E2 | The doc-analyst's task must carry the document URLs | `QUESTION` names both library URLs, and the coordinator prompt says to pass them on. A forced first `extract_metadata` call needs a URL to extract from; without one, the forced step would have no valid input | Every `doc-analyst` Agent prompt in both pipeline runs contains both library URLs |
| C7 | Forced selection on the document analysis agent makes `extract_metadata` the mandatory first step (**Builds on** `05-revised-Agent-SDK-Hooks.md` C16) | `metadata_first` (above). New compared with 05 C16: the gate enforces the order of one subagent's own steps, keyed on its `agent_id`, instead of a prerequisite across tools. Each doc-analyst spawn has its own `agent_id`, so each one must start with `extract_metadata`. The self-check calls `metadata_first` directly with hand-built inputs | Self-check: `load_document` from `agent_id` `a1` is denied; `extract_metadata` from `a1` is allowed; then `load_document` from `a1` is allowed; and `load_document` from `a2` is still denied. Live: in each run, the first `allow` in `state.doc_calls` for each doc-analyst `agent_id` is `extract_metadata`, and any earlier entries are `deny` |
| C13 | An end-to-end test with a query that needs all three agents validates the tool distribution in practice (**New**) | Run `run_pipeline("scoped")`. Print each Agent call (subagent, `started`, `finished`), then each subagent's tool calls in order | The run ends with `success`. Typically 3 Agent calls: `web-searcher`, `doc-analyst` and `synthesizer`, with the synthesizer last. `state.reports` holds 1 brief that typically quotes `48 MWh`, `87.4%` and `$42 million` |
| C15 | The test log: the web search agent uses only its tools, the document agent starts with `extract_metadata` (forced), the synthesis agent uses `compile_report` plus `verify_fact` for simple checks, and no agent calls a tool outside its set (**Builds on** `03-revised-Subagent-Invocation-and-Context-Passing.md` C5) | `cross_role_calls(calls_by_agent)` returns every call whose tool isn't in its subagent's `ROLE_TOOLS`, plus every MCP call the coordinator made itself (`parent_tool_use_id is None`). New compared with 03 C5: four tools per role instead of one or two, a forced first step, and a coordinator that `coordinator_scope` keeps out of the research tools | `cross_role_calls() == []`. `web-searcher`'s calls are all in `WEB_TOOLS`. `doc-analyst` starts with `extract_metadata` (C7). `synthesizer` calls `verify_fact` (typically once per figure it uses, each `verified`) and `compile_report` once |
| C14 (in pipeline) | Scoping prevents cross-role misuse end to end | Count the synthesizer's calls to `WEB_TOOLS` or `DOC_TOOLS` in the scoped run, next to POC 1's overloaded run | 0 in the pipeline, because its `AgentDefinition.tools` has none of them, against typically at least 1 in POC 1's overloaded run |
| C4 (in pipeline) | `verify_fact` handles the simple checks inside the synthesizer | Read the scoped run's `verifications`. Each one ran inside the synthesizer: its `parent_tool_use_id` is the synthesizer's Agent call | Every verification has status `verified`, `needs_coordinator` is typically empty (every figure in the findings has one source), and no extra Agent call was made for checking |
| C5 | Routing every fact verification through the coordinator adds 2–3 round trips and up to 40% latency (**Builds on** `03-revised-Subagent-Invocation-and-Context-Passing.md` C16) | Run `run_pipeline("routed")`. Print both runs' Agent call counts and `delegation_seconds` from `delegation_timing(agent_calls, names=("web-searcher", "doc-analyst", "synthesizer"))`, and the difference as a percentage of the scoped run. New compared with 03 C16: the extra time comes from extra delegation round trips (the synthesizer hands claims back, the coordinator re-delegates them and calls the synthesizer again), not from running independent work one after the other | Scoped: typically 3 Agent calls. Routed: typically 5 or 6, with one or two re-checks and a second synthesizer call, which is 2–3 more round trips. Routed `delegation_seconds` is typically longer. The exact percentage varies between runs (the exam quotes up to 40%) |

### Terminal commands (for the later tutorial)

None: every concept in this topic is a programming concept.

### Already covered by earlier POCs

None: every concept in this topic is new or builds on an earlier POC (cited in its row).
