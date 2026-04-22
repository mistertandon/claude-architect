# Chapter 003 — Model-Driven vs Pre-Configured Tool Sequences

This POC contrasts two approaches to multi-tool orchestration using the **same tools and same user prompts**, making the behavioral difference unmistakable.

## The Two Approaches

### Model-Driven (`model_driven.py`) — The Correct Agentic Pattern

```
User prompt → Model reasons → Picks a tool → Gets result → Reasons again → ...
```

- The **model** decides which tool to call, in what order, and when to stop
- The developer writes a generic loop that is **tool-agnostic**
- Different user intents produce **different tool sequences** automatically
- The model can **skip irrelevant tools** and **adapt** when results change the plan

### Pre-Configured (`preconfigured.py`) — The Anti-Pattern

```
User prompt → Step 1: search → Step 2: inventory → Step 3: shipping → Done
```

- The **developer** hardcodes the tool sequence at build time
- The model is reduced to a **parameter extractor**, not a decision-maker
- Every query runs the **same pipeline** regardless of user intent
- Cannot handle tools outside the pipeline (e.g., discount code)

## Side-by-Side Comparison

| Dimension | Model-Driven | Pre-Configured |
|-----------|-------------|----------------|
| Who decides tool order? | Claude (at runtime) | Developer (at build time) |
| Adapts to user intent? | Yes — different prompts yield different tool paths | No — same pipeline always |
| Handles unexpected needs? | Yes — model can call any available tool | No — only pipeline tools run |
| API calls for simple query | Minimal (model skips unneeded tools) | Fixed (all pipeline steps run) |
| Loop code knows about tools? | No — fully generic | Yes — hardcoded per step |

## Setup

```bash
cd chapter-003

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

## Configure

Edit `.env` and set your API key:

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Run

Run both and compare output:

```bash
export $(grep -v '^#' .env | xargs)

# Model-driven: watch Claude choose different tool paths per scenario
python model_driven.py

# Pre-configured: watch the rigid pipeline waste calls and miss the discount
python preconfigured.py
```

## What to Observe

### Scenario 1: "Looking for a laptop for Seattle, have discount code SAVE10"

| Model-Driven | Pre-Configured |
|-------------|----------------|
| Searches → picks in-stock laptop → checks inventory → gets shipping → applies discount | Searches → checks inventory → gets shipping → **never applies discount** |
| 4-5 tool calls, all relevant | 3 tool calls, misses one the user asked for |

### Scenario 2: "Is product HP-1 in stock?"

| Model-Driven | Pre-Configured |
|-------------|----------------|
| Calls `check_inventory("HP-1")` directly → done | Forces `search_products` first → then inventory → then shipping (unnecessary) |
| 1 tool call | 3 tool calls, 2 wasted |

## Exam Takeaway

The agentic loop pattern works because the **loop is dumb and the model is smart**. The loop's only job is: send messages → execute whatever tools the model chose → feed results back. The moment you hardcode tool sequences, you've replaced model reasoning with developer assumptions — and the system can only handle scenarios you anticipated at build time.
