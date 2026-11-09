"""Chat orchestration, multi-turn persistent memory, and turn processing service for Disha AI Core."""

from __future__ import annotations

import json
import logging
import re
from contextlib import suppress
from typing import Any, AsyncIterator

from disha_core.compliance.ledger import AuditLedger, AuditRecord
from disha_core.engine.normalizer import is_unsupported_language
from disha_core.engine.retriever import STOP_WORDS
from disha_core.models.schemas import TurnRequest, TurnState

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
    call_id: str | None = None,
) -> None:
    """Persist a completed conversational turn into the immutable patient turn journal."""
    if conn_or_pool is None:
        return
    with suppress(Exception):
        if hasattr(conn_or_pool, "acquire") and callable(conn_or_pool.acquire):
            acq = conn_or_pool.acquire()
            if hasattr(acq, "__aenter__"):
                async with acq as conn:
                    await _store_turn_on_conn(conn, patient_id, user_text, assistant_text, session_id, call_id)
            elif hasattr(acq, "__await__"):
                conn = await acq
                await _store_turn_on_conn(conn, patient_id, user_text, assistant_text, session_id, call_id)
            else:
                await _store_turn_on_conn(conn_or_pool, patient_id, user_text, assistant_text, session_id, call_id)
        else:
            await _store_turn_on_conn(conn_or_pool, patient_id, user_text, assistant_text, session_id, call_id)


async def _store_turn_on_conn(
    conn: Any,
    patient_id: str,
    user_text: str,
    assistant_text: str,
    session_id: str,
    call_id: str | None = None,
) -> None:
    max_idx = await conn.fetchval(
        "SELECT COALESCE(MAX(turn_index), -1) FROM patient_turn_journal WHERE patient_id = $1 AND session_id = $2",
        patient_id,
        session_id,
    )
    turn_idx = int(max_idx if max_idx is not None else -1) + 1
    if call_id is not None:
        await conn.execute(
            """INSERT INTO patient_turn_journal (patient_id, session_id, turn_index, speaker, raw_utterance, call_id)
               VALUES ($1, $2, $3, 'user', $4, $5)""",
            patient_id,
            session_id,
            turn_idx,
            user_text,
            call_id,
        )
    else:
        await conn.execute(
            """INSERT INTO patient_turn_journal (patient_id, session_id, turn_index, speaker, raw_utterance)
               VALUES ($1, $2, $3, 'user', $4)""",
            patient_id,
            session_id,
            turn_idx,
            user_text,
        )
    if assistant_text:
        if call_id is not None:
            await conn.execute(
                """INSERT INTO patient_turn_journal (patient_id, session_id, turn_index, speaker, raw_utterance, call_id)
                   VALUES ($1, $2, $3, 'assistant', $4, $5)""",
                patient_id,
                session_id,
                turn_idx + 1,
                assistant_text,
                call_id,
            )
        else:
            await conn.execute(
                """INSERT INTO patient_turn_journal (patient_id, session_id, turn_index, speaker, raw_utterance)
                   VALUES ($1, $2, $3, 'assistant', $4)""",
                patient_id,
                session_id,
                turn_idx + 1,
                assistant_text,
            )


async def load_conversation_history(
    conn_or_pool: Any,
    patient_id: str,
    limit: int = 8,
    session_id: str | None = None,
    call_id: str | None = None,
) -> list[dict[str, str]]:
    """Retrieve recent conversation history (last N messages) chronologically from PostgreSQL."""
    if conn_or_pool is None:
        return []
    history: list[dict[str, str]] = []
    with suppress(Exception):
        if hasattr(conn_or_pool, "acquire"):
            async with conn_or_pool.acquire() as conn:
                history = await _load_history_on_conn(conn, patient_id, limit, session_id, call_id)
        else:
            history = await _load_history_on_conn(conn_or_pool, patient_id, limit, session_id, call_id)
    return history


