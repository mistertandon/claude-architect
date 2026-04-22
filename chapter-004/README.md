# Chapter 004 — Agentic Loop Termination: Correct Pattern vs Anti-Patterns

All four scripts run the **same multi-step task** with the **same tools** — only the loop termination logic differs. This makes each anti-pattern's failure mode visible.

## The One Correct Signal

```python
if response.stop_reason == "end_turn":   # model is done
    break
if response.stop_reason == "tool_use":   # model needs to act
    # execute tools, feed results back
```

`stop_reason` is a **structured enum** set by the API. It is deterministic, unambiguous, and the only field designed for orchestration control flow.

## The Three Anti-Patterns

### Anti-Pattern 1: NLP Parsing (`antipattern_nlp_parsing.py`)

```
❌  if "here is" in response.text.lower():  break
```

| Problem | Detail |
|---------|--------|
| Premature exit | Model says "Here is what I found so far..." then calls a tool → NLP check fires first → tool never executes |
| Brittle | Different models/temperatures produce different phrasing |
| Redundant | `stop_reason` already signals completion without parsing |

### Anti-Pattern 2: Iteration Cap as Primary Stop (`antipattern_iteration_cap.py`)

```
❌  for i in range(MAX_ITERATIONS):  # cap = 3
```

| Problem | Detail |
|---------|--------|
| Silent truncation | 4-step task hits cap at step 3 → transfer never executes, no error raised |
| Arbitrary | Any number you pick is wrong for some valid task |
| Misused safety net | Caps belong as a **fallback**, not the **primary** exit condition |

**Correct use of a cap** (safety net, not control flow):

```python
MAX_SAFETY = 25  # prevent infinite loops from bugs, not from normal operation
iteration = 0
while True:
    iteration += 1
    if iteration > MAX_SAFETY:
        raise RuntimeError("Agentic loop exceeded safety limit")
    # ... normal stop_reason-based loop ...
```

### Anti-Pattern 3: Text Presence (`antipattern_text_presence.py`)

```
❌  if any(block.type == "text" for block in response.content):  break
```

| Problem | Detail |
|---------|--------|
| False positive | Model emits text + tool_use in same response → text check fires → tool call dropped |
| Wrong abstraction | "Has text" ≠ "Is done" — text accompanies tool calls as conversational filler |
| Silent data loss | Tool calls in the same response are never executed |

## Setup

```bash
cd chapter-004

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

## Configure

Edit `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Run

```bash
export $(grep -v '^#' .env | xargs)

# Correct approach — completes all steps
python correct_loop.py

# Anti-pattern 1 — may exit early on "completion phrases"
python antipattern_nlp_parsing.py

# Anti-pattern 2 — truncates at iteration 3
python antipattern_iteration_cap.py

# Anti-pattern 3 — drops tool calls when text is present
python antipattern_text_presence.py
```

## Comparison Matrix

| Behavior | Correct | NLP Parsing | Iteration Cap | Text Presence |
|----------|---------|-------------|---------------|---------------|
| Termination signal | `stop_reason` enum | Free-text heuristic | Loop counter | Content type check |
| Multi-step tasks | Completes all | May truncate | Truncates at cap | Usually truncates at step 1 |
| Single-step tasks | Works | Works (by luck) | Works | Works (by luck) |
| Parallel tool calls | Handles correctly | May miss some | Depends on count | Drops if text present |
| Deterministic? | Yes | No | Yes but wrong | No |

## Exam Takeaway

`stop_reason` is the **only** correct termination signal because:

1. It is a **structured enum**, not free text — no parsing ambiguity
2. It is set by the **model intentionally** — "end_turn" means "I have nothing more to do"
3. It distinguishes **text-with-tool-call** from **final-answer** — something no text-inspection can do
4. Iteration caps are valid only as a **safety net** (set high, raise an error), never as the primary exit
