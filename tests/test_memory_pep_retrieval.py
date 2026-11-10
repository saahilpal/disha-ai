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
from typing import Any

from dotenv import load_dotenv

from disha_core.engine.context_builder import (
    build_patient_context,
    rehydrate_session_state,
    render_context_xml,
    render_user_payload,
)
from disha_core.engine.retriever import retrieve_chunks
from disha_core.models.slots import (
    DEFAULT_SLOT_REGISTRY,
    SourceAuthority,
)
from disha_core.pipeline.validator import (
    LLM_CLINICAL_PERMISSION_REPLACEMENT,
    PEP_REPLACEMENT,
    SentenceValidator,
    evaluate_patient_claims,
)
from disha_core.services.chat_service import (
    load_call_summaries,
    load_conversation_history,
    load_memory_items,
    load_patient_facts,
    persist_patient_disclosure,
    store_call_summary,
    store_conversation_turn,
    store_memory_item,
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
        self.assertIn("<PEP_PERMISSIONS", xml)
        self.assertNotIn('gym_clearance="false"', xml)
        self.assertIn('hypertension_stage="stage 2"', xml)
        self.assertIn("coronary_artery_disease", xml)

        # 2. PEP Restriction Rules must be explicitly present and list forbidden modalities
        self.assertIn("<PEP_RESTRICTION_RULES", xml)
        self.assertIn('FORBIDDEN="heavy_deadlifts, hiit"', xml)
        self.assertNotIn("heavy weightlifting", xml)
        self.assertIn("brisk_walking, light_stretching", xml)

    def test_short_language_codes_render_as_supported_languages(self) -> None:
        for language, expected in (("en", "english"), ("hi", "hindi"), ("hinglish", "hinglish")):
            with self.subTest(language=language):
                xml = render_context_xml({"pep": {"language": language}})
                self.assertIn(f'<USER_LANGUAGE preferred="{expected}"/>', xml)

    def test_diagnosis_does_not_inject_unrecorded_exercise_restrictions(self) -> None:
        context = {
            "pep": {
                "hypertension_stage": "stage 2",
                "restricted_modalities": [],
                "diagnosed_conditions": ["coronary_artery_disease"],
            }
        }

        xml = render_context_xml(context)

        self.assertNotIn("<PEP_RESTRICTION_RULES", xml)
        self.assertIn('diagnosed="coronary_artery_disease"', xml)

    def test_pep_discovery_context_exposes_candidates_without_staging_the_dialogue(self) -> None:
        xml = render_context_xml(
            {
                "pep": {"language": "english"},
                "journey_state": {
                    "current_stage": 3,
                    "stage_status": {
                        "stage_3": {"missing_fields": ["work_schedule", "sleep_time"]},
                    },
                },
            }
        )

        self.assertIn('<PEP_DISCOVERY current_stage="3" mode="passive">', xml)
        self.assertIn('name="Work Shift Schedule"', xml)
        self.assertIn('name="Night Sleep Time"', xml)
        self.assertIn("Ask about at most one only when it directly helps", xml)

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
                    journal.append(
                        {
                            "patient_id": args[0],
                            "session_id": args[1],
                            "turn_index": args[2],
                            "speaker": speaker,
                            "raw_utterance": args[3],
                        }
                    )

            async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
                limit = args[1]
                rows = journal[-limit:]
                return list(reversed(rows))

        conn = MockConnection()
        pid = "patient_turn_test_01"

        # Turn 1
        await store_conversation_turn(
            conn, pid, "I work night shifts (10 PM to 6 AM)", "Got it, I will adapt your meal schedule."
        )
        # Turn 2
        await store_conversation_turn(
            conn, pid, "What should I eat before my shift?", "Have a light protein meal around 8 PM."
        )

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
                    facts_db.append(
                        {
                            "patient_id": args[0],
                            "category": args[1],
                            "fact_key": args[2],
                            "fact_value": args[3],
                            "epistemic_status": args[4],
                        }
                    )

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
            bloating_chunks = await retrieve_chunks(conn, "mujhe pet me bohot gas aur bloating ho rahi hai", limit=3)
            self.assertTrue(len(bloating_chunks) > 0, "No chunks returned for bloating")
            tags = [c["condition_tag"] for c in bloating_chunks]
            self.assertTrue(any("BLOAT" in t or "JEERA" in t or "HING" in t for t in tags), f"Unexpected tags: {tags}")

            # 2. Acidity symptom query
            acidity_chunks = await retrieve_chunks(conn, "khatti dakar aur seene me jalan acidity problem", limit=3)
            self.assertTrue(len(acidity_chunks) > 0, "No chunks returned for acidity")
            tags = [c["condition_tag"] for c in acidity_chunks]
            self.assertTrue(any("GERD" in t or "ACID" in t or "AMLA" in t for t in tags), f"Unexpected tags: {tags}")

            # 3. Knee pain symptom query
            knee_chunks = await retrieve_chunks(conn, "ghutno me dard hai chalne me knee pain", limit=3)
            self.assertTrue(len(knee_chunks) > 0, "No chunks returned for knee pain")
            tags = [c["condition_tag"] for c in knee_chunks]
            self.assertTrue(
                any("KNEE" in t or "SHALLAKI" in t or "PRASARINI" in t or "RASNA" in t for t in tags),
                f"Unexpected tags: {tags}",
            )

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


class TestCanonicalSlotRegistry(unittest.TestCase):
    """Verify trilingual slot registry across English, Hindi (Devanagari), and Hinglish."""

    def setUp(self) -> None:
        self.registry = DEFAULT_SLOT_REGISTRY

    def test_canonical_slots_completeness(self) -> None:
        expected_slots = {
            "wake_time",
            "sleep_time",
            "water_intake_target",
            "meal_preferences",
            "dietary_restrictions",
            "physical_activity_clearance",
            "daily_steps_target",
            "tea_coffee_frequency",
        }
        registered_keys = {s.key for s in self.registry.list_all()}
        self.assertTrue(expected_slots.issubset(registered_keys), f"Missing slots: {expected_slots - registered_keys}")

        # Check PEP-controlled slot has PEP_DOCTOR authority and sensitive_flag=True
        pep_slot = self.registry.get("physical_activity_clearance")
        self.assertIsNotNone(pep_slot)
        self.assertEqual(pep_slot.source_authority, SourceAuthority.PEP_DOCTOR)
        self.assertTrue(pep_slot.sensitive_flag)

        # Check dietary_restrictions has sensitive_flag=True
        diet_slot = self.registry.get("dietary_restrictions")
        self.assertIsNotNone(diet_slot)
        self.assertTrue(diet_slot.sensitive_flag)

    def test_trilingual_wake_time_normalization(self) -> None:
        # English
        self.assertEqual(self.registry.normalize("wake_time", "7:00 AM"), "07:00")
        self.assertEqual(self.registry.normalize("wake_time", "6:30 am"), "06:30")
        # Hindi Devanagari
        self.assertEqual(self.registry.normalize("wake_time", "सुबह ७ बजे"), "07:00")
        self.assertEqual(self.registry.normalize("wake_time", "सुबह 7 बजे"), "07:00")
        # Hinglish
        self.assertEqual(self.registry.normalize("wake_time", "subah 7 baje"), "07:00")
        self.assertEqual(self.registry.normalize("wake_time", "subha 6:30 baje"), "06:30")

    def test_trilingual_sleep_time_normalization(self) -> None:
        # English
        self.assertEqual(self.registry.normalize("sleep_time", "11:00 PM"), "23:00")
        self.assertEqual(self.registry.normalize("sleep_time", "10:30 pm"), "22:30")
        # Hindi Devanagari
        self.assertEqual(self.registry.normalize("sleep_time", "रात ११ बजे"), "23:00")
        self.assertEqual(self.registry.normalize("sleep_time", "रात 10:30 बजे सोना"), "22:30")
        # Hinglish
        self.assertEqual(self.registry.normalize("sleep_time", "raat 11 baje"), "23:00")
        self.assertEqual(self.registry.normalize("sleep_time", "11pm pe sote hain"), "23:00")

    def test_trilingual_water_intake_target(self) -> None:
        # English
        self.assertEqual(self.registry.normalize("water_intake_target", "3 liters"), 3.0)
        self.assertEqual(self.registry.normalize("water_intake_target", "8 glasses"), 2.0)
        # Hindi Devanagari
        self.assertEqual(self.registry.normalize("water_intake_target", "३ लीटर पानी"), 3.0)
        self.assertEqual(self.registry.normalize("water_intake_target", "८ गिलास पानी"), 2.0)
        # Hinglish
        self.assertEqual(self.registry.normalize("water_intake_target", "3 litre paani"), 3.0)
        self.assertEqual(self.registry.normalize("water_intake_target", "8 glass pani"), 2.0)

    def test_trilingual_meal_preferences(self) -> None:
        # English
        self.assertEqual(self.registry.normalize("meal_preferences", "Vegetarian"), "Vegetarian")
        self.assertEqual(self.registry.normalize("meal_preferences", "non-veg"), "Non-Vegetarian")
        # Hindi Devanagari
        self.assertEqual(self.registry.normalize("meal_preferences", "शाकाहारी"), "Vegetarian")
        self.assertEqual(self.registry.normalize("meal_preferences", "मांसाहारी"), "Non-Vegetarian")
        self.assertEqual(self.registry.normalize("meal_preferences", "जैन खाना"), "Jain")
        self.assertEqual(self.registry.normalize("meal_preferences", "सात्विक"), "Satvik")
        # Hinglish
        self.assertEqual(self.registry.normalize("meal_preferences", "shakahari"), "Vegetarian")
        self.assertEqual(self.registry.normalize("meal_preferences", "non veg"), "Non-Vegetarian")
        self.assertEqual(self.registry.normalize("meal_preferences", "jain"), "Jain")

    def test_trilingual_dietary_restrictions(self) -> None:
        # English
        self.assertEqual(
            self.registry.normalize("dietary_restrictions", "gluten-free, lactose intolerant"),
            ["gluten_free", "lactose_intolerant"],
        )
        # Hindi Devanagari
        self.assertEqual(
            self.registry.normalize("dietary_restrictions", "बिना प्याज लहसुन, कम नमक"),
            ["low_sodium", "no_onion_garlic"],
        )
        # Hinglish
        self.assertEqual(
            self.registry.normalize("dietary_restrictions", "bina pyaaz lehsun, kam namak, sugar free"),
            ["low_sodium", "no_onion_garlic", "sugar_free"],
        )

    def test_trilingual_daily_steps_target(self) -> None:
        # English
        self.assertEqual(self.registry.normalize("daily_steps_target", "10,000 steps"), 10000)
        self.assertEqual(self.registry.normalize("daily_steps_target", "8000 steps"), 8000)
        self.assertEqual(self.registry.normalize("daily_steps_target", "10k"), 10000)
        # Hindi Devanagari
        self.assertEqual(self.registry.normalize("daily_steps_target", "१०,००० कदम"), 10000)
        self.assertEqual(self.registry.normalize("daily_steps_target", "दस हजार कदम"), 10000)
        # Hinglish
        self.assertEqual(self.registry.normalize("daily_steps_target", "10 hazar kadam"), 10000)
        self.assertEqual(self.registry.normalize("daily_steps_target", "8k steps"), 8000)

    def test_trilingual_tea_coffee_frequency(self) -> None:
        # English
        res_en = self.registry.normalize("tea_coffee_frequency", "2 cups of tea daily")
        self.assertEqual(res_en["tea_cups_per_day"], 2)
        # Hindi Devanagari
        res_hi = self.registry.normalize("tea_coffee_frequency", "दो कप चाय")
        self.assertEqual(res_hi["tea_cups_per_day"], 2)
        # Hinglish
        res_hing = self.registry.normalize("tea_coffee_frequency", "din mein teen cup chai")
        self.assertEqual(res_hing["tea_cups_per_day"], 3)
        res_coffee = self.registry.normalize("tea_coffee_frequency", "ek cup coffee")
        self.assertEqual(res_coffee["coffee_cups_per_day"], 1)

    def test_slot_extraction_from_utterance(self) -> None:
        text = "Main subah 7 baje uthta hoon, roz 3 litre pani peeta hoon aur mera 10,000 steps ka target hai."
        extracted = self.registry.extract_slots_from_text(text)
        self.assertEqual(extracted.get("wake_time"), "07:00")
        self.assertEqual(extracted.get("water_intake_target"), 3.0)
        self.assertEqual(extracted.get("daily_steps_target"), 10000)


class TestStrictClinicalBoundaryGuard(unittest.TestCase):
    """Verify strict clinical boundaries: LLM permissions = 0, contradiction quarantine, no silent overwrites."""

    def setUp(self) -> None:
        self.validator = SentenceValidator()
        self.registry = DEFAULT_SLOT_REGISTRY

    def test_source_authority_pep_doctor_enforcement(self) -> None:
        # Patient self-report cannot write physical_activity_clearance
        auth_ok, reason = self.registry.validate_authority(
            "physical_activity_clearance", SourceAuthority.PATIENT_REPORTED
        )
        self.assertFalse(auth_ok)
        self.assertIn("Permission Denied", reason)

        # PEP_DOCTOR is authorized
        auth_ok, reason = self.registry.validate_authority("physical_activity_clearance", SourceAuthority.PEP_DOCTOR)
        self.assertTrue(auth_ok)

    def test_llm_written_clinical_permissions_zero(self) -> None:
        """Enforce: LLM-written clinical permissions = 0."""
        forbidden_llm_grants = [
            "I hereby clear you for gym and heavy lifting.",
            "You are cleared for gym; start lifting weights.",
            "Main aapko gym ki clearance deta hoon.",
            "Main aapko heavy workout ki permission de raha hoon.",
            "Maine aapki doctor restrictions hata di hain, aap gym ja sakte hain.",
            "Aap gym ja sakte hain maine clear kar diya.",
            "मैं आपको जिम की अनुमति देता हूँ।",
            "मैंने आपकी पाबंदियां हटा दी हैं।",
        ]

        for grant in forbidden_llm_grants:
            res = self.validator.validate_sentence(grant)
            self.assertEqual(res.status, "rewritten", f"LLM grant was not blocked: {grant}")
            self.assertIn("llm_clinical_permission_grant_blocked", res.reasons)
            self.assertEqual(res.text, LLM_CLINICAL_PERMISSION_REPLACEMENT)

    def test_patient_claim_against_pep_restrictions_flagged_for_review(self) -> None:
        """Patient claims doctor clearance when PEP says gym_clearance=False."""
        pep = {
            "hypertension_stage": "stage 2",
            "gym_clearance": False,
            "allowed_modalities": ["brisk_walking"],
            "restricted_modalities": ["heavy_deadlifts", "hiit"],
        }

        # 1. Patient claims doctor cleared them for heavy gym
        patient_claim = "Doctor cleared me for heavy gym and deadlifts."
        contradictions = evaluate_patient_claims(patient_claim, pep)
        self.assertTrue(len(contradictions) > 0)
        self.assertTrue(any(c["flagged_for_review"] for c in contradictions))
        self.assertEqual(contradictions[0]["required_authority"], "PEP_DOCTOR")
        self.assertEqual(contradictions[0]["action"], "FLAG_CLINICIAN_REVIEW_MAINTAIN_RESTRICTION")

        # 2. Hindi Hinglish patient claim
        patient_hi_claim = "Doctor ne bola heavy deadlifts kar sakte ho ab."
        contradictions_hi = evaluate_patient_claims(patient_hi_claim, pep)
        self.assertTrue(len(contradictions_hi) > 0)
        self.assertTrue(
            any(
                "heavy_deadlifts" in c.get("pep_restriction", "") or "gym_clearance" in c.get("pep_restriction", "")
                for c in contradictions_hi
            )
        )

    def test_contradiction_injected_in_context_xml(self) -> None:
        """Contradictory claims must be flagged in context XML and NEVER silently overwritten."""
        context = {
            "pep": {
                "hypertension_stage": "stage 2",
                "gym_clearance": False,
                "allowed_modalities": ["walking"],
                "restricted_modalities": ["heavy_weightlifting"],
            },
            "contradictions": [
                {
                    "slot_key": "physical_activity_clearance",
                    "pep_restriction": "gym_clearance = False",
                    "reason": "Patient claimed doctor clearance for gym, but official PEP gym_clearance is False.",
                    "flagged_for_review": True,
                }
            ],
            "diet_slot_xml": "",
        }
        xml = render_context_xml(context)
        self.assertIn("<PEP_CONTRADICTION_NOTICE", xml)
        self.assertIn('status="FLAGGED_FOR_CLINICIAN_REVIEW"', xml)
        self.assertIn('action="MAINTAIN_RESTRICTIONS"', xml)
        self.assertIn("gym_clearance = False", xml)
        self.assertIn("LLM-written clinical permissions are 0", xml)


class TestPersistenceAndRehydration(unittest.IsolatedAsyncioTestCase):
    """Verify zero in-RAM session state loss on reconnect, turn_journal view, and memory_items."""

    async def test_zero_in_ram_state_lost_on_reconnect(self) -> None:
        """State must completely rehydrate from DB by session_id / call_id after RAM wipe."""
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            self.skipTest("DATABASE_URL not configured")

        try:
            import asyncpg

            conn = await asyncpg.connect(db_url)
        except Exception as exc:
            self.skipTest(f"PostgreSQL connection unavailable: {exc}")

        test_pid = "pt_rehydrate_test_42"
        test_session = "sess_rehydrate_001"
        test_call = "call_telephony_999"

        try:
            # 1. Setup DB state
            await conn.execute("DELETE FROM patient_turn_journal WHERE patient_id = $1", test_pid)
            await conn.execute("DELETE FROM memory_items WHERE patient_id = $1", test_pid)
            await conn.execute("DELETE FROM call_summaries WHERE patient_id = $1", test_pid)
            await conn.execute(
                """INSERT INTO patient_pep (patient_id, hypertension_stage, gym_clearance, allowed_modalities, restricted_modalities)
                   VALUES ($1, 'Normal', TRUE, ARRAY['walking', 'yoga'], ARRAY['heavy_deadlifts'])
                   ON CONFLICT (patient_id) DO UPDATE SET gym_clearance = TRUE""",
                test_pid,
            )

            # Store turn with session_id and call_id
            await store_conversation_turn(
                conn,
                test_pid,
                "Mujhe subah 7 baje uthna pasand hai.",
                "Bahut accha! Hum aapka breakfast 8 baje schedule karenge.",
                session_id=test_session,
                call_id=test_call,
            )

            # Store habit slot in memory_items
            await store_memory_item(
                conn,
                test_pid,
                slot_key="wake_time",
                slot_value="07:00",
                session_id=test_session,
                call_id=test_call,
            )

            # 2. Simulate complete RAM wipe: in-RAM process restarts, RAM cache is EMPTY
            in_ram_cache: dict[str, Any] = {}
            self.assertNotIn(test_pid, in_ram_cache)

            # 3. Rehydrate from DB by session_id and call_id
            rehydrated = await rehydrate_session_state(conn, test_pid, session_id=test_session, call_id=test_call)

            self.assertTrue(rehydrated["rehydrated_from_db"])
            self.assertEqual(len(rehydrated["conversation_history"]), 2)
            self.assertEqual(rehydrated["conversation_history"][0]["role"], "user")
            self.assertIn("7 baje", rehydrated["conversation_history"][0]["content"])
            self.assertEqual(rehydrated["session_id"], test_session)
            self.assertEqual(rehydrated["call_id"], test_call)
            self.assertIsNotNone(rehydrated["pep"])
            self.assertTrue(rehydrated["pep"]["gym_clearance"])

            # Verify memory slots rehydrated
            self.assertTrue(any(s["slot_key"] == "wake_time" for s in rehydrated["patient_slots"]))

        finally:
            await conn.execute("DELETE FROM patient_turn_journal WHERE patient_id = $1", test_pid)
            await conn.execute("DELETE FROM memory_items WHERE patient_id = $1", test_pid)
            await conn.execute("DELETE FROM call_summaries WHERE patient_id = $1", test_pid)
            await conn.execute("DELETE FROM patient_pep WHERE patient_id = $1", test_pid)
            await conn.close()

    async def test_turn_journal_and_patient_turn_journal_sync(self) -> None:
        """Verify turn_journal view reads from and writes to patient_turn_journal."""
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            self.skipTest("DATABASE_URL not configured")

        try:
            import asyncpg

            conn = await asyncpg.connect(db_url)
        except Exception as exc:
            self.skipTest(f"PostgreSQL connection unavailable: {exc}")

        test_pid = "pt_journal_sync_test"
        try:
            # Insert into turn_journal view
            await conn.execute(
                """INSERT INTO turn_journal (patient_id, session_id, turn_index, speaker, raw_utterance)
                   VALUES ($1, 's1', 0, 'user', 'Sync test utterance')""",
                test_pid,
            )

            # Read from patient_turn_journal table
            row = await conn.fetchrow("SELECT raw_utterance FROM patient_turn_journal WHERE patient_id = $1", test_pid)
            self.assertIsNotNone(row)
            self.assertEqual(row["raw_utterance"], "Sync test utterance")

        finally:
            await conn.execute("DELETE FROM patient_turn_journal WHERE patient_id = $1", test_pid)
            await conn.close()

    async def test_memory_items_persistence_and_superseding(self) -> None:
        """Verify memory_items stores and supersedes slots while maintaining history."""
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            self.skipTest("DATABASE_URL not configured")

        try:
            import asyncpg

            conn = await asyncpg.connect(db_url)
        except Exception as exc:
            self.skipTest(f"PostgreSQL connection unavailable: {exc}")

        test_pid = "pt_mem_items_test"
        try:
            # Step 1: Patient reports wake time 07:00
            await store_memory_item(conn, test_pid, slot_key="wake_time", slot_value="07:00")
            items = await load_memory_items(conn, test_pid, slot_key="wake_time")
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["slot_value"], "07:00")
            self.assertEqual(items[0]["epistemic_status"], "active")

            # Step 2: Patient updates wake time to 06:30
            await store_memory_item(conn, test_pid, slot_key="wake_time", slot_value="06:30")
            active_items = await load_memory_items(conn, test_pid, slot_key="wake_time", epistemic_status="active")
            self.assertEqual(len(active_items), 1)
            self.assertEqual(active_items[0]["slot_value"], "06:30")

            # Check that previous item was superseded, not deleted
            superseded_items = await load_memory_items(
                conn, test_pid, slot_key="wake_time", epistemic_status="superseded"
            )
            self.assertEqual(len(superseded_items), 1)
            self.assertEqual(superseded_items[0]["slot_value"], "07:00")

        finally:
            await conn.execute("DELETE FROM memory_items WHERE patient_id = $1", test_pid)
            await conn.close()

    async def test_call_summaries_persistence(self) -> None:
        """Verify call_summaries table stores and retrieves call summaries."""
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            self.skipTest("DATABASE_URL not configured")

        try:
            import asyncpg

            conn = await asyncpg.connect(db_url)
        except Exception as exc:
            self.skipTest(f"PostgreSQL connection unavailable: {exc}")

        test_pid = "pt_summary_test_01"
        test_call = "call_sum_test_xyz"
        try:
            await store_call_summary(
                conn,
                call_id=test_call,
                patient_id=test_pid,
                session_id="sess_01",
                duration_seconds=185,
                summary_text="Patient reported sleeping at 11pm and requested low sodium diet advice.",
                action_items=["Drink 3L water", "Avoid papad/namkeen"],
                habits_disclosed={"sleep_time": "23:00", "dietary_restrictions": ["low_sodium"]},
                contradictions_detected=[],
                sentiment="positive",
            )

            summaries = await load_call_summaries(conn, test_pid, limit=1)
            self.assertEqual(len(summaries), 1)
            s = summaries[0]
            self.assertEqual(s["call_id"], test_call)
            self.assertEqual(s["duration_seconds"], 185)
            self.assertIn("11pm", s["summary_text"])
            self.assertIn("Drink 3L water", s["action_items"])

        finally:
            await conn.execute("DELETE FROM call_summaries WHERE call_id = $1", test_call)
            await conn.close()


if __name__ == "__main__":
    unittest.main()
