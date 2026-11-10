"""Deterministic exercise-risk tagging and fail-closed suitability checks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence


class SuitabilityCategory(str, Enum):
    SUITABLE = "SUITABLE"
    MODIFIED = "MODIFIED"
    AVOID = "AVOID"
    INSUFFICIENT_INFO = "INSUFFICIENT_INFO"
    REQUIRES_CLINICAL_ASSESSMENT = "REQUIRES_CLINICAL_ASSESSMENT"


@dataclass
class ExerciseEvaluation:
    exercise_name: str
    category: SuitabilityCategory
    reason: str
    modifications: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    caution_notes: str = ""
    clarification_question: str = ""
    source_citation: str = ""


def extract_patient_health_tags(
    pep_data: dict[str, Any] | None = None,
    reported_symptoms: Sequence[str] | None = None,
    physical_limitations: Sequence[str] | None = None,
    recent_injuries: Sequence[str] | None = None,
    **extra_tags: Any,
) -> set[str]:
    """Extract safety signals without generating exercise recommendations."""
    tags: set[str] = set()

    for key in ("patient_health_tags", "patient_tags", "tags"):
        raw_tags = extra_tags.get(key)
        if isinstance(raw_tags, (list, tuple, set)):
            tags.update(str(tag).lower() for tag in raw_tags)

    if pep_data:
        core = pep_data.get("core") if isinstance(pep_data.get("core"), dict) else pep_data
        hypertension = str(core.get("hypertension_stage", "")).lower()
        if "stage 2" in hypertension or "stage_2" in hypertension:
            tags.add("hypertension_stage2")
        elif "stage 1" in hypertension or "stage_1" in hypertension:
            tags.add("hypertension_stage1")

        if core.get("has_cardiac_history") or "cardiac" in str(core.get("conditions", "")).lower():
            tags.add("cardiac_history")

        for restriction in core.get("restricted_modalities") or ():
            normalized = str(restriction).lower()
            if "deadlift" in normalized or "heavy" in normalized:
                tags.add("heavy_deadlifts_restricted")
            if "valsalva" in normalized:
                tags.add("valsalva_restricted")

    for condition in extra_tags.get("diagnosed_conditions") or ():
        normalized = str(condition).lower()
        if "hypertension" in normalized or "high bp" in normalized:
            tags.add("hypertension_stage2" if "stage 2" in normalized else "hypertension_stage1")
        if re.search(
            r"\b(?:cardiac|heart|coronary|cad|angina|arrhythmia|myocardial)\b",
            normalized,
        ):
            tags.add("cardiac_history")

    for restriction in extra_tags.get("restricted_modalities") or ():
        normalized = str(restriction).lower()
        if "deadlift" in normalized or "heavy" in normalized:
            tags.add("heavy_deadlifts_restricted")

    symptom_text = " ".join(
        str(value).lower()
        for values in (reported_symptoms, physical_limitations, recent_injuries)
        for value in (values or ())
    )
    patterns = {
        "knee_pain": r"\b(?:knee|knees|ghutna|ghutne|patella|meniscus|acl)\b",
        "lower_back_pain": r"\b(?:lower back|back pain|kamar dard|lumbar|spine|slip disc|sciatica|reedh)\b",
        "shoulder_pain": r"\b(?:shoulder|shoulders|kandha|rotator cuff|impingement)\b",
        "ankle_injury": r"\b(?:ankle|ankles|heel|plantar|pair|pairon mein dard|takla)\b",
        "acute_severe_pain": r"\b(?:severe|acute|unbearable|very sharp|shiddat|bahut tez|tez dard|cannot walk)\b",
        "physical_limitation": (
            r"\b(?:recent surgery|surgery|operation|post.?operative|post.?op|"
            r"mobility difficulty|difficulty walking|walking difficulty|cannot walk|can't walk|"
            r"sprain|fracture|dislocation|recent injury|new injury)\b"
        ),
    }
    for tag, pattern in patterns.items():
        if re.search(pattern, symptom_text):
            tags.add(tag)
    return tags


def evaluate_exercise_suitability(
    exercise_name: str,
    patient_pep: dict[str, Any] | None = None,
    reported_symptoms: Sequence[str] | None = None,
    physical_limitations: Sequence[str] | None = None,
    recent_injuries: Sequence[str] | None = None,
    activity_level: str | None = None,
    available_equipment: str | None = None,
    location_preference: str | None = None,
    user_preferences: Sequence[str] | None = None,
    **kwargs: Any,
) -> ExerciseEvaluation:
    """Apply explicit risk blocks; otherwise require retrieved exercise evidence."""
    del activity_level, available_equipment, location_preference, user_preferences
    name = exercise_name.strip()
    tags = extract_patient_health_tags(
        pep_data=patient_pep,
        reported_symptoms=reported_symptoms,
        physical_limitations=physical_limitations,
        recent_injuries=recent_injuries,
        **kwargs,
    )
    if "acute_severe_pain" in tags:
        return ExerciseEvaluation(
            name,
            SuitabilityCategory.REQUIRES_CLINICAL_ASSESSMENT,
            "Severe or acute symptoms need appropriate professional assessment before exercise guidance.",
        )

    core = patient_pep.get("core", patient_pep) if patient_pep else {}
    restrictions = list(core.get("restricted_modalities") or ())
    restrictions.extend(kwargs.get("restricted_modalities") or ())
    normalized_name = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    if any(
        re.sub(r"[^a-z0-9]+", " ", str(item).lower()).strip() in normalized_name
        for item in restrictions
        if str(item).strip()
    ):
        return ExerciseEvaluation(
            name,
            SuitabilityCategory.AVOID,
            "This exercise conflicts with a restriction recorded in your profile.",
        )

    return ExerciseEvaluation(
        name,
        SuitabilityCategory.INSUFFICIENT_INFO,
        "I can't verify this exercise's suitability without relevant approved exercise guidance.",
        clarification_question="Please share any current symptoms, injuries, or clinician-recorded exercise restrictions.",
    )


def format_personalised_exercise_advice(evaluation: ExerciseEvaluation) -> str:
    """Format a safety result without supplying routines or alternative exercises."""
    parts = [evaluation.reason]
    if evaluation.clarification_question:
        parts.append(evaluation.clarification_question)
    return " ".join(parts)
