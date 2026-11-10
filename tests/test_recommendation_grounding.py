"""End-to-end regression tests for knowledge-grounded coaching turns."""

from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

import disha_core.main as app_main
from disha_core.engine.retriever import RETRIEVE_SQL
from disha_core.main import _turn_sentences
from disha_core.models.schemas import TurnRequest, TurnState
from disha_core.pipeline.breaker import BreakerResult
from disha_core.pipeline.router import Intent
from disha_core.pipeline.validator import SentenceValidator, knowledge_unavailable_response
from disha_core.voice import VoiceSession


class FakeConnection:
    def __init__(self) -> None:
        self.pep: dict[str, Any] | None = {
            "hypertension_stage": None,
            "gym_clearance": None,
            "allowed_modalities": [],
            "restricted_modalities": [],
            "primary_focus": "",
            "secondary_focuses": [],
            "user_reported_concerns": "",
            "diagnosed_conditions": [],
            "language": "english",
            "dietary_preference": None,
        }
        self.meal: str | None = None
        self.meal_approved = True
        self.knowledge_rows: list[dict[str, Any]] = []
        self.retrieval_calls: list[tuple[Any, ...]] = []

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetchval(self, query: str, *args: Any) -> Any:
        return "ok"

    async def fetchrow(self, query: str, *args: Any) -> Any:
        if "FROM patient_pep" in query:
            return self.pep
        if "FROM patient_diet_schedules" in query:
            assert "approval_status = 'approved'" in query
            if self.meal_approved and self.meal is not None:
                return {"prescribed_items": self.meal}
        return None

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        if query == RETRIEVE_SQL:
            self.retrieval_calls.append(args)
            return list(self.knowledge_rows)
        return []

    async def execute(self, query: str, *args: Any) -> str:
        return "OK"


class FakePool:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def acquire(self) -> Any:
        connection = self.connection

        class Acquisition:
            async def __aenter__(self) -> FakeConnection:
                return connection

            async def __aexit__(self, *_: Any) -> None:
                return None

        return Acquisition()


class FakeRouter:
    def __init__(self) -> None:
        self.breaker = SimpleNamespace(check=self._check_breaker)

    @staticmethod
    def _check_breaker(text: str) -> BreakerResult:
        if "mock emergency" in text.casefold():
            return BreakerResult(
                triggered=True,
                category="test",
                response="Use the emergency response.",
            )
        return BreakerResult(triggered=False)

    async def async_route_decision(self, _: str) -> Any:
        return SimpleNamespace(
            breaker=BreakerResult(triggered=False),
            intent=Intent.GENERAL_COACHING,
            pep_risk=0,
            skip_retrieval=True,
        )


class PromptAwareLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def stream(self, prompt: str, messages: list[dict[str, str]] | None = None):
        self.prompts.append(prompt)

        async def generated():
            saved_meal = re.search(
                r'<DIET_SLOT meal="dinner" status="FOUND">(.*?)</DIET_SLOT>',
                prompt,
            )
            if saved_meal:
                yield f"Your saved dinner is {saved_meal.group(1)}."
                return

            if 'preference="Vegan"' in prompt:
                yield "Using your saved vegan preference with the retrieved guidance."
                return
            if 'preference="Non-Vegetarian"' in prompt:
                yield "Using your saved non-vegetarian preference with the retrieved guidance."
                return

            marker = next(
                (value for value in ("meal alpha", "meal beta", "exercise guidance") if value in prompt),
                "retrieved content",
            )
            yield f"The retrieved source contains {marker}."

        return generated()


def _knowledge_row(chunk_id: str, content: str, tag: str = "MEAL_GUIDANCE") -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "condition_tag": tag,
        "context_header": "Test-only evidence",
        "guideline_content": content,
        "source_citation": "synthetic test source",
        "required_remedy_tokens": [],
        "trigram_score": 0.9,
        "text_score": 0.3,
    }


def test_general_knowledge_query_requires_approved_records():
    assert "WHERE approval_status = 'approved'" in RETRIEVE_SQL


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "I don't have reliable guidance"),
        ("english", "I don't have reliable guidance"),
        ("hi", "भरोसेमंद स्वास्थ्य जानकारी"),
        ("hindi", "भरोसेमंद स्वास्थ्य जानकारी"),
        ("hinglish", "pakki health guidance"),
    ],
)
def test_knowledge_unavailable_response_uses_supported_language(language, expected):
    assert expected in knowledge_unavailable_response(language)


