"""
tools.py - the agent's two tools, and build_options(): the one place that configures every POC run.

A tool = name + description + JSON Schema for its input + an async handler.
Claude sees the first three and decides when to call the tool. The SDK runs the handler.
"""

import ast
import operator
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ToolAnnotations, create_sdk_mcp_server, tool

from common import Settings

# Claude sees each tool under its full name: mcp__<server name>__<tool name>.
SERVER_NAME = "poc"
CALCULATOR = f"mcp__{SERVER_NAME}__calculator"
WEB_SEARCH = f"mcp__{SERVER_NAME}__web_search"

SYSTEM_PROMPT = (
    "You are a helpful assistant. Use web_search to look up facts you don't know, "
    "and use the calculator for every arithmetic step."
)

# ---------------------------------------------------------------- tool 1: calculator

_OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def _evaluate(node: ast.AST) -> float:
    """Compute a parsed expression. Only numbers, + - * / and parentheses are allowed (no eval())."""
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_evaluate(node.operand)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_evaluate(node.left), _evaluate(node.right))
    raise ValueError(f"'{ast.unparse(node)}' is not supported")


@tool(
    "calculator",
    "Evaluate an arithmetic expression and return the exact result. Supports numbers, + - * / "
    "and parentheses. Use it for EVERY arithmetic step instead of calculating in your head.",
    {
        "type": "object",
        "properties": {"expression": {"type": "string", "description": "The expression, e.g. '1234 * 5678'"}},
        "required": ["expression"],
    },
    annotations=ToolAnnotations(readOnlyHint=True),  # no side effects: the SDK may run several calls in parallel
)
async def calculator(args: dict[str, Any]) -> dict[str, Any]:
    expression = str(args.get("expression", ""))
    try:
        value = _evaluate(ast.parse(expression.replace(",", ""), mode="eval"))  # "1,234" -> "1234"
        text = str(int(value)) if float(value).is_integer() else str(round(value, 6))  # 7006652.0 -> "7006652"
    except Exception as exc:
        # A failed tool still returns a RESULT: is_error=True tells Claude it failed, the text helps it recover.
        message = f"Error: {exc}. Use only numbers, + - * / and parentheses (write a power as repeated multiplication)."
        return {"content": [{"type": "text", "text": message}], "is_error": True}
    return {"content": [{"type": "text", "text": text}]}


# ---------------------------------------------------------------- tool 2: web_search (stub)


def _search_backend(search_text: str) -> str:
    """Stands in for a real search API. Nimbus Robotics is made up, so Claude can't know its price."""
    if "nimbus" in search_text.lower():
        return "Nimbus Robotics shares last traded at $187.42."
    return f"No results found for '{search_text}'."


@tool(
    "web_search",
    "Search the web and return result snippets. Use it to look up facts you don't know, "
    "such as current prices or recent events.",
    {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "What to search for, e.g. 'Nimbus Robotics'"}},
        "required": ["query"],
    },
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def web_search(args: dict[str, Any]) -> dict[str, Any]:
    try:
        text = _search_backend(str(args.get("query", "")))  # a real search API can fail (network, quota, ...)
    except Exception as exc:
        return {"content": [{"type": "text", "text": f"Search failed: {exc}"}], "is_error": True}
    return {"content": [{"type": "text", "text": text}]}


# ---------------------------------------------------------------- options for every POC run


def build_options(settings: Settings, max_turns: int | None = None) -> ClaudeAgentOptions:
    """Configure one POC run. Each option is one deliberate decision."""
    return ClaudeAgentOptions(
        model=settings.model_id,
        system_prompt=SYSTEM_PROMPT,  # without one, the SDK sends an empty system prompt
        mcp_servers={SERVER_NAME: create_sdk_mcp_server(name=SERVER_NAME, tools=[calculator, web_search])},
        tools=[],  # remove ALL built-in tools (Bash, Read, WebSearch, ...): Claude can use only ours
        allowed_tools=[CALCULATOR, WEB_SEARCH],  # our tools run without asking for permission
        setting_sources=[],  # ignore ~/.claude settings, CLAUDE.md and hooks: the same run on any machine
        env={"ENABLE_TOOL_SEARCH": "false"},  # send both tool schemas up front: no ToolSearch calls
        thinking={"type": "adaptive", "display": "summarized"},  # return Claude's reasoning text (same cost)
        max_turns=max_turns,  # safety cap on tool-use turns (POC 2); None = no cap
        max_budget_usd=settings.max_budget_usd,  # cost guard: the SDK stops a run whose estimated spend passes this
    )
