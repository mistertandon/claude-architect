"""
common.py - shared helpers: read .env, set up logging, and log the model's input and output.

This topic uses the Messages API (the anthropic package) directly: the Agent SDK has no batch interface.
"""

import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

POC_DIR = Path(__file__).resolve().parent
log = logging.getLogger("poc")


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


def setup_logging(script_name: str) -> None:
    """Log to the console and to logs/<script>_<time>.log, so a paid run can be re-read later."""
    log_dir = POC_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"{script_name}_{datetime.now():%Y%m%d_%H%M%S}.log"
    formatter = logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(log_file, encoding="utf-8")):
        handler.setFormatter(formatter)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def log_model_io(message: Any, tag: str = "") -> None:
    """Log one Messages API response (a synchronous call, or one batch result), tagged with its custom_id."""
    prefix = f"[{tag}] " if tag else ""
    for block in message.content:
        if block.type == "thinking" and block.thinking:
            log.info("MODEL OUTPUT  thinking     %s%s", prefix, block.thinking)
        elif block.type == "text":
            log.info("MODEL OUTPUT  text         %s%s", prefix, block.text)
    log.info("MODEL OUTPUT  stop_reason  %s%s  (Messages API)", prefix, message.stop_reason)
