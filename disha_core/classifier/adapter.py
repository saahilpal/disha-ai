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
import re
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from disha_core.classifier.schemas import CLINICAL_QUESTIONS, SCHEMA_VERSION
from disha_core.pipeline.breaker import EmergencyBreaker

logger = logging.getLogger("disha.classifier")

GREETING_RE = re.compile(
    r"^(?:namaste|hello|hi|hey|good\s+morning|good\s+afternoon|good\s+evening|kaise\s+ho)\b|"
    r"नमस्ते|प्रणाम|नमस्कार",
    re.I,
)

HIGH_RISK_PEP_RE = re.compile(
    r"\b(?:heavy\s+deadlifts?|deadlifts?|max\s+effort|high\s+intensity\s+sprints?|sprints?|sprinting|hiit|crossfit|heavy\s+weights?|heavy\s+lifting|100kg)\b|"
    r"डेडलिफ्ट|भारी\s+वजन",
    re.I,
)

MEAL_QUERY_RE = re.compile(
    r"\b(?:dinner|lunch|breakfast|meal|meals|diet|diet\s+plan|diet\s+chart|recipes?|calories?|"
    r"khana|khaana|nashta|phulkas?|rotis?|paneer|chilla|aam|fruits?|bhindi|sabzi|chawal|rice)\b|"
    r"नाश्ता|खाना|भोजन|डाइट|रोटी|सब्जी|फल",
    re.I,
)

SYMPTOM_COMPLAINT_RE = re.compile(
    r"\b(?:pain|dard|gas|bloat|bloating|pet\s+phool|acidity|fever|bukhar|nausea|vomit|vomiting|ulti|dizziness|chakk?ar|jalan|cramps?|reflux|indigestion|uneasy|takleef)\b|"
    r"दर्द|गैस|बुखार|चक्कर|उल्टी|सूजन|एसिडिटी|जलन|तकलीफ",
    re.I,
)

APP_META_RE = re.compile(
    r"\b(?:who are you|koun ho|tum koun|what is disha|about disha|subscription|price|pricing|fees?|cost|charges?|"
    r"how to use (?:the |this )?app|app features|settings|profile(?:\s+tab|\s+page|\s+update)?|my plan tab|privacy policy|terms)\b|"
    r"तुम कौन हो|दिशा क्या है|सब्सक्रिप्शन|कीमत|फीस|प्रोफाइल",
    re.I,
)

EXERCISE_QUERY_RE = re.compile(
    r"\b(?:gym|workout|workouts|deadlifts?|weight\s*lifting|weights|bench\s*press|squats?|"
    r"sprints?|sprinting|hiit|crossfit|bodybuilding|heavy lifting|strenuous|intense exercise|kasrat)\b|"
    r"जिम|कसरत|व्यायाम|डंबल|डेडलिफ्ट",
    re.I,
)


