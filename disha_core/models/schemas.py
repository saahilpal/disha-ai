"""Strict Pydantic v2 schemas for Disha AI Core request/response validation.

Enforces boundary integrity, payload size bounds, and deterministic normalization.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


@dataclass
class TurnState:
    """State tracking for a conversational turn across breaker and validator."""
    breaker_status: str = "clear"
    validator_status: str = "accepted"


class TurnRequest(BaseModel):
    """Chat/conversation turn input payload."""
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=5000, description="Patient utterance or query")
    meal_type: Literal["breakfast", "lunch", "dinner"] | None = Field(
        default=None,
        description="Optional meal window (only set if relevant to meals/nutrition)"
    )

    @model_validator(mode="before")
    @classmethod
    def infer_meal_type(cls, data: Any) -> Any:
        if isinstance(data, dict):
            text = str(data.get("text", "")).casefold()
            if "meal_type" not in data or data.get("meal_type") is None:
                if any(w in text for w in ("breakfast", "nashta", "naashta", "subah")):
                    data["meal_type"] = "breakfast"
                elif any(w in text for w in ("lunch", "dopahar", "dopehar")):
                    data["meal_type"] = "lunch"
                elif any(w in text for w in ("dinner", "raat", "shaam")):
                    data["meal_type"] = "dinner"
                else:
                    data["meal_type"] = None
        return data

    @model_validator(mode="after")
    def validate_text_not_blank(self) -> TurnRequest:
        if not self.text.strip():
            raise ValueError("text must not be empty or whitespace only")
        return self


class LoginRequest(BaseModel):
    """Patient login credentials payload."""
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255, description="Patient registered email")
    password: str = Field(min_length=1, max_length=255, description="Plaintext password for verification")


class OnboardingRequest(BaseModel):
    """Patient registration and clinical profile onboarding payload."""
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=128, description="Patient full name")
    email: str = Field(min_length=3, max_length=255, description="Unique account email")
    password: str = Field(min_length=6, max_length=255, description="Account password (min 6 chars)")
    age: int = Field(default=35, ge=1, le=120, description="Age in years")
    gender: str = Field(default="male", description="Gender identity")
    height_cm: float = Field(default=170.0, ge=50, le=260, description="Height in centimeters")
    weight_kg: float = Field(default=70.0, ge=20, le=300, description="Weight in kilograms")
    conditions: list[str] = Field(default_factory=list, description="Self-reported clinical conditions")
    hypertension_stage: str = Field(default="normal", description="Hypertension grade or stage")
    gym_clearance: bool = Field(default=False, description="Clinician clearance for gym exertion")
    activity_level: str = Field(default="light", description="Baseline activity level")
    movement_restrictions: list[str] = Field(default_factory=list, description="Physical movement limitations")
    dietary_preference: str = Field(default="Vegetarian", description="Dietary pattern")
    health_goals: list[str] = Field(default_factory=list, description="Primary health coaching objectives")


class HealthResponse(BaseModel):
    """Database and health status response."""
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    database: bool = True


class ReadyResponse(BaseModel):
    """Readiness probe status."""
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    database: bool = True
    classifier: bool = True
    schema_version: str = "2026-11-07.v1"


class PEPDetails(BaseModel):
    """Personalized Exercise Prescription details."""
    model_config = ConfigDict(extra="ignore")

    hypertension_stage: str = "normal"
    gym_clearance: bool = False
    allowed_modalities: list[str] = Field(default_factory=list)
    restricted_modalities: list[str] = Field(default_factory=list)


class AuthResponse(BaseModel):
    """Authentication token response."""
    model_config = ConfigDict(extra="ignore")

    token: str
    patient_id: str
    patient_name: str
    status: str = "authenticated"
    pep: PEPDetails | dict[str, Any] | None = None


class PatientProfileResponse(BaseModel):
    """Full patient profile, exercise prescription, and current diet."""
    model_config = ConfigDict(extra="ignore")

    patient_id: str
    patient_name: str
    day: str
    profile: dict[str, Any] | None = None
    pep: dict[str, Any] = Field(default_factory=dict)
    today_diet: dict[str, str] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """Standard conversational turn response."""
    model_config = ConfigDict(extra="forbid")

    response: str
    status: str


class ClientErrorPayload(BaseModel):
    """Client error reporting payload."""
    model_config = ConfigDict(extra="ignore")

    message: str = "unknown"
    source: str = "browser"


class ClientErrorResponse(BaseModel):
    """Client error ack response."""
    model_config = ConfigDict(extra="forbid")

    logged: bool = True


class ProfileUpdateRequest(BaseModel):
    """Payload for updating patient personal and health details."""
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    age: int | None = Field(default=None, ge=1, le=120)
    gender: str | None = None
    height_cm: float | None = Field(default=None, ge=40.0, le=280.0)
    weight_kg: float | None = Field(default=None, ge=10.0, le=400.0)
    dietary_preference: str | None = None
    health_goals: list[str] | None = None
    health_conditions: list[str] | None = None
