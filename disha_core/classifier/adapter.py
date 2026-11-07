"""Authoritative Laya Classifier Adapter for Disha AI.

Manages System 1 non-autoregressive triage decisions via Laya (POST /v1/systemone
or local in-process Agent), enforcing:
1. Deterministic emergency pre-filter (Aho-Corasick) ahead of the ML layer.
2. 2.0s timeout, single retry, and consecutive-failure circuit breaker.
3. Safe fallback on classifier timeout, failure, or sub-threshold confidence.
4. Non-PHI routing telemetry and live status tracking for /ready and /internal/classifier.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from disha_core.classifier.schemas import CLINICAL_QUESTIONS, SCHEMA_VERSION
from disha_core.pipeline.breaker import EmergencyBreaker

logger = logging.getLogger("disha.classifier")


@dataclass
class LayaClassificationResult:
    intent: str  # meal_query | symptom_complaint | general_coaching | emergency_escalation
    emergency_triage: bool  # True if urgent emergency indicated
    pep_risk: int  # 0=low, 1=moderate, 2=high
    confidence: float
    is_fallback: bool
    checkpoint: str
    latency_ms: float
    raw_answers: dict[str, Any] = field(default_factory=dict)

    @property
    def is_emergency(self) -> bool:
        return self.emergency_triage or self.intent == "emergency_escalation"


class CircuitBreakerOpenError(Exception):
    """Raised when the classifier circuit breaker is open."""


class ClassifierCircuitBreaker:
    def __init__(self, failure_threshold: int = 3, reset_timeout_seconds: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.is_open = False

    def record_success(self) -> None:
        self.failure_count = 0
        self.is_open = False

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.failure_count >= self.failure_threshold:
            self.is_open = True
            logger.warning(
                "Laya classifier circuit breaker OPENED after %d consecutive failures",
                self.failure_count,
            )

    def allow_request(self) -> bool:
        if not self.is_open:
            return True
        # Check if reset timeout elapsed (half-open test)
        if time.monotonic() - self.last_failure_time > self.reset_timeout_seconds:
            logger.info("Laya classifier circuit breaker entering HALF-OPEN state")
            return True
        return False


class LayaClassifierAdapter:
    """Thin adapter owning all Laya System 1 decision calls."""

    def __init__(
        self,
        server_url: Optional[str] = None,
        api_key: Optional[str] = None,
        min_confidence: float = 0.40,
        model_name: str = "multilingual",
    ) -> None:
        self.server_url = server_url or os.getenv("LAYA_SERVER_URL", "")
        self.api_key = api_key or os.getenv("LAYA_API_KEY", "")
        self.min_confidence = float(os.getenv("LAYA_MIN_CONFIDENCE", str(min_confidence)))
        self.model_name = os.getenv("LAYA_MODEL", model_name)
        self.timeout_seconds = float(os.getenv("LAYA_TIMEOUT_SECONDS", "2.0"))

        self.circuit_breaker = ClassifierCircuitBreaker()
        self._in_process_agent: Any = None
        self._agent_init_lock = asyncio.Lock()

        # Telemetry metrics
        self.inference_count = 0
        self.fallback_count = 0
        self.last_latency_ms = 0.0
        self.last_checkpoint = self.model_name
        self.device = os.getenv("LAYA_DEVICE", "cpu")
        self.threads = int(os.getenv("LAYA_THREADS", str(os.cpu_count() or 2)))
        self.breaker = EmergencyBreaker()
        self.started_at = time.time()

    def get_status(self) -> dict[str, Any]:
        """Provides status data for /internal/classifier and /ready."""
        return {
            "service": "laya_decision_engine",
            "schema_version": SCHEMA_VERSION,
            "server_url": self.server_url or "in-process",
            "checkpoint": self.last_checkpoint,
            "device": self.device,
            "threads": self.threads,
            "min_confidence_gate": self.min_confidence,
            "inference_count": self.inference_count,
            "fallback_count": self.fallback_count,
            "last_latency_ms": round(self.last_latency_ms, 2),
            "circuit_breaker_open": self.circuit_breaker.is_open,
            "uptime_seconds": round(time.time() - self.started_at, 1),
        }

    async def is_ready(self) -> bool:
        """Readiness check used by /ready."""
        if self.server_url:
            base = self.server_url.split("/v1")[0]
            try:
                async with httpx.AsyncClient(timeout=1.5) as client:
                    resp = await client.get(f"{base}/health")
                    return resp.status_code == 200
            except Exception:
                return False
        # If in-process, verify package is importable
        try:
            import laya  # noqa: F401
            return True
        except ImportError:
            return False

    async def _classify_via_http(self, text: str) -> dict[str, Any]:
        """Dispatches to remote/containerized laya-serve."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "state": text,
            "questions": CLINICAL_QUESTIONS,
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(self.server_url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def _get_or_create_in_process_agent(self) -> Any:
        """Lazily initialize in-process Laya agent if laya-serve is not configured."""
        if self._in_process_agent is not None:
            return self._in_process_agent
        async with self._agent_init_lock:
            if self._in_process_agent is not None:
                return self._in_process_agent
            import laya

            subfolder = "multilingual" if self.model_name == "multilingual" else None
            # Run in worker thread to prevent event loop block during model construction
            agent = await asyncio.to_thread(
                laya.Agent,
                "convaiinnovations/laya",
                subfolder=subfolder,
                device=self.device,
            )
            self._in_process_agent = agent
            return self._in_process_agent

    async def _classify_via_in_process(self, text: str) -> dict[str, Any]:
        """Dispatches to in-process laya.Agent."""
        agent = await self._get_or_create_in_process_agent()
        return await asyncio.to_thread(agent.predict, text, CLINICAL_QUESTIONS)

    def _fallback_classification(self, text: str, reason: str, latency_ms: float) -> LayaClassificationResult:
        """Deterministic safety fallback when ML classification is unavailable."""
        self.fallback_count += 1
        t_lower = text.lower()
        logger.warning("Classifier fallback engaged (reason: %s)", reason)

        # Conservative deterministic intent heuristics for fallback
        if any(w in t_lower for w in ("dinner", "lunch", "breakfast", "meal", "khana", "diet", "recipe")):
            intent = "meal_query"
        elif any(w in t_lower for w in ("pain", "dard", "gas", "bloat", "pet", "acidity", "fever", "nausea")):
            intent = "symptom_complaint"
        else:
            intent = "general_coaching"

        return LayaClassificationResult(
            intent=intent,
            emergency_triage=False,
            pep_risk=0,
            confidence=0.50,
            is_fallback=True,
            checkpoint="deterministic_fallback",
            latency_ms=latency_ms,
            raw_answers={"fallback_reason": reason},
        )

    async def classify(self, text: str) -> LayaClassificationResult:
        """Main classification entry point.
        
        Performs:
        1. Deterministic red-flag safety check ahead of ML layer.
        2. Laya System 1 non-autoregressive decision classification.
        3. Confidence gating and fallback on timeout/circuit open.
        """
        start_time = time.monotonic()

        # 1. Deterministic red-flag safety layer ahead of ML model
        if self.breaker is not None:
            breaker_res = self.breaker.check(text)
            if breaker_res.triggered:
                latency = (time.monotonic() - start_time) * 1000.0
                return LayaClassificationResult(
                    intent="emergency_escalation",
                    emergency_triage=True,
                    pep_risk=2,
                    confidence=1.0,
                    is_fallback=False,
                    checkpoint="deterministic_breaker",
                    latency_ms=latency,
                    raw_answers={"breaker_category": breaker_res.category},
                )

        if not self.circuit_breaker.allow_request():
            latency = (time.monotonic() - start_time) * 1000.0
            return self._fallback_classification(text, "circuit_breaker_open", latency)

        last_exc: Optional[Exception] = None
        raw_output: Optional[dict[str, Any]] = None

        # Attempt up to 2 times (1 initial + 1 retry)
        for attempt in range(2):
            try:
                if self.server_url:
                    raw_output = await self._classify_via_http(text)
                else:
                    raw_output = await self._classify_via_in_process(text)
                self.circuit_breaker.record_success()
                break
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Laya classification attempt %d failed: %s",
                    attempt + 1,
                    str(exc),
                )
                if attempt == 0:
                    await asyncio.sleep(0.05)

        latency_ms = (time.monotonic() - start_time) * 1000.0
        self.last_latency_ms = latency_ms

        if raw_output is None:
            self.circuit_breaker.record_failure()
            return self._fallback_classification(
                text, f"inference_error: {type(last_exc).__name__}", latency_ms
            )

        self.inference_count += 1
        try:
            answers = raw_output.get("answers", {})
            routing = raw_output.get("routing", {})
            checkpoint_used = str(routing.get("checkpoint") or routing.get("model") or self.model_name)
            self.last_checkpoint = checkpoint_used

            intent_ans = answers.get("intent", {})
            chosen_intent = intent_ans.get("choice") or "general_coaching"
            intent_conf = float(
                intent_ans.get("answer_confidence")
                or (intent_ans.get("probabilities", {}).get(chosen_intent))
                or intent_ans.get("confidence", 0.70)
            )

            # Emergency Triage noul (calibrated threshold fitted at 0.70)
            emg_ans = answers.get("emergency_triage", {})
            emg_prob = float(emg_ans.get("noul") or emg_ans.get("probability", 0.0))
            is_emergency = emg_prob >= 0.70 or chosen_intent == "emergency_escalation"

            # PEP Risk score
            pep_ans = answers.get("pep_risk", {})
            pep_score_raw = pep_ans.get("score")
            pep_risk_idx = int(pep_score_raw) if isinstance(pep_score_raw, int) else 0

            # Confidence Gating: if intent confidence falls below threshold, engage safe fallback
            if intent_conf < self.min_confidence:
                logger.info(
                    "Classifier sub-threshold confidence (%.3f < %.3f); falling back to conservative routing",
                    intent_conf,
                    self.min_confidence,
                )
                return self._fallback_classification(text, "low_confidence_gate", latency_ms)

            # Log routing metadata without PHI
            logger.info(
                "Laya classification complete: intent=%s, conf=%.3f, emg=%s, latency=%.2fms, checkpoint=%s",
                chosen_intent,
                intent_conf,
                is_emergency,
                latency_ms,
                checkpoint_used,
            )

            return LayaClassificationResult(
                intent=chosen_intent,
                emergency_triage=is_emergency,
                pep_risk=pep_risk_idx,
                confidence=intent_conf,
                is_fallback=False,
                checkpoint=checkpoint_used,
                latency_ms=latency_ms,
                raw_answers=answers,
            )
        except Exception as exc:
            logger.error("Failed to parse Laya response schema: %s", exc, exc_info=True)
            return self._fallback_classification(text, f"parse_error: {exc}", latency_ms)
