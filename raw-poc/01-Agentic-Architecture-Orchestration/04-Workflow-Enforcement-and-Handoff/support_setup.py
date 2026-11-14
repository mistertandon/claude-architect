"""
support_setup.py - the Lumen Home support agent: mock data, the session state, the four tools (with the refund
gate and the handoff validator inside their handlers), the prompts, build_support_options() and run_support().
"""

import json
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ResultError,
    ResultMessage,
    ToolAnnotations,
    create_sdk_mcp_server,
    query,
    tool,
)

from common import Settings

SERVER_NAME = "support"
SUPPORT_TOOLS = [f"mcp__{SERVER_NAME}__get_customer", f"mcp__{SERVER_NAME}__lookup_order",
                 f"mcp__{SERVER_NAME}__process_refund"]
ESCALATE = f"mcp__{SERVER_NAME}__escalate_to_human"

# ---------------------------------------------------------------- mock data (made up: Claude must look it up)

CUSTOMERS = {
    "CUST-1042": {"name": "Dana Reyes", "email": "dana.reyes@example.com", "verified": True},
    "CUST-2077": {"name": "Sam Okafor", "email": "sam.okafor@example.com", "verified": False},  # identity check pending
}
ORDERS = {
    "ORD-7731": {"customer_id": "CUST-1042", "item": "Aurora desk lamp", "total": 49.99, "charges": [49.99],
                 "status": "delivered, return eligible"},
    "ORD-7745": {"customer_id": "CUST-1042", "item": "Nimbus wireless headphones", "total": 129.00,
                 "charges": [129.00, 129.00], "charged_on": "2026-10-02", "status": "delivered"},
    "ORD-8810": {"customer_id": "CUST-2077", "item": "Kestrel water bottle", "total": 24.50, "charges": [24.50],
                 "status": "delivered"},
}


@dataclass
class SupportSession:
    """The current session's state. The SDK keeps no business state for you: one new session per run (C7)."""

    verified_ids: set[str] = field(default_factory=set)  # written ONLY by get_customer, for verified customers
    refunds: list[dict] = field(default_factory=list)
    handoffs: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------- the handoff: what the human receives (POC 2)

HANDOFF_FIELDS = ["customer_id", "conversation_summary", "root_cause", "refund_amount", "recommended_action"]
PLACEHOLDERS = ["tbd", "todo", "n/a", "unknown", "placeholder", "[", "<", "..."]
BACK_REFERENCES = ["see above", "as mentioned", "as discussed", "earlier in the conversation", "the transcript"]


def validate_handoff(handoff: dict[str, Any]) -> list[str]:
    """All five fields filled in and self-contained: the human never sees the conversation (C13-C15)."""
    errors = [f"missing {name}" for name in HANDOFF_FIELDS if name not in handoff]
    if handoff.get("customer_id") not in CUSTOMERS:
        errors.append(f"unknown customer_id {handoff.get('customer_id')!r}")
    amount = handoff.get("refund_amount")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
        errors.append("refund_amount must be a number >= 0")
    for name in ("conversation_summary", "root_cause", "recommended_action"):
        text = str(handoff.get(name, "")).strip().lower()
        found = [token for token in PLACEHOLDERS + BACK_REFERENCES if token in text]
        if not text:
            errors.append(f"{name} is empty")
        elif found:
            errors.append(f"{name} contains {found}: write it for a reader who never saw the conversation")
    return errors


# ---------------------------------------------------------------- the tools, bound to one session


