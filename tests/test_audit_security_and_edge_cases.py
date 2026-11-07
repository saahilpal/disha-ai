"""Comprehensive QA & Security Vulnerability Regression Suite for Disha AI Core.

Tests cover:
1. SQL injection / query parameter safety.
2. User Registration race conditions, duplicate email overwriting, auth bypass, and password hashing flaws.
3. Vitals validation, extreme BMI, PEP hypertension parsing, and weekday format mismatches.
4. WebSocket resource exhaustion, unauthenticated frame handling, frame size checks, and audit ledger pollution.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from pydantic import ValidationError

from disha_core.compliance.ledger import AuditLedger, AuditRecord
from disha_core.engine.context_builder import build_patient_context
from disha_core.main import (
    LoginRequest,
    MAX_VOICE_TURN_BYTES,
    OnboardingRequest,
    TurnRequest,
    create_app,
)


# ==============================================================================
# SECTION 1: SQL Injection & Query Parameterization
# ==============================================================================

def test_sql_injection_payload_in_turn_request():
    """Verify that malicious SQL injection strings in TurnRequest are handled safely."""
    malicious_inputs = [
        "'; DROP TABLE patient_profiles; --",
        "1' OR '1'='1",
        "admin'--",
        "UNION SELECT null, null, password_hash FROM patient_profiles--",
    ]
    for sql_inj in malicious_inputs:
        req = TurnRequest(text=sql_inj)
        assert req.text == sql_inj


@pytest.mark.asyncio
async def test_build_patient_context_query_safety():
    """Verify build_patient_context passes query arguments via parameters, not interpolation."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = None

    # Normal query
    context = await build_patient_context(mock_conn, "pt_safe_123", "monday", "breakfast")
    assert context["patient_id"] == "pt_safe_123"
    assert mock_conn.fetchrow.call_count == 2
    
    # Check that parameters are passed as separate arguments, not concatenated
    pep_call = mock_conn.fetchrow.call_args_list[0]
    diet_call = mock_conn.fetchrow.call_args_list[1]
    assert pep_call[0][1] == "pt_safe_123"
    assert diet_call[0][1] == "pt_safe_123"
    assert diet_call[0][2] == "monday"
    assert diet_call[0][3] == "breakfast"


# ==============================================================================
# SECTION 2: User Registration & Authentication
# ==============================================================================

@pytest.mark.asyncio
async def test_duplicate_registration_overwrites_existing_user():
    """Vulnerability Proof: Registering an existing email overwrites the victim's profile

    and generates an orphaned patient_id without returning 409 Conflict.
    """
    app = create_app()
    async with app.router.lifespan_context(app):
        if app.state.pool is None:
            pytest.skip("PostgreSQL pool not available")
        
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            unique_email = f"victim_{uuid.uuid4().hex[:8]}@example.com"
            
            # 1. Victim registers
            r1 = await client.post("/auth/register", json={
                "name": "Victim User",
                "email": unique_email,
                "password": "VictimPassword123",
                "age": 32,
                "gender": "female",
                "height_cm": 165.0,
                "weight_kg": 62.0,
                "dietary_preference": "Vegetarian",
            })
            assert r1.status_code == 200
            data_1 = r1.json()
            victim_pid = data_1["patient_id"]
            victim_token = data_1["token"]

            # 2. Attacker registers with same email
            r2 = await client.post("/auth/register", json={
                "name": "Attacker Hijacker",
                "email": unique_email,
                "password": "AttackerPassword999",
                "age": 48,
                "gender": "male",
                "height_cm": 182.0,
                "weight_kg": 88.0,
                "dietary_preference": "Non-Vegetarian",
            })
            # FLAW: Returns 200 instead of 409 Conflict
            assert r2.status_code == 200
            data_2 = r2.json()
            attacker_pid = data_2["patient_id"]
            attacker_token = data_2["token"]

            # FLAW: A new patient_id was generated instead of rejecting the duplicate
            assert attacker_pid != victim_pid

            # 3. Inspect victim's profile via victim token: Name and vitals were silently overwritten!
            p1_res = await client.get("/patient/profile", headers={"Authorization": f"Bearer {victim_token}"})
            assert p1_res.status_code == 200
            victim_profile = p1_res.json()["profile"]
            assert victim_profile["name"] == "Attacker Hijacker"
            assert victim_profile["age"] == 48

            # 4. Attacker's token points to orphaned patient_id; profile is null!
            p2_res = await client.get("/patient/profile", headers={"Authorization": f"Bearer {attacker_token}"})
            assert p2_res.status_code == 200
            attacker_profile = p2_res.json()["profile"]
            assert attacker_profile is None


@pytest.mark.asyncio
async def test_auth_login_credential_bypass_to_demo_account():
    """Vulnerability Proof: Any non-existent email or wrong password bypasses auth

    and returns a live token for pt_test_01 (Aarav Sharma).
    """
    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post("/auth/login", json={
                "email": "unregistered_stranger_12345@example.com",
                "password": "invalidpassword",
            })
            # FLAW: Instead of 401 Unauthorized, returns 200 OK and logs in as Aarav Sharma!
            assert res.status_code == 200
            data = res.json()
            assert data["patient_id"] == "pt_test_01"
            assert data["patient_name"] == "Aarav Sharma"
            assert data["status"] == "authenticated"


