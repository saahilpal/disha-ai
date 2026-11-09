"""Routers package for Disha AI Core."""

from __future__ import annotations

from disha_core.routers.auth import router as auth_router
from disha_core.routers.chat import router as chat_router
from disha_core.routers.health import router as health_router
from disha_core.routers.internal import router as internal_router
from disha_core.routers.patient import router as patient_router
from disha_core.routers.voice import router as voice_router

__all__ = [
    "auth_router",
    "chat_router",
    "health_router",
    "internal_router",
    "patient_router",
    "voice_router",
]
