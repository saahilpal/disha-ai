from disha_core.engine.context_builder import render_context_xml
from disha_core.journey.question_bank import QUESTION_BY_FIELD
from disha_core.journey.scheduler import _relevance_score


def test_discovery_candidate_is_intent_scoped_and_does_not_expose_stages() -> None:
    rendered = render_context_xml(
        {
            "journey_state": {
                "current_stage": 1,
                "stage_status": {"stage_1": {"missing_fields": ["height_cm"]}},
            },
            "discovery_candidate": {
                "target_field": "primary_health_goal",
                "question": "What is your main health goal right now?",
            },
        }
    )

    assert 'field="primary_health_goal"' in rendered
    assert "What is your main health goal" in rendered
    assert "current_stage" not in rendered
    assert "height_cm" not in rendered
    assert "checklist" in rendered


def test_discovery_relevance_can_surface_a_later_goal_without_stage_order() -> None:
    question = QUESTION_BY_FIELD["primary_health_goal"]
    assert _relevance_score(question, "I want to lose weight") > 0
