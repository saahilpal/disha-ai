from disha_core.services.patient_service import _welcome_question


def test_welcome_uses_existing_concern_before_goal():
    text = _welcome_question(
        {"language": "en", "health_goals": ["weight management"]},
        {"primary_focus": "weight management", "user_reported_concerns": "poor sleep"},
    )
    assert "poor sleep" in text
    assert "weight management matters" not in text
    assert text.count("?") == 1


def test_welcome_uses_goal_and_never_asks_for_it_again():
    text = _welcome_question({"language": "hinglish", "health_goals": ["BP control"]}, {})
    assert "BP control" in text
    assert "goal" not in text.lower()
    assert text.count("?") == 1


def test_welcome_falls_back_to_motivation_in_selected_language():
    text = _welcome_question({"language": "en", "health_goals": []}, {})
    assert text == "I’d like to understand what matters to you. What made you want to focus on your health at this point?"
