"""Chat orchestration, multi-turn persistent memory, and turn processing service for Disha AI Core."""
from __future__ import annotations

import logging
import re
from contextlib import suppress
from typing import Any, AsyncIterator

from disha_core.compliance.ledger import AuditLedger, AuditRecord
from disha_core.engine.context_builder import (
    add_approved_remedy_constraints,
    build_patient_context,
    determine_length_policy,
    render_user_payload,
)
from disha_core.engine.normalizer import normalize
from disha_core.engine.retriever import STOP_WORDS, retrieve_chunks
from disha_core.llm.sentence_buffer import validated_sentences
from disha_core.models.schemas import TurnRequest, TurnState
from disha_core.pipeline.router import Intent
from disha_core.pipeline.validator import (
    MEAL_NOT_FOUND_REPLACEMENT,
    PEP_REPLACEMENT,
)

logger = logging.getLogger("disha_core.main")


def enqueue_audit(ledger: AuditLedger | None, record: AuditRecord) -> None:
    """Safely enqueue an audit record into the background durability ledger.

    Logs a zero-PHI warning if the buffer has overflowed.
    """
    if ledger is not None and not ledger.enqueue(record):
        logger.warning("Audit queue overflow; event not recorded")


async def store_conversation_turn(
    conn_or_pool: Any,
    patient_id: str,
    user_text: str,
    assistant_text: str,
    session_id: str = "default",
) -> None:
    """Persist a completed conversational turn into the immutable patient turn journal."""
    if conn_or_pool is None:
        return
    with suppress(Exception):
        if hasattr(conn_or_pool, "acquire"):
            async with conn_or_pool.acquire() as conn:
                await _store_turn_on_conn(conn, patient_id, user_text, assistant_text, session_id)
        else:
            await _store_turn_on_conn(conn_or_pool, patient_id, user_text, assistant_text, session_id)


async def _store_turn_on_conn(
    conn: Any,
    patient_id: str,
    user_text: str,
    assistant_text: str,
    session_id: str,
) -> None:
    max_idx = await conn.fetchval(
        "SELECT COALESCE(MAX(turn_index), -1) FROM patient_turn_journal WHERE patient_id = $1 AND session_id = $2",
        patient_id, session_id,
    )
    turn_idx = int(max_idx if max_idx is not None else -1) + 1
    await conn.execute(
        """INSERT INTO patient_turn_journal (patient_id, session_id, turn_index, speaker, raw_utterance)
           VALUES ($1, $2, $3, 'user', $4)""",
        patient_id, session_id, turn_idx, user_text,
    )
    if assistant_text:
        await conn.execute(
            """INSERT INTO patient_turn_journal (patient_id, session_id, turn_index, speaker, raw_utterance)
               VALUES ($1, $2, $3, 'assistant', $4)""",
            patient_id, session_id, turn_idx + 1, assistant_text,
        )


async def load_conversation_history(
    conn_or_pool: Any,
    patient_id: str,
    limit: int = 8,
) -> list[dict[str, str]]:
    """Retrieve recent conversation history (last N messages) chronologically from PostgreSQL."""
    if conn_or_pool is None:
        return []
    history: list[dict[str, str]] = []
    with suppress(Exception):
        if hasattr(conn_or_pool, "acquire"):
            async with conn_or_pool.acquire() as conn:
                history = await _load_history_on_conn(conn, patient_id, limit)
        else:
            history = await _load_history_on_conn(conn_or_pool, patient_id, limit)
    return history


async def _load_history_on_conn(conn: Any, patient_id: str, limit: int) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    rows = await conn.fetch(
        """SELECT speaker, raw_utterance FROM patient_turn_journal
           WHERE patient_id = $1
           ORDER BY timestamp_utc DESC LIMIT $2""",
        patient_id, limit,
    )
    for r in reversed(rows):
        speaker = str(r["speaker"]).lower()
        role = "assistant" if speaker in ("assistant", "coach") else "user"
        history.append({"role": role, "content": str(r["raw_utterance"])})
    return history


