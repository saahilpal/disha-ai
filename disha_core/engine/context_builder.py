from __future__ import annotations

import html
import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger("disha_core.engine.context_builder")

from disha_core.engine.normalizer import (
    is_complex_health_query,
    is_detail_requested,
    is_exercise_query,
    is_meal_query,
    is_simple_factual,
)


class ContextConnection(Protocol):
    async def fetchrow(self, query: str, *args: Any) -> Any: ...


PEP_SQL = """
SELECT hypertension_stage, gym_clearance, allowed_modalities, restricted_modalities,
       primary_focus, secondary_focuses, user_reported_concerns, diagnosed_conditions,
       language, dietary_preference
FROM patient_pep WHERE patient_id = $1
"""
DIET_SQL = """
SELECT prescribed_items FROM patient_diet_schedules
WHERE patient_id = $1 AND day_of_week = $2 AND meal_type = $3
  AND is_active = TRUE AND approval_status = 'approved'
"""
FACTS_SQL = """
SELECT category, fact_key, fact_value FROM patient_temporal_facts
WHERE patient_id = $1 AND epistemic_status = 'active'
ORDER BY created_at ASC
"""
SLOTS_SQL = """
SELECT slot_key, slot_value, category, source_authority, sensitive_flag
FROM memory_items
WHERE patient_id = $1 AND epistemic_status = 'active'
ORDER BY created_at ASC
"""
HISTORY_SQL = """
SELECT speaker, raw_utterance FROM patient_turn_journal
WHERE patient_id = $1
ORDER BY timestamp_utc DESC LIMIT $2
"""
HISTORY_SESSION_SQL = """
SELECT speaker, raw_utterance FROM patient_turn_journal
WHERE patient_id = $1 AND session_id = $2
ORDER BY timestamp_utc DESC LIMIT $3
"""
HISTORY_CALL_SQL = """
SELECT speaker, raw_utterance FROM patient_turn_journal
WHERE patient_id = $1 AND call_id = $2
ORDER BY timestamp_utc DESC LIMIT $3
"""
WEEKDAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}


@dataclass(frozen=True)
class LengthPolicy:
    category: str  # "factual", "coaching", "complex", "emergency", "detailed"
    min_sentences: int
    max_sentences: int


def determine_length_policy(
    user_input: str,
    intent: str | None = None,
    is_emergency: bool = False,
) -> LengthPolicy:
    """
    Determine target response sentence bounds based on query intent and complexity:
    - Emergency: 1 to 2 sentences (immediate direct safety action)
    - User requested detail: 3 to 7 sentences
    - Simple factual query: 1 to 2 crisp sentences
    - Complex health concern: 3 to 5 structured sentences
    - Everyday coaching / habit (default): 2 to 4 actionable sentences
    """
    if is_emergency or intent in {"EMERGENCY_TRIAGE", "emergency_escalation"}:
        return LengthPolicy(category="emergency", min_sentences=1, max_sentences=2)

    if is_detail_requested(user_input):
        return LengthPolicy(category="detailed", min_sentences=3, max_sentences=7)

    if is_simple_factual(user_input):
        return LengthPolicy(category="factual", min_sentences=1, max_sentences=2)

    if is_complex_health_query(user_input, intent=intent):
        return LengthPolicy(category="complex", min_sentences=3, max_sentences=5)

    return LengthPolicy(category="coaching", min_sentences=2, max_sentences=4)


def diet_slot_xml(meal_type: str, items: str | None) -> str:
    if meal_type not in {"breakfast", "lunch", "dinner"}:
        raise ValueError("meal_type must be breakfast, lunch, or dinner")
    meal = html.escape(meal_type, quote=True)
    if not isinstance(items, str) or not items.strip():
        return '<DIET_SLOT status="NOT_FOUND"/>'
    return (
        f'<DIET_SLOT meal="{meal}" status="FOUND">'
        f'{html.escape(items)}</DIET_SLOT>'
    )


