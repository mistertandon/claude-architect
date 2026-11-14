"""
routing_setup.py - Lumen Home's two lookup tools in two description versions, the 10 test queries, the system
prompts, build_routing_options() and run_agent() (01's, extended with first_response_tools).

Both versions share the tool names, the input schema and the handlers: only the description text differs. With no
built-in tools and tool search off, Claude has two routing signals left: the descriptions and the system prompt.
"""

import json
import re
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
GET_CUSTOMER = "mcp__lumen__get_customer"
LOOKUP_ORDER = "mcp__lumen__lookup_order"

CUSTOMERS = [
    {"customer_id": "CUST-1042", "name": "Dana Reyes", "email": "dana.reyes@example.com", "phone": "+1-503-555-0142",
     "address_on_file": "12 Alder St, Portland, OR 97205", "tier": "gold", "account_status": "active",
     "order_ids": ["ORD-7731", "ORD-7745"]},
    {"customer_id": "CUST-2077", "name": "Sam Okafor", "email": "sam.okafor@example.com", "phone": "+1-206-555-0177",
     "address_on_file": "9 Birch Ave, Seattle, WA 98101", "tier": "silver", "account_status": "identity check pending",
     "order_ids": ["ORD-8810"]},
]
ORDERS = {  # ORD-7745 shipped to Dana's office: "shipped to" (order) and "address on file" (account) differ
    "ORD-7731": {"order_id": "ORD-7731", "customer_id": "CUST-1042", "customer_name": "Dana Reyes",
                 "item": "Aurora desk lamp", "total": 49.99, "status": "delivered on 2026-10-03",
                 "tracking": "LH-55120931", "shipped_to": "12 Alder St, Portland, OR 97205",
                 "paid_with": "Visa ending 4417"},
    "ORD-7745": {"order_id": "ORD-7745", "customer_id": "CUST-1042", "customer_name": "Dana Reyes",
                 "item": "Nimbus wireless headphones", "total": 129.00, "status": "shipped, in transit",
                 "tracking": "LH-55120988", "shipped_to": "410 Market St, Suite 200, Portland, OR 97204",
                 "paid_with": "Visa ending 4417"},
    "ORD-8810": {"order_id": "ORD-8810", "customer_id": "CUST-2077", "customer_name": "Sam Okafor",
                 "item": "Kestrel water bottle", "total": 24.50, "status": "processing", "tracking": None,
                 "shipped_to": "9 Birch Ave, Seattle, WA 98101", "paid_with": "Mastercard ending 0921"},
}

# One bare argument for both tools: no field description, no pattern. Formats can reach Claude only via descriptions
IDENTIFIER_SCHEMA = {"type": "object", "properties": {"identifier": {"type": "string"}}, "required": ["identifier"]}


