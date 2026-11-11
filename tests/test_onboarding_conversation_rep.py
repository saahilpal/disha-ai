"""Regression & Behavioral Test Suite for Onboarding State, Conversation Repetition, and Empathy.

Covers Tests A through J:
- Test A: Negative medical history ("nhi" -> saved as negative, never re-asked).
- Test B: Repeated meal request ("breakfast" -> guidance; "breakfast" again -> variety/alternatives).
- Test C: Simple acknowledgment ("okay" -> no repeated recipe or questions).
- Test D: Direct answer request ("nhi jo hai de do" -> direct guidance, zero preference questions).
- Test E: Previously collected info not re-asked.
- Test F: Hinglish & spelling variations parsed contextually.
- Test G: Cross-session persistence.
- Test H: Stage progression internal without UI leakage.
- Test I: Empathy & emotional awareness for stress/setbacks.
- Test J: Token-efficient system prompt discipline.
"""

from __future__ import annotations

import os
import unittest

import asyncpg

from disha_core.harness.planner import build_structured_plan
from disha_core.journey.extractor import extract_patient_disclosures
from disha_core.journey.question_bank import QUESTION_BY_FIELD
from disha_core.journey.scheduler import select_next_question
from disha_core.journey.state_machine import (
    load_or_create_journey,
    record_field_answer,
    record_question_asked,
    sync_known_fields_from_db,
)
from disha_core.llm.client import SYSTEM_PROMPT

PG_URL = os.getenv("DATABASE_URL", "postgresql://disha:disha_secure_pass_123@127.0.0.1:5432/disha")


