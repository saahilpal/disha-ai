"""Comprehensive Test Suite for Self-Learning Loop, Zero-PHI Queue, and Model Promotion Oracle.

Enforces:
1. Deterministic Zero-PHI scrubbing and HMAC pseudonymization.
2. Review queue persistence, filtering, and clinician audit lifecycle.
3. Model Promotion Oracle invariants:
   - 100.0% Emergency Recall (Zero False Negatives).
   - Candidate Accuracy >= Baseline Accuracy.
   - Wilson score statistical confidence bounds.
   - ECE calibration stability.
   - P50/P95 latency SLA compliance.
4. Synthetic Defect Injection (Mutation Testing) proving the Oracle cannot be fooled.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from disha_core.classifier.retrain_oracle import (
    EvaluationMetrics,
    LayaPromotionOracle,
    PromotionDecision,
    calculate_ece,
    calculate_wilson_interval,
)
from disha_core.classifier.review_queue import (
    ReviewQueueManager,
    ReviewStatus,
    TriggerType,
    ZeroPHIScrubber,
)

FROZEN_SAMPLE_CASES = [
    # 2 Emergency cases
    {"text": "Severe crushing chest pain radiating to left arm", "expected_intent": "emergency_escalation", "emergency_triage": True},
    {"text": "Saas lene mein bohot takleef hai, dum ghut raha hai", "expected_intent": "emergency_escalation", "emergency_triage": True},
    # 2 Meal queries
    {"text": "What should I eat for dinner tonight?", "expected_intent": "meal_query", "emergency_triage": False},
    {"text": "Aaj lunch mein kya le sakta hoon?", "expected_intent": "meal_query", "emergency_triage": False},
    # 2 Symptom complaints
    {"text": "Pet mein gas aur bloating ho rahi hai", "expected_intent": "symptom_complaint", "emergency_triage": False},
    {"text": "Mild acidity since afternoon", "expected_intent": "symptom_complaint", "emergency_triage": False},
    # 2 General coaching
    {"text": "How many steps should I walk daily?", "expected_intent": "general_coaching", "emergency_triage": False},
    {"text": "Tips for improving deep sleep", "expected_intent": "general_coaching", "emergency_triage": False},
]


def test_zero_phi_scrubber_redaction_and_tokenization():
    """Verifies that all direct PHI markers are redacted and patient ID is HMAC pseudonymized."""
    scrubber = ZeroPHIScrubber(salt=b"test-secret-salt-12345")

    # Patient ID tokenization
    token1 = scrubber.pseudonymize_patient_id("patient_uuid_9999")
    token2 = scrubber.pseudonymize_patient_id("patient_uuid_9999")
    token3 = scrubber.pseudonymize_patient_id("patient_uuid_8888")

    assert token1.startswith("pt_")
    assert token1 == token2, "HMAC tokenization must be deterministic for identical patient_id"
    assert token1 != token3, "Different patient_ids must produce different HMAC tokens"
    assert "patient_uuid_9999" not in token1

    # Phone number scrubbing
    text_phone = "Call me at +91 9876543210 or 9123456789 regarding my symptoms."
    clean_phone, mod_phone = scrubber.scrub(text_phone)
    assert mod_phone is True
    assert "+91 9876543210" not in clean_phone
    assert "9123456789" not in clean_phone
    assert "[PHONE_REDACTED]" in clean_phone

    # Aadhaar scrubbing
    text_aadhaar = "Aadhaar number is 1234 5678 9012 for verification."
    clean_aadhaar, mod_aadhaar = scrubber.scrub(text_aadhaar)
    assert mod_aadhaar is True
    assert "1234 5678 9012" not in clean_aadhaar
    assert "[AADHAAR_REDACTED]" in clean_aadhaar

    # Email & MRN scrubbing
    text_mrn = "Email me at patient.care@apollo.com, MRN-482910"
    clean_mrn, mod_mrn = scrubber.scrub(text_mrn)
    assert mod_mrn is True
    assert "patient.care@apollo.com" not in clean_mrn
    assert "MRN-482910" not in clean_mrn
    assert "[EMAIL_REDACTED]" in clean_mrn
    assert "[MRN_REDACTED]" in clean_mrn

    # Name introduction scrubbing
    text_name = "My name is Rajesh Sharma and I feel dizzy."
    clean_name, mod_name = scrubber.scrub(text_name)
    assert mod_name is True
    assert "Rajesh Sharma" not in clean_name
    assert "[NAME_REDACTED]" in clean_name


def test_review_queue_lifecycle_and_export():
    """Tests the full review queue workflow: enqueue, annotate, approve, and export dataset."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_review_queue.db"
        manager = ReviewQueueManager(db_path=db_path)

        # 1. Enqueue low-confidence decision
        item1 = manager.enqueue_decision(
            raw_user_input="My phone is +91 9876543210. What can I eat for dinner?",
            patient_id="pat_12345",
            audit_event_id="00000000-0000-0000-0000-000000000001",
            ledger_hash="sha256_mock_head_1",
            trigger_type=TriggerType.LOW_CONFIDENCE,
            model_checkpoint="convaiinnovations/laya-v1.0.0",
            predicted_intent="meal_query",
            intent_confidence=0.38,  # Below 0.40 threshold
            emergency_triage_prob=0.02,
            pep_risk_score=0,
            latency_ms=88.5,
            fallback_reason="low_confidence_gate",
        )

        assert item1.review_status == ReviewStatus.PENDING
        assert "[PHONE_REDACTED]" in item1.scrubbed_input_text
        assert "+91 9876543210" not in item1.scrubbed_input_text
        assert item1.anonymized_patient_token.startswith("pt_")

        # 2. Enqueue Breaker Override decision
        item2 = manager.enqueue_decision(
            raw_user_input="Severe chest pain and sweating",
            patient_id="pat_67890",
            audit_event_id="00000000-0000-0000-0000-000000000002",
            ledger_hash="sha256_mock_head_2",
            trigger_type=TriggerType.BREAKER_OVERRIDE,
            model_checkpoint="convaiinnovations/laya-v1.0.0",
            predicted_intent="symptom_complaint",
            intent_confidence=0.75,
            emergency_triage_prob=0.45,
            pep_risk_score=2,
            latency_ms=92.1,
            override_source="deterministic_breaker",
            pre_breaker_category="cardiac",
        )

        assert item2.trigger_type == TriggerType.BREAKER_OVERRIDE
        assert item2.trigger_context.pre_breaker_category == "cardiac"

        # 3. List and filter items
        pending_items = manager.list_items(status=ReviewStatus.PENDING)
        assert len(pending_items) == 2

        breaker_items = manager.list_items(trigger_type=TriggerType.BREAKER_OVERRIDE)
        assert len(breaker_items) == 1
        assert breaker_items[0].review_id == item2.review_id

        # 4. Clinician Annotation
        annotated_item = manager.record_annotation(
            review_id=item2.review_id,
            reviewer_id="dr_sharma_cardiologist",
            ground_truth_intent="emergency_escalation",
            ground_truth_emergency=True,
            ground_truth_pep_risk=2,
            clinical_rationale="Acute coronary syndrome red-flag; immediate emergency escalation required.",
        )

        assert annotated_item.review_status == ReviewStatus.ANNOTATED
        assert annotated_item.clinician_annotation is not None
        assert annotated_item.clinician_annotation.ground_truth_intent == "emergency_escalation"
        assert len(annotated_item.clinician_annotation.signature) == 64

        # 5. Approve for training
        approved_item = manager.approve_for_training(item2.review_id)
        assert approved_item.review_status == ReviewStatus.APPROVED_FOR_TRAINING

        # Unannotated item cannot be approved
        with pytest.raises(ValueError):
            manager.approve_for_training(item1.review_id)

        # 6. Export training dataset
        export_path = Path(tmpdir) / "exported_train.jsonl"
        stats = manager.export_training_dataset(export_path)
        assert stats["total_exported"] == 1
        assert stats["emergency_escalation"] == 1

        with open(export_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) == 1
            record = json.loads(lines[0])
            assert record["expected_intent"] == "emergency_escalation"
            assert record["emergency_triage"] is True
            assert "pat_67890" not in json.dumps(record)  # Zero PHI


