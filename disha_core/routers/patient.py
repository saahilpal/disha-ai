"""Patient profile retrieval endpoint."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Request

from disha_core.services.patient_service import fetch_patient_profile

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
