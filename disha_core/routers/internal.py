"""Internal diagnostic and telemetry endpoints."""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

router = APIRouter(tags=["Internal"])


@router.get("/internal/classifier")
async def classifier_status(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Retrieve operational metrics and runtime model status for Laya classifier."""
    admin_key = os.getenv("ADMIN_API_KEY", "")
    if admin_key:
        token = (authorization or "").removeprefix("Bearer ").strip()
        if token != admin_key:
            raise HTTPException(status_code=403, detail="Admin authorization required")

    classifier = getattr(request.app.state, "classifier_adapter", None)
    if classifier is None:
        raise HTTPException(status_code=503, detail="Classifier adapter not initialized")
    return classifier.get_status()


@router.post("/client-errors")
async def log_client_error(payload: dict[str, Any], request: Request) -> dict[str, bool]:
    """Ingest frontend error telemetry without PHI."""
    err_msg = str(payload.get("message", "unknown"))[:200]
    err_source = str(payload.get("source", "browser"))[:100]
    logging.getLogger("disha.client").warning("[Client Error] source=%s msg=%s", err_source, err_msg)
    return {"logged": True}
