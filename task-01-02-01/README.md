# Task 01-02-01 — Coordinator Agent with Dynamic Subagent Selection

A coordinator agent that **analyzes query requirements** and **dynamically selects** which specialist subagents to invoke, rather than always routing through the full pipeline.

## Architecture

```
                         ┌──────────────────────┐
                         │   COORDINATOR AGENT   │
                         │  (its own agentic     │
                         │   loop with one tool:  │
                         │   delegate_to_subagent)│
                         └─────────┬─────────────┘
                                   │
                    Model decides which to invoke
                    based on query analysis
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                     │
              ▼                    ▼                     ▼
     ┌────────────────┐  ┌────────────────┐   ┌────────────────┐
     │  code_reviewer  │  │  db_analyst     │   │  api_designer   │
     │  (own loop,     │  │  (own loop,     │   │  (own loop,     │
     │   own tools)    │  │   own tools)    │   │   own tools)    │
     └────────────────┘  └────────────────┘   └────────────────┘
```

## Key Design Decisions

### Why subagents are exposed as a tool (not hardcoded routing)

The coordinator uses `delegate_to_subagent` as a tool within its own agentic loop. This means:

- The **model** decides which subagents to call — not if/else chains in code
- It can invoke **1, 2, or all 3** depending on the query
- It can call the **same subagent twice** with different tasks if needed
- The coordinator code is **generic** — adding a new subagent requires zero code changes to the coordinator, only a new registry entry

### Why each subagent has its own agentic loop

- **Isolation**: Each subagent has its own tools, system prompt, and message history — it can't accidentally use another subagent's tools
- **Autonomy**: The coordinator delegates a task, not a sequence of tool calls — the subagent decides how to accomplish it
- **Composability**: Subagents can be tested and run independently

### Why the coordinator reformulates tasks

The coordinator doesn't pass the raw user query to subagents. It extracts the **relevant portion** and crafts a focused instruction. This prevents subagents from being confused by irrelevant context.

## The Three Scenarios

| Scenario | User Query | Subagents Invoked | Why |
|----------|-----------|-------------------|-----|
| 1 | "Optimize this SQL query" | `db_analyst` only | Pure DB task — no code review or API design needed |
| 2 | "Review this code + generate OpenAPI spec" | `code_reviewer` + `api_designer` | Two domains, but no DB optimization needed |
| 3 | "Review handler + optimize SQL + generate spec" | All three | All domains are relevant |

Compare this to a pipeline that always runs all three — Scenario 1 would waste 2 unnecessary subagent invocations.

## Setup

```bash
cd task-01-02-01

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
export $(grep -v '^#' .env | xargs) && python coordinator.py
```

## What to Observe

1. **Scenario 1 output**: The coordinator invokes only `db_analyst`. You'll see one subagent loop. No code_reviewer or api_designer activity.

2. **Scenario 2 output**: Two subagent loops run (`code_reviewer` finds SQL injection, `api_designer` generates spec). No db_analyst.

3. **Scenario 3 output**: All three subagents fire. The coordinator synthesizes all results into a unified answer.

4. **Coordinator reasoning**: Before delegating, the coordinator explains which subagents it chose and why — this is the model-driven selection in action.

## Exam Takeaway

The coordinator pattern works because it applies the agentic loop at **two levels**:

- **Outer loop** (coordinator): model decides which specialists to invoke
- **Inner loops** (subagents): each specialist decides which tools to use

Both loops use the same `stop_reason`-based termination. The coordinator doesn't hardcode routing rules — it treats subagent selection as a tool-use decision, letting the model reason about which expertise the query requires.
