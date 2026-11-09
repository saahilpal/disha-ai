"""Compatibility exports for the former static exercise engine."""
from disha_core.pep.exercise_safety import (
    ExerciseEvaluation,
    SuitabilityCategory,
    evaluate_exercise_suitability,
    extract_patient_health_tags,
    format_personalised_exercise_advice,
)

__all__ = [
    "ExerciseEvaluation",
    "SuitabilityCategory",
    "evaluate_exercise_suitability",
    "extract_patient_health_tags",
    "format_personalised_exercise_advice",
]
