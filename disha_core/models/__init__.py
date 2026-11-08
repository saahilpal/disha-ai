"""Domain models and schemas for Disha AI Core."""
from __future__ import annotations

from disha_core.models.schemas import (
    AuthResponse,
    ChatResponse,
    ClientErrorPayload,
    ClientErrorResponse,
    HealthResponse,
    LoginRequest,
    OnboardingRequest,
    PatientProfileResponse,
    ReadyResponse,
    TurnRequest,
    TurnState,
)
from disha_core.models.slots import (
    CANONICAL_SLOTS,
    DEFAULT_SLOT_REGISTRY,
    ContradictionResult,
    EpistemicStatus,
    SlotDefinition,
    SlotRegistry,
    SourceAuthority,
)

__all__ = [
    "AuthResponse",
    "CANONICAL_SLOTS",
    "ChatResponse",
    "ClientErrorPayload",
    "ClientErrorResponse",
    "ContradictionResult",
    "DEFAULT_SLOT_REGISTRY",
    "EpistemicStatus",
    "HealthResponse",
    "LoginRequest",
    "OnboardingRequest",
    "PatientProfileResponse",
    "ReadyResponse",
    "SlotDefinition",
    "SlotRegistry",
    "SourceAuthority",
    "TurnRequest",
    "TurnState",
]
