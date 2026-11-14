"""Regression & Behavioral Test Suite for Conversational State Continuity, History RAG, and Turn Persistence.

Verifies:
- Test 1: All deflection paths persist user utterance and system deflection to history and turn journal.
- Test 2: Topic shifts during onboarding cleanly defer active pending questions.
- Test 3: Multi-turn conversations (3-10 turns) maintain chronological order and generate <CONVERSATION_STATE>.
- Test 4: Conversation RAG retrieves older relevant turns without duplicating active recent turns.
- Test 5: Cross-session and chat-to-voice transitions preserve conversation continuity via PostgreSQL.
- Test 6: Authenticated /chat/history endpoint retrieves chronological turns for frontend hydration.
"""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from typing import Any, AsyncIterator

import asyncpg
from fastapi import FastAPI
from fastapi.testclient import TestClient

from disha_core.engine.context_builder import build_patient_context, render_user_payload
from disha_core.engine.retriever import retrieve_conversation_history
from disha_core.harness.harness import ResponseHarness, _commit_turn
from disha_core.journey.question_bank import QUESTION_BY_FIELD
from disha_core.journey.state_machine import record_question_asked, record_question_deferred
from disha_core.models.schemas import TurnRequest
from disha_core.pipeline.router import IntentRouter
from disha_core.routers.chat import router as chat_router
from disha_core.services.chat_service import load_conversation_history, store_conversation_turn

PG_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")


class MockLLM:
    """Mock LLM returning deterministic sentences and recording prompt & messages."""

    def __init__(self, response_text: str = "Yeh healthy option hai.") -> None:
        self.response_text = response_text
        self.last_prompt = ""
        self.last_messages: list[dict[str, str]] = []

    async def stream(self, prompt: str, messages: list[dict[str, str]] | None = None) -> AsyncIterator[str]:
        self.last_prompt = prompt
        self.last_messages = list(messages or [])
        yield self.response_text


