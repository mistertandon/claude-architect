"""
propagation_setup.py - the Helios source library with planted failures, the researcher's search layer
(search_once(), search_with_retry(), build_report()), the report contract (REPORT_SCHEMA, validate_report()), and
POC 2's coordinator: its two tool servers, prompts, the researcher subagent and build_propagation_options().

A Claude subagent can't catch a Python exception or wait between attempts, so the subagent's error handling lives
in its tool's code: search_sources catches the backend's exceptions, retries locally, and returns ONE report.
"""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, ToolAnnotations, create_sdk_mcp_server, tool

from common import Settings

SOURCES = {  # the mock library: biomass, fusion and ocean thermal never return a source
    "solar": [{"id": "SOL-1", "fact": "Solar capacity grew 31% in 2025."},
              {"id": "SOL-2", "fact": "Utility-scale solar cost fell to $27.40/MWh."},
              {"id": "SOL-3", "fact": "Rooftop systems made up 38% of new solar capacity."}],
    "wind": [{"id": "WND-1", "fact": "Offshore wind added 19.6 GW in 2025."},
             {"id": "WND-2", "fact": "The average wind capacity factor reached 41.3%."},
             {"id": "WND-3", "fact": "Turbine orders rose 12% year on year."}],
    "geothermal": [{"id": "GEO-1", "fact": "Geothermal output rose 8.7%."},
                   {"id": "GEO-2", "fact": "Enhanced-geothermal pilot wells reached 245 °C."},
                   {"id": "GEO-3", "fact": "Three new binary-cycle plants came online."},
                   {"id": "GEO-4", "fact": "Drilling costs fell 14% per metre."},
                   {"id": "GEO-5", "fact": "Geothermal heat networks served 1.2 million homes."}],
    "tidal": [{"id": "TID-1", "fact": "Tidal stream capacity reached 1.9 GW."},
              {"id": "TID-2", "fact": "The Kestrel Strait array ran at a 37.5% capacity factor."},
              {"id": "TID-3", "fact": "Two new tidal stream projects passed permitting."}],
    "hydropower": [{"id": "HYD-1", "fact": "Hydropower supplied 14.2% of electricity."},
                   {"id": "HYD-2", "fact": "Pumped-storage capacity rose to 212 GW."},
                   {"id": "HYD-3", "fact": "Drought cut output at 6 major dams by 9%."}],
}
NARROW = {"geothermal": "capacity", "tidal": "stream"}  # the keyword that makes a query narrow enough to finish
BROAD_ARRIVALS = {"geothermal": {1: ["GEO-1", "GEO-2"], 2: ["GEO-3"]}, "tidal": {1: ["TID-1"]}}  # before the timeout
REGIONS = ["global", "americas", "europe", "asia"]


class SourceRejected(Exception):
    """The source answered, and the answer was no: asking again gets the same answer."""

    def __init__(self, failure_type: str, description: str, alternatives: list[str]):
        super().__init__(description)
        self.failure_type, self.description, self.alternatives = failure_type, description, alternatives


REJECTIONS = {  # topic -> (failure type, description, alternatives) of a refusal no retry can change
    "biomass": ("business", "The Bioenergy Monitor dataset is licensed: access costs $4,800, and the research budget "
                "allows $500 per source.",
                ["ask a human to approve the $4,800 licence", "report biomass as unavailable"]),
    "fusion": ("permission", "Access denied: the Aurora Labs fusion data room needs the research:restricted scope, "
               "which this research key doesn't have.",
               ["ask an administrator to grant the research:restricted scope", "report fusion as unavailable"]),
}


