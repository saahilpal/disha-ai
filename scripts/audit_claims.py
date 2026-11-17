"""Audit and verify system benchmark claims, token limits, and component timings.
Outputs raw verifiable JSON results to ~/Desktop/disha-lab/results/.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure repo root is on pythonpath
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from disha_core.pipeline.breaker import EmergencyBreaker
from disha_core.voice import get_emergency_audio, detect_turn_language


async def run_audit():
    results_dir = Path(os.path.expanduser("~/Desktop/disha-lab/results"))
    results_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).isoformat()
    audit_data = {
        "timestamp": timestamp,
        "date": "2026-11-17",
        "measurements": {},
    }

    # 1. In-memory breaker timing
    breaker = EmergencyBreaker()
    breaker_times = []
    for _ in range(100):
        t0 = time.perf_counter()
        _ = breaker.check("I have severe crushing chest pain")
        breaker_times.append((time.perf_counter() - t0) * 1000.0)
    breaker_p50 = sorted(breaker_times)[len(breaker_times) // 2]
    audit_data["measurements"]["emergency_breaker_in_memory_p50_ms"] = {
        "value": round(breaker_p50, 4),
        "label": "LOCAL",
        "description": "In-memory Aho-Corasick triage evaluation latency (excludes network)",
        "sample_size": len(breaker_times),
    }

    # 2. In-memory emergency audio fallback retrieval timing
    audio_times = []
    for _ in range(100):
        t0 = time.perf_counter()
        _ = get_emergency_audio("CARDIOVASCULAR")
        audio_times.append((time.perf_counter() - t0) * 1000.0)
    audio_p50 = sorted(audio_times)[len(audio_times) // 2]
    audit_data["measurements"]["pre_rendered_emergency_audio_lookup_p50_ms"] = {
        "value": round(audio_p50, 4),
        "label": "LOCAL",
        "description": "Pre-rendered emergency mp3 memory-cache buffer retrieval (excludes audio decoding/playback)",
        "sample_size": len(audio_times),
    }

    # 3. Language detection timing
    lang_times = []
    test_texts = [
        "Mere pet me gas ho rahi hai kya karu",
        "I need advice on high blood pressure diet",
        "नमस्ते मुझे सिर दर्द की समस्या है",
    ]
    for _ in range(30):
        for text in test_texts:
            t0 = time.perf_counter()
            _ = detect_turn_language(text)
            lang_times.append((time.perf_counter() - t0) * 1000.0)
    lang_p50 = sorted(lang_times)[len(lang_times) // 2]
    audit_data["measurements"]["language_detection_p50_ms"] = {
        "value": round(lang_p50, 4),
        "label": "LOCAL",
        "description": "Script and vocabulary heuristic language classifier latency",
        "sample_size": len(lang_times),
    }

    # 4. Free tier capacity arithmetic model
    # Groq free tier limits (verified 2026): 6,000 TPM, 500,000 TPD, 1,000 RPD
    # Turn size model:
    #   Avg System Prompt + Persona: 450 tokens
    #   Avg Context Window (last 4 turns): 350 tokens
    #   Avg Retrieved Guidelines: 250 tokens
    #   Avg Patient Input: 40 tokens
    #   Avg Disha Response: 110 tokens
    # Total tokens per turn = ~1,200 tokens
    turn_tokens = 1200
    groq_daily_tokens = 500000
    groq_daily_requests = 1000
    patient_daily_turns = 10

    max_patients_groq_token_constrained = groq_daily_tokens // (turn_tokens * patient_daily_turns)
    max_patients_groq_request_constrained = groq_daily_requests // patient_daily_turns
    groq_effective_patient_cap = min(max_patients_groq_token_constrained, max_patients_groq_request_constrained)

    audit_data["capacity_audit"] = {
        "tokens_per_turn_estimate": turn_tokens,
        "patient_daily_turns": patient_daily_turns,
        "groq_free_limits": {
            "tokens_per_day": groq_daily_tokens,
            "requests_per_day": groq_daily_requests,
            "tpm": 6000,
            "source": "https://console.groq.com/docs/rate-limits (Accessed 2026-11-17)",
        },
        "effective_capacity": {
            "token_bound_patients_day": max_patients_groq_token_constrained,
            "request_bound_patients_day": max_patients_groq_request_constrained,
            "groq_daily_patient_capacity": groq_effective_patient_cap,
            "label": "ESTIMATE",
            "notes": "Previous 47 patients/day claim overlooked the 500,000 token/day budget; corrected to 41 patients/day based on 1,200 tokens/turn.",
        },
    }

    # 5. Database Trust Tier and Provenance check
    try:
        import asyncpg
        db_url = os.getenv("DATABASE_URL", "postgresql://disha:disha_secure_pass_123@127.0.0.1:5432/disha")
        conn = await asyncpg.connect(db_url, timeout=3.0)
        try:
            total_chunks = await conn.fetchval("SELECT COUNT(*) FROM knowledge_chunks")
            tier_counts = await conn.fetch(
                "SELECT ks.trust_tier, COUNT(kc.id) FROM knowledge_sources ks LEFT JOIN knowledge_chunks kc ON ks.id = kc.source_id GROUP BY ks.trust_tier"
            )
            sources = await conn.fetch("SELECT id, name, trust_tier FROM knowledge_sources ORDER BY trust_tier, id")
            audit_data["database_provenance"] = {
                "total_chunks": total_chunks,
                "tier_breakdown": {r["trust_tier"]: r["count"] for r in tier_counts},
                "sources": [{"id": s["id"], "name": s["name"], "trust_tier": s["trust_tier"]} for s in sources],
                "label": "LOCAL",
                "notes": "Verified against local Postgres instance. Zero external clinician board certifications logged. Provenance derives from published ICMR-NIN, MoHFW, AYUSH, and WHO clinical guidelines.",
            }
        finally:
            await conn.close()
    except Exception as exc:
        audit_data["database_provenance"] = {"status": "skipped", "error": str(exc)}

    out_file = results_dir / "audit_results_20261117.json"
    out_file.write_text(json.dumps(audit_data, indent=2))
    print(f"Audit completed. Written to {out_file}")
    return audit_data


if __name__ == "__main__":
    asyncio.run(run_audit())
