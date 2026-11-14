"""
common.py - shared helpers: read .env, set up logging, and log the model's input and output.
"""

import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from dotenv import load_dotenv

POC_DIR = Path(__file__).resolve().parent
log = logging.getLogger("poc")


@dataclass(frozen=True)
class Settings:
    model_id: str  # MODEL_ID: the Claude model for the support agent (POC 1) and the reviewer (POC 2)
    max_budget_usd: float  # MAX_BUDGET_USD: cost guard for a single query() call


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
            max_budget_usd=float(os.getenv("MAX_BUDGET_USD") or 0.50),
        )
    except ValueError as exc:
        raise RuntimeError(f"MAX_BUDGET_USD in .env must be a number ({exc})") from exc


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


def log_model_io(message: Any) -> None:
    """Log the model input or output carried by one message from the query() stream."""
    if isinstance(message, AssistantMessage):  # Claude's response = model OUTPUT
        for block in message.content:
            if isinstance(block, ThinkingBlock) and block.thinking:
                log.info("MODEL OUTPUT  thinking     %s", block.thinking)
            elif isinstance(block, TextBlock):
                log.info("MODEL OUTPUT  text         %s", block.text)
            elif isinstance(block, ToolUseBlock) and block.name == "StructuredOutput":
                # output_format at work (POC 2): Claude hands in its JSON through this built-in tool
                log.info("MODEL OUTPUT  structured   %s  (id=%s)", block.input, block.id)
            elif isinstance(block, ToolUseBlock):
                log.info("MODEL OUTPUT  tool_use     %s %s  (id=%s)", block.name, block.input, block.id)

    elif isinstance(message, UserMessage) and isinstance(message.content, list):  # tool results = model INPUT
        for block in message.content:
            if isinstance(block, ToolResultBlock):
                log.info(
                    "MODEL INPUT   tool_result  %s  (tool_use_id=%s, is_error=%s)",
                    block.content, block.tool_use_id, block.is_error,
                )

    elif isinstance(message, ResultMessage):  # the loop has ended
        log.info("MODEL OUTPUT  stop_reason  %s  (loop result: %s)", message.stop_reason, message.subtype)
