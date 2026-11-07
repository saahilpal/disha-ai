"""Disha AI Core — FastAPI Application Entrypoint.

Orchestrates clean layered architecture:
- Config: Environment settings with safe defaults
- Models: Strict Pydantic v2 schemas
- Services: Domain services for authentication, patient profiles, and chat orchestration
- Adapters: Database pool adapter and lifecycle management
- Zero-PHI Logging: Structured logging scrubbing all sensitive identifiers
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.staticfiles import StaticFiles

from disha_core.adapters.db import create_database_pool
from disha_core.classifier.adapter import LayaClassifierAdapter
from disha_core.compliance.ledger import AuditLedger, AuditRecord
from disha_core.config import get_settings
from disha_core.engine.context_builder import (
    add_approved_remedy_constraints,
    build_patient_context,
    render_user_payload,
)
from disha_core.engine.normalizer import normalize
from disha_core.engine.retriever import retrieve_chunks
from disha_core.llm.client import DualProviderClient
from disha_core.llm.sentence_buffer import validated_sentences
from disha_core.logging_config import setup_structured_logging
from disha_core.models.schemas import (
    ChatResponse,
    HealthResponse,
    LoginRequest,
    OnboardingRequest,
    ReadyResponse,
    TurnRequest,
    TurnState,
)
from disha_core.pipeline.router import Intent, IntentRouter, LayaIntentClassifier
from disha_core.pipeline.validator import (
    CHANNEL_RE,
    CHANNEL_REPLACEMENT,
    MEAL_NOT_FOUND_REPLACEMENT,
    SentenceValidator,
)
from disha_core.services.auth_service import (
    access_token_hash,
    login_patient,
    register_patient,
)
from disha_core.services.patient_service import fetch_patient_profile
from disha_core.voice import VoiceSession, transcribe_groq

MAX_VOICE_TURN_BYTES = 10 * 1024 * 1024  # 10 MB limit for voice turns
logger = logging.getLogger(__name__)

# Re-export public symbols for backward compatibility with existing tests
__all__ = [
    "MAX_VOICE_TURN_BYTES",
    "LoginRequest",
    "OnboardingRequest",
    "TurnRequest",
    "TurnState",
    "access_token_hash",
    "app",
    "build_patient_context",
    "create_app",
    "logger",
    "render_user_payload",
    "validated_sentences",
]


def _enqueue_audit(ledger: AuditLedger | None, record: AuditRecord) -> None:
    """Enqueue audit event into ledger queue with zero-PHI warning on overflow."""
    if ledger is not None and not ledger.enqueue(record):
        logger.warning("Audit queue overflow; event not recorded")


async def _authenticated_patient(request: Request | WebSocket, authorization: str | None) -> str:
    """Resolve patient ID from bearer authorization token."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.casefold() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Bearer token required")
    pool = getattr(getattr(request, "app", request).state, "pool", None)
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
    request: Request | WebSocket,
    patient_id: str,
    payload: TurnRequest,
    state: TurnState,
) -> AsyncIterator[str]:
    """Execute pipeline routing, retrieval, LLM streaming, and sentence validation."""
    app_state = getattr(request, "app", request).state
    router = app_state.router

    if hasattr(router, "async_route"):
        emergency, intent = await router.async_route(payload.text)
    else:
        emergency, intent = router.route(payload.text)

    if emergency.triggered:
        state.breaker_status = f"triggered:{emergency.category}"
        yield emergency.response or "Yeh emergency ho sakti hai. Abhi 112 par call karein."
        return

    if CHANNEL_RE.search(payload.text):
        state.validator_status = "rewritten:channel_boundary"
        yield CHANNEL_REPLACEMENT
        return

    day = app_state.today_ist()
    context = await build_patient_context(
        app_state.pool, patient_id, day, payload.meal_type
    )
    normalized = normalize(payload.text)
    context["clinical_tags"] = normalized.tags
    context["intent"] = intent.value if intent else Intent.UNKNOWN.value

    if intent == Intent.MEAL_QUERY and context["diet_status"] == "NOT_FOUND":
        state.validator_status = "rewritten:meal_not_found"
        yield MEAL_NOT_FOUND_REPLACEMENT
        return

    async with app_state.pool.acquire() as connection:
        chunks = await retrieve_chunks(connection, normalized.normalized, patient_id=patient_id)

    add_approved_remedy_constraints(context, chunks)
    prompt = render_user_payload(normalized.normalized, context, chunks)
    emitted = False

    try:
        async for sentence in validated_sentences(
            app_state.llm.stream(prompt), app_state.validator, context
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
    """Application factory initializing routes, middleware, and dependency lifecycle."""
    setup_structured_logging()
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 1. Pipeline and ML components
        classifier_adapter = LayaClassifierAdapter()
        try:
            from disha_core.classifier.review_queue import ReviewQueueManager
            review_queue = ReviewQueueManager()
            classifier_adapter.set_review_queue(review_queue)
            app.state.review_queue = review_queue
        except Exception as exc:
            logger.warning("Could not initialize ReviewQueueManager: %s", exc)
            app.state.review_queue = None
        app.state.classifier_adapter = classifier_adapter
        app.state.router = IntentRouter(LayaIntentClassifier(classifier_adapter))
        app.state.validator = SentenceValidator()
        app.state.llm = DualProviderClient()

        # 2. Database connection pool
        pool = await create_database_pool(
            database_url=os.getenv("DATABASE_URL"),
            min_size=int(os.getenv("DB_POOL_MIN", str(settings.db_pool_min))),
            max_size=int(os.getenv("DB_POOL_MAX", str(settings.db_pool_max))),
            timeout=float(os.getenv("DB_POOL_TIMEOUT", str(settings.db_pool_timeout))),
        )

        ledger = None
        if pool is not None:
            ledger = AuditLedger(pool)
            ledger.start()

        app.state.pool = pool
        app.state.ledger = ledger
        app.state.today_ist = lambda: datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%A").casefold()

        try:
            yield
        finally:
            if ledger is not None:
                await ledger.close()
            if pool is not None:
                await pool.close()

    app = FastAPI(
        title="Disha AI Core",
        version="0.2.0",
        description="Layered backend architecture and safety-critical clinical core.",
        lifespan=lifespan,
    )
    app.state.pool = None
    app.state.ledger = None
    app.state.today_ist = lambda: datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%A").casefold()

    # CORS configuration
    origins = [v.strip() for v in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if v.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )

    # Top-level API Routes (Registered directly for path introspectability)
    @app.get("/health", response_model=HealthResponse)
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

    @app.get("/ready", response_model=ReadyResponse)
    async def ready(request: Request) -> dict[str, Any]:
        pool = getattr(request.app.state, "pool", None)
        if pool is None:
            raise HTTPException(status_code=503, detail="Database pool not initialized")
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Database connectivity failure") from exc

        classifier = getattr(request.app.state, "classifier_adapter", None)
        is_classifier_ready = await classifier.is_ready() if classifier is not None else False
        if not is_classifier_ready:
            raise HTTPException(status_code=503, detail="Laya classifier not ready")

        return {
            "ok": True,
            "database": True,
            "classifier": True,
            "schema_version": "2026-11-07.v1",
        }

    @app.get("/internal/classifier")
    async def classifier_status(request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        admin_key = os.getenv("ADMIN_API_KEY", "")
        if admin_key:
            token = (authorization or "").removeprefix("Bearer ").strip()
            if token != admin_key:
                raise HTTPException(status_code=403, detail="Admin authorization required")
        classifier = getattr(request.app.state, "classifier_adapter", None)
        if classifier is None:
            raise HTTPException(status_code=503, detail="Classifier adapter not initialized")
        return classifier.get_status()

    @app.post("/client-errors")
    async def log_client_error(payload: dict[str, Any], request: Request) -> dict[str, bool]:
        err_msg = str(payload.get("message", "unknown"))[:200]
        err_source = str(payload.get("source", "browser"))[:100]
        logging.getLogger("disha.client").warning("[Client Error] source=%s msg=%s", err_source, err_msg)
        return {"logged": True}

    @app.post("/auth/register")
    @app.post("/auth/onboarding")
    async def register(payload: OnboardingRequest, request: Request) -> dict[str, Any]:
        pool = getattr(request.app.state, "pool", None)
        return await register_patient(pool, payload)

    @app.post("/auth/login")
    async def login(payload: LoginRequest, request: Request) -> dict[str, Any]:
        pool = getattr(request.app.state, "pool", None)
        return await login_patient(pool, payload)

    @app.get("/patient/profile")
    async def get_patient_profile(request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        patient_id = await _authenticated_patient(request, authorization)
        pool = getattr(request.app.state, "pool", None)
        day = request.app.state.today_ist()
        return await fetch_patient_profile(pool, patient_id, day)

    @app.post("/chat", response_model=ChatResponse)
    async def chat(
        payload: TurnRequest,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        emergency = request.app.state.router.breaker.check(payload.text)
        if emergency.triggered:
            return {
                "response": emergency.response or "Yeh emergency ho sakti hai. Abhi 112 par call karein.",
                "status": f"triggered:{emergency.category}",
            }

        patient_id = await _authenticated_patient(request, authorization)
        state = TurnState()
        sentences = [sentence async for sentence in _turn_sentences(request, patient_id, payload, state)]
        output = " ".join(sentences)

        _enqueue_audit(
            request.app.state.ledger,
            AuditRecord(patient_id, payload.text, output, state.breaker_status, state.validator_status),
        )
        return {"response": output, "status": state.validator_status}

    @app.post("/chat/stream")
    async def chat_stream(
        payload: TurnRequest,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> StreamingResponse:
        emergency = request.app.state.router.breaker.check(payload.text)
        if emergency.triggered:
            text = emergency.response or "Yeh emergency ho sakti hai. Abhi 112 par call karein."

            async def emergency_event() -> AsyncIterator[str]:
                yield f"data: {json.dumps({'sentence': text}, ensure_ascii=False)}\n\n"
                yield f"event: done\ndata: {json.dumps({'status': f'triggered:{emergency.category}'})}\n\n"

            return StreamingResponse(emergency_event(), media_type="text/event-stream")

        patient_id = await _authenticated_patient(request, authorization)
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
                    AuditRecord(patient_id, payload.text, " ".join(output), state.breaker_status, state.validator_status),
                )

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    @app.websocket("/voice")
    @app.websocket("/ws/conversation")
    async def voice(websocket: WebSocket) -> None:
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
            patient_id = await _authenticated_patient(websocket, f"Bearer {token}")
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
                    await websocket.send_json(
                        {"type": "error", "message": "Voice turn unavailable; please try again."}
                    )
            finally:
                if transcript:
                    _enqueue_audit(
                        getattr(websocket.app.state, "ledger", None),
                        AuditRecord(
                            patient_id, transcript, " ".join(output), state.breaker_status, state.validator_status
                        ),
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
                    await websocket.send_json(
                        {"type": "error", "message": "Voice turn unavailable; please try again."}
                    )
            finally:
                if text:
                    _enqueue_audit(
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

    # Static frontend assets
    frontend_dir = Path(__file__).resolve().parent / "frontend"
    if frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

    return app


app = create_app()
