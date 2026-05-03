# task-05-01-01 — Persistent Case Facts Outside Summarized History

Core exam concept: Conversation summaries lose precise transactional data (amounts, dates, IDs). A "case facts" block pinned in the system prompt survives compaction and ensures the model never hallucinates a dollar amount or order number from a lossy summary. 

Demonstrates extracting transactional facts (amounts, dates, order numbers,
statuses) into a structured block that lives in the **system prompt** —
outside the conversation history that gets summarized/compacted.

---

## The problem: summaries lose precision

```
Turn 1: "Order #ORD-9821 for $149.99 placed January 15th"
Turn 2: "Payment PAY-4410 via credit card, $149.99"
Turn 3: "Also order #ORD-1087, $39.99, February 3rd"

         ↓  conversation compaction after turn 3

Summary: "Customer Jane contacted about a missing keyboard order
          and confirmed payment was made. She also mentioned a
          second order that arrived fine."

LOST: #ORD-9821, $149.99, Jan 15, PAY-4410, #ORD-1087, $39.99
```

The model now knows "an order" exists but not **which** order, and may
hallucinate "$150" or "ORD-9812" — breaking downstream tool calls and
destroying customer trust.

## The solution: case facts in the system prompt

```
┌──────────────────────────────────────────────────────────┐
│  System Prompt (NEVER summarized — persists verbatim)    │
│                                                          │
│  ## CASE FACTS (authoritative)                           │
│  {                                                       │
│    "customer": {"name": "Jane Smith", ...},              │
│    "orders": [                                           │
│      {"order_id": "ORD-9821", "amount": "$149.99", ...}, │
│      {"order_id": "ORD-1087", "amount": "$39.99", ...}  │
│    ],                                                    │
│    "payments": [                                         │
│      {"payment_id": "PAY-4410", "amount": "$149.99",...} │
│    ]                                                     │
│  }                                                       │
└──────────────────────────────────────────────────────────┘
                         +
┌──────────────────────────────────────────────────────────┐
│  Conversation History (CAN be summarized/compacted)      │
│                                                          │
│  [user] "Hi, I'm Jane Smith..."                          │
│  [assistant] "I can see your order..."                   │
│  ... (may be compacted into a summary) ...               │
└──────────────────────────────────────────────────────────┘
```

Facts survive compaction because they're in the system prompt, not
in the message history.

---

## Architecture: extract → merge → inject

```
  User message arrives
         ↓
  ┌─────────────────────┐
  │ EXTRACT              │  Separate API call with schema-constrained
  │ (stateless, per-turn)│  prompt — pulls structured facts from the
  │                      │  user's message without conversational tone
  └──────────┬───────────┘
             ↓
  ┌─────────────────────┐
  │ MERGE               │  Accumulate new facts into persistent store.
  │ (append-only lists, │  Dedup by ID so repeated mentions don't
  │  update-in-place    │  bloat the system prompt.
  │  for dicts)         │
  └──────────┬───────────┘
             ↓
  ┌─────────────────────┐
  │ INJECT              │  Build system prompt with CASE FACTS block.
  │ (system prompt,     │  Model sees exact values on every turn —
  │  every turn)        │  can never drift to approximate values.
  └──────────┬───────────┘
             ↓
  Main conversation API call
  (system prompt with facts + message history)
```

---

## What the POC does

Simulates a 4-turn customer support conversation:

| Turn | New facts introduced | Cumulative facts |
|------|---------------------|-----------------|
| 1 | Customer name, email, order #ORD-9821 ($149.99, Jan 15) | 1 order |
| 2 | Payment PAY-4410 ($149.99, credit card) | 1 order + 1 payment |
| 3 | Second order #ORD-1087 ($39.99, Feb 3) | 2 orders + 1 payment |
| 4 | Customer asks model to confirm exact details | Model cites from facts block |

Turn 4 is the proof: the model references exact order IDs and amounts
from the case facts block, not from memory of earlier turns.

---

## Prerequisites

- Python 3.11+
- An Anthropic API key (obtain at `console.anthropic.com`)

---

## Step-by-step setup

### 1. Enter the task folder

```bash
cd domain-05/task-05-01-01
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows PowerShell
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and set your key:

```
ANTHROPIC_API_KEY=sk-ant-...
```

### 5. Run the POC

```bash
python case_facts.py
```

---

## Expected output

```
============================================================
Persistent Case Facts — Conversation Demo
============================================================

