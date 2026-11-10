"""Disha AI Response Harness Package (Section 5 Architecture).

Unified module managing the complete conversational lifecycle:
PERCEIVE -> PLAN -> GENERATE -> VERIFY -> REPAIR -> COMMIT
with TurnContext tracking, deterministic verification, repair loops,
structured planning (<=80 tokens JSON), and labeled system errors.
"""

from __future__ import annotations

from disha_core.harness.harness import ResponseHarness
from disha_core.harness.planner import StructuredPlan, build_structured_plan
from disha_core.harness.repair import apply_constrained_fallback, format_system_error, repair_turn
from disha_core.harness.verifier import (
    VerificationResult,
    VerificationViolation,
    check_doctor_or_human_claim,
    check_false_memory_claims,
    check_ngram_repetitions,
    check_pep_and_clinical_bounds,
    check_question_spam,
    check_ungrounded_numbers_and_facts,
    check_unsupported_capabilities,
    verify_response,
)

__all__ = [
    "ResponseHarness",
    "StructuredPlan",
    "VerificationResult",
    "VerificationViolation",
    "apply_constrained_fallback",
    "build_structured_plan",
    "check_doctor_or_human_claim",
    "check_false_memory_claims",
    "check_ngram_repetitions",
    "check_pep_and_clinical_bounds",
    "check_question_spam",
    "check_ungrounded_numbers_and_facts",
    "check_unsupported_capabilities",
    "format_system_error",
    "repair_turn",
    "verify_response",
]
