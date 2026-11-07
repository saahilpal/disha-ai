"""Review Queue and Zero-PHI Self-Learning Module for Laya System 1.

Implements:
1. Deterministic Zero-PHI scrubbing and HMAC-SHA256 patient pseudonymization.
2. Review queue schema capturing low-confidence, abstained, or overridden decisions.
3. Persistent SQLite-backed review queue with WAL mode and atomic state transitions.
4. Dataset export capabilities for offline retraining and benchmark promotion.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("disha.review_queue")

# Default secret salt for patient tokenization (overridden by REVIEW_QUEUE_SALT env)
DEFAULT_SALT = b"disha-clinical-review-salt-2026-strict"


class TriggerType(str, Enum):
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    ABSTAINED_FALLBACK = "ABSTAINED_FALLBACK"
    BREAKER_OVERRIDE = "BREAKER_OVERRIDE"
    VALIDATOR_OVERRIDE = "VALIDATOR_OVERRIDE"
    CLINICIAN_DISAGREEMENT = "CLINICIAN_DISAGREEMENT"
    ADVERSARIAL_PROBE = "ADVERSARIAL_PROBE"


class ReviewStatus(str, Enum):
    PENDING = "PENDING"
    ANNOTATED = "ANNOTATED"
    APPROVED_FOR_TRAINING = "APPROVED_FOR_TRAINING"
    REJECTED_NOISE = "REJECTED_NOISE"
    BENCHMARK_PROMOTED = "BENCHMARK_PROMOTED"


class ZeroPHIScrubber:
    """Deterministic clinical regex scrubber eliminating direct identifiers."""

    # Phone numbers (Indian 10-digit formats with prefixes)
    PHONE_REGEX = re.compile(r"(?:\+91[\-\s]?)?[6789]\d{9}\b|\b\d{5}[\-\s]?\d{5}\b")
    # Aadhaar number (12 digits with optional spaces/hyphens)
    AADHAAR_REGEX = re.compile(r"\b\d{4}[\s\-]\d{4}[\s\-]\d{4}\b")
    # Email addresses
    EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    # MRN / UHID identifiers
    MRN_REGEX = re.compile(r"\b(?:MRN|UHID|PATIENT|IPD|OPD)[#:\-\s]*[A-Za-z0-9]{4,15}\b", re.IGNORECASE)
    # Direct self-identifications (e.g. "My name is X", "Mera naam X hai")
    NAME_PATTERNS = [
        re.compile(r"\b(?:my name is|i am|mera naam|naam hai|patient name is)\s+([A-Za-z]{2,25}(?:\s+[A-Za-z]{2,25})?)", re.IGNORECASE),
        re.compile(r"\b(?:patient|shri|smt|mr|mrs|dr)\.?\s+([A-Za-z]{2,25}(?:\s+[A-Za-z]{2,25})?)", re.IGNORECASE),
    ]

    def __init__(self, salt: bytes | None = None) -> None:
        env_salt = os.getenv("REVIEW_QUEUE_SALT")
        self.salt = env_salt.encode("utf-8") if env_salt else (salt or DEFAULT_SALT)

    def pseudonymize_patient_id(self, patient_id: str) -> str:
        """Derives an irreversible HMAC-SHA256 token from patient_id."""
        if not patient_id:
            return "anon_unknown"
        digest = hmac.new(self.salt, patient_id.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"pt_{digest[:16]}"

    def scrub(self, text: str) -> tuple[str, bool]:
        """Scrubs text of direct personal identifiers.
        
        Returns:
            tuple[str, bool]: (scrubbed_text, was_modified)
        """
        if not text:
            return "", False

        cleaned = text
        was_modified = False

        # 1. Scrub Aadhaar
        if self.AADHAAR_REGEX.search(cleaned):
            cleaned = self.AADHAAR_REGEX.sub("[AADHAAR_REDACTED]", cleaned)
            was_modified = True

        # 2. Scrub Phone numbers
        if self.PHONE_REGEX.search(cleaned):
            cleaned = self.PHONE_REGEX.sub("[PHONE_REDACTED]", cleaned)
            was_modified = True

        # 3. Scrub Emails
        if self.EMAIL_REGEX.search(cleaned):
            cleaned = self.EMAIL_REGEX.sub("[EMAIL_REDACTED]", cleaned)
            was_modified = True

        # 4. Scrub MRN/Hospital IDs
        if self.MRN_REGEX.search(cleaned):
            cleaned = self.MRN_REGEX.sub("[MRN_REDACTED]", cleaned)
            was_modified = True

        # 5. Scrub direct name introductions
        for pat in self.NAME_PATTERNS:
            def _replace_name(match: re.Match[str]) -> str:
                full_matched = match.group(0)
                name_portion = match.group(1)
                return full_matched.replace(name_portion, "[NAME_REDACTED]")

            if pat.search(cleaned):
                cleaned = pat.sub(_replace_name, cleaned)
                was_modified = True

        return cleaned, was_modified


class ModelDecisionPayload(BaseModel):
    predicted_intent: str
    intent_confidence: float = Field(ge=0.0, le=1.0)
    emergency_triage_prob: float = Field(ge=0.0, le=1.0)
    pep_risk_score: int = Field(ge=0, le=2)
    latency_ms: float = Field(ge=0.0)
    raw_answers: dict[str, Any] = Field(default_factory=dict)


class TriggerContextPayload(BaseModel):
    fallback_reason: Optional[str] = None
    override_source: Optional[str] = None
    pre_breaker_category: Optional[str] = None
    validator_violations: list[str] = Field(default_factory=list)


class ClinicianAnnotation(BaseModel):
    reviewer_id: str
    ground_truth_intent: str
    ground_truth_emergency: bool
    ground_truth_pep_risk: int = Field(ge=0, le=2)
    clinical_rationale: str
    annotated_at_utc: str
    signature: str


class ReviewItem(BaseModel):
    review_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    audit_event_id: str
    ledger_hash: str
    anonymized_patient_token: str
    timestamp_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    trigger_type: TriggerType
    scrubbed_input_text: str
    model_checkpoint: str
    model_decision: ModelDecisionPayload
    trigger_context: TriggerContextPayload = Field(default_factory=TriggerContextPayload)
    review_status: ReviewStatus = ReviewStatus.PENDING
    clinician_annotation: Optional[ClinicianAnnotation] = None


class ReviewQueueManager:
    """Persistent SQLite-backed review queue storing non-PHI decision triage."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.scrubber = ZeroPHIScrubber()
        if db_path is None:
            db_env = os.getenv("REVIEW_QUEUE_DB")
            db_path = Path(db_env) if db_env else Path("review_queue.db")
        self.db_path = Path(db_path)
        self._mem_conn: sqlite3.Connection | None = (
            sqlite3.connect(":memory:", check_same_thread=False)
            if str(self.db_path) == ":memory:"
            else None
        )
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        if self._mem_conn is not None:
            return self._mem_conn
        return sqlite3.connect(str(self.db_path))

    def _init_db(self) -> None:
        """Initializes SQLite schema with WAL mode and indexing."""
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS review_items (
                    review_id TEXT PRIMARY KEY,
                    audit_event_id TEXT NOT NULL,
                    ledger_hash TEXT NOT NULL,
                    anonymized_patient_token TEXT NOT NULL,
                    timestamp_utc TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    scrubbed_input_text TEXT NOT NULL,
                    model_checkpoint TEXT NOT NULL,
                    model_decision_json TEXT NOT NULL,
                    trigger_context_json TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    clinician_annotation_json TEXT,
                    created_at REAL NOT NULL
                )"""
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_review_status ON review_items (review_status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trigger_type ON review_items (trigger_type);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_event ON review_items (audit_event_id);")
            conn.commit()

    def enqueue_decision(
        self,
        *,
        raw_user_input: str,
        patient_id: str,
        audit_event_id: str,
        ledger_hash: str,
        trigger_type: TriggerType,
        model_checkpoint: str,
        predicted_intent: str,
        intent_confidence: float,
        emergency_triage_prob: float,
        pep_risk_score: int,
        latency_ms: float,
        raw_answers: dict[str, Any] | None = None,
        fallback_reason: str | None = None,
        override_source: str | None = None,
        pre_breaker_category: str | None = None,
        validator_violations: list[str] | None = None,
    ) -> ReviewItem:
        """Sanitizes text, pseudonymizes patient ID, and persists item to queue."""
        scrubbed_text, _ = self.scrubber.scrub(raw_user_input)
        anon_token = self.scrubber.pseudonymize_patient_id(patient_id)

        decision = ModelDecisionPayload(
            predicted_intent=predicted_intent,
            intent_confidence=intent_confidence,
            emergency_triage_prob=emergency_triage_prob,
            pep_risk_score=pep_risk_score,
            latency_ms=latency_ms,
            raw_answers=raw_answers or {},
        )
        context = TriggerContextPayload(
            fallback_reason=fallback_reason,
            override_source=override_source,
            pre_breaker_category=pre_breaker_category,
            validator_violations=validator_violations or [],
        )

        item = ReviewItem(
            audit_event_id=audit_event_id,
            ledger_hash=ledger_hash,
            anonymized_patient_token=anon_token,
            trigger_type=trigger_type,
            scrubbed_input_text=scrubbed_text,
            model_checkpoint=model_checkpoint,
            model_decision=decision,
            trigger_context=context,
            review_status=ReviewStatus.PENDING,
        )

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO review_items (
                    review_id, audit_event_id, ledger_hash, anonymized_patient_token,
                    timestamp_utc, trigger_type, scrubbed_input_text, model_checkpoint,
                    model_decision_json, trigger_context_json, review_status,
                    clinician_annotation_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.review_id,
                    item.audit_event_id,
                    item.ledger_hash,
                    item.anonymized_patient_token,
                    item.timestamp_utc,
                    item.trigger_type.value,
                    item.scrubbed_input_text,
                    item.model_checkpoint,
                    item.model_decision.model_dump_json(),
                    item.trigger_context.model_dump_json(),
                    item.review_status.value,
                    None,
                    time.time(),
                ),
            )
            conn.commit()

        logger.info(
            "ReviewItem enqueued: id=%s, trigger=%s, anon_pt=%s",
            item.review_id,
            item.trigger_type.value,
            item.anonymized_patient_token,
        )
        return item

    def get_item(self, review_id: str) -> Optional[ReviewItem]:
        """Retrieves a single review item by ID."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM review_items WHERE review_id = ?", (review_id,)).fetchone()
            if not row:
                return None
            return self._row_to_item(row)

    def list_items(
        self,
        status: Optional[ReviewStatus] = None,
        trigger_type: Optional[TriggerType] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ReviewItem]:
        """Lists items filtered by status or trigger type."""
        query = "SELECT * FROM review_items WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND review_status = ?"
            params.append(status.value)
        if trigger_type:
            query += " AND trigger_type = ?"
            params.append(trigger_type.value)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_item(r) for r in rows]

    def record_annotation(
        self,
        *,
        review_id: str,
        reviewer_id: str,
        ground_truth_intent: str,
        ground_truth_emergency: bool,
        ground_truth_pep_risk: int,
        clinical_rationale: str,
        secret_key: bytes | None = None,
    ) -> ReviewItem:
        """Applies clinician ground-truth annotation with cryptographic audit signature."""
        item = self.get_item(review_id)
        if not item:
            raise KeyError(f"Review item {review_id} not found")

        annotated_at = datetime.now(timezone.utc).isoformat()
        # Compute signature: HMAC(secret, review_id + reviewer_id + intent + emg + rationale)
        signing_key = secret_key or self.scrubber.salt
        sig_payload = f"{review_id}|{reviewer_id}|{ground_truth_intent}|{ground_truth_emergency}|{clinical_rationale}|{annotated_at}"
        signature = hmac.new(signing_key, sig_payload.encode("utf-8"), hashlib.sha256).hexdigest()

        annotation = ClinicianAnnotation(
            reviewer_id=reviewer_id,
            ground_truth_intent=ground_truth_intent,
            ground_truth_emergency=ground_truth_emergency,
            ground_truth_pep_risk=ground_truth_pep_risk,
            clinical_rationale=clinical_rationale,
            annotated_at_utc=annotated_at,
            signature=signature,
        )

        with self._connect() as conn:
            conn.execute(
                """UPDATE review_items
                   SET review_status = ?, clinician_annotation_json = ?
                   WHERE review_id = ?""",
                (ReviewStatus.ANNOTATED.value, annotation.model_dump_json(), review_id),
            )
            conn.commit()

        item.review_status = ReviewStatus.ANNOTATED
        item.clinician_annotation = annotation
        logger.info("ReviewItem %s annotated by %s: ground_truth_intent=%s", review_id, reviewer_id, ground_truth_intent)
        return item

    def approve_for_training(self, review_id: str) -> ReviewItem:
        """Transitions an annotated review item to APPROVED_FOR_TRAINING."""
        item = self.get_item(review_id)
        if not item:
            raise KeyError(f"Review item {review_id} not found")
        if item.review_status != ReviewStatus.ANNOTATED or item.clinician_annotation is None:
            raise ValueError(f"Cannot approve unannotated review item {review_id}")

        with self._connect() as conn:
            conn.execute(
                "UPDATE review_items SET review_status = ? WHERE review_id = ?",
                (ReviewStatus.APPROVED_FOR_TRAINING.value, review_id),
            )
            conn.commit()

        item.review_status = ReviewStatus.APPROVED_FOR_TRAINING
        return item

    def export_training_dataset(
        self,
        output_path: str | Path,
        statuses: list[ReviewStatus] | None = None,
    ) -> dict[str, int]:
        """Exports approved review items to JSONL training corpus without PHI."""
        target_statuses = statuses or [ReviewStatus.APPROVED_FOR_TRAINING]
        status_strs = [s.value for s in target_statuses]
        placeholders = ",".join("?" for _ in status_strs)

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM review_items WHERE review_status IN ({placeholders}) ORDER BY created_at ASC",
                status_strs,
            ).fetchall()

        items = [self._row_to_item(r) for r in rows]
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        intent_counts: dict[str, int] = {}
        written_count = 0

        with open(out_file, "w", encoding="utf-8") as f:
            for item in items:
                if not item.clinician_annotation:
                    continue
                record = {
                    "text": item.scrubbed_input_text,
                    "expected_intent": item.clinician_annotation.ground_truth_intent,
                    "emergency_triage": item.clinician_annotation.ground_truth_emergency,
                    "pep_risk": item.clinician_annotation.ground_truth_pep_risk,
                    "metadata": {
                        "review_id": item.review_id,
                        "anonymized_patient_token": item.anonymized_patient_token,
                        "trigger_type": item.trigger_type.value,
                        "original_model_checkpoint": item.model_checkpoint,
                        "reviewer_id": item.clinician_annotation.reviewer_id,
                        "annotated_at": item.clinician_annotation.annotated_at_utc,
                    },
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                intent = item.clinician_annotation.ground_truth_intent
                intent_counts[intent] = intent_counts.get(intent, 0) + 1
                written_count += 1

        return {
            "total_exported": written_count,
            **intent_counts,
        }

    def get_stats(self) -> dict[str, Any]:
        """Provides queue depth and trigger breakdown."""
        with self._connect() as conn:
            total = conn.execute("SELECT count(*) FROM review_items").fetchone()[0]
            status_counts = dict(
                conn.execute("SELECT review_status, count(*) FROM review_items GROUP BY review_status").fetchall()
            )
            trigger_counts = dict(
                conn.execute("SELECT trigger_type, count(*) FROM review_items GROUP BY trigger_type").fetchall()
            )

        return {
            "total_items": total,
            "status_breakdown": status_counts,
            "trigger_breakdown": trigger_counts,
        }

    def _row_to_item(self, row: sqlite3.Row) -> ReviewItem:
        decision_data = json.loads(row["model_decision_json"])
        context_data = json.loads(row["trigger_context_json"])
        annotation_data = json.loads(row["clinician_annotation_json"]) if row["clinician_annotation_json"] else None

        return ReviewItem(
            review_id=row["review_id"],
            audit_event_id=row["audit_event_id"],
            ledger_hash=row["ledger_hash"],
            anonymized_patient_token=row["anonymized_patient_token"],
            timestamp_utc=row["timestamp_utc"],
            trigger_type=TriggerType(row["trigger_type"]),
            scrubbed_input_text=row["scrubbed_input_text"],
            model_checkpoint=row["model_checkpoint"],
            model_decision=ModelDecisionPayload(**decision_data),
            trigger_context=TriggerContextPayload(**context_data),
            review_status=ReviewStatus(row["review_status"]),
            clinician_annotation=ClinicianAnnotation(**annotation_data) if annotation_data else None,
        )
