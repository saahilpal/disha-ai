"""Health and readiness probing endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from disha_core.models.schemas import HealthResponse, ReadyResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> dict[str, bool]:
    """Liveness probe verifying database connectivity."""
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"ok": True, "database": True}


@router.get("/ready", response_model=ReadyResponse)
async def ready(request: Request) -> dict[str, Any]:
    """Readiness probe checking database and Laya classifier status."""
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database pool not initialized")
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database connectivity failure") from exc

    classifier = getattr(request.app.state, "classifier_adapter", None)
    is_classifier_ready = await classifier.is_ready() if classifier is not None else False
    if not is_classifier_ready:
        raise HTTPException(status_code=503, detail="Laya classifier not ready")

    return {
        "ok": True,
        "database": True,
        "classifier": True,
        "schema_version": "2026-11-07.v1",
    }
