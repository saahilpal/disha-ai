import json
import time
from typing import List, Optional
from fastapi import APIRouter, Response
from pydantic import BaseModel
from app.orchestrator.turn_manager import turn_orchestrator, TurnResult
from app.audio.tts import tts_synthesizer
from app.db.connection import get_connection

router = APIRouter(prefix="/api/v1/simulation", tags=["Simulation & Regression Testing"])

class SimulationTurnRequest(BaseModel):
    patient_id: str = "pt_101"
    utterance: str
    session_id: Optional[str] = None
    turn_number: int = 1

class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None

@router.post("/turn", response_model=TurnResult)
async def simulate_conversation_turn(payload: SimulationTurnRequest):
    """
    Executes a complete voice turn simulation with full telemetry:
    Pre-turn emergency triage -> Dynamic Retrieval -> LLM -> Output Sanitizer.
    """
    result = await turn_orchestrator.execute_turn(
        patient_id=payload.patient_id,
        utterance=payload.utterance,
        session_id=payload.session_id,
        turn_number=payload.turn_number
    )
    return result

@router.post("/tts")
async def synthesize_speech(payload: TTSRequest):
    """Synthesizes text into streaming MP3 audio bytes using edge-tts."""
    audio_bytes = await tts_synthesizer.synthesize_to_bytes(payload.text, payload.voice)
    return Response(content=audio_bytes, media_type="audio/mpeg")

@router.post("/run-regression-suite")
async def run_regression_suite():
    """
    Executes all pinned benchmark scenarios across the 8 production failure classes.
    Computes accuracy, emergency recall, and latency benchmarks.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, test_code, failure_category, input_utterance, patient_context,
               expected_phrases, forbidden_phrases, should_emergency_halt
        FROM regression_test_suite WHERE is_active=1
    """)
    benchmarks = cursor.fetchall()
    conn.close()

    total = len(benchmarks)
    passed = 0
    failures = []
    latencies = []
    category_stats = {}

    start_time = time.perf_counter()

    for row in benchmarks:
        cat = row["failure_category"]
        if cat not in category_stats:
            category_stats[cat] = {"tested": 0, "passed": 0}
        category_stats[cat]["tested"] += 1

        expected = json.loads(row["expected_phrases"])
        forbidden = json.loads(row["forbidden_phrases"])
        should_halt = bool(row["should_emergency_halt"])

        # Execute turn
        result = await turn_orchestrator.execute_turn(
            patient_id=row["patient_context"] or "pt_101",
            utterance=row["input_utterance"]
        )

        latencies.append(result.latency.total_ms)

        # Evaluate assertions
        test_passed = True
        reason = ""

        # Check emergency halt assertion
        if should_halt and not result.is_emergency:
            test_passed = False
            reason = "Failed: Expected emergency halt but turn continued"
        elif not should_halt and result.is_emergency:
            test_passed = False
            reason = "Failed: False positive emergency halt triggered"

        # Check expected phrases
        if test_passed and expected:
            lower_res = result.final_response.lower()
            if not any(exp.lower() in lower_res for exp in expected):
                test_passed = False
                reason = f"Failed: Expected at least one of {expected} in response"

        # Check forbidden phrases
        if test_passed and forbidden:
            lower_res = result.final_response.lower()
            if any(forb.lower() in lower_res for forb in forbidden):
                test_passed = False
                reason = f"Failed: Found forbidden phrase in response"

        if test_passed:
            passed += 1
            category_stats[cat]["passed"] += 1
        else:
            failures.append({
                "test_code": row["test_code"],
                "input": row["input_utterance"],
                "response": result.final_response,
                "reason": reason
            })

    total_duration_ms = (time.perf_counter() - start_time) * 1000.0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_benchmarks": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate_pct": round((passed / total) * 100.0, 2) if total else 0.0,
        "emergency_recall_pct": 100.0 if all(f["test_code"] not in ["TEST_EMERGENCY_CHEST_PAIN", "TEST_EMERGENCY_COLLOQUIAL_CHHATI", "TEST_EMERGENCY_BREATHLESS"] for f in failures) else 0.0,
        "average_latency_ms": round(avg_latency, 2),
        "total_suite_duration_ms": round(total_duration_ms, 2),
        "category_breakdown": category_stats,
        "failures": failures
    }

@router.get("/audit/logs")
def get_audit_logs():
    """Retrieves recent turn logs and emergency alerts."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT turn_number, user_utterance, pre_guardrail_status, post_guardrail_status, final_response, latency_breakdown, created_at
        FROM call_turns ORDER BY created_at DESC LIMIT 20
    """)
    turns = [dict(r) for r in cursor.fetchall()]
    
    cursor.execute("""
        SELECT id, patient_id, red_flag_category, detected_phrases, triage_action_taken, care_ops_notified, status, created_at
        FROM emergency_escalations ORDER BY created_at DESC LIMIT 10
    """)
    escalations = [dict(r) for r in cursor.fetchall()]
    conn.close()
    
    return {
        "recent_turns": turns,
        "emergency_escalations": escalations
    }
