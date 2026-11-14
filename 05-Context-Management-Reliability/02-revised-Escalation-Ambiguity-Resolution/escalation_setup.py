"""
escalation_setup.py - Lumen Home's customers and orders, match_customer(), the 3 support tools, the two system
prompts (naive, and criteria + examples), build_escalation_options() and run_agent() (01's, as extended in
05-Agent-SDK-Hooks and 02-Tool-Design-MCP-Integration/01-Tool-Interface-Design: first_response_tools).

Escalation is decided by the model, so it is calibrated in the prompt. Disambiguation is decided in code: the
find_customer handler returns no account data when a name matches several customers.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultError,
    ResultMessage,
    ToolAnnotations,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_sdk_mcp_server,
    query,
    tool,
)

from common import Settings, log, log_model_io

# Claude sees each tool under its full name: mcp__<server name>__<tool name>
FIND_CUSTOMER = "mcp__lumen__find_customer"
LOOKUP_ORDER = "mcp__lumen__lookup_order"
ESCALATE = "mcp__lumen__escalate_to_human"
LUMEN_TOOLS = [FIND_CUSTOMER, LOOKUP_ORDER, ESCALATE]
TRIGGERS = ["explicit_human_request", "policy_gap", "no_progress"]  # the 3 valid triggers (C1); the enum adds "other"

CUSTOMERS = [  # two customers share the name Alex Morgan. last_order_date is read only by poc1_heuristics.py
    {"customer_id": "CUST-1042", "name": "Dana Reyes", "email": "dana.reyes@example.com", "phone": "+1-503-555-0142",
     "postcode": "97205", "city": "Portland, OR", "order_ids": ["ORD-7731", "ORD-7745"],
     "last_order_date": "2026-11-08"},
    {"customer_id": "CUST-2077", "name": "Sam Okafor", "email": "sam.okafor@example.com", "phone": "+1-206-555-0177",
     "postcode": "98101", "city": "Seattle, WA", "order_ids": ["ORD-8810", "ORD-8952"],
     "last_order_date": "2026-11-11"},
    {"customer_id": "CUST-3101", "name": "Alex Morgan", "email": "alex.morgan@example.com", "phone": "+1-503-555-0118",
     "postcode": "97214", "city": "Portland, OR", "order_ids": ["ORD-9310"], "last_order_date": "2026-11-06"},
    {"customer_id": "CUST-3388", "name": "Alex Morgan", "email": "a.morgan@example.net", "phone": "+1-206-555-0164",
     "postcode": "98103", "city": "Seattle, WA", "order_ids": ["ORD-6721", "ORD-7368", "ORD-8462"],
     "last_order_date": "2026-09-19"},
]
ORDERS = {
    "ORD-7731": {"order_id": "ORD-7731", "customer_id": "CUST-1042", "item": "Aurora desk lamp", "total": 49.99,
                 "status": "delivered on 2026-10-03", "tracking": "LH-55120931", "final_sale": False},
    "ORD-7745": {"order_id": "ORD-7745", "customer_id": "CUST-1042", "item": "Nimbus wireless headphones",
                 "total": 129.00, "status": "shipped; delayed in transit, new delivery estimate 2026-11-16",
                 "tracking": "LH-55120988", "final_sale": False},
    "ORD-8810": {"order_id": "ORD-8810", "customer_id": "CUST-2077", "item": "Kestrel water bottle", "total": 24.50,
                 "status": "processing", "tracking": None, "final_sale": False},
    "ORD-8952": {"order_id": "ORD-8952", "customer_id": "CUST-2077", "item": "Linden throw pillow (clearance)",
                 "total": 18.00, "status": "delivered on 2026-11-02", "tracking": "LH-55121407", "final_sale": True},
}


def match_customer(name: str, email: str | None = None, phone: str | None = None, order_number: str | None = None,
                   postcode: str | None = None) -> dict:
    """Exact filters only: it never sorts, ranks or picks one of several matches (C11)."""
    candidates = [c for c in CUSTOMERS if c["name"].lower() == name.strip().lower()]
    if email:  # any ONE identifier the customer chooses is enough to narrow the match (C13)
        candidates = [c for c in candidates if c["email"].lower() == email.strip().lower()]
    if phone:  # compare the last 10 digits: "+1-503-555-0118" and "(503) 555-0118" are the same phone
        candidates = [c for c in candidates if re.sub(r"\D", "", c["phone"])[-10:] == re.sub(r"\D", "", phone)[-10:]]
    if order_number:
        candidates = [c for c in candidates if order_number.strip().upper() in c["order_ids"]]
    if postcode:
        candidates = [c for c in candidates if c["postcode"] == postcode.strip()]

    if len(candidates) == 1:
        return {"status": "matched", "customer": candidates[0]}
    if not candidates:
        return {"status": "not_found", "message": "No customer matches those details. Ask the customer to check them."}
    # 2 or more: no account data at all, so no prompt and no heuristic can pick one (C12)
    return {"status": "ambiguous", "match_count": len(candidates),
            "ask_for": ["email", "phone number", "order number", "postcode"],
            "message": f"{len(candidates)} customers match this name, so no account data is returned. Don't pick one: "
                       "ask the customer for one of these identifiers and let them choose which: email, phone number, "
                       "order number or postcode."}


@dataclass
class EscalationSession:
    """One per run: every handler reads and writes it, so each decision can be read back afterwards."""

    events: list[tuple] = field(default_factory=list)  # (tool, key, outcome) per handler call, in call order
    disclosed: list[str] = field(default_factory=list)  # customer IDs whose record find_customer returned
    escalations: list[dict] = field(default_factory=list)


def text_result(text: str, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": is_error}


def build_escalation_server(session: EscalationSession) -> Any:
    """The 3 tools are defined in here, so every handler shares this run's session."""
    optional = {"type": "string"}

    @tool("find_customer", "Finds one Lumen Home customer account by full name, narrowed by any identifiers the "
          "customer gave: email, phone, order number or postcode. Returns the account only when exactly one customer "
          "matches. When several customers share the name, it returns no account data and lists the identifiers to "
          "ask for.",
          {"type": "object", "properties": {"name": {"type": "string"}, "email": optional, "phone": optional,
                                            "order_number": optional, "postcode": optional}, "required": ["name"]},
          annotations=ToolAnnotations(readOnlyHint=True))
    async def find_customer(args: dict[str, Any]) -> dict[str, Any]:
        result = match_customer(str(args.get("name", "")), args.get("email"), args.get("phone"),
                                args.get("order_number"), args.get("postcode"))
        session.events.append(("find_customer", args.get("name"), result["status"]))
        if result["status"] == "matched":
            session.disclosed.append(result["customer"]["customer_id"])
        # "ambiguous" is a normal result, not is_error: the search worked, and its answer is "more than one"
        return text_result(json.dumps(result))

    @tool("lookup_order", "Looks up one Lumen Home order by its order ID (ORD- plus 4 digits) and returns its item, "
          "total, status, tracking number and final-sale flag.",
          {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
          annotations=ToolAnnotations(readOnlyHint=True))
    async def lookup_order(args: dict[str, Any]) -> dict[str, Any]:
        order_id = str(args.get("order_id", "")).strip().upper()
        if order_id in ORDERS:
            session.events.append(("lookup_order", order_id, "found"))
            return text_result(json.dumps(ORDERS[order_id]))
        session.events.append(("lookup_order", order_id, "not_found"))
        return text_result(f"No order matches '{args.get('order_id')}'. Ask the customer to check the order ID.",
                           is_error=True)

    @tool("escalate_to_human", "Hands this conversation to a human support agent. Pass the trigger that applies and "
          "a one-sentence reason the human can act on.",
          {"type": "object", "properties": {"trigger": {"type": "string", "enum": TRIGGERS + ["other"]},
                                            "reason": {"type": "string"}}, "required": ["trigger", "reason"]})
    async def escalate_to_human(args: dict[str, Any]) -> dict[str, Any]:
        escalation = {"id": f"ESC-{len(session.escalations) + 1:04d}", "trigger": args.get("trigger"),
                      "reason": args.get("reason")}
        session.escalations.append(escalation)
        session.events.append(("escalate_to_human", escalation["trigger"], escalation["id"]))
        return text_result(f"Escalation {escalation['id']} queued: a human agent will take over this conversation.")

    return create_sdk_mcp_server(name="lumen", version="1.0.0", tools=[find_customer, lookup_order, escalate_to_human])


# ---------------------------------------------------------------- the system prompts

BASE_PROMPT = ("You are a customer support agent for Lumen Home, an online store. Use the tools to look up "
               "customers and orders, and never guess an ID, an amount or a policy rule.")
POLICY = ("LUMEN HOME POLICY\n"
          "P1 Returns: unused items can be returned within 30 days of delivery for a full refund.\n"
          "P2 Damaged items: an item that arrives damaged is replaced or refunded, as the customer prefers.\n"
          "P3 Final sale: items marked final sale can't be returned or refunded.\n"
          "P4 Price drops: if an item's price drops on the Lumen Home website after purchase, we refund the "
          "difference on request.")

# The "before": the two anti-patterns written as the escalation rule (C3)
NAIVE_RULE = ("Call escalate_to_human when the customer is upset or angry, or when you aren't confident you can "
              "resolve the request yourself. Otherwise, resolve it.")

CRITERIA = (  # three triggers, each with a description and an action (C1, C4), then the two anti-patterns (C3)
    "WHEN TO ESCALATE. Call escalate_to_human only for one of these three triggers:\n"
    "1. Explicit human request. Description: the customer asks to be handed to a human instead of you, in any "
    "words. Action: escalate at once with trigger explicit_human_request, before any lookup or troubleshooting; "
    "never offer to try first.\n"
    "2. Policy exception or gap. Description: the customer asks for something the policy doesn't address, so any "
    "answer would be a new policy decision. Action: escalate with trigger policy_gap; never invent a policy. A "
    "policy violation is different: when a policy rule explicitly says no, give that documented answer yourself "
    "and don't escalate.\n"
    "3. Inability to make progress. Description: your tools keep failing or return nothing useful, so you can't "
    "complete the request. Action: escalate with trigger no_progress.\n"
    "NEVER escalate for these reasons:\n"
    "- Sentiment: frustration, anger or rude words are not a trigger. Acknowledge the feeling and resolve a simple "
    "issue directly.\n"
    "- Your own confidence: feeling unsure is not a trigger. Use your tools, ask the customer, or apply the "
    "triggers above.")

IDENTITY_RULE = ("WHEN A NAME MATCHES SEVERAL CUSTOMERS: never pick one, by recency, activity, location or "
                 "anything else, and never guess an identifier. Ask the customer for one identifier and let them "
                 "choose which: email, phone number, order number or postcode.")  # (C11, C13)

EXAMPLES = [  # one decision each, with the reasoning that leads to it (C6, C8). Their orders aren't in ORDERS
    {"shows": "explicit human request -> escalate at once",
     "customer": "My order ORD-6120 is late again. Could you connect me with one of your staff, please?",
     "reasoning": "The customer asks for a member of staff: an explicit human request (trigger 1). That rule has no "
                  "exceptions, so I escalate now, before looking up ORD-6120, even though I could check it myself.",
     "action": "escalate_to_human(trigger=\"explicit_human_request\", reason=\"Customer asked for a staff member "
               "about late order ORD-6120.\"), then the reply \"Of course. I've passed you to a member of our team, "
               "who will take it from here.\""},
    {"shows": "frustrated customer, simple issue -> resolve",
     "customer": "This is ridiculous. I've waited a whole week and order ORD-6044 STILL says processing. Where is it?!",
     "reasoning": "The customer is frustrated, but frustration is not a trigger, and they didn't ask for a person. "
                  "A status question is simple: lookup_order answers it. So I acknowledge the frustration and "
                  "resolve it directly.",
     "action": "lookup_order(order_id=\"ORD-6044\"), which returns \"shipped today, tracking LH-55119920, arriving "
               "Friday\", then the reply \"I'm sorry about the wait: a week with no update is frustrating. Good news: "
               "ORD-6044 shipped today with tracking LH-55119920 and should arrive on Friday.\""},  # (C9)
    {"shows": "policy gap -> escalate",
     "customer": "I'm travelling for three weeks. Could you hold order ORD-6077 at your warehouse and ship it when "
                 "I'm back?",
     "reasoning": "The policy covers returns, damaged items, final sale and price drops on our website. It says "
                  "nothing about holding an order, so this is a policy gap (trigger 2), not a violation. Any answer I "
                  "gave would be new policy, so a human decides.",
     "action": "escalate_to_human(trigger=\"policy_gap\", reason=\"Customer asks us to hold ORD-6077 for three weeks; "
               "the policy doesn't cover holding orders.\"), then the reply \"That's a fair request our policy "
               "doesn't cover, so I've passed it to a colleague who can approve it. They'll get back to you.\""},
]


def examples_block() -> str:
    return "EXAMPLES OF THE DECISION\n" + "\n".join(
        f"<example><customer>{e['customer']}</customer><reasoning>{e['reasoning']}</reasoning>"
        f"<action>{e['action']}</action></example>" for e in EXAMPLES)


NAIVE_PROMPT = "\n\n".join([BASE_PROMPT, POLICY, NAIVE_RULE])  # the "before" (C2)
ESCALATION_PROMPT = "\n\n".join([BASE_PROMPT, POLICY, CRITERIA, IDENTITY_RULE, examples_block()])  # the "after"


def build_escalation_options(settings: Settings, session: EscalationSession,
                             system_prompt: str = ESCALATION_PROMPT) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=settings.model_id,
        system_prompt=system_prompt,  # NAIVE_PROMPT or ESCALATION_PROMPT: the only thing the A/B changes (C2)
        mcp_servers={"lumen": build_escalation_server(session)},  # fresh tools bound to this run's session
        tools=[],  # remove ALL built-in tools: Claude can use only ours
        allowed_tools=LUMEN_TOOLS,  # our tools run without asking for permission
        setting_sources=[],  # ignore ~/.claude settings, CLAUDE.md and hooks: the same run on any machine
        env={"ENABLE_TOOL_SEARCH": "false"},  # schemas up front: the first tool call is a decision, not a search (E2)
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=6,  # safety cap (01 C16); a scenario needs at most 3 turns
        max_budget_usd=settings.max_budget_usd,  # cost guard per run
    )


