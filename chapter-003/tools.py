"""Shared tool definitions and mock execution layer."""

import json

TOOLS = [
    {
        "name": "search_products",
        "description": "Search the product catalog by keyword. Returns a list of matching products with IDs and prices.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "check_inventory",
        "description": "Check if a specific product is currently in stock.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "Product ID to check"}
            },
            "required": ["product_id"]
        }
    },
    {
        "name": "get_shipping_estimate",
        "description": "Get estimated shipping time for a product to a destination.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "Product ID"},
                "destination": {"type": "string", "description": "Shipping destination city"}
            },
            "required": ["product_id", "destination"]
        }
    },
    {
        "name": "apply_discount",
        "description": "Check and apply any available discount codes for a product.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "Product ID"},
                "code": {"type": "string", "description": "Discount code to apply"}
            },
            "required": ["product_id", "code"]
        }
    }
]

MOCK_DATA = {
    "products": {
        "laptop": [
            {"id": "LAP-1", "name": "ProBook 14", "price": 999},
            {"id": "LAP-2", "name": "UltraSlim X", "price": 1299},
        ],
        "headphones": [
            {"id": "HP-1", "name": "BassMax Pro", "price": 199},
        ],
    },
    "inventory": {
        "LAP-1": {"in_stock": True, "qty": 23},
        "LAP-2": {"in_stock": False, "qty": 0},
        "HP-1": {"in_stock": True, "qty": 150},
    },
    "shipping": {
        "LAP-1": {"days": 3, "cost": 12.99},
        "LAP-2": {"days": None, "cost": None},
        "HP-1": {"days": 2, "cost": 5.99},
    },
    "discounts": {
        "SAVE10": {"percent": 10, "valid_products": ["LAP-1", "HP-1"]},
    }
}


def execute_tool(name: str, inp: dict) -> str:
    if name == "search_products":
        results = MOCK_DATA["products"].get(inp["query"].lower(), [])
        return json.dumps(results if results else {"message": "No products found"})

    if name == "check_inventory":
        inv = MOCK_DATA["inventory"].get(inp["product_id"], {"error": "unknown product"})
        return json.dumps(inv)

    if name == "get_shipping_estimate":
        ship = MOCK_DATA["shipping"].get(inp["product_id"], {"error": "unknown product"})
        ship["destination"] = inp.get("destination", "unknown")
        return json.dumps(ship)

    if name == "apply_discount":
        code_data = MOCK_DATA["discounts"].get(inp.get("code", ""), None)
        if not code_data:
            return json.dumps({"error": "Invalid discount code"})
        if inp["product_id"] not in code_data["valid_products"]:
            return json.dumps({"error": "Code not valid for this product"})
        return json.dumps({"discount_percent": code_data["percent"], "applied": True})

    return json.dumps({"error": f"Unknown tool: {name}"})
