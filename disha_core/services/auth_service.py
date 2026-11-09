"""Authentication and identity service for Disha AI Core."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import uuid
from typing import Any

from fastapi import HTTPException

from disha_core.models.schemas import LoginRequest, OnboardingRequest

_PASSWORD_ITERATIONS = 310_000


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${_PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, saved_hash: str) -> tuple[bool, bool]:
    """Return (valid, needs_upgrade), supporting legacy fixed-salt SHA-256 once."""
    if saved_hash.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt_hex, digest_hex = saved_hash.split("$", 3)
            actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
            return hmac.compare_digest(actual.hex(), digest_hex), False
        except (ValueError, TypeError):
            return False, False
    legacy = hashlib.sha256((password + os.getenv("PASSWORD_SALT", "disha_salt_v1")).encode()).hexdigest()
    return hmac.compare_digest(legacy, saved_hash), True


def access_token_hash(token: str) -> str:
    """Compute deterministic SHA-256 digest of bearer access token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def authenticate_patient_token(pool: Any, authorization: str | None) -> str:
    """Resolve patient ID from bearer authorization token.

    Fails closed with HTTP 401 or HTTP 503.
    """
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.casefold() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Bearer token required")

    if pool is None:
        raise HTTPException(status_code=503, detail="Patient storage unavailable")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT patient_id FROM patient_access_tokens
               WHERE token_hash = $1 AND revoked_at IS NULL
                 AND (expires_at IS NULL OR expires_at > NOW())""",
            access_token_hash(token.strip()),
        )

    if row is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return str(row["patient_id"])


async def register_patient(pool: Any, payload: OnboardingRequest) -> dict[str, Any]:
    """Register a patient and store only information they actually supplied."""
    if "@" not in payload.email or "." not in payload.email:
        raise HTTPException(status_code=400, detail="Invalid email format")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    patient_id = f"pt_{uuid.uuid4().hex[:10]}"
    raw_token = f"pt_live_{uuid.uuid4().hex}"
    t_hash = access_token_hash(raw_token)
    pwd_hash = _hash_password(payload.password)

    async with pool.acquire() as conn, conn.transaction():
        existing_pid = await conn.fetchval(
            "SELECT patient_id FROM patient_profiles WHERE email = $1",
            payload.email.lower().strip(),
        )
        if existing_pid:
            raise HTTPException(
                status_code=409,
                detail="An account with this email address already exists. Please sign in.",
            )

        # 1. Insert patient profile
        language_val = (payload.language or "hinglish").lower().strip()
        focuses = list(payload.health_focuses or [])
        other_focus = (payload.health_focus_other or "").strip()
        primary_focus = focuses[0] if focuses else ""
        secondary_focuses = focuses[1:] if len(focuses) > 1 else []
        reported_conditions = list(payload.conditions or [])

        await conn.execute(
            """INSERT INTO patient_profiles (
                   patient_id, email, password_hash, name, age, gender, 
                   height_cm, weight_kg, dietary_preference, health_goals,
                   language, health_focuses, health_focus_other, health_conditions,
                   created_at
               ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW())""",
            patient_id,
            payload.email.lower().strip(),
            pwd_hash,
            payload.name.strip(),
            payload.age,
            payload.gender,
            payload.height_cm,
            payload.weight_kg,
            payload.dietary_preference,
            payload.health_goals,
            language_val,
            focuses,
            other_focus,
            reported_conditions,
        )

        # 2. Insert access token
        await conn.execute(
            """INSERT INTO patient_access_tokens (token_hash, patient_id, created_at, expires_at)
               VALUES ($1, $2, NOW(), NOW() + INTERVAL '365 days')""",
            t_hash,
            patient_id,
        )

        # Patient-reported facts stay in the profile; clinical PEP is clinician-owned.
        await conn.execute(
            """INSERT INTO patient_pep (
                   patient_id, primary_focus, secondary_focuses, user_reported_concerns,
                   language, dietary_preference, updated_at
               ) VALUES ($1, $2, $3, $4, $5, $6, NOW())""",
            patient_id,
            primary_focus,
            secondary_focuses,
            other_focus,
            language_val,
            payload.dietary_preference,
        )

    return {
        "token": raw_token,
        "patient_id": patient_id,
        "patient_name": payload.name,
        "status": "authenticated",
        "reported_conditions": reported_conditions,
    }


async def login_patient(pool: Any, payload: LoginRequest) -> dict[str, Any]:
    """Verify credentials and return patient session token."""
    if "@" not in payload.email or "." not in payload.email:
        raise HTTPException(status_code=400, detail="Invalid email format")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    email_clean = payload.email.lower().strip()

    # 1. Check if user exists in database
    if pool is not None:
        async with pool.acquire() as conn:
            user_row = await conn.fetchrow(
                "SELECT patient_id, name, password_hash FROM patient_profiles WHERE email = $1",
                email_clean,
            )
            if user_row is not None:
                valid, needs_upgrade = _verify_password(payload.password, str(user_row["password_hash"]))
                if not valid:
                    raise HTTPException(status_code=401, detail="Invalid email or password")
                if needs_upgrade:
                    await conn.execute(
                        "UPDATE patient_profiles SET password_hash = $2 WHERE patient_id = $1",
                        user_row["patient_id"],
                        _hash_password(payload.password),
                    )
                session_token = f"pt_live_{uuid.uuid4().hex}"
                t_hash = access_token_hash(session_token)
                await conn.execute(
                    """INSERT INTO patient_access_tokens (token_hash, patient_id, created_at, expires_at)
                       VALUES ($1, $2, NOW(), NOW() + INTERVAL '365 days')""",
                    t_hash,
                    user_row["patient_id"],
                )
                return {
                    "token": session_token,
                    "patient_id": user_row["patient_id"],
                    "patient_name": user_row["name"],
                    "status": "authenticated",
                }

    raise HTTPException(status_code=401, detail="Invalid email or password")
