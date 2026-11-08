from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

from disha_core.classifier.adapter import LayaClassificationResult, LayaClassifierAdapter

from .breaker import BreakerResult, EmergencyBreaker


class Intent(str, Enum):
    EMERGENCY_TRIAGE = "EMERGENCY_TRIAGE"
    MEAL_QUERY = "MEAL_QUERY"
    SYMPTOM_COMPLAINT = "SYMPTOM_COMPLAINT"
    EXERCISE_QUERY = "EXERCISE_QUERY"
    GENERAL_COACHING = "GENERAL_COACHING"
    APP_META = "APP_META"
    GREETING = "GREETING"
    UNKNOWN = "UNKNOWN"


@dataclass
class RouteDecision:
    breaker: BreakerResult
    intent: Intent
    pep_risk: int = 0
    confidence: float = 1.0
    is_emergency: bool = False
    skip_retrieval: bool = False
    classification_result: Optional[LayaClassificationResult] = None


class IntentClassifier(Protocol):
    def classify(self, text: str) -> Intent: ...


class LayaIntentClassifier:
    """Production intent classifier delegating to LayaClassifierAdapter."""

    def __init__(self, adapter: LayaClassifierAdapter | None = None) -> None:
        self.adapter = adapter or LayaClassifierAdapter()
        self.last_pep_risk: int = 0
        self.last_result: Optional[LayaClassificationResult] = None

    def classify(self, text: str) -> Intent:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            return RuleIntentClassifier().classify(text)
        return asyncio.run(self.async_classify(text))

    async def async_classify_with_result(self, text: str) -> tuple[Intent, LayaClassificationResult]:
        res = await self.adapter.classify(text)
        self.last_result = res
        self.last_pep_risk = res.pep_risk
        if res.is_emergency:
            return Intent.EMERGENCY_TRIAGE, res
        intent_map = {
            "meal_query": Intent.MEAL_QUERY,
            "symptom_complaint": Intent.SYMPTOM_COMPLAINT,
            "exercise_query": Intent.EXERCISE_QUERY,
            "general_coaching": Intent.GENERAL_COACHING,
            "app_meta": Intent.APP_META,
            "greeting": Intent.GREETING,
            "emergency_escalation": Intent.EMERGENCY_TRIAGE,
        }
        return intent_map.get(res.intent, Intent.GENERAL_COACHING), res

    async def async_classify(self, text: str) -> Intent:
        intent, _ = await self.async_classify_with_result(text)
        return intent


class RuleIntentClassifier:
    def classify(self, text: str) -> Intent:
        value = text.casefold()
        if re.search(r"\b(who are you|koun ho|what is disha|subscription|price|pricing|fees?|cost|charges?|how to use (?:the |this )?app|settings|profile(?:\s+tab|\s+page|\s+update)?)\b|दिशा क्या है|सब्सक्रिप्शन|कीमत|फीस|प्रोफाइल", value):
            return Intent.APP_META
        if re.search(r"\b(gym|workout|workouts|deadlifts?|weights?|lifting|bench press|squats?|sprints?|sprinting|hiit|crossfit|bodybuilding|kasrat)\b|जिम|कसरत|व्यायाम|डंबल|डेडलिफ्ट", value):
            return Intent.EXERCISE_QUERY
        if re.search(r"\b(dinner|breakfast|lunch|meal|khaana|khana|recipe|diet chart|aam|fruit)\b|नाश्ता|खाना|भोजन|डाइट", value):
            return Intent.MEAL_QUERY
        if re.search(r"\b(pain|dard|bloating|gas|fever|dizziness|symptom|pet phool|acidity|vomit|nausea)\b|दर्द|गैस|बुखार|चक्कर|उल्टी|सूजन", value):
            return Intent.SYMPTOM_COMPLAINT
        if re.search(r"^(?:namaste|hello|hi|hey|good morning|kaise ho)\b|नमस्ते|प्रणाम", value):
            return Intent.GREETING
        return Intent.GENERAL_COACHING

    async def async_classify(self, text: str) -> Intent:
        return self.classify(text)


