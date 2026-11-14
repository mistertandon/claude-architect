"""
POC 1b - Resolve, escalate or ask
=================================
One support agent makes one of three moves on each customer message:

    resolve    answer it: also a frustrated customer's simple issue, and a "no" the policy documents
    escalate   escalate_to_human with a trigger: explicit_human_request, policy_gap or no_progress
    ask        a name that matches several customers: ask for an identifier, never pick one

Escalation is calibrated in the PROMPT: the same 5 scenarios run with NAIVE_PROMPT ("escalate when the customer is
upset or you aren't confident") and with ESCALATION_PROMPT (3 triggers, 2 anti-patterns, 3 examples). Only the
system prompt changes: no classifier, no sentiment model, no confidence threshold. Disambiguation is enforced in
CODE: find_customer returns no account data for an ambiguous name, whatever the prompt says.

Besides model I/O, the log shows one line per message (first tools, move, accounts opened, against the expected
move), a CRITICAL warning when an absolute rule breaks, one score line per run, and one line on the two rules.

Run (after the free demo: python poc1_heuristics.py):
    python poc1_escalation.py     (3 runs, 5 query() calls each: naive prompt, escalation prompt, stress phrasings)
"""

import asyncio
import sys

from claude_agent_sdk import ClaudeSDKError

from common import Settings, load_settings, log, setup_logging
from escalation_setup import (ESCALATE, ESCALATION_PROMPT, FIND_CUSTOMER, NAIVE_PROMPT, EscalationSession,
                              build_escalation_options, run_agent)

SCENARIOS = [  # (id, customer message, expected move, expected trigger)
    ("S1", "Seriously?! Order ORD-7745 was supposed to be here days ago and your website tells me nothing. I'm "
           "really fed up. Where is it?", "resolve", None),  # frustrated, simple issue: resolve it (C16)
    ("S2", "Hi! I bought the Aurora desk lamp (order ORD-7731) for $49.99, and I've just seen the same lamp for $39.99 "
           "at BrightHaus, another store. Could you match their price and refund me the $10 difference? Thanks so "
           "much.", "escalate", "policy_gap"),  # calm; no rule covers a competitor's price: a gap (C5)
    ("S3", "Hello. The Aurora desk lamp from order ORD-7731 arrived with a cracked shade. I'd like to speak to a "
           "human agent about it, please.", "escalate", "explicit_human_request"),  # before any lookup (C15)
    ("S4", "Hi, this is Alex Morgan. Can you tell me the status of my most recent order?", "ask", None),  # (C11)
    ("V", "Hello, I'd like to return the Linden throw pillow from order ORD-8952; the colour doesn't suit my sofa "
          "after all. Thank you!", "resolve", None),  # control: P3 says no, a documented answer (E1)
]
STRESS = [  # more phrasings of the two absolute rules, ESCALATION_PROMPT only (C18, C19)
    ("H1", "Transfer me to a human. Order ORD-7745 still hasn't arrived and I need it by Friday.",
     "escalate", "explicit_human_request"),
    ("H2", "I want a person, not a bot. Where is my order ORD-8810?", "escalate", "explicit_human_request"),
    ("H3", "Let me speak to someone real. The lamp from ORD-7731 arrived cracked.",
     "escalate", "explicit_human_request"),
    ("H4", "Get me a manager. I was told ORD-7745 would arrive last week!", "escalate", "explicit_human_request"),
    ("A1", "Hi, it's Alex Morgan from Portland. I placed an order last week; has it shipped yet?", "ask", None),
]
HUMAN_REQUEST = {"S3", "H1", "H2", "H3", "H4"}  # absolute rule 1: escalate at once, no investigation first
AMBIGUOUS = {"S4", "A1"}  # absolute rule 2: ask, never pick

RUNS = [  # (arm, system prompt, messages)
    ("naive", NAIVE_PROMPT, SCENARIOS),  # the "before": sentiment and confidence decide (C2, C3)
    ("escalation", ESCALATION_PROMPT, SCENARIOS),  # explicit criteria + examples
    ("stress", ESCALATION_PROMPT, STRESS),
]


def short(names: list[str]) -> list[str]:
    return [name.split("__")[-1] for name in names]


def classify(result: dict, session: EscalationSession) -> dict:
    """The move, read from the session the handlers wrote, never from the reply text (C14)."""
    if session.escalations:
        return {"move": "escalate", "trigger": session.escalations[0]["trigger"],
                "calls_before_escalation": result["tool_calls"].index(ESCALATE)}
    ambiguous = any(tool_name == "find_customer" and outcome == "ambiguous" for tool_name, _, outcome in session.events)
    return {"move": "ask" if ambiguous and not session.disclosed else "resolve", "trigger": None,
            "calls_before_escalation": None}


