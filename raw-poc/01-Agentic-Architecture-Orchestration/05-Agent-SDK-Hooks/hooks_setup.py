"""
hooks_setup.py - Larkfield Supply: three order systems that disagree on formats (POC 1), three payment tools
(POC 2), the run state that hooks and handlers share, build_hook_options(), and run_agent() (01's, extended).

No handler checks a policy and no tool description mentions one: in POC 2 the hooks are the only enforcement.
"""

import json
from collections import Counter
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

from common import Settings

ORDER_TOOLS = ["mcp__orders__system_a", "mcp__orders__system_b", "mcp__orders__system_c"]
PAYMENT_TOOLS = ["mcp__payments__process_refund", "mcp__payments__aml_check", "mcp__payments__transfer_funds"]


@dataclass
class HookState:
    """One per run: the "current session" that the hooks and the handlers share (04 C7)."""

    calls: Counter = field(default_factory=Counter)  # handler runs per tool: a denied call never gets counted
    denials: dict[str, str] = field(default_factory=dict)  # tool_use_id -> the deny reason Claude received
    refunds: list[dict] = field(default_factory=list)
    escalations: list[dict] = field(default_factory=list)  # opened by the refund-limit hook (POC 2)
    transfers: list[dict] = field(default_factory=list)
    aml_results: dict[str, str] = field(default_factory=dict)  # account -> "pass"/"fail", written only by a hook


