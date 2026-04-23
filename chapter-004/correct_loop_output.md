############################################################
# Scenario 1: Multi-step task (balance + transactions + transfer)
############################################################

============================================================
### CORRECT: stop_reason-based loop
============================================================

#### User: Check my balance on ACC-001, show recent transactions, then transfer $100 to ACC-002.


__Model response__
```
Message(
    id="msg_011m3RJeGfULdnYQdAGcs1vv",
    content=[
        TextBlock(
            citations=None,
            text=(
                "Sure! I'll start by checking your balance and fetching "
                "your recent transactions for ACC-001 simultaneously right away!"
            ),
            type="text"
        ),

        ToolUseBlock(
            id="toolu_01TUbtdVtGESyhzD43J66UPq",
            caller=DirectCaller(
                type="direct"
            ),
            input={
                "account_id": "ACC-001"
            },
            name="get_account_balance",
            type="tool_use"
        ),

        ToolUseBlock(
            id="toolu_01TuU7i21pkjSxtbUPw4g2Eb",
            caller=DirectCaller(
                type="direct"
            ),
            input={
                "account_id": "ACC-001"
            },
            name="get_transactions",
            type="tool_use"
        ),
    ],
)
```
  [Iteration 1 | stop_reason: tool_use]
  Tool: get_account_balance({"account_id": "ACC-001"})
  Result: {"account_id": "ACC-001", "balance": 5200.0}
  Tool: get_transactions({"account_id": "ACC-001"})
  Result: [{"id": "TXN-1", "amount": -45.0, "merchant": "Coffee Shop", "date": "2026-04-20"}, {"id": "TXN-2", "amount": -120.0, "merchant": "Electric Co", "date": "2026-04-19"}, {"id": "TXN-3", "amount": 3000.0, "merchant": "Payroll", "date": "2026-04-15"}]

```
Message(
    id="msg_013FxbXi6gD2RSZsxJtCE94d",
    content=[
        TextBlock(
            citations=None,
            text=(
                "Here's a summary so far:\n\n"
                "💰 **Account Balance (ACC-001):** $5,200.00\n\n"
                "📋 **Recent Transactions:**\n"
                "| Date | Merchant | Amount |\n"
                "|------|----------|--------|\n"
                "| 2026-04-20 | Coffee Shop | -$45.00 |\n"
                "| 2026-04-19 | Electric Co | -$120.00 |\n"
                "| 2026-04-15 | Payroll | +$3,000.00 |\n\n"
                "---\n\n"
                "Great news — you have sufficient funds! "
                "Now I'll proceed with the $100 transfer to ACC-002."
            ),
            type="text"
        ),

        ToolUseBlock(
            id="toolu_011dfTRBnSo2LjpN6SfJ5pwa",
            caller=DirectCaller(
                type="direct"
            ),
            input={
                "from_account": "ACC-001",
                "to_account": "ACC-002",
                "amount": 100
            },
            name="transfer_funds",
            type="tool_use"
        ),
    ],
)
```
  [Iteration 2 | stop_reason: tool_use]
  Tool: transfer_funds({"from_account": "ACC-001", "to_account": "ACC-002", "amount": 100})
  Result: {"status": "success", "new_balance": 5100.0}

Model response
```
Message(
    id="msg_01Cm5HjoWgj9XGNSn4z1VDDd",
    container=None,
    content=[
        TextBlock(
            citations=None,
            text=(
                "✅ **Transfer Complete!**\n"
                "- **Transferred:** $100.00 from ACC-001 → ACC-002\n"
                "- **New Balance (ACC-001):** $5,100.00\n\n"
                "Everything went smoothly! "
                "Let me know if there's anything else you need. 😊"
            ),
            type="text"
        )
    ],
)
```
  [Iteration 3 | stop_reason: end_turn]

Assistant: ✅ **Transfer Complete!**
- **Transferred:** $100.00 from ACC-001 → ACC-002
- **New Balance (ACC-001):** $5,100.00

Everything went smoothly! Let me know if there's anything else you need. 😊
  Total iterations: 3

############################################################
# Scenario 2: Single-step task
############################################################

============================================================
### CORRECT: stop_reason-based loop
============================================================
User: What's the balance on ACC-003?


Model response

```
Message(
    id="msg_016xKjRWYQ9Zxnk62Yy9r1Ed",
    content=[
        TextBlock(
            citations=None,
            text="I'll check the balance for account ACC-003 right away!",
            type="text"
        ),

        ToolUseBlock(
            id="toolu_018EyN3ag3T4dNY8WVwp7nEX",
            caller=DirectCaller(
                type="direct"
            ),
            input={
                "account_id": "ACC-003"
            },
            name="get_account_balance",
            type="tool_use"
        ),
    ],
    ...
)
```

[Iteration 1 | stop_reason: tool_use]
Tool: get_account_balance({"account_id": "ACC-003"})
Result: {"account_id": "ACC-003", "balance": 12400.0}

Model response

```
Message(
    id="msg_012TPhzZLCsGJCo51iX25ANv",
    container=None,
    content=[
        TextBlock(
            citations=None,
            text=(
                "The current balance for account **ACC-003** "
                "is **$12,400.00**. "
                "Is there anything else you'd like to know?"
            ),
            type="text"
        )
    ],
    ...
)
```

  [Iteration 2 | stop_reason: end_turn]

Assistant: The current balance for account **ACC-003** is **$12,400.00**. Is there anything else you'd like to know?
  Total iterations: 2