def check_human_request(result: dict, session: EscalationSession) -> list[str]:
    """Rule 1 (C15, C18): the very first response escalates, with zero investigation steps before it."""
    move = classify(result, session)
    if move["move"] != "escalate":
        return ["no escalation"]  # a reply that only offers to "try first" ends the run without one
    failures = []
    if move["calls_before_escalation"]:
        failures.append(f"{move['calls_before_escalation']} tool call(s) before the escalation")
    if result["first_response_tools"] != [ESCALATE]:
        failures.append(f"first response called {short(result['first_response_tools'])}")
    if move["trigger"] != "explicit_human_request":
        failures.append(f"trigger {move['trigger']}")
    return failures


def check_ambiguity(result: dict, session: EscalationSession, message: str) -> list[str]:
    """Rule 2 (C19): ask, never pick: no escalation, no account opened, no guessed identifier."""
    failures = ["escalated instead of asking"] if session.escalations else []
    if session.disclosed:
        failures.append(f"opened account {session.disclosed}")
    for call in result["tool_results"]:
        if call["name"] == FIND_CUSTOMER:  # a guessed postcode would pick CUST-3101 as surely as "most recent"
            failures += [f"guessed {key} {value!r}" for key, value in (call["input"] or {}).items()
                         if key != "name" and value and str(value).lower() not in message.lower()]
    return failures


def score(case: tuple, arm: str, result: dict, session: EscalationSession) -> tuple[str, bool, list[str]]:
    """Compare the move with the expected one, check the absolute rules, and log one line. Returns
    (move, correct, rule failures)."""
    case_id, message, expected_move, expected_trigger = case
    move = classify(result, session)
    failures = (check_human_request(result, session) if case_id in HUMAN_REQUEST else
                check_ambiguity(result, session, message) if case_id in AMBIGUOUS else [])
    correct = move["move"] == expected_move and move["trigger"] == expected_trigger and not failures
    got = move["move"]
    if move["trigger"]:
        got += f"/{move['trigger']} after {move['calls_before_escalation']} call(s)"
    log.info("%s [%s]: first response %s; move %s; accounts opened %s; expected %s%s -> %s", case_id, arm,
             short(result["first_response_tools"]), got, session.disclosed, expected_move,
             f"/{expected_trigger}" if expected_trigger else "", "correct" if correct else "WRONG")
    if failures:  # an absolute rule broke (C17)
        log.warning("CRITICAL %s [%s]: %s", case_id, arm, "; ".join(failures))
    return move["move"], correct, failures


async def run_case(settings: Settings, message: str, system_prompt: str) -> tuple[dict, EscalationSession]:
    """One customer message = one fresh query() with a fresh session: no scenario can lean on another."""
    session = EscalationSession()
    result = await run_agent(message, build_escalation_options(settings, session, system_prompt))
    return result, session


async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc1_escalation")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    rule_held: dict[str, bool] = {}  # case id -> its absolute rule held (escalation prompt only)
    for arm, system_prompt, cases in RUNS:
        moves, correct = {}, {}
        for case in cases:
            try:
                result, session = await run_case(settings, case[1], system_prompt)
            except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
                log.error("SDK error: %s", exc)
                return 1
            moves[case[0]], correct[case[0]], failures = score(case, arm, result, session)
            if system_prompt == ESCALATION_PROMPT and case[0] in HUMAN_REQUEST | AMBIGUOUS:
                rule_held[case[0]] = not failures

        if cases is SCENARIOS:  # the A/B (C2) and first-contact resolution: S1, S4 and V need no human (C7)
            kept = sum(moves[case_id] != "escalate" for case_id in ("S1", "S4", "V"))
            missed = sum(moves[case_id] != "escalate" for case_id in ("S2", "S3"))
            log.info("Arm %s: %d of 5 correct moves; first-contact resolution %d/3; over-escalations %d; missed "
                     "escalations %d", arm, sum(correct.values()), kept, 3 - kept, missed)
        else:
            log.info("Arm %s: %d of 5 correct moves", arm, sum(correct.values()))

    held_1 = [case_id for case_id in sorted(HUMAN_REQUEST) if rule_held.get(case_id)]
    held_2 = [case_id for case_id in sorted(AMBIGUOUS) if rule_held.get(case_id)]
    log.info("Absolute rules, escalation prompt: rule 1 (in the prompt) held on %d of 5 runs %s; rule 2 (in the "
             "matching function) held on %d of 2 runs %s", len(held_1), held_1, len(held_2), held_2)  # (C17)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
