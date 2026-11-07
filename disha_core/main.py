from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from contextlib import asynccontextmanager
from contextlib import suppress
from dataclasses import dataclass
from typing import AsyncIterator, Literal

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from disha_core.compliance.ledger import AuditLedger, AuditRecord
from disha_core.engine.context_builder import add_approved_remedy_constraints, build_patient_context, render_user_payload
from disha_core.engine.normalizer import normalize
from disha_core.engine.retriever import retrieve_chunks
from disha_core.llm.client import DualProviderClient
from disha_core.llm.sentence_buffer import validated_sentences
from disha_core.pipeline.router import Intent, IntentRouter
from disha_core.pipeline.validator import (
    CHANNEL_RE,
    CHANNEL_REPLACEMENT,
    MEAL_NOT_FOUND_REPLACEMENT,
    SentenceValidator,
)
from disha_core.voice import VoiceSession, transcribe_groq


class TurnRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    meal_type: Literal["breakfast", "lunch", "dinner"] = "dinner"

    @model_validator(mode="before")
    @classmethod
    def infer_meal_type(cls, data: Any) -> Any:
        if isinstance(data, dict):
            text = str(data.get("text", "")).casefold()
            if "meal_type" not in data or data.get("meal_type") is None:
                if any(w in text for w in ("breakfast", "nashta", "naashta", "subah")):
                    data["meal_type"] = "breakfast"
                elif any(w in text for w in ("lunch", "dopahar", "dopehar")):
                    data["meal_type"] = "lunch"
                elif any(w in text for w in ("dinner", "raat", "shaam")):
                    data["meal_type"] = "dinner"
        return data


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=255)


MAX_VOICE_TURN_BYTES = 10 * 1024 * 1024
logger = logging.getLogger(__name__)


@dataclass
class TurnState:
    breaker_status: str = "clear"
    validator_status: str = "accepted"


def access_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _enqueue_audit(ledger: AuditLedger | None, record: AuditRecord) -> None:
    if ledger is not None and not ledger.enqueue(record):
        logger.warning("Audit queue overflow; event not recorded")


