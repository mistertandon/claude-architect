"""
Subagent definitions. Each subagent is a focused specialist with its own
system prompt, tools, and model configuration.

The coordinator never calls these tools directly — it selects WHICH subagent
to invoke, then that subagent runs its own agentic loop autonomously.
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()

import anthropic

client = anthropic.Anthropic()

# ---------------------------------------------------------------------------
# Subagent: Code Reviewer
# ---------------------------------------------------------------------------
CODE_REVIEW_TOOLS = [
    {
        "name": "analyze_complexity",
        "description": "Analyze cyclomatic complexity of a code snippet.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to analyze"}
            },
            "required": ["code"]
        }
    },
    {
        "name": "check_security_patterns",
        "description": "Scan code for common security vulnerabilities (SQL injection, XSS, etc).",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to scan"}
            },
            "required": ["code"]
        }
    },
]

# ---------------------------------------------------------------------------
# Subagent: Database Analyst
# ---------------------------------------------------------------------------
DB_TOOLS = [
    {
        "name": "explain_query",
        "description": "Run EXPLAIN on a SQL query and return the execution plan.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "SQL query to explain"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "suggest_indexes",
        "description": "Suggest database indexes based on query patterns.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table name"},
                "query_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Common query patterns against this table"
                }
            },
            "required": ["table", "query_patterns"]
        }
    },
]

# ---------------------------------------------------------------------------
# Subagent: API Designer
# ---------------------------------------------------------------------------
API_TOOLS = [
    {
        "name": "validate_openapi_spec",
        "description": "Validate an OpenAPI specification for correctness.",
        "input_schema": {
            "type": "object",
            "properties": {
                "spec": {"type": "string", "description": "OpenAPI spec (YAML or JSON string)"}
            },
            "required": ["spec"]
        }
    },
    {
        "name": "generate_endpoint_stub",
        "description": "Generate a stub implementation for an API endpoint.",
        "input_schema": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "description": "HTTP method"},
                "path": {"type": "string", "description": "Endpoint path"},
                "description": {"type": "string", "description": "What the endpoint does"}
            },
            "required": ["method", "path", "description"]
        }
    },
]

# ---------------------------------------------------------------------------
# Mock tool execution
# ---------------------------------------------------------------------------
MOCK_RESULTS = {
    "analyze_complexity": lambda inp: {
        "cyclomatic_complexity": 8,
        "risk": "moderate",
        "suggestion": "Consider extracting the nested conditionals into helper functions"
    },
    "check_security_patterns": lambda inp: {
        "vulnerabilities": [
            {"type": "SQL_INJECTION", "line": 12, "severity": "HIGH",
             "detail": "String concatenation in query construction"},
        ],
        "score": "6/10"
    },
    "explain_query": lambda inp: {
        "plan": "Seq Scan on users -> Filter (age > 25) -> Sort (name)",
        "estimated_cost": 1245.00,
        "warning": "Sequential scan on large table — missing index on 'age'"
    },
    "suggest_indexes": lambda inp: {
        "suggestions": [
            {"columns": ["age"], "type": "btree", "reason": "Frequent range queries on age"},
            {"columns": ["name", "age"], "type": "composite", "reason": "Covers sort + filter"},
        ]
    },
    "validate_openapi_spec": lambda inp: {
        "valid": True,
        "warnings": ["Missing 404 response definition on /users/{id}"]
    },
    "generate_endpoint_stub": lambda inp: {
        "code": f"@app.route('{inp.get('path', '/')}', methods=['{inp.get('method', 'GET')}'])\ndef handler():\n    pass  # TODO: implement",
        "framework": "Flask"
    },
}


def execute_tool(name: str, inp: dict) -> str:
    handler = MOCK_RESULTS.get(name)
    if handler:
        return json.dumps(handler(inp))
    return json.dumps({"error": f"Unknown tool: {name}"})


# ---------------------------------------------------------------------------
# Subagent registry — the coordinator references this to understand what
# specialists are available. Each entry is self-describing so the coordinator
# can make informed routing decisions.
# ---------------------------------------------------------------------------
SUBAGENT_REGISTRY = {
    "code_reviewer": {
        "description": "Reviews code for complexity, security vulnerabilities, and best practices.",
        "system_prompt": (
            "You are a senior code reviewer. Analyze code for complexity and security issues. "
            "Use your tools to provide concrete, actionable feedback. Be concise."
        ),
        "tools": CODE_REVIEW_TOOLS,
        "capabilities": ["code review", "security analysis", "complexity analysis"],
    },
    "db_analyst": {
        "description": "Analyzes SQL queries, suggests indexes, and optimizes database performance.",
        "system_prompt": (
            "You are a database performance analyst. Analyze queries, suggest indexes, "
            "and identify performance bottlenecks. Use your tools for evidence-based recommendations."
        ),
        "tools": DB_TOOLS,
        "capabilities": ["SQL analysis", "index optimization", "query performance"],
    },
    "api_designer": {
        "description": "Designs and validates REST API specifications and generates endpoint stubs.",
        "system_prompt": (
            "You are an API design specialist. Validate specs, suggest improvements, "
            "and generate implementation stubs. Follow REST best practices."
        ),
        "tools": API_TOOLS,
        "capabilities": ["API design", "OpenAPI validation", "endpoint generation"],
    },
}


def run_subagent(agent_name: str, task: str) -> str:
    """
    Run a subagent with its own agentic loop.

    Each subagent is an independent agentic loop with its own tools and
    system prompt. The coordinator doesn't micromanage — it delegates a
    task and gets back a result.
    """
    config = SUBAGENT_REGISTRY[agent_name]
    messages = [{"role": "user", "content": task}]
    iteration = 0

    print(f"\n    --- Subagent [{agent_name}] started ---")

    while True:
        iteration += 1
        response = client.messages.create(
            model=os.getenv("MODEL_ID", "claude-sonnet-4-20250514"),
            max_tokens=4096,
            system=config["system_prompt"],
            tools=config["tools"],
            # Each subagent gets ONLY its own tools — it can't accidentally
            # call another subagent's tools. This is isolation by design.
            messages=messages,
        )

        print(f"    [{agent_name}] iteration {iteration} | stop_reason: {response.stop_reason}")

        if response.stop_reason == "end_turn":
            result = ""
            for block in response.content:
                if hasattr(block, "text"):
                    result += block.text
            print(f"    --- Subagent [{agent_name}] finished ({iteration} iterations) ---")
            return result

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"    [{agent_name}] tool: {block.name}({json.dumps(block.input)[:80]}...)")
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})

        if response.stop_reason == "max_tokens":
            # Response was truncated — append the partial assistant message and
            # ask the model to continue from where it left off.
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": "Continue your response."})
            continue
