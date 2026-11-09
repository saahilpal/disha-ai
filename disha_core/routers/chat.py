"""Conversational turn and SSE streaming endpoints."""

from __future__ import annotations

import json
from contextlib import suppress
from typing import Any, AsyncIterator

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

from disha_core.compliance.ledger import AuditRecord
from disha_core.models.schemas import ChatResponse, TurnRequest, TurnState

router = APIRouter(tags=["Chat"])


@router.get("/chat/history")
async def get_chat_history(
    request: Request,
    authorization: str | None = Header(default=None),
    limit: int = 20,
) -> dict[str, Any]:
    """Retrieve chronological turn history for the authenticated patient."""
    import disha_core.main as app_main
    from disha_core.services.chat_service import load_conversation_history

    patient_id = await app_main._authenticated_patient(request, authorization)
    pool = getattr(request.app.state, "pool", None)
    history: list[dict[str, str]] = []
    if pool is not None:
        history = await load_conversation_history(pool, patient_id, limit=limit)
    elif hasattr(request.app.state, "conversation_history"):
        history = list(request.app.state.conversation_history.get(patient_id, []))[-limit:]
    return {"patient_id": patient_id, "history": history}


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: TurnRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    """Process a single conversational turn through deterministic safety and LLM generation."""
    import disha_core.main as app_main

    emergency = request.app.state.router.breaker.check(payload.text)
    if emergency.triggered:
        resp_text = emergency.response or "Yeh emergency ho sakti hai. Abhi 112 par call karein."
        with suppress(Exception):
            patient_id = await app_main._authenticated_patient(request, authorization)
            from disha_core.harness.harness import _commit_turn

            await _commit_turn(request.app.state, patient_id, payload.text, resp_text)
        return {
            "response": resp_text,
            "status": f"triggered:{emergency.category}",
        }

    patient_id = await app_main._authenticated_patient(request, authorization)
    state = TurnState()
    sentences = [sentence async for sentence in app_main._turn_sentences(request, patient_id, payload, state)]
    output = " ".join(sentences)

    app_main._enqueue_audit(
        request.app.state.ledger,
        AuditRecord(patient_id, payload.text, output, state.breaker_status, state.validator_status),
    )
    return {
        "response": output,
        "status": state.validator_status,
        "evidence_ids": state.evidence_ids,
    }


@router.post("/chat/stream")
async def chat_stream(
    payload: TurnRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    """Stream validated sentences via Server-Sent Events (SSE)."""
    import disha_core.main as app_main

    emergency = request.app.state.router.breaker.check(payload.text)
    if emergency.triggered:
        text = emergency.response or "Yeh emergency ho sakti hai. Abhi 112 par call karein."
        with suppress(Exception):
            patient_id = await app_main._authenticated_patient(request, authorization)
            from disha_core.harness.harness import _commit_turn

            await _commit_turn(request.app.state, patient_id, payload.text, text)

        async def emergency_event() -> AsyncIterator[str]:
            yield f"data: {json.dumps({'sentence': text}, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'status': f'triggered:{emergency.category}'})}\n\n"

        return StreamingResponse(emergency_event(), media_type="text/event-stream")

    patient_id = await app_main._authenticated_patient(request, authorization)
    state = TurnState()

    async def events() -> AsyncIterator[str]:
        output: list[str] = []
        try:
            async for sentence in app_main._turn_sentences(request, patient_id, payload, state):
                output.append(sentence)
                yield f"data: {json.dumps({'sentence': sentence}, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'status': state.validator_status, 'evidence_ids': state.evidence_ids})}\n\n"
        finally:
            app_main._enqueue_audit(
                request.app.state.ledger,
                AuditRecord(patient_id, payload.text, " ".join(output), state.breaker_status, state.validator_status),
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
