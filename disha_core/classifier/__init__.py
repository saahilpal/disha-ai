"""Disha AI Laya Classifier Integration Package."""

from __future__ import annotations

from disha_core.classifier.adapter import (
    CircuitBreakerOpenError,
    LayaClassificationResult,
    LayaClassifierAdapter,
)
from disha_core.classifier.retrain_oracle import (
    EvaluationMetrics,
    LayaPromotionOracle,
    PromotionDecision,
    PromotionReport,
    WilsonInterval,
    calculate_ece,
    calculate_wilson_interval,
)
from disha_core.classifier.review_queue import (
    ClinicianAnnotation,
    ModelDecisionPayload,
    ReviewItem,
    ReviewQueueManager,
    ReviewStatus,
    TriggerContextPayload,
    TriggerType,
    ZeroPHIScrubber,
)
from disha_core.classifier.schemas import CLINICAL_QUESTIONS, SCHEMA_VERSION

__all__ = [
    "LayaClassifierAdapter",
    "LayaClassificationResult",
    "CircuitBreakerOpenError",
    "CLINICAL_QUESTIONS",
    "SCHEMA_VERSION",
    # Review Queue & Zero-PHI
    "ReviewQueueManager",
    "ReviewItem",
    "TriggerType",
    "ReviewStatus",
    "ZeroPHIScrubber",
    "ClinicianAnnotation",
    "ModelDecisionPayload",
    "TriggerContextPayload",
    # Promotion Oracle
    "LayaPromotionOracle",
    "PromotionDecision",
    "PromotionReport",
    "EvaluationMetrics",
    "WilsonInterval",
    "calculate_wilson_interval",
    "calculate_ece",
]