def refine_clinical_intent(base_intent: str, text: str, pep_risk: int) -> tuple[str, int]:
    """Disambiguates intent and calibrates PEP risk for safety bounds."""
    refined_pep = pep_risk
    if HIGH_RISK_PEP_RE.search(text):
        refined_pep = max(pep_risk, 2)

    if refined_pep >= 2 or EXERCISE_QUERY_RE.search(text):
        return "exercise_query", refined_pep

    if GREETING_RE.search(text.strip()) and not SYMPTOM_COMPLAINT_RE.search(text) and not MEAL_QUERY_RE.search(text):
        return "general_coaching", refined_pep

    if APP_META_RE.search(text):
        return "app_meta", refined_pep

    if base_intent == "general_coaching":
        if SYMPTOM_COMPLAINT_RE.search(text):
            return "symptom_complaint", refined_pep
        if MEAL_QUERY_RE.search(text):
            return "meal_query", refined_pep

    if base_intent == "symptom_complaint" and not SYMPTOM_COMPLAINT_RE.search(text):
        if MEAL_QUERY_RE.search(text):
            return "meal_query", refined_pep
        if GREETING_RE.search(text.strip()):
            return "general_coaching", refined_pep

    return base_intent, refined_pep


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
        self._cache: OrderedDict[str, LayaClassificationResult] = OrderedDict()
        self._cache_max_size = int(os.getenv("LAYA_CACHE_MAX_SIZE", "2048"))

        # Telemetry metrics
        self.inference_count = 0
        self.fallback_count = 0
        self.last_latency_ms = 0.0
        self.last_checkpoint = self.model_name
        self.device = os.getenv("LAYA_DEVICE", "cpu")
        self.threads = int(os.getenv("LAYA_THREADS", "4"))
        self.breaker = EmergencyBreaker()
        self.started_at = time.time()
        self.review_queue: Any = None

    def set_review_queue(self, review_queue: Any) -> None:
        """Attaches an optional ReviewQueueManager for zero-PHI telemetry."""
        self.review_queue = review_queue

    def _enqueue_review_trigger(
        self,
        raw_text: str,
        trigger_type: str,
        predicted_intent: str,
        confidence: float,
        emergency: bool,
        fallback_reason: Optional[str] = None,
        pre_breaker_category: Optional[str] = None,
        pep_risk: int = 0,
        raw_answers: Optional[dict[str, Any]] = None,
        patient_id: str = "runtime_turn",
    ) -> None:
        if self.review_queue is None:
            return
        try:
            from disha_core.classifier.review_queue import TriggerType

            trig_enum = TriggerType(trigger_type) if isinstance(trigger_type, str) else trigger_type

            self.review_queue.enqueue_decision(
                raw_user_input=raw_text,
                patient_id=patient_id,
                audit_event_id=str(uuid.uuid4()),
                ledger_hash="pending_turn_commit",
                trigger_type=trig_enum,
                model_checkpoint=self.last_checkpoint,
                predicted_intent=predicted_intent,
                intent_confidence=confidence,
                emergency_triage_prob=1.0 if emergency else 0.0,
                pep_risk_score=pep_risk,
                latency_ms=self.last_latency_ms,
                raw_answers=raw_answers or {},
                fallback_reason=fallback_reason,
                pre_breaker_category=pre_breaker_category,
            )
        except Exception as exc:
            logger.debug("Non-fatal review queue ingestion exception: %s", exc)

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
        # If in-process, verify package is importable or fallback mode permitted
        try:
            import laya  # noqa: F401
            return True
        except ImportError:
            return os.getenv("ALLOW_CLASSIFIER_FALLBACK", "true").lower() in ("1", "true", "yes")

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
        import torch

        agent = await self._get_or_create_in_process_agent()

        def _predict() -> dict[str, Any]:
            if self.device == "cpu":
                torch.set_num_threads(self.threads)
            with torch.inference_mode():
                return agent.predict(text, CLINICAL_QUESTIONS)

        return await asyncio.to_thread(_predict)

    def _fallback_classification(self, text: str, reason: str, latency_ms: float) -> LayaClassificationResult:
        """Deterministic safety fallback when ML classification is unavailable."""
        self.fallback_count += 1
        t_lower = text.lower()
        logger.warning("Classifier fallback engaged (reason: %s)", reason)

        pep_risk = 0
        if HIGH_RISK_PEP_RE.search(text):
            pep_risk = 2
            intent = "exercise_query"
        elif EXERCISE_QUERY_RE.search(text):
            pep_risk = 1
            intent = "exercise_query"
        elif APP_META_RE.search(text):
            intent = "app_meta"
        elif SYMPTOM_COMPLAINT_RE.search(text):
            intent = "symptom_complaint"
        elif MEAL_QUERY_RE.search(text):
            intent = "meal_query"
        elif GREETING_RE.search(text.strip()):
            intent = "general_coaching"
        else:
            intent = "general_coaching"

        trig = "LOW_CONFIDENCE" if "low_confidence" in reason else "ABSTAINED_FALLBACK"
        self._enqueue_review_trigger(
            raw_text=text,
            trigger_type=trig,
            predicted_intent=intent,
            confidence=0.50,
            emergency=False,
            fallback_reason=reason,
            pep_risk=pep_risk,
        )

        return LayaClassificationResult(
            intent=intent,
            emergency_triage=False,
            pep_risk=pep_risk,
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
        2. High-speed LRU query cache lookup (<0.5ms).
        3. Laya System 1 non-autoregressive decision classification.
        4. Confidence gating, ambiguous intent audit queueing, and fallback.
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

        # 2. High-speed LRU query cache check (<0.5ms)
        cache_key = text.strip().lower()
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            self.inference_count += 1
            hit_latency = (time.monotonic() - start_time) * 1000.0
            self.last_latency_ms = hit_latency
            self._cache.move_to_end(cache_key)
            return LayaClassificationResult(
                intent=cached.intent,
                emergency_triage=cached.emergency_triage,
                pep_risk=cached.pep_risk,
                confidence=cached.confidence,
                is_fallback=cached.is_fallback,
                checkpoint=cached.checkpoint,
                latency_ms=hit_latency,
                raw_answers=cached.raw_answers,
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

            # PEP Risk score (clamped to 0..2)
            pep_ans = answers.get("pep_risk", {})
            pep_score_raw = pep_ans.get("score")
            pep_risk_idx = int(round(pep_score_raw)) if isinstance(pep_score_raw, (int, float)) else 0
            if pep_risk_idx > 2:
                pep_risk_idx = 2
            elif pep_risk_idx < 0:
                pep_risk_idx = 0

            # Disambiguate into exercise_query or app_meta where indicated, and calibrate PEP risk
            final_intent, pep_risk_idx = refine_clinical_intent(chosen_intent, text, pep_risk_idx)

            # Check if intent prediction is ambiguous (margin < 0.15 between top 2 intents)
            probs = intent_ans.get("probabilities", {})
            sorted_probs = sorted(probs.values(), reverse=True) if probs else []
            is_ambiguous = len(sorted_probs) >= 2 and (sorted_probs[0] - sorted_probs[1] < 0.15)

            # Confidence Gating: if intent confidence falls below threshold, engage safe fallback
            if intent_conf < self.min_confidence:
                logger.info(
                    "Classifier sub-threshold confidence (%.3f < %.3f); falling back to conservative routing",
                    intent_conf,
                    self.min_confidence,
                )
                return self._fallback_classification(text, "low_confidence_gate", latency_ms)

            # Low-confidence (<0.7) or ambiguous intent audit wiring:
            # Asynchronously enqueue to review queue for clinical inspection
            if intent_conf < 0.70 or is_ambiguous:
                audit_reason = (
                    f"low_conf_{intent_conf:.2f}"
                    if intent_conf < 0.70
                    else f"ambiguous_margin_{sorted_probs[0] - sorted_probs[1]:.2f}"
                )
                self._enqueue_review_trigger(
                    raw_text=text,
                    trigger_type="LOW_CONFIDENCE",
                    predicted_intent=final_intent,
                    confidence=intent_conf,
                    emergency=is_emergency,
                    pep_risk=pep_risk_idx,
                    raw_answers=answers,
                    fallback_reason=audit_reason,
                )

            # Log routing metadata without PHI
            logger.info(
                "Laya classification complete: intent=%s, conf=%.3f, emg=%s, pep=%d, latency=%.2fms, checkpoint=%s",
                final_intent,
                intent_conf,
                is_emergency,
                pep_risk_idx,
                latency_ms,
                checkpoint_used,
            )

            result = LayaClassificationResult(
                intent=final_intent,
                emergency_triage=is_emergency,
                pep_risk=pep_risk_idx,
                confidence=intent_conf,
                is_fallback=False,
                checkpoint=checkpoint_used,
                latency_ms=latency_ms,
                raw_answers=answers,
            )

            # Update LRU cache
            self._cache[cache_key] = result
            if len(self._cache) > self._cache_max_size:
                self._cache.popitem(last=False)

            return result
        except Exception as exc:
            logger.error("Failed to parse Laya response schema: %s", exc, exc_info=True)
            return self._fallback_classification(text, f"parse_error: {exc}", latency_ms)
