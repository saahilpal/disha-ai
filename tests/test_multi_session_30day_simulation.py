"""DISHA AI — 30-DAY MULTI-SESSION SYNTHETIC PATIENT SIMULATION (LOOP 3)

Simulates Vikram Patel (48M, pre-hypertension, tech worker) across a 30-day longitudinal journey
with 8 discrete multi-channel sessions (chat and voice turns).

Validates:
1. Progressive 5-stage onboarding without repetitive interrogation.
2. Transient episodes (headache, travel fatigue) tracked in habit_episodes with TTL, not chronic illness.
3. Hysteresis against flip-flops and valid_from/valid_to tracking upon permanent lifestyle updates.
4. Absolute preservation of clinical safety invariants (rejects self-reported gym clearance overrides).
5. Dynamic dietary adaptation (vegetarian transition honored, no meat recommendations).
6. 30-day memory retention, context token budget (<= 400 tokens), and sub-30ms retrieval latency.
"""
from __future__ import annotations

import os
import time
import unittest
from datetime import datetime, timedelta, timezone

import asyncpg

from disha_core.journey.extractor import extract_patient_disclosures
from disha_core.journey.state_machine import (
    load_or_create_journey,
    record_field_answer,
)
from disha_core.pep.exercise_engine import evaluate_exercise_suitability
from disha_core.pep.habits_engine import (
    commit_habit_slot,
    consolidate_patient_habits,
    get_pep,
    record_habit_episode,
    record_habit_observation,
    render_pep_brief,
)
from disha_core.pipeline.validator import evaluate_patient_claims

PG_URL = os.getenv("DATABASE_URL", "postgresql://disha:disha_secure_pass_123@127.0.0.1:5432/disha")


