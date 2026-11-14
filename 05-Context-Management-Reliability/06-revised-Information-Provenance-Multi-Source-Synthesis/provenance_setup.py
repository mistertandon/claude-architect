"""
provenance_setup.py - a made-up library on sodium-ion grid storage (6 documents, 13 passages), its two tools, the
claim-source mapping and validate_mapping(), the two research analysts, the synthesis prompts, the brief's schema,
and the fixed gold mappings with their 2 planted conflicts.

No SDK feature keeps a claim attached to its source: that depends on the formats the prompts require, and on code
that checks them at every hop.
"""

import json
import re
from typing import Any

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, ToolAnnotations, create_sdk_mcp_server, tool

from common import Settings

DOCUMENTS = [  # a context line that states no finding, then one finding per passage (its id is the key)
    {"sourceUrl": "https://example.com/helios/market-outlook-2025", "documentName": "Helios Market Outlook 2025",
     "publicationDate": "2025-03-10", "focus": "market", "context": "This outlook covers grid storage markets.",
     "passages": {"M1": "The sodium-ion grid storage market is growing 12% a year.",
                  "M2": "Average sodium-ion pack prices fell to $78 per kWh in 2024."}},
    {"sourceUrl": "https://example.org/kestrel-analytics/storage-brief-2026",
     "documentName": "Kestrel Analytics Storage Brief 2026", "publicationDate": "2026-02-20", "focus": "market",
     "context": "This brief summarises storage market data.",
     "passages": {"M3": "The sodium-ion grid storage market is growing 18% a year.",
                  "M4": "Sodium-ion pack prices averaged $64 per kWh in 2025."}},
    {"sourceUrl": "https://example.net/tessaly/datasheet-v3", "documentName": "Tessaly Cell Datasheet v3",
     "publicationDate": "2026-01-15", "focus": "market", "context": "Datasheet for Tessaly sodium-ion cells.",
     "passages": {"M5": "Tessaly cells reach an energy density of 160 Wh/kg.",
                  "M6": "Rated cycle life is 6,000 cycles at 80% depth of discharge.",
                  "M7": "The operating temperature range is -20 °C to 55 °C."}},
    {"sourceUrl": "https://example.org/grid-storage-regulator/bulletin-2026-01",
     "documentName": "Grid Storage Regulator Bulletin, January 2026", "publicationDate": "2026-01-28",
     "focus": "policy", "context": "Official bulletin of the Grid Storage Regulator.",
     "passages": {"M8": "On 27 January 2026 the regulator approved sodium-ion systems for frequency-response markets.",
                  "M9": "Installed sodium-ion grid capacity reached 4.2 GWh at the end of 2025, counting "
                        "grid-connected systems only."}},
    {"sourceUrl": "https://example.net/kestrel-ridge/news/2026-02", "documentName": "Kestrel Ridge Utility Newsroom",
     "publicationDate": "2026-02-05", "focus": "policy", "context": "News from Kestrel Ridge Utility.",
     "passages": {"M10": "Kestrel Ridge broke ground on its 300 MWh Tessaly expansion this month.",
                  "M11": "Installed sodium-ion capacity reached 5.1 GWh at the end of 2025, including "
                         "behind-the-meter systems."}},
    {"sourceUrl": "https://example.org/clean-grid/policy-review-2026", "documentName": "Clean Grid Policy Review 2026",
     "publicationDate": "2026-03-02", "focus": "policy", "context": "Annual review of clean-grid policy.",
     "passages": {"M12": "Three states added sodium-ion storage to their procurement targets this year.",
                  "M13": "A federal safety standard for sodium-ion systems is expected in late 2026."}},
]

