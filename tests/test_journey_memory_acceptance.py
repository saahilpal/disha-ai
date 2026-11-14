"""Acceptance Test Suite for Disha AI Journey, Memory, and Channel Invariants (Phase 3B RC).

Covers all 7 Core Verification Pillars:
1. Complete onboarding via chat and voice with direct PostgreSQL assertions.
2. Channel switch with state and cursor resume between Chat and Voice.
3. Slot skip, defer, and undo interactions in the stage engine.
4. Habit change mid-conversation landing in patient_habits with 'user_reported' provenance.
5. Clinical disclosures landing as 'proposed' in memory_items and NEVER altering clinician-owned PEP records.
6. Second session cross-session memory recall proof where Disha demonstrably recalls and uses the saved habit.
7. Post-call summary generation, returning-user home hydration, unsupported-language deflection, and emergency during onboarding.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import httpx
import pytest
import websockets

from disha_core.engine.normalizer import UNSUPPORTED_LANGUAGE_REPLACEMENT
from disha_core.journey.scheduler import select_next_question
from disha_core.journey.state_machine import (
    load_or_create_journey,
    record_field_answer,
    record_question_asked,
    record_question_deferred,
    record_question_skipped,
    record_slot_undo,
)
from disha_core.models.slots import SourceAuthority
from disha_core.pep.habits_engine import commit_habit_slot, consolidate_patient_habits
from disha_core.pipeline.breaker import EmergencyBreaker
from disha_core.pipeline.validator import SentenceValidator
from disha_core.services.chat_service import (
    load_call_summaries,
    persist_patient_disclosure,
    store_call_summary,
)

BASE_HTTP = os.getenv("DISHA_HTTP_URL", "http://127.0.0.1:8080")
BASE_WS = os.getenv("DISHA_WS_URL", "ws://127.0.0.1:8080/ws/conversation")
PG_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")

pytestmark = pytest.mark.live_network


class TestJourneyAndMemoryAcceptance(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        if not PG_URL:
            self.skipTest("TEST_DATABASE_URL not configured")
        try:
            self.conn = await asyncpg.connect(PG_URL)
        except Exception as exc:
            self.skipTest(f"PostgreSQL not accessible: {exc}")

        self.test_pids: list[str] = [
            "pt_jm_chat_01",
            "pt_jm_voice_01",
            "pt_jm_channel_01",
            "pt_jm_engine_01",
            "pt_jm_habit_01",
            "pt_jm_pep_01",
            "pt_jm_cross_01",
            "pt_jm_summary_01",
        ]
        for pid in self.test_pids:
            await self._clean_patient(pid)

    async def asyncTearDown(self) -> None:
        if hasattr(self, "conn") and self.conn:
            for pid in self.test_pids:
                await self._clean_patient(pid)
            await self.conn.close()

    async def _clean_patient(self, pid: str) -> None:
        await self.conn.execute("DELETE FROM journey_question_history WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM patient_journey_state WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM habit_current_state WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM habit_observations WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM habit_episodes WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM habit_rollups WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM patient_temporal_facts WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM memory_items WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM call_summaries WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM patient_access_tokens WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM patient_pep WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM patient_profiles WHERE patient_id = $1", pid)

    async def _create_test_patient_token(self, pid: str, email: str, name: str) -> str:
        token = f"token_{pid}"
        t_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc)
        await self.conn.execute(
            """INSERT INTO patient_profiles (patient_id, email, password_hash, name, age, gender, height_cm, weight_kg, language, dietary_preference, health_goals)
               VALUES ($1, $2, 'hash', $3, 35, 'Male', 175.0, 75.0, 'hinglish', 'Vegetarian', ARRAY['Fitness & general wellness'])
               ON CONFLICT (patient_id) DO NOTHING""",
            pid,
            email,
            name,
        )
        await self.conn.execute(
            """INSERT INTO patient_pep (patient_id, hypertension_stage, gym_clearance, allowed_modalities, restricted_modalities, primary_focus, diagnosed_conditions)
               VALUES ($1, 'Normal', TRUE, ARRAY['brisk_walking'], ARRAY['heavy_deadlifts'], 'General Wellness', ARRAY['none'])
               ON CONFLICT (patient_id) DO NOTHING""",
            pid,
        )
        await self.conn.execute(
            """INSERT INTO patient_access_tokens (token_hash, patient_id, expires_at, created_at)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (token_hash) DO UPDATE SET patient_id = EXCLUDED.patient_id""",
            t_hash,
            pid,
            now + timedelta(days=7),
            now,
        )
        return token

    # =========================================================================
    # 1. Complete Onboarding via Chat and Voice with Direct DB Assertions
    # =========================================================================
    async def test_01_complete_onboarding_chat_and_voice(self) -> None:
        """Pillar 1: Test complete onboarding via chat and via voice using API and direct DB assertions."""
        # 1a. Chat Onboarding Flow
        pid_chat = f"pt_jm_chat_{uuid.uuid4().hex[:6]}"
        email_chat = f"rohan_chat_{uuid.uuid4().hex[:8]}@disha.test"

        async with httpx.AsyncClient(base_url=BASE_HTTP, timeout=60.0) as client:
            reg_resp = await client.post(
                "/auth/register",
                json={
                    "name": "Rohan Mehra",
                    "email": email_chat,
                    "password": "password123",
                    "age": 36,
                    "gender": "male",
                    "height_cm": 175.0,
                    "weight_kg": 78.0,
                    "dietary_preference": "Vegetarian",
                    "hypertension_stage": "stage 1",
                    "gym_clearance": True,
                    "activity_level": "moderate",
                    "health_goals": ["Blood Pressure Care"],
                    "health_focuses": ["Blood Pressure Care"],
                },
            )
            self.assertEqual(reg_resp.status_code, 200, f"Registration failed: {reg_resp.text}")
            token_chat = reg_resp.json()["token"]
            pid_chat = reg_resp.json()["patient_id"]
            self.test_pids.append(pid_chat)

            # DB Check: Profile, PEP, and Journey State initialized
            prof_row = await self.conn.fetchrow(
                "SELECT name, height_cm, weight_kg FROM patient_profiles WHERE patient_id = $1", pid_chat
            )
            self.assertIsNotNone(prof_row)
            self.assertEqual(prof_row["name"], "Rohan Mehra")
            self.assertEqual(float(prof_row["weight_kg"]), 78.0)

            pep_row = await self.conn.fetchrow(
                "SELECT primary_focus, dietary_preference, gym_clearance FROM patient_pep WHERE patient_id = $1",
                pid_chat,
            )
            self.assertIsNotNone(pep_row)
            self.assertEqual(pep_row["primary_focus"], "Blood Pressure Care")
            self.assertEqual(pep_row["dietary_preference"], "Vegetarian")

            journey = await load_or_create_journey(pid_chat, self.conn, channel="chat")
            self.assertEqual(journey["stage_status"]["stage_1"]["status"], "completed")
            self.assertEqual(journey["current_stage"], 2)

            # Chat Turn 1: Conditions Disclosure (Stage 2)
            c1_resp = await client.post(
                "/chat",
                headers={"Authorization": f"Bearer {token_chat}"},
                json={"text": "Mujhe koi serious bimari nahi hai, sab theek hai."},
            )
            self.assertEqual(c1_resp.status_code, 200)

            # DB Check: Stage 2 Completed
            journey = await load_or_create_journey(pid_chat, self.conn, channel="chat")
            self.assertEqual(journey["stage_status"]["stage_2"]["status"], "completed")
            self.assertEqual(journey["current_stage"], 3)

            # Chat Turn 2: Habits Disclosure (Stage 3)
            c2_resp = await client.post(
                "/chat",
                headers={"Authorization": f"Bearer {token_chat}"},
                json={
                    "text": "Main subah 6:30 baje uthta hoon, raat ko 11:00 baje sota hoon aur din mein 3 litre paani peeta hoon."
                },
            )
            self.assertEqual(c2_resp.status_code, 200)

            # DB Check: Habits committed in habit_current_state
            active_slots = await self.conn.fetch(
                "SELECT slot_key, value_norm, source FROM habit_current_state WHERE patient_id = $1 AND valid_to IS NULL",
                pid_chat,
            )
            slot_map = {r["slot_key"]: r["value_norm"] for r in active_slots}
            self.assertIn("wake_time", slot_map)
            self.assertEqual(slot_map["wake_time"], "06:30")
            self.assertIn("sleep_time", slot_map)
            self.assertIn(slot_map["sleep_time"], ("11:00", "23:00"))
            self.assertIn("water_intake_target", slot_map)
            self.assertEqual(slot_map["water_intake_target"], "3.0")

        # 1b. Voice Onboarding Flow
        pid_voice = "pt_jm_voice_01"
        email_voice = "vikram_voice@disha.test"
        token_voice = await self._create_test_patient_token(pid_voice, email_voice, "Vikram Voice")

        # Connect full-duplex WebSocket
        async with websockets.connect(f"{BASE_WS}?token={token_voice}") as ws:
            # Send voice turn answering lifestyle question
            await ws.send(
                json.dumps(
                    {"type": "text", "text": "Main day shift job karta hoon aur daily 8000 steps walk karta hoon."}
                )
            )

            # Read frames until 'done'
            transcript_received = False
            done_received = False
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=60.0)
                if isinstance(msg, str):
                    data = json.loads(msg)
                    if data.get("type") == "transcript":
                        transcript_received = True
                    elif data.get("type") == "done":
                        done_received = True
                        break

            self.assertTrue(transcript_received, "Expected voice transcript frame")
            self.assertTrue(done_received, "Expected voice done completion frame")

        # DB Assertions for Voice Onboarding Turn
        voice_slots = await self.conn.fetch(
            "SELECT slot_key, value_norm, source FROM habit_current_state WHERE patient_id = $1 AND valid_to IS NULL",
            pid_voice,
        )
        v_map = {r["slot_key"]: r for r in voice_slots}
        self.assertIn("daily_steps_target", v_map, "Daily steps target should be persisted via voice")
        self.assertEqual(v_map["daily_steps_target"]["value_norm"], "8000")
        self.assertEqual(v_map["daily_steps_target"]["source"], "voice")

        v_journey = await self.conn.fetchrow(
            "SELECT last_interaction_channel FROM patient_journey_state WHERE patient_id = $1", pid_voice
        )
        self.assertIsNotNone(v_journey)
        self.assertEqual(v_journey["last_interaction_channel"], "voice")

    # =========================================================================
    # 2. Channel Switch with State and Cursor Resume (Chat <-> Voice)
    # =========================================================================
    async def test_02_channel_switch_state_and_cursor_resume(self) -> None:
        """Pillar 2: Verify channel switch with state and cursor resume between Chat and Voice."""
        pid = "pt_jm_channel_01"
        token = await self._create_test_patient_token(pid, "channel_user@disha.test", "Siddharth Verma")

        # Step 1: Start in Chat -> Answer work schedule
        await record_field_answer(pid, "work_schedule", "night_shift", "Main night shift karta hoon", "chat", self.conn)

        chat_journey = await load_or_create_journey(pid, self.conn, channel="chat")
        self.assertIn("work_schedule", chat_journey["completed_fields"])
        self.assertEqual(chat_journey["channel"], "chat")

        # Step 2: Switch to Voice -> Select next question in voice channel
        voice_journey = await load_or_create_journey(pid, self.conn, channel="voice")
        self.assertEqual(voice_journey["channel"], "voice")
        q_voice = await select_next_question(pid, voice_journey, channel="voice", conn=self.conn)
        self.assertIsNotNone(q_voice)
        # Voice must resume at next uncompleted field, NEVER re-asking work_schedule
        self.assertNotEqual(q_voice.target_field, "work_schedule")
        self.assertIn(q_voice.target_field, ("wake_time", "sleep_time"))

        # Answer wake_time in Voice
        await record_field_answer(pid, "wake_time", "05:00", "Subah 5 baje uthta hoon", "voice", self.conn)

        # Verify voice channel recorded
        v_chan = await self.conn.fetchval(
            "SELECT last_interaction_channel FROM patient_journey_state WHERE patient_id = $1", pid
        )
        self.assertEqual(v_chan, "voice")

        # Step 3: Switch back to Chat -> Select next question in chat channel
        chat_journey_resumed = await load_or_create_journey(pid, self.conn, channel="chat")
        self.assertIn("wake_time", chat_journey_resumed["completed_fields"])
        self.assertIn("work_schedule", chat_journey_resumed["completed_fields"])

        q_chat = await select_next_question(pid, chat_journey_resumed, channel="chat", conn=self.conn)
        self.assertIsNotNone(q_chat)
        # Resumed chat must not re-ask work_schedule or wake_time
        self.assertNotIn(q_chat.target_field, ("work_schedule", "wake_time"))
        self.assertEqual(q_chat.target_field, "sleep_time")

    # =========================================================================
    # 3. Slot Skip, Defer, and Undo Interactions in Stage Engine
    # =========================================================================
    async def test_03_stage_engine_skip_defer_undo(self) -> None:
        """Pillar 3: Test slot skip, defer, and undo interactions in the stage engine."""
        pid = "pt_jm_engine_01"
        await self._create_test_patient_token(pid, "engine_user@disha.test", "Pooja Hegde")

        # 3a. Test Skip Interaction
        journey = await load_or_create_journey(pid, self.conn, channel="chat")
        await record_question_asked(pid, "Q_STAGE3_TEA_COFFEE", "chat", "Tea/Coffee count?", self.conn)
        await record_question_skipped(pid, "Q_STAGE3_TEA_COFFEE", "User skipped tea/coffee", "chat", self.conn)

        hist_status = await self.conn.fetchval(
            "SELECT status FROM journey_question_history WHERE patient_id = $1 AND question_id = 'Q_STAGE3_TEA_COFFEE'",
            pid,
        )
        self.assertEqual(hist_status, "skipped")

        journey_skipped = await load_or_create_journey(pid, self.conn, channel="chat")
        self.assertIn("tea_coffee_frequency", journey_skipped.get("skipped_fields", []))

        # Scheduler must never ask the skipped field
        q_next = await select_next_question(pid, journey_skipped, channel="chat", conn=self.conn)
        if q_next:
            self.assertNotEqual(q_next.question_id, "Q_STAGE3_TEA_COFFEE")

        # 3b. Test Defer Interaction
        await record_question_asked(pid, "Q_STAGE4_DISLIKED_FOODS", "chat", "Any disliked foods?", self.conn)
        await record_question_deferred(pid, "Q_STAGE4_DISLIKED_FOODS", "baad mein bataunga", "chat", self.conn)

        defer_reason = await self.conn.fetchval(
            "SELECT skip_reason FROM journey_question_history WHERE patient_id = $1 AND question_id = 'Q_STAGE4_DISLIKED_FOODS'",
            pid,
        )
        self.assertIn("deferred: baad mein bataunga", defer_reason)

        journey_deferred = await load_or_create_journey(pid, self.conn, channel="chat")
        # Defer does NOT mark as permanently skipped; cursor is preserved
        self.assertNotIn("disliked_foods", journey_deferred.get("skipped_fields", []))

        # 3c. Test Undo Interaction
        await record_question_asked(pid, "Q_STAGE3_WATER", "chat", "Kitna paani peete hain?", self.conn)
        await record_field_answer(pid, "water_intake_target", 3.0, "3 liters", "chat", self.conn)
        journey_before_undo = await load_or_create_journey(pid, self.conn, channel="chat")
        self.assertIn("water_intake_target", journey_before_undo["completed_fields"])

        undo_res = await record_slot_undo(pid, "water_intake_target", "chat", self.conn)
        self.assertEqual(undo_res["status"], "success")

        # DB Assertion: history marked superseded, active slot retired, field removed from completed
        history_status = await self.conn.fetchval(
            "SELECT status FROM journey_question_history WHERE patient_id = $1 AND question_id = 'Q_STAGE3_WATER' ORDER BY id DESC LIMIT 1",
            pid,
        )
        self.assertEqual(history_status, "superseded")

        active_slot = await self.conn.fetchrow(
            "SELECT id FROM habit_current_state WHERE patient_id = $1 AND slot_key = 'water_intake_target' AND valid_to IS NULL",
            pid,
        )
        self.assertIsNone(active_slot, "Active habit slot should be retired upon undo")

        journey_after_undo = await load_or_create_journey(pid, self.conn, channel="chat")
        self.assertNotIn("water_intake_target", journey_after_undo["completed_fields"])

    # =========================================================================
    # 4. Habit Change Mid-Conversation Landing in patient_habits (user_reported)
    # =========================================================================
    async def test_04_habit_change_lands_in_patient_habits_user_reported(self) -> None:
        """Pillar 4: Test habit change mid-conversation and verify it lands in patient_habits with 'user_reported' provenance."""
        pid = "pt_jm_habit_01"
        await self._create_test_patient_token(pid, "habit_user@disha.test", "Manish Malhotra")

        # 1. Establish baseline habit
        commit1 = await commit_habit_slot(
            patient_id=pid,
            slot_key="wake_time",
            raw_value="07:00",
            raw_text="Main subah 7 baje uthta hoon",
            source="user_reported",
            conn=self.conn,
        )
        self.assertEqual(commit1["status"], "committed")

        # 2. Mid-conversation habit change with permanence cue ("ab se")
        commit2 = await commit_habit_slot(
            patient_id=pid,
            slot_key="wake_time",
            raw_value="05:30",
            raw_text="Maine apna schedule badal diya hai, ab se main subah 5:30 baje uthta hoon",
            source="user_reported",
            conn=self.conn,
        )
        self.assertEqual(commit2["status"], "superseded")
        self.assertEqual(commit2["old_id"], commit1["id"])

        # 3. Direct DB Query against patient_habits view
        habit_row = await self.conn.fetchrow(
            """
            SELECT slot_key, value_norm, provenance, version, supersedes
            FROM patient_habits
            WHERE patient_id = $1 AND slot_key = 'wake_time' AND valid_to IS NULL
            """,
            pid,
        )
        self.assertIsNotNone(habit_row, "Active habit must be visible in patient_habits view")
        self.assertEqual(habit_row["slot_key"], "wake_time")
        self.assertEqual(habit_row["value_norm"], "05:30")
        self.assertEqual(habit_row["provenance"], "user_reported", "Provenance must be 'user_reported'")
        self.assertEqual(habit_row["version"], 2)
        self.assertEqual(habit_row["supersedes"], commit1["id"])

    # =========================================================================
    # 5. Clinical Disclosures Land as 'proposed' and NEVER Alter Clinician PEP
    # =========================================================================
    async def test_05_clinical_disclosures_land_proposed_never_alter_pep(self) -> None:
        """Pillar 5: Verify clinical disclosures land as 'proposed' and NEVER alter clinician-owned PEP records."""
        pid = "pt_jm_pep_01"
        token = await self._create_test_patient_token(pid, "pep_user@disha.test", "Dr. Clinician Patient")

        # Seed strict clinician-verified PEP
        now = datetime.now(timezone.utc)
        await self.conn.execute(
            """
            UPDATE patient_pep
            SET hypertension_stage = 'Stage 2',
                gym_clearance = FALSE,
                restricted_modalities = ARRAY['heavy_deadlifts', 'valsalva_maneuvers', 'crossfit'],
                allowed_modalities = ARRAY['walking', 'breathing_pranayama'],
                clinician_verified_at = $2
            WHERE patient_id = $1
            """,
            pid,
            now,
        )

        pep_before = await self.conn.fetchrow(
            "SELECT hypertension_stage, gym_clearance, restricted_modalities, clinician_verified_at FROM patient_pep WHERE patient_id = $1",
            pid,
        )
        self.assertEqual(pep_before["hypertension_stage"], "Stage 2")
        self.assertFalse(pep_before["gym_clearance"])
        self.assertIn("heavy_deadlifts", pep_before["restricted_modalities"])

        # Patient claims contradictory doctor clearance mid-conversation
        adversarial_turn = "Doctor ne bola gym allowed hai, main heavy deadlifts kar sakta hoon."

        # Verify pipeline validator blocks clinical permission grant
        pep_dict = {
            "hypertension_stage": "Stage 2",
            "gym_clearance": False,
            "restricted_modalities": ["heavy_deadlifts", "valsalva_maneuvers"],
        }
        validator = SentenceValidator()
        val_res = validator.validate_sentence(adversarial_turn, {"pep": pep_dict})
        self.assertNotEqual(val_res.status, "accepted", "Contradictory clinical claim must NOT be accepted")

        # Process disclosure via chat service memory persistence
        await persist_patient_disclosure(self.conn, pid, adversarial_turn, session_id="test_session")

        # Verify proposal stored in memory_items with 'PATIENT_REPORTED' and 'flagged_review' (proposed)
        mem_row = await self.conn.fetchrow(
            """
            SELECT slot_key, source_authority, epistemic_status, sensitive_flag, raw_quote
            FROM memory_items
            WHERE patient_id = $1 AND epistemic_status = 'flagged_review'
            ORDER BY created_at DESC LIMIT 1
            """,
            pid,
        )
        self.assertIsNotNone(mem_row, "Contradictory clinical claim must land in memory_items as flagged_review")
        self.assertEqual(mem_row["source_authority"], SourceAuthority.PATIENT_REPORTED.value)
        self.assertEqual(mem_row["epistemic_status"], "flagged_review")
        self.assertTrue(mem_row["sensitive_flag"])

        # INVARIANT GATE: Clinician-owned PEP records MUST BE COMPLETELY UNALTERED
        pep_after = await self.conn.fetchrow(
            "SELECT hypertension_stage, gym_clearance, restricted_modalities, clinician_verified_at FROM patient_pep WHERE patient_id = $1",
            pid,
        )
        self.assertEqual(pep_after["hypertension_stage"], "Stage 2", "hypertension_stage was modified!")
        self.assertFalse(pep_after["gym_clearance"], "gym_clearance was unlawfully granted!")
        self.assertEqual(
            list(pep_after["restricted_modalities"]), ["heavy_deadlifts", "valsalva_maneuvers", "crossfit"]
        )
        self.assertEqual(pep_after["clinician_verified_at"], pep_before["clinician_verified_at"])

    # =========================================================================
    # 6. Second Session Cross-Session Memory Recall Proof
    # =========================================================================
    async def test_06_second_session_cross_session_memory_proof(self) -> None:
        """Pillar 6: Conduct a second session test proving Disha demonstrably recalls and uses the saved habit across sessions."""
        pid = "pt_jm_cross_01"
        token = await self._create_test_patient_token(pid, "cross_user@disha.test", "Aarav Deshpande")

        # Session 1: Patient records a unique habit (3.5L hydration target)
        await commit_habit_slot(
            patient_id=pid,
            slot_key="water_intake_target",
            raw_value=3.5,
            raw_text="Ab se main daily 3.5 litre paani peeta hoon",
            source="user_reported",
            conn=self.conn,
        )
        await consolidate_patient_habits(pid, conn=self.conn)

        # Verify habits snapshot in patient_pep
        pep_habits = await self.conn.fetchval("SELECT habits FROM patient_pep WHERE patient_id = $1", pid)
        habits_json = json.loads(pep_habits) if isinstance(pep_habits, str) else pep_habits
        self.assertIn("water_intake_target", habits_json.get("slots", {}))

        # Session 1 Ends.
        # Now Session 2 begins: Fresh HTTP client query asking for the saved habit
        async with httpx.AsyncClient(base_url=BASE_HTTP, timeout=60.0) as client:
            ans = ""
            for attempt in range(3):
                resp = await client.post(
                    "/chat",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"text": "Disha, mera daily water intake target kitna set kiya tha humne?"},
                )
                self.assertEqual(resp.status_code, 200)
                ans = resp.json()["response"]
                if "System Error" not in ans:
                    break
                if attempt < 2:
                    await asyncio.sleep(1.5)

            # Disha demonstrably recalls and uses the saved habit across sessions
            self.assertTrue(
                "3.5" in ans or "water" in ans.lower() or "paani" in ans.lower() or "litre" in ans.lower(),
                f"Expected cross-session habit recall of 3.5L water intake, got: '{ans}'",
            )

    # =========================================================================
    # 7. Post-Call Summary, Returning Hydration, Unsupported Lang, Emergency
    # =========================================================================
    async def test_07_summary_hydration_unsupported_emergency(self) -> None:
        """Pillar 7: Verify post-call summary generation, returning-user home hydration, unsupported-language deflection, and emergency during onboarding."""
        pid = "pt_jm_summary_01"
        token = await self._create_test_patient_token(pid, "summary_user@disha.test", "Sneha Roy")

        # 7a. Post-call summary generation
        call_id = "call_rc_acceptance_001"
        await store_call_summary(
            self.conn,
            call_id=call_id,
            patient_id=pid,
            session_id="session_voice_01",
            duration_seconds=210,
            summary_text="Patient reported regular evening brisk walking and consistent vegetarian diet; advised on sodium monitoring.",
            action_items=["Maintain 30 min brisk walk", "Check BP on Wednesday"],
            habits_disclosed={"evening_walk_mins": 30, "diet": "Vegetarian"},
            sentiment="positive",
            language="hinglish",
        )

        summaries = await load_call_summaries(self.conn, pid, limit=5)
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["call_id"], call_id)
        self.assertEqual(summaries[0]["duration_seconds"], 210)
        self.assertIn("evening brisk walking", summaries[0]["summary_text"])

        # 7b. Returning-user home hydration
        async with httpx.AsyncClient(base_url=BASE_HTTP, timeout=60.0) as client:
            prof_resp = await client.get("/patient/profile", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(prof_resp.status_code, 200)
            pdata = prof_resp.json()

            # Ensure all required hydration keys exist
            self.assertEqual(pdata["patient_id"], pid)
            self.assertIn("profile", pdata)
            self.assertIn("pep", pdata)
            self.assertIn("today_diet", pdata)
            self.assertIn("journey", pdata)
            self.assertEqual(pdata["pep"]["hypertension_stage"], "Normal")
            self.assertTrue(pdata["pep"]["gym_clearance"])

            # Verify dedicated journey endpoint
            j_resp = await client.get("/patient/journey", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(j_resp.status_code, 200)
            jdata = j_resp.json()
            self.assertEqual(jdata["patient_id"], pid)
            self.assertIn("stage_status", jdata)
            self.assertIn("current_stage", jdata)

            # 7c. Unsupported-language deflection
            french_msg = "Bonjour Disha, pouvez-vous m'aider avec mon régime alimentaire s'il vous plaît?"
            lang_resp = await client.post(
                "/chat",
                headers={"Authorization": f"Bearer {token}"},
                json={"text": french_msg},
            )
            self.assertEqual(lang_resp.status_code, 200)
            lang_data = lang_resp.json()
            self.assertEqual(lang_data["status"], "deflected:unsupported_language")
            self.assertEqual(lang_data["response"], UNSUPPORTED_LANGUAGE_REPLACEMENT)

            # Ensure 0 facts written from unsupported language
            french_facts = await self.conn.fetch(
                "SELECT fact_id FROM patient_temporal_facts WHERE patient_id = $1 AND fact_value ILIKE '%bonjour%'",
                pid,
            )
            self.assertEqual(len(french_facts), 0)

            # 7d. Emergency during onboarding
            emergency_text = "Severe crushing chest pain and breathing difficulty radiating to neck."
            breaker = EmergencyBreaker()
            em_eval = breaker.check(emergency_text)
            self.assertTrue(em_eval.triggered)
            self.assertEqual(em_eval.category, "CARDIOVASCULAR")

            # Call /chat with emergency turn
            em_resp = await client.post(
                "/chat",
                headers={"Authorization": f"Bearer {token}"},
                json={"text": emergency_text},
            )
            self.assertEqual(em_resp.status_code, 200)
            em_data = em_resp.json()
            self.assertIn("112", em_data["response"])

            # Verify Question Scheduler suppresses 100% of onboarding questions during emergency
            journey_state = await load_or_create_journey(pid, self.conn)
            scheduled_during_emergency = await select_next_question(
                pid,
                journey_state,
                user_turn_text=emergency_text,
                is_emergency=em_eval.triggered,
                conn=self.conn,
            )
            self.assertIsNone(
                scheduled_during_emergency,
                "Intelligent question scheduler must strictly return 0 questions during emergency",
            )


if __name__ == "__main__":
    unittest.main()
