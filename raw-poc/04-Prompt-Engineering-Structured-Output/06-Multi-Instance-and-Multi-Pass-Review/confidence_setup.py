"""
confidence_setup.py - 06's per-file review (repo loader, numbered listing, reviewer prompt, answer key), with a
confidence score and its reason added to every finding, the verifier's schema, the options (fresh or resumed
session) and run_review(), which now also returns the session id.
"""

from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultError, ResultMessage, query

from common import POC_DIR, Settings

REPO_DIR = POC_DIR / "sample_repo"
SOURCE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")

ROUTE_THRESHOLD = 0.8  # raw confidence at or above this goes straight to the developer (C10)
TARGET_PRECISION = 0.9  # a calibrated threshold keeps at least 90% of the findings above it confirmed (C15)
SUBSET = ["checkout.ts", "inventory.ts", "pricing.ts"]  # the files the second instance re-judges (all 3 here)


def load_repo(path: Path = REPO_DIR) -> list[dict[str, Any]]:
    """Read every source file in the folder, sorted by name (copied from 06)."""
    files = [(p.name, p.read_text(encoding="utf-8")) for p in sorted(path.iterdir()) if p.suffix in SOURCE_EXTENSIONS]
    if not files:
        raise ValueError(f"no {SOURCE_EXTENSIONS} files in {path}")
    return [{"index": i, "name": name, "text": text, "lines": len(text.splitlines())}
            for i, (name, text) in enumerate(files, 1)]


def format_file(f: dict[str, Any]) -> str:
    """The ONLY way code enters a prompt: a header and numbered lines (copied from 06)."""
    numbered = [f"{i:>4} | {line}" for i, line in enumerate(f["text"].splitlines(), 1)]
    return f"=== {f['name']} ({f['lines']} lines) ===\n" + "\n".join(numbered)


# ---------------------------------------------------------------- prompts and schemas

REVIEWER_PROMPT = (  # 06's reviewer prompt
    "You are a senior TypeScript reviewer for the Fernway Outfitters order service. Find real defects: logic errors, "
    "unhandled edge cases, security problems and performance problems. Give every file the same depth of review, "
    "from the first file to the last. For each issue, give the exact line number from the numbered listing, a "
    "severity (critical, major or minor) and a one-sentence description, and set bug_count to the number of issues. "
    "For each file, also record its interface for later cross-file checks: exports (each export's signature, units "
    "and error behavior) and uses (each call into another module: what it passes and what it assumes about the result)."
)
CONFIDENCE_RULE = (" For each issue, also give confidence, a number from 0.0 to 1.0 for how sure you are that it is a "
                   "real defect, and confidence_reason, one sentence on why.")
VERIFIER_PROMPT = ("You are an independent code reviewer. Another reviewer reported the issues below. For each one, "
                   "decide from the code alone whether it is a real defect: confirmed or rejected, with your own "
                   "confidence (0.0 to 1.0) and a one-sentence reason.")

CONFIDENT_ISSUE = {"type": "object",  # 06's issue item, plus a score and its reason (C9)
                   "required": ["line", "severity", "description", "confidence", "confidence_reason"],
                   "properties": {"line": {"type": "integer"},
                                  "severity": {"type": "string", "enum": ["critical", "major", "minor"]},
                                  "description": {"type": "string"},
                                  "confidence": {"type": "number"},  # range checked in Python: no minimum/maximum here
                                  "confidence_reason": {"type": "string"}}}
