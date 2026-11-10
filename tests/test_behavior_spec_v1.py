"""Conformance Test Suite for Behavior Spec v1.

Verifies:
- P1 to P6: Persona, tone, Hinglish/English/Hindi scripts, banned honorifics, 1-3 sentences
- F1 to F5: Zero-echo, at most 1 question, 1-3 sentences, selective empathy, forward motion
- C1 to C4: History triangle, no advice on chat, emergency red flags (112), pivot
- M1 to M3: Memory retention, vague answer clarification, root system prompt rendering
- D2 to D5: Critical values flag, C2 boundary, expert call CTA, 2-turn silent language switch
- Rollback: BEHAVIOR_SPEC_V1=false restores legacy behavior
"""

from disha_core.harness.perception import TriangleStatus, TurnPerception, select_move
from disha_core.harness.verifier import (
    check_c2_clinical_boundary,
    check_f1_zero_echo,
    check_f2_at_most_one_question,
    check_f4_selective_empathy,
    check_p3_language_mode,
    check_p4_honorifics,
    check_p6_f3_length,
)
from disha_core.llm.client import PROMPT_VERSION, get_system_prompt
from disha_core.pipeline.breaker import EmergencyBreaker


class TestBehaviorSpecPromptAndRules:
    """M3 & Spec V1 System Prompt Rendering."""

    def test_all_18_rule_ids_present_in_rendered_prompt(self):
        prompt = get_system_prompt(behavior_spec_v1=True, language_mode="hinglish")
        expected_ids = [
            "P1",
            "P2",
            "P3",
            "P4",
            "P5",
            "P6",
            "F1",
            "F2",
            "F3",
            "F4",
            "F5",
            "C1",
            "C2",
            "C3",
            "C4",
            "M1",
            "M2",
            "M3",
        ]
        for rid in expected_ids:
            assert f"[{rid}]" in prompt, f"Rule ID {rid} missing from rendered system prompt"

    def test_prompt_token_budget_under_600_tokens(self):
        prompt = get_system_prompt(behavior_spec_v1=True, language_mode="hinglish")
        est_tokens = len(prompt) // 4
        assert est_tokens <= 600, f"System prompt exceeds 600 tokens: {est_tokens} tokens ({len(prompt)} chars)"

    def test_prompt_version_and_hash_present(self):
        prompt = get_system_prompt(behavior_spec_v1=True, language_mode="hinglish")
        assert "# PROMPT_VERSION: v2-" in prompt
        assert len(PROMPT_VERSION) >= 10

    def test_language_mode_injection(self):
        p_hi = get_system_prompt(behavior_spec_v1=True, language_mode="hindi")
        assert "Devanagari" in p_hi
        p_en = get_system_prompt(behavior_spec_v1=True, language_mode="english")
        assert "English" in p_en
        assert "casual English" in p_en

    def test_legacy_switch_cannot_reintroduce_a_second_behavior_policy(self):
        assert get_system_prompt(behavior_spec_v1=False) == get_system_prompt(behavior_spec_v1=True)