def test_chat_stream_and_voice_serialize_shared_turn_provenance():
    from fastapi import HTTPException
    from fastapi.testclient import TestClient

    connection = FakeConnection()
    connection.knowledge_rows = [_knowledge_row("kb-wire-1", "meal alpha")]
    app = app_main.create_app()
    app.state.pool = FakePool(connection)
    app.state.router = FakeRouter()
    app.state.llm = PromptAwareLLM()
    app.state.validator = SentenceValidator()
    app.state.conversation_history = {"user-wire": []}
    app.state.sync_history = False
    app.state.today_ist = lambda: "monday"
    app.state.ledger = None
    client = TestClient(app)

    def done_payload(body: str) -> dict[str, Any]:
        current_event = "message"
        for line in body.splitlines():
            if line.startswith("event: "):
                current_event = line[7:]
            elif line.startswith("data: ") and current_event == "done":
                return json.loads(line[6:])
        raise AssertionError("SSE done event missing")

    with patch.object(app_main, "_authenticated_patient", AsyncMock(return_value="user-wire")):
        json_response = client.post("/chat", json={"text": "What should I eat for dinner?"})
        assert json_response.status_code == 200
        json_body = json_response.json()
        assert json_body["evidence_ids"] == ["kb-wire-1"]
        assert json_body["retrieval_status"] == "retrieved"

        emergency_json = client.post("/chat", json={"text": "mock emergency"})
        assert emergency_json.json()["status"] == "triggered:test"
        assert emergency_json.json()["evidence_ids"] == []
        assert emergency_json.json()["retrieval_status"] == "not_requested"

        stream_response = client.post("/chat/stream", json={"text": "What should I eat for dinner?"})
        assert stream_response.status_code == 200
        stream_done = done_payload(stream_response.text)
        assert stream_done["evidence_ids"] == ["kb-wire-1"]
        assert stream_done["retrieval_status"] == "retrieved"

        emergency_response = client.post("/chat/stream", json={"text": "mock emergency"})
        emergency_done = done_payload(emergency_response.text)
        assert emergency_done == {
            "status": "triggered:test",
            "evidence_ids": [],
            "retrieval_status": "not_requested",
        }

    with patch.object(
        app_main,
        "_authenticated_patient",
        AsyncMock(side_effect=HTTPException(status_code=503)),
    ):
        unavailable_json = client.post("/chat", json={"text": "What should I eat for dinner?"})
        unavailable_response = client.post("/chat/stream", json={"text": "What should I eat for dinner?"})
    assert unavailable_json.json()["status"] == "deflected:db_unavailable"
    assert unavailable_json.json()["evidence_ids"] == []
    assert unavailable_json.json()["retrieval_status"] == "unavailable"
    assert unavailable_response.status_code == 200
    assert "Kripya thodi der baad koshish karein." in unavailable_response.text
    assert done_payload(unavailable_response.text) == {
        "status": "deflected:db_unavailable",
        "evidence_ids": [],
        "retrieval_status": "unavailable",
    }

    with (
        patch.object(app_main, "_authenticated_patient", AsyncMock(return_value="user-wire")),
        patch.object(VoiceSession, "speak", AsyncMock()),
    ):
        with client.websocket_connect("/voice?token=valid_tok") as websocket:
            websocket.send_json({"type": "text", "text": "What should I eat for dinner?"})
            frames: list[dict[str, Any]] = []
            while not any(frame.get("type") == "done" for frame in frames):
                frames.append(websocket.receive_json())

    voice_done = next(frame for frame in frames if frame.get("type") == "done")
    assert voice_done["evidence_ids"] == ["kb-wire-1"]
    assert voice_done["retrieval_status"] == "retrieved"


async def _run_turn(
    connection: FakeConnection,
    user_id: str,
    text: str,
) -> tuple[str, TurnState, PromptAwareLLM]:
    llm = PromptAwareLLM()
    app_state = SimpleNamespace(
        pool=FakePool(connection),
        router=FakeRouter(),
        llm=llm,
        validator=SentenceValidator(),
        conversation_history={user_id: []},
        sync_history=False,
        today_ist=lambda: "monday",
    )
    request = SimpleNamespace(app=SimpleNamespace(state=app_state))
    state = TurnState()
    sentences = [
        sentence
        async for sentence in _turn_sentences(
            request,
            user_id,
            TurnRequest(text=text),
            state,
        )
    ]
    return " ".join(sentences), state, llm