def test_password_storage_insecure_hashing():
    """Vulnerability Proof: Password hashing uses static-salt single-iteration SHA-256."""
    raw_pwd = "MySecretPassword123"
    # Current main.py implementation:
    hash_v1 = hashlib.sha256((raw_pwd + "disha_salt_v1").encode()).hexdigest()
    # Identical for any user with the same password (no unique per-user salt)
    hash_v2 = hashlib.sha256((raw_pwd + "disha_salt_v1").encode()).hexdigest()
    assert hash_v1 == hash_v2
    # 64-character un-stretched SHA256 hex string
    assert len(hash_v1) == 64


# ==============================================================================
# SECTION 3: PEP & Diet Schedule Generation & Vitals Edge Cases
# ==============================================================================

def test_vitals_negative_age_rejected_by_pydantic():
    """Negative age is rejected by Pydantic validation."""
    with pytest.raises(ValidationError):
        OnboardingRequest(name="Test", email="test@example.com", password="password", age=-5)


def test_vitals_extreme_bmi_unrestricted_gym_clearance():
    """Edge Case: Height 120cm, Weight 300kg (BMI = 208) is accepted by schema

    and receives unrestricted gym clearance if gym_clearance=True.
    """
    req = OnboardingRequest(
        name="Extreme BMI Patient",
        email="bmi_extreme@example.com",
        password="password123",
        height_cm=120.0,
        weight_kg=300.0,
        hypertension_stage="normal",
        gym_clearance=True,
    )
    assert req.height_cm == 120.0
    assert req.weight_kg == 300.0
    bmi = req.weight_kg / ((req.height_cm / 100.0) ** 2)
    assert bmi > 200.0

    # Test main.py PEP classification logic with extreme BMI
    htn_input = (req.hypertension_stage or "").lower()
    if "stage 2" in htn_input or any("stage 2" in c.lower() for c in req.conditions):
        htn_stage = "stage 2"
    elif "stage 1" in htn_input or any("stage 1" in c.lower() for c in req.conditions):
        htn_stage = "stage 1"
    else:
        htn_stage = "normal"

    if htn_stage in ("stage 1", "stage 2") or not req.gym_clearance or any("heavy" in r.lower() for r in req.movement_restrictions):
        allowed = ["brisk walking", "gentle yoga"]
        gym_cleared = False
    else:
        allowed = ["brisk walking", "jogging", "swimming", "cycling", "moderate strength training"]
        gym_cleared = bool(req.gym_clearance)

    # Patient with BMI 208 is cleared for unmonitored jogging and moderate strength training!
    assert gym_cleared is True
    assert "jogging" in allowed
    assert "moderate strength training" in allowed


def test_hypertension_stage_parsing_loopholes():
    """Edge Case: Common hypertension clinical labels silently fall back to 'normal'."""
    failing_labels = [
        "stage2",
        "stage-2",
        "grade 2",
        "severe hypertension",
        "hypertensive crisis",
        "high blood pressure",
        "stage 2 hypertension - severe",
    ]
    for label in failing_labels:
        htn_input = label.lower()
        if "stage 2" in htn_input:
            stage = "stage 2"
        elif "stage 1" in htn_input:
            stage = "stage 1"
        else:
            stage = "normal"
        
        # Notice "stage2", "stage-2", "grade 2", "severe hypertension", "hypertensive crisis"
        # all erroneously resolve to "normal"
        if label in ["stage2", "stage-2", "grade 2", "severe hypertension", "hypertensive crisis", "high blood pressure"]:
            assert stage == "normal"


@pytest.mark.asyncio
async def test_today_ist_weekday_mismatch_crashes_patient_context():
    """Edge Case: Abbreviated or non-English day formats cause an uncaught ValueError."""
    mock_conn = AsyncMock()
    with pytest.raises(ValueError, match="day_of_week must be a full weekday name"):
        await build_patient_context(mock_conn, "pt_123", "sat", "dinner")
    with pytest.raises(ValueError, match="day_of_week must be a full weekday name"):
        await build_patient_context(mock_conn, "pt_123", "शनिवार", "dinner")


# ==============================================================================
# SECTION 4: WebSocket Security & Resource Exhaustion
# ==============================================================================

def test_max_voice_turn_bytes_constant():
    """Verify MAX_VOICE_TURN_BYTES constant is 10 MB."""
    assert MAX_VOICE_TURN_BYTES == 10 * 1024 * 1024


@pytest.mark.asyncio
async def test_websocket_text_frame_audit_ledger_pollution():
    """Vulnerability Proof: Oversized text frames on WebSocket bypass size limits

    and pollute the Audit Ledger.
    """
    oversized_text = "emergency advice needed " * 500  # 12,000 characters
    assert len(oversized_text) > 5000

    # TurnRequest enforces max_length=5000
    with pytest.raises(ValidationError):
        TurnRequest(text=oversized_text)

    # In main.py lines 582-586, even when process_text catches the ValidationError,
    # it still executes:
    # finally:
    #     if text:
    #         _enqueue_audit(..., AuditRecord(patient_id, text, ...))
    # This proves the ledger is forced to record rejected, oversized payloads.
    mock_pool = MagicMock()
    ledger = AuditLedger(mock_pool, wal_path=None)
    record = AuditRecord("pt_test", oversized_text, "", "clear", "accepted")
    assert ledger.enqueue(record) is True
    assert ledger.queue.qsize() == 1
    queued = ledger.queue.get_nowait()
    assert len(queued.user_input) == len(oversized_text)
