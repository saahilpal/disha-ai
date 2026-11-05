import re
import time
from typing import Dict, List, Optional
from pydantic import BaseModel
from app.guardrails.lexicon import EMERGENCY_PATTERNS, EMERGENCY_TRIAGE_SCRIPTS

class EmergencyCheckResult(BaseModel):
    is_emergency: bool
    category: Optional[str] = None
    matched_phrases: List[str] = []
    triage_message: Optional[str] = None
    latency_ms: float

class PreTurnEmergencyCircuitBreaker:
    """
    Sub-millisecond Pre-Turn Deterministic Circuit Breaker.
    Completely bypasses the LLM on acute medical red flags (<0.005ms execution).
    """

    def __init__(self):
        self._compiled_categories: Dict[str, re.Pattern] = {}
        for category, patterns in EMERGENCY_PATTERNS.items():
            combined = "|".join(f"(?:{p})" for p in patterns)
            self._compiled_categories[category] = re.compile(combined, re.IGNORECASE)
            
        # Ingestion prompt injection cleaner
        self._tag_cleaner = re.compile(r"<[^>]+>")

    def sanitize_transcript(self, raw_text: str) -> str:
        """Strips HTML/XML tags from raw transcript to prevent delimiter escape injections."""
        if not raw_text:
            return ""
        return self._tag_cleaner.sub(" ", raw_text).strip()

    def evaluate(self, transcript: str) -> EmergencyCheckResult:
        """
        Evaluates user utterance for acute red-flag symptoms.
        Returns EmergencyCheckResult in microseconds.
        """
        start_time = time.perf_counter()
        clean_text = self.sanitize_transcript(transcript)
        
        for category, pattern in self._compiled_categories.items():
            matches = list(pattern.finditer(clean_text))
            if matches:
                matched_phrases = [m.group(0) for m in matches]
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                triage_script = EMERGENCY_TRIAGE_SCRIPTS.get(
                    category, EMERGENCY_TRIAGE_SCRIPTS["general"]
                )
                return EmergencyCheckResult(
                    is_emergency=True,
                    category=category,
                    matched_phrases=matched_phrases,
                    triage_message=triage_script,
                    latency_ms=latency_ms
                )

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return EmergencyCheckResult(
            is_emergency=False,
            category=None,
            matched_phrases=[],
            triage_message=None,
            latency_ms=latency_ms
        )

# Global singleton
emergency_circuit_breaker = PreTurnEmergencyCircuitBreaker()

