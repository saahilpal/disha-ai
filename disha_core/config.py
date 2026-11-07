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
    groq_health_data_authorized: bool = True
    groq_usage_charges_authorized: bool = True
    groq_health_data_processing_approved: bool = True

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gemini_health_data_authorized: bool = True
    gemini_paid_or_contracted: bool = True

    edge_tts_health_data_processing_approved: bool = True

    # Security & API limits
    cors_allowed_origins: Sequence[str] = field(default_factory=tuple)
    admin_api_key: str = ""
    max_voice_turn_bytes: int = 10 * 1024 * 1024  # 10 MB limit for voice turns
    password_salt: str = "disha_salt_v1"

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
            groq_health_data_authorized=os.getenv("GROQ_HEALTH_DATA_AUTHORIZED", "true").casefold() == "true",
            groq_usage_charges_authorized=os.getenv("GROQ_USAGE_CHARGES_AUTHORIZED", "true").casefold() == "true",
            groq_health_data_processing_approved=os.getenv("GROQ_HEALTH_DATA_PROCESSING_APPROVED", "true").casefold() == "true",
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
            gemini_health_data_authorized=os.getenv("GEMINI_HEALTH_DATA_AUTHORIZED", "true").casefold() == "true",
            gemini_paid_or_contracted=os.getenv("GEMINI_PAID_OR_CONTRACTED", "true").casefold() == "true",
            edge_tts_health_data_processing_approved=os.getenv("EDGE_TTS_HEALTH_DATA_PROCESSING_APPROVED", "true").casefold() == "true",
            cors_allowed_origins=cors_origins,
            admin_api_key=os.getenv("ADMIN_API_KEY", ""),
            max_voice_turn_bytes=int(os.getenv("MAX_VOICE_TURN_BYTES", str(10 * 1024 * 1024))),
            password_salt=os.getenv("PASSWORD_SALT", "disha_salt_v1"),
        )


def get_settings() -> Settings:
    """Convenience getter returning fresh settings evaluated from os.environ."""
    return Settings.from_env()
