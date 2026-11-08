"""Full-duplex WebSocket conversational voice and barge-in endpoints."""
from __future__ import annotations

import asyncio
import json
from contextlib import suppress

from fastapi import APIRouter, HTTPException, WebSocket

from disha_core.compliance.ledger import AuditRecord
from disha_core.models.schemas import TurnState
from disha_core.voice import VoiceSession, detect_turn_language, execute_voice_turn, transcribe_groq

router = APIRouter(tags=["Voice"])


@router.websocket("/voice")
@router.websocket("/ws/conversation")
async def voice(websocket: WebSocket) -> None:
    """Full-duplex WebSocket conversational streaming voice endpoint with barge-in support."""
    import disha_core.main as app_main

    await websocket.accept()
    auth_frame_received = False
    token = websocket.query_params.get("token") or (
        websocket.headers.get("authorization") or ""
    ).removeprefix("Bearer ").strip()

    if not token:
        try:
            auth = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
            if isinstance(auth, dict) and auth.get("type") == "auth" and isinstance(auth.get("token"), str):
                token = auth["token"].strip()
                auth_frame_received = True
        except Exception:
            pass

    if not token:
        await websocket.close(code=4401)
        return

    try:
        patient_id = await app_main._authenticated_patient(websocket, f"Bearer {token}")
    except (HTTPException, ValueError):
        await websocket.close(code=4401)
        return

    if auth_frame_received:
        with suppress(Exception):
            await websocket.send_json({"type": "authenticated", "patient_id": patient_id})

    session = VoiceSession()
    turn_task: asyncio.Task[None] | None = None

    async def cancel_active_turn() -> None:
        nonlocal turn_task
        if turn_task is not None and not turn_task.done():
            turn_task.cancel()
            with suppress(asyncio.CancelledError):
                await turn_task
            turn_task = None
        await session.barge_in()
        with suppress(Exception):
            await websocket.send_json({"type": "interrupted"})

    async def process_audio(audio: bytes) -> None:
        transcript = ""
        state = TurnState()
        output: list[str] = []
        try:
            transcript = await transcribe_groq(audio)
            lang = detect_turn_language(transcript)
            await websocket.send_json({"type": "transcript", "text": transcript, "language": lang})
            output = await execute_voice_turn(
                websocket,
                patient_id,
                transcript,
                session,
                send_json=websocket.send_json,
                send_audio=websocket.send_bytes,
                state=state,
                language=lang,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            err_str = str(exc)
            if "filtered silence hallucination" in err_str or "silent audio frame" in err_str:
                with suppress(Exception):
                    await websocket.send_json({"type": "silence", "message": "Silence detected"})
                return
            with suppress(Exception):
                await websocket.send_json(
                    {"type": "error", "message": "Voice turn unavailable; please try again."}
                )
        finally:
            if transcript:
                app_main._enqueue_audit(
                    getattr(websocket.app.state, "ledger", None),
                    AuditRecord(
                        patient_id, transcript, " ".join(output), state.breaker_status, state.validator_status
                    ),
                )

    async def process_text(text: str) -> None:
        state = TurnState()
        output: list[str] = []
        try:
            lang = detect_turn_language(text)
            await websocket.send_json({"type": "transcript", "text": text, "language": lang})
            output = await execute_voice_turn(
                websocket,
                patient_id,
                text,
                session,
                send_json=websocket.send_json,
                send_audio=websocket.send_bytes,
                state=state,
                language=lang,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            with suppress(Exception):
                await websocket.send_json(
                    {"type": "error", "message": "Voice turn unavailable; please try again."}
                )
        finally:
            if text:
                app_main._enqueue_audit(
                    getattr(websocket.app.state, "ledger", None),
                    AuditRecord(
                        patient_id, text, " ".join(output), state.breaker_status, state.validator_status
                    ),
                )

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            audio = message.get("bytes")
            text_input = None
            is_interrupt = False
            if audio is None and message.get("text"):
                with suppress(Exception):
                    parsed = json.loads(message["text"])
                    if isinstance(parsed, dict):
                        msg_type = str(parsed.get("type", "")).strip().casefold()
                        if msg_type in ("interrupt", "interrupted", "barge_in"):
                            is_interrupt = True
                        elif msg_type == "auth":
                            with suppress(Exception):
                                await websocket.send_json(
                                    {"type": "authenticated", "patient_id": patient_id}
                                )
                            continue
                        elif msg_type == "audio" and parsed.get("data"):
                            import base64

                            audio = base64.b64decode(parsed["data"])
                        elif msg_type == "text" and parsed.get("text"):
                            text_input = str(parsed["text"]).strip()

            if is_interrupt:
                await cancel_active_turn()
                continue

            if audio is None and text_input is None:
                await websocket.send_json(
                    {"type": "error", "message": "Send audio bytes or json turn payload."}
                )
                continue
            if audio is not None and len(audio) > app_main.MAX_VOICE_TURN_BYTES:
                await websocket.close(code=1009, reason="Audio turn exceeds 10 MB")
                break

            if turn_task is not None and not turn_task.done():
                await cancel_active_turn()
            else:
                await session.barge_in()

            if audio is not None:
                turn_task = asyncio.create_task(process_audio(audio))
            else:
                assert text_input is not None
                turn_task = asyncio.create_task(process_text(text_input))
    finally:
        if turn_task is not None and not turn_task.done():
            turn_task.cancel()
            with suppress(asyncio.CancelledError):
                await turn_task
        await session.barge_in()