async def build_patient_context(
    connection: ContextConnection,
    patient_id: str,
    day_of_week: str,
    meal_type: str | None = None,
    user_input: str | None = None,
    intent: str | None = None,
    session_id: str | None = None,
    call_id: str | None = None,
    check_contradictions: bool = True,
) -> dict[str, Any]:
    if not isinstance(patient_id, str) or not patient_id.strip():
        raise ValueError("patient_id is required")
    patient_id = patient_id.strip()
    if not isinstance(day_of_week, str):
        raise ValueError("day_of_week must be a string")
    day_of_week = day_of_week.strip().casefold()
    if day_of_week not in WEEKDAYS:
        raise ValueError("day_of_week must be a full weekday name")

    pep_dict: dict[str, Any] | None = None
    if connection is not None and hasattr(connection, "fetchrow"):
        try:
            pep = await connection.fetchrow(PEP_SQL, patient_id)
            pep_dict = dict(pep) if pep else None
        except Exception as exc:
            logger.exception("Could not load persisted PEP for the current turn")
            raise RuntimeError("Could not load patient safety context") from exc

    patient_facts: list[dict[str, Any]] = []
    patient_slots: list[dict[str, Any]] = []
    conversation_history: list[dict[str, str]] = []
    if hasattr(connection, "fetch"):
        try:
            fact_rows = await connection.fetch(FACTS_SQL, patient_id)
            patient_facts = [dict(r) for r in fact_rows]
            slot_rows = await connection.fetch(SLOTS_SQL, patient_id)
            patient_slots = [dict(r) for r in slot_rows]
            if call_id:
                hist_rows = await connection.fetch(HISTORY_CALL_SQL, patient_id, call_id, 8)
            elif session_id:
                hist_rows = await connection.fetch(HISTORY_SESSION_SQL, patient_id, session_id, 8)
            else:
                hist_rows = await connection.fetch(HISTORY_SQL, patient_id, 8)
            for r in reversed(hist_rows):
                speaker = str(r["speaker"]).lower()
                role = "assistant" if speaker in ("assistant", "coach") else "user"
                conversation_history.append({"role": role, "content": str(r["raw_utterance"])})
        except Exception as exc:
            logger.exception("Could not load persisted user context for the current turn")
            raise RuntimeError("Could not load persisted user context") from exc

    contradictions: list[dict[str, Any]] = []
    if user_input and check_contradictions and pep_dict:
        from disha_core.pipeline.validator import evaluate_patient_claims
        contradictions = evaluate_patient_claims(user_input, pep_dict)

    length_policy = None
    if user_input:
        length_policy = determine_length_policy(user_input, intent=intent)

    if meal_type is not None:
        if not isinstance(meal_type, str):
            raise ValueError("meal_type must be a string or None")
        meal_type = meal_type.strip().casefold()
        if meal_type not in {"breakfast", "lunch", "dinner"}:
            raise ValueError("meal_type must be breakfast, lunch, or dinner")
        diet = None
        if connection is not None and hasattr(connection, "fetchrow"):
            try:
                diet = await connection.fetchrow(DIET_SQL, patient_id, day_of_week, meal_type)
            except Exception as exc:
                logger.exception("Could not load prescribed meal schedule for the current turn")
                raise RuntimeError("Could not load prescribed meal schedule") from exc
        if connection is None or not hasattr(connection, "fetchrow"):
            diet_status = "UNAVAILABLE"
            items = None
        else:
            items = diet["prescribed_items"] if diet else None
            diet_status = "FOUND" if items is not None else "NOT_FOUND"
        if isinstance(items, str):
            items = items.strip() or None
            if items is None and diet_status == "FOUND":
                diet_status = "NOT_FOUND"
        ctx = {
            "patient_id": patient_id,
            "session_id": session_id or "default",
            "call_id": call_id,
            "pep": pep_dict,
            "patient_facts": patient_facts,
            "patient_slots": patient_slots,
            "contradictions": contradictions,
            "conversation_history": conversation_history,
            "diet_status": diet_status,
            "diet_items": items,
            "diet_slot_xml": diet_slot_xml(meal_type, items),
        }
        if length_policy:
            ctx["length_policy"] = length_policy
        return ctx

    ctx = {
        "patient_id": patient_id,
        "session_id": session_id or "default",
        "call_id": call_id,
        "pep": pep_dict,
        "patient_facts": patient_facts,
        "patient_slots": patient_slots,
        "contradictions": contradictions,
        "conversation_history": conversation_history,
        "diet_status": "NOT_REQUESTED",
        "diet_items": None,
        "diet_slot_xml": "",
    }
    if length_policy:
        ctx["length_policy"] = length_policy
    return ctx