class TestOnboardingConversationRepetition(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        try:
            self.conn = await asyncpg.connect(PG_URL)
        except Exception as exc:
            self.skipTest(f"PostgreSQL not accessible: {exc}")

        self.test_pid = "pt_onboarding_rep_test_01"
        await self._clean_patient(self.test_pid)

    async def asyncTearDown(self) -> None:
        if hasattr(self, "conn") and self.conn:
            await self._clean_patient(self.test_pid)
            await self.conn.close()

    async def _clean_patient(self, pid: str) -> None:
        await self.conn.execute("DELETE FROM journey_question_history WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM patient_journey_state WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM patient_pep WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM patient_profiles WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM habit_current_state WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM patient_temporal_facts WHERE patient_id = $1", pid)

    # --------------------------------------------------------------------------
    # Test A: Negative medical history ("nhi" -> saved as negative, never re-asked)
    # --------------------------------------------------------------------------
    async def test_a_negative_medical_history_never_reasked(self) -> None:
        # Step 1: Agent asks the conditions question
        q_def = QUESTION_BY_FIELD["diagnosed_conditions"]
        qid = q_def.question_id
        target = q_def.target_field
        await record_question_asked(
            patient_id=self.test_pid,
            question_id=qid,
            channel="chat",
            question_text="Kya aapko koi pehle se diagnosed medical condition hai?",
            conn=self.conn,
        )

        # Step 2: Patient answers "nhi"
        disclosures = extract_patient_disclosures("nhi", lang="hinglish", pending_field=target)
        self.assertEqual(disclosures, {"diagnosed_conditions": ["none"]})

        # Step 3: Record the disclosure
        res = await record_field_answer(
            patient_id=self.test_pid,
            field_id="diagnosed_conditions",
            raw_value=disclosures["diagnosed_conditions"],
            raw_text="nhi",
            channel="chat",
            conn=self.conn,
        )
        self.assertEqual(res["status"], "success")

        # Step 4: Verify journey state marks diagnosed_conditions as completed and answered_negatively
        journey = await load_or_create_journey(self.test_pid, self.conn)
        self.assertIn("diagnosed_conditions", journey["completed_fields"])
        self.assertEqual(journey["field_states"]["diagnosed_conditions"], "answered_negatively")
        self.assertIsNone(journey["pending_question"])

        # Step 5: Check next scheduled question: conditions question must NEVER be picked
        next_q = await select_next_question(
            patient_id=self.test_pid,
            journey_state=journey,
            user_turn_text="breakfast mein kya khana chahiye?",
            channel="chat",
            conn=self.conn,
        )
        if next_q:
            self.assertNotEqual(next_q.question_id, qid)
            self.assertNotEqual(next_q.target_field, "diagnosed_conditions")

    # --------------------------------------------------------------------------
    # Test B: Repeated meal request (variety instead of robotic duplicate)
    # --------------------------------------------------------------------------
    def test_b_repeated_meal_request_offers_alternatives(self) -> None:
        # First turn: user asks for breakfast
        ctx_turn1 = {
            "intent": "meal_query",
            "conversation_history": [
                {"role": "user", "content": "breakfast suggestions please"},
                {
                    "role": "assistant",
                    "content": "You can have vegetable oats porridge or a boiled egg with whole wheat toast.",
                },
            ],
            "has_history": True,
        }
        # Second turn: user again asks for breakfast
        plan = build_structured_plan("breakfast", context=ctx_turn1, intent="meal_query")
        self.assertIn("Offer fresh variety/alternatives instead of repeating past advice", plan.coach_moves)
        self.assertIn("repeating same recommendations", plan.things_to_avoid)

    # --------------------------------------------------------------------------
    # Test C: Simple acknowledgment still moves the conversation
    # --------------------------------------------------------------------------
    def test_c_simple_acknowledgment_requires_question(self) -> None:
        ctx = {
            "intent": "general_coaching",
            "has_history": True,
            "conversation_history": [
                {"role": "user", "content": "dinner mein kya khayein?"},
                {"role": "assistant", "content": "Moong dal khichdi ya dalia soup le sakte hain."},
            ],
        }
        plan = build_structured_plan("okay", context=ctx, intent="general_coaching")
        self.assertTrue(plan.question_required)
        self.assertIn("Acknowledge warmly and briefly", plan.coach_moves)

    # --------------------------------------------------------------------------
    # Test D: Direct answer request ("nhi jo hai de do")
    # --------------------------------------------------------------------------
    def test_d_direct_answer_request_gives_immediate_suggestion(self) -> None:
        ctx = {"intent": "meal_query", "has_history": True}
        plan = build_structured_plan("nhi jo hai de do", context=ctx, intent="meal_query")
        self.assertTrue(plan.question_required)
        self.assertIn("Give a concrete, practical suggestion immediately", plan.coach_moves)
        self.assertIn("asking more preference questions", plan.things_to_avoid)

    # --------------------------------------------------------------------------
    # Test E: Previously collected info not re-asked
    # --------------------------------------------------------------------------
    async def test_e_previously_collected_info_not_reasked(self) -> None:
        # Seed patient profile with name, age, dietary preference, and negative conditions
        await self.conn.execute(
            """INSERT INTO patient_profiles (patient_id, name, email, password_hash, age, dietary_preference, health_conditions)
               VALUES ($1, 'Aarav Sharma', 'aarav@test.com', 'dummy_hash', 28, 'vegetarian', $2)""",
            self.test_pid,
            ["none"],
        )
        journey = await load_or_create_journey(self.test_pid, self.conn)
        self.assertIn("name", journey["completed_fields"])
        self.assertIn("age", journey["completed_fields"])
        self.assertIn("dietary_preference", journey["completed_fields"])
        self.assertIn("diagnosed_conditions", journey["completed_fields"])

        # Scheduler must not pick any of these completed fields
        scheduled = await select_next_question(
            patient_id=self.test_pid,
            journey_state=journey,
            user_turn_text="hello",
            channel="chat",
            conn=self.conn,
        )
        if scheduled:
            self.assertNotIn(scheduled.target_field, {"name", "age", "dietary_preference", "diagnosed_conditions"})

    # --------------------------------------------------------------------------
    # Test F: Hinglish & spelling variations parsed contextually
    # --------------------------------------------------------------------------
    def test_f_hinglish_spelling_variations(self) -> None:
        # Negative condition responses
        d1 = extract_patient_disclosures("kuch ni hai sab theek hai", pending_field="diagnosed_conditions")
        self.assertEqual(d1.get("diagnosed_conditions"), ["none"])

        d2 = extract_patient_disclosures("bilkul nahi", pending_field="diagnosed_conditions")
        self.assertEqual(d2.get("diagnosed_conditions"), ["none"])

        d3 = extract_patient_disclosures("nahi koi dikkat nahi", pending_field="diagnosed_conditions")
        self.assertEqual(d3.get("diagnosed_conditions"), ["none"])

        # Weight goal disclosure with phonetic Hinglish
        d4 = extract_patient_disclosures("muhje lagra hai mera weight bhut bdh gya wazan kam karna hai")
        self.assertEqual(d4.get("primary_health_goal"), "weight_loss")

    # --------------------------------------------------------------------------
    # Test G: Cross-session persistence
    # --------------------------------------------------------------------------
    async def test_g_cross_session_persistence(self) -> None:
        # Session 1: Record field answer
        await record_field_answer(
            patient_id=self.test_pid,
            field_id="diagnosed_conditions",
            raw_value=["none"],
            raw_text="nhi",
            channel="chat",
            conn=self.conn,
        )

        # Simulate fresh session reload
        known = await sync_known_fields_from_db(self.test_pid, self.conn)
        self.assertEqual(known.get("diagnosed_conditions"), ["none"])

        fresh_journey = await load_or_create_journey(self.test_pid, self.conn)
        self.assertIn("diagnosed_conditions", fresh_journey["completed_fields"])
        self.assertEqual(fresh_journey["field_states"]["diagnosed_conditions"], "answered_negatively")

    # --------------------------------------------------------------------------
    # Test H: Stage progression internal without UI leakage
    # --------------------------------------------------------------------------
    def test_h_stage_progression_internal_and_ui_hidden(self) -> None:
        # Verify CSS sets chat-journey-banner and source-trace to display: none !important
        css_path = os.path.join(os.path.dirname(__file__), "..", "disha_core", "frontend", "style.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css_content = f.read()

        self.assertIn(".chat-journey-banner {\n  display: none !important;", css_content)
        self.assertIn(".source-trace {\n  display: none !important;", css_content)

        # Verify index.html does not render visible stage indicator
        html_path = os.path.join(os.path.dirname(__file__), "..", "disha_core", "frontend", "index.html")
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        self.assertNotIn("chat-stage-pill", html_content)
        self.assertIn("call-advisory-pill", html_content)

    # --------------------------------------------------------------------------
    # Test I: Empathy & Emotional Awareness for stress/setbacks
    # --------------------------------------------------------------------------
    def test_i_empathy_and_emotional_awareness(self) -> None:
        # User feeling stressed about weight loss stall
        plan = build_structured_plan(
            "weight nahi kam ho raha stress ho raha hai",
            context={"intent": "general_coaching", "has_history": True},
        )
        self.assertIn("Acknowledge struggle with deep empathy without guilt or blame", plan.goal)
        self.assertIn("Validate feelings with genuine empathy and care", plan.coach_moves)
        self.assertIn("judgment or guilt", plan.things_to_avoid)
        self.assertIn("cheerful toxic positivity", plan.things_to_avoid)
        self.assertTrue(plan.question_required)

        # User feeling guilty about a cheat meal
        plan_cheat = build_structured_plan(
            "aaj maine cheat meal kha liya bahut guilt feel ho raha hai",
            context={"intent": "general_coaching", "has_history": True},
        )
        self.assertIn("judgment or guilt", plan_cheat.things_to_avoid)
        self.assertTrue(plan_cheat.question_required)

    # --------------------------------------------------------------------------
    # Test J: Token-efficient system prompt discipline
    # --------------------------------------------------------------------------
    def test_j_token_efficient_system_prompt_discipline(self) -> None:
        from disha_core.config import get_settings
        from disha_core.llm.client import _LEGACY_SYSTEM_PROMPT

        if get_settings().behavior_spec_v1:
            self.assertIn("two to four useful sentences", SYSTEM_PROMPT)
            self.assertIn("Normal replies end with exactly one meaningful question", SYSTEM_PROMPT)
            self.assertIn("Selective empathy", SYSTEM_PROMPT)
        else:
            self.assertIn("RESPONSE LENGTH & TOKEN EFFICIENCY", _LEGACY_SYSTEM_PROMPT)
            self.assertIn("2 to 4 focused sentences", _LEGACY_SYSTEM_PROMPT)
            self.assertIn("EMPATHY, TONE & EMOTIONAL AWARENESS", _LEGACY_SYSTEM_PROMPT)
            self.assertIn("toxic positivity", _LEGACY_SYSTEM_PROMPT)
            self.assertIn("Never sound like a form-filling questionnaire", _LEGACY_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
