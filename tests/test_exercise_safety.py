from disha_core.pep.exercise_engine import evaluate_exercise_suitability as legacy_suitability
from disha_core.pep.exercise_safety import (
    SuitabilityCategory,
    evaluate_exercise_suitability,
    extract_patient_health_tags,
    format_personalised_exercise_advice,
)


def test_missing_exercise_knowledge_abstains_without_static_alternatives() -> None:
    result = evaluate_exercise_suitability("squats")

    assert result.category == SuitabilityCategory.INSUFFICIENT_INFO
    assert result.alternatives == []
    assert result.modifications == []
    assert "approved exercise guidance" in format_personalised_exercise_advice(result)


def test_recorded_restriction_withholds_that_exercise() -> None:
    result = evaluate_exercise_suitability(
        "heavy deadlifts",
        patient_pep={"restricted_modalities": ["heavy deadlifts"]},
    )

    assert result.category == SuitabilityCategory.AVOID
    assert result.alternatives == []


def test_safety_tags_preserve_known_user_limitations() -> None:
    tags = extract_patient_health_tags(
        reported_symptoms=["My knee hurts"],
        recent_injuries=["recent ankle sprain"],
    )

    assert "knee_pain" in tags
    assert "ankle_injury" in tags
    assert "physical_limitation" in tags


def test_safety_tags_recognize_coronary_condition() -> None:
    tags = extract_patient_health_tags(
        diagnosed_conditions=["coronary artery disease"],
    )

    assert "cardiac_history" in tags


def test_legacy_exercise_engine_import_is_fail_closed() -> None:
    result = legacy_suitability("walking")

    assert result.category == SuitabilityCategory.INSUFFICIENT_INFO
    assert not result.alternatives