def test_wilson_interval_and_calibration():
    """Verifies statistical calculation properties of Wilson confidence intervals and ECE."""
    # Wilson interval properties:
    # 1. Exact 100% successes
    w_100 = calculate_wilson_interval(10, 10)
    assert w_100.estimate == 1.0
    assert w_100.lower_bound > 0.65
    assert w_100.upper_bound == 1.0

    # 2. Exact 0% successes
    w_0 = calculate_wilson_interval(0, 10)
    assert w_0.estimate == 0.0
    assert w_0.lower_bound == 0.0
    assert w_0.upper_bound < 0.35

    # 3. 50% successes
    w_50 = calculate_wilson_interval(50, 100)
    assert w_50.estimate == 0.50
    assert 0.39 < w_50.lower_bound < 0.42
    assert 0.58 < w_50.upper_bound < 0.61

    # ECE (Expected Calibration Error)
    # Perfectly calibrated: confidence 0.8 on 8/10 correct matches
    confs_perfect = [0.8] * 10
    matches_perfect = [True] * 8 + [False] * 2
    ece_perf = calculate_ece(confs_perfect, matches_perfect)
    assert ece_perf == 0.0, "Perfect calibration must yield ECE == 0.0"

    # Completely miscalibrated: confidence 1.0 but 0/10 correct
    confs_mis = [1.0] * 10
    matches_mis = [False] * 10
    ece_mis = calculate_ece(confs_mis, matches_mis)
    assert ece_mis == 1.0, "Total miscalibration must yield ECE == 1.0"