def backend_stream(topic: str, query: str, region: str | None, attempt: int):
    """The mock backend: yields sources one at a time, and raises the failures planted for each topic."""
    if topic in REJECTIONS:
        raise SourceRejected(*REJECTIONS[topic])
    if topic == "hydropower" and region not in REGIONS:
        raise SourceRejected("validation", "Hydropower sources are indexed by region, and no region was given.",
                             ["call search_sources again with region set to global, americas, europe or asia"])
    if topic == "ocean thermal":
        return  # the library has no 2026 sources on it: the query runs and finds nothing
    if topic not in SOURCES:
        raise SourceRejected("validation", f"Unknown topic '{topic}'.", ["use one of the brief's topics"])
    if topic == "wind" and attempt == 1:
        raise TimeoutError("the Helios library didn't answer within 10 s")
    if topic == "wind" and attempt == 2:
        raise ConnectionError("the connection to the Helios library was reset")
    if topic in NARROW and NARROW[topic] not in query.lower():  # a broad query: a few sources, then a timeout
        yield from (s for s in SOURCES[topic] if s["id"] in BROAD_ARRIVALS[topic].get(attempt, []))
        raise TimeoutError("the Helios library didn't answer within 10 s")
    yield from SOURCES[topic]


# ---------------------------------------------------------------- the researcher's search layer (POC 1)

MAX_RETRIES = 3
BASE_DELAY = 1  # seconds; the wait doubles with each retry: 1, 2, 4


def search_once(topic: str, query: str, region: str | None, attempt: int) -> dict:
    """One attempt. try/except separates an access failure from a refusal and from a valid empty result (C8).
    backend_stream() is called only here, inside the try: no exception can escape as a bare message (C3)."""
    sources = []
    try:
        for source in backend_stream(topic, query, region, attempt):
            sources.append(source)  # what arrived stays, even if the stream breaks later (C13)
    except (TimeoutError, ConnectionError) as exc:  # the query didn't run to the end: worth retrying
        return {"outcome": "access_failure", "sources": sources, "detail": f"{type(exc).__name__}: {exc}"}
    except SourceRejected as exc:  # the source answered, and the answer was no: a retry gets the same answer
        return {"outcome": exc.failure_type, "sources": sources, "description": exc.description,
                "alternatives": exc.alternatives}
    return {"outcome": "ok", "sources": sources}  # the query ran: 0 sources is a valid answer, not a failure


async def search_with_retry(topic: str, query: str, region: str | None, state: "PropagationState") -> dict:
    """Retry access failures locally, MAX_RETRIES times with a doubling wait (C10, C12). Only the final outcome
    leaves the subagent, as one report (C11)."""
    retrieved: dict[str, dict] = {}  # source id -> source, across ALL attempts (C13)
    for attempt in range(1, MAX_RETRIES + 2):
        result = search_once(topic, query, region, attempt)
        retrieved.update({source["id"]: source for source in result["sources"]})  # a repeat counts once
        retry = result["outcome"] == "access_failure" and attempt <= MAX_RETRIES  # a refusal is never retried
        wait = BASE_DELAY * 2 ** (attempt - 1) if retry else 0  # computed, so the doubling is visible
        state.attempts.append((topic, attempt, result["outcome"], [s["id"] for s in result["sources"]], wait,
                               result.get("detail", "")))
        if not retry:
            break
        await asyncio.sleep(wait)
    report = build_report(topic, query, region, result, list(retrieved.values()), attempt)
    state.reports.append(report)
    return report


def build_report(topic: str, query: str, region: str | None, final: dict, retrieved: list[dict], attempts: int) -> dict:
    """The one report that leaves the subagent: REPORT_SCHEMA, filled from the final outcome (C1, C5, C9)."""
    if final["outcome"] == "ok":
        return {"topic": topic, "status": "success", "shouldRetry": False, "results": final["sources"], "error": None}
    attempted = {"tool": "search_sources", "query": query, "parameters": {"region": region}}
    if final["outcome"] == "access_failure":
        narrower = f"{topic} {NARROW.get(topic, 'specific')} 2026"
        error = {"failureType": "transient", "attemptedAction": attempted, "partialResults": retrieved,
                 "alternativeApproaches": [f"retry with a narrower query, such as '{narrower}'",
                                           f"proceed with the {len(retrieved)} partial result(s)"],
                 "description": f"The Helios library timed out on all {attempts} attempts (1 try and {attempts - 1} "
                                f"local retries); {len(retrieved)} source(s) arrived before the timeouts."}
    else:  # a refusal keeps its own failure type, description and alternatives
        error = {"failureType": final["outcome"], "attemptedAction": attempted, "partialResults": retrieved,
                 "alternativeApproaches": final["alternatives"], "description": final["description"]}
    return {"topic": topic, "status": "partial_failure" if retrieved else "error",
            "shouldRetry": error["failureType"] == "transient", "results": [], "error": error}