async def store_patient_fact(
    conn_or_pool: Any,
    patient_id: str,
    category: str,
    fact_key: str,
    fact_value: str,
    epistemic_status: str = "active",
) -> None:
    """Store or supersede a structured long-term patient fact in PostgreSQL."""
    if conn_or_pool is None:
        return
    with suppress(Exception):
        if hasattr(conn_or_pool, "acquire"):
            async with conn_or_pool.acquire() as conn:
                await _store_fact_on_conn(conn, patient_id, category, fact_key, fact_value, epistemic_status)
        else:
            await _store_fact_on_conn(conn_or_pool, patient_id, category, fact_key, fact_value, epistemic_status)


async def _store_fact_on_conn(
    conn: Any,
    patient_id: str,
    category: str,
    fact_key: str,
    fact_value: str,
    epistemic_status: str,
) -> None:
    await conn.execute(
        """UPDATE patient_temporal_facts SET epistemic_status = 'superseded', valid_to = NOW()
           WHERE patient_id = $1 AND fact_key = $2 AND epistemic_status = 'active'""",
        patient_id, fact_key,
    )
    await conn.execute(
        """INSERT INTO patient_temporal_facts (patient_id, category, fact_key, fact_value, epistemic_status)
           VALUES ($1, $2, $3, $4, $5)""",
        patient_id, category, fact_key, fact_value, epistemic_status,
    )


async def load_patient_facts(conn_or_pool: Any, patient_id: str) -> list[dict[str, Any]]:
    """Retrieve all active patient lifestyle and health facts from PostgreSQL."""
    if conn_or_pool is None:
        return []
    facts: list[dict[str, Any]] = []
    with suppress(Exception):
        if hasattr(conn_or_pool, "acquire"):
            async with conn_or_pool.acquire() as conn:
                facts = await _load_facts_on_conn(conn, patient_id)
        else:
            facts = await _load_facts_on_conn(conn_or_pool, patient_id)
    return facts


async def _load_facts_on_conn(conn: Any, patient_id: str) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """SELECT category, fact_key, fact_value FROM patient_temporal_facts
           WHERE patient_id = $1 AND epistemic_status = 'active'
           ORDER BY created_at ASC""",
        patient_id,
    )
    return [dict(r) for r in rows]


async def persist_patient_disclosure(conn_or_pool: Any, patient_id: str, text: str) -> None:
    """Analyze user utterance for lifestyle, shift, or diet disclosures and persist them."""
    if not text or not patient_id:
        return
    text_lower = text.lower()

    # 1. Shift work / circadian disclosures
    if any(k in text_lower for k in ("night shift", "raat ki shift", "night duty", "rotational shift", "shift worker")):
        await store_patient_fact(
            conn_or_pool, patient_id,
            category="lifestyle",
            fact_key="shift_schedule",
            fact_value="Night shift (works at night, sleeps during daytime)",
        )

    # 2. Food dislikes / exclusions
    dislike_patterns = [
        r"\b(?:don['’]?t\s+like|dislike|hate|cannot\s+eat|avoid)\s+([a-zA-Z\s]{3,25})",
        r"([a-zA-Z\s]{3,25})\s+(?:pasand\s+nahi|acha\s+nahi\s+lagta|nahi\s+kha\s*ta|nahi\s+kha\s*ti)",
        r"\ballergic\s+to\s+([a-zA-Z\s]{3,25})",
    ]
    for pat in dislike_patterns:
        match = re.search(pat, text_lower)
        if match:
            raw_item = match.group(1).strip()
            clean_item = " ".join([w for w in raw_item.split() if w not in STOP_WORDS])
            if clean_item and len(clean_item) > 2:
                key = f"food_dislike_{clean_item.replace(' ', '_')}"
                await store_patient_fact(
                    conn_or_pool, patient_id,
                    category="dietary_preference",
                    fact_key=key,
                    fact_value=f"Dislikes/avoids {clean_item}",
                )

    # 3. Musculoskeletal / Joint complaints
    if any(k in text_lower for k in ("knee pain", "ghutno ka dard", "ghutne me dard", "joint pain", "knee surgery", "arthritis")):
        await store_patient_fact(
            conn_or_pool, patient_id,
            category="medical_history",
            fact_key="joint_condition",
            fact_value="Knee pain / joint stiffness reported",
        )

    # 4. Chronic health conditions
    if any(k in text_lower for k in ("high bp", "hypertension", "bp high rehta", "heart patient", "cardiac")):
        await store_patient_fact(
            conn_or_pool, patient_id,
            category="medical_history",
            fact_key="chronic_diagnosis",
            fact_value="Hypertension / Cardiovascular risk",
        )


