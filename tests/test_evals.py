import pytest
from evals.runner import DishaEvalHarness

@pytest.mark.asyncio
async def test_full_evaluation_harness_suite():
    """Runs the complete Disha Evaluation Suite and verifies 100% safety and conversation passes."""
    harness = DishaEvalHarness()
    results = await harness.run_all()

    # Assert 100% safety suite compliance
    assert results["safety_suite"]["passed"] == results["safety_suite"]["total"]

    # Assert 100% realistic multi-turn conversations
    assert results["conversational_suite"]["passed"] == results["conversational_suite"]["total"]

    # Assert Voice mechanics
    assert results["voice_suite"]["sentence_buffering_passed"] is True
    assert results["voice_suite"]["bargein_context_alignment_passed"] is True
    assert results["voice_suite"]["context_fillers_passed"] is True

    # Assert pre-turn circuit breaker sub-millisecond latency
    assert results["performance_suite"]["guardrail_triage_latency_ms"] < 0.5

