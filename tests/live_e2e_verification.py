"""Comprehensive Live End-to-End Voice & Merkle Ledger Verification Runner.

Tests all required aspects against live Docker container stack (port 8080):
1. Authentication Handshake (query param, in-band auth, rejection on invalid token).
2. Streaming Audio / Text turn with sub-budget latency breakdown.
3. Interruption / Barge-in: sending {"type": "interrupt"} and asserting {"type": "interrupted"}.
4. Merkle Ledger Commit Verification in PostgreSQL audit_claim_ledger.
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import io
import json
import os
import sys
import time
from typing import Any

import asyncpg
import edge_tts
import websockets

WS_URL = "ws://127.0.0.1:8080/ws/conversation"
VALID_TOKEN = "pt_test_01_valid_bearer_token"
INVALID_TOKEN = "pt_invalid_dummy_token_99999"
PG_URL = os.getenv("DATABASE_URL", f"postgresql://disha:{os.getenv('POSTGRES_PASSWORD', 'postgres')}@127.0.0.1:5432/disha")


async def generate_test_audio(text: str = "Pet mein gas ho rahi hai.") -> bytes:
    """Synthesize speech audio for live STT turnaround test."""
    communicate = edge_tts.Communicate(text, voice="hi-IN-SwaraNeural")
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()


async def verify_auth_handshake() -> dict[str, Any]:
    print("\n--- [TEST 1: Authentication Handshake] ---")
    results = {}

    # 1. Reject invalid token in query
    print("  1. Testing rejection of invalid token...")
    try:
        async with websockets.connect(f"{WS_URL}?token={INVALID_TOKEN}") as ws:
            await ws.recv()
            results["invalid_token_rejected"] = False
    except websockets.exceptions.InvalidStatusCode as e:
        results["invalid_token_rejected"] = (e.status_code == 401)
        print(f"     Rejected with HTTP status {e.status_code}")
    except websockets.exceptions.ConnectionClosed as e:
        results["invalid_token_rejected"] = (e.code == 4401)
        print(f"     Connection closed with WS code {e.code}")

    # 2. In-band authentication handshake
    print("  2. Testing in-band authentication handshake...")
    try:
        async with websockets.connect(WS_URL) as ws:
            # Send in-band auth message
            await ws.send(json.dumps({"type": "auth", "token": VALID_TOKEN}))
            # Wait for authenticated acknowledgment or send probe
            resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(resp)
            if data.get("type") == "authenticated":
                # Auth confirmed, now send probe turn
                await ws.send(json.dumps({"type": "text", "text": "Namaste"}))
                resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(resp)
            in_band_ok = data.get("type") == "transcript"
            # Drain until done
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                if isinstance(msg, str) and json.loads(msg).get("type") == "done":
                    break
            results["in_band_auth_success"] = in_band_ok
            print(f"     In-band auth succeeded: {in_band_ok}")
    except Exception as e:
        print(f"     In-band auth error: {e}")
        results["in_band_auth_success"] = False

    # 3. Query parameter authentication
    print("  3. Testing query parameter authentication...")
    try:
        async with websockets.connect(f"{WS_URL}?token={VALID_TOKEN}") as ws:
            await ws.send(json.dumps({"type": "text", "text": "Hello"}))
            resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(resp)
            query_ok = data.get("type") == "transcript"
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                if isinstance(msg, str) and json.loads(msg).get("type") == "done":
                    break
            results["query_param_auth_success"] = query_ok
            print(f"     Query param auth succeeded: {query_ok}")
    except Exception as e:
        print(f"     Query param auth error: {e}")
        results["query_param_auth_success"] = False

    all_passed = results.get("invalid_token_rejected", False) and \
                 results.get("in_band_auth_success", False) and \
                 results.get("query_param_auth_success", False)
    results["passed"] = all_passed
    return results


async def verify_streaming_audio_turn(audio_bytes: bytes) -> dict[str, Any]:
    print("\n--- [TEST 2: Streaming Audio Turn Latency Trace] ---")
    async with websockets.connect(f"{WS_URL}?token={VALID_TOKEN}") as ws:
        t0 = time.perf_counter()
        await ws.send(audio_bytes)

        t_stt: float | None = None
        t_first_sentence: float | None = None
        t_first_audio: float | None = None
        t_done: float | None = None

        transcript = ""
        first_sentence = ""
        all_sentences = []
        audio_chunk_count = 0
        total_audio_bytes = 0

        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
            t_now = time.perf_counter()

            if isinstance(msg, str):
                data = json.loads(msg)
                msg_type = data.get("type")
                if msg_type == "transcript" and t_stt is None:
                    t_stt = t_now
                    transcript = data.get("text", "")
                elif msg_type == "sentence":
                    if t_first_sentence is None:
                        t_first_sentence = t_now
                        first_sentence = data.get("text", "")
                    all_sentences.append(data.get("text", ""))
                elif msg_type == "done":
                    t_done = t_now
                    break
                elif msg_type == "error":
                    raise RuntimeError(f"Server error: {data.get('message')}")
            elif isinstance(msg, bytes):
                audio_chunk_count += 1
                total_audio_bytes += len(msg)
                if t_first_audio is None:
                    t_first_audio = t_now

        stt_ms = (t_stt - t0) * 1000.0 if t_stt else 0.0
        llm_val_ms = (t_first_sentence - t_stt) * 1000.0 if (t_first_sentence and t_stt) else 0.0
        text_ready_ms = (t_first_sentence - t0) * 1000.0 if t_first_sentence else 0.0
        tts_first_chunk_ms = (t_first_audio - t_first_sentence) * 1000.0 if (t_first_audio and t_first_sentence) else 0.0
        total_turnaround_ms = (t_first_audio - t0) * 1000.0 if t_first_audio else 0.0
        turn_complete_ms = (t_done - t0) * 1000.0 if t_done else 0.0

        print(f"  Transcript:            \"{transcript}\"")
        print(f"  First Sentence:        \"{first_sentence}\"")
        print(f"  • STT (Groq Whisper):  {stt_ms:.2f} ms")
        print(f"  • LLM TTFT + Val:      {llm_val_ms:.2f} ms")
        print(f"  • Text Ready Latency:  {text_ready_ms:.2f} ms")
        print(f"  • TTS First Chunk:     {tts_first_chunk_ms:.2f} ms")
        print(f"  • Total Turnaround:    {total_turnaround_ms:.2f} ms")
        print(f"  • Audio Chunks/Bytes:  {audio_chunk_count} chunks ({total_audio_bytes} bytes)")

        return {
            "passed": bool(t_stt and t_first_sentence and t_first_audio and t_done),
            "transcript": transcript,
            "first_sentence": first_sentence,
            "all_sentences": all_sentences,
            "audio_chunk_count": audio_chunk_count,
            "total_audio_bytes": total_audio_bytes,
            "latency_trace_ms": {
                "stt_whisper_ms": round(stt_ms, 2),
                "llm_and_validator_ms": round(llm_val_ms, 2),
                "text_ready_turnaround_ms": round(text_ready_ms, 2),
                "tts_first_chunk_ms": round(tts_first_chunk_ms, 2),
                "total_mouth_to_ear_ms": round(total_turnaround_ms, 2),
                "total_turn_completed_ms": round(turn_complete_ms, 2),
            },
        }


async def verify_streaming_text_turn() -> dict[str, Any]:
    print("\n--- [TEST 3: Streaming Text Turn] ---")
    async with websockets.connect(f"{WS_URL}?token={VALID_TOKEN}") as ws:
        t0 = time.perf_counter()
        query_text = "Aaj lunch mein kya khana theek rahega?"
        await ws.send(json.dumps({"type": "text", "text": query_text}))

        t_first_sentence: float | None = None
        t_first_audio: float | None = None
        t_done: float | None = None
        sentences = []
        audio_chunks = 0

        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
            t_now = time.perf_counter()

            if isinstance(msg, str):
                data = json.loads(msg)
                if data.get("type") == "sentence":
                    if t_first_sentence is None:
                        t_first_sentence = t_now
                    sentences.append(data.get("text", ""))
                elif data.get("type") == "done":
                    t_done = t_now
                    break
            elif isinstance(msg, bytes):
                audio_chunks += 1
                if t_first_audio is None:
                    t_first_audio = t_now

        ttft_ms = (t_first_sentence - t0) * 1000.0 if t_first_sentence else 0.0
        tts_first_ms = (t_first_audio - t0) * 1000.0 if t_first_audio else 0.0
        done_ms = (t_done - t0) * 1000.0 if t_done else 0.0

        print(f"  Query: \"{query_text}\"")
        print(f"  Emitted {len(sentences)} sentence(s): \"{' '.join(sentences)[:80]}...\"")
        print(f"  • Text TTFT:       {ttft_ms:.2f} ms")
        print(f"  • TTS First Audio: {tts_first_ms:.2f} ms")
        print(f"  • Turn Done:       {done_ms:.2f} ms")

        return {
            "passed": bool(t_first_sentence and t_first_audio and t_done),
            "query": query_text,
            "response": " ".join(sentences),
            "audio_chunks": audio_chunks,
            "latency_ms": {
                "text_ttft_ms": round(ttft_ms, 2),
                "tts_first_audio_ms": round(tts_first_ms, 2),
                "total_completed_ms": round(done_ms, 2),
            },
        }


async def verify_interruption_barge_in() -> dict[str, Any]:
    print("\n--- [TEST 4: Interruption / Barge-In Test] ---")
    async with websockets.connect(f"{WS_URL}?token={VALID_TOKEN}") as ws:
        long_query = "Mujhe acidity aur digestion ke baare mein poori jankari dijiye, subah se shaam tak kya karein."
        print("  1. Dispatching prompt to trigger long streaming speech...")
        await ws.send(json.dumps({"type": "text", "text": long_query}))

        # Wait until first sentence or audio chunk is received (speech is actively running)
        received_active_speech = False
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
            if isinstance(msg, (str, bytes)):
                if isinstance(msg, str) and json.loads(msg).get("type") == "sentence":
                    received_active_speech = True
                    break
                elif isinstance(msg, bytes):
                    received_active_speech = True
                    break

        print("  2. Active speech received. Sending interrupt: {\"type\": \"interrupt\"}...")
        t_interrupt_sent = time.perf_counter()
        await ws.send(json.dumps({"type": "interrupt"}))

        # Assert server responds with {"type": "interrupted"}
        received_interrupted_msg = False
        audio_after_interrupt = 0

        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
            except asyncio.TimeoutError:
                break

            if isinstance(msg, str):
                data = json.loads(msg)
                if data.get("type") == "interrupted":
                    received_interrupted_msg = True
                    t_interrupted_recv = time.perf_counter()
                    latency_ms = (t_interrupted_recv - t_interrupt_sent) * 1000.0
                    print(f"  3. Received {{\"type\": \"interrupted\"}} in {latency_ms:.2f} ms!")
                    break
            elif isinstance(msg, bytes):
                audio_after_interrupt += 1

        # Now test that the connection is still healthy and ready for the next turn
        print("  4. Verifying connection accepts immediate subsequent turn...")
        await ws.send(json.dumps({"type": "text", "text": "Theek hai, dhanyawad."}))
        subsequent_turn_ok = False
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            if isinstance(msg, str):
                data = json.loads(msg)
                if data.get("type") == "done":
                    subsequent_turn_ok = True
                    break

        print(f"  5. Subsequent turn completed successfully: {subsequent_turn_ok}")

        passed = received_active_speech and received_interrupted_msg and subsequent_turn_ok
        return {
            "passed": passed,
            "received_active_speech": received_active_speech,
            "received_interrupted_msg": received_interrupted_msg,
            "subsequent_turn_ok": subsequent_turn_ok,
            "audio_packets_leaked_post_interrupt": audio_after_interrupt,
        }


async def verify_merkle_ledger_commit() -> dict[str, Any]:
    print("\n--- [TEST 5: Merkle Ledger Commit Verification] ---")
    # Allow background queue worker to persist
    await asyncio.sleep(1.0)

    conn = await asyncpg.connect(PG_URL)
    try:
        total_records = await conn.fetchval("SELECT COUNT(*) FROM audit_claim_ledger")
        patient_records = await conn.fetchval(
            "SELECT COUNT(*) FROM audit_claim_ledger WHERE patient_id = 'pt_test_01'"
        )
        head_hash = await conn.fetchval(
            "SELECT current_hash FROM audit_chain_head WHERE singleton = TRUE"
        )

        rows = await conn.fetch(
            """SELECT event_id, patient_id, user_input, llm_output, breaker_status,
                      validator_status, prev_hash, current_hash, timestamp
               FROM audit_claim_ledger
               ORDER BY turn_id DESC
               LIMIT 10"""
        )

        print(f"  • Total Ledger Records:    {total_records}")
        print(f"  • Patient (pt_test_01):    {patient_records}")
        print(f"  • Current Head Hash:       {head_hash}")

        # Check cryptographic formula on the latest records
        verified_count = 0
        mismatches = []
        for r in rows:
            record_patient_id = r["patient_id"]
            record_input = r["user_input"]
            record_output = r["llm_output"]
            status_combined = f"{r['breaker_status']}|{r['validator_status']}"
            prev_hash = r["prev_hash"]
            expected_payload = f"{prev_hash}|{record_patient_id}|{record_input}|{record_output}|{status_combined}"
            recomputed = hashlib.sha256(expected_payload.encode("utf-8")).hexdigest()

            if recomputed == r["current_hash"]:
                verified_count += 1
            else:
                mismatches.append({
                    "event_id": str(r["event_id"]),
                    "expected": recomputed,
                    "actual": r["current_hash"],
                })

        print(f"  • Cryptographic Hashes:    {verified_count}/{len(rows)} verified matches in recent window")
        if mismatches:
            print(f"    WARNING: Mismatches detected: {mismatches}")

        latest_record = dict(rows[0]) if rows else None
        if latest_record:
            latest_record["event_id"] = str(latest_record["event_id"])
            latest_record["timestamp"] = str(latest_record["timestamp"])

        passed = (total_records > 0) and (verified_count == len(rows)) and (mismatches == []) and (head_hash == rows[0]["current_hash"])
        print(f"  • Head Hash Alignment:    {'PASS' if head_hash == rows[0]['current_hash'] else 'FAIL'}")

        return {
            "passed": passed,
            "total_records": total_records,
            "patient_records": patient_records,
            "head_hash": head_hash,
            "verified_recent_records": verified_count,
            "hash_mismatches": mismatches,
            "latest_record": latest_record,
        }
    finally:
        await conn.close()


async def main() -> None:
    print("=" * 70)
    print("LIVE END-TO-END VERIFICATION RUNNER")
    print(f"Target WebSocket: {WS_URL}")
    print(f"Target Database:  {PG_URL.split('@')[-1]}")
    print("=" * 70)

    # Prepare reference audio
    print("\nSynthesizing test audio sample via Edge-TTS...")
    audio_sample = await generate_test_audio("Pet mein gas ho rahi hai.")
    print(f"Sample generated: {len(audio_sample)} bytes.")

    # 1. Auth Handshake
    auth_res = await verify_auth_handshake()

    # 2. Streaming Audio Turn
    audio_res = await verify_streaming_audio_turn(audio_sample)

    # 3. Streaming Text Turn
    text_res = await verify_streaming_text_turn()

    # 4. Interruption / Barge-in
    barge_res = await verify_interruption_barge_in()

    # 5. Merkle Ledger Verification
    merkle_res = await verify_merkle_ledger_commit()

    all_passed = (
        auth_res["passed"]
        and audio_res["passed"]
        and text_res["passed"]
        and barge_res["passed"]
        and merkle_res["passed"]
    )

    summary = {
        "timestamp": datetime.datetime.now().isoformat(),
        "overall_status": "PASSED" if all_passed else "FAILED",
        "tests": {
            "authentication_handshake": auth_res,
            "streaming_audio_turn": audio_res,
            "streaming_text_turn": text_res,
            "interruption_barge_in": barge_res,
            "merkle_ledger_verification": merkle_res,
        },
    }

    report_path = "audit/reports/live_verification_report.json"
    os.makedirs("audit/reports", exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as fp:
        json.dump(summary, fp, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print("LIVE VERIFICATION SUMMARY")
    print("=" * 70)
    print(f"1. Authentication Handshake:       {'PASS' if auth_res['passed'] else 'FAIL'}")
    print(f"2. Streaming Audio Turn:           {'PASS' if audio_res['passed'] else 'FAIL'}")
    print(f"3. Streaming Text Turn:            {'PASS' if text_res['passed'] else 'FAIL'}")
    print(f"4. Interruption / Barge-In:        {'PASS' if barge_res['passed'] else 'FAIL'}")
    print(f"5. Merkle Claim Ledger & Head:     {'PASS' if merkle_res['passed'] else 'FAIL'}")
    print("----------------------------------------------------------------------")
    print(f"OVERALL STATUS:                    {'PASSED' if all_passed else 'FAILED'}")
    print(f"Report saved to:                   {report_path}")
    print("=" * 70 + "\n")

    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
