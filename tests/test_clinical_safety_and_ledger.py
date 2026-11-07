"""Clinical Safety & Merkle Audit Ledger Concurrency Test Suite.

Verifies:
1. Aho-Corasick Emergency Breaker against adversarial Hinglish/Devanagari/punctuation edge cases.
2. Clinical Safety Guardrails prohibiting:
   - Unsupported diagnosis claims (e.g. 'Aapko diabetes hai')
   - Unauthorized prescription alterations (e.g. 'Metformin dose double kar lijiye')
   - High-sodium / unsafe food recommendations for hypertension patients
   - Ungrounded clinical claims
3. Merkle Audit Ledger concurrency, non-blocking behavior, dynamic WAL crash recovery, and parallel chain integrity.
"""
from __future__ import annotations

import asyncio
import hashlib
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from disha_core.compliance.ledger import AuditLedger, AuditRecord, current_hash
from disha_core.engine.context_builder import add_approved_remedy_constraints
from disha_core.pipeline.breaker import EmergencyBreaker
from disha_core.pipeline.router import Intent, IntentRouter
from disha_core.pipeline.validator import (
    DIAGNOSIS_REPLACEMENT,
    HYPERTENSION_SODIUM_REPLACEMENT,
    PRESCRIPTION_REPLACEMENT,
    REMEDY_UNAVAILABLE,
    SentenceValidator,
)


# ==============================================================================
# SECTION 1: Aho-Corasick Emergency Breaker Adversarial Edge Cases
# ==============================================================================

@pytest.mark.parametrize(
    "text,expected_category",
    [
        # Cardiovascular & Acute Presentations
        ("dil ka daura", "CARDIOVASCULAR"),
        ("dil ka daura pada hai", "CARDIOVASCULAR"),
        ("left hand pain with sweating", "CARDIOVASCULAR"),
        ("left arm pain radiating to neck", "CARDIOVASCULAR"),
        ("severe chest tightness", "CARDIOVASCULAR"),
        ("chaati mein dard", "CARDIOVASCULAR"),
        ("heart-attack", "CARDIOVASCULAR"),
        ("cardiac-arrest", "CARDIOVASCULAR"),
        ("heart\u200battack", "CARDIOVASCULAR"),
        ("heart\xadattack", "CARDIOVASCULAR"),
        ("छाती में दर्द", "CARDIOVASCULAR"),
        ("सीने में दर्द", "CARDIOVASCULAR"),
        ("दिल का दौरा", "CARDIOVASCULAR"),
        # Respiratory
        ("saas lene me taklif", "RESPIRATORY"),
        ("dum ghut raha hai", "RESPIRATORY"),
        ("asthma-attack", "RESPIRATORY"),
        ("सांस नहीं आ रही", "RESPIRATORY"),
        # Neurological
        ("achanak chehra tedha", "NEUROLOGICAL"),
        ("ek taraf kamzori", "NEUROLOGICAL"),
        ("चेहरा टेढ़ा", "NEUROLOGICAL"),
        # Crisis / Self-Harm
        ("self-harm", "CRISIS"),
        ("आत्महत्या", "CRISIS"),
        ("ज़हर खा लिया", "CRISIS"),
        # Trauma
        ("blood-vomiting", "TRAUMA"),
        ("खून की उल्टी", "TRAUMA"),
    ],
)
def test_emergency_breaker_intercepts_adversarial_edge_cases(text: str, expected_category: str):
    breaker = EmergencyBreaker()
    result = breaker.check(text)
    assert result.triggered, f"Failed to trigger on emergency utterance: {text!r}"
    assert result.category == expected_category, f"Expected {expected_category}, got {result.category}"
    assert "112" in (result.response or "")


def test_emergency_breaker_preserves_safe_utterances():
    breaker = EmergencyBreaker()
    safe_cases = [
        "I like chest painting as an art form.",
        "Aam khana pasand hai mujhe.",
        "Kal morning walk par 112 steps chale.",
        "Mere paas ek heart-shaped pillow hai.",
    ]
    for safe_text in safe_cases:
        res = breaker.check(safe_text)
        assert not res.triggered, f"False positive triggered on safe text: {safe_text!r}"


def test_devanagari_router_emergency_deflection():
    router = IntentRouter()
    emergency, intent = router.route("सीने में बहुत तेज दर्द है")
    assert emergency.triggered
    assert emergency.category == "CARDIOVASCULAR"
    assert intent is None


# ==============================================================================
# SECTION 2: Clinical Safety Guardrails (Diagnosis, Prescription, Sodium, Grounding)
# ==============================================================================

@pytest.mark.parametrize(
    "text",
    [
        "Aapko diabetes hai.",
        "You have been diagnosed with Type 2 Diabetes.",
        "Mera diagnosis yeh hai ki aapko hypertension hai.",
        "आपको डायबिटीज है।",
    ],
)
def test_prohibit_diagnosis_claims(text: str):
    validator = SentenceValidator()
    result = validator.validate_sentence(text)
    assert result.status == "rewritten"
    assert "diagnosis_boundary" in result.reasons
    assert result.text == DIAGNOSIS_REPLACEMENT
    assert "doctor" not in result.text.lower()


@pytest.mark.parametrize(
    "text",
    [
        "Metformin dose double kar lijiye.",
        "Apni blood pressure ki dawai band kar dijiye.",
        "Take 500mg Metformin twice daily.",
        "Change your medication dose right now.",
        "दवा बंद कर दीजिए।",
    ],
)
def test_prohibit_unauthorized_prescription_changes(text: str):
    validator = SentenceValidator()
    result = validator.validate_sentence(text)
    assert result.status == "rewritten"
    assert "prescription_boundary" in result.reasons
    assert result.text == PRESCRIPTION_REPLACEMENT


