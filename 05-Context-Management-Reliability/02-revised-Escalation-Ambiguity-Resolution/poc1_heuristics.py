"""
POC 1a - Ask, never pick   (offline: no API call, free)
=======================================================
Two Lumen Home customers are named Alex Morgan. What would a selection heuristic do with them?

    most_recent   opens the account with the latest order       -> CUST-3101
    most_active   opens the account with the most orders        -> CUST-3388

The two heuristics don't even agree, and each one opens the OTHER customer's account for one of the two callers:
their orders, address and contact details, and any refund or address change made there. match_customer() never
picks: for 2 or more matches it returns no account data, and any ONE identifier the customer chooses narrows the
match to exactly one account.

Run:  python poc1_heuristics.py
"""

import json
import sys

from escalation_setup import CUSTOMERS, match_customer


def most_recent(candidates: list[dict]) -> dict:
    """Anti-pattern: the latest last_order_date wins."""
    return max(candidates, key=lambda customer: customer["last_order_date"])


def most_active(candidates: list[dict]) -> dict:
    """Anti-pattern: the most orders wins."""
    return max(candidates, key=lambda customer: len(customer["order_ids"]))


def main() -> int:
    alex_morgans = [customer for customer in CUSTOMERS if customer["name"] == "Alex Morgan"]

    print("A heuristic picks one Alex Morgan, whoever is calling (C12):")
    wrong = 0
    for caller in alex_morgans:
        for heuristic in (most_recent, most_active):
            opened = heuristic(alex_morgans)["customer_id"]
            verdict = "their own account" if opened == caller["customer_id"] else "SOMEONE ELSE'S account"
            wrong += opened != caller["customer_id"]
            print(f"   caller {caller['customer_id']}: {heuristic.__name__:<11} opens {opened} -> {verdict}")
    print(f"   {wrong} of 4 picks expose another customer's data\n")

    print("match_customer() never picks (C11):")
    print(f"   match_customer('Alex Morgan') -> {json.dumps(match_customer('Alex Morgan'))}\n")

    print("Any ONE identifier the customer chooses is enough (C13):")
    for identifier in ({"email": "A.Morgan@example.net"}, {"phone": "(503) 555-0118"}, {"order_number": "ord-8462"},
                       {"postcode": "97214"}, {"email": "alex@example.org"}):
        result = match_customer("Alex Morgan", **identifier)
        print(f"   + {identifier} -> {result['status']} {result.get('customer', {}).get('customer_id', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