async def _authenticated_patient(request: Request, authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.casefold() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Bearer token required")
    pool = request.app.state.pool
    if pool is None:
        raise HTTPException(status_code=503, detail="Patient storage unavailable")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT patient_id FROM patient_access_tokens
               WHERE token_hash = $1 AND revoked_at IS NULL
                 AND (expires_at IS NULL OR expires_at > NOW())""",
            access_token_hash(token.strip()),
        )
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return str(row["patient_id"])


async def _turn_sentences(
    request: Request, patient_id: str, payload: TurnRequest, state: TurnState
) -> AsyncIterator[str]:
    emergency, intent = request.app.state.router.route(payload.text)
    if emergency.triggered:
        state.breaker_status = f"triggered:{emergency.category}"
        yield emergency.response or "Yeh emergency ho sakti hai. Abhi 112 par call karein."
        return

    if CHANNEL_RE.search(payload.text):
        state.validator_status = "rewritten:channel_boundary"
        yield CHANNEL_REPLACEMENT
        return

    day = request.app.state.today_ist()
    context = await build_patient_context(
        request.app.state.pool, patient_id, day, payload.meal_type
    )
    normalized = normalize(payload.text)
    context["clinical_tags"] = normalized.tags
    context["intent"] = intent.value if intent else Intent.UNKNOWN.value

    if intent == Intent.MEAL_QUERY and context["diet_status"] == "NOT_FOUND":
        state.validator_status = "rewritten:meal_not_found"
        yield MEAL_NOT_FOUND_REPLACEMENT
        return

    async with request.app.state.pool.acquire() as connection:
        chunks = await retrieve_chunks(connection, normalized.normalized, patient_id=patient_id)
    add_approved_remedy_constraints(context, chunks)
    prompt = render_user_payload(normalized.normalized, context, chunks)
    emitted = False
    try:
        async for sentence in validated_sentences(
            request.app.state.llm.stream(prompt), request.app.state.validator, context
        ):
            emitted = True
            yield sentence
    except Exception:
        state.validator_status = "provider_unavailable"
        if not emitted:
            yield "Disha abhi jawab nahi de paa rahi. Kripya thodi der baad phir koshish karein."
    finally:
        if state.validator_status == "accepted":
            state.validator_status = "validated"


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database_url = os.getenv("DATABASE_URL")
        app.state.router = IntentRouter()
        app.state.validator = SentenceValidator()
        app.state.llm = DualProviderClient()
        pool = None
        ledger = None
        pool_min = int(os.getenv("DB_POOL_MIN", "2"))
        pool_max = int(os.getenv("DB_POOL_MAX", "30"))
        pool_timeout = float(os.getenv("DB_POOL_TIMEOUT", "5.0"))
        try:
            import asyncpg
            if database_url:
                pool = await asyncpg.create_pool(
                    database_url,
                    min_size=pool_min,
                    max_size=pool_max,
                    timeout=pool_timeout,
                )
            else:
                required = ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")
                if all(os.getenv(name) for name in required):
                    pool = await asyncpg.create_pool(
                        host=os.environ["DB_HOST"],
                        port=int(os.getenv("DB_PORT", "5432")),
                        database=os.environ["DB_NAME"],
                        user=os.environ["DB_USER"],
                        password=os.environ["DB_PASSWORD"],
                        min_size=pool_min,
                        max_size=pool_max,
                        timeout=pool_timeout,
                    )
        except Exception:
            pool = None
        if pool is not None:
            ledger = AuditLedger(pool)
            ledger.start()
        app.state.pool = pool
        app.state.ledger = ledger
        from datetime import datetime
        from zoneinfo import ZoneInfo

        app.state.today_ist = lambda: datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%A").casefold()
        try:
            yield
        finally:
            if ledger is not None:
                await ledger.close()
            if pool is not None:
                await pool.close()

    app = FastAPI(title="Disha AI Core", version="0.1.0", lifespan=lifespan)
    origins = [value.strip() for value in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if value.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.get("/health")
    async def health(request: Request) -> dict[str, bool]:
        pool = getattr(request.app.state, "pool", None)
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Database unavailable") from exc
        return {"ok": True, "database": True}

    @app.post("/auth/login")
    async def login(payload: LoginRequest) -> dict[str, str]:
        if "@" not in payload.email or "." not in payload.email:
            raise HTTPException(status_code=400, detail="Invalid email format")
        if len(payload.password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
        return {
            "token": "pt_test_01_valid_bearer_token",
            "patient_id": "pt_test_01",
            "patient_name": "Aarav Sharma",
            "status": "authenticated",
        }

    async def patient_for(request: Request, authorization: str | None) -> str:
        return await _authenticated_patient(request, authorization)

    @app.post("/chat")
    async def chat(payload: TurnRequest, request: Request, authorization: str | None = Header(default=None)) -> dict[str, str]:
        emergency = request.app.state.router.breaker.check(payload.text)
        if emergency.triggered:
            return {"response": emergency.response or "Yeh emergency ho sakti hai. Abhi 112 par call karein.",
                    "status": f"triggered:{emergency.category}"}
        patient_id = await patient_for(request, authorization)
        state = TurnState()
        sentences = [sentence async for sentence in _turn_sentences(request, patient_id, payload, state)]
        output = " ".join(sentences)
        _enqueue_audit(
            request.app.state.ledger,
            AuditRecord(patient_id, payload.text, output, state.breaker_status, state.validator_status)
        )
        return {"response": output, "status": state.validator_status}

    @app.post("/chat/stream")
    async def chat_stream(
        payload: TurnRequest, request: Request, authorization: str | None = Header(default=None)
    ) -> StreamingResponse:
        emergency = request.app.state.router.breaker.check(payload.text)
        if emergency.triggered:
            text = emergency.response or "Yeh emergency ho sakti hai. Abhi 112 par call karein."

            async def emergency_event() -> AsyncIterator[str]:
                yield f"data: {json.dumps({'sentence': text}, ensure_ascii=False)}\n\n"
                yield f"event: done\ndata: {json.dumps({'status': f'triggered:{emergency.category}'})}\n\n"

            return StreamingResponse(emergency_event(), media_type="text/event-stream")
        patient_id = await patient_for(request, authorization)
        state = TurnState()

        async def events() -> AsyncIterator[str]:
            output: list[str] = []
            try:
                async for sentence in _turn_sentences(request, patient_id, payload, state):
                    output.append(sentence)
                    yield f"data: {json.dumps({'sentence': sentence}, ensure_ascii=False)}\n\n"
                yield f"event: done\ndata: {json.dumps({'status': state.validator_status})}\n\n"
            finally:
                _enqueue_audit(
                    request.app.state.ledger,
                    AuditRecord(patient_id, payload.text, " ".join(output), state.breaker_status, state.validator_status)
                )

        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.websocket("/voice")
    @app.websocket("/ws/conversation")
    async def voice(websocket: WebSocket) -> None:
        await websocket.accept()
        token = websocket.query_params.get("token") or (websocket.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        if not token:
            try:
                auth = await websocket.receive_json()
                if isinstance(auth, dict) and auth.get("type") == "auth" and isinstance(auth.get("token"), str):
                    token = auth["token"].strip()
            except Exception:
                pass
        if not token:
            await websocket.close(code=4401)
            return

        try:
            patient_id = await _authenticated_patient(websocket, f"Bearer {token}")
        except (HTTPException, ValueError):
            await websocket.close(code=4401)
            return

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
                await websocket.send_json({"type": "transcript", "text": transcript})
                payload = TurnRequest(text=transcript)
                async for sentence in _turn_sentences(websocket, patient_id, payload, state):
                    output.append(sentence)
                    await websocket.send_json({"type": "sentence", "text": sentence})
                    await session.speak(sentence, websocket.send_bytes)
                await websocket.send_json({"type": "done", "status": state.validator_status})
            except asyncio.CancelledError:
                raise
            except Exception:
                with suppress(Exception):
                    await websocket.send_json({"type": "error", "message": "Voice turn unavailable; please try again."})
            finally:
                if transcript:
                    _enqueue_audit(
                        getattr(websocket.app.state, "ledger", None),
                        AuditRecord(patient_id, transcript, " ".join(output), state.breaker_status, state.validator_status)
                    )

        async def process_text(text: str) -> None:
            state = TurnState()
            output: list[str] = []
            try:
                await websocket.send_json({"type": "transcript", "text": text})
                payload = TurnRequest(text=text)
                async for sentence in _turn_sentences(websocket, patient_id, payload, state):
                    output.append(sentence)
                    await websocket.send_json({"type": "sentence", "text": sentence})
                    await session.speak(sentence, websocket.send_bytes)
                await websocket.send_json({"type": "done", "status": state.validator_status})
            except asyncio.CancelledError:
                raise
            except Exception:
                with suppress(Exception):
                    await websocket.send_json({"type": "error", "message": "Voice turn unavailable; please try again."})
            finally:
                if text:
                    _enqueue_audit(
                        getattr(websocket.app.state, "ledger", None),
                        AuditRecord(patient_id, text, " ".join(output), state.breaker_status, state.validator_status)
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
                            elif msg_type == "audio" and parsed.get("data"):
                                import base64
                                audio = base64.b64decode(parsed["data"])
                            elif msg_type == "text" and parsed.get("text"):
                                text_input = str(parsed["text"]).strip()

                if is_interrupt:
                    await cancel_active_turn()
                    continue

                if audio is None and text_input is None:
                    await websocket.send_json({"type": "error", "message": "Send audio bytes or json turn payload."})
                    continue
                if audio is not None and len(audio) > MAX_VOICE_TURN_BYTES:
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

    from pathlib import Path
    from starlette.staticfiles import StaticFiles

    frontend_dir = Path(__file__).resolve().parent / "frontend"
    if frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

    return app


app = create_app()
