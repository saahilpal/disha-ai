"""Latency Profiler Suite.

Sub-turn micro-benchmarks executing 1,000 iterations each for breaker.py,
retriever.py (pg_trgm), and validator.py, computing P50, P95, and P99 percentiles.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from disha_core.engine.retriever import retrieve_chunks
from disha_core.pipeline.breaker import EmergencyBreaker
from disha_core.pipeline.validator import SentenceValidator


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1
    if c < len(sorted_vals):
        return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])
    return sorted_vals[f]


def _benchmark_breaker(iterations: int = 1000) -> dict[str, Any]:
    breaker = EmergencyBreaker()
    test_utterances = [
        "mujhe pet mein halka dard ho raha hai",
        "chhati mein dard ho raha hai",
        "aaj ka breakfast kya hona chahiye",
        "dum ghut raha hai saans nahi aa rahi",
        "kya main walking shuru kar sakta hoon",
    ]
    timings_ms: list[float] = []

    for i in range(iterations):
        text = test_utterances[i % len(test_utterances)]
        t0 = time.perf_counter()
        _ = breaker.check(text)
        dt = (time.perf_counter() - t0) * 1000.0
        timings_ms.append(dt)

    p50 = _percentile(timings_ms, 50.0)
    p95 = _percentile(timings_ms, 95.0)
    p99 = _percentile(timings_ms, 99.0)

    # Hard target: P95 < 0.05ms
    passed = p95 < 0.05
    return {
        "iterations": iterations,
        "p50_ms": round(p50, 4),
        "p95_ms": round(p95, 4),
        "p99_ms": round(p99, 4),
        "target_ms": "< 0.05ms",
        "passed": passed,
    }


def _benchmark_validator(iterations: int = 1000) -> dict[str, Any]:
    validator = SentenceValidator()
    test_sentences = [
        "Follow-up consultations ₹0 hain aur dedicated plan ₹1,499 per month hai.",
        "Aap daily 30 minutes brisk walking kar sakte hain.",
        "Is meal ka prescribed plan My Plan tab mein check karein.",
        "Main Disha hoon, aapki AI health coach.",
        "Warm jeera aur saunf ka paani pijiye digestion ke liye.",
    ]
    context = {"pep": {"allowed_modalities": ["brisk_walking"], "gym_clearance": True}}
    timings_ms: list[float] = []

    for i in range(iterations):
        sentence = test_sentences[i % len(test_sentences)]
        t0 = time.perf_counter()
        _ = validator.validate_sentence(sentence, context)
        dt = (time.perf_counter() - t0) * 1000.0
        timings_ms.append(dt)

    p50 = _percentile(timings_ms, 50.0)
    p95 = _percentile(timings_ms, 95.0)
    p99 = _percentile(timings_ms, 99.0)

    # Hard target: P95 < 2.0ms per sentence
    passed = p95 < 2.0
    return {
        "iterations": iterations,
        "p50_ms": round(p50, 4),
        "p95_ms": round(p95, 4),
        "p99_ms": round(p99, 4),
        "target_ms": "< 2.0ms",
        "passed": passed,
    }


async def _benchmark_retriever(iterations: int = 1000) -> dict[str, Any]:
    import asyncpg

    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    db_url = f"postgresql://disha:{password}@127.0.0.1:5432/disha"
    conn = await asyncpg.connect(db_url)

    test_queries = [
        "pet phoolna gas acidity indigestion",
        "bloating relief remedy",
        "mango aam fruit moderation",
        "high blood pressure diet salt",
        "saunf jeera water digestion",
    ]
    timings_ms: list[float] = []

    try:
        # Warmup
        for q in test_queries:
            await retrieve_chunks(conn, q, use_cache=False)

        for i in range(iterations):
            query = test_queries[i % len(test_queries)]
            t0 = time.perf_counter()
            _ = await retrieve_chunks(conn, query, use_cache=False)
            dt = (time.perf_counter() - t0) * 1000.0
            timings_ms.append(dt)
    finally:
        await conn.close()

    p50 = _percentile(timings_ms, 50.0)
    p95 = _percentile(timings_ms, 95.0)
    p99 = _percentile(timings_ms, 99.0)

    # Hard target: P95 < 2.0ms
    passed = p95 < 2.0
    return {
        "iterations": iterations,
        "p50_ms": round(p50, 4),
        "p95_ms": round(p95, 4),
        "p99_ms": round(p99, 4),
        "target_ms": "< 2.0ms",
        "passed": passed,
    }


def run_latency_profiler(iterations: int = 1000) -> dict[str, Any]:
    """Execute all micro-benchmarks across breaker, validator, and retriever."""
    breaker_stats = _benchmark_breaker(iterations)
    validator_stats = _benchmark_validator(iterations)

    loop = asyncio.new_event_loop()
    try:
        retriever_stats = loop.run_until_complete(_benchmark_retriever(iterations))
    finally:
        loop.close()

    overall_passed = breaker_stats["passed"] and validator_stats["passed"] and retriever_stats["passed"]
    total_p95_overhead = (
        breaker_stats["p95_ms"] + validator_stats["p95_ms"] + retriever_stats["p95_ms"]
    )
    score = 100.0 if overall_passed else (66.6 if sum(1 for s in (breaker_stats, validator_stats, retriever_stats) if s["passed"]) == 2 else 33.3)

    return {
        "suite": "latency_profiler",
        "passed": overall_passed,
        "score": score,
        "total_deterministic_p95_overhead_ms": round(total_p95_overhead, 4),
        "budget_limit_ms": 35.0,
        "within_35ms_budget": total_p95_overhead < 35.0,
        "components": {
            "breaker": breaker_stats,
            "validator": validator_stats,
            "retriever_pg_trgm": retriever_stats,
        },
    }


if __name__ == "__main__":
    import json
    res = run_latency_profiler(iterations=1000)
    print(json.dumps(res, indent=2))

