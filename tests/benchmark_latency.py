import asyncio
import statistics
import time
from typing import List, Dict
from app.orchestrator.turn_manager import turn_orchestrator

SAMPLE_UTTERANCES = [
    "Yeh app paid hai kya? Kitne ka subscription hai?",
    "Mujhe periods ke chalte bahut bloating ho rahi hai",
    "Mujhe mera diet chart WhatsApp par bhej do",
    "Aap sach mein insaan ho ya robot ho?",
    "Workout karte waqt seene mein dard aur left hand numb ho raha hai",
    "Chhati mein dabav hai aur ulta haath sunn ho gaya hai",
    "Aaj dinner mein kya hai mere diet chart ke hisaab se?",
    "Maine kal gym join kiya hai, wahan workout karoon?",
    "Kya main weight loss ke time aam (mangoes) kha sakti hoon?",
    "Namaste Disha ji, aaj meri tabiyat achhi hai",
    "Subah se pet mein halka dard hai",
    "Main intermittent fasting start karna chahti hoon",
    "Aap kaun ho?",
    "Kitne paise lagenge subscription ke?",
    "Gym mein kitna weight uthana chahiye?"
]

async def run_latency_benchmark(num_iterations: int = 50) -> Dict[str, float]:
    """
    Executes multiple voice simulation turns to calculate latency percentiles
    across all stages of the Thick Deterministic Spine.
    """
    total_latencies: List[float] = []
    guard_latencies: List[float] = []
    rag_latencies: List[float] = []
    sanitizer_latencies: List[float] = []

    print(f"\n=======================================================")
    print(f"  DISHA CLINICAL VOICE ENGINE — LATENCY BENCHMARK")
    print(f"  Target SLA Turn Latency: <1,200ms (P95)")
    print(f"  Executing {num_iterations} turns across randomized Hinglish prompts...")
    print(f"=======================================================\n")

    for i in range(num_iterations):
        utt = SAMPLE_UTTERANCES[i % len(SAMPLE_UTTERANCES)]
        result = await turn_orchestrator.execute_turn(
            patient_id="pt_101",
            utterance=utt,
            turn_number=i + 1
        )
        total_latencies.append(result.latency.total_ms)
        guard_latencies.append(result.latency.guardrail_ms)
        rag_latencies.append(result.latency.retrieval_ms)
        sanitizer_latencies.append(result.latency.sanitizer_ms)

    # Compute percentiles
    total_latencies.sort()
    p50 = statistics.median(total_latencies)
    p90 = total_latencies[int(len(total_latencies) * 0.90)]
    p95 = total_latencies[int(len(total_latencies) * 0.95)]
    p99 = total_latencies[int(len(total_latencies) * 0.99)]
    avg_total = statistics.mean(total_latencies)
    avg_guard = statistics.mean(guard_latencies)
    avg_rag = statistics.mean(rag_latencies)
    avg_sanitizer = statistics.mean(sanitizer_latencies)

    print("--- BENCHMARK RESULTS (50 Iterations) ---")
    print(f"  Pre-Turn Guardrail Latency (Avg) : {avg_guard:.4f} ms  (<0.01ms deterministic)")
    print(f"  SQLite FTS5 + PEP Retrieval (Avg): {avg_rag:.2f} ms")
    print(f"  Output Sanitizer Latency (Avg)   : {avg_sanitizer:.2f} ms")
    print(f"  -------------------------------------------------")
    print(f"  Total Turn Latency P50           : {p50:.2f} ms")
    print(f"  Total Turn Latency P90           : {p90:.2f} ms")
    print(f"  Total Turn Latency P95           : {p95:.2f} ms")
    print(f"  Total Turn Latency P99           : {p99:.2f} ms")
    print(f"  Total Turn Latency Mean          : {avg_total:.2f} ms")
    print(f"=======================================================\n")

    # SLA Assertions
    assert p50 < 900.0, f"P50 latency {p50}ms exceeded 900ms SLA target"
    assert p95 < 1200.0, f"P95 latency {p95}ms exceeded 1,200ms SLA target"
    assert avg_guard < 1.0, f"Pre-turn emergency guard {avg_guard}ms exceeded 1.0ms"

    return {
        "p50_ms": p50,
        "p90_ms": p90,
        "p95_ms": p95,
        "p99_ms": p99,
        "mean_ms": avg_total,
        "guardrail_avg_ms": avg_guard,
        "retrieval_avg_ms": avg_rag,
        "sanitizer_avg_ms": avg_sanitizer
    }

if __name__ == "__main__":
    asyncio.run(run_latency_benchmark(50))