def build_support_server(session: SupportSession, gate: bool = True, handoff: bool = False) -> Any:
    """Define the tools inside this function, so every handler reads and writes the same session."""

    @tool(
        "get_customer",
        "Look up a customer by full name or email address. Returns their customer ID and whether their identity "
        "is verified.",
        {"type": "object",
         "properties": {"name_or_email": {"type": "string", "description": "the customer's full name or email address"}},
         "required": ["name_or_email"]},
        annotations=ToolAnnotations(readOnlyHint=True),  # reads only: the SDK may run lookups in parallel (C18)
    )
    async def get_customer(args: dict[str, Any]) -> dict[str, Any]:
        name_or_email = str(args.get("name_or_email", ""))
        for customer_id, customer in CUSTOMERS.items():
            if name_or_email.strip().lower() in (customer["name"].lower(), customer["email"]):
                if customer["verified"]:  # the state the gate trusts: only what get_customer returned (C7)
                    session.verified_ids.add(customer_id)
                text = json.dumps({"customer_id": customer_id, "name": customer["name"], "verified": customer["verified"]})
                return {"content": [{"type": "text", "text": text}]}
        message = f"No customer matches '{name_or_email}'. Ask for the full name or email address."
        return {"content": [{"type": "text", "text": message}], "is_error": True}

    @tool(
        "lookup_order",
        "Look up an order by its ID. Returns the customer, item, total, every charge and the status.",
        {"type": "object", "properties": {"order_id": {"type": "string", "pattern": "^ORD-\\d{4}$"}},
         "required": ["order_id"]},
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    async def lookup_order(args: dict[str, Any]) -> dict[str, Any]:  # reads only, so it has no prerequisite
        order_id = str(args.get("order_id", ""))
        if order_id not in ORDERS:
            return {"content": [{"type": "text", "text": f"No order {order_id}."}], "is_error": True}
        return {"content": [{"type": "text", "text": json.dumps({"order_id": order_id, **ORDERS[order_id]})}]}

    # process_refund MOVES MONEY: its prerequisite (a customer verified by get_customer in this session) is
    # enforced here, in code, where neither the prompt nor Claude's choices can get around it (C3).
    @tool(
        "process_refund",
        "Refund an amount to a customer for a returned item. Requires a customer verified by get_customer in "
        "this session.",
        {"type": "object",
         "properties": {"customer_id": {"type": "string", "pattern": "^CUST-\\d{4}$"},
                        "amount": {"type": "number", "exclusiveMinimum": 0}},
         "required": ["customer_id", "amount"]},
    )
    async def process_refund(args: dict[str, Any]) -> dict[str, Any]:
        customer_id = str(args.get("customer_id", ""))
        try:
            amount = float(args.get("amount", 0))
        except (TypeError, ValueError):
            return {"content": [{"type": "text", "text": "amount must be a number."}], "is_error": True}
        verified = customer_id in session.verified_ids  # never what the user or Claude claims
        if gate and not verified:  # THE GATE: checked before anything else (C4, C8)
            message = (f"BLOCKED: refund not processed. Customer {customer_id} has not been verified in this "
                       "session. Call get_customer first, then retry.")  # names the missing step (C11)
            return {"content": [{"type": "text", "text": message}], "is_error": True}
        refund_id = f"RF-{len(session.refunds) + 1:04d}"
        session.refunds.append({"id": refund_id, "customer_id": customer_id, "amount": amount, "verified": verified})
        return {"content": [{"type": "text", "text": f"Refund of ${amount:.2f} processed for {customer_id}. "
                                                     f"Refund ID {refund_id}."}]}

    @tool(
        "escalate_to_human",
        "Hand the case to a human agent. Call it once, when a request needs an account change or a billing-dispute "
        "decision. The human sees ONLY this handoff: in conversation_summary, number every concern the customer "
        "raised and give each one's status (resolved, or needs a human).",
        {"type": "object",
         "properties": {
             "customer_id": {"type": "string"},
             "conversation_summary": {"type": "string"},
             "root_cause": {"type": "string"},
             "refund_amount": {"type": "number", "minimum": 0, "description": "the amount in USD that the human "
                               "must still decide on, not refunds you already processed"},
             "recommended_action": {"type": "string"}},
         "required": HANDOFF_FIELDS},
    )
    async def escalate_to_human(args: dict[str, Any]) -> dict[str, Any]:
        errors = validate_handoff(args)  # in the handler: an incomplete handoff can't reach the human (C15)
        if errors:
            return {"content": [{"type": "text", "text": f"Handoff rejected: {'; '.join(errors)}. Fix and call "
                                                         "escalate_to_human again."}], "is_error": True}
        session.handoffs.append(dict(args))
        return {"content": [{"type": "text", "text": f"Handoff HO-{len(session.handoffs):04d} queued for a human agent."}]}

    tools = [get_customer, lookup_order, process_refund] + ([escalate_to_human] if handoff else [])
    return create_sdk_mcp_server(name=SERVER_NAME, version="1.0.0", tools=tools)


# ---------------------------------------------------------------- the agent

SYSTEM_PROMPT = ("You are a customer support agent for Lumen Home, an online store. Use the tools to look up "
                 "customers and orders, and never guess an ID or an amount. You may refund a returned item, "
                 "up to its order total, with process_refund.")
VERIFY_RULE = " Always call get_customer and confirm the customer is verified before you call process_refund."
HANDOFF_RULE = (" You cannot change account details or resolve billing disputes. When a request needs either, "
                "finish everything you can, then call escalate_to_human once with a summary that covers every "
                "concern the customer raised. The human agent sees only that summary, never this conversation.")


def build_support_options(
    settings: Settings, session: SupportSession, gate: bool = True, verify_rule: bool = True, handoff: bool = False
) -> ClaudeAgentOptions:
    """gate: the check in process_refund's code. verify_rule: the same rule as a prompt instruction."""
    return ClaudeAgentOptions(
        model=settings.model_id,
        system_prompt=SYSTEM_PROMPT + (VERIFY_RULE if verify_rule else "") + (HANDOFF_RULE if handoff else ""),
        mcp_servers={SERVER_NAME: build_support_server(session, gate, handoff)},  # tools bound to THIS session (C7)
        tools=[],  # remove ALL built-in tools: Claude can use only ours
        allowed_tools=SUPPORT_TOOLS + ([ESCALATE] if handoff else []),  # our tools run without asking for permission
        setting_sources=[],  # ignore ~/.claude settings, CLAUDE.md and hooks: the same run on any machine
        env={"ENABLE_TOOL_SEARCH": "false"},  # send all tool schemas up front: no ToolSearch calls
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=settings.max_turns,  # safety cap (01 C16); a normal run needs far fewer
        max_budget_usd=settings.max_budget_usd,  # cost guard per run
    )


async def run_support(prompt: str, options: ClaudeAgentOptions) -> str | None:
    """Stream one customer request through the agent. Returns the final answer, or None if the loop didn't finish."""
    answer = None
    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage) and message.subtype == "success" and message.stop_reason == "end_turn":
                answer = message.result
            # No `break`: a few system events can still arrive after the ResultMessage.
    except ResultError:  # raised AFTER the error ResultMessage, e.g. error_max_turns or the cost guard
        pass
    return answer
