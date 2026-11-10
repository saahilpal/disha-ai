"""Strict Pydantic v2 schemas for Disha AI Core request/response validation.

Enforces boundary integrity, payload size bounds, and deterministic normalization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


@dataclass
class TurnState:
    """State tracking for a conversational turn across breaker and validator."""

    breaker_status: str = "clear"
    validator_status: str = "accepted"
    retrieval_status: str = "not_requested"
    evidence_ids: list[str] = field(default_factory=list)


class TurnRequest(BaseModel):
    """Chat/conversation turn input payload."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=5000, description="Patient utterance or query")
    client_msg_id: str | None = Field(default=None, description="Client idempotency message ID")
    conversation_id: str | None = Field(default=None, description="Active conversation UUID")
    meal_type: Literal["breakfast", "lunch", "dinner"] | None = Field(
        default=None, description="Optional meal window (only set if relevant to meals/nutrition)"
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
                elif any(w in text for w in ("dinner", "raat", "khana", "khaane", "raat ka khana")):
                    data["meal_type"] = "dinner"
                else:
                    data["meal_type"] = None
        return data

    @model_validator(mode="after")
    def validate_text_not_blank(self) -> TurnRequest:
        if not self.text.strip():
            raise ValueError("text must not be empty or whitespace only")
        if "\x00" in self.text:
            raise ValueError("text must not contain null bytes")
        return self


class LoginRequest(BaseModel):
    """Patient login credentials payload."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255, description="Patient registered email")
    password: str = Field(min_length=1, max_length=255, description="Plaintext password for verification")

    @model_validator(mode="after")
    def validate_login_fields(self) -> LoginRequest:
        if "\x00" in self.email or "\x00" in self.password:
            raise ValueError("Credentials must not contain null bytes")
        return self


class OnboardingRequest(BaseModel):
    """Patient registration and clinical profile onboarding payload."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=128, description="Patient full name")
    email: str = Field(min_length=3, max_length=255, description="Unique account email")
    password: str = Field(min_length=6, max_length=255, description="Account password (min 6 chars)")
    age: int | None = Field(default=None, ge=1, le=120, description="Age in years")
    gender: str | None = Field(default=None, max_length=32, description="Gender identity")
    height_cm: float | None = Field(default=None, ge=40.0, le=280.0, description="Height in centimeters")
    weight_kg: float | None = Field(default=None, ge=10.0, le=400.0, description="Weight in kilograms")
    conditions: list[str] = Field(default_factory=list, max_length=50, description="Self-reported clinical conditions")
    hypertension_stage: str | None = Field(
        default=None, max_length=32, description="Patient-reported hypertension grade or stage"
    )
    gym_clearance: bool | None = Field(default=None, description="Deprecated; not treated as clinician verification")
    activity_level: str | None = Field(default=None, max_length=32, description="Baseline activity level")
    movement_restrictions: list[str] = Field(
        default_factory=list, max_length=50, description="Physical movement limitations"
    )
    dietary_preference: str | None = Field(default=None, max_length=64, description="Dietary pattern")
    health_goals: list[str] = Field(
        default_factory=list, max_length=50, description="Primary health coaching objectives"
    )
    language: str = Field(
        default="hinglish", max_length=32, description="Preferred language (english, hindi, hinglish)"
    )
    health_focuses: list[str] = Field(default_factory=list, max_length=50, description="Selected health focus areas")
    health_focus_other: str = Field(default="", max_length=1000, description="Custom self-described health concern")

    @model_validator(mode="after")
    def validate_onboard_fields(self) -> OnboardingRequest:
        if "@" not in self.email or "." not in self.email:
            raise ValueError("Invalid email format")
        if "\x00" in self.email or "\x00" in self.password or "\x00" in self.name:
            raise ValueError("Fields must not contain null bytes")
        return self


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
    """Personal Experience Profile details."""

    model_config = ConfigDict(extra="ignore")

    hypertension_stage: str = "unknown"
    gym_clearance: bool | None = None
    allowed_modalities: list[str] = Field(default_factory=list)
    restricted_modalities: list[str] = Field(default_factory=list)
    primary_focus: str = ""
    secondary_focuses: list[str] = Field(default_factory=list)
    user_reported_concerns: str = ""
    diagnosed_conditions: list[str] = Field(default_factory=list)


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
    evidence_ids: list[str] = Field(default_factory=list)
    retrieval_status: str = "not_requested"
    conversation_id: str | None = None


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

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=128)
    age: int | None = Field(default=None, ge=1, le=120)
    gender: str | None = Field(default=None, max_length=32)
    height_cm: float | None = Field(default=None, ge=40.0, le=280.0)
    weight_kg: float | None = Field(default=None, ge=10.0, le=400.0)
    dietary_preference: str | None = Field(default=None, max_length=64)
    health_goals: list[str] | None = Field(default=None, max_length=50)
    health_conditions: list[str] | None = Field(default=None, max_length=50)
    language: str | None = Field(default=None, max_length=32)
    health_focuses: list[str] | None = Field(default=None, max_length=50)
    health_focus_other: str | None = Field(default=None, max_length=1000)
    primary_focus: str | None = Field(default=None, max_length=255)
    secondary_focuses: list[str] | None = Field(default=None, max_length=50)
    user_reported_concerns: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_profile_fields(self) -> ProfileUpdateRequest:
        for k, v in self.__dict__.items():
            if isinstance(v, str) and "\x00" in v:
                raise ValueError(f"{k} must not contain null bytes")
        return self