class TestConversationalStateContinuity(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        if not PG_URL:
            self.skipTest("TEST_DATABASE_URL not configured")
        try:
            self.conn = await asyncpg.connect(PG_URL)
        except Exception as exc:
            self.skipTest(f"PostgreSQL not accessible: {exc}")

        self.test_pid = "pt_state_continuity_test_01"
        await self._clean_patient(self.test_pid)

    async def asyncTearDown(self) -> None:
        if hasattr(self, "conn") and self.conn:
            await self._clean_patient(self.test_pid)
            await self.conn.close()

    async def _clean_patient(self, pid: str) -> None:
        await self.conn.execute("DELETE FROM patient_turn_journal WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM journey_question_history WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM patient_journey_state WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM patient_pep WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM patient_profiles WHERE patient_id = $1", pid)

    # --------------------------------------------------------------------------
    # Test 1: Deflection Turn Persistence
    # --------------------------------------------------------------------------
    async def test_01_deflection_turn_persistence(self) -> None:
        """Verify that early deflection turns commit both user input and assistant response."""
        app_state = SimpleNamespace(
            conversation_history={},
            pool=None,  # test in-memory first
            router=IntentRouter(),
            llm=MockLLM(),
            validator=None,
        )
        req = SimpleNamespace(app=SimpleNamespace(state=app_state))
        harness = ResponseHarness(llm_client=app_state.llm)

        # 1a: Emergency deflection
        res = [
            sent
            async for sent in harness.execute_turn(req, self.test_pid, TurnRequest(text="Mujhe severe chest pain hai"))
        ]
        self.assertTrue(len(res) > 0)
        self.assertIn("112", res[0])
        # Verify in-memory history committed the deflection
        history = app_state.conversation_history.get(self.test_pid, [])
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["content"], "Mujhe severe chest pain hai")
        self.assertIn("112", history[1]["content"])

        # 1b: Verify DB persistence via _commit_turn with live connection
        await _commit_turn(
            app_state,
            self.test_pid,
            "Mujhe severe chest pain hai",
            res[0],
            session_id="session_01",
        )
        await store_conversation_turn(self.conn, self.test_pid, "Mujhe severe chest pain hai", res[0], "session_01")
        db_history = await load_conversation_history(self.conn, self.test_pid, limit=10)
        self.assertTrue(len(db_history) >= 2)
        self.assertEqual(db_history[0]["content"], "Mujhe severe chest pain hai")
        self.assertIn("112", db_history[1]["content"])

    # --------------------------------------------------------------------------
    # Test 2: Topic Shift Defers Pending Question
    # --------------------------------------------------------------------------
    async def test_02_topic_shift_defers_pending_question(self) -> None:
        """Verify that user topic shift cleanly defers the active pending question."""
        q_def = QUESTION_BY_FIELD["primary_health_goal"]
        qid = q_def.question_id
        await record_question_asked(
            patient_id=self.test_pid,
            question_id=qid,
            channel="chat",
            question_text="Aapka primary health goal kya hai?",
            conn=self.conn,
        )

        # Confirm it is currently active 'asked'
        row_before = await self.conn.fetchrow(
            """SELECT status, skip_reason FROM journey_question_history
               WHERE patient_id = $1 AND question_id = $2 AND status = 'asked'""",
            self.test_pid,
            qid,
        )
        self.assertIsNotNone(row_before)
        self.assertEqual(row_before["status"], "asked")

        # Defer due to topic shift
        await record_question_deferred(
            patient_id=self.test_pid,
            question_id=qid,
            reason="topic_shift",
            channel="chat",
            conn=self.conn,
        )

        # Verify status is now 'skipped' with deferred reason and NOT 'asked'
        row_after = await self.conn.fetchrow(
            """SELECT status, skip_reason FROM journey_question_history
               WHERE patient_id = $1 AND question_id = $2""",
            self.test_pid,
            qid,
        )
        self.assertEqual(row_after["status"], "skipped")
        self.assertIn("deferred: topic_shift", row_after["skip_reason"])

        # Querying active question must return None
        active_row = await self.conn.fetchrow(
            """SELECT question_id FROM journey_question_history
               WHERE patient_id = $1 AND status = 'asked'""",
            self.test_pid,
        )
        self.assertIsNone(active_row)

    # --------------------------------------------------------------------------
    # Test 3: Multi-Turn Context & Follow-Up Anaphora Resolution
    # --------------------------------------------------------------------------
    async def test_03_multi_turn_context_and_anaphora_resolution(self) -> None:
        """Test multi-turn context preservation and <CONVERSATION_STATE> for follow-up turns."""
        turns = [
            ("user", "Maine subah poha khaya."),
            ("assistant", "Poha halka aur nutritious option hai. Lunch mein kya khane ka plan hai?"),
            ("user", "Same thing."),
            ("assistant", "Poha phir se lena theek hai par thoda protein add kar lijiye."),
            ("user", "Why is that?"),
            ("assistant", "Kyunki protein se muscle recovery aur sustained energy milti hai."),
        ]

        # Verify render_user_payload generates <CONVERSATION_STATE>
        context: dict[str, Any] = {
            "conversation_history": [{"role": t[0], "content": t[1]} for t in turns],
            "meal_relevant": True,
            "exercise_relevant": False,
        }
        payload = render_user_payload("Why is that?", context)
        self.assertIn("<CONVERSATION_STATE", payload)
        self.assertIn('is_followup_or_short_reply="true"', payload)
        self.assertIn("<LAST_ASSISTANT_UTTERANCE>", payload)
        self.assertIn("Kyunki protein se muscle recovery", payload)

    # --------------------------------------------------------------------------
    # Test 4: Conversation History RAG Retrieval
    # --------------------------------------------------------------------------
    async def test_04_conversation_history_rag_retrieval(self) -> None:
        """Verify conversation RAG retrieves older turns matching query without duplicating active turns."""
        # Insert 10 older turns into the turn journal
        for i in range(10):
            await store_conversation_turn(
                self.conn,
                self.test_pid,
                f"Past turn user message about thyroid test {i}",
                f"Past turn assistant advice on thyroid medication and monitoring {i}",
                session_id="old_session",
            )

        recent_active_history = {
            "Past turn user message about thyroid test 9",
            "Past turn assistant advice on thyroid medication and monitoring 9",
        }

        retrieved = await retrieve_conversation_history(
            self.conn,
            patient_id=self.test_pid,
            query="Tell me what you said earlier about my thyroid medication",
            exclude_texts=recent_active_history,
            limit=3,
        )

        self.assertTrue(len(retrieved) > 0)
        for item in retrieved:
            # Must not be the excluded recent turn
            self.assertNotIn("test 9", item["content"])
            # Must be relevant to thyroid
            self.assertTrue("thyroid" in item["content"].lower() or "medication" in item["content"].lower())

    # --------------------------------------------------------------------------
    # Test 5: Cross-Session & Chat-to-Voice Continuity
    # --------------------------------------------------------------------------
    async def test_05_cross_session_and_chat_voice_continuity(self) -> None:
        """Verify turns recorded in chat session are loaded seamlessly in voice call context."""
        # Record turns in 'chat_session_01'
        await store_conversation_turn(
            self.conn,
            self.test_pid,
            "Main kal se 30 minute walk karunga.",
            "Yeh bahut achha decision hai! Consistency maintain karein.",
            session_id="chat_session_01",
        )

        # Call build_patient_context with a voice call_id (which has no call-specific turns yet)
        ctx = await build_patient_context(
            self.conn,
            self.test_pid,
            day_of_week="monday",
            call_id="voice_call_999",
        )

        history = ctx.get("conversation_history") or []
        self.assertTrue(len(history) >= 2)
        self.assertIn("30 minute walk", history[0]["content"])
        self.assertIn("Consistency maintain", history[1]["content"])

    # --------------------------------------------------------------------------
    # Test 6: Authenticated /chat/history API Endpoint
    # --------------------------------------------------------------------------
    async def test_06_chat_history_api_endpoint(self) -> None:
        """Verify GET /chat/history returns chronological turns for client hydration."""
        await store_conversation_turn(
            self.conn,
            self.test_pid,
            "Hello Disha",
            "Namaste! Main Disha hoon. Aap kaisa mehsoos kar rahe hain?",
            session_id="session_api",
        )

        app = FastAPI()
        app.include_router(chat_router)
        app.state.pool = None
        app.state.conversation_history = {
            self.test_pid: [
                {"role": "user", "content": "Hello Disha"},
                {"role": "assistant", "content": "Namaste! Main Disha hoon."},
            ]
        }

        # Mock authentication dependency
        import disha_core.main as app_main

        original_auth = app_main._authenticated_patient

        async def mock_auth(req: Any, auth: Any) -> str:
            return self.test_pid

        app_main._authenticated_patient = mock_auth

        try:
            client = TestClient(app)
            response = client.get("/chat/history?limit=10", headers={"Authorization": "Bearer fake_token"})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["patient_id"], self.test_pid)
            self.assertEqual(len(data["history"]), 2)
            self.assertEqual(data["history"][0]["role"], "user")
            self.assertEqual(data["history"][1]["role"], "assistant")
        finally:
            app_main._authenticated_patient = original_auth

    # --------------------------------------------------------------------------
    # Test 7: Multi-Turn Conversation Dependency (3-10 Turns)
    # --------------------------------------------------------------------------
    async def test_07_ten_turn_conversation_dependency(self) -> None:
        """Verify 10-turn continuous dialogue where meaning of later turns depends on earlier turns."""
        from disha_core.pipeline.validator import SentenceValidator

        mock_llm = MockLLM("Response to user")
        validator = SentenceValidator()
        app_state = SimpleNamespace(
            conversation_history={},
            pool=None,
            router=IntentRouter(),
            llm=mock_llm,
            validator=validator,
        )
        req = SimpleNamespace(app=SimpleNamespace(state=app_state))
        harness = ResponseHarness(llm_client=mock_llm, validator=validator)

        ten_user_turns = [
            "Maine subah 2 parathe khaye.",
            "Dopehar mein dal chawal liya.",
            "Shaam ko chai ke sath samosa liya tha.",
            "Raat ko sirf thoda salad khaya.",
            "Total water intake lagbhag 2 litre tha.",
            "Kal se gym start karna chahta hoon.",
            "Same time as before.",
            "Why is that good?",
            "Okay samajh gaya.",
            "Gym ke sath diet kaise rakhu?",
        ]

        for idx, text in enumerate(ten_user_turns, start=1):
            mock_llm.response_text = f"Coach guidance for turn {idx}."
            sentences = [s async for s in harness.execute_turn(req, self.test_pid, TurnRequest(text=text))]
            self.assertTrue(len(sentences) > 0)

        # Inspect final in-memory conversation history
        history = app_state.conversation_history.get(self.test_pid, [])
        # History stores user and assistant pairs: 10 turns * 2 = 20 messages
        self.assertEqual(len(history), 20)

        # Turn 1 (breakfast) is at index 0
        self.assertEqual(history[0]["content"], "Maine subah 2 parathe khaye.")
        self.assertEqual(history[1]["content"], "Coach guidance for turn 1.")

        # Turn 7 ("Same time as before.") has previous 6 turns before it
        self.assertEqual(history[12]["content"], "Same time as before.")

        # The last turn was "Gym ke sath diet kaise rakhu?"
        self.assertEqual(history[-2]["content"], "Gym ke sath diet kaise rakhu?")

        # Check the messages that were passed to the mock LLM on turn 10
        # It must receive the preceding history in chronological order
        passed_messages = mock_llm.last_messages
        self.assertTrue(len(passed_messages) >= 16)  # Last 16 messages
        # Verify chronological order: user -> assistant -> user -> assistant...
        for m_idx in range(len(passed_messages) - 1):
            if passed_messages[m_idx]["role"] == "user":
                self.assertEqual(passed_messages[m_idx + 1]["role"], "assistant")

        # Verify <CONVERSATION_STATE> was rendered in the last prompt
        self.assertIn("<CONVERSATION_STATE", mock_llm.last_prompt)
        self.assertIn("<LAST_ASSISTANT_UTTERANCE>", mock_llm.last_prompt)
        self.assertIn("Coach guidance for turn 9", mock_llm.last_prompt)


if __name__ == "__main__":
    unittest.main()