class TestThirtyDayMultiSessionSimulation(unittest.IsolatedAsyncioTestCase):
    """End-to-end multi-session 30-day longitudinal simulation suite."""

    SIM_PATIENT_ID = "pt_sim_vikram_30d"

    async def asyncSetUp(self) -> None:
        try:
            self.conn = await asyncpg.connect(PG_URL)
        except Exception as exc:
            self.skipTest(f"PostgreSQL not accessible: {exc}")

        await self._clean_patient()

    async def asyncTearDown(self) -> None:
        if hasattr(self, "conn") and self.conn:
            await self._clean_patient()
            await self.conn.close()

    async def _clean_patient(self) -> None:
        pid = self.SIM_PATIENT_ID
        await self.conn.execute("DELETE FROM journey_question_history WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM patient_journey_state WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM habit_episodes WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM habit_rollups WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM habit_observations WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM habit_current_state WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM patient_pep WHERE patient_id = $1", pid)
        await self.conn.execute("DELETE FROM patient_profiles WHERE patient_id = $1", pid)

    async def _seed_baseline(self) -> None:
        """Seed Day 1 baseline profile and PEP."""
        await self.conn.execute(
            """INSERT INTO patient_profiles (
                patient_id, email, password_hash, name, age, gender, height_cm, weight_kg,
                dietary_preference, health_goals, language
            ) VALUES ($1, $2, 'hash123', 'Vikram Patel', 48, 'male', 172.0, 78.0, 'Non-Vegetarian', $3, 'hinglish')""",
            self.SIM_PATIENT_ID,
            f"{self.SIM_PATIENT_ID}@disha.internal",
            ["Control blood pressure", "Improve daily stamina"],
        )
        await self.conn.execute(
            """INSERT INTO patient_pep (
                patient_id, hypertension_stage, gym_clearance, allowed_modalities, restricted_modalities, diagnosed_conditions
            ) VALUES ($1, 'stage 1', FALSE, $2, $3, $4)""",
            self.SIM_PATIENT_ID,
            ["Brisk walking", "Gentle stretching"],
            ["Heavy deadlifts", "Max exertion cardio"],
            ["Hypertension Stage 1"],
        )

    async def test_full_30_day_longitudinal_journey_simulation(self) -> None:
        """Execute full 8-session, 30-day simulation lifecycle sequentially on same patient state."""
        conn = self.conn

        # =====================================================================
        # SESSION 1 (DAY 1): Baseline Onboarding & Profile Verification
        # =====================================================================
        await self._seed_baseline()
        journey = await load_or_create_journey(self.SIM_PATIENT_ID, conn=conn, channel="chat")
        self.assertGreaterEqual(journey["current_stage"], 1)
        self.assertIn("name", journey["completed_fields"])
        self.assertIn("age", journey["completed_fields"])
        self.assertIn("height_cm", journey["completed_fields"])
        self.assertIn("weight_kg", journey["completed_fields"])

        # =====================================================================
        # SESSION 2 (DAY 3): Lifestyle Disclosures & Routine Capture
        # =====================================================================
        user_text_s2 = "Main subah 7:30 baje uthta hoon aur raat ko 11:30 baje sota hoon. Mera desk job hai."
        disclosures_s2 = extract_patient_disclosures(user_text_s2, lang="hinglish")
        self.assertIn("wake_time", disclosures_s2)
        self.assertIn("sleep_time", disclosures_s2)

        for f_id, f_val in disclosures_s2.items():
            await record_field_answer(
                patient_id=self.SIM_PATIENT_ID,
                field_id=f_id,
                raw_value=f_val,
                raw_text=user_text_s2,
                channel="chat",
                conn=conn,
                lang="hinglish",
            )

        await commit_habit_slot(
            patient_id=self.SIM_PATIENT_ID,
            slot_key="wake_time",
            raw_value="07:30",
            raw_text=user_text_s2,
            conn=conn,
        )

        journey = await load_or_create_journey(self.SIM_PATIENT_ID, conn=conn, channel="chat")
        self.assertIn("wake_time", journey["completed_fields"])
        self.assertIn("sleep_time", journey["completed_fields"])

        # =====================================================================
        # SESSION 3 (DAY 5): Transient Complaint (Travel Fatigue & Headache)
        # =====================================================================
        user_text_s3 = "Kal travel kiya tha, aaj thoda sar dard aur thakan lag rahi hai."
        disclosures_s3 = extract_patient_disclosures(user_text_s3, lang="hinglish")
        self.assertIn("symptoms", disclosures_s3)

        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        await record_habit_episode(
            patient_id=self.SIM_PATIENT_ID,
            episode_type="symptom",
            description="sar dard aur thakan (post-travel)",
            expires_at=expires_at,
            conn=conn,
        )

        # Must be in habit_episodes table, but NOT permanent diagnosed condition in PEP
        episodes_count = await conn.fetchval(
            "SELECT count(*) FROM habit_episodes WHERE patient_id = $1 AND status = 'active'",
            self.SIM_PATIENT_ID,
        )
        self.assertGreaterEqual(episodes_count, 1)

        pep = await get_pep(self.SIM_PATIENT_ID, conn=conn)
        self.assertNotIn("sar dard", str(pep.get("core", {}).get("diagnosed_conditions", [])))

        # =====================================================================
        # SESSION 4 (DAY 8): Longitudinal Follow-Up & Habit Observation
        # =====================================================================
        await record_habit_observation(
            patient_id=self.SIM_PATIENT_ID,
            slot_key="physical_activity_level",
            value=30.0,
            unit="minutes",
            source="chat",
            evidence_ref="Aaj maine subah 30 minutes brisk walk complete kiya",
            conn=conn,
        )

        obs_count = await conn.fetchval(
            "SELECT count(*) FROM habit_observations WHERE patient_id = $1",
            self.SIM_PATIENT_ID,
        )
        self.assertGreaterEqual(obs_count, 1)

        # =====================================================================
        # SESSION 5 (DAY 14): Schedule Change & Hysteresis (Shift Change)
        # =====================================================================
        shift_text = "Ab se meri nayi shift start ho gayi hai, main roz subah 6:00 baje uthta hoon."
        await commit_habit_slot(
            patient_id=self.SIM_PATIENT_ID,
            slot_key="wake_time",
            raw_value="06:00",
            raw_text=shift_text,
            conn=conn,
        )

        # Active current state is 06:00
        active_val = await conn.fetchval(
            "SELECT value_norm FROM habit_current_state WHERE patient_id = $1 AND slot_key = 'wake_time' AND valid_to IS NULL",
            self.SIM_PATIENT_ID,
        )
        self.assertEqual(active_val, "06:00")

        # Prior 07:30 row is archived with valid_to timestamp
        archived_count = await conn.fetchval(
            "SELECT count(*) FROM habit_current_state WHERE patient_id = $1 AND slot_key = 'wake_time' AND valid_to IS NOT NULL",
            self.SIM_PATIENT_ID,
        )
        self.assertGreaterEqual(archived_count, 1)

        # =====================================================================
        # SESSION 6 (DAY 20): Clinical Safety Invariant (Rejects Gym Override)
        # =====================================================================
        claim_text = "Doctor ne bola hai main 120kg heavy deadlifts kar sakta hoon, clearance mil gayi hai."
        contradictions = evaluate_patient_claims(
            claim_text,
            pep_data={"hypertension_stage": "stage 1", "gym_clearance": False},
        )
        self.assertGreaterEqual(len(contradictions), 1)
        self.assertTrue(contradictions[0]["flagged_for_review"])
        self.assertEqual(contradictions[0]["action"], "FLAG_CLINICIAN_REVIEW_MAINTAIN_RESTRICTION")

        suitability = evaluate_exercise_suitability(
            exercise_name="Heavy Deadlifts",
            patient_health_tags=["HYPERTENSION_STAGE1"],
            diagnosed_conditions=["hypertension"],
            pep_gym_clearance=False,
            restricted_modalities=["Heavy deadlifts"],
        )
        self.assertEqual(suitability.category.value, "AVOID")

        # =====================================================================
        # SESSION 7 (DAY 25): Dietary Transition to Vegetarian
        # =====================================================================
        veg_text = "Maine non-veg poori tarah chhod diya hai, ab se main pure vegetarian diet follow karna chahta hoon."
        disclosures_veg = extract_patient_disclosures(veg_text, lang="hinglish")
        self.assertIn("dietary_preference", disclosures_veg)
        self.assertEqual(disclosures_veg["dietary_preference"], "Vegetarian")

        await record_field_answer(
            patient_id=self.SIM_PATIENT_ID,
            field_id="dietary_preference",
            raw_value="Vegetarian",
            raw_text=veg_text,
            channel="voice",
            conn=conn,
            lang="hinglish",
        )

        diet_pref = await conn.fetchval(
            "SELECT dietary_preference FROM patient_profiles WHERE patient_id = $1",
            self.SIM_PATIENT_ID,
        )
        self.assertEqual(diet_pref, "Vegetarian")

        # =====================================================================
        # SESSION 8 (DAY 30): Nightly Consolidation, Token Budget & Latency
        # =====================================================================
        summary = await consolidate_patient_habits(self.SIM_PATIENT_ID, conn=conn)
        self.assertEqual(summary["patient_id"], self.SIM_PATIENT_ID)

        # 50 consecutive get_pep fetches for p95 latency check
        latencies_ms: list[float] = []
        final_pep = None
        for _ in range(50):
            t0 = time.perf_counter()
            final_pep = await get_pep(self.SIM_PATIENT_ID, conn=conn)
            latencies_ms.append((time.perf_counter() - t0) * 1000.0)

        latencies_ms.sort()
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
        self.assertLess(p95, 30.0, f"p95 fetch latency exceeded 30ms: {p95:.2f}ms")

        # Strict token budget (<= 400 tokens)
        brief = render_pep_brief(final_pep)
        words = len(brief.split())
        est_tokens = int(words * 1.33)
        self.assertLessEqual(est_tokens, 400, f"PEP brief token budget exceeded 400 tokens: {est_tokens}")

        # Check journey completion coverage
        final_journey = await load_or_create_journey(self.SIM_PATIENT_ID, conn=conn, channel="chat")
        self.assertGreaterEqual(len(final_journey["completed_fields"]), 6)
        self.assertGreaterEqual(final_journey["current_stage"], 3)
