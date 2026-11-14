"""
criteria_setup.py - what both POCs share: the 5 snippets and their answer key, ONE findings schema, the system
prompts under test, the options, review() and the scorer.

Model, schema, snippets and options never change between prompt versions: only the system prompt does (C13).
"""

from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultError, ResultMessage, query

from common import POC_DIR, Settings

SNIPPETS_DIR = POC_DIR / "snippets"


def load_snippets() -> list[dict[str, Any]]:
    """The 5 TypeScript files, sorted by name (the order of the listings in every prompt)."""
    files = [(p.name, p.read_text(encoding="utf-8")) for p in sorted(SNIPPETS_DIR.glob("*.ts"))]
    if len(files) != 5:
        raise RuntimeError(f"expected 5 .ts files in {SNIPPETS_DIR}, found {len(files)}")
    return [{"name": name, "text": text, "lines": len(text.splitlines())} for name, text in files]


def format_file(f: dict[str, Any]) -> str:
    """The ONLY way code enters a prompt: a header and numbered lines (copied from 06's review_setup.py)."""
    numbered = [f"{i:>4} | {line}" for i, line in enumerate(f["text"].splitlines(), 1)]
    return f"=== {f['name']} ({f['lines']} lines) ===\n" + "\n".join(numbered)


# ---------------------------------------------------------------- the answer key: 9 real defects, 7 decoys (C2)

PLANTED = [  # (id, file, a piece of its line, kind, true severity of a real defect)
    {"id": i, "file": f, "contains": c, "kind": k, "severity": s} for i, f, c, k, s in [
        ("R1", "payments.ts", "WHERE order_id = '\" + orderId", "real", "critical"),  # SQL built from input
        ("D1", "payments.ts", "var attempts = 0;", "decoy", None),  # style: var
        ("R2", "payments.ts", "card.number", "real", "critical"),  # card number in the logs
        ("R3", "checkout.ts", 'order.status = "paid"', "real", "critical"),  # = in an if: ships unpaid orders
        ("D2", "checkout.ts", "void auditLog.write", "decoy", None),  # local pattern: fire-and-forget
        ("R4", "checkout.ts", "line.quantity += qty", "real", "major"),  # unchecked find(): crash
        ("R5", "inventory.ts", "if (isReserved(sku))", "real", "major"),  # missing await: always truthy
        ("D3", "inventory.ts", 'units < 5 ? "low"', "decoy", None),  # style: nested ternary
        ("R6", "inventory.ts", "i <= bins.length", "real", "major"),  # off by one: throws
        ("R7", "discounts.ts", "getMonth()", "real", "minor"),  # zero-based month in a label
        ("D4", "discounts.ts", "TODO: load promo codes", "decoy", None),  # comment: a harmless TODO
        ("R8", "discounts.ts", "return codes.sort();", "real", "minor"),  # comment says copy, code mutates
        ("D6", "shipping.ts", "2025 carrier contract", "decoy", None),  # comment: dated, contradicts nothing
        ("D7", "shipping.ts", "function calc_rate", "decoy", None),  # style: snake_case
        ("D5", "shipping.ts", "zone == null", "decoy", None),  # local pattern: == null on purpose
        ("R9", "shipping.ts", "subtotal > 50", "real", "minor"),  # "$50 or more" but > 50
    ]
]


def locate(text: str, contains: str) -> int:
    """The line that holds a spot, found from its text: no hard-coded line numbers."""
    return next(i for i, line in enumerate(text.splitlines(), 1) if contains in line)


# ---------------------------------------------------------------- one schema and the prompts under test

REVIEW_SCHEMA = {"type": "object", "required": ["findings"], "properties": {"findings": {"type": "array", "items": {
    "type": "object",
    "properties": {
        "file": {"type": "string"},
        "line": {"type": "integer"},
        # style and other are allowed, so the vague prompt CAN report noise: the schema filters nothing (E1)
        "category": {"type": "string", "enum": ["bug", "security", "comment_mismatch", "style", "other"]},
        "severity": {"type": "string", "enum": ["critical", "major", "minor"]},
        "description": {"type": "string"},
    },
    "required": ["file", "line", "category", "severity", "description"]}}}}

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


def criteria_prompt(severity_rules: str) -> str:
    """Explicit categories: what to REPORT and what to SKIP (C7), the comment rule (C8), and the severity rules."""
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


