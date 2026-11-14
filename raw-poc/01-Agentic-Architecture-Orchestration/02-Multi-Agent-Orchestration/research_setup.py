"""
research_setup.py - the mock Helios corpus, the two research tools, the coordinator's role and its two subagents.

build_coordinator_options() configures every coordinator call: the hub (COORDINATOR_PROMPT) and its two spokes
(AGENTS). The subagents use the tools; the coordinator only gets the Agent tool, which spawns them.
"""

from typing import Any

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, ToolAnnotations, create_sdk_mcp_server, tool

from common import Settings

SERVER_NAME = "research"
WEB_SEARCH = f"mcp__{SERVER_NAME}__web_search"
READ_DOCUMENT = f"mcp__{SERVER_NAME}__read_document"

# ---------------------------------------------------------------- the mock corpus (made up: Claude must search)

# category -> (words web_search matches, doc id, web_search fact, read_document fact)
CORPUS = {
    "solar": (("solar", "photovoltaic"), "HX-SOL-7",
              "solar capacity grew 31% in 2025", "utility-scale cost fell to $27.40/MWh"),
    "wind": (("wind",), "HX-WND-2",
             "offshore wind added 19.6 GW in 2025", "the average capacity factor reached 41.3%"),
    "hydropower": (("hydropower", "hydroelectric", "hydro power"), "HX-HYD-5",
                   "hydropower supplied 14.2% of electricity", "pumped-storage capacity rose to 212 GW"),
    "geothermal": (("geothermal",), "HX-GEO-3",
                   "geothermal output rose 8.7%", "enhanced-geothermal pilot wells reached 245 °C"),
    "tidal": (("tidal", "wave", "ocean", "marine"), "HX-TID-4",
              "tidal stream capacity reached 1.9 GW", "the Kestrel Strait array ran at a 37.5% capacity factor"),
    "biomass": (("biomass", "bioenergy", "biofuel", "biogas"), "HX-BIO-6",
                "bioenergy supplied 9.4% of industrial heat", "waste feedstocks made up 63% of supply"),
    "fusion": (("fusion",), "HX-FUS-1",
               "the Aurora-3 test reactor held plasma for 412 seconds", "a 140 MW grid pilot is planned for 2034"),
}

# What a full report on "renewable energy technologies" must cover (C8). No decomposition prompt lists these:
# the coordinator has to find the breadth itself.
REQUIRED = ["solar", "wind", "geothermal", "tidal", "biomass", "fusion"]


def missing_categories(texts: list[str]) -> list[str]:
    """The REQUIRED categories that none of the texts mentions (by the words web_search matches)."""
    joined = " ".join(texts).lower()
    return [category for category in REQUIRED if not any(word in joined for word in CORPUS[category][0])]


# ---------------------------------------------------------------- the two research tools (used by the subagents)


@tool(
    "web_search",
    "Search Helios Institute sources. Returns one line per matching renewable-energy category, with a key "
    "figure and the id of the document that holds the full analysis.",
    {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "What to search for, e.g. 'tidal energy'"}},
        "required": ["query"],
    },
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def web_search(args: dict[str, Any]) -> dict[str, Any]:
    query_text = str(args.get("query", ""))
    lines = [
        f"Helios Review 2026, {category}: {web_fact}. Full analysis: document {doc_id}."
        for category, (words, doc_id, web_fact, _) in CORPUS.items()
        if any(word in query_text.lower() for word in words)
    ]
    return {"content": [{"type": "text", "text": "\n".join(lines) or f"No Helios results for '{query_text}'."}]}


