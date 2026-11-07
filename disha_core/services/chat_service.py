"""Chat orchestration and turn processing service for Disha AI Core."""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from disha_core.compliance.ledger import AuditLedger, AuditRecord
from disha_core.engine.context_builder import (
    add_approved_remedy_constraints,
    build_patient_context,
    render_user_payload,
)
from disha_core.engine.normalizer import normalize
from disha_core.engine.retriever import retrieve_chunks
from disha_core.llm.sentence_buffer import validated_sentences
from disha_core.models.schemas import TurnRequest, TurnState
from disha_core.pipeline.router import Intent
from disha_core.pipeline.validator import (
    CHANNEL_RE,
    CHANNEL_REPLACEMENT,
    MEAL_NOT_FOUND_REPLACEMENT,
)

logger = logging.getLogger("disha_core.main")


def enqueue_audit(ledger: AuditLedger | None, record: AuditRecord) -> None:
    """Safely enqueue an audit record into the background durability ledger.

    Logs a zero-PHI warning if the buffer has overflowed.
    """
    if ledger is not None and not ledger.enqueue(record):
        logger.warning("Audit queue overflow; event not recorded")


async def generate_turn_sentences(
    request: Any,
    patient_id: str,
    payload: TurnRequest,
    state: TurnState,
) -> AsyncIterator[str]:
    """Execute pipeline routing, retrieval, LLM streaming, and clinical sentence validation."""
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