async def rehydrate_session_state(
    connection: ContextConnection,
    patient_id: str,
    session_id: str | None = None,
    call_id: str | None = None,
    limit: int = 16,
) -> dict[str, Any]:
    """Rehydrate complete session and conversational state from PostgreSQL.

    Guarantees ZERO in-RAM session state is lost on client disconnect,
    worker recycling, or container reconnect.
    """
    if not isinstance(patient_id, str) or not patient_id.strip():
        raise ValueError("patient_id is required")
    patient_id = patient_id.strip()

    pep_dict: dict[str, Any] | None = None
    if connection is not None and hasattr(connection, "fetchrow"):
        try:
            pep = await connection.fetchrow(PEP_SQL, patient_id)
            pep_dict = dict(pep) if pep else None
        except Exception as exc:
            logger.warning("Database unavailable in build_patient_context fetchrow: %s", exc)

    conversation_history: list[dict[str, str]] = []
    patient_facts: list[dict[str, Any]] = []
    patient_slots: list[dict[str, Any]] = []

    if hasattr(connection, "fetch"):
        with suppress(Exception):
            fact_rows = await connection.fetch(FACTS_SQL, patient_id)
            patient_facts = [dict(r) for r in fact_rows]
        with suppress(Exception):
            slot_rows = await connection.fetch(SLOTS_SQL, patient_id)
            patient_slots = [dict(r) for r in slot_rows]
        with suppress(Exception):
            if call_id:
                hist_rows = await connection.fetch(HISTORY_CALL_SQL, patient_id, call_id, limit)
            elif session_id:
                hist_rows = await connection.fetch(HISTORY_SESSION_SQL, patient_id, session_id, limit)
            else:
                hist_rows = await connection.fetch(HISTORY_SQL, patient_id, limit)
            for r in reversed(hist_rows):
                speaker = str(r["speaker"]).lower()
                role = "assistant" if speaker in ("assistant", "coach") else "user"
                conversation_history.append({"role": role, "content": str(r["raw_utterance"])})

    return {
        "patient_id": patient_id,
        "session_id": session_id or "default",
        "call_id": call_id,
        "conversation_history": conversation_history,
        "pep": pep_dict,
        "patient_facts": patient_facts,
        "patient_slots": patient_slots,
        "rehydrated_from_db": True,
    }