class OnnxIntentClassifier:
    """Loads an ONNX graph; model-specific input/output mapping must be supplied."""

    def __init__(
        self,
        model_path: str | os.PathLike[str],
        encode: Callable[[str], dict[str, Any]],
        decode: Callable[[list[Any]], Intent],
    ) -> None:
        path = Path(model_path)
        if not path.is_file():
            raise FileNotFoundError(f"ONNX intent model not found: {path}")
        try:
            import onnxruntime as ort  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Install onnxruntime to use the local ONNX classifier") from exc
        self._session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        self._encode = encode
        self._decode = decode

    def classify(self, text: str) -> Intent:
        values = self._session.run(None, self._encode(text))
        intent = self._decode(values)
        if not isinstance(intent, Intent):
            raise TypeError("intent decoder must return an Intent")
        return intent

    async def async_classify(self, text: str) -> Intent:
        return await asyncio.to_thread(self.classify, text)


class IntentRouter:
    def __init__(
        self, classifier: IntentClassifier | None = None, breaker: EmergencyBreaker | None = None
    ) -> None:
        self.breaker = breaker or EmergencyBreaker()
        self.classifier = classifier if classifier is not None else LayaIntentClassifier()
        self.last_pep_risk: int = 0
        self.last_decision: Optional[RouteDecision] = None

    def route(self, text: str) -> tuple[BreakerResult, Intent | None]:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        emergency = self.breaker.check(text)
        if emergency.triggered:
            return emergency, None
        try:
            intent = self.classifier.classify(text)
            self.last_pep_risk = getattr(self.classifier, "last_pep_risk", 0)
            return emergency, intent
        except Exception:
            return emergency, Intent.UNKNOWN

    async def async_classify(self, text: str) -> Intent:
        if hasattr(self.classifier, "async_classify"):
            return await self.classifier.async_classify(text)
        return await asyncio.to_thread(self.classifier.classify, text)

    async def async_route_decision(self, text: str) -> RouteDecision:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        emergency = self.breaker.check(text)
        if emergency.triggered:
            decision = RouteDecision(
                breaker=emergency,
                intent=Intent.EMERGENCY_TRIAGE,
                pep_risk=2,
                confidence=1.0,
                is_emergency=True,
                skip_retrieval=True,
            )
            self.last_decision = decision
            self.last_pep_risk = 2
            return decision

        try:
            if hasattr(self.classifier, "async_classify_with_result"):
                intent, res = await self.classifier.async_classify_with_result(text)
                pep_risk = res.pep_risk
                conf = res.confidence
                is_emg = res.is_emergency
            else:
                intent = await self.async_classify(text)
                res = None
                pep_risk = getattr(self.classifier, "last_pep_risk", 0)
                conf = 1.0
                is_emg = (intent == Intent.EMERGENCY_TRIAGE)

            self.last_pep_risk = pep_risk
            skip_retrieval = intent in {
                Intent.GENERAL_COACHING,
                Intent.APP_META,
                Intent.GREETING,
                Intent.EMERGENCY_TRIAGE,
            }
            decision = RouteDecision(
                breaker=emergency,
                intent=intent,
                pep_risk=pep_risk,
                confidence=conf,
                is_emergency=is_emg,
                skip_retrieval=skip_retrieval,
                classification_result=res,
            )
            self.last_decision = decision
            return decision
        except Exception:
            decision = RouteDecision(
                breaker=emergency,
                intent=Intent.UNKNOWN,
                pep_risk=0,
                confidence=0.0,
                skip_retrieval=False,
            )
            self.last_decision = decision
            return decision

    async def async_route(self, text: str) -> tuple[BreakerResult, Intent | None]:
        decision = await self.async_route_decision(text)
        if decision.breaker.triggered:
            return decision.breaker, None
        return decision.breaker, decision.intent



