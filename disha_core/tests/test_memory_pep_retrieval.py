"""Automated Verification Suite for Disha AI Memory, PEP, and Dataset Retrieval.

Tests:
1. Multi-turn conversation history persistence across consecutive turns.
2. Cross-session memory recall from PostgreSQL (surviving cache eviction / session resets).
3. PEP constraint injection and forbidden exercise rejection (cardiac / stage 2 HTN / restricted modalities).
4. Accurate dataset chunk retrieval for symptoms (bloating, acidity, knee pain) with deduplication and thresholding.
"""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dotenv import load_dotenv

from disha_core.engine.context_builder import (
    build_patient_context,
    render_context_xml,
    render_user_payload,
)
from disha_core.engine.normalizer import normalize
from disha_core.engine.retriever import retrieve_chunks
from disha_core.pipeline.validator import (
    PEP_REPLACEMENT,
    SentenceValidator,
)
from disha_core.services.chat_service import (
    load_conversation_history,
    load_patient_facts,
    persist_patient_disclosure,
    store_conversation_turn,
    store_patient_fact,
)

load_dotenv()


class TestPEPIntegrationAndRejection(unittest.TestCase):
    """Verify PEP permissions, XML constraint injection, and safety validator interception."""

    def setUp(self) -> None:
        self.validator = SentenceValidator()

    def test_pep_xml_rendering_with_cardiac_and_htn_constraints(self) -> None:
        context = {
            "pep": {
                "patient_id": "cardiac_pt_01",
                "hypertension_stage": "stage 2",
                "gym_clearance": False,
                "allowed_modalities": ["brisk_walking", "light_stretching"],
                "restricted_modalities": ["heavy_deadlifts", "hiit"],
                "diagnosed_conditions": ["coronary_artery_disease", "hypertension"],
                "primary_focus": "Heart Health",
                "language": "hinglish",
                "dietary_preference": "Vegetarian",
            },
            "diet_slot_xml": "",
        }
        xml = render_context_xml(context)

        # 1. PEP Permissions must reflect explicit values
        self.assertIn('<PEP_PERMISSIONS', xml)
        self.assertIn('gym_clearance="false"', xml)
        self.assertIn('hypertension_stage="stage 2"', xml)
        self.assertIn('coronary_artery_disease', xml)

        # 2. PEP Restriction Rules must be explicitly present and list forbidden modalities
        self.assertIn('<PEP_RESTRICTION_RULES', xml)
        self.assertIn('FORBIDDEN="heavy_deadlifts, hiit', xml)
        self.assertIn('heavy weightlifting', xml)
        self.assertIn('brisk_walking, light_stretching', xml)

    def test_cardiac_patient_forbidden_exercise_rejected(self) -> None:
        context = {
            "pep": {
                "patient_id": "pt_cardiac",
                "hypertension_stage": "stage 2",
                "gym_clearance": False,
                "allowed_modalities": ["brisk_walking", "yoga"],
                "restricted_modalities": ["heavy_deadlifts", "hiit"],
                "diagnosed_conditions": ["cardiac_arrest_history"],
            }
        }

        # Attempts to recommend or perform heavy weightlifting or deadlifts
        bad_sentences = [
            "Aap gym mein heavy weightlifting shuru kar sakte hain.",
            "Aaj 100kg deadlifts aur powerlifting kijiye.",
            "Aap 30 minute high intensity interval training hiit karein.",
            "Gym jaakar bench press aur heavy deadlifts lagayein.",
        ]

        for s in bad_sentences:
            res = self.validator.validate_sentence(s, context)
            self.assertEqual(res.status, "rewritten", f"Failed to rewrite: {s}")
            self.assertIn("pep_restriction", res.reasons)
            self.assertEqual(res.text, PEP_REPLACEMENT)

    def test_allowed_modalities_accepted_without_rejection(self) -> None:
        context = {
            "pep": {
                "patient_id": "pt_normal",
                "hypertension_stage": "normal",
                "gym_clearance": True,
                "allowed_modalities": ["brisk_walking", "yoga"],
                "restricted_modalities": ["heavy_deadlifts"],
            }
        }

        safe_sentence = "Aap roz subah 20 minute brisk walking aur halka yoga kar sakte hain."
        res = self.validator.validate_sentence(safe_sentence, context)
        self.assertEqual(res.status, "accepted")
        self.assertNotIn("pep_restriction", res.reasons)


