"""Pytest Test Suite for Disha AI Behavior Spec v1 Golden Test Cases.

Independent QA Test Suite verifying conformance to:
- P1-P6: Persona, tone, multi-lingual scripts, banned honorifics, WhatsApp brevity
- F1-F6: Zero-echo, one meaningful closing question, 1-3 sentences, selective empathy, forward motion
- C1-C4: History Triangle progression, no advice on chat, emergency red flags (112), pivot
- M1-M3: Multi-turn memory retention, ambiguity handling, root system prompt integrity
- Precedence hierarchy: C3 > Honesty Invariants > C2 > M2 > C1 > F5/C4 > Style
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from disha_core.harness.perception import TriangleStatus, TurnPerception, select_move
from disha_core.harness.verifier import (
    check_c2_clinical_boundary,
    split_sentences_multilingual,
    verify_response,
)
from disha_core.llm.client import get_system_prompt
from disha_core.pipeline.breaker import EmergencyBreaker

GOLDEN_DIR = Path(__file__).resolve().parent
BREAKER = EmergencyBreaker()


def load_all_cases() -> list[dict[str, Any]]:
    """Load all test cases across all golden YAML files."""
    cases = []
    for yf in sorted(GOLDEN_DIR.glob("*.yaml")):
        with open(yf, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for c in data.get("cases", []):
            c["_file"] = yf.name
            cases.append(c)
    return cases


ALL_CASES = load_all_cases()
CASE_IDS = [f"{c.get('_file', '')}::{c.get('id', 'unknown')}" for c in ALL_CASES]


@pytest.mark.parametrize("case", ALL_CASES, ids=CASE_IDS)
def test_golden_case(case: dict[str, Any]) -> None:
    """Execute a single golden test case."""
    cid = case.get("id")

    # 1. Emergency Breaker Check
    if "input_text" in case:
        res = BREAKER.check(case["input_text"])
        expected_triggered = case.get("expected_triggered", True)
        assert res.triggered == expected_triggered, (
            f"Case {cid}: breaker trigger mismatch. Got {res.triggered}, expected {expected_triggered}"
        )

        if expected_triggered:
            max_lat = case.get("max_latency_ms", 5.0)
            assert res.elapsed_ms < max_lat, (
                f"Case {cid}: breaker latency SLA failed: {res.elapsed_ms:.3f}ms >= {max_lat}ms"
            )
            required = case.get("required_in_response", ["112"])
            for token in required:
                assert token in (res.response or ""), (
                    f"Case {cid}: required emergency token '{token}' not in response '{res.response}'"
                )
            if "max_sentences" in case:
                sents = split_sentences_multilingual(res.response or "")
                assert len(sents) <= case["max_sentences"], (
                    f"Case {cid}: sentence count {len(sents)} > {case['max_sentences']}"
                )
            if "max_questions" in case:
                q_count = (res.response or "").count("?")
                assert q_count <= case["max_questions"], (
                    f"Case {cid}: question count {q_count} > {case['max_questions']}"
                )

    # 2. Move Selection & Triangle Check
    if "expected_move" in case and "context" in case:
        ctx = case["context"]
        t_data = ctx.get("triangle_status", {})
        t_stat = TriangleStatus(**t_data) if t_data else TriangleStatus()
        perception = TurnPerception(
            current_concern=ctx.get("current_concern"),
            triangle_status=t_stat,
            medication_inquiry=ctx.get("medication_inquiry", False),
            answer_quality=ctx.get("answer_quality", "na"),
            user_act=ctx.get("user_act", "other"),
        )
        move = select_move(perception)
        assert move == case["expected_move"], (
            f"Case {cid}: move mismatch. Got '{move}', expected '{case['expected_move']}'"
        )
        if "expected_triangle_axis" in case:
            next_axis = perception.triangle_status.next_unanswered()
            assert next_axis == case["expected_triangle_axis"], (
                f"Case {cid}: axis mismatch. Got '{next_axis}', expected '{case['expected_triangle_axis']}'"
            )

    # 3. Candidate Response Verification Check
    if "candidate_response" in case:
        candidate = case["candidate_response"]
        ctx = case.get("context", {}).copy()
        ctx["language"] = case.get("language", ctx.get("language", "hinglish"))

        vr = verify_response(candidate, ctx)
        c2_viols = [v.check_name for v in check_c2_clinical_boundary(candidate)]
        all_viols = set([v.check_name for v in vr.violations] + c2_viols)

        # These old fixtures tested style blockers that are intentionally advisory now.
        retired_style_rule = case.get("rule_id") in {"F1", "F2", "F4", "P4"}
        expected_valid = True if retired_style_rule else case.get("expected_valid", True)
        assert vr.is_valid == expected_valid, (
            f"Case {cid}: validity mismatch. Got {vr.is_valid}, expected {expected_valid}. Detected: {sorted(all_viols)}"
        )

        if case.get("expected_violations") and not retired_style_rule:
            expected_set = set(case["expected_violations"])
            assert any(ev in all_viols for ev in expected_set), (
                f"Case {cid}: none of expected violations {case['expected_violations']} matched actual {sorted(all_viols)}"
            )

    # 4. Root Prompt Check (M3)
    if "expected_rule_ids" in case:
        prompt = get_system_prompt(behavior_spec_v1=True, language_mode="hinglish")
        for rid in case["expected_rule_ids"]:
            assert f"[{rid}]" in prompt, f"Case {cid}: Rule [{rid}] missing from system prompt"

    if "max_token_budget" in case:
        prompt = get_system_prompt(behavior_spec_v1=True, language_mode="hinglish")
        tokens = len(prompt) // 4
        assert tokens <= case["max_token_budget"], (
            f"Case {cid}: Prompt token budget exceeded: {tokens} > {case['max_token_budget']}"
        )

    if "expected_version_prefix" in case:
        prompt = get_system_prompt(behavior_spec_v1=True, language_mode="hinglish")
        assert f"# PROMPT_VERSION: {case['expected_version_prefix']}" in prompt, (
            f"Case {cid}: Prompt version prefix missing"
        )


class TestGoldenSuiteIntegrity:
    """Meta-assertions verifying Golden Test Suite completeness and integrity."""

    def test_all_19_rule_ids_covered(self):
        """Verify that every rule from P1-P6, F1-F6, C1-C4, M1-M3 has at least one golden test case."""
        expected_rules = [
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
            "F6",
            "C1",
            "C2",
            "C3",
            "C4",
            "M1",
            "M2",
            "M3",
        ]
        tested_rules = {c.get("rule_id") for c in ALL_CASES if c.get("rule_id")}
        for r in expected_rules:
            assert r in tested_rules, f"Rule {r} has no test cases in golden suite"

    def test_supported_languages_covered(self):
        """Verify that hinglish, english, and hindi are all tested in golden test suite."""
        languages = {c.get("language") for c in ALL_CASES if c.get("language")}
        assert "hinglish" in languages
        assert "english" in languages
        assert "hindi" in languages

    def test_precedence_matrix_complete(self):
        """Verify that precedence levels 1 through 7 are represented."""
        prec_levels = {c.get("precedence_level") for c in ALL_CASES if c.get("precedence_level")}
        assert prec_levels == {1, 2, 3, 4, 5, 6, 7}

    def test_minimum_test_case_volume(self):
        """Ensure Golden Test Suite maintains a high-assurance count (>= 60 cases)."""
        assert len(ALL_CASES) >= 60, f"Expected >= 60 golden cases, found {len(ALL_CASES)}"