def test_promotion_oracle_enforces_100_percent_emergency_recall():
    """CRITICAL SAFETY INVARIANT: Candidate missing even 1 emergency is immediately rejected."""
    oracle = LayaPromotionOracle(frozen_benchmark_cases=FROZEN_SAMPLE_CASES)

    baseline_metrics = EvaluationMetrics(
        checkpoint_name="laya_baseline_v1",
        total_cases=8,
        correct_cases=7,
        accuracy=0.875,
        accuracy_wilson=calculate_wilson_interval(7, 8),
        emergency_cases=2,
        emergency_caught=2,
        emergency_recall=1.0,  # 100% emergency recall
        ece=0.04,
        p50_latency_ms=90.0,
        p95_latency_ms=110.0,
        evaluation_hash="baseline_hash",
    )

    # Candidate has higher overall accuracy (8/8 = 100% on everything except it misses 1 emergency)
    # Invariant check: candidate misses 1 emergency -> FATAL REJECTION
    candidate_metrics_flawed = EvaluationMetrics(
        checkpoint_name="laya_candidate_flawed",
        total_cases=8,
        correct_cases=7,
        accuracy=0.875,
        accuracy_wilson=calculate_wilson_interval(7, 8),
        emergency_cases=2,
        emergency_caught=1,  # MISSED 1 EMERGENCY!
        emergency_recall=0.50,
        ece=0.03,
        p50_latency_ms=85.0,
        p95_latency_ms=105.0,
        evaluation_hash="flawed_hash",
    )

    report = oracle.evaluate_promotion(candidate_metrics_flawed, baseline_metrics)
    assert report.promoted is False
    assert report.decision == PromotionDecision.REJECTED_SAFETY_BREACH
    assert any("FATAL: Candidate missed" in r for r in report.decision_reasons)


def test_promotion_oracle_approves_superior_candidate():
    """Verifies that a valid candidate model exceeding baseline on all invariants is approved."""
    oracle = LayaPromotionOracle(frozen_benchmark_cases=FROZEN_SAMPLE_CASES)

    baseline_metrics = EvaluationMetrics(
        checkpoint_name="laya_baseline_v1",
        total_cases=8,
        correct_cases=6,
        accuracy=0.75,
        accuracy_wilson=calculate_wilson_interval(6, 8),
        emergency_cases=2,
        emergency_caught=2,
        emergency_recall=1.0,
        ece=0.06,
        p50_latency_ms=95.0,
        p95_latency_ms=120.0,
        evaluation_hash="baseline_hash",
    )

    candidate_metrics_superior = EvaluationMetrics(
        checkpoint_name="laya_candidate_superior",
        total_cases=8,
        correct_cases=8,
        accuracy=1.0,
        accuracy_wilson=calculate_wilson_interval(8, 8),
        emergency_cases=2,
        emergency_caught=2,
        emergency_recall=1.0,
        ece=0.02,
        p50_latency_ms=88.0,
        p95_latency_ms=105.0,
        evaluation_hash="superior_hash",
    )

    report = oracle.evaluate_promotion(candidate_metrics_superior, baseline_metrics)
    assert report.promoted is True
    assert report.decision == PromotionDecision.APPROVED
    assert len(report.audit_hash) == 64


def test_synthetic_defect_injection_audit():
    """Falsifiability test: proves that synthetic defects are caught and rejected."""
    oracle = LayaPromotionOracle(frozen_benchmark_cases=FROZEN_SAMPLE_CASES)
    baseline_metrics = EvaluationMetrics(
        checkpoint_name="laya_baseline_v1",
        total_cases=8,
        correct_cases=7,
        accuracy=0.875,
        accuracy_wilson=calculate_wilson_interval(7, 8),
        emergency_cases=2,
        emergency_caught=2,
        emergency_recall=1.0,
        ece=0.04,
        p50_latency_ms=90.0,
        p95_latency_ms=110.0,
        evaluation_hash="baseline_hash",
    )

    defect_results = oracle.verify_defect_injection(baseline_metrics)
    assert defect_results["catches_emergency_defect"] is True
    assert defect_results["catches_accuracy_defect"] is True
    assert defect_results["catches_latency_defect"] is True


@pytest.mark.asyncio
async def test_adapter_review_queue_automatic_ingestion():
    """Verifies adapter automatically queues fallback/low confidence events into ReviewQueueManager."""
    from disha_core.classifier.adapter import LayaClassifierAdapter

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_hook_queue.db"
        manager = ReviewQueueManager(db_path=db_path)

        adapter = LayaClassifierAdapter(min_confidence=0.99)  # Force low-confidence gate
        adapter.set_review_queue(manager)

        # Trigger fallback via low-confidence gate
        res = adapter._fallback_classification(
            "Call 9876543210: What should I eat for dinner?",
            "low_confidence_gate",
            12.5,
        )

        assert res.is_fallback is True

        # Check queue
        items = manager.list_items()
        assert len(items) == 1
        item = items[0]
        assert item.trigger_type == TriggerType.LOW_CONFIDENCE
        assert "[PHONE_REDACTED]" in item.scrubbed_input_text
        assert "9876543210" not in item.scrubbed_input_text
        assert item.review_status == ReviewStatus.PENDING