──────────────────────────────────────────────────────────
Turn 1
──────────────────────────────────────────────────────────

  Customer: Hi, I'm Jane Smith (jane.smith@example.com). I placed order #ORD-9821 on January...

  [Extracted facts]
    customer: {"name": "Jane Smith", "email": "jane.smith@example.com"}
    orders: [{"order_id": "ORD-9821", "amount": "$149.99", ...}]

  [Case facts block in system prompt]
    Orders:   1
    Payments: 0
    Customer: Jane Smith

  Agent: Hello Jane! I can see your order #ORD-9821 for $149.99 placed on
         January 15th, 2025. Let me look into the delivery status...

──────────────────────────────────────────────────────────
Turn 2
──────────────────────────────────────────────────────────

  Customer: I also made a payment of $149.99 via credit card on January 15th...

  [Extracted facts]
    payments: [{"payment_id": "PAY-4410", "amount": "$149.99", ...}]

  [Case facts block in system prompt]
    Orders:   1
    Payments: 1
    Customer: Jane Smith

  Agent: I've noted payment PAY-4410 for $149.99 via credit card...

──────────────────────────────────────────────────────────
Turn 4
──────────────────────────────────────────────────────────

  Customer: Can you confirm exactly which orders I mentioned and their amounts?...

  Agent: Of course, Jane. Here are the exact details from our conversation:

         1. Order #ORD-9821 — $149.99 (wireless keyboard, January 15, 2025)
            Status: not yet received
         2. Order #ORD-1087 — $39.99 (USB-C hub, February 3, 2025)
            Status: delivered
         Payment: PAY-4410 — $149.99 via credit card (January 15, 2025)

============================================================
Final Case Facts (survives any conversation compaction)
============================================================
{
  "customer": {"name": "Jane Smith", "email": "jane.smith@example.com"},
  "orders": [
    {"order_id": "ORD-9821", "amount": "$149.99", ...},
    {"order_id": "ORD-1087", "amount": "$39.99", ...}
  ],
  "payments": [
    {"payment_id": "PAY-4410", "amount": "$149.99", ...}
  ]
}

============================================================
Why This Matters
============================================================

  If the conversation history were compacted after turn 2,
  the exact order numbers, amounts, and dates would be LOST.

  With case facts in the system prompt, those values persist
  verbatim — the model can NEVER hallucinate "$150" or "ORD-9812".

Full results → output.json
```

---

## Key design decisions

### Why the system prompt, not a user message?

The system prompt is **never summarized** during conversation compaction.
User messages are fair game for summarization — a fact in turn 1's user
message becomes "the customer discussed an order" after compaction.  The
system prompt persists verbatim across the entire conversation lifetime.

### Why a separate extraction call, not inline?

Extraction must be schema-constrained and deterministic.  Mixing it into
the conversational response would let the model's tone corrupt the
structured output — "Sure! The order is #ORD-9821" instead of clean JSON.
The separate call uses a strict schema prompt with no conversational
context.

### Why structured JSON, not prose?

Prose drifts: "about $150" vs "$149.99".  JSON preserves exact values and
makes downstream tool calls trivial — pass `case_facts["orders"][0]["order_id"]`
directly to a lookup tool without re-parsing natural language.

### Why merge with dedup, not replace?

Facts accumulate across turns.  Turn 1 mentions the order, turn 2 the
payment.  Replacing would lose the order when the payment arrives.
Dedup-by-ID prevents bloat when the customer re-mentions the same order.

### Why extract BEFORE the main response?

The system prompt for the current turn must already include facts from
THIS turn's user message.  If extraction happened after the response, the
model's answer for this turn wouldn't have the structured facts available.

---

## Files

```
domain-05/task-05-01-01/
├── case_facts.py        # entry point — main() and run_conversation()
├── config.py            # Anthropic client setup and MODEL constant
├── prompts.py           # system prompt templates (extraction + base)
├── data.py              # simulated conversation turns and initial case facts schema
├── extraction.py        # extract_facts() — schema-constrained fact extraction
├── merge.py             # merge_facts() — accumulate facts with dedup
├── prompt_builder.py    # build_system_prompt() — inject facts into system prompt
├── requirements.txt
├── .env.example
└── README.md
```

`output.json` is written on each run with the final case facts and
system prompt.