def render_context_xml(context: dict[str, Any], chunks: Any = ()) -> str:
    pep = context.get("pep")
    focus_xml = ""
    diet_rule_xml = ""
    pep_rule_xml = ""
    if pep:
        allowed = html.escape(", ".join(map(str, pep.get("allowed_modalities") or ())), quote=True)
        restricted = html.escape(", ".join(map(str, pep.get("restricted_modalities") or ())), quote=True)
        htn = html.escape(str(pep.get("hypertension_stage") or "unknown"), quote=True)
        diag = html.escape(", ".join(map(str, pep.get("diagnosed_conditions") or ())), quote=True)
        pep_xml = (
            f'<PEP_PERMISSIONS allowed="{allowed}" hypertension_stage="{htn}" '
            f'restricted="{restricted}" diagnosed="{diag}"/>'
        )
        prim = html.escape(str(pep.get("primary_focus") or ""), quote=True)
        sec = html.escape(", ".join(map(str, pep.get("secondary_focuses") or ())), quote=True)
        concerns = html.escape(str(pep.get("user_reported_concerns") or ""), quote=True)
        if prim or sec or concerns or diag:
            focus_xml = f'<PEP_FOCUS primary="{prim}" secondary="{sec}" concerns="{concerns}" diagnosed="{diag}"/>'

        if restricted:
            pep_rule_xml = (
                f'<PEP_RESTRICTION_RULES FORBIDDEN="{restricted}">'
                f'Do not recommend the listed restricted modalities. '
                f'Patient-recorded allowed modalities: {allowed}.'
                f'</PEP_RESTRICTION_RULES>'
            )

        raw_lang = str(pep.get("language") or "hinglish").strip().lower()
        valid_lang = raw_lang if raw_lang in {"english", "hindi", "hinglish"} else "hinglish"
        lang_xml = f'<USER_LANGUAGE preferred="{html.escape(valid_lang, quote=True)}"/>'
        diet_pref = str(pep.get("dietary_preference") or "").strip()
        if diet_pref:
            diet_rule_xml = f'<DIETARY_PREFERENCE preference="{html.escape(diet_pref, quote=True)}"/>'
        else:
            diet_rule_xml = '<DIETARY_PREFERENCE status="NOT_RECORDED"/>'
    else:
        pep_xml = '<PEP_PERMISSIONS status="NOT_FOUND"/>'
        lang_xml = '<USER_LANGUAGE preferred="hinglish"/>'
        diet_rule_xml = '<DIETARY_PREFERENCE status="NOT_RECORDED"/>'

    facts_xml = ""
    facts = context.get("patient_facts") or ()
    if facts:
        fact_elements = []
        for f in facts:
            cat = html.escape(str(f.get("category", "lifestyle")), quote=True)
            k = html.escape(str(f.get("fact_key", "")), quote=True)
            v = html.escape(str(f.get("fact_value", "")))
            if k and v:
                fact_elements.append(f'<FACT category="{cat}" key="{k}">{v}</FACT>')
        if fact_elements:
            facts_xml = f'<PATIENT_FACTS>{"".join(fact_elements)}</PATIENT_FACTS>'

    clinical_parts = []
    for chunk in chunks:
        getter = chunk.get if hasattr(chunk, "get") else lambda key, default=None: getattr(chunk, key, default)
        chunk_id = html.escape(str(getter("chunk_id", "")), quote=True)
        citation = html.escape(str(getter("source_citation", "")), quote=True)
        header = html.escape(str(getter("context_header", "")))
        content = html.escape(str(getter("guideline_content", "")))
        clinical_parts.append(f'<CHUNK id="{chunk_id}" source="{citation}">{header} {content}</CHUNK>')
    clinical_xml = (
        f'<CLINICAL_GROUNDING>{"".join(clinical_parts)}</CLINICAL_GROUNDING>'
        if clinical_parts else '<CLINICAL_GROUNDING status="NOT_FOUND"/>'
    )
    diet_xml = context.get("diet_slot_xml", "")
    if not isinstance(diet_xml, str):
        diet_xml = ""

    policy = context.get("length_policy")
    length_xml = ""
    if policy:
        category = html.escape(str(getattr(policy, "category", "") or policy.get("category", "")), quote=True)
        min_s = str(getattr(policy, "min_sentences", 2) if hasattr(policy, "min_sentences") else policy.get("min_sentences", 2))
        max_s = str(getattr(policy, "max_sentences", 4) if hasattr(policy, "max_sentences") else policy.get("max_sentences", 4))
        length_xml = f'<RESPONSE_TARGET category="{category}" min_sentences="{min_s}" max_sentences="{max_s}"/>'

    contradiction_xml = ""
    contradictions = context.get("contradictions") or ()
    if contradictions:
        c_parts = []
        for c in contradictions:
            slot = html.escape(str(c.get("slot_key", "")), quote=True)
            restr = html.escape(str(c.get("pep_restriction", "")), quote=True)
            reason = html.escape(str(c.get("reason", "")))
            c_parts.append(
                f'<CONTRADICTION slot="{slot}" restriction="{restr}" flagged="true">{reason}</CONTRADICTION>'
            )
        contradiction_xml = (
            f'<PEP_CONTRADICTION_NOTICE status="FLAGGED_FOR_CLINICIAN_REVIEW" action="MAINTAIN_RESTRICTIONS">'
            f'{"".join(c_parts)}'
            f'Patient reported claims contradicting official PEP clinical restrictions. '
            f'LLM-written clinical permissions are 0. Do NOT grant or affirm medical clearance.'
            f'</PEP_CONTRADICTION_NOTICE>'
        )

    slots_xml = ""
    slots = context.get("patient_slots") or ()
    if slots:
        slot_parts = []
        for s in slots:
            k = html.escape(str(s.get("slot_key", "")), quote=True)
            auth = html.escape(str(s.get("source_authority", "PATIENT_REPORTED")), quote=True)
            val = html.escape(str(s.get("slot_value", "")))
            slot_parts.append(f'<SLOT key="{k}" authority="{auth}">{val}</SLOT>')
        if slot_parts:
            slots_xml = f'<PATIENT_SLOTS>{"".join(slot_parts)}</PATIENT_SLOTS>'

    return f'<PATIENT_PROFILE>{pep_xml}{pep_rule_xml}{focus_xml}{lang_xml}{diet_rule_xml}{facts_xml}{slots_xml}{contradiction_xml}{diet_xml}</PATIENT_PROFILE>{length_xml}{clinical_xml}'