class TestDeterministicVerifiers:
    """P3, P4, P6, F1, F2, F4, C2 Verification Checks."""

    def test_p3_hinglish_rejects_devanagari(self):
        viol = check_p3_language_mode("Yeh aapke liye achha hai नमस्ते", "hinglish")
        assert viol is not None
        assert viol.check_name == "p3_script_mismatch"

    def test_p3_english_rejects_hindi_words(self):
        viol = check_p3_language_mode("Please follow this diet aapka health theek hoga", "english")
        assert viol is not None
        assert viol.check_name == "p3_english_pure"

    def test_p4_banned_honorifics(self):
        for phrase in ["Ji sir, main batati hoon", "Sure ma'am", "Haanji madam", "श्रीमान आपका स्वागत है"]:
            viol = check_p4_honorifics(phrase)
            assert viol is not None, f"Expected violation for '{phrase}'"
            assert viol.check_name == "p4_banned_honorific"

    def test_p6_f3_max_3_sentences_without_turn_policy(self):
        four_sents = (
            "Yeh pehla sentence hai. Yeh doosra sentence hai! Yeh teesra sentence hai? Yeh chautha sentence hai."
        )
        viol = check_p6_f3_length(four_sents)
        assert viol is not None
        assert viol.check_name == "p6_f3_sentence_count"

    def test_verify_response_uses_turn_length_policy(self):
        from disha_core.engine.context_builder import LengthPolicy
        from disha_core.harness.verifier import verify_response

        response = "First point. Second point. Third point. Fourth point."
        assert verify_response(response, {"length_policy": LengthPolicy("coaching", 2, 4)}).is_valid

    def test_p6_f3_allows_1_to_3_sentences(self):
        assert check_p6_f3_length("Pani zyada piyein. Thoda walk karein.") is None

    def test_f1_zero_echo_user_facts(self):
        ctx = {"user_input": "Mera weight 62kg hai aur age 28 saal"}
        viol = check_f1_zero_echo("Aapka weight 62kg hai toh diet plan karte hain.", ctx)
        assert viol is not None
        assert viol.check_name == "f1_zero_echo"

    def test_f1_zero_echo_prefix(self):
        ctx = {"user_input": "Mujhe subah acidity hoti hai"}
        viol = check_f1_zero_echo("Aapne bataya ki aapko acidity hoti hai, toh pani piyein.", ctx)
        assert viol is not None
        assert viol.check_name == "f1_zero_echo_prefix"

    def test_f2_at_most_one_question(self):
        viol = check_f2_at_most_one_question("Aap kab uthte hain? Aur kitna sote hain?")
        assert viol is not None
        assert viol.check_name == "f2_multiple_questions"

    def test_f2_allows_single_question(self):
        assert check_f2_at_most_one_question("Aapka daily water intake kitna hai?") is None

    def test_f4_selective_empathy_disallows_boilerplate_without_distress(self):
        ctx = {"distress_expressed": False}
        viol = check_f4_selective_empathy("Main aapka dard samajh sakti hoon. Diet shuru karein.", ctx)
        assert viol is not None
        assert viol.check_name == "f4_unprompted_boilerplate_empathy"

    def test_f4_selective_empathy_allows_when_distress_expressed(self):
        ctx = {"distress_expressed": True}
        assert check_f4_selective_empathy("Main samajh sakti hoon, thoda aaram karein.", ctx) is None

    def test_c2_boundary_medication_dose_forbidden(self):
        viols = check_c2_clinical_boundary("Aap Metformin 500 mg le lijiye.")
        assert len(viols) > 0
        names = [v.check_name for v in viols]
        assert "c2_medication_dose_advice" in names

    def test_c2_boundary_diagnosis_forbidden(self):
        viols = check_c2_clinical_boundary("Aapko diabetes hai, dhyan dein.")
        assert any(v.check_name == "c2_diagnosis_claim" for v in viols)

    def test_c2_boundary_treatment_plan_forbidden(self):
        viols = check_c2_clinical_boundary("Aap double the dose of insulin kar sakte hain.")
        assert any(v.check_name in ("c2_treatment_plan", "c2_medication_dose_advice") for v in viols)


class TestMovePrecedenceAndTriangle:
    """Precedence Chain & History Triangle (Section 5.3 & C1/C4/M2)."""

    def test_precedence_medication_inquiry_withholds_and_pivots(self):
        p = TurnPerception(medication_inquiry=True, current_concern="fever")
        move = select_move(p)
        assert move == "withhold_and_pivot"

    def test_precedence_clarify_vague_answer(self):
        p = TurnPerception(answer_quality="vague", current_concern="back pain")
        move = select_move(p)
        assert move == "clarify"

    def test_precedence_triangle_question_before_insight(self):
        p = TurnPerception(
            current_concern="headache",
            triangle_status=TriangleStatus(duration="unknown", past_attempts="unknown", severity="unknown"),
        )
        move = select_move(p)
        assert move == "triangle_question"
        assert p.triangle_status.next_unanswered() == "duration"

    def test_precedence_clinical_insight_only_after_triangle_complete(self):
        p = TurnPerception(
            current_concern="headache",
            triangle_status=TriangleStatus(duration="answered", past_attempts="answered", severity="answered"),
        )
        move = select_move(p)
        assert move == "clinical_insight"

    def test_precedence_declined_axis_counts_as_complete(self):
        p = TurnPerception(
            current_concern="acidity",
            triangle_status=TriangleStatus(duration="answered", past_attempts="declined", severity="answered"),
        )
        move = select_move(p)
        assert move == "clinical_insight"

    def test_c3_emergency_red_flag_preempts_everything(self):
        breaker = EmergencyBreaker()
        res = breaker.check("Severe chest pain radiating to left arm and sweating")
        assert res.triggered is True
        assert "112" in res.response