def response_text(tool_response: Any) -> str:
    """A tool result's text: a string, a list of {"type": "text", ...} blocks, or a dict holding that list."""
    if isinstance(tool_response, dict):
        tool_response = tool_response.get("content", [])
    if isinstance(tool_response, list):
        return "".join(block.get("text", "") for block in tool_response if isinstance(block, dict))
    return str(tool_response or "")


async def run_agent(user_prompt: str, options: ClaudeAgentOptions) -> dict[str, Any]:
    """01's run_agent(), extended with options=, tool_results and first_response_tools: the tools of Claude's FIRST
    tool-calling response, i.e. the messages that share the first tool call's message_id.

    Returns {"answer", "subtype", "stop_reason", "num_turns", "tool_calls", "tool_results", "first_response_tools"};
    each tool_results item is {"tool_use_id", "name", "input", "is_error", "text"}.
    """
    log.info("MODEL INPUT   prompt       %s", user_prompt)
    run: dict[str, Any] = {"answer": None, "subtype": None, "stop_reason": None, "num_turns": 0,
                           "tool_calls": [], "tool_results": [], "first_response_tools": []}
    uses: dict[str, tuple[str, dict]] = {}  # tool_use id -> (name, input)
    first_response_id = None  # message_id of the first response that called a tool
    try:
        async for message in query(prompt=user_prompt, options=options):
            log_model_io(message)
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        if not run["tool_calls"]:  # Claude's first tool call: remember which response it is in
                            first_response_id = message.message_id
                        if message.message_id == first_response_id:  # one response can call several tools
                            run["first_response_tools"].append(block.name)
                        run["tool_calls"].append(block.name)
                        uses[block.id] = (block.name, block.input)
            elif isinstance(message, UserMessage) and isinstance(message.content, list):
                for block in message.content:
                    if isinstance(block, ToolResultBlock):
                        name, tool_input = uses.get(block.tool_use_id, (None, None))
                        run["tool_results"].append({"tool_use_id": block.tool_use_id, "name": name, "input": tool_input,
                                                    "is_error": block.is_error, "text": response_text(block.content)})
            elif isinstance(message, ResultMessage):
                run.update(subtype=message.subtype, stop_reason=message.stop_reason, num_turns=message.num_turns)
                if message.subtype == "success" and message.stop_reason == "end_turn":
                    run["answer"] = message.result
            # No `break`: a few system events can still arrive after the ResultMessage.
    except ResultError as exc:  # raised AFTER the error ResultMessage (already logged)
        if exc.subtype == "error_max_turns":
            log.warning("Safety cap hit: max_turns=%s was used up before Claude finished. No answer.", options.max_turns)
        else:  # e.g. error_max_budget_usd, error_during_execution, an invalid API key
            log.error("The run failed: %s", exc)
    return run
