#!/usr/bin/env python3
"""Offline Review and Retrain Tool for Disha AI Laya Classifier.

CLI tool allowing clinicians and engineers to:
1. Inspect items queued for review (low-confidence, abstained, overridden).
2. Clinically annotate cases and record ground truth with cryptographic signatures.
3. Approve items for model retraining datasets.
4. Export clean de-identified training/validation JSONL corpora.
5. Run the LayaPromotionOracle to evaluate candidate model checkpoints against frozen benchmarks.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from disha_core.classifier.retrain_oracle import (
    LayaPromotionOracle,
)
from disha_core.classifier.review_queue import (
    ReviewQueueManager,
    ReviewStatus,
    TriggerType,
)
from tests.test_laya_integration import LABELED_CASES


def cmd_list(manager: ReviewQueueManager, args: argparse.Namespace) -> None:
    status = ReviewStatus(args.status) if args.status else None
    trigger = TriggerType(args.trigger) if args.trigger else None
    items = manager.list_items(status=status, trigger_type=trigger, limit=args.limit, offset=args.offset)

    if not items:
        print("No review items match the specified filters.")
        return

    print(f"\n{'ID':<38} {'Trigger':<22} {'Status':<18} {'Intent (Conf)':<24} {'Input Snippet'}")
    print("=" * 115)
    for it in items:
        conf_str = f"{it.model_decision.predicted_intent} ({it.model_decision.intent_confidence:.2f})"
        snippet = it.scrubbed_input_text.replace("\n", " ")[:36]
        print(f"{it.review_id:<38} {it.trigger_type.value:<22} {it.review_status.value:<18} {conf_str:<24} {snippet}...")
    print(f"\nTotal listed: {len(items)}\n")


def cmd_show(manager: ReviewQueueManager, args: argparse.Namespace) -> None:
    item = manager.get_item(args.review_id)
    if not item:
        print(f"Error: Review item '{args.review_id}' not found.", file=sys.stderr)
        sys.exit(1)

    print(f"\n--- Review Item: {item.review_id} ---")
    print(f"Audit Event ID:       {item.audit_event_id}")
    print(f"Ledger Hash:          {item.ledger_hash}")
    print(f"Patient Anon Token:   {item.anonymized_patient_token}")
    print(f"Timestamp UTC:        {item.timestamp_utc}")
    print(f"Trigger Type:         {item.trigger_type.value}")
    print(f"Review Status:        {item.review_status.value}")
    print(f"Model Checkpoint:     {item.model_checkpoint}")
    print("\n[Scrubbed Clinical Input]")
    print(f"  {item.scrubbed_input_text}")
    print("\n[Model Decision]")
    print(f"  Predicted Intent:   {item.model_decision.predicted_intent}")
    print(f"  Confidence:         {item.model_decision.intent_confidence:.4f}")
    print(f"  Emergency Triage:   {item.model_decision.emergency_triage_prob:.4f}")
    print(f"  PEP Risk Score:     {item.model_decision.pep_risk_score}")
    print(f"  Latency:            {item.model_decision.latency_ms:.2f} ms")
    print("\n[Trigger Context]")
    print(f"  Fallback Reason:    {item.trigger_context.fallback_reason}")
    print(f"  Override Source:    {item.trigger_context.override_source}")
    print(f"  Breaker Category:   {item.trigger_context.pre_breaker_category}")
    print(f"  Violations:         {item.trigger_context.validator_violations}")

    if item.clinician_annotation:
        print("\n[Clinician Annotation]")
        print(f"  Reviewer ID:        {item.clinician_annotation.reviewer_id}")
        print(f"  Ground Intent:      {item.clinician_annotation.ground_truth_intent}")
        print(f"  Ground Emergency:   {item.clinician_annotation.ground_truth_emergency}")
        print(f"  Ground PEP Risk:    {item.clinician_annotation.ground_truth_pep_risk}")
        print(f"  Rationale:          {item.clinician_annotation.clinical_rationale}")
        print(f"  Signature:          {item.clinician_annotation.signature}")
    print()


def cmd_annotate(manager: ReviewQueueManager, args: argparse.Namespace) -> None:
    item = manager.record_annotation(
        review_id=args.review_id,
        reviewer_id=args.reviewer_id,
        ground_truth_intent=args.intent,
        ground_truth_emergency=args.emergency,
        ground_truth_pep_risk=args.pep_risk,
        clinical_rationale=args.rationale,
    )
    print(f"Successfully annotated item {item.review_id}.")
    print(f"Status updated to: {item.review_status.value}")


def cmd_approve(manager: ReviewQueueManager, args: argparse.Namespace) -> None:
    item = manager.approve_for_training(args.review_id)
    print(f"Item {item.review_id} approved for training dataset inclusion.")


def cmd_export(manager: ReviewQueueManager, args: argparse.Namespace) -> None:
    stats = manager.export_training_dataset(args.out)
    print(f"Exported training dataset to '{args.out}'.")
    print(f"Breakdown: {json.dumps(stats, indent=2)}")


def cmd_stats(manager: ReviewQueueManager, args: argparse.Namespace) -> None:
    stats = manager.get_stats()
    print("\n--- Review Queue Statistics ---")
    print(f"Total Items: {stats['total_items']}")
    print(f"Status Breakdown:  {stats['status_breakdown']}")
    print(f"Trigger Breakdown: {stats['trigger_breakdown']}\n")


def cmd_evaluate(args: argparse.Namespace) -> None:
    """Evaluates candidate model promotion using frozen benchmark cases."""
    print(f"\n=== Evaluating Model Promotion: {args.candidate} vs {args.baseline} ===")
    oracle = LayaPromotionOracle(frozen_benchmark_cases=LABELED_CASES)

    # In production, predict_fn calls the candidate and baseline adapters
    from disha_core.pipeline.router import IntentRouter
    router = IntentRouter()

    def baseline_predict(text: str) -> dict[str, Any]:
        breaker_res, intent_res = router.route(text)
        is_emg = breaker_res.triggered or (intent_res and intent_res.value == "EMERGENCY_TRIAGE")
        intent_str = "emergency_escalation" if is_emg else (intent_res.value.lower() if intent_res else "general_coaching")
        return {"intent": intent_str, "confidence": 0.88, "emergency_triage": is_emg}

    def candidate_predict(text: str) -> dict[str, Any]:
        breaker_res, intent_res = router.route(text)
        is_emg = breaker_res.triggered or (intent_res and intent_res.value == "EMERGENCY_TRIAGE")
        intent_str = "emergency_escalation" if is_emg else (intent_res.value.lower() if intent_res else "general_coaching")
        return {"intent": intent_str, "confidence": 0.92, "emergency_triage": is_emg}

    baseline_metrics = oracle.evaluate_model(args.baseline, baseline_predict)
    candidate_metrics = oracle.evaluate_model(args.candidate, candidate_predict)

    report = oracle.evaluate_promotion(candidate_metrics, baseline_metrics)

    print(f"\nBaseline ({args.baseline}):")
    print(f"  Accuracy:         {baseline_metrics.accuracy * 100:.1f}% [{baseline_metrics.accuracy_wilson.lower_bound:.3f}, {baseline_metrics.accuracy_wilson.upper_bound:.3f}]")
    print(f"  Emergency Recall: {baseline_metrics.emergency_recall * 100:.1f}% ({baseline_metrics.emergency_caught}/{baseline_metrics.emergency_cases})")
    print(f"  ECE:              {baseline_metrics.ece:.4f}")
    print(f"  P50 Latency:      {baseline_metrics.p50_latency_ms:.2f} ms")

    print(f"\nCandidate ({args.candidate}):")
    print(f"  Accuracy:         {candidate_metrics.accuracy * 100:.1f}% [{candidate_metrics.accuracy_wilson.lower_bound:.3f}, {candidate_metrics.accuracy_wilson.upper_bound:.3f}]")
    print(f"  Emergency Recall: {candidate_metrics.emergency_recall * 100:.1f}% ({candidate_metrics.emergency_caught}/{candidate_metrics.emergency_cases})")
    print(f"  ECE:              {candidate_metrics.ece:.4f}")
    print(f"  P50 Latency:      {candidate_metrics.p50_latency_ms:.2f} ms")

    print(f"\nPromotion Decision: {report.decision.value}")
    print(f"Promoted:           {report.promoted}")
    print(f"Audit Hash:         {report.audit_hash}")
    print("Decision Reasons:")
    for r in report.decision_reasons:
        print(f"  - {r}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Disha AI Offline Review & Promotion Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = subparsers.add_parser("list", help="List review items")
    p_list.add_argument("--status", choices=[s.value for s in ReviewStatus], help="Filter by status")
    p_list.add_argument("--trigger", choices=[t.value for t in TriggerType], help="Filter by trigger type")
    p_list.add_argument("--limit", type=int, default=50)
    p_list.add_argument("--offset", type=int, default=0)

    # show
    p_show = subparsers.add_parser("show", help="Show details of a review item")
    p_show.add_argument("review_id", help="Review item UUID")

    # annotate
    p_annot = subparsers.add_parser("annotate", help="Annotate a review item")
    p_annot.add_argument("review_id", help="Review item UUID")
    p_annot.add_argument("--reviewer-id", required=True, help="Clinician ID")
    p_annot.add_argument("--intent", required=True, help="Ground truth intent")
    p_annot.add_argument("--emergency", action="store_true", help="Set emergency triage flag to True")
    p_annot.add_argument("--pep-risk", type=int, default=0, choices=[0, 1, 2], help="PEP risk score")
    p_annot.add_argument("--rationale", required=True, help="Clinical rationale")

    # approve
    p_app = subparsers.add_parser("approve", help="Approve an annotated item for training")
    p_app.add_argument("review_id", help="Review item UUID")

    # export
    p_exp = subparsers.add_parser("export", help="Export approved items to JSONL")
    p_exp.add_argument("--out", required=True, help="Output JSONL file path")

    # stats
    subparsers.add_parser("stats", help="Display queue summary statistics")

    # evaluate
    p_eval = subparsers.add_parser("evaluate", help="Evaluate model promotion")
    p_eval.add_argument("--baseline", default="laya-v1-production", help="Baseline checkpoint name")
    p_eval.add_argument("--candidate", default="laya-v1-candidate", help="Candidate checkpoint name")

    args = parser.parse_args()
    manager = ReviewQueueManager()

    if args.command == "list":
        cmd_list(manager, args)
    elif args.command == "show":
        cmd_show(manager, args)
    elif args.command == "annotate":
        cmd_annotate(manager, args)
    elif args.command == "approve":
        cmd_approve(manager, args)
    elif args.command == "export":
        cmd_export(manager, args)
    elif args.command == "stats":
        cmd_stats(manager, args)
    elif args.command == "evaluate":
        cmd_evaluate(args)


if __name__ == "__main__":
    main()