CRITERIA_PROMPT = criteria_prompt(SEVERITY_PROSE)  # step 2: explicit categories, prose severities
EXAMPLES_PROMPT = criteria_prompt(SEVERITY_EXAMPLES)  # step 3: the same, with code examples instead of prose

REVIEW_TASK = "Review these 5 files of the order service.\n\n"


def build_review_options(settings: Settings, system_prompt: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=settings.model_id,  # one model for every prompt version
        system_prompt=system_prompt,  # the ONLY thing that changes between versions
        output_format={"type": "json_schema", "schema": REVIEW_SCHEMA},  # the same findings shape every time (E1)
        tools=[],  # no built-in tools: the code is in the prompt
        setting_sources=[],  # ignore ~/.claude settings, CLAUDE.md and hooks: the same run on any machine
        env={"ENABLE_TOOL_SEARCH": "false"},  # no ToolSearch calls
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=settings.max_turns,  # safety cap (01 C16); a review needs only a few turns
        max_budget_usd=settings.max_budget_usd,  # cost guard per review call
        # No temperature or seed: ClaudeAgentOptions has none, so variation shows only by running again (C6).
    )


async def review(settings: Settings, system_prompt: str, files: list[dict[str, Any]]) -> list[dict] | None:
    """One review = one query() over all 5 listings. Returns the findings, or None on failure."""
    prompt = REVIEW_TASK + "\n\n".join(format_file(f) for f in files)
    findings = None
    try:
        async for message in query(prompt=prompt, options=build_review_options(settings, system_prompt)):
            if isinstance(message, ResultMessage) and message.subtype == "success" and message.structured_output:
                findings = message.structured_output["findings"]
            # No `break`: a few system events can still arrive after the ResultMessage.
    except ResultError:  # raised AFTER the error ResultMessage, e.g. error_max_structured_output_retries
        pass
    return findings


# ---------------------------------------------------------------- scoring against the answer key


def match(finding: dict, files: list[dict[str, Any]]) -> dict | None:
    """The spot a finding points at: same file, line within 2 of the spot's line (06 E2). Spots are 5+ lines apart."""
    text = {f["name"]: f["text"] for f in files}.get(Path(finding["file"]).name.lower())
    return next((s for s in PLANTED if text and s["file"] == Path(finding["file"]).name.lower()
                 and abs(finding["line"] - locate(text, s["contains"])) <= 2), None)


def is_false_positive(finding: dict, files: list[dict[str, Any]]) -> bool:
    spot = match(finding, files)
    return spot is None or spot["kind"] == "decoy"  # a decoy, or nothing planted there at all


def score_run(findings: list[dict], files: list[dict[str, Any]]) -> dict[str, Any]:
    """One run: false positives, and each spot's verdict (a real spot's reported severity or missed; a decoy's
    flagged or skipped)."""
    verdicts = {s["id"]: ("missed" if s["kind"] == "real" else "skipped") for s in PLANTED}
    fp_spots = []
    for finding in findings:
        spot = match(finding, files)
        if spot is None or spot["kind"] == "decoy":
            fp_spots.append(spot["id"] if spot else f"unmatched:{finding['file']}:{finding['line']}")
        if spot and verdicts[spot["id"]] in ("missed", "skipped"):  # the first matching finding decides
            verdicts[spot["id"]] = finding["severity"] if spot["kind"] == "real" else "flagged"
    return {"fp": len(fp_spots), "total": len(findings), "verdicts": verdicts, "fp_spots": fp_spots}


def is_right(spot: dict, verdict: str) -> bool:
    return verdict == spot["severity"] if spot["kind"] == "real" else verdict == "skipped"


def summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """One prompt's runs: false-positive rate, inconsistency (wrong verdicts), stable spots, severity accuracy."""
    total = sum(r["total"] for r in runs)
    wrong = sum(not is_right(s, r["verdicts"][s["id"]]) for r in runs for s in PLANTED)
    reported = [(s, r["verdicts"][s["id"]]) for r in runs for s in PLANTED
                if s["kind"] == "real" and r["verdicts"][s["id"]] != "missed"]
    return {
        "fp_rate": sum(r["fp"] for r in runs) / total if total else 0.0,
        "inconsistency": (wrong, len(PLANTED) * len(runs)),
        "stable": sum(len({r["verdicts"][s["id"]] for r in runs}) == 1 for s in PLANTED) if len(runs) > 1 else None,
        "severity_accuracy": sum(v == s["severity"] for s, v in reported) / len(reported) if reported else 0.0,
    }
