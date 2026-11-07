from __future__ import annotations

import asyncio
import os
import re
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol

from .breaker import BreakerResult, EmergencyBreaker
from disha_core.classifier.adapter import LayaClassifierAdapter, LayaClassificationResult


class Intent(str, Enum):
    EMERGENCY_TRIAGE = "EMERGENCY_TRIAGE"
    MEAL_QUERY = "MEAL_QUERY"
    SYMPTOM_COMPLAINT = "SYMPTOM_COMPLAINT"
    GENERAL_COACHING = "GENERAL_COACHING"
    UNKNOWN = "UNKNOWN"


class IntentClassifier(Protocol):
    def classify(self, text: str) -> Intent: ...


class LayaIntentClassifier:
    """Production intent classifier delegating to LayaClassifierAdapter."""

    def __init__(self, adapter: LayaClassifierAdapter | None = None) -> None:
        self.adapter = adapter or LayaClassifierAdapter()

    def classify(self, text: str) -> Intent:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            return RuleIntentClassifier().classify(text)
        return asyncio.run(self.async_classify(text))

    async def async_classify(self, text: str) -> Intent:
        res = await self.adapter.classify(text)
        if res.is_emergency:
            return Intent.EMERGENCY_TRIAGE
        intent_map = {
            "meal_query": Intent.MEAL_QUERY,
            "symptom_complaint": Intent.SYMPTOM_COMPLAINT,
            "general_coaching": Intent.GENERAL_COACHING,
            "emergency_escalation": Intent.EMERGENCY_TRIAGE,
        }
        return intent_map.get(res.intent, Intent.GENERAL_COACHING)


class RuleIntentClassifier:
    def classify(self, text: str) -> Intent:
        value = text.casefold()
        if re.search(r"\b(dinner|breakfast|lunch|meal|khaana|khana|recipe|diet chart)\b|नाश्ता|खाना|भोजन|डाइट", value):
            return Intent.MEAL_QUERY
        if re.search(r"\b(pain|dard|bloating|gas|fever|dizziness|symptom|pet phool)\b|दर्द|गैस|बुखार|चक्कर|उल्टी|सूजन", value):
            return Intent.SYMPTOM_COMPLAINT
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

    def route(self, text: str) -> tuple[BreakerResult, Intent | None]:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        emergency = self.breaker.check(text)
        if emergency.triggered:
            return emergency, None
        try:
            return emergency, self.classifier.classify(text)
        except Exception:
            return emergency, Intent.UNKNOWN

    async def async_classify(self, text: str) -> Intent:
        if hasattr(self.classifier, "async_classify"):
            return await self.classifier.async_classify(text)
        return await asyncio.to_thread(self.classifier.classify, text)

    async def async_route(self, text: str) -> tuple[BreakerResult, Intent | None]:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        emergency = self.breaker.check(text)
        if emergency.triggered:
            return emergency, None
        try:
            return emergency, await self.async_classify(text)
        except Exception:
            return emergency, Intent.UNKNOWN


