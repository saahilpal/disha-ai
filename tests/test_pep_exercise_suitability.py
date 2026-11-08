"""Regression Test Suite for PEP-Aware Personalised Exercise Recommendation and Restriction Engine.

Validates all 10 clinical scenarios mandated by the User Correction:
1. Knee pain (squats / jumping avoided or modified, glute bridges recommended).
2. Lower-back discomfort (deadlifts avoided, bird-dog / walking recommended).
3. Cardiovascular conditions (Valsalva / heavy maximal deadlifts contraindicated, brisk walking recommended).
4. Exercise preferences (yoga / low-impact preferences honored).
5. Home workout preferences (dumbbells / bodyweight, zero barbell requirements).
6. New injuries (acute ankle sprain invalidates running).
7. Changing symptoms (worsening pain stops exercise, triggers clinical assessment).
8. Missing medical information (asks clarifying question, does not guess).
9. Conflicting PEP information (patient claim overridden by clinical PEP safety bounds).
10. Dynamic updates (previously recommended exercise becomes unsuitable upon new symptom disclosure).
"""
from __future__ import annotations

from disha_core.pep.exercise_engine import (
    SuitabilityCategory,
    evaluate_exercise_suitability,
    format_personalised_exercise_advice,
)


class TestPEPAwareExerciseSuitability:
    """Rigorous clinical test suite for PEP-driven exercise recommendation logic."""

    # --------------------------------------------------------------------------
    # Scenario 1: Knee Pain & Patellar Loading
    # --------------------------------------------------------------------------
    def test_knee_pain_avoids_high_impact_and_modifies_squats(self) -> None:
        """Knee discomfort avoids jumping/running and recommends safe floor-based alternatives."""
        eval_squats = evaluate_exercise_suitability(
            exercise_name="squats",
            reported_symptoms=["ghutne mein halka dard rehta hai"],
        )
        assert eval_squats.category == SuitabilityCategory.MODIFIED
        assert "ghutne" in eval_squats.reason.lower() or "knee" in eval_squats.reason.lower()
        # Must provide chair support or shallow bend modification
        assert any("chair" in m.lower() or "shallow" in m.lower() for m in eval_squats.modifications)
        # Must provide knee-friendly alternative like glute bridges
        assert any("glute bridge" in a.lower() for a in eval_squats.alternatives)

        # High-impact jumping jacks with knee pain must be modified or avoided
        eval_jumping = evaluate_exercise_suitability(
            exercise_name="jumping_jacks",
            reported_symptoms=["left knee pain when bending"],
        )
        assert eval_jumping.category in (SuitabilityCategory.MODIFIED, SuitabilityCategory.AVOID)
        assert any("step-jacks" in m.lower() or "low-impact" in m.lower() for m in eval_jumping.modifications)

    # --------------------------------------------------------------------------
    # Scenario 2: Lower-Back Discomfort & Lumbar Shear
    # --------------------------------------------------------------------------
    def test_lower_back_pain_avoids_heavy_deadlifts_and_crunches(self) -> None:
        """Lower-back discomfort strictly avoids heavy axial spine loads and suggests bird-dog."""
        eval_deadlift = evaluate_exercise_suitability(
            exercise_name="heavy_deadlifts",
            reported_symptoms=["chronic lower back stiffness and disc bulge"],
        )
        assert eval_deadlift.category == SuitabilityCategory.AVOID
        assert any(term in eval_deadlift.reason.lower() for term in ("kamar", "back", "spine"))
        assert any("bird-dog" in a.lower() for a in eval_deadlift.alternatives)

        eval_crunches = evaluate_exercise_suitability(
            exercise_name="crunches",
            physical_limitations=["kamar dard", "slip disc"],
        )
        assert eval_crunches.category in (SuitabilityCategory.MODIFIED, SuitabilityCategory.AVOID)
        assert any("bird-dog" in a.lower() or "deadbug" in m.lower() for a in eval_crunches.alternatives for m in eval_crunches.modifications)

    # --------------------------------------------------------------------------
    # Scenario 3: Cardiovascular Conditions & Hypertension
    # --------------------------------------------------------------------------
    def test_cardiovascular_and_hypertension_stage2_contraindications(self) -> None:
        """Stage 2 Hypertension strictly avoids heavy deadlifts/Valsalva and allows brisk walking."""
        pep_htn2 = {
            "core": {
                "hypertension_stage": "stage 2",
                "restricted_modalities": ["heavy_deadlifts", "valsalva"],
                "allowed_modalities": ["brisk_walking", "gentle_yoga"],
            }
        }
        eval_deadlift = evaluate_exercise_suitability(
            exercise_name="heavy_deadlifts",
            patient_pep=pep_htn2,
        )
        assert eval_deadlift.category == SuitabilityCategory.AVOID
        assert "blood pressure" in eval_deadlift.reason.lower() or "contraindicated" in eval_deadlift.reason.lower()

        # Brisk walking is suitable and safe
        eval_walking = evaluate_exercise_suitability(
            exercise_name="brisk_walking",
            patient_pep=pep_htn2,
        )
        assert eval_walking.category == SuitabilityCategory.SUITABLE

    # --------------------------------------------------------------------------
    # Scenario 4: Exercise Preferences
    # --------------------------------------------------------------------------
    def test_exercise_preferences_honored(self) -> None:
        """Gentle yoga preference receives suitable mobility flow without heavy gym bias."""
        eval_yoga = evaluate_exercise_suitability(
            exercise_name="gentle_yoga",
            user_preferences=["gentle mobility", "pranayama"],
        )
        assert eval_yoga.category == SuitabilityCategory.SUITABLE
        assert "gentle yoga" in eval_yoga.exercise_name.lower() or "yoga" in eval_yoga.exercise_name.lower()

    # --------------------------------------------------------------------------
    # Scenario 5: Home Workout Preferences & Zero Equipment
    # --------------------------------------------------------------------------
    def test_home_workout_zero_equipment_adaptation(self) -> None:
        """When equipment is 'none' and location is 'home', machine/barbell loads adapt to bodyweight."""
        eval_res = evaluate_exercise_suitability(
            exercise_name="squats",
            available_equipment="none",
            location_preference="home",
        )
        assert eval_res.category == SuitabilityCategory.SUITABLE
        # No gym machines recommended
        advice = format_personalised_exercise_advice(eval_res)
        assert "barbell" not in advice.lower()

    # --------------------------------------------------------------------------
    # Scenario 6: New Acute Injuries
    # --------------------------------------------------------------------------
    def test_new_acute_injury_invalidates_running(self) -> None:
        """Sudden ankle sprain or acute knee injury invalidates previously viable running."""
        # Mild injury / discomfort
        eval_running = evaluate_exercise_suitability(
            exercise_name="running",
            recent_injuries=["mild ankle soreness and foot sprain"],
        )
        assert eval_running.category in (SuitabilityCategory.MODIFIED, SuitabilityCategory.AVOID)
        assert any("walking" in a.lower() or "cycling" in a.lower() or "swimming" in a.lower() for a in eval_running.alternatives)

        # Acute severe injury requires doctor assessment
        eval_acute = evaluate_exercise_suitability(
            exercise_name="running",
            recent_injuries=["acute ankle sprain with severe swelling"],
        )
        assert eval_acute.category == SuitabilityCategory.REQUIRES_CLINICAL_ASSESSMENT

    # --------------------------------------------------------------------------
    # Scenario 7: Changing Symptoms from Mild to Severe
    # --------------------------------------------------------------------------
    def test_changing_symptoms_trigger_clinical_assessment(self) -> None:
        """Worsening to acute severe pain stops self-coaching and requires clinician assessment."""
        eval_acute = evaluate_exercise_suitability(
            exercise_name="brisk_walking",
            reported_symptoms=["severe sharp chest pain and radiating numbness, bahut tez dard"],
        )
        assert eval_acute.category == SuitabilityCategory.REQUIRES_CLINICAL_ASSESSMENT
        assert "clinician" in eval_acute.reason.lower() or "jaanch" in eval_acute.reason.lower()

    # --------------------------------------------------------------------------
    # Scenario 8: Missing Medical Information (Clarification Guard)
    # --------------------------------------------------------------------------
    def test_missing_medical_information_asks_clarification(self) -> None:
        """Unknown or uncataloged exercise input asks for clarification instead of guessing."""
        eval_unknown = evaluate_exercise_suitability(
            exercise_name="hyperbolic_plyometric_inversion",
        )
        assert eval_unknown.category == SuitabilityCategory.INSUFFICIENT_INFO
        assert len(eval_unknown.clarification_question) > 0
        advice = format_personalised_exercise_advice(eval_unknown)
        assert "?" in advice or "jankari" in advice.lower()

    # --------------------------------------------------------------------------
    # Scenario 9: Conflicting Patient Claims (Zero LLM Override)
    # --------------------------------------------------------------------------
    def test_conflicting_patient_claims_maintained_by_clinical_safety(self) -> None:
        """Patient claims they can do max deadlifts; PEP Stage 2 HTN safety bounds maintain restriction."""
        pep_restricted = {
            "core": {
                "hypertension_stage": "stage 2",
                "restricted_modalities": ["heavy_deadlifts"],
            }
        }
        eval_res = evaluate_exercise_suitability(
            exercise_name="heavy_deadlifts",
            patient_pep=pep_restricted,
            reported_symptoms=["I am totally fine to lift 150kg today"],
        )
        # Clinical safety wins over verbal claim
        assert eval_res.category == SuitabilityCategory.AVOID
        assert any("bird-dog" in a.lower() or "glute bridge" in a.lower() for a in eval_res.alternatives)

    # --------------------------------------------------------------------------
    # Scenario 10: Dynamic Recommendation Invalidation
    # --------------------------------------------------------------------------
    def test_dynamic_recommendation_invalidation(self) -> None:
        """Exercise suitable at baseline becomes modified/avoided when new limitation is introduced."""
        # 1. Baseline: Healthy patient, squats are fully suitable
        eval_before = evaluate_exercise_suitability(
            exercise_name="squats",
            reported_symptoms=[],
        )
        assert eval_before.category == SuitabilityCategory.SUITABLE

        # 2. Patient updates state: New knee discomfort
        eval_after = evaluate_exercise_suitability(
            exercise_name="squats",
            reported_symptoms=["aaj subah se right knee mein dard hai"],
        )
        assert eval_after.category == SuitabilityCategory.MODIFIED
        assert eval_after.category != eval_before.category
        assert len(eval_after.modifications) > 0
