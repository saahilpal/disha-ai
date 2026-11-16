"""Shared Interface for PEP (Patient Enablement Protocol) Updates.

Provides unified interface across:
- PEP_UPDATE_MODE=classifier: Classifier-Gated PEP Update (Agent A)
- PEP_UPDATE_MODE=summary: Summary-then-Update PEP Baseline (Agent B)
- PEP_UPDATE_MODE=off: Passthrough / Disabled baseline
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field

logger = logging.getLogger("disha_core.pep.shared_interface")


class SlotSource(str, Enum):
    ONBOARDING = "onboarding"
    CHAT_USER = "chat_user"
    CLINICIAN = "clinician"
    SYSTEM = "system"


class ClinicalStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    RESOLVED = "resolved"


class VerificationStatus(str, Enum):
    UNCONFIRMED = "unconfirmed"
    CONFIRMED = "confirmed"
    ENTERED_IN_ERROR = "entered_in_error"


class PEPSlotRecord(BaseModel):
    slot: str
    value: Any
    source: SlotSource = SlotSource.CHAT_USER
    clinical_status: ClinicalStatus = ClinicalStatus.ACTIVE
    verification_status: VerificationStatus = VerificationStatus.UNCONFIRMED
    valid_from: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valid_until: datetime | None = None
    evidence: str = ""


class SlotOperation(BaseModel):
    op: Literal["ADD", "SUPERSEDE", "NOOP"]
    slot: str
    value: Any = None
    evidence: str = ""


def get_pep_update_mode() -> str:
    """Return active PEP update mode ('classifier', 'summary', or 'off')."""
    return os.getenv("PEP_UPDATE_MODE", "off").lower().strip()


async def record_slot(
    patient_id: str,
    slot: str,
    value: Any,
    source: SlotSource | str = SlotSource.CHAT_USER,
    clinical_status: ClinicalStatus | str = ClinicalStatus.ACTIVE,
    verification_status: VerificationStatus | str = VerificationStatus.UNCONFIRMED,
    evidence: str = "",
    conn: Any = None,
) -> PEPSlotRecord:
    """Record a slot into patient_pep_slots table with deterministic provenance."""
    src_val = getattr(source, "value", str(source))
    clin_val = getattr(clinical_status, "value", str(clinical_status))
    ver_val = getattr(verification_status, "value", str(verification_status))
    val_json = json.dumps(value) if not isinstance(value, str) else json.dumps({"value": value})
    now = datetime.now(timezone.utc)

    rec = PEPSlotRecord(
        slot=slot,
        value=value,
        source=SlotSource(src_val),
        clinical_status=ClinicalStatus(clin_val),
        verification_status=VerificationStatus(ver_val),
        valid_from=now,
        evidence=evidence,
    )

    if conn is not None and hasattr(conn, "execute"):
        try:
            # Supersede existing active slot for this patient
            await conn.execute(
                """
                UPDATE patient_pep_slots
                SET valid_until = $3, updated_at = $3
                WHERE patient_id = $1 AND slot = $2 AND valid_until IS NULL
                """,
                patient_id,
                slot,
                now,
            )
            # Insert new slot row
            await conn.execute(
                """
                INSERT INTO patient_pep_slots (
                    patient_id, slot, value, source, clinical_status,
                    verification_status, valid_from, evidence, created_at, updated_at
                ) VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7, $8, $7, $7)
                """,
                patient_id,
                slot,
                val_json,
                src_val,
                clin_val,
                ver_val,
                now,
                evidence,
            )
        except Exception as exc:
            logger.warning("Could not persist slot to patient_pep_slots: %s", exc)

    return rec


async def on_turn(
    patient_id: str,
    user_text: str,
    assistant_text: str,
    session_id: str = "default",
    call_id: str | None = None,
    conn: Any = None,
    app_state: Any = None,
    turn_context: Any = None,
) -> dict[str, Any]:
    """Turn-level hook executed on every user utterance."""
    mode = get_pep_update_mode()
    if mode == "classifier":
        try:
            from disha_core.pep.classifier_gated import on_turn_classifier
            return await on_turn_classifier(
                patient_id, user_text, assistant_text, session_id, call_id, conn, app_state, turn_context
            )
        except ImportError:
            return {"mode": mode, "status": "module_not_implemented"}
    # In 'summary' or 'off' mode, turn-level extraction is skipped
    return {"mode": mode, "status": "skipped"}


async def on_session_end(
    patient_id: str,
    session_id: str = "default",
    call_id: str | None = None,
    conn: Any = None,
    app_state: Any = None,
) -> dict[str, Any]:
    """Session-end hook executed upon idle timeout or explicit session close."""
    mode = get_pep_update_mode()
    if mode == "summary":
        try:
            from disha_core.pep.summary_update import on_session_end_summary
            return await on_session_end_summary(patient_id, session_id, call_id, conn, app_state)
        except ImportError:
            return {"mode": mode, "status": "module_not_implemented"}
    return {"mode": mode, "status": "skipped"}


def context_slice(
    patient_id: str,
    intent: str | None = None,
    context: dict[str, Any] | None = None,
    app_state: Any = None,
) -> dict[str, Any]:
    """Retrieve intent-scoped context slice of PEP slots."""
    mode = get_pep_update_mode()
    if mode == "classifier":
        try:
            from disha_core.pep.classifier_gated import context_slice_classifier
            return context_slice_classifier(patient_id, intent, context, app_state)
        except ImportError:
            pass
    elif mode == "summary":
        try:
            from disha_core.pep.summary_update import context_slice_summary
            return context_slice_summary(patient_id, intent, context, app_state)
        except ImportError:
            pass
    return {"slots": {}}