@pytest.mark.asyncio
async def test_dataset_updates_change_live_turn_and_provenance_without_code_changes():
    connection = FakeConnection()
    connection.knowledge_rows = [_knowledge_row("kb-meal-1", "meal alpha")]

    first, first_state, _ = await _run_turn(connection, "user-a", "What should I eat for dinner?")
    connection.knowledge_rows = [_knowledge_row("kb-meal-2", "meal beta")]
    second, second_state, _ = await _run_turn(connection, "user-a", "What should I eat for dinner?")

    assert "meal alpha" in first
    assert "meal beta" in second
    assert first_state.evidence_ids == ["kb-meal-1"]
    assert second_state.evidence_ids == ["kb-meal-2"]
    assert len(connection.retrieval_calls) == 2


@pytest.mark.asyncio
async def test_missing_knowledge_still_uses_the_coach_without_inventing_retrieval():
    connection = FakeConnection()

    response, state, llm = await _run_turn(connection, "user-a", "How much water should I drink?")

    assert "retrieved content" in response
    assert state.validator_status != "deflected:knowledge_unavailable"
    assert state.evidence_ids == []
    assert len(llm.prompts) == 1


@pytest.mark.asyncio
async def test_saved_dietary_preferences_are_passed_through_to_grounded_response():
    connection = FakeConnection()
    connection.knowledge_rows = [_knowledge_row("kb-meal-3", "general meal guidance")]
    connection.pep = {**(connection.pep or {}), "dietary_preference": "Vegan"}

    vegan_response, _, vegan_llm = await _run_turn(connection, "user-vegan", "What should I eat?")
    connection.pep = {**(connection.pep or {}), "dietary_preference": "Non-Vegetarian"}
    non_vegetarian_response, _, non_vegetarian_llm = await _run_turn(connection, "user-nonveg", "What should I eat?")

    assert "vegan preference" in vegan_response.lower()
    assert "non-vegetarian preference" in non_vegetarian_response.lower()
    assert 'preference="Vegan"' in vegan_llm.prompts[0]
    assert 'preference="Non-Vegetarian"' in non_vegetarian_llm.prompts[0]


@pytest.mark.asyncio
async def test_prescribed_meal_reads_current_approved_schedule_and_rejects_pending():
    connection = FakeConnection()
    connection.meal = "Saved meal A"
    first, first_state, first_llm = await _run_turn(connection, "user-a", "What is my prescribed dinner?")

    connection.meal = "Saved meal B"
    second, _, _ = await _run_turn(connection, "user-a", "What is my prescribed dinner?")
    connection.meal_approved = False
    pending, pending_state, pending_llm = await _run_turn(connection, "user-a", "What is my prescribed dinner?")

    assert "Saved meal A" in first
    assert "Saved meal B" in second
    assert first_state.evidence_ids == []
    assert first_llm.prompts
    assert "prescribed plan" in pending.lower()
    assert pending_state.validator_status == "rewritten:meal_not_found"
    assert pending_llm.prompts == []


@pytest.mark.asyncio
async def test_exercise_with_known_limitation_is_withheld_after_retrieval():
    connection = FakeConnection()
    connection.knowledge_rows = [_knowledge_row("kb-exercise-1", "exercise guidance", "EXERCISE_GUIDANCE")]

    response, state, llm = await _run_turn(
        connection,
        "user-knee",
        "What workout should I do? My knee hurts.",
    )

    assert "recommend nahi karungi" in response
    assert state.evidence_ids == ["kb-exercise-1"]
    assert state.validator_status == "deflected:exercise_suitability_uncertain"
    assert llm.prompts == []


@pytest.mark.asyncio
async def test_exercise_with_recorded_cardiac_condition_is_withheld_after_retrieval():
    connection = FakeConnection()
    connection.pep = {
        **(connection.pep or {}),
        "diagnosed_conditions": ["coronary artery disease"],
    }
    connection.knowledge_rows = [_knowledge_row("kb-exercise-cardiac", "exercise guidance", "EXERCISE_GUIDANCE")]

    response, state, llm = await _run_turn(connection, "user-cardiac", "What workout should I do?")

    assert "recommend nahi karungi" in response
    assert state.evidence_ids == ["kb-exercise-cardiac"]
    assert state.validator_status == "deflected:exercise_suitability_uncertain"
    assert llm.prompts == []


@pytest.mark.asyncio
async def test_personalized_exercise_is_not_recommended_with_missing_safety_context():
    connection = FakeConnection()
    connection.knowledge_rows = [_knowledge_row("kb-exercise-2", "exercise guidance", "EXERCISE_GUIDANCE")]

    response, state, llm = await _run_turn(connection, "new-user", "What workout should I do?")

    assert "exercise guidance" in response
    assert state.validator_status != "deflected:exercise_context_required"
    assert state.evidence_ids == ["kb-exercise-2"]
    assert len(llm.prompts) == 1
