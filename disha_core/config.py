"""Configuration management for Disha AI Core.

Reads runtime configuration from shell environment variables with secure defaults.
Supports dynamic override during tests and isolated container execution.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True)
class Settings:
    """Runtime configuration settings."""

    # Database connection parameters
    database_url: str | None = None
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "disha"
    db_user: str = "disha"
    db_password: str = ""

    # Database connection pool settings
    db_pool_min: int = 2
    db_pool_max: int = 30
    db_pool_timeout: float = 5.0

    # LLM Providers
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_health_data_authorized: bool = False
    groq_usage_charges_authorized: bool = False
    groq_health_data_processing_approved: bool = False

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gemini_health_data_authorized: bool = False
    gemini_paid_or_contracted: bool = False

    edge_tts_health_data_processing_approved: bool = False
    qwen3_tts_health_data_processing_approved: bool = False
    qwen3_tts_url: str = "http://localhost:8880/v1/audio/speech"
    qwen3_tts_model: str = "qwen3-tts"
    qwen3_tts_voice: str = "disha-warm-hinglish"
    tts_engine: str = "qwen3"

    # Security & API limits
    cors_allowed_origins: Sequence[str] = field(default_factory=tuple)
    admin_api_key: str = ""
    max_voice_turn_bytes: int = 10 * 1024 * 1024  # 10 MB limit for voice turns
    max_request_body_bytes: int = 2 * 1024 * 1024  # 2 MB limit for standard JSON payloads
    rate_limit_enabled: bool = True
    password_salt: str = "disha_salt_v1"

    # Behavior Spec v1 feature flag (rollback to legacy by setting env BEHAVIOR_SPEC_V1=false)
    behavior_spec_v1: bool = True
    confirm_critical_values: bool = False  # D2: confirm allergies/medicines/doses; default OFF
    language_switch_threshold: int = 2  # D5: consecutive msgs before silent language switch

    @classmethod
    def from_env(cls) -> Settings:
        """Dynamically load settings from current os.environ."""
        cors_raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
        cors_origins = tuple(v.strip() for v in cors_raw.split(",") if v.strip())

        return cls(
            database_url=os.getenv("DATABASE_URL"),
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_name=os.getenv("DB_NAME", "disha"),
            db_user=os.getenv("DB_USER", "disha"),
            db_password=os.getenv("DB_PASSWORD", ""),
            db_pool_min=int(os.getenv("DB_POOL_MIN", "2")),
            db_pool_max=int(os.getenv("DB_POOL_MAX", "30")),
            db_pool_timeout=float(os.getenv("DB_POOL_TIMEOUT", "5.0")),
            groq_api_key=os.getenv("GROQ_API_KEY", ""),
            groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
            groq_health_data_authorized=os.getenv("GROQ_HEALTH_DATA_AUTHORIZED", "false").casefold() == "true",
            groq_usage_charges_authorized=os.getenv("GROQ_USAGE_CHARGES_AUTHORIZED", "false").casefold() == "true",
            groq_health_data_processing_approved=os.getenv("GROQ_HEALTH_DATA_PROCESSING_APPROVED", "false").casefold()
            == "true",
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
            gemini_health_data_authorized=os.getenv("GEMINI_HEALTH_DATA_AUTHORIZED", "false").casefold() == "true",
            gemini_paid_or_contracted=os.getenv("GEMINI_PAID_OR_CONTRACTED", "false").casefold() == "true",
            edge_tts_health_data_processing_approved=os.getenv(
                "EDGE_TTS_HEALTH_DATA_PROCESSING_APPROVED", "false"
            ).casefold()
            == "true",
            qwen3_tts_health_data_processing_approved=os.getenv(
                "QWEN3_TTS_HEALTH_DATA_PROCESSING_APPROVED", "false"
            ).casefold()
            == "true",
            qwen3_tts_url=os.getenv("QWEN3_TTS_URL", "http://localhost:8880/v1/audio/speech"),
            qwen3_tts_model=os.getenv("QWEN3_TTS_MODEL", "qwen3-tts"),
            qwen3_tts_voice=os.getenv("QWEN3_TTS_VOICE", "disha-warm-hinglish"),
            tts_engine=os.getenv("TTS_ENGINE", "qwen3"),
            cors_allowed_origins=cors_origins,
            admin_api_key=os.getenv("ADMIN_API_KEY", ""),
            max_voice_turn_bytes=int(os.getenv("MAX_VOICE_TURN_BYTES", str(10 * 1024 * 1024))),
            max_request_body_bytes=int(os.getenv("MAX_REQUEST_BODY_BYTES", str(2 * 1024 * 1024))),
            rate_limit_enabled=os.getenv("RATE_LIMIT_ENABLED", "true").casefold() != "false",
            password_salt=os.getenv("PASSWORD_SALT", "disha_salt_v1"),
            behavior_spec_v1=os.getenv("BEHAVIOR_SPEC_V1", "true").casefold() == "true",
            confirm_critical_values=os.getenv("CONFIRM_CRITICAL_VALUES", "false").casefold() == "true",
            language_switch_threshold=int(os.getenv("LANGUAGE_SWITCH_THRESHOLD", "2")),
        )


def get_settings() -> Settings:
    """Convenience getter returning fresh settings evaluated from os.environ."""
    return Settings.from_env()


TEAM_CONFIRMATION_REPLACEMENTS = {
    "hinglish": "Main is baare mein team se confirm karke aapko bataungi.",
    "hi_deva": "मैं इस बारे में टीम से पुष्टि करके आपको बताऊँगी।",
    "en": "I will confirm the plan and pricing details with the team and get back to you.",
}

DEFAULT_PRICING_REPLACEMENT = os.getenv(
    "PRICING_REPLACEMENT",
    TEAM_CONFIRMATION_REPLACEMENTS["hinglish"],
)