GOLD_CLAIMS = {  # the claim of each passage, in other words: POC 2's fixed input (E1)
    "M1": "The sodium-ion grid storage market grows 12% a year.",
    "M2": "Sodium-ion pack prices fell to $78/kWh in 2024.",
    "M3": "The sodium-ion grid storage market grows 18% a year.",
    "M4": "Sodium-ion pack prices averaged $64/kWh in 2025.",
    "M5": "Tessaly cells store 160 Wh/kg.",
    "M6": "Tessaly cells are rated for 6,000 cycles at 80% depth of discharge.",
    "M7": "Tessaly cells operate from -20 °C to 55 °C.",
    "M8": "The regulator approved sodium-ion systems for frequency-response markets on 27 January 2026.",
    "M9": "Grid-connected sodium-ion capacity was 4.2 GWh at the end of 2025.",
    "M10": "Kestrel Ridge broke ground on a 300 MWh Tessaly expansion.",
    "M11": "Sodium-ion capacity including behind-the-meter systems was 5.1 GWh at the end of 2025.",
    "M12": "Three states added sodium-ion storage to their procurement targets.",
    "M13": "A federal safety standard for sodium-ion systems is expected in late 2026.",
}
KIND = {"M1": "financial", "M2": "financial", "M3": "financial", "M4": "financial", "M5": "technical",
        "M6": "technical", "M7": "technical", "M8": "news", "M9": "financial", "M10": "news", "M11": "financial",
        "M12": "news", "M13": "news"}  # the content type each finding belongs to (C15)
# The same measure with different values. M2/M4 differ too, but each states its year: a trend, not a conflict
CONFLICTS = {"K1": ("M1", "M3", "temporal"), "K2": ("M9", "M11", "scope")}

# ---------------------------------------------------------------- the claim-source mapping (C1)

MAPPING_FIELDS = {  # all five are required: what each holds, and why provenance needs it
    "claim": "One factual sentence, in your own words: what the source says.",
    "sourceUrl": "The source's URL, copied exactly: where a reader can check the claim.",
    "documentName": "The source's title, copied exactly: how a reader recognises the source.",
    "relevantExcerpt": "The supporting passage, copied word for word: the evidence itself.",
    "publicationDate": "When the source was published (YYYY-MM-DD): needed to compare figures that differ (C3).",
}
MAPPING_SCHEMA = {"type": "object", "additionalProperties": False, "required": list(MAPPING_FIELDS),
                  "properties": {name: {"type": "string", "description": text}
                                 for name, text in MAPPING_FIELDS.items()}}


def gold_mappings() -> list[dict]:
    """One mapping per passage, in id order: what a perfect research round returns."""
    return [{"claim": GOLD_CLAIMS[passage_id], "sourceUrl": doc["sourceUrl"], "documentName": doc["documentName"],
             "relevantExcerpt": passage, "publicationDate": doc["publicationDate"]}
            for doc in DOCUMENTS for passage_id, passage in doc["passages"].items()]


def with_ids(mappings: list[dict]) -> list[dict]:
    """Number the mappings M1, M2, ... in order: the ids every citation marker points to."""
    return [{"id": f"M{n}", **mapping} for n, mapping in enumerate(mappings, 1)]


def validate_mapping(mapping: Any) -> list[str]:
    """[] when the mapping is valid: the 5 fields, an ISO date, a real source, and its excerpt word for word."""
    if not isinstance(mapping, dict) or sorted(mapping) != sorted(MAPPING_FIELDS):
        return [f"the mapping must have exactly the fields {list(MAPPING_FIELDS)}"]
    errors = [f"{name} is empty" for name in MAPPING_FIELDS if not str(mapping[name]).strip()]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(mapping["publicationDate"])):
        errors.append(f"publicationDate {mapping['publicationDate']!r} isn't YYYY-MM-DD")
    source = next((doc for doc in DOCUMENTS if (doc["sourceUrl"], doc["documentName"], doc["publicationDate"])
                   == (mapping["sourceUrl"], mapping["documentName"], mapping["publicationDate"])), None)
    if source is None:
        errors.append("sourceUrl, documentName and publicationDate match no source exactly")
    elif not any(str(mapping["relevantExcerpt"]) in passage for passage in source["passages"].values()):
        errors.append("relevantExcerpt isn't word for word in its source")
    return errors


def markers(text: str) -> list[str]:
    """The finding ids a text cites: [M3], [M3][M4] or [M3, M4]."""
    return [found for group in re.findall(r"\[([^\]]*)\]", text) for found in re.findall(r"M\d+", group)]