async def _load_history_on_conn(
    conn: Any,
    patient_id: str,
    limit: int,
    session_id: str | None = None,
    call_id: str | None = None,
) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    if call_id:
        rows = await conn.fetch(
            """SELECT speaker, raw_utterance FROM patient_turn_journal
               WHERE patient_id = $1 AND call_id = $2
               ORDER BY timestamp_utc DESC LIMIT $3""",
            patient_id,
            call_id,
            limit,
        )
    elif session_id:
        rows = await conn.fetch(
            """SELECT speaker, raw_utterance FROM patient_turn_journal
               WHERE patient_id = $1 AND session_id = $2
               ORDER BY timestamp_utc DESC LIMIT $3""",
            patient_id,
            session_id,
            limit,
        )
    else:
        rows = await conn.fetch(
            """SELECT speaker, raw_utterance FROM patient_turn_journal
               WHERE patient_id = $1
               ORDER BY timestamp_utc DESC LIMIT $2""",
            patient_id,
            limit,
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
        patient_id,
        fact_key,
    )
    await conn.execute(
        """INSERT INTO patient_temporal_facts (patient_id, category, fact_key, fact_value, epistemic_status)
           VALUES ($1, $2, $3, $4, $5)""",
        patient_id,
        category,
        fact_key,
        fact_value,
        epistemic_status,
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


async def validate_evidence_quote_in_journal(
    conn_or_pool: Any,
    patient_id: str,
    raw_quote: str,
) -> bool:
    """Validator checking that an asserted evidence quote actually exists in patient_turn_journal."""
    if not raw_quote or not patient_id:
        return True
    q = raw_quote.strip()
    if not q:
        return True
    try:
        if hasattr(conn_or_pool, "acquire"):
            async with conn_or_pool.acquire() as conn:
                res = await conn.fetchval(
                    "SELECT 1 FROM patient_turn_journal WHERE patient_id = $1 AND (raw_utterance ILIKE $2 OR $3 ILIKE '%' || raw_utterance || '%') LIMIT 1",
                    patient_id,
                    f"%{q[:80]}%",
                    q,
                )
                return bool(res)
        else:
            res = await conn_or_pool.fetchval(
                "SELECT 1 FROM patient_turn_journal WHERE patient_id = $1 AND (raw_utterance ILIKE $2 OR $3 ILIKE '%' || raw_utterance || '%') LIMIT 1",
                patient_id,
                f"%{q[:80]}%",
                q,
            )
            return bool(res)
    except Exception as exc:
        logger.debug("Journal evidence quote verification error: %s", exc)
        return True


async def store_memory_item(
    conn_or_pool: Any,
    patient_id: str,
    slot_key: str,
    slot_value: Any,
    category: str = "lifestyle",
    source_authority: str = "PATIENT_REPORTED",
    epistemic_status: str = "active",
    sensitive_flag: bool = False,
    confidence: float = 1.0,
    raw_quote: str = "",
    language: str = "hinglish",
    session_id: str = "default",
    call_id: str | None = None,
) -> None:
    """Store or supersede a structured memory item in PostgreSQL memory_items."""
    if conn_or_pool is None:
        return
    val_json = json.dumps(slot_value)
    with suppress(Exception):
        if hasattr(conn_or_pool, "acquire"):
            async with conn_or_pool.acquire() as conn:
                await _store_memory_item_on_conn(
                    conn,
                    patient_id,
                    slot_key,
                    val_json,
                    category,
                    source_authority,
                    epistemic_status,
                    sensitive_flag,
                    confidence,
                    raw_quote,
                    language,
                    session_id,
                    call_id,
                )
        else:
            await _store_memory_item_on_conn(
                conn_or_pool,
                patient_id,
                slot_key,
                val_json,
                category,
                source_authority,
                epistemic_status,
                sensitive_flag,
                confidence,
                raw_quote,
                language,
                session_id,
                call_id,
            )


async def _store_memory_item_on_conn(
    conn: Any,
    patient_id: str,
    slot_key: str,
    slot_value_json: str,
    category: str,
    source_authority: str,
    epistemic_status: str,
    sensitive_flag: bool,
    confidence: float,
    raw_quote: str,
    language: str,
    session_id: str,
    call_id: str | None,
) -> None:
    if epistemic_status == "active":
        await conn.execute(
            """UPDATE memory_items SET epistemic_status = 'superseded', valid_to = NOW(), updated_at = NOW()
               WHERE patient_id = $1 AND slot_key = $2 AND epistemic_status = 'active'""",
            patient_id,
            slot_key,
        )
    await conn.execute(
        """INSERT INTO memory_items (
               patient_id, slot_key, slot_value, category, source_authority,
               epistemic_status, sensitive_flag, confidence, raw_quote, language,
               session_id, call_id
           ) VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7, $8, $9, $10, $11, $12)""",
        patient_id,
        slot_key,
        slot_value_json,
        category,
        source_authority,
        epistemic_status,
        sensitive_flag,
        confidence,
        raw_quote,
        language,
        session_id,
        call_id,
    )


async def load_memory_items(
    conn_or_pool: Any,
    patient_id: str,
    slot_key: str | None = None,
    epistemic_status: str = "active",
) -> list[dict[str, Any]]:
    """Retrieve memory items for a patient from PostgreSQL."""
    if conn_or_pool is None:
        return []
    items: list[dict[str, Any]] = []
    with suppress(Exception):
        if hasattr(conn_or_pool, "acquire"):
            async with conn_or_pool.acquire() as conn:
                items = await _load_memory_items_on_conn(conn, patient_id, slot_key, epistemic_status)
        else:
            items = await _load_memory_items_on_conn(conn_or_pool, patient_id, slot_key, epistemic_status)
    return items


async def _load_memory_items_on_conn(
    conn: Any,
    patient_id: str,
    slot_key: str | None,
    epistemic_status: str,
) -> list[dict[str, Any]]:
    if slot_key:
        rows = await conn.fetch(
            """SELECT item_id, patient_id, slot_key, slot_value, category, source_authority,
                      epistemic_status, sensitive_flag, confidence, raw_quote, language, session_id, call_id, created_at
               FROM memory_items
               WHERE patient_id = $1 AND slot_key = $2 AND epistemic_status = $3
               ORDER BY created_at DESC""",
            patient_id,
            slot_key,
            epistemic_status,
        )
    else:
        rows = await conn.fetch(
            """SELECT item_id, patient_id, slot_key, slot_value, category, source_authority,
                      epistemic_status, sensitive_flag, confidence, raw_quote, language, session_id, call_id, created_at
               FROM memory_items
               WHERE patient_id = $1 AND epistemic_status = $2
               ORDER BY created_at ASC""",
            patient_id,
            epistemic_status,
        )
    result = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("slot_value"), str):
            try:
                d["slot_value"] = json.loads(d["slot_value"])
            except Exception:
                pass
        result.append(d)
    return result


