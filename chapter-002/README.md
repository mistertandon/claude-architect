# Chapter 002 — Tool Results in Conversation History

Minimal POC showing **how tool results are appended to conversation history** so the model can reason across multiple tool calls.

## Core Concept

The model is stateless between API calls. The only way it "remembers" prior tool calls and their results is through the `messages` list you send each iteration. This POC makes that visible by:

1. Printing the message count each iteration
2. Dumping the full conversation history at the end

## The Three-Step History Contract

Each agentic loop iteration appends exactly **two messages**:

| Step | Role | Content | Why |
|------|------|---------|-----|
| 1 | `assistant` | Full response (text + tool_use blocks) | Preserves the model's reasoning and call metadata |
| 2 | `user` | `tool_result` blocks with matching `tool_use_id` | Returns external data; user-role because it comes from outside the model |

Skipping either step breaks the API's alternating-role requirement and loses context the model needs for its next decision.

## Multi-Step Reasoning Demo

The prompt forces a dependent chain:

```
User: "My order ORD-101 is delayed. When will the item be back in stock?"

Iteration 1:  Model calls lookup_order("ORD-101")
              → learns product_id is "PROD-A"

Iteration 2:  Model calls check_inventory("PROD-A")   ← only possible because
              → learns restock_date is "2026-04-25"      iteration 1's result is
                                                          in the history

Iteration 3:  Model synthesizes both results → end_turn
```

Without appending tool results to history, the model at iteration 2 would have no idea that `PROD-A` is the relevant product.

## Setup

```bash
cd chapter-002

python3 -m venv venv
source venv/bin/activate

pip install anthropic
```

## Configure

Edit `.env` and set your API key:

```
ANTHROPIC_API_KEY=sk-ant-...
MODEL_ID=claude-sonnet-4-20250514
```

## Run

```bash
export $(grep -v '^#' .env | xargs) && python tool_result_history.py
```

## Expected Output

You will see:

- **Iteration counts** showing the loop progressing
- **Message count growing** (1 → 3 → 5 → ...) as assistant + tool_result pairs accumulate
- **Tool calls chaining** — the second call uses data from the first call's result
- **Final history dump** showing the complete message structure the API received