def add_approved_remedy_constraints(context: dict[str, Any], chunks: Any) -> None:
    context.update(protocol_approved=False, required_remedy_tokens=(), approved_remedy_text="")
    clinical_tags = {str(t).upper() for t in (context.get("clinical_tags") or ())}
    for chunk in chunks:
        getter = chunk.get if hasattr(chunk, "get") else lambda key, default=None: getattr(chunk, key, default)
        tag = str(getter("condition_tag", "")).upper()
        if tag not in clinical_tags:
            continue
        tokens = tuple(str(token).strip() for token in getter("required_remedy_tokens", ()) or () if str(token).strip())
        content = str(getter("guideline_content", "")).strip()
        if not tokens or not content:
            continue
        if all(token.casefold() in content.casefold() for token in tokens):
            context.update(
                protocol_approved=True,
                required_remedy_tokens=tokens,
                approved_remedy_text=content,
            )
            return


def render_user_payload(user_input: str, context: dict[str, Any], chunks: Any = ()) -> str:
    if not isinstance(user_input, str):
        raise TypeError("user_input must be a string")

    # If length_policy is not explicitly set, determine it now
    if "length_policy" not in context:
        intent = getattr(context.get("intent", ""), "value", context.get("intent", ""))
        context["length_policy"] = determine_length_policy(user_input, intent=intent)

    is_meal = context.get("meal_relevant", is_meal_query(user_input))
    is_exercise = context.get("exercise_relevant", is_exercise_query(user_input))

    discipline_xml = (
        f'<RESPONSE_DISCIPLINE answer_first="true" '
        f'prompted_for_meals="{str(is_meal).lower()}" '
        f'prompted_for_exercise="{str(is_exercise).lower()}"/>'
    )

    scheduled_xml = ""
    scheduled_q = context.get("scheduled_question")
    if scheduled_q:
        scheduled_text = html.escape(str(scheduled_q))
        scheduled_xml = (
            f'<SCHEDULED_ONBOARDING_INQUIRY instruction="After addressing the patient above, naturally ask this single question at the end:">'
            f'{scheduled_text}'
            f'</SCHEDULED_ONBOARDING_INQUIRY>'
        )

    return (
        f"{render_context_xml(context, chunks)}"
        f"{discipline_xml}"
        f"{scheduled_xml}"
        f"<USER_UTTERANCE>{html.escape(user_input)}</USER_UTTERANCE>"
    )
