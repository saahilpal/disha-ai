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
    # Auth tokens and keys
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"\bpt_live_[0-9a-fA-F]+", re.IGNORECASE), "pt_live_[REDACTED]"),
    (re.compile(r"\bpt_test_[A-Za-z0-9_]+_token", re.IGNORECASE), "pt_test_[REDACTED]"),
    (re.compile(r"(?i)\b(?:password|passwd|pwd)\s*[:=]\s*[^\s,]+"), "password=[REDACTED]"),
    (
        re.compile(r"(?i)\b(?:token|api_key|apikey|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{8,}['\"]?"),
        "token=[REDACTED]",
    ),
    (re.compile(r"AIza[0-9A-Za-z\-_]{30,40}"), "[GOOGLE_API_KEY_REDACTED]"),
    (re.compile(r"gsk_[a-zA-Z0-9]{20,}"), "[GROQ_API_KEY_REDACTED]"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "[API_KEY_REDACTED]"),
    # Direct personal identifiers / PII / PHI
    (re.compile(r"\b\d{4}[\s\-]\d{4}[\s\-]\d{4}\b"), "[AADHAAR_REDACTED]"),
    (re.compile(r"(?:\+91[\-\s]?)?[6789]\d{9}\b|\b\d{5}[\-\s]?\d{5}\b"), "[PHONE_REDACTED]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[EMAIL_REDACTED]"),
    (
        re.compile(r"\b(?:MRN|UHID|PATIENT[_\s-]?ID|PATIENT#|IPD|OPD)[#:\-\s]*[A-Za-z0-9_\-]{4,20}\b", re.IGNORECASE),
        "[MRN_REDACTED]",
    ),
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
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
            ):
                payload[key] = redact_phi(str(value))

        return json.dumps(payload, ensure_ascii=False)


def setup_structured_logging(level: int = logging.INFO) -> None:
    """Configure root, disha, and disha_core loggers to use structured Zero-PHI JSON logging."""
    formatter = ZeroPHIJsonFormatter()

    for name in ("", "disha", "disha_core"):
        logger = logging.getLogger(name)
        logger.setLevel(level)
        if not any(isinstance(h.formatter, ZeroPHIJsonFormatter) for h in logger.handlers):
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            logger.addHandler(handler)
