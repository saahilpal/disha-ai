"""Production Laya Integration Test Suite for Disha AI Core.

Validates:
1. Accurate intent classification across Indian health queries (Hinglish, Hindi, English)
   spanning all 6 clinical intents:
   - meal_query
   - symptom_complaint
   - exercise_query
   - general_coaching
   - emergency_escalation
   - app_meta
2. Retrieval routing & short-circuiting:
   - Skips pgvector knowledge base retrieval on pure greeting, general coaching, and app meta.
   - Routes to targeted domain retrieval on symptom, meal, and exercise queries.
3. PEP risk triage:
   - Laya System 1 early-detects high-risk exercise requests (pep_risk=2) and triggers
     deterministic clinical safety bounds ahead of LLM generation.
4. Review queue capture:
   - Asynchronously captures sub-threshold confidence (<0.7) and ambiguous turns into
     the zero-PHI ReviewQueueManager for clinical audit.
5. High-speed latency SLA:
   - Guarantees fast execution (<25ms cached and fallback paths).
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from disha_core.classifier.adapter import (
    LayaClassifierAdapter,
)
from disha_core.classifier.review_queue import (
    ReviewQueueManager,
    TriggerType,
)
from disha_core.models.schemas import TurnRequest, TurnState
from disha_core.pipeline.router import (
    Intent,
    IntentRouter,
)
from disha_core.pipeline.validator import PEP_REPLACEMENT, SentenceValidator
from disha_core.services.chat_service import generate_turn_sentences

# Indian Multilingual Test Cases: Hinglish, Hindi, and English
INDIAN_HEALTH_CASES: list[dict[str, str]] = [
    # Meal Query
    {"text": "What should I eat for dinner tonight?", "expected_intent": "meal_query", "lang": "en"},
    {"text": "Aaj raat ke khane mein kya prescribed hai?", "expected_intent": "meal_query", "lang": "hinglish"},
    {"text": "आज रात के खाने में क्या खाना चाहिए?", "expected_intent": "meal_query", "lang": "hi"},
    {
        "text": "Lunch mein dal roti aur salad kitna kha sakte hain?",
        "expected_intent": "meal_query",
        "lang": "hinglish",
    },
    # Symptom Complaint
    {"text": "I am feeling severe stomach bloating and acidity.", "expected_intent": "symptom_complaint", "lang": "en"},
    {
        "text": "Khana khane ke baad pet phool raha hai aur gas ho rahi hai.",
        "expected_intent": "symptom_complaint",
        "lang": "hinglish",
    },
    {"text": "पेट में बहुत तेज दर्द और गैस बन रही है।", "expected_intent": "symptom_complaint", "lang": "hi"},
    {"text": "Pet mein halka dard aur ajeeb si jalan hai.", "expected_intent": "symptom_complaint", "lang": "hinglish"},
    # Exercise Query
    {"text": "Can I do heavy deadlifts and squats at the gym?", "expected_intent": "exercise_query", "lang": "en"},
    {
        "text": "Aaj gym mein 100kg deadlift aur heavy weights kar sakta hoon?",
        "expected_intent": "exercise_query",
        "lang": "hinglish",
    },
    {"text": "क्या मैं जिम में भारी वजन और कसरत कर सकता हूँ?", "expected_intent": "exercise_query", "lang": "hi"},
    {"text": "Is high intensity workout allowed today?", "expected_intent": "exercise_query", "lang": "en"},
    # General Coaching / Wellness
    {
        "text": "How many steps should I walk daily for my blood pressure?",
        "expected_intent": "general_coaching",
        "lang": "en",
    },
    {
        "text": "Namaste Disha, din bhar mein kitna paani peena chahiye?",
        "expected_intent": "general_coaching",
        "lang": "hinglish",
    },
    {
        "text": "Tips for improving my deep sleep and stress levels.",
        "expected_intent": "general_coaching",
        "lang": "en",
    },
    {
        "text": "I completed my 8,000 steps today, feeling energetic.",
        "expected_intent": "general_coaching",
        "lang": "en",
    },
    # Emergency Escalation
    {
        "text": "Severe crushing chest pain and profuse sweating right now.",
        "expected_intent": "emergency_escalation",
        "lang": "en",
    },
    {
        "text": "Chhati mein tez dabaav aur dard ho raha hai, left arm mein fail raha hai.",
        "expected_intent": "emergency_escalation",
        "lang": "hinglish",
    },
    {"text": "सीने में असहनीय दर्द हो रहा है और सांस नहीं आ रही।", "expected_intent": "emergency_escalation", "lang": "hi"},
    {
        "text": "Patient has collapsed and is unresponsive on the floor.",
        "expected_intent": "emergency_escalation",
        "lang": "en",
    },
    # App Meta / Settings / Pricing
    {
        "text": "What is the subscription fee for Disha AI nutritionist plan?",
        "expected_intent": "app_meta",
        "lang": "en",
    },
    {"text": "Disha AI kya hai aur nutritionist fees kitni hai?", "expected_intent": "app_meta", "lang": "hinglish"},
    {"text": "इस ऐप का सब्सक्रिप्शन चार्ज कितना है?", "expected_intent": "app_meta", "lang": "hi"},
    {"text": "How to use this app and where is my profile tab?", "expected_intent": "app_meta", "lang": "en"},
]


# =============================================================================
# 1. Indian Multilingual Intent Classification Accuracy
# =============================================================================


@pytest.mark.asyncio
async def test_accurate_intent_classification_indian_health_queries():
    """Verifies that LayaClassifierAdapter accurately classifies Indian health queries
    across Hinglish, Hindi, and English into all 6 clinical intents.
    """
    adapter = LayaClassifierAdapter(model_name="multilingual")
    correct = 0

    for case in INDIAN_HEALTH_CASES:
        res = await adapter.classify(case["text"])
        expected = case["expected_intent"]
        actual = res.intent

        if expected == "emergency_escalation":
            matched = res.is_emergency or actual == "emergency_escalation"
        else:
            matched = (actual == expected) and not res.is_emergency

        assert matched, (
            f"Case '{case['text']}' (lang: {case['lang']}) mismatched: "
            f"expected={expected}, actual={actual}, is_emg={res.is_emergency}"
        )
        correct += 1

    accuracy = (correct / len(INDIAN_HEALTH_CASES)) * 100.0
    assert accuracy == 100.0, f"Expected 100% accuracy on curated Indian suite, got {accuracy:.1f}%"


# =============================================================================
# 2. Retrieval Routing & Short-Circuiting Verification
# =============================================================================


@pytest.mark.asyncio
async def test_retrieval_routing_and_short_circuiting():
    """Verifies that:
    1. Greeting, General Coaching, and App Meta SKIP pgvector retrieval (skip_retrieval=True).
    2. Symptom, Meal, and Exercise queries route to targeted domain retrieval.
    """
    router = IntentRouter()

    # Queries that MUST skip retrieval
    skip_queries = [
        "Namaste Disha",
        "Hello good morning",
        "Tips for improving my deep sleep and stress levels",
        "How many steps should I walk daily?",
        "What is Disha AI and how much is the subscription fee?",
        "Where can I find the My Plan tab in the app?",
    ]

    for q in skip_queries:
        decision = await router.async_route_decision(q)
        assert decision.skip_retrieval is True, (
            f"Query '{q}' (intent={decision.intent}) should have skip_retrieval=True"
        )
        assert decision.intent in {
            Intent.GENERAL_COACHING,
            Intent.APP_META,
            Intent.GREETING,
            Intent.EMERGENCY_TRIAGE,
        }

    # Queries that MUST perform domain retrieval
    retrieval_queries = [
        ("Khana khane ke baad pet phool raha hai aur gas ho rahi hai.", Intent.SYMPTOM_COMPLAINT),
        ("What should I eat for dinner tonight?", Intent.MEAL_QUERY),
        ("Can I do heavy deadlifts and squats at the gym?", Intent.EXERCISE_QUERY),
    ]

    for q, exp_intent in retrieval_queries:
        decision = await router.async_route_decision(q)
        assert decision.skip_retrieval is False, (
            f"Query '{q}' (intent={decision.intent}) should have skip_retrieval=False"
        )
        assert decision.intent == exp_intent


@pytest.mark.asyncio
async def test_pipeline_skips_database_retrieval_on_coaching_and_meta():
    """Verifies in the end-to-end turn generator that when intent is general coaching or app meta,
    database retrieval is NOT called and connection pool is not touched for chunks.
    """
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire.return_value = cm
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=tx)

    # Setup mock patient context return
    mock_conn.fetchrow.return_value = {
        "hypertension_stage": "Stage 1",
        "gym_clearance": True,
        "allowed_modalities": ["walking", "yoga"],
        "restricted_modalities": ["heavy_deadlifts"],
        "language": "hinglish",
    }
    mock_conn.fetch.return_value = []

    mock_llm = MagicMock()

    async def _mock_stream(prompt, messages=None):
        yield "Namaste! Deep sleep ke liye raat ko phone dur rakhein."

    mock_llm.stream = _mock_stream

    app_state = SimpleNamespace(
        router=IntentRouter(),
        validator=SentenceValidator(),
        llm=mock_llm,
        pool=mock_pool,
        today_ist=lambda: "monday",
    )
    request = SimpleNamespace(state=app_state)

    with (
        patch("disha_core.main.retrieve_chunks") as mock_retrieve,
        patch("disha_core.harness.harness.retrieve_chunks", side_effect=mock_retrieve),
    ):
        # 1. Turn with General Coaching -> retrieval must be skipped!
        payload = TurnRequest(text="Help me stay motivated today")
        state = TurnState()
        sentences = [s async for s in generate_turn_sentences(request, "pt_test_01", payload, state)]
        assert len(sentences) > 0
        mock_retrieve.assert_not_called()

        # 2. Turn with App Meta -> retrieval must be skipped!
        payload_meta = TurnRequest(text="How much does the nutritionist subscription cost?")
        state_meta = TurnState()
        sentences_meta = [s async for s in generate_turn_sentences(request, "pt_test_01", payload_meta, state_meta)]
        assert len(sentences_meta) > 0
        mock_retrieve.assert_not_called()

        # 3. Turn with Symptom Complaint -> retrieval MUST be called!
        mock_retrieve.return_value = [
            {
                "chunk_id": 1,
                "condition_tag": "GI_BLOATING",
                "context_header": "[Scope: Functional Dyspepsia]",
                "guideline_content": "Suggest warm jeera or saunf water.",
                "source_citation": "ICMR Guidelines",
                "required_remedy_tokens": ["jeera", "saunf"],
            }
        ]
        payload_symptom = TurnRequest(text="Pet mein gas aur bloating ho rahi hai")
        state_symptom = TurnState()
        _ = [s async for s in generate_turn_sentences(request, "pt_test_01", payload_symptom, state_symptom)]
        assert mock_retrieve.called, "retrieve_chunks should have been called for symptom_complaint"


# =============================================================================
# 3. PEP Risk Triage & Early Safety Bounds
# =============================================================================


@pytest.mark.asyncio
async def test_pep_risk_flagging_for_high_risk_exercise():
    """Verifies that:
    1. Laya System 1 flags high-exertion requests as pep_risk == 2.
    2. The turn pipeline early-detects restricted modalities for cardiac/hypertension patients
       and immediately triggers PEP_REPLACEMENT safety bounds without LLM hallucination.
    """
    adapter = LayaClassifierAdapter(model_name="multilingual")

    # High-risk exercise request
    high_risk_query = "Can I do heavy deadlifts and max effort squats at the gym?"
    res = await adapter.classify(high_risk_query)
    assert res.pep_risk >= 2, f"Expected pep_risk >= 2 for heavy deadlifts, got {res.pep_risk}"
    assert res.intent == "exercise_query"

    # Moderate / Low risk exercise request
    low_risk_query = "Can I go for a gentle 20 minute morning walk?"
    res_low = await adapter.classify(low_risk_query)
    assert res_low.pep_risk <= 1, f"Expected pep_risk <= 1 for gentle walk, got {res_low.pep_risk}"

    # Verify Early PEP Safety Bound in Pipeline
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire.return_value = cm
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=tx)

    # Patient has cardiac restrictions against heavy deadlifts
    mock_conn.fetchrow.return_value = {
        "hypertension_stage": "Stage 1",
        "gym_clearance": False,
        "allowed_modalities": ["walking", "gentle_yoga"],
        "restricted_modalities": ["heavy_deadlifts", "valsalva_maneuver"],
        "language": "hinglish",
    }
    mock_conn.fetch.return_value = []

    mock_llm = MagicMock()
    # LLM should NEVER be called when early PEP restriction fires!
    mock_llm.stream.side_effect = AssertionError("LLM stream must not be invoked on early PEP restriction!")

    app_state = SimpleNamespace(
        router=IntentRouter(),
        validator=SentenceValidator(),
        llm=mock_llm,
        pool=mock_pool,
        today_ist=lambda: "monday",
    )
    request = SimpleNamespace(state=app_state)

    payload = TurnRequest(text="Aaj gym mein 100kg deadlift aur heavy weights kar sakta hoon?")
    state = TurnState()

    sentences = [s async for s in generate_turn_sentences(request, "pt_cardiac_01", payload, state)]
    assert len(sentences) == 1
    assert sentences[0] == PEP_REPLACEMENT
    assert state.validator_status == "rewritten:pep_restriction"


# =============================================================================
# 4. Review Queue Capture on Edge Cases & Low Confidence
# =============================================================================


@pytest.mark.asyncio
async def test_review_queue_captures_subthreshold_and_ambiguous_turns():
    """Verifies that sub-threshold confidence (<0.7) or ambiguous intent classifications
    are captured into ReviewQueueManager for clinician audit.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "audit_review_queue.db"
        review_mgr = ReviewQueueManager(db_path=db_path)

        adapter = LayaClassifierAdapter(model_name="multilingual")
        adapter.set_review_queue(review_mgr)

        # 1. Turn with sub-threshold confidence (<0.70)
        # Ambiguous Indian greeting / lifestyle query
        res = await adapter.classify("Good morning Disha, namaste")
        # In Laya, "Good morning Disha, namaste" has confidence around ~0.40 - 0.50 (< 0.70)
        assert res.confidence < 0.70

        # Verify review queue item persisted
        items = review_mgr.list_items()
        assert len(items) >= 1
        latest = items[0]
        assert latest.trigger_type == TriggerType.LOW_CONFIDENCE
        assert latest.model_decision.intent_confidence < 0.70
        assert "Disha" in latest.scrubbed_input_text or "namaste" in latest.scrubbed_input_text.lower()
        assert latest.anonymized_patient_token.startswith("pt_")

        # 2. Fallback edge case (circuit breaker / offline fallback)
        res_fallback = adapter._fallback_classification(
            "Call 9876543210: mujhe ajeeb sa lag raha hai",
            "low_confidence_gate",
            10.0,
        )
        assert res_fallback.is_fallback is True

        items_after = review_mgr.list_items()
        assert len(items_after) >= 2
        # Verify phone number was scrubbed before enqueueing!
        scrubbed_texts = [item.scrubbed_input_text for item in items_after]
        assert any("[PHONE_REDACTED]" in txt for txt in scrubbed_texts)
        assert not any("9876543210" in txt for txt in scrubbed_texts)