class TestMemoryPersistenceAndRecall(unittest.IsolatedAsyncioTestCase):
    """Verify multi-turn history persistence and cross-session fact recall."""

    async def test_mock_multi_turn_history_persistence(self) -> None:
        """Verify that store_conversation_turn records turns and load_conversation_history retrieves them."""
        journal: list[dict[str, Any]] = []

        class MockConnection:
            async def fetchval(self, query: str, *args: Any) -> Any:
                return len(journal) - 1

            async def execute(self, query: str, *args: Any) -> None:
                if "INSERT INTO patient_turn_journal" in query:
                    speaker = "user" if "'user'" in query else "assistant"
                    journal.append({
                        "patient_id": args[0],
                        "session_id": args[1],
                        "turn_index": args[2],
                        "speaker": speaker,
                        "raw_utterance": args[3],
                    })

            async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
                limit = args[1]
                rows = journal[-limit:]
                return list(reversed(rows))

        conn = MockConnection()
        pid = "patient_turn_test_01"

        # Turn 1
        await store_conversation_turn(conn, pid, "I work night shifts (10 PM to 6 AM)", "Got it, I will adapt your meal schedule.")
        # Turn 2
        await store_conversation_turn(conn, pid, "What should I eat before my shift?", "Have a light protein meal around 8 PM.")

        # Load history
        history = await load_conversation_history(conn, pid, limit=6)
        self.assertEqual(len(history), 4)
        self.assertEqual(history[0]["role"], "user")
        self.assertIn("night shifts", history[0]["content"])
        self.assertEqual(history[1]["role"], "assistant")
        self.assertEqual(history[2]["role"], "user")
        self.assertIn("before my shift", history[2]["content"])
        self.assertEqual(history[3]["role"], "assistant")

    async def test_cross_session_memory_and_disclosure_recall(self) -> None:
        """Verify patient facts (e.g. night shift, food dislikes) are stored and injected into PATIENT_PROFILE."""
        facts_db: list[dict[str, Any]] = []

        class MockConnection:
            async def execute(self, query: str, *args: Any) -> None:
                if "UPDATE patient_temporal_facts" in query:
                    for f in facts_db:
                        if f["patient_id"] == args[0] and f["fact_key"] == args[1]:
                            f["epistemic_status"] = "superseded"
                elif "INSERT INTO patient_temporal_facts" in query:
                    facts_db.append({
                        "patient_id": args[0],
                        "category": args[1],
                        "fact_key": args[2],
                        "fact_value": args[3],
                        "epistemic_status": args[4],
                    })

            async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
                return [f for f in facts_db if f["patient_id"] == args[0] and f["epistemic_status"] == "active"]

        conn = MockConnection()
        pid = "pt_cross_session_99"

        # User discloses night shift and dislike for bitter gourd (karela)
        await persist_patient_disclosure(conn, pid, "Mera night shift hai aur mujhe karela bilkul pasand nahi.")

        active_facts = await load_patient_facts(conn, pid)
        self.assertTrue(any(f["fact_key"] == "shift_schedule" for f in active_facts))
        self.assertTrue(any("food_dislike" in f["fact_key"] for f in active_facts))

        # Context build with facts
        context = {
            "pep": {
                "patient_id": pid,
                "hypertension_stage": "normal",
                "gym_clearance": True,
                "allowed_modalities": ["walking"],
                "restricted_modalities": [],
            },
            "patient_facts": active_facts,
            "diet_slot_xml": "",
        }
        xml = render_context_xml(context)

        self.assertIn("<PATIENT_FACTS>", xml)
        self.assertIn('category="lifestyle"', xml)
        self.assertIn("Night shift", xml)
        self.assertIn('category="dietary_preference"', xml)
        self.assertIn("karela", xml.lower())


class TestDatasetRetrievalQuality(unittest.IsolatedAsyncioTestCase):
    """Verify vector / full-text retrieval from clinical_guideline_chunks."""

    async def test_retrieval_for_symptoms_bloating_acidity_knee_pain(self) -> None:
        """Verify accurate chunk retrieval, thresholding, and deduplication across symptoms."""
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            self.skipTest("DATABASE_URL not configured")

        try:
            import asyncpg
            conn = await asyncpg.connect(db_url)
        except Exception as exc:
            self.skipTest(f"PostgreSQL connection unavailable: {exc}")

        try:
            # 1. Bloating symptom query
            bloating_chunks = await retrieve_chunks(
                conn, "mujhe pet me bohot gas aur bloating ho rahi hai", limit=3
            )
            self.assertTrue(len(bloating_chunks) > 0, "No chunks returned for bloating")
            tags = [c["condition_tag"] for c in bloating_chunks]
            self.assertTrue(any("BLOAT" in t or "JEERA" in t or "HING" in t for t in tags), f"Unexpected tags: {tags}")

            # 2. Acidity symptom query
            acidity_chunks = await retrieve_chunks(
                conn, "khatti dakar aur seene me jalan acidity problem", limit=3
            )
            self.assertTrue(len(acidity_chunks) > 0, "No chunks returned for acidity")
            tags = [c["condition_tag"] for c in acidity_chunks]
            self.assertTrue(any("GERD" in t or "ACID" in t or "AMLA" in t for t in tags), f"Unexpected tags: {tags}")

            # 3. Knee pain symptom query
            knee_chunks = await retrieve_chunks(
                conn, "ghutno me dard hai chalne me knee pain", limit=3
            )
            self.assertTrue(len(knee_chunks) > 0, "No chunks returned for knee pain")
            tags = [c["condition_tag"] for c in knee_chunks]
            self.assertTrue(any("KNEE" in t or "SHALLAKI" in t or "PRASARINI" in t or "RASNA" in t for t in tags), f"Unexpected tags: {tags}")

            # 4. Verify Deduplication
            chunk_ids = [c["chunk_id"] for c in bloating_chunks]
            self.assertEqual(len(chunk_ids), len(set(chunk_ids)), "Duplicate chunk IDs found in retrieval")

            # 5. Irrelevant query should not retrieve random medical chunks with high confidence
            irrelevant_chunks = await retrieve_chunks(
                conn, "quantum computer graphics card python script", threshold=0.3, limit=3
            )
            self.assertEqual(len(irrelevant_chunks), 0, "Irrelevant query returned clinical chunks")

        finally:
            await conn.close()


