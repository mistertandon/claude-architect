"""
attribution_setup.py - the mock Tessaly sources, the three source tools, the finding format that keeps content
apart from metadata, the three subagents, and build_pipeline_options() for every coordinator call.
"""

import json
from typing import Any

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, ToolAnnotations, create_sdk_mcp_server, tool

from common import Settings

SERVER_NAME = "sources"
SOURCE_TOOLS = [f"mcp__{SERVER_NAME}__web_search", f"mcp__{SERVER_NAME}__list_documents",
                f"mcp__{SERVER_NAME}__read_document"]
QUESTION = "What is known about the Tessaly sodium-ion grid battery pilot at Kestrel Ridge?"

# ---------------------------------------------------------------- the mock sources (made up: Claude must look)

WEB_RESULTS = [  # web_search returns all three for any query that mentions Tessaly
    {"title": "Tessaly Grid Pilot: Year-One Results", "url": "https://example.com/tessaly/year-one-results",
     "page": 3, "snippet": "The Tessaly pilot delivered 48 MWh of storage at peak demand in 2025."},
    {"title": "Sodium-Ion Cost Tracker 2026", "url": "https://example.org/sodium-ion-cost-tracker-2026",
     "page": 2, "snippet": "Tessaly cells cost $61 per kWh at pack level."},
    {"title": "Kestrel Ridge Utility Newsroom", "url": "https://example.net/kestrel-ridge/news/tessaly-expansion",
     "page": 1, "snippet": "Kestrel Ridge plans a 300 MWh Tessaly expansion by 2028."},
]
DOCUMENTS = {  # the local library: file name -> title, URL and the text of each page
    "tessaly-safety-audit.pdf": {
        "title": "Tessaly Pilot Safety Audit", "url": "https://example.com/library/tessaly-safety-audit.pdf",
        "pages": {1: "Scope: independent audit of the Tessaly sodium-ion pilot at Kestrel Ridge.",  # no figure
                  2: "No thermal runaway events were recorded across 1,200 charge cycles.",
                  5: "Round-trip efficiency averaged 87.4%.",
                  7: "Capacity fade was 3.1% after the first year."}},
    "kestrel-ridge-board-minutes.pdf": {
        "title": "Kestrel Ridge Board Minutes, March 2026",
        "url": "https://example.com/library/kestrel-ridge-board-minutes.pdf",
        "pages": {4: "The board approved $42 million for phase two of the Tessaly deployment."}},
}


