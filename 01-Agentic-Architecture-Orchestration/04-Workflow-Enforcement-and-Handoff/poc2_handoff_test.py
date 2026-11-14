"""
POC 2 - The structured handoff
===============================
When a request needs something the agent may not do (a billing dispute, an account change), it finishes what it
can and hands the rest to a human with escalate_to_human. The human sees ONLY that handoff, so:

  * its five fields are required by the tool's JSON Schema,
  * validate_handoff() runs inside the handler and rejects empty, placeholder or "see above" text,
  * one handoff covers every concern of the request.

The POC 1 gate stays on: the return refund still needs a verified customer. Besides model I/O, the log shows
per run the refunds paid and the handoffs stored, and which concerns each handoff covers.

Run:  python poc2_handoff_test.py     (2 short API runs)
"""

import asyncio
import sys

from claude_agent_sdk import ClaudeSDKError

from common import load_settings, log, setup_logging
from support_setup import SupportSession, build_support_options, run_support

DISPUTE_PROMPT = "Hi, this is Dana Reyes (dana.reyes@example.com). I was charged twice for order ORD-7745. Please sort it out."
MULTI_PROMPT = (
    "Hi, this is Dana Reyes (dana.reyes@example.com). Three things: 1) the Aurora desk lamp from order ORD-7731 "
    "arrived cracked, so I'm returning it and want my money back; 2) I was charged twice for order ORD-7745; "
    "3) please change my shipping address to 88 Larkspur Lane, Portland, OR 97211."
)

RUNS = [  # (prompt, concern -> the detail the handoff must mention)
    (DISPUTE_PROMPT, {"billing dispute": "ORD-7745"}),  # expect a handoff with refund_amount 129.0
    (MULTI_PROMPT, {"return": "ORD-7731", "billing dispute": "ORD-7745", "account update": "88 Larkspur Lane"}),
]


def concern_coverage(handoff: dict, concerns: dict[str, str]) -> dict[str, bool]:
    """Does the handoff's text name each concern's key detail? (C16)"""
    text = " ".join(str(handoff[name]) for name in ("conversation_summary", "root_cause", "recommended_action")).lower()
    return {concern: detail.lower() in text for concern, detail in concerns.items()}


async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc2_handoff_test")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    for prompt, concerns in RUNS:
        session = SupportSession()
        try:
            await run_support(prompt, build_support_options(settings, session, handoff=True))  # gate and rule on
        except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
            log.error("SDK error: %s", exc)
            return 1
        # Expected: the $49.99 return is refunded by the agent; the $129.00 duplicate charge goes to the human.
        log.info("Refunds paid: %s · handoffs stored: %d", [f"${r['amount']:.2f}" for r in session.refunds],
                 len(session.handoffs))
        for handoff in session.handoffs:
            log.info("Handoff covers %s · amount left for the human: $%.2f",
                     concern_coverage(handoff, concerns), handoff["refund_amount"])
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