class TestLivePostgresMemoryEndToEnd(unittest.IsolatedAsyncioTestCase):
    """Live end-to-end multi-turn persistence test using PostgreSQL."""

    async def test_live_multi_turn_consecutive_flow(self) -> None:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            self.skipTest("DATABASE_URL not configured")

        try:
            import asyncpg
            conn = await asyncpg.connect(db_url)
        except Exception as exc:
            self.skipTest(f"PostgreSQL connection unavailable: {exc}")

        test_pid = "pt_live_test_e2e_mem_123"

        try:
            # Clean initial test state
            await conn.execute("DELETE FROM patient_turn_journal WHERE patient_id = $1", test_pid)
            await conn.execute("DELETE FROM patient_temporal_facts WHERE patient_id = $1", test_pid)
            await conn.execute(
                """INSERT INTO patient_pep (patient_id, hypertension_stage, gym_clearance, allowed_modalities, restricted_modalities)
                   VALUES ($1, 'Stage 1', TRUE, ARRAY['walking', 'yoga'], ARRAY['heavy_deadlifts'])
                   ON CONFLICT (patient_id) DO UPDATE SET gym_clearance = TRUE""",
                test_pid,
            )

            # Turn 1: User states night shift
            turn1_user = "Main raat ki shift karta hoon aur dinner raat 2 baje leta hoon."
            turn1_assistant = "Samajh gayi, aapke shift schedule ke anusaar hum diet adjust karenge."
            await store_conversation_turn(conn, test_pid, turn1_user, turn1_assistant)
            await persist_patient_disclosure(conn, test_pid, turn1_user)

            # Turn 2: Follow-up question in the same session
            history_after_turn1 = await load_conversation_history(conn, test_pid, limit=6)
            self.assertEqual(len(history_after_turn1), 2)
            self.assertEqual(history_after_turn1[0]["content"], turn1_user)
            self.assertEqual(history_after_turn1[1]["content"], turn1_assistant)

            # Turn 2: User states dislike for karela
            turn2_user = "Mujhe karela bilkul pasand nahi hai, koi aur subzi batao."
            turn2_assistant = "Karela ki jagah aap ghiya ya tori le sakte hain."
            await store_conversation_turn(conn, test_pid, turn2_user, turn2_assistant)
            await persist_patient_disclosure(conn, test_pid, turn2_user)

            # Turn 3: Check memory across turns
            history_after_turn2 = await load_conversation_history(conn, test_pid, limit=6)
            self.assertEqual(len(history_after_turn2), 4)

            # Check patient facts stored
            facts = await load_patient_facts(conn, test_pid)
            self.assertTrue(any(f["fact_key"] == "shift_schedule" for f in facts))
            self.assertTrue(any("karela" in f["fact_value"].lower() for f in facts))

            # Simulate cross-session context build
            ctx = await build_patient_context(conn, test_pid, "monday", None, user_input="Subah kya khayein?")
            self.assertIn("patient_facts", ctx)
            self.assertIn("conversation_history", ctx)
            self.assertEqual(len(ctx["conversation_history"]), 4)

            xml = render_user_payload("Subah kya khayein?", ctx)
            self.assertIn("<PATIENT_FACTS>", xml)
            self.assertIn("Night shift", xml)
            self.assertIn("karela", xml.lower())

        finally:
            await conn.execute("DELETE FROM patient_turn_journal WHERE patient_id = $1", test_pid)
            await conn.execute("DELETE FROM patient_temporal_facts WHERE patient_id = $1", test_pid)
            await conn.execute("DELETE FROM patient_pep WHERE patient_id = $1", test_pid)
            await conn.close()


if __name__ == "__main__":
    unittest.main()
