# Chapter 01 — Agentic Loop Control Flow

Minimal POC demonstrating the core agentic loop pattern: keep looping on `tool_use`, stop on `end_turn`.

## Setup

```bash
cd chapter-01

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependency
pip install anthropic python-dotenv
```

## Configure

Edit `.env` and set your API key:

```
ANTHROPIC_API_KEY=sk-ant-...
MODEL_ID=claude-sonnet-4-20250514
```

## Run

```bash
# Load env vars and run
export $(grep -v '^#' .env | xargs) && python agentic_loop.py
```

## What to observe

1. **Single tool call** — the model calls `get_weather` once, receives the result, then responds (`end_turn`).
2. **Multi tool call** — the model calls `get_weather` for each city (possibly in parallel within one turn), gathers all results, then synthesizes a comparison (`end_turn`).

## Agentic Loop Flow

```
User message
     │
     ▼
┌──────────┐
│  API Call │◄──────────────────┐
└────┬─────┘                    │
     │                          │
     ▼                          │
 stop_reason?                   │
     │                          │
     ├── "tool_use" ──► Execute tools, append results to messages
     │
     └── "end_turn" ──► Print final answer, EXIT loop
```
