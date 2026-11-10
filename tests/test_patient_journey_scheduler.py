"""Comprehensive End-to-End Test Suite for 5-Stage Patient Journey and Intelligent Question Scheduler.

Verifies all 17 mandatory scenarios from Master Engineering Order:
1. Registration data deduplication (never ask what's known).
2. Multi-field extraction in a single turn.
3. Cross-channel continuity: Chat -> Voice.
4. Cross-channel continuity: Voice -> Chat.
5. Future stage information capture.
6. Field correction / update handling.
7. Contradiction detection & safety boundary.
8. Question skipping preservation.
9. Persistence across application restarts.
10. Long-term return without onboarding reset.
11. Transient symptom vs permanent diagnosis separation.
12. Emergency preemption over onboarding.
13. Dietary preference updates.
14. Optional question refusal handling.
15. Multi-field voice turn persistence.
16. Off-topic educational inquiry without forced questions.
17. Incomplete registration targeting only missing fields.
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone

import asyncpg

from disha_core.journey.extractor import extract_patient_disclosures
from disha_core.journey.scheduler import select_next_question
from disha_core.journey.state_machine import (
    load_or_create_journey,
    record_field_answer,
    record_question_asked,
    record_question_skipped,
    sync_known_fields_from_db,
)
from disha_core.pipeline.router import EmergencyBreaker

PG_URL = os.getenv("DATABASE_URL", "postgresql://disha:disha_secure_pass_123@127.0.0.1:5432/disha")


class TestPatientJourneyScheduler(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        try:
            self.conn = await asyncpg.connect(PG_URL)
        except Exception as exc:
            self.skipTest(f"PostgreSQL not accessible: {exc}")

        self.test_pid = "pt_journey_e2e_test_999"
        await self._clean_patient(self.test_pid)

    async def asyncTearDown(self) -> None:
        if hasattr(self, "conn") and self.conn:
            await self._clean_patient(self.test_pid)
            await self.conn.close()

    async def _clean_patient(self, pid: str) -> None:
        await self.conn.execute("DELETE FROM journey_question_history WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM patient_journey_state WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM habit_current_state WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM habit_observations WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM habit_episodes WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM habit_rollups WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM patient_temporal_facts WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM patient_pep WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM patient_profiles WHERE patient_id = $1", pid)

    # -------------------------------------------------------------------------
    # Scenario 1: User registers with basic profile; Chat never asks for them again
    # -------------------------------------------------------------------------
    async def test_01_registration_data_deduplication(self) -> None:
        # Pre-seed patient profile from registration
        await self.conn.execute(
            """INSERT INTO patient_profiles (patient_id, email, password_hash, name, age, gender, height_cm, weight_kg, language)
               VALUES ($1, 'test@disha.io', 'hash', 'Rajesh Kumar', 42, 'Male', 174.0, 78.5, 'hinglish')""",
            self.test_pid,
        )

        journey = await load_or_create_journey(self.test_pid, self.conn, channel="chat")
        self.assertEqual(journey["stage_status"]["stage_1"]["status"], "completed")
        self.assertGreaterEqual(journey["current_stage"], 2)

        # Scheduler must NOT ask any Stage 1 question
        q = await select_next_question(self.test_pid, journey, channel="chat", conn=self.conn)
        self.assertIsNotNone(q)
        self.assertNotEqual(q.stage, 1)
        self.assertEqual(q.stage, 2)
        self.assertEqual(q.target_field, "diagnosed_conditions")

    # -------------------------------------------------------------------------
    # Scenario 2: User provides several lifestyle details in one message
    # -------------------------------------------------------------------------
    async def test_02_multi_field_extraction_in_single_turn(self) -> None:
        msg = "I work night shifts, usually sleep around 9 in the morning, wake at 5 pm, and drink 3 liters of water."
        extracted = extract_patient_disclosures(msg)

        self.assertEqual(extracted.get("work_schedule"), "night_shift")
        self.assertEqual(extracted.get("sleep_time"), "09:00")
        self.assertEqual(extracted.get("wake_time"), "17:00")
        self.assertEqual(extracted.get("water_intake_target"), 3.0)

        # Persist all 4 fields
        for fid, val in extracted.items():
            await record_field_answer(self.test_pid, fid, val, msg, "chat", self.conn)

        known = await sync_known_fields_from_db(self.test_pid, self.conn)
        self.assertEqual(known.get("work_schedule"), "night_shift")
        self.assertEqual(known.get("sleep_time"), "09:00")
        self.assertEqual(known.get("wake_time"), "17:00")
        self.assertEqual(known.get("water_intake_target"), 3.0)

    # -------------------------------------------------------------------------
    # Scenario 3: User answers in chat and switches to voice; Voice never repeats it
    # -------------------------------------------------------------------------
    async def test_03_cross_channel_chat_to_voice_continuity(self) -> None:
        # Pre-seed Stage 1 & 2
        await self.conn.execute(
            """INSERT INTO patient_profiles (patient_id, email, password_hash, name, age, gender, height_cm, weight_kg)
               VALUES ($1, 't@d.io', 'h', 'Anita', 30, 'Female', 160.0, 58.0)""",
            self.test_pid,
        )
        await self.conn.execute(
            """INSERT INTO patient_pep (patient_id, diagnosed_conditions)
               VALUES ($1, ARRAY['none'])""",
            self.test_pid,
        )

        # User answers work schedule in chat
        await record_field_answer(
            self.test_pid, "work_schedule", "night_shift", "Main night shift karta hoon", "chat", self.conn
        )

        # Patient switches to voice call
        voice_journey = await load_or_create_journey(self.test_pid, self.conn, channel="voice")
        q = await select_next_question(self.test_pid, voice_journey, channel="voice", conn=self.conn)

        self.assertIsNotNone(q)
        # Must not ask work_schedule again
        self.assertNotEqual(q.target_field, "work_schedule")
        self.assertIn(q.target_field, ("wake_time", "sleep_time"))

    # -------------------------------------------------------------------------
    # Scenario 4: User answers in voice and returns to chat; Chat continues correctly
    # -------------------------------------------------------------------------
    async def test_04_cross_channel_voice_to_chat_continuity(self) -> None:
        # User answers sleep time in voice
        await record_field_answer(self.test_pid, "sleep_time", "23:00", "Raat 11 baje sota hoon", "voice", self.conn)

        # Patient returns to chat
        chat_journey = await load_or_create_journey(self.test_pid, self.conn, channel="chat")
        self.assertIn("sleep_time", chat_journey["completed_fields"])

        q = await select_next_question(self.test_pid, chat_journey, channel="chat", conn=self.conn)
        self.assertIsNotNone(q)
        self.assertNotEqual(q.target_field, "sleep_time")

    # -------------------------------------------------------------------------
    # Scenario 5: User provides future stage info; Captured immediately
    # -------------------------------------------------------------------------
    async def test_05_capture_future_stage_information_immediately(self) -> None:
        # Patient is in Stage 1, but discloses Stage 4 preferences
        msg = "Mera goal weight loss hai aur main pure vegetarian khana chahta hoon."
        extracted = extract_patient_disclosures(msg)

        self.assertEqual(extracted.get("primary_health_goal"), "weight_loss")
        self.assertEqual(extracted.get("dietary_preference"), "Vegetarian")

        # Record answers
        for fid, val in extracted.items():
            await record_field_answer(self.test_pid, fid, val, msg, "chat", self.conn)

        journey = await load_or_create_journey(self.test_pid, self.conn)
        self.assertIn("primary_health_goal", journey["completed_fields"])
        self.assertIn("dietary_preference", journey["completed_fields"])

    # -------------------------------------------------------------------------
    # Scenario 6: User corrects an existing PEP field; Record updated accurately
    # -------------------------------------------------------------------------
    async def test_06_user_corrects_existing_field(self) -> None:
        await self.conn.execute(
            """INSERT INTO patient_profiles (patient_id, email, password_hash, name, weight_kg)
               VALUES ($1, 't@d.io', 'h', 'Vikram', 82.0)""",
            self.test_pid,
        )

        # Correction
        correction_text = "Actually my current weight is 76kg now."
        extracted = extract_patient_disclosures(correction_text)
        self.assertEqual(extracted.get("weight_kg"), 76.0)

        await record_field_answer(
            self.test_pid, "weight_kg", extracted["weight_kg"], correction_text, "chat", self.conn
        )

        updated_wt = await self.conn.fetchval(
            "SELECT weight_kg FROM patient_profiles WHERE patient_id = $1", self.test_pid
        )
        self.assertEqual(float(updated_wt), 76.0)

    # -------------------------------------------------------------------------
    # Scenario 7: Contradictory information detected and clinical bounds protected
    # -------------------------------------------------------------------------
    async def test_07_contradictory_information_safety(self) -> None:
        # Pre-set severe hypertension with restricted deadlifts
        await self.conn.execute(
            """INSERT INTO patient_pep (patient_id, hypertension_stage, gym_clearance, restricted_modalities)
               VALUES ($1, 'Stage 2', FALSE, ARRAY['heavy_deadlifts', 'heavy_weightlifting'])""",
            self.test_pid,
        )

        from disha_core.pipeline.validator import SentenceValidator

        validator = SentenceValidator()

        # User claims they can do heavy deadlifts and gym
        user_claim = "Doctor ne bola restrictions khatam, main gym ja sakta hoon aur heavy deadlifts karunga."
        pep_ctx = {
            "pep": {
                "hypertension_stage": "Stage 2",
                "gym_clearance": False,
                "restricted_modalities": ["heavy_deadlifts"],
            }
        }

        res = validator.validate_sentence(user_claim, pep_ctx)
        self.assertNotEqual(res.status, "accepted")
        self.assertTrue(any("pep_restriction" in r or "llm_clinical_permission" in r for r in res.reasons))

    # -------------------------------------------------------------------------
    # Scenario 8: User skips a question; Skip state preserved
    # -------------------------------------------------------------------------
    async def test_08_skip_question_preservation(self) -> None:
        journey = await load_or_create_journey(self.test_pid, self.conn)
        await record_question_asked(self.test_pid, "Q_STAGE3_TEA_COFFEE", "chat", "Tea count?", self.conn)
        await record_question_skipped(
            self.test_pid, "Q_STAGE3_TEA_COFFEE", "User skipped optional question", "chat", self.conn
        )

        history_status = await self.conn.fetchval(
            "SELECT status FROM journey_question_history WHERE patient_id = $1 AND question_id = 'Q_STAGE3_TEA_COFFEE'",
            self.test_pid,
        )
        self.assertEqual(history_status, "skipped")

        j_state = await load_or_create_journey(self.test_pid, self.conn)
        self.assertIn("tea_coffee_frequency", j_state.get("skipped_fields", []))

    # -------------------------------------------------------------------------
    # Scenario 9: Application restart simulation; State fully preserved
    # -------------------------------------------------------------------------
    async def test_09_persistence_across_app_restart(self) -> None:
        # Record answers on current connection
        await record_field_answer(self.test_pid, "work_schedule", "day_shift", "Day shift", "chat", self.conn)
        await record_field_answer(self.test_pid, "wake_time", "06:30", "6:30 am", "chat", self.conn)

        # Simulate restart by establishing an entirely new database connection
        new_conn = await asyncpg.connect(PG_URL)
        try:
            rehydrated = await load_or_create_journey(self.test_pid, new_conn)
            self.assertIn("work_schedule", rehydrated["completed_fields"])
            self.assertIn("wake_time", rehydrated["completed_fields"])
        finally:
            await new_conn.close()

    # -------------------------------------------------------------------------
    # Scenario 10: User returns after several days; Resume without resetting
    # -------------------------------------------------------------------------
    async def test_10_resume_after_days_without_reset(self) -> None:
        # Pre-seed Stage 1 & 2 completed
        await self.conn.execute(
            """INSERT INTO patient_profiles (patient_id, email, password_hash, name, age, gender, height_cm, weight_kg)
               VALUES ($1, 't@d.io', 'h', 'Anita', 30, 'Female', 160.0, 58.0)""",
            self.test_pid,
        )
        await self.conn.execute(
            """INSERT INTO patient_pep (patient_id, diagnosed_conditions)
               VALUES ($1, ARRAY['none'])""",
            self.test_pid,
        )

        # Simulate interaction 10 days ago
        past_time = datetime.now(timezone.utc) - timedelta(days=10)
        await record_field_answer(self.test_pid, "work_schedule", "night_shift", "Night shift", "chat", self.conn)
        await self.conn.execute(
            "UPDATE patient_journey_state SET last_interaction_ts = $2, current_stage = 3 WHERE patient_id = $1",
            self.test_pid,
            past_time,
        )

        journey = await load_or_create_journey(self.test_pid, self.conn)
        self.assertGreaterEqual(journey["current_stage"], 3)
        self.assertIn("work_schedule", journey["completed_fields"])

    # -------------------------------------------------------------------------
    # Scenario 11: Transient symptoms are not classified as permanent diagnosis
    # -------------------------------------------------------------------------
    async def test_11_transient_symptom_vs_permanent_diagnosis(self) -> None:
        msg = "Aaj thoda bloating aur pet kharab lag raha hai subah se."
        extracted = extract_patient_disclosures(msg)

        self.assertIn("symptoms", extracted)
        self.assertNotIn("diagnosed_conditions", extracted)

        await record_field_answer(self.test_pid, "symptoms", extracted["symptoms"], msg, "chat", self.conn)

        # Verify habit_episodes has the transient symptom
        ep_count = await self.conn.fetchval(
            "SELECT COUNT(*) FROM habit_episodes WHERE patient_id = $1 AND episode_type = 'symptom_transient'",
            self.test_pid,
        )
        self.assertEqual(ep_count, 1)

        # Verify diagnosed_conditions in PEP is clean / empty
        pep_diag = await self.conn.fetchval(
            "SELECT diagnosed_conditions FROM patient_pep WHERE patient_id = $1",
            self.test_pid,
        )
        self.assertTrue(pep_diag is None or len(pep_diag) == 0)

    # -------------------------------------------------------------------------
    # Scenario 12: Emergency symptoms trigger immediate escalation, 0 questions
    # -------------------------------------------------------------------------
    async def test_12_emergency_preemption_over_onboarding(self) -> None:
        emergency_msg = "Severe crushing chest pain and sweating radiating to left arm."
        breaker = EmergencyBreaker()
        em = breaker.check(emergency_msg)
        self.assertTrue(em.triggered)

        journey = await load_or_create_journey(self.test_pid, self.conn)
        q = await select_next_question(
            self.test_pid,
            journey,
            user_turn_text=emergency_msg,
            is_emergency=em.triggered,
            conn=self.conn,
        )
        self.assertIsNone(q)  # Strict constraint: 0 onboarding questions during emergency

    # -------------------------------------------------------------------------
    # Scenario 13: User changes dietary preference; PEP updated
    # -------------------------------------------------------------------------
    async def test_13_dietary_preference_update(self) -> None:
        await self.conn.execute(
            """INSERT INTO patient_pep (patient_id, dietary_preference)
               VALUES ($1, 'Non-Vegetarian')""",
            self.test_pid,
        )

        msg = "Maine ab se non-veg chhod diya hai, main pure vegetarian khana chahta hoon."
        extracted = extract_patient_disclosures(msg)
        self.assertEqual(extracted.get("dietary_preference"), "Vegetarian")

        await record_field_answer(
            self.test_pid, "dietary_preference", extracted["dietary_preference"], msg, "chat", self.conn
        )

        updated_diet = await self.conn.fetchval(
            "SELECT dietary_preference FROM patient_pep WHERE patient_id = $1", self.test_pid
        )
        self.assertEqual(updated_diet, "Vegetarian")

    # -------------------------------------------------------------------------
    # Scenario 14: Optional question refusal handled without nagging
    # -------------------------------------------------------------------------
    async def test_14_refusal_of_optional_question_handled(self) -> None:
        await record_question_asked(self.test_pid, "Q_STAGE4_DISLIKED_FOODS", "chat", "Any disliked foods?", self.conn)
        await record_question_skipped(
            self.test_pid, "Q_STAGE4_DISLIKED_FOODS", "User declined to specify", "chat", self.conn
        )

        journey = await load_or_create_journey(self.test_pid, self.conn)
        q = await select_next_question(self.test_pid, journey, channel="chat", conn=self.conn)

        if q:
            self.assertNotEqual(q.question_id, "Q_STAGE4_DISLIKED_FOODS")

    # -------------------------------------------------------------------------
    # Scenario 15: User provides multiple answers during voice call
    # -------------------------------------------------------------------------
    async def test_15_multi_field_voice_call_persistence(self) -> None:
        voice_msg = "I walk 8000 steps daily and drink 2.5 liters of water."
        extracted = extract_patient_disclosures(voice_msg)

        self.assertEqual(extracted.get("daily_movement_level"), 8000)
        self.assertEqual(extracted.get("water_intake_target"), 2.5)

        for fid, val in extracted.items():
            await record_field_answer(self.test_pid, fid, val, voice_msg, "voice", self.conn)

        # Confirm both persisted into habit_current_state
        slots = await self.conn.fetch(
            "SELECT slot_key, value_norm, source FROM habit_current_state WHERE patient_id = $1",
            self.test_pid,
        )
        slot_map = {s["slot_key"]: s for s in slots}
        self.assertIn("daily_steps_target", slot_map)
        self.assertIn("water_intake_target", slot_map)
        self.assertEqual(slot_map["daily_steps_target"]["source"], "voice")

    # -------------------------------------------------------------------------
    # Scenario 16: Unrelated question answered without forcing questionnaire
    # -------------------------------------------------------------------------
    async def test_16_off_topic_query_answered_without_forced_questions(self) -> None:
        journey = await load_or_create_journey(self.test_pid, self.conn)
        off_topic_msg = "Jeera water peene se weight loss hota hai kya?"

        # Scheduler is called with is_off_topic_query=True
        q = await select_next_question(
            self.test_pid,
            journey,
            user_turn_text=off_topic_msg,
            is_off_topic_query=True,
            conn=self.conn,
        )
        self.assertIsNone(q)  # Must be None so model answers the question cleanly!

    # -------------------------------------------------------------------------
    # Scenario 17: Incomplete registration data targets only missing fields
    # -------------------------------------------------------------------------
    async def test_17_incomplete_registration_targets_only_missing(self) -> None:
        # Patient registered with name and age only (height and weight missing)
        await self.conn.execute(
            """INSERT INTO patient_profiles (patient_id, email, password_hash, name, age)
               VALUES ($1, 'inc@disha.io', 'h', 'Suresh', 29)""",
            self.test_pid,
        )

        journey = await load_or_create_journey(self.test_pid, self.conn)
        self.assertEqual(journey["current_stage"], 1)
        self.assertIn("name", journey["completed_fields"])
        self.assertIn("age", journey["completed_fields"])
        self.assertNotIn("height_cm", journey["completed_fields"])
        self.assertNotIn("weight_kg", journey["completed_fields"])

        q = await select_next_question(self.test_pid, journey, channel="chat", conn=self.conn)
        self.assertIsNotNone(q)
        # Must ask for missing fields (height or weight or gender), NOT name or age
        self.assertNotIn(q.target_field, ("name", "age"))
        self.assertIn(q.target_field, ("gender", "height_cm", "weight_kg"))

    # -------------------------------------------------------------------------
    # Scenario 18: Concurrent updates handling without state corruption
    # -------------------------------------------------------------------------
    async def test_18_concurrent_turn_updates_preserve_state(self) -> None:
        import asyncio

        conn2 = await asyncpg.connect(PG_URL)
        try:
            # Fire two simultaneous field records using separate connection handles
            t1 = record_field_answer(self.test_pid, "wake_time", "06:30", "wake at 6:30", "chat", self.conn)
            t2 = record_field_answer(self.test_pid, "sleep_time", "22:30", "sleep at 10:30", "voice", conn2)
            await asyncio.gather(t1, t2)
        finally:
            await conn2.close()

        journey = await load_or_create_journey(self.test_pid, self.conn)
        self.assertIn("wake_time", journey["completed_fields"])
        self.assertIn("sleep_time", journey["completed_fields"])

    # -------------------------------------------------------------------------
    # Scenario 19: Database write transient failure recovery
    # -------------------------------------------------------------------------
    async def test_19_transient_db_failure_graceful_handling(self) -> None:
        class FailingConnection:
            async def fetchrow(self, *args, **kwargs):
                raise ConnectionResetError("Simulated socket drop")

            async def execute(self, *args, **kwargs):
                raise ConnectionResetError("Simulated socket drop")

        # Must not raise unhandled crash; falls back gracefully
        journey = await load_or_create_journey("pt_transient_fail_patient", FailingConnection())
        self.assertEqual(journey["current_stage"], 1)
        self.assertEqual(journey["patient_id"], "pt_transient_fail_patient")


if __name__ == "__main__":
    unittest.main()
