"""
common.py - shared helpers: read .env.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

POC_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    model_id: str  # MODEL_ID: the Claude model of POC 1's extractions (POC 2 uses FORCED_MODEL)
    max_turns: int  # MAX_TURNS: safety cap on turns per extraction call
    max_budget_usd: float  # MAX_BUDGET_USD: cost guard for a single run


def load_settings() -> Settings:
    """Read .env. The SDK's Claude Code process takes ANTHROPIC_API_KEY from the environment."""
    env_file = POC_DIR / ".env"
    if not env_file.is_file():
        raise RuntimeError(f"{env_file} not found: copy .env.example to .env and add your API key")
    load_dotenv(env_file, override=True)  # .env wins over variables already set in your shell
    if os.getenv("ANTHROPIC_API_KEY", "") in ("", "your-api-key-here"):
        raise RuntimeError(f"set ANTHROPIC_API_KEY in {env_file}")
    try:
        return Settings(
            model_id=os.getenv("MODEL_ID") or "claude-sonnet-5-5",
            max_turns=int(os.getenv("MAX_TURNS") or 10),
            max_budget_usd=float(os.getenv("MAX_BUDGET_USD") or 0.50),
        )
    except ValueError as exc:
        raise RuntimeError(f"MAX_TURNS and MAX_BUDGET_USD in .env must be numbers ({exc})") from exc
