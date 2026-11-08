from __future__ import annotations

import html
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol

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
WHERE patient_id = $1 AND day_of_week = $2 AND meal_type = $3 AND is_active = TRUE
"""
FACTS_SQL = """
SELECT category, fact_key, fact_value FROM patient_temporal_facts
WHERE patient_id = $1 AND epistemic_status = 'active'
ORDER BY created_at ASC
"""
HISTORY_SQL = """
SELECT speaker, raw_utterance FROM patient_turn_journal
WHERE patient_id = $1
ORDER BY timestamp_utc DESC LIMIT $2
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
) -> dict[str, Any]:
    if not isinstance(patient_id, str) or not patient_id.strip():
        raise ValueError("patient_id is required")
    patient_id = patient_id.strip()
    if not isinstance(day_of_week, str):
        raise ValueError("day_of_week must be a string")
    day_of_week = day_of_week.strip().casefold()
    if day_of_week not in WEEKDAYS:
        raise ValueError("day_of_week must be a full weekday name")

    pep = await connection.fetchrow(PEP_SQL, patient_id)

    patient_facts: list[dict[str, Any]] = []
    conversation_history: list[dict[str, str]] = []
    if hasattr(connection, "fetch"):
        with suppress(Exception):
            fact_rows = await connection.fetch(FACTS_SQL, patient_id)
            patient_facts = [dict(r) for r in fact_rows]
        with suppress(Exception):
            hist_rows = await connection.fetch(HISTORY_SQL, patient_id, 8)
            for r in reversed(hist_rows):
                speaker = str(r["speaker"]).lower()
                role = "assistant" if speaker in ("assistant", "coach") else "user"
                conversation_history.append({"role": role, "content": str(r["raw_utterance"])})

    length_policy = None
    if user_input:
        length_policy = determine_length_policy(user_input, intent=intent)

    if meal_type is not None:
        if not isinstance(meal_type, str):
            raise ValueError("meal_type must be a string or None")
        meal_type = meal_type.strip().casefold()
        if meal_type not in {"breakfast", "lunch", "dinner"}:
            raise ValueError("meal_type must be breakfast, lunch, or dinner")
        diet = await connection.fetchrow(DIET_SQL, patient_id, day_of_week, meal_type)
        items = diet["prescribed_items"] if diet else None
        if isinstance(items, str):
            items = items.strip() or None
        ctx = {
            "patient_id": patient_id,
            "pep": dict(pep) if pep else None,
            "patient_facts": patient_facts,
            "conversation_history": conversation_history,
            "diet_status": "FOUND" if items is not None else "NOT_FOUND",
            "diet_items": items,
            "diet_slot_xml": diet_slot_xml(meal_type, items),
        }
        if length_policy:
            ctx["length_policy"] = length_policy
        return ctx

    ctx = {
        "patient_id": patient_id,
        "pep": dict(pep) if pep else None,
        "patient_facts": patient_facts,
        "conversation_history": conversation_history,
        "diet_status": "NOT_REQUESTED",
        "diet_items": None,
        "diet_slot_xml": "",
    }
    if length_policy:
        ctx["length_policy"] = length_policy
    return ctx