@tool(
    "read_document",
    "Read one Helios document by its exact id, as named in web_search results (e.g. 'HX-SOL-7'), "
    "and return its key figures.",
    {
        "type": "object",
        "properties": {"doc_id": {"type": "string", "description": "The document id, e.g. 'HX-SOL-7'"}},
        "required": ["doc_id"],
    },
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def read_document(args: dict[str, Any]) -> dict[str, Any]:
    doc_id = str(args.get("doc_id", ""))
    for category, (_, known_id, _, document_fact) in CORPUS.items():
        if doc_id.strip().upper() == known_id:
            return {"content": [{"type": "text", "text": f"{known_id} ({category}): {document_fact}."}]}
    # A guessed id gets an error RESULT with a hint, so the subagent can recover (01 E4).
    message = f"Unknown document id '{doc_id}'. Only ids that appear in web_search results exist."
    return {"content": [{"type": "text", "text": message}], "is_error": True}


# ---------------------------------------------------------------- the hub (coordinator) and its spokes (subagents)

COORDINATOR_PROMPT = (
    "You are the coordinator of a research team: the hub of a hub-and-spoke system. You own three jobs. "
    "1) Decompose: split a topic into 5 to 8 distinct subtopics that cover its full breadth, including "
    "mainstream, niche, and emerging or experimental categories. Each subtopic is one category of the topic "
    "itself, never a cross-cutting theme such as policy, cost or history. "
    "2) Delegate: never research yourself. The web-searcher subagent finds sources; the doc-analyst subagent "
    "reads the documents they name. Subagents share no memory with you or with each other, so every Agent "
    "prompt must state the research goal, the exact subtopic names, and every fact from earlier reports that "
    "the subagent needs, such as document ids. "
    "3) Aggregate: combine both reports into one section per subtopic, and judge coverage honestly."
)

# Each spoke: a description (Claude picks the subagent from it, as it picks a tool), its own system prompt,
# and one tool. The subagent sees its prompt plus the Agent call's prompt, and nothing else.
AGENTS = {
    "web-searcher": AgentDefinition(
        description="Finds Helios Institute sources for a list of subtopics. Use it before doc-analyst.",
        prompt=("You are a web-search specialist. Call web_search once for each subtopic in your task. "
                "For each subtopic, report the key figure and the document id from the result. "
                "Use only what the tool returns; if a search finds nothing, say so."),
        tools=[WEB_SEARCH],  # its only tool: it can't read documents or spawn agents
        model="inherit",  # the coordinator's model
        maxTurns=15,  # per-subagent safety cap (camelCase, as in the SDK)
    ),
    "doc-analyst": AgentDefinition(
        description="Reads Helios documents by exact document id and extracts their key figures.",
        prompt=("You are a document analyst. Read each document id in your task with read_document and "
                "report its key figures per subtopic. You cannot search. If your task gives no document "
                "id, say which ids you need instead of guessing."),
        tools=[READ_DOCUMENT],
        model="inherit",
        maxTurns=15,
    ),
}


def build_coordinator_options(
    settings: Settings, schema: dict[str, Any] | None = None, with_agents: bool = True
) -> ClaudeAgentOptions:
    """Options for one coordinator call. with_agents=False (decompose, assess coverage): the coordinator only thinks."""
    research_server = create_sdk_mcp_server(name=SERVER_NAME, version="1.0.0", tools=[web_search, read_document])
    return ClaudeAgentOptions(
        model=settings.model_id,
        system_prompt=COORDINATOR_PROMPT,  # the hub's role (C4); the subagents never see it
        output_format={"type": "json_schema", "schema": schema} if schema else None,  # JSON in .structured_output
        tools=["Agent"] if with_agents else [],  # the ONLY built-in tool is Agent, which spawns subagents (C9)
        agents=AGENTS if with_agents else None,  # the two spokes
        mcp_servers={SERVER_NAME: research_server} if with_agents else {},  # the mock tools, used by the subagents
        allowed_tools=["Agent", WEB_SEARCH, READ_DOCUMENT],  # no permission prompts
        disallowed_tools=["Agent(fork)"],  # no forks: a fork inherits the coordinator's whole conversation (E1)
        setting_sources=[],  # ignore ~/.claude settings, CLAUDE.md and hooks: the same run on any machine
        env={
            "ENABLE_TOOL_SEARCH": "false",  # send all tool schemas up front: no ToolSearch calls
            "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",  # subagents run in the foreground: wait for each report (E2)
            "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",  # only our two spokes, no general-purpose fallback (E3)
        },
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=settings.max_turns,  # safety cap per coordinator call (01 C16)
        max_budget_usd=settings.max_budget_usd,  # cost guard per call, subagents included
    )