def sentences(text: str) -> list[str]:
    """Split prose into sentences. A marker right after a full stop belongs to that sentence; a decimal such as
    4.2 doesn't end one, because no space follows its point."""
    text = re.sub(r"([.!?])((?:\s*\[[^\]]*\])+)", r"\2\1", text)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if re.search(r"[A-Za-z]{3}", s)]


# ---------------------------------------------------------------- the library and the analysts (POC 1)

LIBRARY_TOOLS = ["mcp__library__list_sources", "mcp__library__read_source"]


def text_result(text: str, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": is_error}


def build_library_server() -> Any:
    @tool("list_sources", "Lists the library's sources for one research focus, with each source's URL, title and "
          "publication date.",
          {"type": "object", "properties": {"focus": {"type": "string", "enum": ["market", "policy"]}},
           "required": ["focus"]}, annotations=ToolAnnotations(readOnlyHint=True))
    async def list_sources(args: dict[str, Any]) -> dict[str, Any]:
        found = [{key: doc[key] for key in ("sourceUrl", "documentName", "publicationDate")}
                 for doc in DOCUMENTS if doc["focus"] == args.get("focus")]
        return text_result(json.dumps(found, indent=2))

    @tool("read_source", "Returns one source's full text: its title, URL and publication date, then one passage per "
          "line.", {"type": "object", "properties": {"source_url": {"type": "string"}}, "required": ["source_url"]},
          annotations=ToolAnnotations(readOnlyHint=True))
    async def read_source(args: dict[str, Any]) -> dict[str, Any]:
        doc = next((doc for doc in DOCUMENTS if doc["sourceUrl"] == str(args.get("source_url", "")).strip()), None)
        if doc is None:
            return text_result(f"Unknown source '{args.get('source_url')}'. Call list_sources first.", is_error=True)
        return text_result("\n".join([f"Title: {doc['documentName']}", f"URL: {doc['sourceUrl']}",
                                      f"Published: {doc['publicationDate']}", doc["context"],
                                      *doc["passages"].values()]))

    return create_sdk_mcp_server(name="library", version="1.0.0", tools=[list_sources, read_source])


MAPPING_FORMAT = (  # the analysts return mappings from the start, never prose (C5, C6)
    'Your final message must be only a JSON object {"findings": [...]}, with no other text. Each finding is a '
    'claim-source mapping with exactly these five fields, all required: "claim" (one factual sentence, in your '
    'own words), "sourceUrl", "documentName" and "publicationDate" (copied exactly from the source), and '
    '"relevantExcerpt" (the supporting passage, copied word for word). Write one finding per factual passage.')

AGENTS = {  # two research subagents, one focus each (C4)
    "market-analyst": AgentDefinition(
        description="Researches market data and technology: growth, prices, capacity and cell specifications.",
        prompt=("You are a market and technology analyst. Call list_sources with focus 'market', read every source "
                "with read_source, and report its findings. " + MAPPING_FORMAT),
        tools=LIBRARY_TOOLS, model="inherit", maxTurns=12),
    "policy-analyst": AgentDefinition(
        description="Researches regulation and news: approvals, standards, projects and policy.",
        prompt=("You are a regulation and news analyst. Call list_sources with focus 'policy', read every source "
                "with read_source, and report its findings. " + MAPPING_FORMAT),
        tools=LIBRARY_TOOLS, model="inherit", maxTurns=12),
}

COORDINATOR_PROMPT = (
    "You coordinate a research team. Never research yourself: delegate. market-analyst covers market data and "
    "technology; policy-analyst covers regulation and news. Give both of them the full research question in one "
    "response, with two Agent calls, and wait for both reports.")


def build_research_options(settings: Settings) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=settings.model_id,
        system_prompt=COORDINATOR_PROMPT,
        tools=["Agent"],  # the coordinator only delegates
        agents=AGENTS,  # the two analysts
        mcp_servers={"library": build_library_server()},  # list_sources and read_source, used by the analysts
        allowed_tools=["Agent"] + LIBRARY_TOOLS,  # no permission prompts
        disallowed_tools=["Agent(fork)"],  # no forks (01-02 E1)
        setting_sources=[],  # ignore ~/.claude settings, CLAUDE.md and hooks: the same run on any machine
        env={
            "ENABLE_TOOL_SEARCH": "false",  # send all tool schemas up front: no ToolSearch calls
            "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",  # each Agent result holds the report (01-02 E2)
            "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",  # only the two analysts (01-02 E3)
        },
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=20,  # safety cap (01 C16)
        max_budget_usd=settings.max_budget_usd,  # cost guard per call, subagents included
    )