async def store_call_summary(
    conn_or_pool: Any,
    call_id: str,
    patient_id: str,
    session_id: str = "default",
    duration_seconds: int = 0,
    summary_text: str = "",
    action_items: list[str] | None = None,
    habits_disclosed: dict[str, Any] | None = None,
    contradictions_detected: list[dict[str, Any]] | None = None,
    sentiment: str = "neutral",
    language: str = "hinglish",
) -> None:
    """Store persistent call summary into PostgreSQL call_summaries table."""
    if conn_or_pool is None:
        return
    action_json = json.dumps(action_items or [])
    habits_json = json.dumps(habits_disclosed or {})
    contradictions_json = json.dumps(contradictions_detected or [])
    with suppress(Exception):
        if hasattr(conn_or_pool, "acquire"):
            async with conn_or_pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO call_summaries (
                           call_id, session_id, patient_id, duration_seconds,
                           summary_text, action_items, habits_disclosed,
                           contradictions_detected, sentiment, language
                       ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8::jsonb, $9, $10)
                       ON CONFLICT (call_id) DO UPDATE SET
                           summary_text = EXCLUDED.summary_text,
                           action_items = EXCLUDED.action_items,
                           habits_disclosed = EXCLUDED.habits_disclosed,
                           contradictions_detected = EXCLUDED.contradictions_detected,
                           duration_seconds = EXCLUDED.duration_seconds""",
                    call_id,
                    session_id,
                    patient_id,
                    duration_seconds,
                    summary_text,
                    action_json,
                    habits_json,
                    contradictions_json,
                    sentiment,
                    language,
                )
        else:
            await conn_or_pool.execute(
                """INSERT INTO call_summaries (
                       call_id, session_id, patient_id, duration_seconds,
                       summary_text, action_items, habits_disclosed,
                       contradictions_detected, sentiment, language
                   ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8::jsonb, $9, $10)
                   ON CONFLICT (call_id) DO UPDATE SET
                       summary_text = EXCLUDED.summary_text,
                       action_items = EXCLUDED.action_items,
                       habits_disclosed = EXCLUDED.habits_disclosed,
                       contradictions_detected = EXCLUDED.contradictions_detected,
                       duration_seconds = EXCLUDED.duration_seconds""",
                call_id,
                session_id,
                patient_id,
                duration_seconds,
                summary_text,
                action_json,
                habits_json,
                contradictions_json,
                sentiment,
                language,
            )


async def load_call_summaries(
    conn_or_pool: Any,
    patient_id: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Load recent call summaries for a patient."""
    if conn_or_pool is None:
        return []
    summaries: list[dict[str, Any]] = []
    with suppress(Exception):
        if hasattr(conn_or_pool, "acquire"):
            async with conn_or_pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT summary_id, call_id, session_id, patient_id, start_time, duration_seconds,
                              summary_text, action_items, habits_disclosed, contradictions_detected, sentiment, language
                       FROM call_summaries
                       WHERE patient_id = $1
                       ORDER BY created_at DESC LIMIT $2""",
                    patient_id,
                    limit,
                )
                summaries = [dict(r) for r in rows]
        else:
            rows = await conn_or_pool.fetch(
                """SELECT summary_id, call_id, session_id, patient_id, start_time, duration_seconds,
                          summary_text, action_items, habits_disclosed, contradictions_detected, sentiment, language
                   FROM call_summaries
                   WHERE patient_id = $1
                   ORDER BY created_at DESC LIMIT $2""",
                patient_id,
                limit,
            )
            summaries = [dict(r) for r in rows]
    return summaries


async def persist_patient_disclosure(
    conn_or_pool: Any,
    patient_id: str,
    text: str,
    session_id: str = "default",
    call_id: str | None = None,
    pep_data: dict[str, Any] | None = None,
) -> None:
    """Analyze user utterance for lifestyle, shift, habit disclosures, and canonical slots, persisting them."""
    if not text or not patient_id:
        return
    # Invariant: Never store facts or slots from unsupported languages
    if is_unsupported_language(text):
        return
    text_lower = text.lower()

    # Slot registry trilingual extraction
    try:
        from disha_core.models.slots import DEFAULT_SLOT_REGISTRY, SourceAuthority

        extracted = DEFAULT_SLOT_REGISTRY.extract_slots_from_text(text)
        for slot_key, slot_val in extracted.items():
            if slot_key == "patient_claimed_clearance":
                # Contradictory clearance claim quarantined for clinician review; NEVER grant or overwrite PEP!
                await store_memory_item(
                    conn_or_pool,
                    patient_id,
                    slot_key="physical_activity_clearance",
                    slot_value={"claimed_clearance": str(slot_val)},
                    source_authority=SourceAuthority.PATIENT_REPORTED.value,
                    epistemic_status="flagged_review",
                    sensitive_flag=True,
                    raw_quote=text,
                    session_id=session_id,
                    call_id=call_id,
                )
                continue
            auth_ok, reason = DEFAULT_SLOT_REGISTRY.validate_authority(slot_key, SourceAuthority.PATIENT_REPORTED)
            contradiction = DEFAULT_SLOT_REGISTRY.check_pep_contradiction(slot_key, slot_val, pep_data)

            if not auth_ok or contradiction.is_contradiction:
                # Contradiction flagged for clinician review; NEVER silently overwrite PEP!
                await store_memory_item(
                    conn_or_pool,
                    patient_id,
                    slot_key=slot_key,
                    slot_value=slot_val,
                    source_authority=SourceAuthority.PATIENT_REPORTED.value,
                    epistemic_status="flagged_review",
                    sensitive_flag=True,
                    raw_quote=text,
                    session_id=session_id,
                    call_id=call_id,
                )
            else:
                await store_memory_item(
                    conn_or_pool,
                    patient_id,
                    slot_key=slot_key,
                    slot_value=slot_val,
                    source_authority=SourceAuthority.PATIENT_REPORTED.value,
                    epistemic_status="active",
                    sensitive_flag=False,
                    raw_quote=text,
                    session_id=session_id,
                    call_id=call_id,
                )
                # Commit low-risk habits to PEP with user_reported provenance
                low_risk_slots = {
                    "wake_time",
                    "sleep_time",
                    "water_intake_target",
                    "daily_steps_target",
                    "tea_coffee_frequency",
                    "meal_preferences",
                    "dietary_restrictions",
                    "work_schedule",
                }
                if slot_key in low_risk_slots:
                    with suppress(Exception):
                        from disha_core.pep.habits_engine import commit_habit_slot

                        if hasattr(conn_or_pool, "acquire"):
                            async with conn_or_pool.acquire() as h_conn:
                                await commit_habit_slot(
                                    patient_id=patient_id,
                                    slot_key=slot_key,
                                    raw_value=slot_val,
                                    raw_text=text,
                                    source="user_reported",
                                    evidence_ref=f"chat:{session_id}",
                                    conn=h_conn,
                                )
                        else:
                            await commit_habit_slot(
                                patient_id=patient_id,
                                slot_key=slot_key,
                                raw_value=slot_val,
                                raw_text=text,
                                source="user_reported",
                                evidence_ref=f"chat:{session_id}",
                                conn=conn_or_pool,
                            )
    except Exception as exc:
        logger.debug("Slot extraction non-blocking error: %s", exc)

    # 1. Shift work / circadian disclosures
    if any(k in text_lower for k in ("night shift", "raat ki shift", "night duty", "rotational shift", "shift worker")):
        await store_patient_fact(
            conn_or_pool,
            patient_id,
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
                    conn_or_pool,
                    patient_id,
                    category="dietary_preference",
                    fact_key=key,
                    fact_value=f"Dislikes/avoids {clean_item}",
                )

    # 3. Musculoskeletal / Joint complaints
    if any(
        k in text_lower
        for k in ("knee pain", "ghutno ka dard", "ghutne me dard", "joint pain", "knee surgery", "arthritis")
    ):
        await store_patient_fact(
            conn_or_pool,
            patient_id,
            category="medical_history",
            fact_key="joint_condition",
            fact_value="Knee pain / joint stiffness reported",
        )

    # 4. Chronic health conditions
    if any(k in text_lower for k in ("high bp", "hypertension", "bp high rehta", "heart patient", "cardiac")):
        await store_patient_fact(
            conn_or_pool,
            patient_id,
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
    """Compatibility entry point sharing the production chat/voice turn pipeline."""
    from disha_core.main import _turn_sentences

    async for sentence in _turn_sentences(request, patient_id, payload, state):
        yield sentence
