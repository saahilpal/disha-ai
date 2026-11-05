import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.orchestrator.turn_manager import turn_orchestrator
from app.audio.tts import tts_synthesizer

router = APIRouter(tags=["WebSocket Real-Time Voice Streaming"])

@router.websocket("/ws/call/{patient_id}")
async def websocket_call_endpoint(websocket: WebSocket, patient_id: str):
    """
    Real-time streaming WebSocket endpoint for voice follow-up turns.
    Streams text metadata and binary audio chunks sentence-by-sentence with sub-second turnaround.
    """
    await websocket.accept()
    session_id = f"ws_sess_{patient_id}"
    turn_counter = 1
    
    # Send connection greeting
    await websocket.send_json({
        "type": "session_ready",
        "patient_id": patient_id,
        "message": "Connection established with Disha Voice Engine."
    })

    try:
        while True:
            # Receive client message
            message = await websocket.receive_text()
            data = json.loads(message)
            msg_type = data.get("type", "user_utterance")

            if msg_type == "user_utterance":
                utterance = data.get("text", "")
                if not utterance:
                    continue

                # Execute turn orchestration
                result = await turn_orchestrator.execute_turn(
                    patient_id=patient_id,
                    utterance=utterance,
                    session_id=session_id,
                    turn_number=turn_counter
                )
                turn_counter += 1

                # If emergency halted, send immediate alert event
                if result.is_emergency:
                    await websocket.send_json({
                        "type": "emergency_halt",
                        "turn_id": result.turn_id,
                        "category": result.pre_guardrail.get("category"),
                        "triage_message": result.final_response,
                        "latency_ms": result.latency.total_ms
                    })
                else:
                    # Send turn metadata & telemetry
                    await websocket.send_json({
                        "type": "turn_metadata",
                        "turn_id": result.turn_id,
                        "pre_guardrail": result.pre_guardrail,
                        "retrieved_rules": result.retrieved_rules,
                        "post_guardrail": result.post_guardrail,
                        "latency": result.latency.model_dump()
                    })

                # Stream audio chunks binary frames over WebSocket
                try:
                    async for chunk in tts_synthesizer.stream_audio_chunks(result.final_response):
                        await websocket.send_bytes(chunk)
                except Exception:
                    pass

                # Signal turn playback completion
                await websocket.send_json({
                    "type": "turn_complete",
                    "turn_id": result.turn_id,
                    "final_response": result.final_response,
                    "total_turn_latency_ms": result.latency.total_ms
                })

            elif msg_type == "interrupt":
                # Handle barge-in
                await websocket.send_json({
                    "type": "interrupted",
                    "message": "Playback halted by user barge-in."
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.close()
        except Exception:
            pass
