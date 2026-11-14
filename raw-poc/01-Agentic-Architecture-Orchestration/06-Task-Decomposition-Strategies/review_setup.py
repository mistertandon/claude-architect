"""
review_setup.py - what both review architectures share: the repo loader and its numbered listing, ONE reviewer
prompt, ONE per-file review schema, the options, run_review(), and the answer key that scores a review.

Same model, same prompt, same schema in both POCs: only the structure of the review changes (C7, C11).
"""

from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultError, ResultMessage, query

from common import POC_DIR, Settings

REPO_DIR = POC_DIR / "sample_repo"
SOURCE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")


def load_repo(path: Path = REPO_DIR) -> list[dict[str, Any]]:
    """Read every source file in the folder, sorted by name: that is the review order (C1)."""
    files = [(p.name, p.read_text(encoding="utf-8")) for p in sorted(path.iterdir()) if p.suffix in SOURCE_EXTENSIONS]
    if not files:
        raise ValueError(f"no {SOURCE_EXTENSIONS} files in {path}")
    return [{"index": i, "name": name, "text": text, "lines": len(text.splitlines())}
            for i, (name, text) in enumerate(files, 1)]


def format_file(f: dict[str, Any]) -> str:
    """The ONLY way code enters a prompt: a header and numbered lines, the same in both POCs (E1)."""
    numbered = [f"{i:>4} | {line}" for i, line in enumerate(f["text"].splitlines(), 1)]
    return f"=== {f['name']} ({f['lines']} lines) ===\n" + "\n".join(numbered)


# ---------------------------------------------------------------- one prompt and one item schema for both POCs

REVIEWER_PROMPT = (
    "You are a senior TypeScript reviewer for the Fernway Outfitters order service. Find real defects: logic errors, "
    "unhandled edge cases, security problems and performance problems. Give every file the same depth of review, "
    "from the first file to the last. For each issue, give the exact line number from the numbered listing, a "
    "severity (critical, major or minor) and a one-sentence description, and set bug_count to the number of issues. "
    "For each file, also record its interface for later cross-file checks: exports (each export's signature, units "
    "and error behavior) and uses (each call into another module: what it passes and what it assumes about the result)."
)

FILE_REVIEW = {  # structured per-file feedback: bug count, severities, line references (C6)
    "type": "object",
    "properties": {
        "file": {"type": "string"},
        "bug_count": {"type": "integer"},
        "issues": {"type": "array", "items": {
            "type": "object",
            "properties": {"line": {"type": "integer"},
                           "severity": {"type": "string", "enum": ["critical", "major", "minor"]},
                           "description": {"type": "string"}},
            "required": ["line", "severity", "description"]}},
        "exports": {"type": "array", "items": {"type": "string"}},  # the interface: what the integration pass reads
        "uses": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["file", "bug_count", "issues", "exports", "uses"],
}
CROSS_FILE_ISSUES = {"type": "array", "items": {
    "type": "object",
    "properties": {"files": {"type": "array", "items": {"type": "string"}},
                   "kind": {"type": "string", "enum": ["data_flow", "api_consistency", "pattern_consistency"]},
                   "description": {"type": "string"}},
    "required": ["files", "kind", "description"]}}

SINGLE_PASS_SCHEMA = {"type": "object", "properties": {"files": {"type": "array", "items": FILE_REVIEW},
                                                       "cross_file_issues": CROSS_FILE_ISSUES},
                      "required": ["files", "cross_file_issues"]}
FILE_REVIEW_SCHEMA = FILE_REVIEW
INTEGRATION_SCHEMA = {"type": "object", "properties": {"cross_file_issues": CROSS_FILE_ISSUES},
                      "required": ["cross_file_issues"]}


def build_review_options(settings: Settings, schema: dict[str, Any]) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=settings.model_id,  # one model for every pass (C11)
        system_prompt=REVIEWER_PROMPT,  # one reviewer prompt for every pass, with the equal-depth rule (C7)
        output_format={"type": "json_schema", "schema": schema},  # validated JSON in ResultMessage.structured_output
        tools=[],  # no built-in tools: the code is in the prompt, and no pass can open another file
        setting_sources=[],  # ignore ~/.claude settings, CLAUDE.md and hooks: the same run on any machine
        env={"ENABLE_TOOL_SEARCH": "false"},  # no ToolSearch calls
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=settings.max_turns,  # safety cap (01 C16); a review needs only a few turns
        max_budget_usd=settings.max_budget_usd,  # cost guard per review call
    )


async def run_review(prompt: str, options: ClaudeAgentOptions) -> dict[str, Any] | None:
    """One review call = one NEW session with an empty history. Returns the validated JSON, or None on failure."""
    output = None
    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage) and message.subtype == "success":
                output = message.structured_output  # None here means no structured output: treat it as a failure
            # No `break`: a few system events can still arrive after the ResultMessage.
    except ResultError:  # raised AFTER the error ResultMessage, e.g. error_max_structured_output_retries
        pass
    return output


# ---------------------------------------------------------------- the answer key (made-up code, planted on purpose)

PLANTED = {  # one local bug per file: a piece of its line
    "checkout.ts": 'if (order.status = "paid")',  # assignment instead of comparison
    "inventory.ts": "units * unitFee === invoiced",  # exact equality between computed decimals
    "pricing.ts": "i <= tiers.length",  # off by one: reads past the last tier
}
CROSS_FILE = {  # each side looks right on its own: only the two files together show the bug
    "cents vs dollars": ("pricing.ts", "checkout.ts"),  # orderTotal() returns cents; checkout formats it as dollars
    "false vs throw": ("inventory.ts", "checkout.ts"),  # reserveStock() returns false; checkout waits for a throw
}
PATTERN_FILES, PATTERN_LINE = ("pricing.ts", "inventory.ts"), "lookup.find("  # the same forEach + nested find, twice


def flagged(review: dict, f: dict[str, Any], fragment: str) -> bool:
    """Does any issue point within 2 lines of the line that holds fragment?"""
    line = next(i for i, text in enumerate(f["text"].splitlines(), 1) if fragment in text)
    return any(abs(issue["line"] - line) <= 2 for issue in review.get("issues", []))


def score_review(reviews: dict[str, dict], files: list[dict[str, Any]], cross_file_issues: list[dict]) -> dict[str, Any]:
    """The lesson: depth per file, the same code judged the same way, and the cross-file layer."""
    by_name = {f["name"]: f for f in files}
    per_file = {}
    for f in files:
        review = reviews.get(f["name"], {})
        per_file[f["name"]] = {"issues": len(review.get("issues", [])),
                               "planted_bug_flagged": flagged(review, f, PLANTED[f["name"]])}
    # forEach + nested find, identical in both files: the same verdict = consistent, else a contradiction
    verdicts = {name: flagged(reviews.get(name, {}), by_name[name], PATTERN_LINE) for name in PATTERN_FILES}
    named = [{Path(name).name.lower() for name in issue["files"]} for issue in cross_file_issues]
    found = [label for label, pair in CROSS_FILE.items() if any(set(pair) <= files_named for files_named in named)]
    return {"per_file": per_file, "consistent": len(set(verdicts.values())) == 1, "cross_file_found": found}