@tool(
    "web_search",
    "Search the web. Returns a JSON list of results, each with title, url, page and snippet.",
    {"type": "object", "properties": {"query": {"type": "string", "description": "What to search for"}},
     "required": ["query"]},
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def web_search(args: dict[str, Any]) -> dict[str, Any]:
    query_text = str(args.get("query", ""))
    text = json.dumps(WEB_RESULTS) if "tessaly" in query_text.lower() else f"No results for '{query_text}'."
    return {"content": [{"type": "text", "text": text}]}


@tool(
    "list_documents",
    "List the file names and titles of the documents in the local library.",
    {"type": "object", "properties": {}},
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def list_documents(args: dict[str, Any]) -> dict[str, Any]:
    lines = [f"{name}: {document['title']}" for name, document in DOCUMENTS.items()]
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "read_document",
    "Read one library document by its exact file name. Returns its title and URL, then one '[page N]' line per page.",
    {"type": "object", "properties": {"document_name": {"type": "string", "description": "e.g. 'tessaly-safety-audit.pdf'"}},
     "required": ["document_name"]},
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def read_document(args: dict[str, Any]) -> dict[str, Any]:
    name = str(args.get("document_name", ""))
    document = DOCUMENTS.get(name.strip().lower())
    if document is None:  # an error RESULT with a hint, so the subagent can recover (01 E4)
        return {"content": [{"type": "text", "text": f"Unknown document '{name}'. Call list_documents first."}],
                "is_error": True}
    lines = [f"Title: {document['title']} · URL: {document['url']}"]
    lines += [f"[page {page}] {text}" for page, text in document["pages"].items()]
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


# ---------------------------------------------------------------- one finding = content + metadata (C8)

CONTENT_FIELDS = ["claim", "analysis"]  # what was found
METADATA_FIELDS = ["source_url", "document_name", "page_number", "confidence", "retrieved_by"]  # where it came from

FINDING_FORMAT = (
    'Your final message must be only a JSON object {"findings": [...]}, with no other text. '
    'Each finding has exactly these keys. Content: "claim" (one factual sentence) and "analysis" '
    '(one sentence on why it matters). Metadata: "source_url", "document_name", "page_number" '
    '(an integer), "confidence" ("high", "medium" or "low") and "retrieved_by" (your agent name). '
    "Copy source_url, document_name and page_number exactly from the tool output; never invent them."
)

# The 7 correct findings, as the two research subagents should return them: POC 2's fixed handoff input.
FINDINGS = [
    {"claim": r["snippet"], "analysis": "A published figure on the Tessaly pilot.", "source_url": r["url"],
     "document_name": r["title"], "page_number": r["page"], "confidence": "high", "retrieved_by": "web-searcher"}
    for r in WEB_RESULTS
] + [
    {"claim": text, "analysis": "A figure from the local library.", "source_url": d["url"], "document_name": d["title"],
     "page_number": page, "confidence": "high", "retrieved_by": "doc-analyst"}
    for d in DOCUMENTS.values() for page, text in d["pages"].items()
    if any(char.isdigit() for char in text)  # one finding per page that states a figure: not the audit's cover page
]


def parse_json_object(text: str) -> Any:
    """A subagent's report is TEXT: take its first JSON object and ignore what follows, such as 'agentId: ...' (E2)."""
    if "{" not in text:
        raise ValueError("the report holds no JSON object")
    value, _ = json.JSONDecoder().raw_decode(text[text.index("{"):])
    return value


def parse_findings(report: str) -> list[dict[str, Any]]:
    findings = parse_json_object(report).get("findings")
    if not isinstance(findings, list):
        raise ValueError("the report's JSON has no 'findings' list")
    return findings


# ---------------------------------------------------------------- the three spokes and the coordinator

AGENTS = {
    "web-searcher": AgentDefinition(
        description="Searches the web for sources on a research question. Returns findings with source URLs and titles.",
        prompt=("You are a web-search specialist. Call web_search for the question in your task and report one "
                "finding per search result, using the result's title as document_name and its page as page_number. "
                + FINDING_FORMAT),
        tools=[SOURCE_TOOLS[0]],  # search tools only
        model="inherit",
        maxTurns=10,
    ),
    "doc-analyst": AgentDefinition(
        description="Reads the local document library for a research question. Returns analysis with page references.",
        prompt=("You are a document analyst. Call list_documents, read every document with read_document, and report "
                "one finding per page that states a figure, using the document's title as document_name. "
                + FINDING_FORMAT),
        tools=SOURCE_TOOLS[1:],  # file-reading tools only
        model="inherit",
        maxTurns=10,
    ),
    "synthesizer": AgentDefinition(
        description="Writes the final sourced brief from the findings in its task. Call it last, after both research reports.",
        prompt=('You are a synthesis writer with no tools: use only the findings in your task. Your final message must be '
                'only a JSON object {"statements": [{"text": "...", "citations": [{"source_url": "...", "page_number": 1}]}]}. '
                "Cite the source_url and page_number of every finding a statement uses, copied exactly from the findings. "
                "If a finding has no source_url or page_number, still write the statement but leave its citations empty: "
                "never invent a citation."),
        tools=[],  # no tools: it reasons only over what its task contains
        model="inherit",
        maxTurns=5,
    ),
}

SEQUENTIAL_RULE = "Call web-searcher first and wait for its report; only then call doc-analyst."
PARALLEL_RULE = ("web-searcher and doc-analyst are independent: call both in one response, with two Agent tool "
                 "calls, and wait for both reports before you go on.")


def coordinator_prompt(parallel: bool) -> str:
    return ("You are the coordinator of a research team. Never research yourself: delegate. web-searcher finds web "
            "sources; doc-analyst reads the local document library. "
            + (PARALLEL_RULE if parallel else SEQUENTIAL_RULE)
            + " Subagents start with no context, so give each research subagent the full research question. "
            "Call synthesizer only when your task asks for a brief: call it last, and pass it one JSON object "
            '{"findings": [...]} holding every finding from both reports, unchanged. Never drop, shorten or '
            "summarize any field.")


def build_pipeline_options(
    settings: Settings, parallel: bool = False, agent_tool: bool = True, approve_agent: bool = True
) -> ClaudeAgentOptions:
    """Options for one coordinator call. agent_tool=False closes the gate: no subagent can start (C1, C3)."""
    sources_server = create_sdk_mcp_server(name=SERVER_NAME, version="1.0.0",
                                           tools=[web_search, list_documents, read_document])
    return ClaudeAgentOptions(
        model=settings.model_id,
        system_prompt=coordinator_prompt(parallel),  # POC 1: sequential; POC 2: parallel (C15)
        tools=["Agent"] if agent_tool else [],  # THE GATE: the session's tool set is fixed when query() starts
        agents=AGENTS,  # the three spokes (they still can't run without the Agent tool)
        mcp_servers={SERVER_NAME: sources_server},  # the mock tools, used by the subagents
        # Exam answer: Agent must be in allowedTools. In the SDK that only pre-approves it (E1).
        allowed_tools=(["Agent"] if agent_tool and approve_agent else []) + SOURCE_TOOLS,
        disallowed_tools=["Agent(fork)"] + ([] if agent_tool else ["Agent"]),  # no forks (02 E1); gate off: deny Agent
        setting_sources=[],  # ignore ~/.claude settings, CLAUDE.md and hooks: the same run on any machine
        env={
            "ENABLE_TOOL_SEARCH": "false",  # send all tool schemas up front: no ToolSearch calls
            "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",  # the coordinator waits for every report (02 E2, C17)
            "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",  # only our spokes, no general-purpose fallback (02 E3)
        },
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=settings.max_turns,  # safety cap per coordinator call (01 C16)
        max_budget_usd=settings.max_budget_usd,  # cost guard per call, subagents included
    )