ERROR_SCHEMA = {
    "type": ["object", "null"],
    "description": "null on success; otherwise the context the coordinator decides with.",
    "required": ["failureType", "attemptedAction", "partialResults", "alternativeApproaches", "description"],
    "properties": {
        "failureType": {"type": "string", "enum": ["transient", "validation", "business", "permission"],
                        "description": "The kind of failure, which selects the recovery."},
        "attemptedAction": {"type": "object", "required": ["tool", "query", "parameters"],
                            "description": "Exactly what was tried, so a retry can change it on purpose."},
        "partialResults": {"type": "array",
                           "description": "Every source retrieved before the failure, across all attempts."},
        "alternativeApproaches": {"type": "array", "items": {"type": "string"},
                                  "description": "Recovery options the coordinator can choose from."},
        "description": {"type": "string", "description": "What went wrong, in one or two sentences."},
    },
}
REPORT_SCHEMA = {  # what a researcher returns for one topic; each description says why the coordinator needs it
    "type": "object", "required": ["topic", "status", "shouldRetry", "results", "error"],
    "properties": {
        "topic": {"type": "string", "description": "The topic this report covers."},
        "status": {"type": "string", "enum": ["success", "partial_failure", "error"],
                   "description": "success: the search finished, even with 0 results. partial_failure: it failed after "
                                  "retrieving some sources. error: it failed with nothing retrieved."},
        "shouldRetry": {"type": "boolean", "description": "true only for an access failure (timeout, connection "
                                                          "error): trying again may work."},
        "results": {"type": "array",
                    "description": "The sources of a finished search; [] for a valid empty result or a failure."},
        "error": ERROR_SCHEMA,
    },
}


def validate_report(report: Any) -> list[str]:
    """The contract, checked: [] when the report is valid. A bare "search unavailable" message fails it (C3)."""
    if not isinstance(report, dict) or sorted(report) != sorted(REPORT_SCHEMA["required"]):
        return [f"the report must have exactly the keys {REPORT_SCHEMA['required']}"]
    status, error, errors = report["status"], report["error"], []
    if status not in REPORT_SCHEMA["properties"]["status"]["enum"]:
        errors.append(f"unknown status {status!r}")
    if not isinstance(report["shouldRetry"], bool) or not isinstance(report["results"], list):
        errors.append("shouldRetry must be a boolean and results a list")
    error_schema = REPORT_SCHEMA["properties"]["error"]
    if status == "success" and error is not None:
        errors.append("a success must have error null")
    if status in ("partial_failure", "error"):
        if report["results"] != []:
            errors.append("a failure must have results []")
        if not isinstance(error, dict) or sorted(error) != sorted(error_schema["required"]):
            return errors + [f"a failure needs an error object with exactly {error_schema['required']}"]
        if error["failureType"] not in error_schema["properties"]["failureType"]["enum"]:
            errors.append(f"unknown failureType {error['failureType']!r}")
        if not all(key in (error["attemptedAction"] or {}) for key in ("tool", "query", "parameters")):
            errors.append("attemptedAction needs tool, query and parameters")
        alternatives = error["alternativeApproaches"]
        if not alternatives or not all(isinstance(a, str) for a in alternatives) or not error["description"]:
            errors.append("a failure needs alternativeApproaches and a description")
        if bool(error["partialResults"]) != (status == "partial_failure"):
            errors.append("partialResults must be non-empty exactly for a partial_failure")
    transient = isinstance(error, dict) and error.get("failureType") == "transient"
    if report["shouldRetry"] != transient:
        errors.append("shouldRetry must be true exactly for a transient failure")
    return errors


