
## Risk: model says 'Here is your balance...' while also calling a tool → NLP check fires first → remaining tools never execute

### ANTI-PATTERN: NLP-based termination

#### Scenario # User: Check my balance on ACC-001, show recent transactions, then transfer $100 to ACC-002.

#### Model response

```
Message(
    id="msg_013A7amd8eN4LiBFqbTi33Vs",
    container=None,
    content=[
        TextBlock(
            citations=None,
            text=(
                "I'll start by checking your balance and recent transactions "
                "on ACC-001 simultaneously, then handle the transfer once I "
                "have that information!\n\n"
                "**Step 1: Fetching balance & transactions in parallel...**"
            ),
            type="text"
        ),

        ToolUseBlock(
            id="toolu_01WfZVECXg9sHBPNhNDdTbFz",
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
            id="toolu_01Nv4Rbdct2NCXshGx9djr72",
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
    ...
```


>  [Iteration 1 | stop_reason: tool_use]
```
  Tool: get_account_balance({"account_id": "ACC-001"})
  Result: {"account_id": "ACC-001", "balance": 5200.0}
  ```
  ```
  Tool: get_transactions({"account_id": "ACC-001"})
  Result = [
    {
        "id": "TXN-1",
        "amount": -45.0,
        "merchant": "Coffee Shop",
        "date": "2026-04-20",
    },
    {
        "id": "TXN-2",
        "amount": -120.0,
        "merchant": "Electric Co",
        "date": "2026-04-19",
    },
    {
        "id": "TXN-3",
        "amount": 3000.0,
        "merchant": "Payroll",
        "date": "2026-04-15",
    },
]
```
<hr>

#### Model response

```
Message(
    id="msg_01KzDL4FMZcwzNpAmn27tAkE",
    container=None,
    content=[
        TextBlock(
            citations=None,
            text=(
                "Got everything! Your balance is sufficient for the transfer. "
                "Now proceeding!\n\n"
                "**Step 2: Transferring $100 to ACC-002...**"
            ),
            type="text"
        ),

        ToolUseBlock(
            id="toolu_01D5pxPJpnAe1uLAdnYzFvv5",
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
    ...
)
```


>  [Iteration 2 | stop_reason: tool_use]
```
  Tool: transfer_funds({"from_account": "ACC-001", "to_account": "ACC-002", "amount": 100})
  Result: {"status": "success", "new_balance": 5100.0}
```
<hr>

#### Model response

```
Message(
    id="msg_01Qji5pmrEQxWJgsoheUeetZ",
    container=None,
    content=[
        TextBlock(
            citations=None,
            text=(
                "Everything is done! Here's a full summary:\n\n"
                "---\n\n"

                "### 💰 Account Balance — ACC-001\n"
                "| | |\n"
                "|---|---|\n"
                "| **Previous Balance** | $5,200.00 |\n"
                "| **Transfer Amount** | -$100.00 |\n"
                "| **New Balance** | **$5,100.00** |\n\n"

                "---\n\n"

                "### 📋 Recent Transactions — ACC-001\n"
                "| Date | Merchant | Amount |\n"
                "|---|---|---|\n"
                "| 2026-04-20 | ☕ Coffee Shop | -$45.00 |\n"
                "| 2026-04-19 | ⚡ Electric Co | -$120.00 |\n"
                "| 2026-04-15 | 💼 Payroll | +$3,000.00 |\n\n"

                "---\n\n"

                "### ✅ Transfer Complete\n"
                "- **From:** ACC-001\n"
                "- **To:** ACC-002\n"
                "- **Amount:** $100.00\n"
                "- **Status:** Success!\n\n"

                "Let me know if there's anything else you need!"
            ),
            type="text"
        )
    ],
    ...
)
```


>  [Iteration 3 | stop_reason: end_turn]

  >>> NLP heuristic triggered — exiting loop <<<

Assistant: Everything is done! Here's a full summary:

---

### 💰 Account Balance — ACC-001
| | |
|---|---|
| **Previous Balance** | $5,200.00 |
| **Transfer Amount** | -$100.00 |
| **New Balance** | **$5,100.00** |

---

### 📋 Recent Transactions — ACC-001
| Date | Merchant | Amount |
|---|---|---|
| 2026-04-20 | ☕ Coffee Shop | -$45.00 |
| 2026-04-19 | ⚡ Electric Co | -$120.00 |
| 2026-04-15 | 💼 Payroll | +$3,000.00 |

---

### ✅ Transfer Complete
- **From:** ACC-001
- **To:** ACC-002
- **Amount:** $100.00
- **Status:** Success!

Let me know if there's anything else you need!
  Total iterations: 3