FILE_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {"file": {"type": "string"}, "bug_count": {"type": "integer"},
                   "issues": {"type": "array", "items": CONFIDENT_ISSUE},
                   "exports": {"type": "array", "items": {"type": "string"}},
                   "uses": {"type": "array", "items": {"type": "string"}}},
    "required": ["file", "bug_count", "issues", "exports", "uses"],
}
INTEGRATION_SCHEMA = {"type": "object", "required": ["cross_file_issues", "contradictions"], "properties": {
    "cross_file_issues": {"type": "array", "items": {
        "type": "object", "required": ["files", "description", "confidence", "confidence_reason"],
        "properties": {"files": {"type": "array", "items": {"type": "string"}}, "description": {"type": "string"},
                       "confidence": {"type": "number"}, "confidence_reason": {"type": "string"}}}},
    "contradictions": {"type": "array", "items": {  # per-file findings that judge the same pattern differently (C6)
        "type": "object", "required": ["files", "description"],
        "properties": {"files": {"type": "array", "items": {"type": "string"}}, "description": {"type": "string"}}}},
}}
VERIFY_SCHEMA = {"type": "object", "required": ["verdicts"], "properties": {"verdicts": {"type": "array", "items": {
    "type": "object", "required": ["finding_id", "verdict", "confidence", "reason"],
    "properties": {"finding_id": {"type": "string"}, "verdict": {"type": "string", "enum": ["confirmed", "rejected"]},
                   "confidence": {"type": "number"}, "reason": {"type": "string"}}}}}}


def build_review_options(settings: Settings, schema: dict, system_prompt: str = REVIEWER_PROMPT + CONFIDENCE_RULE,
                         resume: str | None = None) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=settings.model_id,  # one model for every pass and both verifiers
        system_prompt=system_prompt,  # the reviewer's prompt, or the independent verifier's
        output_format={"type": "json_schema", "schema": schema},  # validated JSON in ResultMessage.structured_output
        resume=resume,  # None: a fresh session (independent); a session_id: the same reviewer again (C14)
        tools=[],  # no built-in tools: the code is in the prompt
        setting_sources=[],  # ignore ~/.claude settings, CLAUDE.md and hooks: the same run on any machine
        env={"ENABLE_TOOL_SEARCH": "false"},  # no ToolSearch calls
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=settings.max_turns,  # safety cap (01 C16)
        max_budget_usd=settings.max_budget_usd,  # cost guard per call
    )


async def run_review(prompt: str, options: ClaudeAgentOptions) -> dict[str, Any]:
    """One call. Without resume it is a NEW session with an empty history. Returns the output and the session id."""
    output, session_id = None, None
    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                session_id = message.session_id  # set on every result: the key for resume=
                if message.subtype == "success":
                    output = message.structured_output  # None here means no structured output: a failure
            # No `break`: a few system events can still arrive after the ResultMessage.
    except ResultError:  # raised AFTER the error ResultMessage, e.g. error_max_structured_output_retries
        pass
    return {"output": output, "session_id": session_id}


# ---------------------------------------------------------------- the answer key: the labelled set (from 06)

ANSWER_KEY = {  # per file, the lines a correct finding points at: its planted bug, a cross-file side, the pattern
    "checkout.ts": ['if (order.status = "paid")', "const amountDollars = orderTotal", "reserveStock(item.sku"],
    "inventory.ts": ["units * unitFee === invoiced", "Returns false when stock is short", "lookup.find("],
    "pricing.ts": ["i <= tiers.length", "Returns the order total in integer cents", "lookup.find("],
}
CROSS_FILE = {"cents vs dollars": ("pricing.ts", "checkout.ts"), "false vs throw": ("inventory.ts", "checkout.ts")}


def label(item: dict, files: list[dict[str, Any]]) -> str:
    """correct when the finding points at a known defect (within 2 lines), incorrect otherwise."""
    if "files" in item:  # a cross-file finding: correct when it names both files of a known pair
        named = {Path(name).name.lower() for name in item["files"]}
        return "correct" if any(set(pair) <= named for pair in CROSS_FILE.values()) else "incorrect"
    text = next(f["text"] for f in files if f["name"] == item["file"]).splitlines()
    lines = [i for i, line in enumerate(text, 1) for fragment in ANSWER_KEY[item["file"]] if fragment in line]
    return "correct" if any(abs(item["line"] - line) <= 2 for line in lines) else "incorrect"
