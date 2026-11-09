"""Regression coverage for exercise safety without a static recommendation catalog."""
from disha_core.pep.exercise_engine import (
    SuitabilityCategory,
    evaluate_exercise_suitability,
    extract_patient_health_tags,
    format_personalised_exercise_advice,
)


def test_missing_knowledge_abstains_for_known_exercise() -> None:
    result = evaluate_exercise_suitability("brisk_walking")

    assert result.category == SuitabilityCategory.INSUFFICIENT_INFO
    assert result.alternatives == []
    assert result.modifications == []
    assert "approved exercise guidance" in format_personalised_exercise_advice(result)


def test_explicit_restriction_blocks_requested_exercise_without_alternative() -> None:
    result = evaluate_exercise_suitability(
        "heavy deadlifts",
        patient_pep={"restricted_modalities": ["heavy_deadlifts"]},
    )

    assert result.category == SuitabilityCategory.AVOID
    assert result.alternatives == []
    assert result.modifications == []


def test_acute_symptoms_require_assessment_without_exercise_suggestion() -> None:
    result = evaluate_exercise_suitability(
        "brisk_walking",
        reported_symptoms=["severe sharp chest pain"],
    )

    assert result.category == SuitabilityCategory.REQUIRES_CLINICAL_ASSESSMENT
    assert result.alternatives == []
    assert result.modifications == []


def test_patient_condition_and_limitation_tags_are_extracted() -> None:
    tags = extract_patient_health_tags(
        pep_data={"hypertension_stage": "stage 2"},
        diagnosed_conditions=["coronary artery disease"],
        reported_symptoms=["knee pain"],
        recent_injuries=["ankle sprain"],
    )

    assert {"hypertension_stage2", "cardiac_history", "knee_pain", "ankle_injury"} <= tags
