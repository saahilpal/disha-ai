"""Golden corpus checks for sustained coaching behavior.

These checks validate the scenario contract and deterministic conversation invariants;
provider-backed response quality still requires a live/model grader.
"""

from __future__ import annotations

from pathlib import Path

import yaml

CORPUS = Path(__file__).parent / "golden" / "d_rules_long_conversation.yaml"
CASES = yaml.safe_load(CORPUS.read_text(encoding="utf-8"))["cases"]


def test_long_conversation_corpus_covers_distinct_user_types() -> None:
    assert len(CASES) >= 8
    assert len({case["user_type"] for case in CASES}) == len(CASES)
    assert {"chat", "voice"} <= {channel for case in CASES for channel in case["channel_sequence"]}


def test_long_conversation_cases_have_real_multi_turn_contracts() -> None:
    for case in CASES:
        assert len(case["turns"]) >= 4, case["id"]
        assert len(case["turns"]) == len(case["channel_sequence"]), case["id"]
        assert case["required"], case["id"]
        assert all(turn["user"].strip() and turn["assistant"].strip() for turn in case["turns"]), case["id"]


def test_long_conversation_fixture_rejects_repeated_question_text() -> None:
    for case in CASES:
        questions = [turn["assistant"] for turn in case["turns"] if "?" in turn["assistant"]]
        assert len(questions) == len(set(questions)), case["id"]


def test_long_conversation_fixture_has_explicit_quality_assertions() -> None:
    required = {item for case in CASES for item in case["required"]}
    assert {
        "uses_prior_context",
        "natural_pep_discovery",
        "respects_refusal",
        "honors_correction",
        "follows_current_intent",
        "cross_channel_context",
        "clinical_uncertainty",
    } <= required
