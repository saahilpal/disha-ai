"""Patient authentication and registration endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from disha_core.models.schemas import LoginRequest, OnboardingRequest
from disha_core.services.auth_service import login_patient, register_patient

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register")
@router.post("/onboarding")
async def register(payload: OnboardingRequest, request: Request) -> dict[str, Any]:
    """Register a new patient account with profile, PEP, and diet schedules."""
    pool = getattr(request.app.state, "pool", None)
    return await register_patient(pool, payload)


@router.post("/login")
async def login(payload: LoginRequest, request: Request) -> dict[str, Any]:
    """Authenticate patient credentials and return session token."""
    pool = getattr(request.app.state, "pool", None)
    return await login_patient(pool, payload)
