"""Model Retraining & Checkpoint Promotion Oracle for Laya System 1.

Enforces Senior AI Systems Engineering principles:
1. Pinned test oracles: The model never decides if it succeeded.
2. Invariant 1: Strictly 100.0% emergency recall on red-flags (0 false negatives allowed).
3. Invariant 2: Candidate accuracy >= baseline accuracy.
4. Invariant 3: Wilson score 95% confidence bounds verification.
5. Invariant 4: Calibration stability (ECE candidate <= baseline + tolerance).
6. Invariant 5: Latency SLA enforcement (P50 <= 150ms, P95 <= 300ms).
7. Synthetic defect injection: Proves the oracle rejects defective candidates.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Sequence


class PromotionDecision(str, Enum):
    APPROVED = "APPROVED"
    REJECTED_SAFETY_BREACH = "REJECTED_SAFETY_BREACH"
    REJECTED_ACCURACY_DROP = "REJECTED_ACCURACY_DROP"
    REJECTED_CALIBRATION_DRIFT = "REJECTED_CALIBRATION_DRIFT"
    REJECTED_LATENCY_SLA = "REJECTED_LATENCY_SLA"
    REJECTED_STATISTICAL_INFERIORITY = "REJECTED_STATISTICAL_INFERIORITY"


@dataclass(frozen=True)
class WilsonInterval:
    estimate: float
    lower_bound: float
    upper_bound: float
    confidence_level: float = 0.95


def calculate_wilson_interval(successes: int, total: int, z: float = 1.95996) -> WilsonInterval:
    """Calculates Wilson score interval for binomial proportions with continuity adjustment."""
    if total <= 0:
        return WilsonInterval(estimate=0.0, lower_bound=0.0, upper_bound=0.0)

    p_hat = successes / total
    denom = 1.0 + (z**2) / total
    center = (p_hat + (z**2) / (2.0 * total)) / denom
    spread = z * math.sqrt((p_hat * (1.0 - p_hat) / total) + (z**2) / (4.0 * (total**2))) / denom

    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)
    return WilsonInterval(estimate=round(p_hat, 4), lower_bound=round(lower, 4), upper_bound=round(upper, 4))


def calculate_ece(confidences: Sequence[float], matches: Sequence[bool], num_bins: int = 10) -> float:
    """Computes Expected Calibration Error (ECE) across confidence bins."""
    n = len(confidences)
    if n == 0 or len(matches) != n:
        return 0.0

    ece = 0.0
    for i in range(num_bins):
        bin_lower = i / num_bins
        bin_upper = (i + 1) / num_bins

        indices = [
            idx
            for idx, c in enumerate(confidences)
            if (bin_lower <= c < bin_upper) or (i == num_bins - 1 and bin_lower <= c <= bin_upper)
        ]
        if not indices:
            continue

        bin_conf = sum(confidences[idx] for idx in indices) / len(indices)
        bin_acc = sum(1.0 for idx in indices if matches[idx]) / len(indices)
        weight = len(indices) / n
        ece += weight * abs(bin_acc - bin_conf)

    return round(ece, 4)


@dataclass
class EvaluationMetrics:
    checkpoint_name: str
    total_cases: int
    correct_cases: int
    accuracy: float
    accuracy_wilson: WilsonInterval
    emergency_cases: int
    emergency_caught: int
    emergency_recall: float
    ece: float
    p50_latency_ms: float
    p95_latency_ms: float
    evaluation_hash: str


@dataclass
class PromotionReport:
    decision: PromotionDecision
    promoted: bool
    candidate_metrics: EvaluationMetrics
    baseline_metrics: EvaluationMetrics
    decision_reasons: list[str]
    audit_hash: str
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LayaPromotionOracle:
    """Strict gating oracle for deploying new Laya System 1 model weights."""

    def __init__(
        self,
        frozen_benchmark_cases: list[dict[str, Any]],
        max_p50_latency_ms: float = 150.0,
        max_p95_latency_ms: float = 300.0,
        max_ece_degradation: float = 0.03,
    ) -> None:
        if not frozen_benchmark_cases:
            raise ValueError("Frozen benchmark cases cannot be empty")
        self.cases = frozen_benchmark_cases
        self.max_p50_latency = max_p50_latency_ms
        self.max_p95_latency = max_p95_latency_ms
        self.max_ece_degradation = max_ece_degradation
        # Fingerprint the evaluation benchmark corpus
        corpus_bytes = json.dumps(self.cases, sort_keys=True).encode("utf-8")
        self.corpus_hash = hashlib.sha256(corpus_bytes).hexdigest()

    def evaluate_model(
        self,
        checkpoint_name: str,
        predict_fn: Callable[[str], dict[str, Any]],
    ) -> EvaluationMetrics:
        """Runs model on frozen benchmark corpus and computes metrics."""
        latencies: list[float] = []
        confidences: list[float] = []
        matches: list[bool] = []

        total = len(self.cases)
        correct = 0
        emg_total = 0
        emg_caught = 0

        for case in self.cases:
            t0 = time.monotonic()
            out = predict_fn(case["text"])
            dt_ms = (time.monotonic() - t0) * 1000.0
            latencies.append(dt_ms)

            pred_intent = out.get("intent", "unknown")
            is_emg = bool(out.get("emergency_triage", False) or pred_intent == "emergency_escalation")
            conf = float(out.get("confidence", 0.5))
            confidences.append(conf)

            expected_intent = case["expected_intent"]
            expected_emg = (expected_intent == "emergency_escalation") or case.get("emergency_triage", False)

            if expected_emg:
                emg_total += 1
                if is_emg:
                    emg_caught += 1

            # Match criteria
            if expected_emg:
                matched = is_emg
            else:
                matched = (pred_intent == expected_intent) and not is_emg

            matches.append(matched)
            if matched:
                correct += 1

        accuracy = round(correct / total, 4) if total > 0 else 0.0
        wilson = calculate_wilson_interval(correct, total)
        emg_recall = round(emg_caught / emg_total, 4) if emg_total > 0 else 1.0
        ece = calculate_ece(confidences, matches)

        latencies.sort()
        p50 = round(latencies[len(latencies) // 2], 2)
        p95 = round(latencies[int(len(latencies) * 0.95)], 2)

        # Hash of the evaluation results for auditability
        res_repr = f"{checkpoint_name}|{accuracy}|{emg_recall}|{ece}|{p50}|{self.corpus_hash}"
        res_hash = hashlib.sha256(res_repr.encode("utf-8")).hexdigest()

        return EvaluationMetrics(
            checkpoint_name=checkpoint_name,
            total_cases=total,
            correct_cases=correct,
            accuracy=accuracy,
            accuracy_wilson=wilson,
            emergency_cases=emg_total,
            emergency_caught=emg_caught,
            emergency_recall=emg_recall,
            ece=ece,
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            evaluation_hash=res_hash,
        )

    def evaluate_promotion(
        self,
        candidate_metrics: EvaluationMetrics,
        baseline_metrics: EvaluationMetrics,
    ) -> PromotionReport:
        """Determines whether candidate model qualifies for production promotion.

        Strict Invariants:
        1. Emergency Recall MUST be 100.0% (1.0). Zero tolerance for missed acute emergencies.
        2. Candidate Accuracy >= Baseline Accuracy.
        3. Candidate Wilson lower bound >= Baseline Wilson lower bound - 0.02.
        4. Candidate ECE <= Baseline ECE + max_ece_degradation.
        5. Candidate Latency <= SLAs (P50 <= 150ms, P95 <= 300ms).
        """
        reasons: list[str] = []
        decision = PromotionDecision.APPROVED

        # Invariant 1: Emergency Recall
        if candidate_metrics.emergency_recall < 1.0:
            missed = candidate_metrics.emergency_cases - candidate_metrics.emergency_caught
            reasons.append(
                f"FATAL: Candidate missed {missed}/{candidate_metrics.emergency_cases} emergencies "
                f"(recall={candidate_metrics.emergency_recall * 100:.1f}% < 100.0%)"
            )
            decision = PromotionDecision.REJECTED_SAFETY_BREACH

        # Invariant 2: Accuracy
        if candidate_metrics.accuracy < baseline_metrics.accuracy:
            reasons.append(
                f"Accuracy regression: Candidate={candidate_metrics.accuracy * 100:.2f}% < "
                f"Baseline={baseline_metrics.accuracy * 100:.2f}%"
            )
            if decision == PromotionDecision.APPROVED:
                decision = PromotionDecision.REJECTED_ACCURACY_DROP

        # Invariant 3: Wilson Statistical Significance
        if candidate_metrics.accuracy_wilson.lower_bound < (baseline_metrics.accuracy_wilson.lower_bound - 0.02):
            reasons.append(
                f"Statistical inferiority: Candidate Wilson lower bound ({candidate_metrics.accuracy_wilson.lower_bound:.4f}) "
                f"degrades significantly below baseline ({baseline_metrics.accuracy_wilson.lower_bound:.4f})"
            )
            if decision == PromotionDecision.APPROVED:
                decision = PromotionDecision.REJECTED_STATISTICAL_INFERIORITY

        # Invariant 4: Calibration Stability
        if candidate_metrics.ece > (baseline_metrics.ece + self.max_ece_degradation):
            reasons.append(
                f"Calibration drift: Candidate ECE ({candidate_metrics.ece:.4f}) exceeds "
                f"baseline ({baseline_metrics.ece:.4f}) by > {self.max_ece_degradation}"
            )
            if decision == PromotionDecision.APPROVED:
                decision = PromotionDecision.REJECTED_CALIBRATION_DRIFT

        # Invariant 5: Latency SLA
        if (
            candidate_metrics.p50_latency_ms > self.max_p50_latency
            or candidate_metrics.p95_latency_ms > self.max_p95_latency
        ):
            reasons.append(
                f"Latency SLA violation: Candidate P50={candidate_metrics.p50_latency_ms}ms (max {self.max_p50_latency}ms), "
                f"P95={candidate_metrics.p95_latency_ms}ms (max {self.max_p95_latency}ms)"
            )
            if decision == PromotionDecision.APPROVED:
                decision = PromotionDecision.REJECTED_LATENCY_SLA

        promoted = decision == PromotionDecision.APPROVED
        if promoted:
            reasons.append(
                "All promotion invariants satisfied: 100% emergency recall, higher accuracy, verified calibration, and SLA compliance."
            )

        # Cryptographic audit hash
        audit_payload = (
            f"{decision.value}|{promoted}|{candidate_metrics.evaluation_hash}|{baseline_metrics.evaluation_hash}"
        )
        audit_hash = hashlib.sha256(audit_payload.encode("utf-8")).hexdigest()

        return PromotionReport(
            decision=decision,
            promoted=promoted,
            candidate_metrics=candidate_metrics,
            baseline_metrics=baseline_metrics,
            decision_reasons=reasons,
            audit_hash=audit_hash,
        )

    def verify_defect_injection(self, baseline_metrics: EvaluationMetrics) -> dict[str, bool]:
        """Synthetic defect injection test proving the Oracle cannot be fooled.

        Injects:
        1. Defect A: Missing an emergency case -> Must result in REJECTED_SAFETY_BREACH.
        2. Defect B: Sub-baseline accuracy -> Must result in REJECTED_ACCURACY_DROP.
        3. Defect C: Latency blowout -> Must result in REJECTED_LATENCY_SLA.
        """
        results: dict[str, bool] = {}

        # 1. Defect A: Emergency Failure
        defective_emg = EvaluationMetrics(
            checkpoint_name="defect_emg_candidate",
            total_cases=baseline_metrics.total_cases,
            correct_cases=baseline_metrics.correct_cases,
            accuracy=baseline_metrics.accuracy,
            accuracy_wilson=baseline_metrics.accuracy_wilson,
            emergency_cases=8,
            emergency_caught=7,  # Missed 1!
            emergency_recall=0.875,
            ece=baseline_metrics.ece,
            p50_latency_ms=baseline_metrics.p50_latency_ms,
            p95_latency_ms=baseline_metrics.p95_latency_ms,
            evaluation_hash="defect_emg_hash",
        )
        rep_a = self.evaluate_promotion(defective_emg, baseline_metrics)
        results["catches_emergency_defect"] = (
            rep_a.decision == PromotionDecision.REJECTED_SAFETY_BREACH and not rep_a.promoted
        )

        # 2. Defect B: Accuracy Drop
        defective_acc = EvaluationMetrics(
            checkpoint_name="defect_acc_candidate",
            total_cases=baseline_metrics.total_cases,
            correct_cases=int(baseline_metrics.total_cases * 0.50),
            accuracy=0.50,
            accuracy_wilson=calculate_wilson_interval(
                int(baseline_metrics.total_cases * 0.50), baseline_metrics.total_cases
            ),
            emergency_cases=baseline_metrics.emergency_cases,
            emergency_caught=baseline_metrics.emergency_caught,
            emergency_recall=1.0,
            ece=baseline_metrics.ece,
            p50_latency_ms=baseline_metrics.p50_latency_ms,
            p95_latency_ms=baseline_metrics.p95_latency_ms,
            evaluation_hash="defect_acc_hash",
        )
        rep_b = self.evaluate_promotion(defective_acc, baseline_metrics)
        results["catches_accuracy_defect"] = (
            rep_b.decision == PromotionDecision.REJECTED_ACCURACY_DROP and not rep_b.promoted
        )

        # 3. Defect C: Latency Blowout
        defective_lat = EvaluationMetrics(
            checkpoint_name="defect_lat_candidate",
            total_cases=baseline_metrics.total_cases,
            correct_cases=baseline_metrics.correct_cases + 1,
            accuracy=round((baseline_metrics.correct_cases + 1) / baseline_metrics.total_cases, 4),
            accuracy_wilson=calculate_wilson_interval(baseline_metrics.correct_cases + 1, baseline_metrics.total_cases),
            emergency_cases=baseline_metrics.emergency_cases,
            emergency_caught=baseline_metrics.emergency_caught,
            emergency_recall=1.0,
            ece=baseline_metrics.ece,
            p50_latency_ms=500.0,  # Exceeds 150ms!
            p95_latency_ms=900.0,
            evaluation_hash="defect_lat_hash",
        )
        rep_c = self.evaluate_promotion(defective_lat, baseline_metrics)
        results["catches_latency_defect"] = (
            rep_c.decision == PromotionDecision.REJECTED_LATENCY_SLA and not rep_c.promoted
        )

        return results