# =============================================================================
# 5. Latency SLA (<25ms cached / fallback)
# =============================================================================


@pytest.mark.asyncio
async def test_laya_cache_and_fallback_latency_under_25ms():
    """Verifies that:
    1. Cached Laya results execute in <25ms (in fact <2ms).
    2. Fallback classification executes in <25ms.
    Ensures zero obstruction to first-token latency of chat/voice.
    """
    adapter = LayaClassifierAdapter(model_name="multilingual")

    query = "What should I eat for dinner tonight?"

    # Warmup / Initial inference
    await adapter.classify(query)

    # 1. Cache hit benchmark
    cache_latencies: list[float] = []
    for _ in range(20):
        t0 = time.monotonic()
        res = await adapter.classify(query)
        dt = (time.monotonic() - t0) * 1000.0
        cache_latencies.append(dt)
        assert res.intent == "meal_query"

    cache_p50 = sorted(cache_latencies)[len(cache_latencies) // 2]
    assert cache_p50 < 25.0, f"Cache P50 latency exceeded 25ms SLA: {cache_p50:.2f}ms"
    assert cache_p50 < 2.0, f"Cache hit should be sub-2ms, got {cache_p50:.2f}ms"

    # 2. Deterministic fallback benchmark
    fallback_latencies: list[float] = []
    for _ in range(20):
        t0 = time.monotonic()
        res_fb = adapter._fallback_classification("Dinner mein kya khana hai?", "circuit_open", 0.0)
        dt = (time.monotonic() - t0) * 1000.0
        fallback_latencies.append(dt)
        assert res_fb.intent == "meal_query"

    fb_p50 = sorted(fallback_latencies)[len(fallback_latencies) // 2]
    assert fb_p50 < 25.0, f"Fallback P50 latency exceeded 25ms SLA: {fb_p50:.2f}ms"
