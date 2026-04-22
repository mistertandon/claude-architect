"""Shared tool definitions and mock execution layer."""

import json

TOOLS = [
    {
        "name": "get_account_balance",
        "description": "Get the current balance for a bank account.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Account ID"}
            },
            "required": ["account_id"]
        }
    },
    {
        "name": "get_transactions",
        "description": "Get recent transactions for an account.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Account ID"},
                "limit": {"type": "integer", "description": "Max transactions to return"}
            },
            "required": ["account_id"]
        }
    },
    {
        "name": "transfer_funds",
        "description": "Transfer money between two accounts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_account": {"type": "string", "description": "Source account ID"},
                "to_account": {"type": "string", "description": "Destination account ID"},
                "amount": {"type": "number", "description": "Amount to transfer"}
            },
            "required": ["from_account", "to_account", "amount"]
        }
    }
]

MOCK_DATA = {
    "balances": {"ACC-001": 5200.00, "ACC-002": 890.50, "ACC-003": 12400.00},
    "transactions": {
        "ACC-001": [
            {"id": "TXN-1", "amount": -45.00, "merchant": "Coffee Shop", "date": "2026-04-20"},
            {"id": "TXN-2", "amount": -120.00, "merchant": "Electric Co", "date": "2026-04-19"},
            {"id": "TXN-3", "amount": 3000.00, "merchant": "Payroll", "date": "2026-04-15"},
        ],
    }
}


def execute_tool(name: str, inp: dict) -> str:
    if name == "get_account_balance":
        bal = MOCK_DATA["balances"].get(inp["account_id"])
        if bal is None:
            return json.dumps({"error": "Account not found"})
        return json.dumps({"account_id": inp["account_id"], "balance": bal})

    if name == "get_transactions":
        txns = MOCK_DATA["transactions"].get(inp["account_id"], [])
        limit = inp.get("limit", 5)
        return json.dumps(txns[:limit])

    if name == "transfer_funds":
        src = inp["from_account"]
        dst = inp["to_account"]
        amt = inp["amount"]
        if src not in MOCK_DATA["balances"]:
            return json.dumps({"error": f"Source account {src} not found"})
        if MOCK_DATA["balances"][src] < amt:
            return json.dumps({"error": "Insufficient funds"})
        MOCK_DATA["balances"][src] -= amt
        MOCK_DATA["balances"].setdefault(dst, 0)
        MOCK_DATA["balances"][dst] += amt
        return json.dumps({"status": "success", "new_balance": MOCK_DATA["balances"][src]})

    return json.dumps({"error": f"Unknown tool: {name}"})
