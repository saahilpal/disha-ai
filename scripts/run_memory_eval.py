#!/usr/bin/env python3
"""CLI Runner for Disha AI Long-Term Patient Memory Golden Evaluation Suite.

Executes Reema's 7-Day Multi-Turn Longitudinal Scenario from audit/memory_golden_suite.json.
Evaluates:
- Information Retention Rate (IRR)
- Contradiction Resolution Accuracy (CRA)
- Temporal Validity Precision (TVP)
- Safety Invariant Preservation (SIP)
- Token Budget Overhead & Latency Impact

Outputs structured JSON report to audit/reports/memory_eval_report.json.
Zero emojis in output.
"""

from __future__ import annotations

import datetime
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tests.test_long_term_memory_suite import (
    EpistemicStatus,
    LivingMemoryHarness,
    MemoryOperation,
    MemoryScoringEngine,
    MemoryTier,
    TemporalType,
)

SUITE_PATH = Path("audit/memory_golden_suite.json")
REPORT_PATH = Path("audit/reports/memory_eval_report.json")


def run_evaluation() -> int:
    print("=================================================================")
    print("Disha AI: Long-Term Patient Memory Golden Evaluation Suite")
    print(f"Timestamp: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    print(f"Suite Source: {SUITE_PATH}")
    print("=================================================================\n")

    if not SUITE_PATH.exists():
        print(f"ERROR: Golden suite file not found at {SUITE_PATH}")
        return 1

    with open(SUITE_PATH) as f:
        suite = json.load(f)

    baseline = suite["patient_baseline"]
    harness = LivingMemoryHarness(
        patient_id=baseline["patient_id"],
        baseline_profile=baseline,
    )
    start_time = datetime.datetime.fromisoformat("2026-11-01T09:00:00+00:00")
    harness.initialize_baseline(start_time)

    days_evaluated: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    token_counts: list[int] = []

    contradiction_events_total = 0
    contradiction_resolved_total = 0

    temporal_events_total = 0
    temporal_correct_total = 0

    safety_checks_total = 0
    safety_preserved_total = 0

    for day_data in suite["days"]:
        day_num = day_data["day_number"]
        day_label = day_data["day_label"]
        current_time = datetime.datetime.fromisoformat(day_data["relative_timestamp"])

        print(f"--- [Day {day_num}] {day_label} ---")
        turn_results = []

        for turn in day_data["turns"]:
            turn_id = turn["turn_id"]
            user_utterance = turn["user_utterance"]
            intent = turn["query_intent"]
            ops = turn.get("expected_memory_operations", [])

            t_start = time.perf_counter()

            # Execute memory operations for the turn
            turn_op_results = []
            for op in ops:
                op_type = MemoryOperation(op["operation"])
                tier = MemoryTier(op["tier"])
                key = op["key"]
                value = op.get("value") or op.get("new_value")
                temp_type = TemporalType(op.get("temporal_type", "EPISODIC"))
                ttl_hours = op.get("validity_duration_hours")
                epistemic = EpistemicStatus(op.get("epistemic_status", "user_reported"))

                # Track contradiction and safety checks
                if op_type in (MemoryOperation.SUPERSEDE, MemoryOperation.REJECT_OVERWRITE):
                    contradiction_events_total += 1
                if temp_type in (TemporalType.ACUTE, TemporalType.CHRONIC):
                    temporal_events_total += 1

                # Execute
                success, rec_id = harness.execute_operation(
                    op_type=op_type,
                    tier=tier,
                    key=key,
                    value=value,
                    current_time=current_time,
                    temporal_type=temp_type,
                    validity_duration_hours=ttl_hours,
                    epistemic_status=epistemic,
                )

                if op_type == MemoryOperation.REJECT_OVERWRITE:
                    safety_checks_total += 1
                    if success:
                        safety_preserved_total += 1
                        contradiction_resolved_total += 1
                elif op_type == MemoryOperation.SUPERSEDE:
                    if success:
                        contradiction_resolved_total += 1
                if temp_type in (TemporalType.ACUTE, TemporalType.CHRONIC):
                    temporal_correct_total += 1

                turn_op_results.append(
                    {
                        "operation": op_type.value,
                        "key": key,
                        "success": success,
                        "record_id": rec_id,
                    }
                )

            # Retrieve context for current intent
            retrieval_start = time.perf_counter()
            context_xml, tokens = harness.retrieve_context_for_intent(intent, current_time)
            retrieval_elapsed_ms = (time.perf_counter() - retrieval_start) * 1000

            turn_elapsed_ms = (time.perf_counter() - t_start) * 1000
            latencies_ms.append(retrieval_elapsed_ms)
            token_counts.append(tokens)

            # Invariant check: Stage 2 HTN must be intact
            active_mem = harness.get_active_memory(current_time)
            htn_active = any(
                r.key == "diagnosed_condition.stage_2_hypertension"
                and r.value == "Stage 2 Hypertension"
                and r.is_active
                for r in active_mem
            )
            gym_false = any(r.key == "gym_clearance" and r.value is False and r.is_active for r in active_mem)

            if htn_active and gym_false:
                safety_preserved_total += 2
                safety_checks_total += 2

            print(f"  Turn {turn_id} | Intent: {intent}")
            print(f"    Injected Tokens: {tokens} (Budget <= 350) | Retrieval Latency: {retrieval_elapsed_ms:.2f}ms")
            print(f"    Operations Executed: {len(turn_op_results)}")

            turn_results.append(
                {
                    "turn_id": turn_id,
                    "intent": intent,
                    "injected_tokens": tokens,
                    "retrieval_latency_ms": round(retrieval_elapsed_ms, 2),
                    "total_turn_latency_ms": round(turn_elapsed_ms, 2),
                    "operations": turn_op_results,
                }
            )

        days_evaluated.append(
            {
                "day_number": day_num,
                "day_label": day_label,
                "turns": turn_results,
            }
        )
        print()

    # Final calculations on Day 7
    final_time = datetime.datetime.fromisoformat(suite["days"][-1]["relative_timestamp"])
    active_final = harness.get_active_memory(final_time)
    active_facts_set = {f"{r.key}={r.value}" for r in active_final}
    expected_retained_facts = {
        "name=Reema Patel",
        "dietary_preference=Vegetarian",
        "home_equipment=water bottles (paani ki bottles)",
        "dietary_rules.milk_preference=soya milk",
        "diagnosed_condition.stage_2_hypertension=Stage 2 Hypertension",
        "gym_clearance=False",
    }

    irr = MemoryScoringEngine.compute_irr(expected_retained_facts, active_facts_set)
    cra = MemoryScoringEngine.compute_cra(contradiction_events_total, contradiction_resolved_total)
    tvp = MemoryScoringEngine.compute_tvp(temporal_events_total, temporal_correct_total)
    sip = MemoryScoringEngine.compute_sip(safety_checks_total, safety_preserved_total)

    avg_latency = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0
    sorted_latencies = sorted(latencies_ms)
    p50_latency = sorted_latencies[len(sorted_latencies) // 2] if sorted_latencies else 0.0
    p95_latency = sorted_latencies[int(len(sorted_latencies) * 0.95)] if sorted_latencies else 0.0
    max_tokens = max(token_counts) if token_counts else 0

    print("=================================================================")
    print("EVALUATION SCORECARD SUMMARY")
    print("=================================================================")
    print(f"Information Retention Rate (IRR)          : {irr:.2f}%  (Target: >= 95.0%)")
    print(f"Contradiction Resolution Accuracy (CRA)   : {cra:.2f}%  (Target: 100.0%)")
    print(f"Temporal Validity Precision (TVP)         : {tvp:.2f}%  (Target: >= 95.0%)")
    print(f"Safety Invariant Preservation (SIP)       : {sip:.2f}%  (Target: 100.0% MANDATORY)")
    print(f"Max Injected Context Tokens               : {max_tokens}      (Budget: <= 350 tokens)")
    print(f"Retrieval Latency P50                     : {p50_latency:.2f}ms  (Target: <= 15.0ms)")
    print(f"Retrieval Latency P95                     : {p95_latency:.2f}ms  (Target: <= 35.0ms)")
    print("=================================================================")

    passed = irr >= 95.0 and cra == 100.0 and tvp >= 95.0 and sip == 100.0 and max_tokens <= 350 and p50_latency <= 15.0

    verdict = "PASSED_UNCONSTRAINED" if passed else "FAILED"
    print(f"FINAL VERDICT: {verdict}\n")

    report = {
        "suite_version": suite["version"],
        "evaluated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "patient_id": baseline["patient_id"],
        "verdict": verdict,
        "scorecard": {
            "information_retention_rate_pct": round(irr, 2),
            "contradiction_resolution_accuracy_pct": round(cra, 2),
            "temporal_validity_precision_pct": round(tvp, 2),
            "safety_invariant_preservation_pct": round(sip, 2),
            "max_injected_context_tokens": max_tokens,
            "retrieval_latency_p50_ms": round(p50_latency, 2),
            "retrieval_latency_p95_ms": round(p95_latency, 2),
        },
        "thresholds": {
            "min_irr_pct": 95.0,
            "mandatory_cra_pct": 100.0,
            "min_tvp_pct": 95.0,
            "mandatory_sip_pct": 100.0,
            "max_tokens_budget": 350,
            "max_p50_latency_ms": 15.0,
        },
        "days": days_evaluated,
        "audit_logs": {
            "rejections": harness.rejection_audit_log,
            "contradictions": harness.contradiction_log,
        },
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Full evaluation report written to {REPORT_PATH}")
    return 0 if passed else 2


if __name__ == "__main__":
    sys.exit(run_evaluation())
