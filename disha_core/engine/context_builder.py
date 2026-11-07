from __future__ import annotations

import html
from typing import Any, Protocol


class ContextConnection(Protocol):
    async def fetchrow(self, query: str, *args: Any) -> Any: ...


PEP_SQL = """
SELECT hypertension_stage, gym_clearance, allowed_modalities, restricted_modalities
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
    connection: ContextConnection, patient_id: str, day_of_week: str, meal_type: str
) -> dict[str, Any]:
    if not isinstance(patient_id, str) or not patient_id.strip():
        raise ValueError("patient_id is required")
    patient_id = patient_id.strip()
    if not isinstance(day_of_week, str) or not isinstance(meal_type, str):
        raise ValueError("day_of_week and meal_type must be strings")
    day_of_week = day_of_week.strip().casefold()
    meal_type = meal_type.strip().casefold()
    if day_of_week not in WEEKDAYS:
        raise ValueError("day_of_week must be a full weekday name")
    if meal_type not in {"breakfast", "lunch", "dinner"}:
        raise ValueError("meal_type must be breakfast, lunch, or dinner")
    pep = await connection.fetchrow(PEP_SQL, patient_id)
    diet = await connection.fetchrow(DIET_SQL, patient_id, day_of_week.casefold(), meal_type)
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


def render_context_xml(context: dict[str, Any], chunks: Any = ()) -> str:
    pep = context.get("pep")
    if pep:
        allowed = html.escape(", ".join(map(str, pep.get("allowed_modalities") or ())), quote=True)
        restricted = html.escape(", ".join(map(str, pep.get("restricted_modalities") or ())), quote=True)
        gym = str(bool(pep.get("gym_clearance"))).lower()
        pep_xml = (
            f'<PEP_PERMISSIONS allowed="{allowed}" gym_clearance="{gym}" '
            f'restricted="{restricted}"/>'
        )
    else:
        pep_xml = '<PEP_PERMISSIONS status="NOT_FOUND"/>'
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
    diet_xml = context.get("diet_slot_xml") or diet_slot_xml(
        context.get("meal_type", "dinner"), context.get("diet_items")
    )
    return f'<PATIENT_PROFILE>{pep_xml}{diet_xml}</PATIENT_PROFILE>{clinical_xml}'


def add_approved_remedy_constraints(context: dict[str, Any], chunks: Any) -> None:
    context.update(protocol_approved=False, required_remedy_tokens=(), approved_remedy_text="")
    for chunk in chunks:
        getter = chunk.get if hasattr(chunk, "get") else lambda key, default=None: getattr(chunk, key, default)
        if str(getter("condition_tag", "")).upper() != "GI_BLOATING":
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
