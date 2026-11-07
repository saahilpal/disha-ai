from __future__ import annotations

import html
from typing import Any, Protocol


class ContextConnection(Protocol):
    async def fetchrow(self, query: str, *args: Any) -> Any: ...


PEP_SQL = """
SELECT hypertension_stage, gym_clearance, allowed_modalities, restricted_modalities,
       primary_focus, secondary_focuses, user_reported_concerns, diagnosed_conditions,
       language
FROM patient_pep WHERE patient_id = $1
"""
DIET_SQL = """
SELECT prescribed_items FROM patient_diet_schedules
WHERE patient_id = $1 AND day_of_week = $2 AND meal_type = $3 AND is_active = TRUE
"""
WEEKDAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}


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
    connection: ContextConnection, patient_id: str, day_of_week: str, meal_type: str | None = None
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
        return {
            "patient_id": patient_id,
            "pep": dict(pep) if pep else None,
            "diet_status": "FOUND" if items is not None else "NOT_FOUND",
            "diet_items": items,
            "diet_slot_xml": diet_slot_xml(meal_type, items),
        }

    return {
        "patient_id": patient_id,
        "pep": dict(pep) if pep else None,
        "diet_status": "NOT_REQUESTED",
        "diet_items": None,
        "diet_slot_xml": "",
    }


def render_context_xml(context: dict[str, Any], chunks: Any = ()) -> str:
    pep = context.get("pep")
    focus_xml = ""
    if pep:
        allowed = html.escape(", ".join(map(str, pep.get("allowed_modalities") or ())), quote=True)
        restricted = html.escape(", ".join(map(str, pep.get("restricted_modalities") or ())), quote=True)
        gym = str(bool(pep.get("gym_clearance"))).lower()
        pep_xml = (
            f'<PEP_PERMISSIONS allowed="{allowed}" gym_clearance="{gym}" '
            f'restricted="{restricted}"/>'
        )
        prim = html.escape(str(pep.get("primary_focus") or ""), quote=True)
        sec = html.escape(", ".join(map(str, pep.get("secondary_focuses") or ())), quote=True)
        concerns = html.escape(str(pep.get("user_reported_concerns") or ""), quote=True)
        diag = html.escape(", ".join(map(str, pep.get("diagnosed_conditions") or ())), quote=True)
        if prim or sec or concerns or diag:
            focus_xml = f'<PEP_FOCUS primary="{prim}" secondary="{sec}" concerns="{concerns}" diagnosed="{diag}"/>'
        raw_lang = str(pep.get("language") or "hinglish").strip().lower()
        valid_lang = raw_lang if raw_lang in {"english", "hindi", "hinglish"} else "hinglish"
        lang_xml = f'<USER_LANGUAGE preferred="{html.escape(valid_lang, quote=True)}"/>'
    else:
        pep_xml = '<PEP_PERMISSIONS status="NOT_FOUND"/>'
        lang_xml = '<USER_LANGUAGE preferred="hinglish"/>'
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
    return f'<PATIENT_PROFILE>{pep_xml}{focus_xml}{lang_xml}{diet_xml}</PATIENT_PROFILE>{clinical_xml}'


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
    return f"{render_context_xml(context, chunks)}<USER_UTTERANCE>{html.escape(user_input)}</USER_UTTERANCE>"
