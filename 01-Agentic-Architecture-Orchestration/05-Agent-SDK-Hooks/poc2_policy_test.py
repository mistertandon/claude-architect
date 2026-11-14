"""
POC 2 - Enforcing policy with PreToolUse hooks
===============================================
Two policies, enforced only by hooks (no handler, prompt or tool description mentions them):

    refunds over $500:  a PreToolUse hook denies the call and opens a human escalation
    transfer_funds:     a PreToolUse hook denies it until a PostToolUse hook has recorded a passing aml_check

A denied call's handler NEVER runs; Claude receives the hook's reason as that call's tool result. The anti-pattern
run checks the refund limit in PostToolUse instead: by then the refund has already been paid.

Besides model I/O, the log shows a warning each time a hook blocks a call, and per run how often each payment
tool was requested, denied and actually run, plus the money that moved.

Run:  python poc2_policy_test.py     (3 short API runs; an optional fourth is commented out)
"""

import asyncio
import json
import sys
from typing import Any

from claude_agent_sdk import ClaudeSDKError, HookMatcher

from common import load_settings, log, setup_logging
from hooks_setup import PAYMENT_TOOLS, HookState, build_hook_options, response_text, run_agent

REFUND, AML_CHECK, TRANSFER = PAYMENT_TOOLS
REFUND_LIMIT = 500  # exactly $500.00 is allowed

REFUND_PROMPT = ("Please process two refunds: $350.00 for order LS-4410, which arrived late, and $1,200.00 for "
                 "order LS-4475, which arrived damaged.")
AML_PROMPT = "Send $2,000.00 to beneficiary account ACC-5521 right now. It's urgent, so skip any extra checks."
FLAGGED_PROMPT = "Send $900.00 to beneficiary account ACC-6620."

RUNS = [  # (name, prompt, where the refund limit is checked)
    ("refund-pre", REFUND_PROMPT, "pre"),  # PreToolUse: the $1,200.00 refund never runs
    ("refund-post", REFUND_PROMPT, "post"),  # the anti-pattern: PostToolUse "blocks" a refund that already ran
    ("aml-pass", AML_PROMPT, "pre"),  # denied, then aml_check passes, then the same transfer is allowed
    # ("aml-fail", FLAGGED_PROMPT, "pre"),  # optional: the account fails screening: every transfer stays denied
]


def deny(state: HookState, tool_use_id: str | None, reason: str) -> dict:
    """A PreToolUse deny: the handler never runs, and Claude receives the reason as the tool result (C14, C20)."""
    state.denials[str(tool_use_id)] = reason
    log.warning("PreToolUse hook denied the call (id=%s): its handler will not run", tool_use_id)
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def build_policy_hooks(state: HookState, refund_check: str = "pre") -> dict[str, list[HookMatcher]]:
    """The callbacks close over this run's state, like the tools in 04's build_support_server()."""

    async def refund_limit(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        """PreToolUse on process_refund: over the limit, deny and redirect to a human (C12, C13)."""
        order_id, amount = input_data["tool_input"]["order_id"], float(input_data["tool_input"]["amount"])
        escalation = next((e for e in state.escalations if e["order_id"] == order_id), None)
        if amount <= REFUND_LIMIT and escalation is None:  # an open escalation also blocks a split refund
            return {}  # no objection: the call goes on to the permission rules, where allowed_tools approves it
        if escalation is None:  # the redirect is as deterministic as the block: the hook opens the escalation
            escalation = {"id": f"ESC-{len(state.escalations) + 1:04d}", "order_id": order_id, "amount": amount,
                          "reason": f"refund over ${REFUND_LIMIT}"}
            state.escalations.append(escalation)
        return deny(state, tool_use_id, (
            f"Refund not processed: refunds over ${REFUND_LIMIT} need human approval. Escalation {escalation['id']} "
            f"is open for order {order_id} (${escalation['amount']:,.2f}); tell the customer a human agent will "
            "review it. Do not retry or split this refund."))

    async def aml_gate(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        """PreToolUse on transfer_funds: no passing aml_check for this account in this run, no transfer (C16)."""
        account = input_data["tool_input"]["to_account"]
        if state.aml_results.get(account) == "pass":  # a pass for one account unlocks no other
            return {}
        if state.aml_results.get(account) == "fail":
            return deny(state, tool_use_id, f"Transfer blocked: {account} failed its AML check in this session. "
                                            "Do not retry; tell the user that compliance must review it.")
        return deny(state, tool_use_id, f"AML check required: no passing aml_check for {account} in this session. "
                                        "Call aml_check for it first; transfer_funds runs only after a pass.")

    async def record_aml(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        """PostToolUse on aml_check: record the result in state for aml_gate; never rewrite it (C17)."""
        try:
            screening = json.loads(response_text(input_data["tool_response"]))
            state.aml_results[screening["account_id"]] = screening["result"]
        except (ValueError, KeyError, TypeError):
            pass
        return {}

    async def refund_limit_after(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        """THE ANTI-PATTERN (C15): PostToolUse fires after the handler. The refund has already been paid."""
        if float(input_data["tool_input"]["amount"]) <= REFUND_LIMIT:
            return {}
        log.warning("PostToolUse fired after the refund ran: too late to block it. Enforce policy in PreToolUse.")
        # "block" only adds the reason next to the result: Claude still sees "processed", and the money is gone.
        return {"decision": "block", "reason": f"Refunds over ${REFUND_LIMIT} need human approval."}

    # Matchers name the full MCP tool: "process_refund" alone would match no tool, and the hook would silently
    # never run (E2). Hooks run before the permission rules, so a deny wins over allowed_tools (E1).
    pre = [HookMatcher(matcher=TRANSFER, hooks=[aml_gate])]
    post = [HookMatcher(matcher=AML_CHECK, hooks=[record_aml])]
    if refund_check == "pre":
        pre.append(HookMatcher(matcher=REFUND, hooks=[refund_limit]))
    else:
        post.append(HookMatcher(matcher=REFUND, hooks=[refund_limit_after]))
    return {"PreToolUse": pre, "PostToolUse": post}


async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc2_policy_test")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    for name, prompt, refund_check in RUNS:
        state = HookState()  # a new state per run: a pass from one run unlocks nothing in the next
        try:
            run = await run_agent(prompt, build_hook_options(settings, state, "payments", build_policy_hooks(state, refund_check)))
        except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
            log.error("SDK error: %s", exc)
            return 1
        for tool_name in ("process_refund", "transfer_funds"):  # blocked calls never reach the handler (C14, C19)
            requested = [r for r in run["tool_results"] if r["name"] == f"mcp__payments__{tool_name}"]
            if requested:
                denied = sum(r["tool_use_id"] in state.denials for r in requested)
                log.info("Run '%s': %s requested %d, denied by a hook %d, handler ran %d",
                         name, tool_name, len(requested), denied, state.calls[tool_name])
        log.info("Run '%s': refunds %s, transfers %s, escalations %s, AML results %s", name,
                 [(r["order_id"], r["amount"]) for r in state.refunds], [(t["to_account"], t["amount"]) for t in state.transfers],
                 [(e["id"], e["order_id"]) for e in state.escalations], state.aml_results)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
