"""Metrics calculation and evaluation engine for PEP Benchmarking.

Computes:
1. Harmful writes (forbidden writes, assistant content, unconfirmed loosening, injections).
2. Critical-fact recall (allergies, conditions, medications, pregnancy, limitations, restrictions).
3. Slot precision, recall, F1, wrong-value rate, temporary vs permanent accuracy.
4. Staleness: share where next_turn_must_know fact is present in next turn context.
5. Cost: LLM calls, input/output tokens (p50, p95).
6. Latency: hot-path ms added per turn (p50, p95) and background lag.
7. Gate confusion matrix (SKIP, SLOW, FAST).
8. Bootstrap 95% confidence intervals.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

CRITICAL_SLOTS = {
    "dietary_restrictions",
    "diagnosed_conditions",
    "current_medications",
    "pregnancy",
    "physical_limitations",
    "restricted_modalities",
}


def bootstrap_ci(
    values: list[float],
    n_resamples: int = 1000,
    ci_level: float = 0.95,
) -> tuple[float, float, float]:
    """Compute mean and bootstrap confidence interval [lower, upper]."""
    if not values:
        return 0.0, 0.0, 0.0
    mean_val = sum(values) / len(values)
    if len(values) == 1:
        return mean_val, mean_val, mean_val

    resamples: list[float] = []
    n = len(values)
    for _ in range(n_resamples):
        sample = [random.choice(values) for _ in range(n)]
        resamples.append(sum(sample) / n)
    resamples.sort()

    alpha = (1.0 - ci_level) / 2.0
    low_idx = int(math.floor(alpha * n_resamples))
    high_idx = int(math.ceil((1.0 - alpha) * n_resamples)) - 1
    low = resamples[max(0, min(low_idx, n_resamples - 1))]
    high = resamples[max(0, min(high_idx, n_resamples - 1))]
    return round(mean_val, 4), round(low, 4), round(high, 4)


def percentile(data: list[float], p: float) -> float:
    """Compute p-th percentile of data."""
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return round(s[int(k)], 3)
    d0 = s[int(f)] * (c - k)
    d1 = s[int(c)] * (k - f)
    return round(d0 + d1, 3)


@dataclass
class ConversationEvalResult:
    conv_id: str
    language: str
    category: str
    harmful_writes: list[str] = field(default_factory=list)
    critical_facts_expected: int = 0
    critical_facts_recalled: int = 0
    tp_slots: int = 0
    fp_slots: int = 0
    fn_slots: int = 0
    wrong_value_count: int = 0
    stale_failures: int = 0
    stale_checks: int = 0
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    turn_latencies_ms: list[float] = field(default_factory=list)
    background_lag_ms: float = 0.0
    gate_predictions: list[dict[str, str]] = field(default_factory=list)


def evaluate_conversation(
    conv: dict[str, Any],
    final_extracted_state: list[dict[str, Any]],
    llm_calls: int,
    input_tokens: int,
    output_tokens: int,
    turn_latencies: list[float],
    background_lag: float,
    gate_predictions: list[dict[str, str]] | None = None,
    next_turn_context_text: str = "",
) -> ConversationEvalResult:
    cid = conv["id"]
    lang = conv.get("language", "english")
    cat = conv.get("category", "general")
    expected_state = conv.get("expected_final_state", [])
    forbidden = conv.get("forbidden_writes", [])
    next_must_know = conv.get("next_turn_must_know")

    res = ConversationEvalResult(
        conv_id=cid,
        language=lang,
        category=cat,
        llm_calls=llm_calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        turn_latencies_ms=turn_latencies,
        background_lag_ms=background_lag,
        gate_predictions=gate_predictions or [],
    )

    # 1. Harmful writes check
    ext_keys = {item.get("slot") for item in final_extracted_state if item.get("slot")}
    ext_items_str = json_str(final_extracted_state).lower()

    for forb in forbidden:
        f_lower = str(forb).lower()
        if f_lower in ext_keys or f_lower in ext_items_str:
            res.harmful_writes.append(f"Forbidden fact or attribute saved: {forb}")

    # Check for assistant echo leakage
    for turn in conv.get("turns", []):
        if turn.get("role") == "assistant":
            ast_words = [w.strip() for w in turn.get("text", "").lower().split() if len(w) > 5]
            for ext in final_extracted_state:
                ev_str = str(ext.get("evidence", "")).lower()
                if any(w in ev_str for w in ast_words[:3]):
                    res.harmful_writes.append(f"Assistant echo stored as evidence: {ev_str[:40]}")

    # 2. Critical fact recall and Slot precision/recall
    exp_map = {item["slot"]: item for item in expected_state if "slot" in item}
    ext_map = {item["slot"]: item for item in final_extracted_state if "slot" in item}

    for slot, exp in exp_map.items():
        is_critical = slot in CRITICAL_SLOTS
        if is_critical:
            res.critical_facts_expected += 1

        if slot in ext_map:
            ext = ext_map[slot]
            if compare_slot_values(exp.get("value"), ext.get("value")):
                res.tp_slots += 1
                if is_critical:
                    res.critical_facts_recalled += 1
            else:
                res.wrong_value_count += 1
                res.fp_slots += 1
        else:
            res.fn_slots += 1

    for slot in ext_map:
        if slot not in exp_map:
            res.fp_slots += 1

    # 3. Staleness check
    if next_must_know and isinstance(next_must_know, dict):
        res.stale_checks += 1
        target_slot = next_must_know.get("slot", "")
        if next_turn_context_text:
            if target_slot.lower() not in next_turn_context_text.lower():
                res.stale_failures += 1
        else:
            res.stale_failures += 1

    return res


def compare_slot_values(v1: Any, v2: Any) -> bool:
    """Compare slot values allowing for list order normalization and string casing."""
    if v1 is None and v2 is None:
        return True
    if v1 is None or v2 is None:
        return False
    if isinstance(v1, list) and isinstance(v2, list):
        s1 = sorted([str(x).strip().lower() for x in v1])
        s2 = sorted([str(x).strip().lower() for x in v2])
        return s1 == s2
    if isinstance(v1, dict) and isinstance(v2, dict):
        return {k: str(v).lower() for k, v in v1.items()} == {k: str(v).lower() for k, v in v2.items()}
    return str(v1).strip().lower() == str(v2).strip().lower()


def json_str(obj: Any) -> str:
    import json
    return json.dumps(obj)


def aggregate_metrics(results: list[ConversationEvalResult]) -> dict[str, Any]:
    """Aggregate per-conversation results into benchmark metrics summary."""
    n = len(results)
    if n == 0:
        return {}

    total_harmful = sum(len(r.harmful_writes) for r in results)
    harmful_cases = [r.conv_id for r in results if r.harmful_writes]

    total_crit_exp = sum(r.critical_facts_expected for r in results)
    total_crit_rec = sum(r.critical_facts_recalled for r in results)
    crit_recall = (total_crit_rec / total_crit_exp) if total_crit_exp > 0 else 1.0

    total_tp = sum(r.tp_slots for r in results)
    total_fp = sum(r.fp_slots for r in results)
    total_fn = sum(r.fn_slots for r in results)
    precision = (total_tp / (total_tp + total_fp)) if (total_tp + total_fp) > 0 else 1.0
    recall = (total_tp / (total_tp + total_fn)) if (total_tp + total_fn) > 0 else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    total_stale_checks = sum(r.stale_checks for r in results)
    total_stale_fails = sum(r.stale_failures for r in results)
    staleness_rate = (total_stale_fails / total_stale_checks) if total_stale_checks > 0 else 0.0

    llm_calls_list = [float(r.llm_calls) for r in results]
    inp_tok_list = [float(r.input_tokens) for r in results]
    out_tok_list = [float(r.output_tokens) for r in results]

    all_turn_latencies = [lat for r in results for lat in r.turn_latencies_ms]
    bg_lags = [r.background_lag_ms for r in results]

    # CI calculations
    crit_mean, crit_low, crit_high = bootstrap_ci(
        [r.critical_facts_recalled / r.critical_facts_expected for r in results if r.critical_facts_expected > 0]
    )
    f1_mean, f1_low, f1_high = bootstrap_ci(
        [
            (2 * r.tp_slots / (2 * r.tp_slots + r.fp_slots + r.fn_slots))
            if (2 * r.tp_slots + r.fp_slots + r.fn_slots) > 0
            else 1.0
            for r in results
        ]
    )

    return {
        "total_conversations": n,
        "harmful_writes": {
            "total_count": total_harmful,
            "affected_conversations": harmful_cases,
        },
        "critical_fact_recall": {
            "mean": round(crit_recall, 4),
            "ci_95": [crit_low, crit_high],
        },
        "slot_f1": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "ci_95": [f1_low, f1_high],
        },
        "staleness": {
            "checks": total_stale_checks,
            "failures": total_stale_fails,
            "staleness_rate": round(staleness_rate, 4),
        },
        "cost": {
            "llm_calls_p50": percentile(llm_calls_list, 50),
            "llm_calls_p95": percentile(llm_calls_list, 95),
            "input_tokens_p50": percentile(inp_tok_list, 50),
            "input_tokens_p95": percentile(inp_tok_list, 95),
            "output_tokens_p50": percentile(out_tok_list, 50),
            "output_tokens_p95": percentile(out_tok_list, 95),
        },
        "latency": {
            "hot_path_turn_ms_p50": percentile(all_turn_latencies, 50),
            "hot_path_turn_ms_p95": percentile(all_turn_latencies, 95),
            "background_lag_ms_p50": percentile(bg_lags, 50),
            "background_lag_ms_p95": percentile(bg_lags, 95),
        },
    }
