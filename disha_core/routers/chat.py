"""Conversational turn and SSE streaming endpoints."""
from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

from disha_core.compliance.ledger import AuditRecord
from disha_core.models.schemas import ChatResponse, TurnRequest, TurnState

router = APIRouter(tags=["Chat"])


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
        return {
            "response": emergency.response or "Yeh emergency ho sakti hai. Abhi 112 par call karein.",
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
    return {"response": output, "status": state.validator_status}


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
            yield f"event: done\ndata: {json.dumps({'status': state.validator_status})}\n\n"
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
