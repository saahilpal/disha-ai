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
import re
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator
from zoneinfo import ZoneInfo

import asyncpg
from fastapi import FastAPI, Header, HTTPException, Request, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocketDisconnect

from disha_core.adapters.db import create_database_pool
from disha_core.classifier.adapter import LayaClassifierAdapter
from disha_core.compliance.ledger import AuditLedger, AuditRecord
from disha_core.config import get_settings
from disha_core.engine.context_builder import (
    build_patient_context,
    render_user_payload,
)
from disha_core.engine.retriever import retrieve_chunks  # noqa: F401
from disha_core.harness import ResponseHarness, format_system_error
from disha_core.llm.client import DualProviderClient
from disha_core.llm.sentence_buffer import validated_sentences
from disha_core.logging_config import setup_structured_logging
from disha_core.models.schemas import (
    ChatResponse,
    HealthResponse,
    LoginRequest,
    OnboardingRequest,
    ProfileUpdateRequest,
    ReadyResponse,
    TurnRequest,
    TurnState,
)
from disha_core.models.turn_context import TurnContext
from disha_core.pipeline.router import IntentRouter, LayaIntentClassifier
from disha_core.pipeline.validator import (
    SentenceValidator,
)
from disha_core.security.rate_limiter import limiter
from disha_core.services.auth_service import (
    access_token_hash,
    login_patient,
    register_patient,
)
from disha_core.services.patient_service import fetch_patient_profile, update_patient_profile
from disha_core.voice import VoiceSession, detect_turn_language, execute_voice_turn, transcribe_groq

MAX_VOICE_TURN_BYTES = 10 * 1024 * 1024  # 10 MB limit for voice turns
logger = logging.getLogger(__name__)
EXPLICIT_NO_EXERCISE_LIMITATION_RE = re.compile(
    r"\b(?:no|without|don't have|do not have)\s+(?:any\s+)?"
    r"(?:known\s+)?(?:pain|injuries|injury|physical limitations?|mobility issues?|"
    r"exercise restrictions?)\b",
    re.I,
)

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


