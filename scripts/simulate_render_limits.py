"""Simulate Render free-tier constraints (0.1 vCPU, 512MB RAM) to evaluate Laya memory and latency headroom."""

from __future__ import annotations

import os
import resource
import sys
import time
from pathlib import Path

# Add repo to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def get_rss_mb() -> float:
    # ru_maxrss is in KB on Linux, bytes on macOS
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return usage / (1024 * 1024)
    return usage / 1024


def main():
    print("=== Render Free-Tier Simulation Test ===")
    t_start = time.perf_counter()

    initial_rss = get_rss_mb()
    print(f"Initial Process RSS: {initial_rss:.2f} MB")

    # Measure cold start import time
    t0 = time.perf_counter()
    from disha_core.classifier.adapter import LayaClassifierAdapter

    import_time_s = time.perf_counter() - t0
    rss_after_import = get_rss_mb()
    print(f"Laya Module Import Time: {import_time_s:.2f}s | RSS: {rss_after_import:.2f} MB")

    # Initialize adapter
    t0 = time.perf_counter()
    adapter = LayaClassifierAdapter(model_name="multilingual")
    init_time_s = time.perf_counter() - t0
    rss_after_init = get_rss_mb()
    print(f"Laya Model Init Time: {init_time_s:.2f}s | RSS: {rss_after_init:.2f} MB")

    # Run warm-up classification
    t0 = time.perf_counter()
    import asyncio

    warmup_res = asyncio.run(adapter.classify("Warmup check"))
    warmup_lat_ms = (time.perf_counter() - t0) * 1000.0
    rss_after_warmup = get_rss_mb()
    print(f"Warmup Latency: {warmup_lat_ms:.2f}ms | RSS: {rss_after_warmup:.2f} MB")

    # Run 10 inference turns
    test_queries = [
        "Mere pet me gas ho rahi hai kya karu",
        "Aaj lunch me moong dal khayi thi",
        "Severe crushing chest pain and sweating",
        "BP ki dawai subah leni hai ya shaam ko",
        "Walk karne ke baad thakan lag rahi hai",
        "Khichdi ke saath dahi kha sakte hain?",
        "Doctor ne namak kam karne bola hai",
        "Can I do heavy weight lifting today?",
        "Subah se sar me dard hai",
        "What should I eat for breakfast tomorrow?",
    ]

    latencies = []
    for q in test_queries:
        t0 = time.perf_counter()
        _ = asyncio.run(adapter.classify(q))
        lat = (time.perf_counter() - t0) * 1000.0
        latencies.append(lat)

    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[int(len(latencies) * 0.95)]
    peak_rss = get_rss_mb()
    total_time = time.perf_counter() - t_start

    print("\n--- RESULTS ---")
    print(f"Total Execution Time: {total_time:.2f}s")
    print(f"Peak RSS Memory: {peak_rss:.2f} MB")
    print(f"Memory Headroom (vs 512MB): {512.0 - peak_rss:.2f} MB")
    print(f"Inference Latencies (n={len(latencies)}): P50={p50:.2f}ms | P95={p95:.2f}ms")

    # Pass/Fail criteria for Render Free Tier:
    # Headroom >= 100MB and P95 <= 150ms
    headroom_pass = (512.0 - peak_rss) >= 100.0
    latency_pass = p95 <= 150.0

    print(f"Headroom Check (>=100MB): {'PASS' if headroom_pass else 'FAIL'}")
    print(f"Latency SLA Check (P95 <= 150ms): {'PASS' if latency_pass else 'FAIL'}")

    if not latency_pass or not headroom_pass:
        print("\nDECISION TRIGGERED: Laya exceeds Render 0.1 vCPU / 512MB SLA.")
        print("Fallback required: Set LAYA_ENABLED=false behind feature flag, defaulting to regex/rule intent router.")


if __name__ == "__main__":
    main()