def test_prohibit_high_sodium_food_for_hypertension():
    validator = SentenceValidator()
    context = {"pep": {"hypertension_stage": "stage 2"}}
    for food in [
        "Aap roz papad khayein.",
        "Khane ke saath achaar zaroor lein.",
        "Pickles and namkeen are great snacks.",
        "Thoda zyada namak add karein.",
    ]:
        result = validator.validate_sentence(food, context)
        assert result.status == "rewritten"
        assert "hypertension_sodium" in result.reasons
        assert result.text == HYPERTENSION_SODIUM_REPLACEMENT


def test_grounding_validation_rewrites_ungrounded_symptoms():
    validator = SentenceValidator()
    # Unapproved remedy for GI_BLOATING
    result = validator.validate_turn(
        "Aap rest karein.",
        {"clinical_tags": ["GI_BLOATING"], "protocol_approved": False},
    )
    assert result.status == "rewritten"
    assert "remedy_not_configured" in result.reasons
    assert result.text == REMEDY_UNAVAILABLE


def test_grounding_validation_accepts_verified_tokens():
    validator = SentenceValidator()
    context: dict[str, Any] = {"clinical_tags": ["GI_BLOATING"]}
    chunks = [
        {
            "condition_tag": "GI_BLOATING",
            "required_remedy_tokens": ("jeera", "saunf"),
            "guideline_content": "Warm jeera and saunf water provides relief.",
            "source_citation": "ICMR Clinical Guidance",
        }
    ]
    add_approved_remedy_constraints(context, chunks)
    assert context["protocol_approved"] is True

    turn_res = validator.validate_turn("Peejiye warm jeera and saunf water.", context)
    assert turn_res.status == "accepted"


# ==============================================================================
# SECTION 3: Merkle Audit Ledger Concurrency & Tamper Evidence
# ==============================================================================

class MockConnection:
    def __init__(self, state):
        self.state = state

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def transaction(self):
        return self

    async def fetchval(self, query, *args):
        if "FROM audit_chain_head" in query:
            return self.state["head"]
        if "SELECT EXISTS" in query:
            return False
        return None

    async def execute(self, query, *args):
        if "INSERT INTO audit_claim_ledger" in query:
            ev_id, p_id, u_in, llm_out, brk, val, prev, cur = args
            self.state["rows"].append({
                "event_id": ev_id,
                "patient_id": p_id,
                "user_input": u_in,
                "llm_output": llm_out,
                "status": f"{brk}|{val}",
                "prev_hash": prev,
                "current_hash": cur,
            })
        elif "UPDATE audit_chain_head" in query:
            self.state["head"] = args[0]


class MockPool:
    def __init__(self):
        self.state = {"head": "0" * 64, "rows": []}

    def acquire(self):
        return MockConnection(self.state)


@pytest.mark.asyncio
async def test_ledger_parallel_concurrency_and_chain_integrity():
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_path = Path(tmpdir) / "test_wal.db"
        pool = MockPool()
        ledger = AuditLedger(pool, max_queue_size=1024, wal_path=wal_path)
        ledger.start()

        num_tasks = 8
        records_per_task = 25
        total_records = num_tasks * records_per_task

        async def worker(w_id: int):
            for i in range(records_per_task):
                rec = AuditRecord(
                    patient_id=f"pt_parallel_{w_id}",
                    user_input=f"query_{w_id}_{i}",
                    llm_output=f"response_{w_id}_{i}",
                    breaker_status="clear",
                    validator_status="accepted",
                )
                success = ledger.enqueue(rec)
                assert success

        await asyncio.gather(*(worker(w) for w in range(num_tasks)))
        await ledger.close(drain_timeout=10.0)

        rows = pool.state["rows"]
        assert len(rows) == total_records

        # Cryptographically verify the SHA-256 Merkle chain
        prev = "0" * 64
        for idx, row in enumerate(rows):
            assert row["prev_hash"] == prev, f"Chain broken at block {idx}"
            payload = f"{prev}|{row['patient_id']}|{row['user_input']}|{row['llm_output']}|{row['status']}"
            expected_cur = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            assert row["current_hash"] == expected_cur, f"Hash divergence at block {idx}"
            prev = row["current_hash"]


@pytest.mark.asyncio
async def test_ledger_wal_dynamic_crash_recovery_no_stranded_records():
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_path = Path(tmpdir) / "crash_recovery_wal.db"
        total_stranded = 80
        queue_size = 15

        # Populate SQLite directly to simulate crash with uncommitted records
        with sqlite3.connect(str(wal_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""CREATE TABLE wal_audit_records (
                event_id TEXT PRIMARY KEY, patient_id TEXT, user_input TEXT,
                llm_output TEXT, breaker_status TEXT, validator_status TEXT, created_at REAL
            )""")
            for i in range(total_stranded):
                conn.execute(
                    "INSERT INTO wal_audit_records VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), f"pt_crash_{i}", f"in_{i}", f"out_{i}", "clear", "accepted", float(i)),
                )
            conn.commit()

        pool = MockPool()
        # Initialize ledger with queue size much smaller than total uncommitted records
        ledger = AuditLedger(pool, max_queue_size=queue_size, wal_path=wal_path)
        ledger.start()

        # Let the worker drain and dynamically refill all records
        await asyncio.sleep(0.4)
        await ledger.close(drain_timeout=5.0)

        assert len(pool.state["rows"]) == total_stranded
        with sqlite3.connect(str(wal_path)) as conn:
            remaining = conn.execute("SELECT COUNT(*) FROM wal_audit_records").fetchone()[0]
        assert remaining == 0