def _response_metadata(
    state: TurnState,
    *,
    status: str | None = None,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Return bounded provenance metadata shared by all turn response channels."""
    return {
        "status": status or state.validator_status,
        "evidence_ids": list(state.evidence_ids),
        "retrieval_status": state.retrieval_status,
        "conversation_id": conversation_id,
    }


async def _authenticated_patient(request: Request | WebSocket, authorization: str | None) -> str:
    """Resolve patient ID from bearer authorization token."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.casefold() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Bearer token required")
    pool = getattr(getattr(request, "app", request).state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Patient storage unavailable")
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT patient_id FROM patient_access_tokens
                   WHERE token_hash = $1 AND revoked_at IS NULL
                     AND (expires_at IS NULL OR expires_at > NOW())""",
                access_token_hash(token.strip()),
            )
    except (asyncpg.PostgresError, ConnectionError, OSError, RuntimeError) as exc:
        logger.warning("Database unavailable during token auth: %s", exc)
        raise HTTPException(status_code=503, detail="Database temporarily unavailable; please retry shortly")
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return str(row["patient_id"])


async def _turn_sentences(
    request: Request | WebSocket,
    patient_id: str,
    payload: TurnRequest,
    state: TurnState,
) -> AsyncIterator[str]:
    """Execute pipeline routing, retrieval, LLM streaming, and sentence validation via ResponseHarness."""
    app_state = getattr(request, "app", request).state
    harness = getattr(app_state, "harness", None)
    if harness is None:
        validator = getattr(app_state, "validator", None) or SentenceValidator()
        llm = getattr(app_state, "llm", None) or DualProviderClient()
        harness = ResponseHarness(llm, validator)

    turn_ctx = TurnContext(patient_id=patient_id)
    if hasattr(request, "state"):
        request.state.turn_context = turn_ctx

    async for sentence in harness.execute_turn(request, patient_id, payload, legacy_state=state, turn_context=turn_ctx):
        yield sentence


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
        app.state.harness = ResponseHarness(app.state.llm, app.state.validator)

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
    app.state.sync_history = True
    app.state.today_ist = lambda: datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%A").casefold()

    # CORS configuration
    origins = [v.strip() for v in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if v.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=["Authorization", "Content-Type"],
        )

    # Request body size limiter middleware (Max 2 MB for standard JSON payloads)
    @app.middleware("http")
    async def enforce_payload_size_limit(request: Request, call_next: Any) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                max_bytes = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(settings.max_request_body_bytes)))
                if int(content_length) > max_bytes:
                    return Response(
                        content=json.dumps({"detail": "Payload too large. Maximum allowed size is 2MB."}),
                        status_code=413,
                        media_type="application/json",
                    )
            except ValueError:
                pass
        return await call_next(request)

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
        client_ip = request.client.host if request.client else "127.0.0.1"
        allowed, _, retry_after = limiter.is_allowed(f"auth_{client_ip}", "auth", limit=20, window_seconds=60.0)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": str(int(retry_after))},
            )
        pool = getattr(request.app.state, "pool", None)
        return await register_patient(pool, payload)

    @app.post("/auth/login")
    async def login(payload: LoginRequest, request: Request) -> dict[str, Any]:
        client_ip = request.client.host if request.client else "127.0.0.1"
        allowed, _, retry_after = limiter.is_allowed(f"auth_{client_ip}", "auth", limit=20, window_seconds=60.0)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": str(int(retry_after))},
            )
        pool = getattr(request.app.state, "pool", None)
        return await login_patient(pool, payload)

    @app.get("/patient/profile")
    async def get_patient_profile(request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        patient_id = await _authenticated_patient(request, authorization)
        pool = getattr(request.app.state, "pool", None)
        day = request.app.state.today_ist()
        return await fetch_patient_profile(pool, patient_id, day)

    @app.get("/patient/journey")
    async def get_patient_journey(request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        """Retrieve persistent patient onboarding journey state."""
        from disha_core.journey import load_or_create_journey

        patient_id = await _authenticated_patient(request, authorization)
        pool = getattr(request.app.state, "pool", None)
        if not pool:
            return {"current_stage": 1, "overall_status": "in_progress", "last_completed_stage": 0}
        async with pool.acquire() as conn:
            return await load_or_create_journey(patient_id, conn)

    @app.put("/patient/profile")
    async def update_patient_profile_endpoint(
        payload: ProfileUpdateRequest,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        patient_id = await _authenticated_patient(request, authorization)
        pool = getattr(request.app.state, "pool", None)
        day = request.app.state.today_ist()
        updates = payload.model_dump(exclude_unset=True)
        return await update_patient_profile(pool, patient_id, updates, day)

    @app.get("/chat/conversation")
    async def get_active_conversation(
        request: Request,
        authorization: str | None = Header(default=None),
        limit: int = 50,
    ) -> dict[str, Any]:
        """Resolve and hydrate the active conversation with chronological messages (Contract 2 / Spec M1)."""
        patient_id = await _authenticated_patient(request, authorization)
        pool = getattr(request.app.state, "pool", None)
        if pool is None:
            return {"conversation_id": None, "user_id": patient_id, "messages": [], "dialogue_state": {}}
        from disha_core.services.chat_service import get_active_conversation_with_messages

        return await get_active_conversation_with_messages(pool, patient_id, limit=limit)

    @app.post("/chat/conversation/new")
    async def new_conversation(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Archive active conversation and spawn a fresh one (Contract 2 / Spec M1)."""
        patient_id = await _authenticated_patient(request, authorization)
        pool = getattr(request.app.state, "pool", None)
        if pool is None:
            return {"status": "ok", "conversation_id": None}
        from disha_core.services.chat_service import archive_active_conversation, resolve_active_conversation

        await archive_active_conversation(pool, patient_id)
        conv = await resolve_active_conversation(pool, patient_id)
        return {"status": "ok", "conversation": conv}

    @app.get("/chat/history")
    async def get_chat_history(
        request: Request,
        authorization: str | None = Header(default=None),
        limit: int = 30,
    ) -> dict[str, Any]:
        """Chronological turn history for backward compatibility with older UI and tests."""
        patient_id = await _authenticated_patient(request, authorization)
        pool = getattr(request.app.state, "pool", None)
        if pool is not None:
            from disha_core.services.chat_service import (
                get_active_conversation_with_messages,
                load_conversation_history,
            )

            active_data = await get_active_conversation_with_messages(pool, patient_id, limit=limit)
            if active_data.get("messages"):
                history = [
                    {"role": m["role"], "content": m["content"]} for m in active_data["messages"] if m.get("content")
                ]
                return {"patient_id": patient_id, "history": history}
            # Fallback to patient_turn_journal
            history = await load_conversation_history(pool, patient_id, limit=limit)
            return {"patient_id": patient_id, "history": history}
        return {"patient_id": patient_id, "history": []}

    @app.post("/chat", response_model=ChatResponse)
    async def chat(
        payload: TurnRequest,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        client_key = (
            authorization.removeprefix("Bearer ").strip()
            if authorization
            else (request.client.host if request.client else "127.0.0.1")
        )
        allowed, _, retry_after = limiter.is_allowed(f"chat_{client_key[:16]}", "chat", limit=60, window_seconds=60.0)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": str(int(retry_after))},
            )

        emergency = request.app.state.router.breaker.check(payload.text)
        if emergency.triggered:
            text = emergency.response or "Yeh emergency ho sakti hai. Abhi 112 par call karein."
            with suppress(Exception):
                patient_id = await _authenticated_patient(request, authorization)
                pool = getattr(request.app.state, "pool", None)
                if pool is not None:
                    from disha_core.services.chat_service import (
                        record_message,
                        resolve_active_conversation,
                        store_conversation_turn,
                    )

                    conv = await resolve_active_conversation(pool, patient_id)
                    if conv and conv.get("id"):
                        cid = str(conv["id"])
                        c_msg_id = getattr(payload, "client_msg_id", None) or str(uuid.uuid4())
                        await record_message(
                            pool, cid, patient_id, "user", "chat", payload.text, status="complete", client_msg_id=c_msg_id
                        )
                        await record_message(
                            pool,
                            cid,
                            patient_id,
                            "assistant",
                            "chat",
                            text,
                            status="complete",
                            client_msg_id=f"{c_msg_id}:assistant",
                        )
                    await store_conversation_turn(pool, patient_id, payload.text, text)
            _enqueue_audit(
                request.app.state.ledger,
                AuditRecord(
                    patient_id if "patient_id" in locals() else "unknown", payload.text, text, "triggered", "emergency"
                ),
            )
            return {
                "response": text,
                **_response_metadata(
                    TurnState(),
                    status=f"triggered:{emergency.category}",
                ),
            }

        try:
            patient_id = await _authenticated_patient(request, authorization)
        except HTTPException as he:
            if he.status_code == 503:
                return {
                    "response": format_system_error(
                        "Database connection unavailable", "Kripya thodi der baad koshish karein."
                    ),
                    **_response_metadata(
                        TurnState(retrieval_status="unavailable"),
                        status="deflected:db_unavailable",
                    ),
                }
            raise
        state = TurnState()
        sentences = [sentence async for sentence in _turn_sentences(request, patient_id, payload, state)]
        output = " ".join(sentences)

        # Persist turn to active conversation (Spec M1 / Contract 2)
        pool = getattr(request.app.state, "pool", None)
        conversation_id = None
        if pool is not None:
            with suppress(Exception):
                from disha_core.services.chat_service import record_message, resolve_active_conversation

                conv = await resolve_active_conversation(pool, patient_id)
                if conv and conv.get("id"):
                    cid = str(conv["id"])
                    conversation_id = cid
                    c_msg_id = getattr(payload, "client_msg_id", None) or str(uuid.uuid4())
                    await record_message(
                        pool, cid, patient_id, "user", "chat", payload.text, status="complete", client_msg_id=c_msg_id
                    )
                    await record_message(
                        pool,
                        cid,
                        patient_id,
                        "assistant",
                        "chat",
                        output,
                        status="complete",
                        client_msg_id=f"{c_msg_id}:assistant",
                    )

        _enqueue_audit(
            request.app.state.ledger,
            AuditRecord(patient_id, payload.text, output, state.breaker_status, state.validator_status),
        )
        return {
            "response": output,
            **_response_metadata(state, conversation_id=conversation_id),
        }

    @app.post("/chat/stream")
    async def chat_stream(
        payload: TurnRequest,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> StreamingResponse:
        client_key = (
            authorization.removeprefix("Bearer ").strip()
            if authorization
            else (request.client.host if request.client else "127.0.0.1")
        )
        allowed, _, retry_after = limiter.is_allowed(f"chat_{client_key[:16]}", "chat", limit=60, window_seconds=60.0)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": str(int(retry_after))},
            )

        emergency = request.app.state.router.breaker.check(payload.text)
        if emergency.triggered:
            text = emergency.response or "Yeh emergency ho sakti hai. Abhi 112 par call karein."
            with suppress(Exception):
                patient_id = await _authenticated_patient(request, authorization)
                pool = getattr(request.app.state, "pool", None)
                if pool is not None:
                    from disha_core.services.chat_service import (
                        record_message,
                        resolve_active_conversation,
                        store_conversation_turn,
                    )

                    conv = await resolve_active_conversation(pool, patient_id)
                    if conv and conv.get("id"):
                        cid = str(conv["id"])
                        c_msg_id = getattr(payload, "client_msg_id", None) or str(uuid.uuid4())
                        await record_message(
                            pool, cid, patient_id, "user", "chat", payload.text, status="complete", client_msg_id=c_msg_id
                        )
                        await record_message(
                            pool,
                            cid,
                            patient_id,
                            "assistant",
                            "chat",
                            text,
                            status="complete",
                            client_msg_id=f"{c_msg_id}:assistant",
                        )
                    await store_conversation_turn(pool, patient_id, payload.text, text)
            _enqueue_audit(
                request.app.state.ledger,
                AuditRecord(
                    patient_id if "patient_id" in locals() else "unknown", payload.text, text, "triggered", "emergency"
                ),
            )
            metadata = _response_metadata(
                TurnState(),
                status=f"triggered:{emergency.category}",
            )

            async def emergency_event() -> AsyncIterator[str]:
                yield f"data: {json.dumps({'sentence': text}, ensure_ascii=False)}\n\n"
                yield f"event: done\ndata: {json.dumps(metadata)}\n\n"

            return StreamingResponse(
                emergency_event(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        try:
            patient_id = await _authenticated_patient(request, authorization)
        except HTTPException as he:
            if he.status_code == 503:
                text = format_system_error("Database connection unavailable", "Kripya thodi der baad koshish karein.")
                metadata = _response_metadata(
                    TurnState(retrieval_status="unavailable"),
                    status="deflected:db_unavailable",
                )

                async def unavailable_event() -> AsyncIterator[str]:
                    yield f"data: {json.dumps({'sentence': text}, ensure_ascii=False)}\n\n"
                    yield f"event: done\ndata: {json.dumps(metadata)}\n\n"

                return StreamingResponse(
                    unavailable_event(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    },
                )
            raise
        state = TurnState()
        pool = getattr(request.app.state, "pool", None)
        asst_msg_id = None
        conversation_id = None
        if pool is not None:
            with suppress(Exception):
                from disha_core.services.chat_service import record_message, resolve_active_conversation

                conv = await resolve_active_conversation(pool, patient_id)
                if conv and conv.get("id"):
                    cid = str(conv["id"])
                    conversation_id = cid
                    c_msg_id = getattr(payload, "client_msg_id", None) or str(uuid.uuid4())
                    await record_message(
                        pool, cid, patient_id, "user", "chat", payload.text, status="complete", client_msg_id=c_msg_id
                    )
                    asst_rec = await record_message(
                        pool,
                        cid,
                        patient_id,
                        "assistant",
                        "chat",
                        "",
                        status="streaming",
                        client_msg_id=f"{c_msg_id}:assistant",
                    )
                    if asst_rec and asst_rec.get("id"):
                        asst_msg_id = str(asst_rec["id"])

        async def events() -> AsyncIterator[str]:
            output: list[str] = []
            try:
                async for sentence in _turn_sentences(request, patient_id, payload, state):
                    output.append(sentence)
                    yield f"data: {json.dumps({'sentence': sentence}, ensure_ascii=False)}\n\n"
                    if await request.is_disconnected():
                        break
                yield f"event: done\ndata: {json.dumps(_response_metadata(state, conversation_id=conversation_id))}\n\n"
            except (asyncio.CancelledError, GeneratorExit):
                pass
            finally:
                if pool is not None and asst_msg_id is not None:
                    with suppress(Exception):
                        from disha_core.services.chat_service import update_message_status

                        final_reply = " ".join(output)
                        st = (
                            "complete"
                            if output and state.validator_status in ("validated", "accepted")
                            else ("aborted" if not output else "complete")
                        )
                        await update_message_status(pool, asst_msg_id, st, content=final_reply)

                _enqueue_audit(
                    request.app.state.ledger,
                    AuditRecord(
                        patient_id, payload.text, " ".join(output), state.breaker_status, state.validator_status
                    ),
                )

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.websocket("/voice")
    @app.websocket("/ws/conversation")
    async def voice(websocket: WebSocket) -> None:
        await websocket.accept()
        auth_frame_received = False
        token = (
            websocket.query_params.get("token")
            or (websocket.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        )

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

        stored_lang = "hinglish"
        pool = getattr(websocket.app.state, "pool", None)
        if pool is not None:
            with suppress(Exception):
                row = await pool.fetchrow("SELECT language FROM patient_profiles WHERE patient_id = $1", patient_id)
                if row and row.get("language"):
                    stored_lang = str(row["language"])

        async def process_audio(audio: bytes) -> None:
            transcript = ""
            state = TurnState()
            output: list[str] = []
            try:
                async with asyncio.timeout(30.0):
                    transcript = await transcribe_groq(audio, language=stored_lang)
                    await websocket.send_json({"type": "transcript", "text": transcript})
                    output = await execute_voice_turn(
                        websocket,
                        patient_id,
                        transcript,
                        session,
                        send_json=websocket.send_json,
                        send_audio=websocket.send_bytes,
                        state=state,
                    )
            except (asyncio.CancelledError, GeneratorExit):
                raise
            except (asyncio.TimeoutError, TimeoutError):
                with suppress(Exception):
                    await websocket.send_json({"type": "error", "message": "Voice processing timed out."})
            except Exception as exc:
                err_str = str(exc)
                if "filtered silence hallucination" in err_str or "silent audio frame" in err_str:
                    with suppress(Exception):
                        await websocket.send_json({"type": "silence", "message": "Silence detected"})
                    return
                with suppress(Exception):
                    await websocket.send_json({"type": "error", "message": "Voice turn unavailable; please try again."})
            finally:
                if transcript:
                    pool = getattr(websocket.app.state, "pool", None)
                    if pool is not None and output:
                        with suppress(Exception):
                            from disha_core.services.chat_service import (
                                record_message,
                                resolve_active_conversation,
                                store_conversation_turn,
                            )

                            conv = await resolve_active_conversation(pool, patient_id, channel="voice")
                            if conv and conv.get("id"):
                                cid = str(conv["id"])
                                await record_message(
                                    pool, cid, patient_id, "user", "voice", transcript, status="complete"
                                )
                                await record_message(
                                    pool, cid, patient_id, "assistant", "voice", " ".join(output), status="complete"
                                )
                            await store_conversation_turn(pool, patient_id, transcript, " ".join(output))

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
                async with asyncio.timeout(30.0):
                    await websocket.send_json({"type": "transcript", "text": text, "is_text_echo": True})
                    output = await execute_voice_turn(
                        websocket,
                        patient_id,
                        text,
                        session,
                        send_json=websocket.send_json,
                        send_audio=websocket.send_bytes,
                        state=state,
                    )
            except (asyncio.CancelledError, GeneratorExit):
                raise
            except (asyncio.TimeoutError, TimeoutError):
                with suppress(Exception):
                    await websocket.send_json({"type": "error", "message": "Text processing timed out."})
            except Exception:
                with suppress(Exception):
                    await websocket.send_json({"type": "error", "message": "Voice turn unavailable; please try again."})
            finally:
                if text:
                    pool = getattr(websocket.app.state, "pool", None)
                    if pool is not None and output:
                        with suppress(Exception):
                            from disha_core.services.chat_service import (
                                record_message,
                                resolve_active_conversation,
                                store_conversation_turn,
                            )

                            conv = await resolve_active_conversation(pool, patient_id, channel="voice")
                            if conv and conv.get("id"):
                                cid = str(conv["id"])
                                await record_message(pool, cid, patient_id, "user", "voice", text, status="complete")
                                await record_message(
                                    pool, cid, patient_id, "assistant", "voice", " ".join(output), status="complete"
                                )
                            await store_conversation_turn(pool, patient_id, text, " ".join(output))

                    _enqueue_audit(
                        getattr(websocket.app.state, "ledger", None),
                        AuditRecord(patient_id, text, " ".join(output), state.breaker_status, state.validator_status),
                    )

        try:
            while True:
                try:
                    message = await asyncio.wait_for(websocket.receive(), timeout=300.0)
                except (asyncio.TimeoutError, TimeoutError):
                    with suppress(Exception):
                        await websocket.close(code=1000, reason="Inactivity timeout")
                    break

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
                                    await websocket.send_json({"type": "authenticated", "patient_id": patient_id})
                                continue
                            elif msg_type == "audio" and parsed.get("data"):
                                import base64

                                audio = base64.b64decode(parsed["data"])
                            elif msg_type == "text" and parsed.get("text"):
                                text_input = str(parsed["text"]).strip()
                            elif msg_type in ("interim_transcript", "interim", "partial_transcript") and parsed.get(
                                "text"
                            ):
                                interim_text = str(parsed["text"]).strip()
                                if interim_text:
                                    router = getattr(websocket.app.state, "router", None)
                                    breaker = getattr(router, "breaker", None) if router else None
                                    if breaker:
                                        emergency = breaker.check(interim_text)
                                        if emergency.triggered:
                                            await cancel_active_turn()
                                            resp_text = emergency.response or breaker.default_protocol
                                            with suppress(Exception):
                                                await websocket.send_json(
                                                    {"type": "transcript", "text": interim_text, "is_interim": True}
                                                )
                                                await websocket.send_json({"type": "sentence", "text": resp_text})
                                                await websocket.send_json(
                                                    {"type": "done", "status": f"triggered:{emergency.category}"}
                                                )
                                            sent_lang = detect_turn_language(resp_text)
                                            with suppress(Exception):
                                                await session.speak(resp_text, websocket.send_bytes, language=sent_lang)
                                            continue

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
        except (WebSocketDisconnect, RuntimeError):
            pass
        except Exception as exc:
            logger.warning("Voice websocket unexpected exception: %s", exc)
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
