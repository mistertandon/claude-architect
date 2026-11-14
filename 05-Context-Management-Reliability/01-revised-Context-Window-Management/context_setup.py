"""
context_setup.py - Lumen Home's two order tools, the PostToolUse hook that records the case facts and trims each
order lookup, build_case_options() and run_agent() (01's, as extended in 05-Agent-SDK-Hooks).

lookup_order returns all 42 fields of an order, as an order API you can't change would. The hook sees each RAW
result before Claude does: it copies the transactional facts into CaseState.case_facts, then hands Claude only the
5 fields a refund needs.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
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
LOOKUP_ORDER = "mcp__lumen__lookup_order"
PROCESS_REFUND = "mcp__lumen__process_refund"
LUMEN_TOOLS = [LOOKUP_ORDER, PROCESS_REFUND]

FACT_FIELDS = {  # the fixed set of transactional field types (C2) and the fields that carry them
    "customer_id": ["customer_id"],
    "reference": ["order_id", "refund_id"],
    "amount": ["total_amount", "refund_amount"],
    "date": ["order_date", "refund_date"],
    "status": ["order_status", "refund_status"],
}
TASK_FIELDS = {  # what each task needs from an order lookup: the task decides what to keep (C7)
    "refund": ["order_id", "order_date", "total_amount", "return_eligible", "item_description"],
    "delivery": ["order_id", "carrier", "tracking_number", "shipped_date", "delivered_date"],
}

ORDER_8891 = {  # 42 fields, 1,341 characters as JSON. Total: $229.47 + $18.36 tax = $247.83
    "order_id": "ORD-8891", "order_date": "2026-03-03", "order_status": "delivered",
    "customer_id": "CUST-1042", "customer_name": "Dana Reyes", "customer_email": "dana.reyes@example.com",
    "loyalty_tier": "gold",
    "item_sku": "AUR-FL-BR-01", "item_description": "Aurora floor lamp, brushed brass", "item_quantity": 1,
    "item_unit_price": 229.47, "item_weight_kg": 6.8,
    "currency": "USD", "subtotal_amount": 229.47, "discount_amount": 0.0, "shipping_amount": 0.0,
    "tax_amount": 18.36, "total_amount": 247.83,
    "payment_method": "card", "card_brand": "Visa", "card_last4": "4417", "payment_status": "captured",
    "invoice_number": "INV-2026-03318",
    "shipping_address": "12 Alder St, Portland, OR 97205", "carrier": "Lumen Freight",
    "tracking_number": "LH-55129904", "shipped_date": "2026-03-04", "delivered_date": "2026-03-07",
    "warehouse_id": "WH-PDX-2", "fulfillment_status": "fulfilled",
    "return_eligible": True, "return_window_ends": "2026-04-06", "return_policy_code": "RP-30-STD",
    "sales_channel": "web", "loyalty_points": 229, "marketing_opt_in": False, "fraud_score": 0.02,
    "created_at": "2026-03-03T18:42:11Z", "updated_at": "2026-03-07T15:05:42Z",
    "delivery_instructions": "Leave at the side door.",
    "customer_note": "A birthday present, please pack it carefully!",
    "internal_note": "Customer called on 2026-03-05 about the delivery window.",
}
REFUND = {"refund_id": "RF-0001", "order_id": "ORD-8891", "refund_amount": 247.83, "refund_date": "2026-03-20",
          "refund_status": "processed", "refund_method": "Visa ending 4417",
          "message": "Refunds usually reach the card within 5-7 business days. A prepaid return label has been "
                     "emailed; please send the lamp back within 14 days."}


@dataclass
class CaseState:
    """One per conversation (05's HookState pattern): the hook and both tool handlers share it."""

    case_facts: dict = field(default_factory=dict)  # written only by the hook, never summarised (C3)
    sizes: list[tuple] = field(default_factory=list)  # (tool, raw_chars, sent_chars) per result the hook saw (C10)
    refunds: list[dict] = field(default_factory=list)


def text_result(text: str, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": is_error}


def response_text(tool_response: Any) -> str:
    """A tool result's text. Its shape depends on the tool (05 E3): a string, a list of {"type": "text", ...}
    blocks, or a dict that holds that list under "content"."""
    if isinstance(tool_response, dict):
        tool_response = tool_response.get("content", [])
    if isinstance(tool_response, list):
        return "".join(block.get("text", "") for block in tool_response if isinstance(block, dict))
    return str(tool_response or "")


def same_shape(tool_response: Any, text: str) -> Any:
    """updatedToolOutput must have the shape of the tool's output, and MCP output isn't validated (05 E3)."""
    if isinstance(tool_response, dict):
        return {**tool_response, "content": [{"type": "text", "text": text}]}
    if isinstance(tool_response, list):
        return [{"type": "text", "text": text}]
    return text


def extract_case_facts(result: dict) -> dict:
    """Copy the transactional facts of one tool result, unchanged (C1). It reads only the named FACT_FIELDS and
    never pattern-matches text, so the date inside internal_note can't become a fact."""
    return {name: result[name] for names in FACT_FIELDS.values() for name in names if name in result}


def trim_result(result: dict, task: str = "refund") -> dict:
    """Keep only the fields the current task needs (C7): 42 fields -> 5, 1,341 -> 157 characters (C10)."""
    return {name: result[name] for name in TASK_FIELDS[task]}


def build_case_hooks(state: CaseState) -> dict[str, list[HookMatcher]]:
    async def case_hook(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        """PostToolUse: the handler has returned the RAW result, and Claude hasn't seen it yet (C9)."""
        tool_name, tool_response = input_data["tool_name"], input_data["tool_response"]
        raw_text = response_text(tool_response)
        try:
            result = json.loads(raw_text)
        except ValueError:  # not a JSON record: leave the result alone
            return {}
        # 1) Facts first, from the RAW result: customer_id and order_status aren't refund fields, so the trim drops them
        state.case_facts.update(extract_case_facts(result))
        if tool_name != LOOKUP_ORDER:  # the refund record passes unchanged
            state.sizes.append((tool_name, len(raw_text), len(raw_text)))
            return {}
        sent_text = json.dumps(trim_result(result))  # 2) then the trim
        state.sizes.append((tool_name, len(raw_text), len(sent_text)))
        # The trimmed result replaces the raw one BEFORE it enters the conversation history (C9)
        return {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                       "updatedToolOutput": same_shape(tool_response, sent_text)}}

    # Exact tool names joined by | (05 E2): no regex characters, so no other tool can match
    return {"PostToolUse": [HookMatcher(matcher=f"{LOOKUP_ORDER}|{PROCESS_REFUND}", hooks=[case_hook])]}


def build_lumen_server(state: CaseState) -> Any:
    """Both tools are defined in here, so their handlers share this conversation's CaseState."""
    order_input = {"type": "object",
                   "properties": {"order_id": {"type": "string", "description": "The order ID, e.g. ORD-1234"}},
                   "required": ["order_id"]}

    @tool("lookup_order", "Looks up one Lumen Home order by its order ID (ORD- plus 4 digits) and returns the order "
          "record as JSON.", order_input, annotations=ToolAnnotations(readOnlyHint=True))
    async def lookup_order(args: dict[str, Any]) -> dict[str, Any]:
        if str(args.get("order_id", "")).strip().upper() != ORDER_8891["order_id"]:
            return text_result(f"No order matches '{args.get('order_id')}'. Ask the customer for the order ID "
                               "(ORD- plus 4 digits).", is_error=True)
        return text_result(json.dumps(ORDER_8891))  # all 42 fields: the hook, not the API, trims them

    @tool("process_refund", "Refunds the full total of a returnable Lumen Home order to the card that paid for it, "
          "and returns the refund record as JSON.", order_input)
    async def process_refund(args: dict[str, Any]) -> dict[str, Any]:
        order_id = str(args.get("order_id", "")).strip().upper()
        if order_id != ORDER_8891["order_id"] or not ORDER_8891["return_eligible"]:
            return text_result(f"No order matches '{args.get('order_id')}'. Look the order up first.", is_error=True)
        done = next((refund for refund in state.refunds if refund["order_id"] == order_id), None)
        if done:  # state outlives each query(), so a later turn can't refund the same order twice
            return text_result(f"Order {order_id} was already refunded ({done['refund_id']}). Don't refund it "
                               "again; give the customer that refund's details.", is_error=True)
        refund = {**REFUND, "refund_id": f"RF-{len(state.refunds) + 1:04d}"}
        state.refunds.append(refund)
        return text_result(json.dumps(refund))

    return create_sdk_mcp_server(name="lumen", version="1.0.0", tools=[lookup_order, process_refund])


AGENT_PROMPT = (
    "You are a customer support agent for Lumen Home, an online store. Look orders up with lookup_order and refund "
    "them with process_refund; never guess an ID, a date or an amount. Each message you receive is built from "
    "labelled sections: CASE FACTS holds exact values copied from tool results in this case and is always correct; "
    "CONVERSATION SUMMARY is a shortened record of earlier turns that may leave details out; RECENT TURNS are the "
    "latest turns, word for word; CUSTOMER MESSAGE is what you answer now. Reply to the customer message only."
)


def build_case_options(settings: Settings, state: CaseState) -> ClaudeAgentOptions:
    """Options for ONE customer turn: no resume and no continue_conversation, so each query() starts fresh (E1)."""
    return ClaudeAgentOptions(
        model=settings.model_id,
        system_prompt=AGENT_PROMPT,  # names the sections of every prompt and how far to trust each (C5)
        mcp_servers={"lumen": build_lumen_server(state)},  # lookup_order and process_refund, bound to this state
        tools=[],  # remove ALL built-in tools: Claude can use only ours
        allowed_tools=LUMEN_TOOLS,  # our tools run without asking for permission
        hooks=build_case_hooks(state),  # PostToolUse: record the facts, then trim (C1, C9)
        setting_sources=[],  # ignore ~/.claude settings, CLAUDE.md and hooks: the same run on any machine
        env={"ENABLE_TOOL_SEARCH": "false"},  # send both tool schemas up front: no ToolSearch calls
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=6,  # safety cap (01 C16); one customer turn needs at most 3
        max_budget_usd=settings.max_budget_usd,  # cost guard per turn
    )


async def run_agent(user_prompt: str, options: ClaudeAgentOptions) -> dict[str, Any]:
    """01's run_agent(), extended with options= and tool_results: what Claude actually received for each call.

    Returns {"answer", "subtype", "stop_reason", "num_turns", "tool_calls", "tool_results"}; each tool_results item
    is {"tool_use_id", "name", "input", "is_error", "text"}.
    """
    log.info("MODEL INPUT   prompt       %s", user_prompt)
    run: dict[str, Any] = {"answer": None, "subtype": None, "stop_reason": None, "num_turns": 0,
                           "tool_calls": [], "tool_results": []}
    uses: dict[str, tuple[str, dict]] = {}  # tool_use id -> (name, input)
    try:
        async for message in query(prompt=user_prompt, options=options):
            log_model_io(message)
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
    except ResultError as exc:  # raised AFTER the error ResultMessage (already logged)
        if exc.subtype == "error_max_turns":
            log.warning("Safety cap hit: max_turns=%s was used up before Claude finished. No answer.", options.max_turns)
        else:  # e.g. error_max_budget_usd, error_during_execution, an invalid API key
            log.error("The run failed: %s", exc)
    return run
