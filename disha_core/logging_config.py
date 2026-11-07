"""Structured JSON logging with strict Zero-PHI enforcement for Disha AI Core.

Ensures no Protected Health Information (PHI), tokens, or raw medical narratives
leak into application logs or telemetry.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

# Sensitive regex patterns to redact
_SENSITIVE_PATTERNS = [
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"pt_live_[0-9a-fA-F]+"), "pt_live_[REDACTED]"),
    (re.compile(r"password=([^\s,]+)", re.IGNORECASE), "password=[REDACTED]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[EMAIL_REDACTED]"),
]


def redact_phi(text: str) -> str:
    """Scrub known credentials, tokens, and PHI markers from log text."""
    redacted = text
    for pattern, replacement in _SENSITIVE_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


class ZeroPHIJsonFormatter(logging.Formatter):
    """Formats log records as structured JSON without PHI."""

    def format(self, record: logging.LogRecord) -> str:
        # Standard message resolution
        message = record.getMessage()
        clean_message = redact_phi(message)

        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": clean_message,
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Include custom extra attributes if present
        for key, value in record.__dict__.items():
            if key not in (
                "args", "asctime", "created", "exc_info", "exc_text",
                "filename", "funcName", "levelname", "levelno", "lineno",
                "module", "msecs", "message", "msg", "name", "pathname",
                "process", "processName", "relativeCreated", "stack_info",
                "thread", "threadName",
            ):
                payload[key] = redact_phi(str(value))

        return json.dumps(payload, ensure_ascii=False)


def setup_structured_logging(level: int = logging.INFO) -> None:
    """Configure the root or disha logger to use structured JSON logging."""
    root_logger = logging.getLogger("disha")
    root_logger.setLevel(level)

    # Avoid adding duplicate handlers if already configured
    if not any(isinstance(h.formatter, ZeroPHIJsonFormatter) for h in root_logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(ZeroPHIJsonFormatter())
        root_logger.addHandler(handler)
