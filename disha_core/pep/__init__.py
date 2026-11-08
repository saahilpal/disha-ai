"""PEP Habits Scale Architecture and Personalised Exercise Engine."""
from __future__ import annotations

from disha_core.pep.exercise_engine import (
    ExerciseEvaluation,
    SuitabilityCategory,
    evaluate_exercise_suitability,
    format_personalised_exercise_advice,
)
from disha_core.pep.habits_engine import (
    commit_habit_slot,
    consolidate_patient_habits,
    detect_habit_signals,
    get_pep,
    record_habit_observation,
    render_pep_brief,
)

__all__ = [
    "ExerciseEvaluation",
    "SuitabilityCategory",
    "evaluate_exercise_suitability",
    "format_personalised_exercise_advice",
    "commit_habit_slot",
    "consolidate_patient_habits",
    "detect_habit_signals",
    "get_pep",
    "record_habit_observation",
    "render_pep_brief",
]
