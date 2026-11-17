"""Regression tests for live recovery: stale conversation ID, missing conversation,

metadata assertion (llm_provider, llm_model), and /ready boolean fields.
"""

import os
from typing import Any
import pytest
from httpx import ASGITransport, AsyncClient
from disha_core.main import create_app
from disha_core.models.schemas import ReadyResponse, TurnRequest, TurnState


@pytest.mark.asyncio
async def test_ready_endpoint_reports_required_booleans():
    """Verify /ready probe reports database, tables, groq_key_set, gemini_key_set, classifier_loaded."""
    app = create_app()
    # Mock classifier and pool
    class DummyClassifier:
        async def is_ready(self) -> bool:
            return True

    class DummyConn:
        async def fetchval(self, query: str) -> Any:
            return 1

    class DummyPool:
        def acquire(self):
            class Ctx:
                async def __aenter__(self):
                    return DummyConn()
                async def __aexit__(self, *args):
                    pass
            return Ctx()

    app.state.classifier_adapter = DummyClassifier()
    app.state.pool = DummyPool()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/ready")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["database"] is True
        assert "tables" in data
        assert "groq_key_set" in data
        assert "gemini_key_set" in data
        assert "classifier_loaded" in data


@pytest.mark.asyncio
async def test_response_metadata_includes_llm_provider_and_model():
    """Verify _response_metadata returns llm_provider and llm_model."""
    from disha_core.main import _response_metadata
    state = TurnState()
    state.llm_provider = "groq"
    state.llm_model = "qwen/qwen3.8-27b"
    meta = _response_metadata(state, conversation_id="conv-1234")
    assert meta["llm_provider"] == "groq"
    assert meta["llm_model"] == "qwen/qwen3.8-27b"
    assert meta["conversation_id"] == "conv-1234"


@pytest.mark.asyncio
async def test_missing_conversation_hydration_returns_clean_schema():
    """Verify get_active_conversation_with_messages returns empty structure when no conversation exists."""
    from disha_core.services.chat_service import get_active_conversation_with_messages
    class EmptyPool:
        def acquire(self):
            class Ctx:
                async def __aenter__(self):
                    class EmptyConn:
                        async def fetchrow(self, *args):
                            return None
                        async def fetch(self, *args):
                            return []
                    return EmptyConn()
                async def __aexit__(self, *args):
                    pass
            return Ctx()

    res = await get_active_conversation_with_messages(EmptyPool(), "patient_nonexistent")
    assert res["conversation_id"] is None
    assert res["messages"] == []


def test_system_prompt_forbids_support_fillers_and_premature_advice():
    """Verify system prompt enforces perceptive coaching without support clichés or premature advice."""
    from disha_core.llm.client import get_system_prompt
    prompt = get_system_prompt()
    assert "[P1]" in prompt
    assert "no support openers" in prompt
    assert "[P2]" in prompt
    assert "premature advice" in prompt
    assert "[F2]" in prompt
    assert "sharp, context-aware" in prompt
    assert len(prompt) // 4 <= 600


def test_classify_conversation_control_preserves_follow_up_on_answers():
    """Verify short replies or negations to assistant questions maintain follow-up permission."""
    from disha_core.harness.perception import classify_conversation_control

    # Standalone closing
    closing = classify_conversation_control("bye")
    assert closing.is_closing is True
    assert closing.follow_up_allowed is False

    # Standalone refusal
    refusal = classify_conversation_control("stop asking questions")
    assert refusal.follow_up_allowed is False

    # Short response answering prior assistant question
    history = [{"role": "assistant", "content": "Aapko koi BP ya diabetes ki problem hai?"}]
    for reply in ["no", "nahi", "haan", "okay", "don't know", "pata nahi"]:
        ctrl = classify_conversation_control(reply, history)
        assert ctrl.follow_up_allowed is True, f"Failed for reply: {reply}"


def test_verifier_accepts_rephrased_candidate_question():
    """Verify F6 check accepts naturally rephrased discovery candidate question."""
    from disha_core.harness.verifier import check_f6_question_requirement

    context = {
        "question_required": True,
        "discovery_candidate": {
            "target_field": "diagnosed_conditions",
            "question": "Aapko koi diagnosed health condition hai jaise diabetes ya high BP?",
        },
        "user_input": "Mujhe health plan chahiye",
    }
    # Naturally rephrased question sharing candidate terms
    response = "Bilkul, chaliye aapki health history samajhte hain. Kya aapko pehle se high BP ya diabetes ki problem hai?"
    violation = check_f6_question_requirement(response, context)
    assert violation is None

