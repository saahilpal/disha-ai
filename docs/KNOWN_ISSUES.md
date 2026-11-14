# Known Issues and Deferred Technical Debt (KNOWN_ISSUES)

This document catalogs known architectural defects, test limitations, and deferred migrations identified during the repository audit.

---

## 1. Alembic Version Column String Truncation
- **Severity**: P1
- **Location**: `migrations/versions/0004_approved_condition_tag_index.py` and PostgreSQL `alembic_version` table.
- **Description**: Standard Alembic `alembic_version` tables define `version_num VARCHAR(32)`. Revision ID `0004_approved_condition_tag_index` contains 33 characters. Running `alembic upgrade head` throws `psycopg2.errors.StringDataRightTruncation: value too long for type character varying(32)`.
- **Reproduction**:
  ```bash
  alembic upgrade head
  ```
- **Why Deferred**: Bypassed safely in test and production setup by applying schema scripts directly (`apply_conversations_schema.py`, `apply_journey_schema.py`, `apply_pep_habits_schema.py`). Altering the revision hash requires a coordinated migration reset across production environments.

---

## 2. Telephony Tunnel Ephemeral Verification
- **Severity**: P3
- **Location**: `scripts/tunnel-watchdog.sh`, `scripts/verify-telephony-live.sh`
- **Description**: Verification of live telephony WebSocket endpoints requires a running Cloudflare Tunnel daemon and active microphone permission. Offline test environments skip live carrier checks.
- **Remediation**: Offline tests verify the deterministic speech engine, RMS silence detection, and VAD audio processing directly without external network dependency.

---

## Recently Resolved Issues (Verified in Test Suite)

- **Journey Acceptance 502 Bad Gateway**: Resolved by configuring `DISHA_HTTP_URL` to the direct backend endpoint and aligning Docker bridge network aliases (`dishaai_disha_internal`).
- **Replay Journal Turn XML Idempotency Discrepancy**: Resolved by ordering habit consolidation prior to rehydration in `test_acceptance_resilience.py`.
- **Gastrointestinal Transliteration Retrieval Gap**: Resolved by updating `ingest_open_datasets.py` to index colloquial Hinglish trigger terms (`pet`, `gas`, `bloating`) under approved clinical home remedies.
- **Recommendation Grounding Repair Count Alignment**: Resolved by aligning mock LLM completion responses to comply with F6 follow-up constraints in `test_recommendation_grounding.py`.