def text_result(text: str, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": is_error}


def response_text(tool_response: Any) -> str:
    """A tool result's text: a string, a list of {"type": "text", ...} blocks, or a dict holding that list."""
    if isinstance(tool_response, dict):
        tool_response = tool_response.get("content", [])
    if isinstance(tool_response, list):
        return "".join(block.get("text", "") for block in tool_response if isinstance(block, dict))
    return str(tool_response or "")


# The two handlers never change. Neither error says which tool to use instead: the descriptions stay the only
# routing signal, and a misroute costs one wasted round trip (C2).
async def get_customer_handler(args: dict[str, Any]) -> dict[str, Any]:
    identifier = str(args.get("identifier", "")).strip()
    for customer in CUSTOMERS:  # a customer ID, an email or an exact full name, case-insensitive
        if identifier.lower() in (customer["customer_id"].lower(), customer["email"].lower(), customer["name"].lower()):
            return text_result(json.dumps(customer))
    return text_result(f"No customer matches '{identifier}'.", is_error=True)


async def lookup_order_handler(args: dict[str, Any]) -> dict[str, Any]:
    identifier = str(args.get("identifier", "")).strip().upper()
    if re.fullmatch(r"\d{4}", identifier):  # a bare 4-digit number is an order number
        identifier = f"ORD-{identifier}"
    if identifier in ORDERS:
        return text_result(json.dumps(ORDERS[identifier]))
    return text_result(f"No order matches '{args.get('identifier', '')}'.", is_error=True)


DESCRIPTIONS = {
    "minimal": {  # one vague sentence each: both seem to fit "Who placed order ORD-8810?" (C1)
        "get_customer": "Retrieves customer information.",
        "lookup_order": "Retrieves order details.",
    },
    "improved": {  # five sentences each: purpose, formats, examples, an edge case, a boundary (C7, C9)
        "get_customer": (
            "Looks up one Lumen Home customer account and returns its customer ID, name, email, phone, address on "
            "file, loyalty tier, account status and order IDs. "
            "Pass identifier as a customer ID (CUST- plus 4 digits, such as CUST-1042), an email address or a full "
            "name; a bare number is never a customer ID. "
            "Use it for questions about a customer or their account, such as \"Look up CUST-1042\", \"What's Dana "
            "Reyes' address on file?\" or \"Is sam.okafor@example.com a gold member?\", and call it first when the "
            "user names a customer but gives no order ID, because it returns the order IDs that lookup_order needs. "
            "If a name matches no customer exactly, it returns an error, so ask for the email or customer ID instead "
            "of guessing. "
            "Do NOT use it for order-specific details (items, order status, tracking, where an order shipped, how it "
            "was paid): use lookup_order for those."
        ),
        "lookup_order": (
            "Looks up one Lumen Home order and returns its item, total, order status, tracking number, shipping "
            "address, payment card and the customer who placed it (ID and name). "
            "Pass identifier as an order ID, ORD- plus 4 digits such as ORD-7745; a bare 4-digit number such as "
            "7745 is an order number, so pass it with the ORD- prefix. "
            "Use it for questions about one specific order, such as \"Has ORD-7745 shipped?\", \"Which card paid "
            "for ORD-7731?\" or \"Who placed order ORD-8810?\". "
            "If the user gives only a name, an email or a customer ID, call get_customer first to get their order IDs. "
            "Do NOT use it for account questions (contact details, address on file, loyalty tier, account status): "
            "use get_customer for those."
        ),
    },
}


def build_tools(version: str) -> list[Any]:
    """The same names, schema, annotations and handlers in every version: only the description is swapped in.
    tool(...) is the @tool decorator, applied here to the same two module-level handlers."""
    read_only = ToolAnnotations(readOnlyHint=True)  # no side effects
    get_customer = tool("get_customer", DESCRIPTIONS[version]["get_customer"], IDENTIFIER_SCHEMA, annotations=read_only)
    lookup_order = tool("lookup_order", DESCRIPTIONS[version]["lookup_order"], IDENTIFIER_SCHEMA, annotations=read_only)
    return [get_customer(get_customer_handler), lookup_order(lookup_order_handler)]


def build_routing_server(version: str) -> Any:
    return create_sdk_mcp_server(name="lumen", version="1.0.0", tools=build_tools(version))


def compare_versions() -> list[str]:
    """Every field that differs between the two versions of each tool (C11)."""
    return [f"{old.name}.{field}" for old, new in zip(build_tools("minimal"), build_tools("improved"))
            for field in ("name", "description", "input_schema", "annotations", "handler")
            if getattr(old, field) != getattr(new, field)]


def sentence_count(text: str) -> int:
    """Split after . ! or ? followed by whitespace, so a ? inside a quoted example doesn't end a sentence."""
    return len(re.split(r"(?<=[.!?])\s+", text.strip()))


QUERIES = [  # (query, the tool its FIRST response should call). Controls: 1, 2, 7, 10. The rest sit in the overlap
    ("Look up customer CUST-1042.", "get_customer"),
    ("Has order ORD-7745 shipped yet?", "lookup_order"),
    ("What's the shipping address on file for Dana Reyes?", "get_customer"),  # "shipping" sounds like an order
    ("Pull up 7745.", "lookup_order"),  # a bare number could be either
    ("Who placed order ORD-8810?", "lookup_order"),  # "who" sounds like customer information
    ("Which card was used to pay for ORD-7731?", "lookup_order"),  # a card sounds like account information
    ("Is Sam Okafor a gold-tier member?", "get_customer"),
    ("What did sam.okafor@example.com buy recently?", "get_customer"),  # "buy" sounds like an order, but no order ID
    ("Can you check the status for dana.reyes@example.com?", "get_customer"),  # "status" could be an order's
    ("What's the phone number on CUST-2077's account?", "get_customer"),
]

BASE_PROMPT = ("You are a support assistant for Lumen Home, an online store. Answer each question with the tools, "
               "and never guess an ID, a date or an amount.")
# POC 2: two sentences that tie a trigger word ("Always", "first") to get_customer's vocabulary (C12)
CONFLICT_PROMPT = BASE_PROMPT + (" Always check customer details before you answer any question."
                                 " For anything about a purchase, retrieve the customer information first.")
REWRITES = {  # each keyword-sensitive sentence -> a rewrite that keeps its intent and names a precise condition (C14)
    "Always check customer details before you answer any question.":
        "Before you change anything on an account, confirm who the customer is with get_customer; "
        "for questions about an order, lookup_order is enough.",
    "For anything about a purchase, retrieve the customer information first.":
        "For a question about one purchase, start with lookup_order and its order ID.",
}
FIXED_PROMPT = BASE_PROMPT + " " + " ".join(REWRITES.values())


def build_routing_options(settings: Settings, version: str, system_prompt: str = BASE_PROMPT) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=settings.model_id,
        system_prompt=system_prompt,  # POC 2 passes CONFLICT_PROMPT or FIXED_PROMPT
        mcp_servers={"lumen": build_routing_server(version)},  # only the descriptions differ between versions (C11)
        tools=[],  # no built-in tools: the two lumen tools are the only choice
        allowed_tools=[GET_CUSTOMER, LOOKUP_ORDER],  # our tools run without asking for permission
        setting_sources=[],  # ignore ~/.claude settings, CLAUDE.md and hooks: the same run on any machine
        env={"ENABLE_TOOL_SEARCH": "false"},  # full definitions up front: the first tool call is a routing choice (E2)
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=6,  # safety cap (01 C16); a misroute costs a turn or two
        max_budget_usd=settings.max_budget_usd,  # cost guard per query
    )


async def run_agent(user_prompt: str, options: ClaudeAgentOptions) -> dict[str, Any]:
    """01's run_agent(), as extended in 05-Agent-SDK-Hooks (options=, tool_results), plus first_response_tools: the
    tools of Claude's FIRST tool-calling response, i.e. the messages that share the first tool call's message_id.

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