def text_result(text: str, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": is_error}


def response_text(tool_response: Any) -> str:
    """A tool result's text. Its shape depends on the tool (E3): a string, a list of {"type": "text", ...}
    blocks, or a dict that holds that list under "content"."""
    if isinstance(tool_response, dict):
        tool_response = tool_response.get("content", [])
    if isinstance(tool_response, list):
        return "".join(block.get("text", "") for block in tool_response if isinstance(block, dict))
    return str(tool_response or "")


# ---------------------------------------------------------------- POC 1: three order systems, three formats

CUSTOMER_SCHEMA = {"type": "object", "properties": {"customer_id": {"type": "string", "pattern": "^CUST-\\d{4}$"}},
                   "required": ["customer_id"]}
ORDERS = {  # customer CUST-3318 has one order in each system. Same keys everywhere; only the VALUE FORMATS differ
    "a": {"name": "A (the legacy warehouse system)",  # Unix seconds, numeric status codes
          "orders": [{"order_id": "LS-1042", "item": "Cedar desk organizer", "order_date": 1776686400, "status": 2}]},
    "b": {"name": "B (the web store)",  # ISO 8601 dates, status words
          "orders": [{"order_id": "LS-2087", "item": "Linen throw blanket", "order_date": "2026-04-28", "status": "delivered"}]},
    "c": {"name": "C (the partner marketplace)",  # DD/MM/YYYY dates, one-letter status codes
          "orders": [{"order_id": "LS-3150", "item": "Copper pour-over kettle", "order_date": "04/05/2026", "status": "P"}]},
}


def build_orders_server(state: HookState) -> Any:
    def order_system(system: str) -> Any:  # the description names the system but not its formats, like many legacy APIs
        @tool(f"system_{system}", f"Order system {ORDERS[system]['name']}: returns a customer's orders as JSON.",
              CUSTOMER_SCHEMA, annotations=ToolAnnotations(readOnlyHint=True))
        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            state.calls[f"system_{system}"] += 1
            orders = ORDERS[system]["orders"] if args.get("customer_id") == "CUST-3318" else []
            return text_result(json.dumps({"system": system.upper(), "orders": orders}))
        return handler

    return create_sdk_mcp_server(name="orders", version="1.0.0", tools=[order_system(s) for s in ORDERS])


# ---------------------------------------------------------------- POC 2: payments (no policy code in any handler)


def build_payments_server(state: HookState) -> Any:
    amount = {"type": "number", "exclusiveMinimum": 0}

    @tool("process_refund", "Refunds an amount to the customer for an order.",
          {"type": "object", "properties": {"order_id": {"type": "string", "pattern": "^LS-\\d{4}$"}, "amount": amount},
           "required": ["order_id", "amount"]})
    async def process_refund(args: dict[str, Any]) -> dict[str, Any]:
        state.calls["process_refund"] += 1  # reached only if no PreToolUse hook denied the call
        refund = {"id": f"RF-{len(state.refunds) + 1:04d}", "order_id": args["order_id"], "amount": float(args["amount"])}
        state.refunds.append(refund)
        return text_result(f"Refund {refund['id']} of ${refund['amount']:,.2f} for order {refund['order_id']} processed.")

    @tool("aml_check", "Screens a beneficiary account against anti-money-laundering (AML) watchlists and returns "
          "pass or fail.", {"type": "object", "properties": {"account_id": {"type": "string", "pattern": "^ACC-\\d{4}$"}},
                            "required": ["account_id"]},
          annotations=ToolAnnotations(readOnlyHint=True))
    async def aml_check(args: dict[str, Any]) -> dict[str, Any]:
        state.calls["aml_check"] += 1
        account = str(args.get("account_id", ""))
        if account == "ACC-5521":
            return text_result(json.dumps({"account_id": account, "result": "pass"}))
        if account == "ACC-6620":  # a fail is a NORMAL result: an error result would fire PostToolUseFailure instead
            return text_result(json.dumps({"account_id": account, "result": "fail",
                                           "note": "Name matches a sanctions watchlist entry."}))
        return text_result(f"Unknown account '{account}'.", is_error=True)

    @tool("transfer_funds", "Sends money from the Larkfield Supply operating account to a beneficiary account.",
          {"type": "object", "properties": {"to_account": {"type": "string", "pattern": "^ACC-\\d{4}$"}, "amount": amount},
           "required": ["to_account", "amount"]})
    async def transfer_funds(args: dict[str, Any]) -> dict[str, Any]:
        state.calls["transfer_funds"] += 1
        transfer = {"id": f"TR-{len(state.transfers) + 1:04d}", "to_account": args["to_account"],
                    "amount": float(args["amount"])}
        state.transfers.append(transfer)
        return text_result(f"Transfer {transfer['id']} of ${transfer['amount']:,.2f} to {transfer['to_account']} sent.")

    return create_sdk_mcp_server(name="payments", version="1.0.0", tools=[process_refund, aml_check, transfer_funds])


# ---------------------------------------------------------------- options and the agent run

SYSTEM_PROMPTS = {  # no policy rules: in POC 2 the hooks enforce them
    "orders": ("You are an order-support assistant for Larkfield Supply, an online store. Customer orders live in "
               "three order systems, A, B and C. Use the tools to look orders up; never guess an order, a date or a status."),
    "payments": ("You are a payments assistant for Larkfield Supply. Use process_refund to refund an order, aml_check to "
                 "screen a beneficiary account, and transfer_funds to send money. Never guess an ID or an amount."),
}


def build_hook_options(settings: Settings, state: HookState, server: str, hooks: dict | None = None) -> ClaudeAgentOptions:
    build_server, tool_names = {"orders": (build_orders_server, ORDER_TOOLS),
                                "payments": (build_payments_server, PAYMENT_TOOLS)}[server]
    return ClaudeAgentOptions(
        model=settings.model_id,
        system_prompt=SYSTEM_PROMPTS[server],  # without one, the SDK sends an empty system prompt
        mcp_servers={server: build_server(state)},  # fresh tools bound to this run's state
        tools=[],  # remove ALL built-in tools: Claude can use only ours
        allowed_tools=tool_names,  # pre-approve every tool, so only a hook can block one (E1)
        hooks=hooks,  # {"PreToolUse": [...], "PostToolUse": [...]}; None = no hooks (the baseline)
        setting_sources=[],  # ignore settings files and their shell hooks; our callback hooks still run
        env={"ENABLE_TOOL_SEARCH": "false"},  # send all tool schemas up front: no ToolSearch calls
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=settings.max_turns,  # safety cap (01 C16); a normal run needs far fewer
        max_budget_usd=settings.max_budget_usd,  # cost guard per run
    )


async def run_agent(user_prompt: str, options: ClaudeAgentOptions) -> dict[str, Any]:
    """01's run_agent(), extended with options= and tool_results: what Claude actually received for each call.

    Returns {"answer", "subtype", "stop_reason", "num_turns", "tool_calls", "tool_results"}; each tool_results item
    is {"tool_use_id", "name", "input", "is_error", "text"}.
    """
    run: dict[str, Any] = {"answer": None, "subtype": None, "stop_reason": None, "num_turns": 0,
                           "tool_calls": [], "tool_results": []}
    uses: dict[str, tuple[str, dict]] = {}  # tool_use id -> (name, input)
    try:
        async for message in query(prompt=user_prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
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
    except ResultError:  # raised AFTER the error ResultMessage, e.g. error_max_turns, error_max_budget_usd
        pass
    return run