def render_context_xml(context: dict[str, Any], chunks: Any = ()) -> str:
    pep = context.get("pep")
    focus_xml = ""
    diet_rule_xml = ""
    pep_rule_xml = ""
    if pep:
        allowed = html.escape(", ".join(map(str, pep.get("allowed_modalities") or ())), quote=True)
        restricted = html.escape(", ".join(map(str, pep.get("restricted_modalities") or ())), quote=True)
        gym = str(bool(pep.get("gym_clearance"))).lower()
        htn = html.escape(str(pep.get("hypertension_stage") or "normal"), quote=True)
        diag = html.escape(", ".join(map(str, pep.get("diagnosed_conditions") or ())), quote=True)
        pep_xml = (
            f'<PEP_PERMISSIONS allowed="{allowed}" gym_clearance="{gym}" '
            f'hypertension_stage="{htn}" restricted="{restricted}" diagnosed="{diag}"/>'
        )
        prim = html.escape(str(pep.get("primary_focus") or ""), quote=True)
        sec = html.escape(", ".join(map(str, pep.get("secondary_focuses") or ())), quote=True)
        concerns = html.escape(str(pep.get("user_reported_concerns") or ""), quote=True)
        if prim or sec or concerns or diag:
            focus_xml = f'<PEP_FOCUS primary="{prim}" secondary="{sec}" concerns="{concerns}" diagnosed="{diag}"/>'

        # Cardiac or Stage 2 Hypertension or restricted modalities safety rule
        diag_str = " ".join(str(d) for d in (pep.get("diagnosed_conditions") or ()))
        is_cardiac = any(c in diag_str.lower() for c in ("cardiac", "heart", "cad", "angina", "coronary", "arrhythmia", "mi"))
        is_htn2 = "stage 2" in htn.lower() or "crisis" in htn.lower()
        if restricted or not pep.get("gym_clearance") or is_cardiac or is_htn2:
            extra_restrictions = []
            if is_cardiac or is_htn2:
                extra_restrictions.append("heavy weightlifting, heavy deadlifts, hiit, valsalva maneuver, high intensity sprinting")
            combined_restricted = html.escape(", ".join(filter(None, [restricted, *extra_restrictions])), quote=True)
            pep_rule_xml = (
                f'<PEP_RESTRICTION_RULES gym_clearance="{gym}" FORBIDDEN="{combined_restricted}">'
                f'Vigorous exertion, heavy weightlifting, and restricted modalities are strictly disallowed. '
                f'Only allowed safe modalities: {allowed}.'
                f'</PEP_RESTRICTION_RULES>'
            )

        raw_lang = str(pep.get("language") or "hinglish").strip().lower()
        valid_lang = raw_lang if raw_lang in {"english", "hindi", "hinglish"} else "hinglish"
        lang_xml = f'<USER_LANGUAGE preferred="{html.escape(valid_lang, quote=True)}"/>'
        diet_pref = str(pep.get("dietary_preference") or "Vegetarian").strip()
        is_veg = "veg" in diet_pref.lower() and "non" not in diet_pref.lower() and "egg" not in diet_pref.lower()
        if is_veg:
            diet_rule_xml = '<DIETARY_PREFERENCE preference="Vegetarian" FORBIDDEN="chicken, meat, poultry, fish, seafood, mutton, eggs"/>'
        else:
            diet_rule_xml = f'<DIETARY_PREFERENCE preference="{html.escape(diet_pref, quote=True)}"/>'
    else:
        pep_xml = '<PEP_PERMISSIONS status="NOT_FOUND"/>'
        lang_xml = '<USER_LANGUAGE preferred="hinglish"/>'

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
        citation = html.escape(str(getter("source_citation", "")), quote=True)
        header = html.escape(str(getter("context_header", "")))
        content = html.escape(str(getter("guideline_content", "")))
        clinical_parts.append(f'<CHUNK source="{citation}">{header} {content}</CHUNK>')
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

    return f'<PATIENT_PROFILE>{pep_xml}{pep_rule_xml}{focus_xml}{lang_xml}{diet_rule_xml}{facts_xml}{diet_xml}</PATIENT_PROFILE>{length_xml}{clinical_xml}'


def add_approved_remedy_constraints(context: dict[str, Any], chunks: Any) -> None:
    context.update(protocol_approved=False, required_remedy_tokens=(), approved_remedy_text="")
    clinical_tags = {str(t).upper() for t in (context.get("clinical_tags") or ("GI_BLOATING",))}
    for chunk in chunks:
        getter = chunk.get if hasattr(chunk, "get") else lambda key, default=None: getattr(chunk, key, default)
        tag = str(getter("condition_tag", "")).upper()
        if tag not in clinical_tags and tag != "GI_BLOATING":
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
    return (
        f"{render_context_xml(context, chunks)}"
        f"{discipline_xml}"
        f"<USER_UTTERANCE>{html.escape(user_input)}</USER_UTTERANCE>"
    )
