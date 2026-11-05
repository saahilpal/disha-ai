import re
from typing import List, Tuple

class EgressGate:
    """
    Tier 1 Egress Gate: Scrubs sensitive credentials and patient PHI before logging or transmission.
    Complies with DISHA, DPDP Act 2023, and HIPAA data minimization standards.
    """

    PATTERNS: List[Tuple[str, re.Pattern]] = [
        # API Keys & Secrets
        ("GROQ_KEY", re.compile(r"your_groq_api_key_here[A-Za-z0-9]{48,}")),
        ("OPENAI_KEY", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{32,128}")),
        ("GITHUB_PAT", re.compile(r"ghp_[A-Za-z0-9_]{36,255}")),
        ("BEARER_TOKEN", re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}", re.IGNORECASE)),
        
        # Indian Healthcare Identifiers (ABHA)
        ("ABHA_ID", re.compile(r"\b\d{2}-\d{4}-\d{4}-\d{4}\b|\b\d{14}\b")),
        ("ABHA_ADDRESS", re.compile(r"\b[A-Za-z0-9._%+-]+@abdm\b")),
        
        # Indian National IDs (Aadhaar & PAN)
        ("AADHAAR", re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")),
        ("PAN_CARD", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b")),
        
        # Indian Phone Numbers (+91 or 10-digit mobile starting with 6-9)
        ("INDIAN_PHONE", re.compile(r"(?:(?:\+|0{0,2})91[\s-]?)?[6789]\d{9}")),
    ]

    @classmethod
    def sanitize(cls, text: str) -> str:
        """Redacts all discovered credentials and PHI with deterministic placeholders."""
        if not text:
            return ""
        sanitized = text
        for token_name, pattern in cls.PATTERNS:
            sanitized = pattern.sub(f"[REDACTED_{token_name}]", sanitized)
        return sanitized

    @classmethod
    def contains_leak(cls, text: str) -> bool:
        """Returns True if any sensitive token or PHI identifier is present."""
        if not text:
            return False
        return any(pattern.search(text) is not None for _, pattern in cls.PATTERNS)