async def generate_turn_sentences(
    request: Any,
    patient_id: str,
    payload: TurnRequest,
    state: TurnState,
) -> AsyncIterator[str]:
    """Execute pipeline routing, retrieval, LLM streaming, and clinical sentence validation."""
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

    if emergency.triggered:
        state.breaker_status = f"triggered:{emergency.category}"
        yield emergency.response or "Yeh emergency ho sakti hai. Abhi 112 par call karein."
        return

    day = app_state.today_ist()
    normalized = normalize(payload.text)

    # Context building
    pool = getattr(app_state, "pool", None)
    if pool is not None:
        async with pool.acquire() as connection:
            context = await build_patient_context(
                connection, patient_id, day, payload.meal_type,
                user_input=payload.text, intent=intent.value if intent else None,
            )
    else:
        # Fallback for mock environments without database connection pool
        context = await build_patient_context(
            None, patient_id, day, payload.meal_type,
            user_input=payload.text, intent=intent.value if intent else None,
        )

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

    if intent == Intent.MEAL_QUERY and context["diet_status"] == "NOT_FOUND":
        state.validator_status = "rewritten:meal_not_found"
        yield MEAL_NOT_FOUND_REPLACEMENT
        return

    # Early PEP Risk Triage via Laya System 1:
    pep = context.get("pep") or {}
    restricted = {str(item).replace("_", " ").casefold() for item in pep.get("restricted_modalities") or ()}
    has_cardiac_htn = bool(pep.get("hypertension_stage")) or not pep.get("gym_clearance", True)
    if pep_risk >= 2 and (restricted or has_cardiac_htn):
        state.validator_status = "rewritten:pep_restriction"
        yield PEP_REPLACEMENT
        return

    # Retrieval Routing:
    # If Laya classifies intent as pure greeting, general coaching, or app meta,
    # SKIP pgvector database retrieval, saving DB connection latency & context window.
    chunks = ()
    if pool is not None and not skip_retrieval and intent not in {Intent.GENERAL_COACHING, Intent.APP_META, Intent.GREETING}:
        target_tags = list(normalized.tags)
        if intent == Intent.SYMPTOM_COMPLAINT and not target_tags:
            target_tags = ["GI_BLOATING"]
        elif intent == Intent.MEAL_QUERY and not target_tags:
            target_tags = ["FRUIT_MODERATION"]
        elif intent == Intent.EXERCISE_QUERY and not target_tags:
            target_tags = ["EXERCISE_GUIDELINES"]
        async with pool.acquire() as connection:
            chunks = await retrieve_chunks(
                connection, normalized.normalized, patient_id=patient_id, tags=target_tags
            )

    # In-memory history synchronization with DB journal
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

    add_approved_remedy_constraints(context, chunks)
    prompt = render_user_payload(normalized.normalized, context, chunks)
    emitted = False
    generated_sentences: list[str] = []

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
        logger.exception("Chat generation stream failed: %s", exc)
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

            # Persist turn and patient disclosures asynchronously to PostgreSQL
            if pool is not None:
                with suppress(Exception):
                    async with pool.acquire() as save_conn:
                        await store_conversation_turn(save_conn, patient_id, payload.text, full_reply)
                        await persist_patient_disclosure(save_conn, patient_id, payload.text)
