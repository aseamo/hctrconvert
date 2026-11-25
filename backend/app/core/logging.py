"""
HctrConvert — Structured Logging
──────────────────────────────
Sets up Python's logging module once at startup.

SOFTWARE ENGINEERING PRINCIPLE: "Observability"
- Every conversion should be traceable via logs
- Structured logs make debugging production issues possible
- Never use print() for operational output
"""
from __future__ import annotations

import logging
import sys

from app.core.config import get_settings


def setup_logging() -> None:
    """Configure root logger based on settings. Called once at app startup."""
    settings = get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format=settings.LOG_FORMAT,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,  # override any existing config
    )

    # Quiet noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("multipart").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger. Usage: logger = get_logger(__name__)"""
    return logging.getLogger(name)