# ---------------------------------------------------------------- synthesis (POC 1 and POC 2)

def build_synth_options(settings: Settings, system_prompt: str, schema: dict | None = None) -> ClaudeAgentOptions:
    """A synthesis session: no tools, only the findings in its prompt."""
    return ClaudeAgentOptions(
        model=settings.model_id,
        system_prompt=system_prompt,  # PLAIN_PROMPT, TRACEABLE_PROMPT or BRIEF_PROMPT
        output_format={"type": "json_schema", "schema": schema} if schema else None,  # POC 2's structured brief
        tools=[],  # it can't fetch anything the findings don't hold
        setting_sources=[],
        env={"ENABLE_TOOL_SEARCH": "false"},
        thinking={"type": "adaptive", "display": "summarized"},
        max_turns=5,  # safety cap (01 C16)
        max_budget_usd=settings.max_budget_usd,
    )


SYNTH_TASK = "Write a short brief on the state of sodium-ion grid storage in 2026 from these findings:\n"
PLAIN_PROMPT = "You write short research briefs from the findings you are given."  # the anti-pattern (C8)
TRACEABLE_PROMPT = (  # POC 1 (C8, C9)
    "You write short research briefs from the findings you are given. Combine related findings, but every "
    "sentence that states a fact must end with the id of each finding it uses, in brackets, such as [M3]: never "
    "state a fact without its marker. End with a 'References' section: one line per cited finding, in the form "
    "[Mn] documentName — sourceUrl — publicationDate, copied exactly from the findings.")
BRIEF_PROMPT = (  # POC 2 (C10, C12, C13, C15)
    "You write research briefs as structured JSON from the findings you are given. Group the findings into "
    "sections by content type: financial (numerical comparisons such as rates, prices and capacities), news "
    "(events such as approvals, announcements and projects) and technical (specifications and patterns). In a "
    "financial section, each entry gives measure, year (the period the value describes, or the source's "
    "publication year when it doesn't say) and value. Every entry cites the ids of the findings it uses, and "
    "every finding is cited at least once. When two findings give different values for the same measure, keep "
    "both entries and add the pair to conflicts, with both values, their citations and a possibleExplanation "
    "(different reporting periods, methods or scope). Never choose one value over another.")

NULLABLE = {"type": ["string", "null"]}
ENTRY = {"type": "object", "required": ["text", "citations"],
         "properties": {"text": {"type": "string"}, "measure": NULLABLE, "year": NULLABLE, "value": NULLABLE,
                        "citations": {"type": "array", "items": {"type": "string"}}}}
SECTION = {"type": "object", "required": ["title", "content_type", "entries"],
           "properties": {"title": {"type": "string"},
                          "content_type": {"type": "string", "enum": ["financial", "news", "technical"]},
                          "entries": {"type": "array", "items": ENTRY}}}
CONFLICT = {"type": "object", "required": ["measure", "values", "possibleExplanation"],
            "properties": {"measure": {"type": "string"},
                           "values": {"type": "array", "items": {
                               "type": "object", "required": ["value", "citation"],
                               "properties": {"value": {"type": "string"}, "citation": {"type": "string"}}}},
                           "possibleExplanation": {"type": "string"}}}
BRIEF_SCHEMA = {"type": "object", "required": ["sections", "conflicts"],
                "properties": {"sections": {"type": "array", "items": SECTION},
                               "conflicts": {"type": "array", "items": CONFLICT}}}
