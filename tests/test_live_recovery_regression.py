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