def parse_json_object(text: str) -> Any:
    """A subagent's report is TEXT: take its first JSON object and ignore what follows, such as 'agentId: ...'."""
    if "{" not in text:
        raise ValueError("the report holds no JSON object")
    value, _ = json.JSONDecoder().raw_decode(text[text.index("{"):])
    return value


# ---------------------------------------------------------------- the coordinator (POC 2)

@dataclass
class PropagationState:
    """One per run (05-Agent-SDK-Hooks' HookState pattern): every handler writes to it."""

    attempts: list[tuple] = field(default_factory=list)  # (topic, attempt, outcome, source ids, wait, exception)
    reports: list[dict] = field(default_factory=list)  # every report search_with_retry() built, in order
    escalations: list[dict] = field(default_factory=list)
    alerts: list[dict] = field(default_factory=list)


def text_result(text: str, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": is_error}


def build_sources_server(state: PropagationState) -> Any:
    @tool("search_sources", "Searches the Helios Institute source library for one topic. It retries timeouts itself "
          "(3 retries, waiting 1, 2 and 4 seconds) and returns one JSON report with status, shouldRetry, results and "
          "error.",
          {"type": "object", "properties": {"topic": {"type": "string"}, "query": {"type": "string"},
                                            "region": {"type": "string", "enum": REGIONS}},
           "required": ["topic", "query"]},
          annotations=ToolAnnotations(readOnlyHint=True))
    async def search_sources(args: dict[str, Any]) -> dict[str, Any]:
        report = await search_with_retry(str(args.get("topic", "")).strip().lower(), str(args.get("query", "")),
                                         args.get("region"), state)
        # is_error reaches only the researcher. The coordinator gets the researcher's final message, so the outcome
        # must be written INTO the report (C5)
        return text_result(json.dumps(report, ensure_ascii=False), is_error=report["status"] != "success")

    return create_sdk_mcp_server(name="sources", version="1.0.0", tools=[search_sources])


def build_ops_server(state: PropagationState) -> Any:
    @tool("escalate_to_human", "Opens a case for a human to decide about one topic of the brief, such as approving "
          "a paid licence.",
          {"type": "object", "properties": {"topic": {"type": "string"}, "reason": {"type": "string"}},
           "required": ["topic", "reason"]})
    async def escalate_to_human(args: dict[str, Any]) -> dict[str, Any]:
        case = {"id": f"ESC-{len(state.escalations) + 1:04d}", "topic": args.get("topic"), "reason": args.get("reason")}
        state.escalations.append(case)
        return text_result(f"Escalation {case['id']} opened for {case['topic']}.")

    @tool("alert_admin", "Alerts an administrator that the research key lacks an access scope a topic needs.",
          {"type": "object", "properties": {"topic": {"type": "string"}, "scope": {"type": "string"},
                                            "reason": {"type": "string"}}, "required": ["topic", "scope", "reason"]})
    async def alert_admin(args: dict[str, Any]) -> dict[str, Any]:
        alert = {"id": f"ADM-{len(state.alerts) + 1:04d}", "topic": args.get("topic"), "scope": args.get("scope"),
                 "reason": args.get("reason")}
        state.alerts.append(alert)
        return text_result(f"Alert {alert['id']} sent: an administrator will review the {alert['scope']} scope.")

    return create_sdk_mcp_server(name="ops", version="1.0.0", tools=[escalate_to_human, alert_admin])


SUFFICIENT_SOURCES = 3  # partial results at or above this are enough to proceed (C17)

RECOVERY_POLICY = (  # one recovery per failure type (C16), plus the partial-results rule (C17)
    "- success: use the results. A success with no results is a valid answer: don't retry it.\n"
    f"- transient: if partialResults hold at least {SUFFICIENT_SOURCES} sources, proceed with them and mark the topic "
    "limited; otherwise delegate the topic once more with the narrower query from alternativeApproaches.\n"
    "- validation: delegate the topic once more, with the parameters fixed as the error says.\n"
    "- business: don't retry; call escalate_to_human with the topic and the reason.\n"
    "- permission: don't retry; call alert_admin with the topic, the missing scope and the reason.")

COORDINATOR_PROMPT = (
    "You coordinate the research for the Helios Institute 2026 renewables brief. Never search yourself: give each "
    "topic to the researcher subagent with the Agent tool. Every Agent prompt is exactly three lines: "
    "'topic: <topic>', 'query: <query>' and 'parameters: <JSON object, {} if none>'. First, delegate every topic at "
    "once, in one response, with the query '<topic> 2026' and parameters {}. Each researcher returns a JSON report "
    "with status, shouldRetry, results and error. Recover from each report by its status and failureType:\n"
    + RECOVERY_POLICY + "\n"
    "Never drop a topic, and never abandon the brief because one topic failed. Write findings only from sources the "
    "reports returned, citing their ids. Give every topic one coverage entry: well_supported (complete results), "
    "limited (partial results, with the reason) or unavailable (no usable results, with what failed and why).")

AGENTS = {
    "researcher": AgentDefinition(
        description="Researches one topic of the Helios brief with search_sources and returns its JSON report.",
        prompt=("You are a research subagent. Call search_sources exactly once, with exactly the topic, query and "
                "parameters in your task and nothing else. Your final message must be only the JSON report that "
                "search_sources returned, unchanged: never summarise it, shorten it or describe an error in your own "
                "words."),  # the report crosses the hop as this final message (C2)
        tools=["mcp__sources__search_sources"],  # its only tool
        model="inherit",
        maxTurns=5,
    ),
}

FINDING = {"type": "object", "required": ["claim", "source_ids"],
           "properties": {"claim": {"type": "string"}, "source_ids": {"type": "array", "items": {"type": "string"}}}}
SECTION = {"type": "object", "required": ["topic", "findings"],
           "properties": {"topic": {"type": "string"}, "findings": {"type": "array", "items": FINDING}}}
COVERAGE_ENTRY = {"type": "object", "required": ["topic", "status", "reason", "sources_used"],
                  "properties": {"topic": {"type": "string"},
                                 "status": {"type": "string", "enum": ["well_supported", "limited", "unavailable"]},
                                 "reason": {"type": "string"},
                                 "sources_used": {"type": "integer"}}}
BRIEF_SCHEMA = {  # the findings, and a SEPARATE coverage section (C18, C20)
    "type": "object", "required": ["sections", "coverage"],
    "properties": {"sections": {"type": "array", "items": SECTION},
                   "coverage": {"type": "array", "items": COVERAGE_ENTRY}},
}


def build_propagation_options(settings: Settings, state: PropagationState) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=settings.model_id,
        system_prompt=COORDINATOR_PROMPT,  # the recovery policy and the coverage rule
        output_format={"type": "json_schema", "schema": BRIEF_SCHEMA},  # the brief as validated JSON
        tools=["Agent"],  # the coordinator's only built-in tool: it delegates
        agents=AGENTS,  # the researcher subagent
        mcp_servers={"sources": build_sources_server(state),  # search_sources, used by the researcher
                     "ops": build_ops_server(state)},  # escalate_to_human and alert_admin, used by the coordinator
        allowed_tools=["Agent", "mcp__sources__search_sources", "mcp__ops__escalate_to_human", "mcp__ops__alert_admin"],
        disallowed_tools=["Agent(fork)"],  # no forks (01-02 E1)
        setting_sources=[],  # ignore ~/.claude settings, CLAUDE.md and hooks: the same run on any machine
        env={
            "ENABLE_TOOL_SEARCH": "false",  # send all tool schemas up front: no ToolSearch calls
            "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",  # each Agent result holds the report (01-02 E2)
            "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",  # only the researcher: no general-purpose (01-02 E3)
        },
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=30,  # safety cap per coordinator call (01 C16)
        max_budget_usd=settings.max_budget_usd,  # cost guard per coordinator call, its subagents included
    )
