"""
common.py - shared helpers: read .env.

This topic uses the Messages API (the anthropic package) directly: the Agent SDK has no batch interface.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

POC_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    model_id: str  # MODEL_ID: the Claude model for the sample calls and every batch request
    poll_seconds: int  # POLL_SECONDS: how often a running batch is checked


def load_settings() -> Settings:
    """Read .env. The anthropic client takes ANTHROPIC_API_KEY from the environment."""
    env_file = POC_DIR / ".env"
    if not env_file.is_file():
        raise RuntimeError(f"{env_file} not found: copy .env.example to .env and add your API key")
    load_dotenv(env_file, override=True)  # .env wins over variables already set in your shell
    if os.getenv("ANTHROPIC_API_KEY", "") in ("", "your-api-key-here"):
        raise RuntimeError(f"set ANTHROPIC_API_KEY in {env_file}")
    try:
        return Settings(model_id=os.getenv("MODEL_ID") or "claude-sonnet-5-5",
                        poll_seconds=int(os.getenv("POLL_SECONDS") or 60))
    except ValueError as exc:
        raise RuntimeError(f"POLL_SECONDS in .env must be a number ({exc})") from exc
