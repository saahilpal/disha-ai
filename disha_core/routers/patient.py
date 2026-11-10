"""Patient profile retrieval endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Request

from disha_core.models.schemas import ProfileUpdateRequest
from disha_core.services.patient_service import fetch_patient_profile, update_patient_profile

router = APIRouter(prefix="/patient", tags=["Patient"])


@router.get("/profile")
async def get_patient_profile(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Retrieve full patient clinical profile, exercise prescription, and today's diet."""
    import disha_core.main as app_main

    patient_id = await app_main._authenticated_patient(request, authorization)
    pool = getattr(request.app.state, "pool", None)
    day = request.app.state.today_ist()
    return await fetch_patient_profile(pool, patient_id, day)


@router.get("/journey")
async def get_patient_journey(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Retrieve persistent patient onboarding journey state."""
    import disha_core.main as app_main
    from disha_core.journey import load_or_create_journey

    patient_id = await app_main._authenticated_patient(request, authorization)
    pool = getattr(request.app.state, "pool", None)
    if not pool:
        return {"current_stage": 1, "overall_status": "in_progress", "last_completed_stage": 0}
    async with pool.acquire() as conn:
        return await load_or_create_journey(patient_id, conn)


@router.put("/profile")
async def update_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Update patient demographic details, vitals, and dietary preferences."""
    import disha_core.main as app_main

    patient_id = await app_main._authenticated_patient(request, authorization)
    pool = getattr(request.app.state, "pool", None)
    day = request.app.state.today_ist()
    updates = payload.model_dump(exclude_unset=True)
    return await update_patient_profile(pool, patient_id, updates, day)
