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
    add_approved_remedy_constraints,
    build_patient_context,
    determine_length_policy,
    normalize_preferred_language,
    render_user_payload,
)
from disha_core.engine.normalizer import (
    UNSUPPORTED_LANGUAGE_REPLACEMENT,
    is_prescribed_meal_query,
    is_unsupported_language,
    normalize,
)
from disha_core.engine.retriever import retrieve_chunks
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
from disha_core.pep.exercise_safety import extract_patient_health_tags
from disha_core.pipeline.router import Intent, IntentRouter, LayaIntentClassifier
from disha_core.pipeline.validator import (
    MEAL_NOT_FOUND_REPLACEMENT,
    PEP_REPLACEMENT,
    SentenceValidator,
    knowledge_unavailable_response,
)
from disha_core.security.rate_limiter import limiter
from disha_core.services.auth_service import (
    access_token_hash,
    login_patient,
    register_patient,
)
from disha_core.services.patient_service import fetch_patient_profile, update_patient_profile
from disha_core.voice import VoiceSession, execute_voice_turn, transcribe_groq

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
) -> dict[str, Any]:
    """Return bounded provenance metadata shared by all turn response channels."""
    return {
        "status": status or state.validator_status,
        "evidence_ids": list(state.evidence_ids),
        "retrieval_status": state.retrieval_status,
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
    """Execute pipeline routing, retrieval, LLM streaming, and sentence validation."""
    app_state = getattr(request, "app", request).state
    router = app_state.router

    pep_risk = 0
    skip_retrieval = False
    if hasattr(router, "async_route_decision"):
        decision = await router.async_route_decision(payload.text)
        emergency = decision.breaker
        intent = decision.intent
        pep_risk = decision.pep_risk
        skip_retrieval = decision.skip_retrieval
    elif hasattr(router, "async_route"):
        emergency, intent = await router.async_route(payload.text)
        pep_risk = getattr(router, "last_pep_risk", 0)
        skip_retrieval = intent in {Intent.GENERAL_COACHING, Intent.APP_META, Intent.GREETING}
    else:
        emergency, intent = router.route(payload.text)
        pep_risk = getattr(router, "last_pep_risk", 0)
        skip_retrieval = intent in {Intent.GENERAL_COACHING, Intent.APP_META, Intent.GREETING}

    emitted = False
    generated_sentences: list[str] = []

    if emergency.triggered:
        state.breaker_status = f"triggered:{emergency.category}"
        text = emergency.response or "Yeh emergency ho sakti hai. Abhi 112 par call karein."
        generated_sentences.append(text)
        yield text
        return

    # Language Boundary Check: Deflect non-supported languages politely
    if is_unsupported_language(payload.text):
        state.validator_status = "deflected:unsupported_language"
        generated_sentences.append(UNSUPPORTED_LANGUAGE_REPLACEMENT)
        yield UNSUPPORTED_LANGUAGE_REPLACEMENT
        return

    day = app_state.today_ist()
    prescribed_meal_query = is_prescribed_meal_query(payload.text)
    pool = getattr(app_state, "pool", None)
    try:
        if pool is None:
            context = await build_patient_context(
                None,
                patient_id,
                day,
                payload.meal_type if prescribed_meal_query else None,
                user_input=payload.text,
                intent=intent.value if intent else None,
            )
        else:
            async with pool.acquire() as connection:
                context = await build_patient_context(
                    connection,
                    patient_id,
                    day,
                    payload.meal_type if prescribed_meal_query else None,
                    user_input=payload.text,
                    intent=intent.value if intent else None,
                )
    except (asyncpg.PostgresError, ConnectionError, OSError, RuntimeError) as exc:
        logger.warning("Database unavailable in _turn_sentences: %s", exc)
        state.validator_status = "deflected:db_unavailable"
        state.retrieval_status = "unavailable"
        deflection_msg = "Disha abhi technical samasya ke kaaran database se connect nahi kar paa rahi. Kripya thodi der baad koshish karein."
        generated_sentences.append(deflection_msg)
        yield deflection_msg
        return
    normalized = normalize(payload.text)
    context["clinical_tags"] = normalized.tags
    context["intent"] = intent.value if intent else Intent.UNKNOWN.value
    context["pep_risk"] = pep_risk
    context["user_input"] = payload.text
    context["meal_relevant"] = normalized.is_meal_query or intent == Intent.MEAL_QUERY
    context["exercise_relevant"] = normalized.is_exercise_query or intent == Intent.EXERCISE_QUERY
    context["length_policy"] = determine_length_policy(
        payload.text,
        intent.value if intent else None,
        is_emergency=emergency.triggered,
    )

    if prescribed_meal_query and payload.meal_type is None:
        state.validator_status = "deflected:meal_window_required"
        yield "Aap apne prescribed plan mein kaunsa meal dekhna chahte hain: breakfast, lunch, ya dinner?"
        return

    if prescribed_meal_query and context.get("diet_status") == "NOT_FOUND":
        state.validator_status = "rewritten:meal_not_found"
        generated_sentences.append(MEAL_NOT_FOUND_REPLACEMENT)
        yield MEAL_NOT_FOUND_REPLACEMENT
        return
    if prescribed_meal_query and context.get("diet_status") != "FOUND":
        state.validator_status = "deflected:meal_plan_unavailable"
        yield "Main abhi aapka saved meal plan access nahi kar paa rahi. Kripya thodi der baad phir koshish karein."
        return

    # Early PEP Risk Triage via Laya System 1:
    pep = context.get("pep") or {}
    restricted = {str(item).replace("_", " ").casefold() for item in pep.get("restricted_modalities") or ()}
    hypertension_stage = str(pep.get("hypertension_stage") or "").casefold().replace("_", " ")
    diagnosed = " ".join(str(item) for item in pep.get("diagnosed_conditions") or ()).casefold()
    has_cardiac_htn = hypertension_stage in {"stage 1", "stage 2", "crisis"} or any(
        condition in diagnosed for condition in ("cardiac", "heart", "coronary", "arrhythmia")
    )
    if pep_risk >= 2 and (restricted or has_cardiac_htn):
        state.validator_status = "rewritten:pep_restriction"
        generated_sentences.append(PEP_REPLACEMENT)
        yield PEP_REPLACEMENT
        return

    if not hasattr(app_state, "conversation_history"):
        app_state.conversation_history = {}

    db_history = context.get("conversation_history") or []
    if patient_id not in app_state.conversation_history or not app_state.conversation_history[patient_id]:
        if db_history:
            app_state.conversation_history[patient_id] = list(db_history)
        else:
            app_state.conversation_history[patient_id] = []

    history = app_state.conversation_history.get(patient_id, [])[-8:]
    context["has_history"] = bool(history)

    # 5-Stage Patient Journey & Retrieval Routing via single acquired connection
    channel = "voice" if hasattr(request, "client_state") or "WebSocket" in str(type(request)) else "chat"
    chunks = ()
    if getattr(app_state, "pool", None) is not None:
        try:
            async with app_state.pool.acquire() as connection:
                with suppress(Exception):
                    from disha_core.journey import (
                        extract_patient_disclosures,
                        load_or_create_journey,
                        record_field_answer,
                        select_next_question,
                    )
                    lang = normalize_preferred_language(
                        (context.get("pep") or {}).get("language")
                    )
                    lang = {"english": "en", "hindi": "hi"}.get(lang, "hinglish")
                    # 1. Multi-field extraction from user input
                    disclosures = extract_patient_disclosures(payload.text, lang=lang)
                    for f_id, f_val in disclosures.items():
                        await record_field_answer(
                            patient_id=patient_id,
                            field_id=f_id,
                            raw_value=f_val,
                            raw_text=payload.text,
                            channel=channel,
                            conn=connection,
                            lang=lang,
                        )

                    # 2. Sync / load journey state
                    journey_state = await load_or_create_journey(patient_id, conn=connection, channel=channel)
                    context["journey_state"] = journey_state

                    # 3. Off-topic check (e.g. general nutrition query vs answering onboarding question)
                    is_off_topic = bool(
                        normalized.is_meal_query 
                        or normalized.is_exercise_query 
                        or intent in {Intent.MEAL_QUERY, Intent.EXERCISE_QUERY, Intent.SYMPTOM_COMPLAINT}
                    ) and not disclosures

                    # 4. Schedule next question
                    scheduled_q = await select_next_question(
                        patient_id=patient_id,
                        journey_state=journey_state,
                        user_turn_text=payload.text,
                        channel=channel,
                        is_emergency=emergency.triggered,
                        is_off_topic_query=is_off_topic,
                        conn=connection,
                        preferred_lang=lang,
                    )
                    if scheduled_q:
                        context["scheduled_question"] = scheduled_q.text

                # Retrieval Routing:
                # Health-domain questions retrieve even when the intent router calls them general coaching.
                should_retrieve = not prescribed_meal_query and (
                    bool(normalized.tags)
                    or normalized.is_meal_query
                    or normalized.is_exercise_query
                    or normalized.is_recommendation_request
                    or (
                        not skip_retrieval
                        and intent not in {Intent.GENERAL_COACHING, Intent.APP_META, Intent.GREETING}
                    )
                )
                if should_retrieve:
                    pep_context = context.get("pep") or {}
                    contextual_terms: list[str] = []
                    if normalized.is_meal_query:
                        contextual_terms.extend(
                            str(value)
                            for value in (
                                pep_context.get("dietary_preference"),
                                pep_context.get("primary_focus"),
                                *(pep_context.get("diagnosed_conditions") or ()),
                            )
                            if value
                        )
                    if normalized.is_exercise_query:
                        contextual_terms.extend(
                            str(value)
                            for value in (
                                pep_context.get("user_reported_concerns"),
                                *(pep_context.get("restricted_modalities") or ()),
                                *(pep_context.get("diagnosed_conditions") or ()),
                            )
                            if value
                        )
                    retrieval_query = " ".join((normalized.normalized, *contextual_terms))
                    profile_tags = normalize(" ".join(contextual_terms)).tags
                    target_tags = list(dict.fromkeys((*normalized.tags, *profile_tags)))
                    chunks = await retrieve_chunks(
                        connection, retrieval_query, patient_id=patient_id, tags=target_tags
                    )
                    state.retrieval_status = "retrieved" if chunks else "no_results"
                    state.evidence_ids = [
                        str(getter("chunk_id"))
                        for chunk in chunks
                        if (getter := (
                            chunk.get
                            if hasattr(chunk, "get")
                            else lambda key, default=None: getattr(chunk, key, default)
                        ))("chunk_id", None) is not None
                    ]
                    if len(state.evidence_ids) != len(chunks):
                        logger.error("Retrieved health guidance without complete chunk provenance")
                        state.retrieval_status = "invalid_provenance"
                        chunks = ()
                        state.evidence_ids = []
                    else:
                        context["retrieved_evidence_ids"] = state.evidence_ids
                    if getattr(app_state, "sync_history", False) and not app_state.conversation_history[patient_id]:
                        with suppress(Exception):
                            from disha_core.services.chat_service import load_conversation_history
                            loaded = await load_conversation_history(connection, patient_id, 8)
                            if loaded:
                                app_state.conversation_history[patient_id] = loaded
                                history = loaded[-8:]
        except (asyncpg.PostgresError, ConnectionError, OSError, RuntimeError) as exc:
            logger.warning("Database retrieval unavailable: %s", exc)
            state.retrieval_status = "unavailable"
            chunks = ()
    elif normalized.tags or intent in {
        Intent.MEAL_QUERY,
        Intent.EXERCISE_QUERY,
        Intent.SYMPTOM_COMPLAINT,
    }:
        state.retrieval_status = "unavailable"

    requires_grounding = (
        bool(normalized.tags)
        or normalized.is_meal_query
        or normalized.is_exercise_query
        or normalized.is_recommendation_request
        or intent in {
        Intent.MEAL_QUERY,
        Intent.EXERCISE_QUERY,
        Intent.SYMPTOM_COMPLAINT,
        }
    )
    if prescribed_meal_query and context.get("diet_status") == "FOUND":
        requires_grounding = False
    if requires_grounding and not chunks:
        state.validator_status = "deflected:knowledge_unavailable"
        preferred_language = (context.get("pep") or {}).get("language")
        yield knowledge_unavailable_response(preferred_language)
        return

    if normalized.is_exercise_query and normalized.is_recommendation_request:
        pep_context = context.get("pep") or {}
        slot_values = [
            str(slot.get("slot_value", ""))
            for slot in context.get("patient_slots") or ()
            if isinstance(slot, dict)
        ]
        safety_text = " ".join(
            str(value)
            for value in (
                payload.text,
                pep_context.get("user_reported_concerns"),
                *(pep_context.get("restricted_modalities") or ()),
                *(pep_context.get("diagnosed_conditions") or ()),
                *slot_values,
            )
            if value
        )
        safety_tags = extract_patient_health_tags(
            pep_data=pep_context,
            reported_symptoms=[
                payload.text,
                str(pep_context.get("user_reported_concerns") or ""),
            ],
            physical_limitations=pep_context.get("restricted_modalities") or (),
            diagnosed_conditions=pep_context.get("diagnosed_conditions") or (),
        )
        has_recorded_safety_context = bool(
            pep_context.get("user_reported_concerns")
            or pep_context.get("restricted_modalities")
            or pep_context.get("diagnosed_conditions")
            or (pep_context.get("hypertension_stage") or "").casefold()
            not in {"", "unknown", "none"}
            or EXPLICIT_NO_EXERCISE_LIMITATION_RE.search(safety_text)
        )
        if safety_tags:
            state.validator_status = "deflected:exercise_suitability_uncertain"
            yield (
                "Aapke bataye hue ya saved health context ke saath main abhi workout ya alternate movement "
                "recommend nahi karungi, kyunki uski suitability establish nahi hui. Aap apni limitation "
                "aur jis activity ke baare mein pooch rahe hain woh batayein; zarurat par clinician se "
                "suitability confirm karein."
            )
            return
        if not has_recorded_safety_context:
            state.validator_status = "deflected:exercise_context_required"
            yield (
                "Personalized exercise suggestion se pehle batayein ki aapko pain, injury, recent surgery, "
                "mobility difficulty, heart condition, ya exercise restriction hai ya nahi. Bina is context "
                "ke main workout recommend nahi karungi."
            )
            return

    add_approved_remedy_constraints(context, chunks)
    prompt = render_user_payload(normalized.normalized, context, chunks)

    try:
        llm_stream = app_state.llm.stream(prompt, messages=history)
    except TypeError:
        llm_stream = app_state.llm.stream(prompt)

    try:
        async for sentence in validated_sentences(
            llm_stream, app_state.validator, context
        ):
            emitted = True
            generated_sentences.append(sentence)
            yield sentence
    except Exception as exc:
        logger.exception("LLM generation stream failed: %s", exc)
        state.validator_status = "provider_unavailable"
        if not emitted:
            yield "Disha abhi jawab nahi de paa rahi. Kripya thodi der baad phir koshish karein."
    finally:
        if state.validator_status == "accepted":
            state.validator_status = "validated"
        if generated_sentences:
            full_reply = " ".join(generated_sentences)
            if patient_id not in app_state.conversation_history:
                app_state.conversation_history[patient_id] = []
            app_state.conversation_history[patient_id].append({"role": "user", "content": payload.text})
            app_state.conversation_history[patient_id].append({"role": "assistant", "content": full_reply})
            app_state.conversation_history[patient_id] = app_state.conversation_history[patient_id][-16:]

            if getattr(app_state, "pool", None) is not None:
                with suppress(Exception):
                    from disha_core.services.chat_service import persist_patient_disclosure, store_conversation_turn
                    async with app_state.pool.acquire() as save_conn:
                        await store_conversation_turn(save_conn, patient_id, payload.text, full_reply)
                        await persist_patient_disclosure(save_conn, patient_id, payload.text)


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

    @app.post("/chat", response_model=ChatResponse)
    async def chat(
        payload: TurnRequest,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        client_key = authorization.removeprefix("Bearer ").strip() if authorization else (request.client.host if request.client else "127.0.0.1")
        allowed, _, retry_after = limiter.is_allowed(f"chat_{client_key[:16]}", "chat", limit=60, window_seconds=60.0)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": str(int(retry_after))},
            )

        emergency = request.app.state.router.breaker.check(payload.text)
        if emergency.triggered:
            return {
                "response": emergency.response or "Yeh emergency ho sakti hai. Abhi 112 par call karein.",
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
                    "response": "Disha abhi technical samasya ke kaaran database se connect nahi kar paa rahi. Kripya thodi der baad koshish karein.",
                    **_response_metadata(
                        TurnState(retrieval_status="unavailable"),
                        status="deflected:db_unavailable",
                    ),
                }
            raise
        state = TurnState()
        sentences = [sentence async for sentence in _turn_sentences(request, patient_id, payload, state)]
        output = " ".join(sentences)

        _enqueue_audit(
            request.app.state.ledger,
            AuditRecord(patient_id, payload.text, output, state.breaker_status, state.validator_status),
        )
        return {
            "response": output,
            **_response_metadata(state),
        }

    @app.post("/chat/stream")
    async def chat_stream(
        payload: TurnRequest,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> StreamingResponse:
        client_key = authorization.removeprefix("Bearer ").strip() if authorization else (request.client.host if request.client else "127.0.0.1")
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
                text = "Disha abhi technical samasya ke kaaran database se connect nahi kar paa rahi. Kripya thodi der baad koshish karein."
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

        async def events() -> AsyncIterator[str]:
            output: list[str] = []
            try:
                async for sentence in _turn_sentences(request, patient_id, payload, state):
                    output.append(sentence)
                    yield f"data: {json.dumps({'sentence': sentence}, ensure_ascii=False)}\n\n"
                    if await request.is_disconnected():
                        break
                yield f"event: done\ndata: {json.dumps(_response_metadata(state))}\n\n"
            except (asyncio.CancelledError, GeneratorExit):
                pass
            finally:
                _enqueue_audit(
                    request.app.state.ledger,
                    AuditRecord(patient_id, payload.text, " ".join(output), state.breaker_status, state.validator_status),
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
                async with asyncio.timeout(30.0):
                    transcript = await transcribe_groq(audio)
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
                    await websocket.send_json(
                        {"type": "error", "message": "Voice processing timed out."}
                    )
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
                    await websocket.send_json(
                        {"type": "error", "message": "Text processing timed out."}
                    )
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
