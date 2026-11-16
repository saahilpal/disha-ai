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

## 3. Items Recommended for Clinician Review
- **Pregnancy & Acute Abdomen Red-Flag Symptoms**: Sourced from NHS 111 clinical pathways and AIIMS Emergency Medicine Triage protocols (accessed November 2026). Clinician review recommended for boundary weights.
- **Crisis Helpline Numbers**: Tele-MANAS (`14416` / `1800-891-4416`) and National KIRAN Mental Health Helpline (`1800-599-0019`) sourced from official Ministry of Health and Family Welfare (MoHFW) directories (accessed November 2026).
- **Acute Pain Herbal Deflection**: Botanical remedy checks in `SentenceValidator` deflect home remedies (turmeric/haldi, ashwagandha) during acute abdominal complaints. Clinician review recommended.
- **Transient Symptom Expiry Defaults**: Ephemeral complaints (bloating, headache, acidity, fever) expire after 48 hours in `habit_episodes`. Clinician review recommended to validate whether acute fever requires shorter 24-hour reassessment.
- **Sodium Restriction Threshold in Hypertension**: Automated flagging quarantines user reports claiming high sodium / namkeen intake when clinical protocol denotes stage 2 hypertension. Clinician review recommended for precise dietary sodium thresholds.
- **Physical Activity Clearance Modalities**: Clinician-verified restrictions distinguish walking from heavy deadlifts / Valsalva exertion; boundary list requires periodic clinical review against cardiovascular rehabilitation guidelines.

---

## 4. Architectural & Schema Debt (Identified in PEP Audit)
- **Dual Table Fact Redundancy**:
  - `diagnosed_conditions` is maintained in both `patient_pep.diagnosed_conditions` and `patient_profiles.health_conditions`.
  - `dietary_preference` is duplicated across `patient_pep.dietary_preference`, `patient_profiles.dietary_preference`, and `habit_current_state` (under slot `meal_preferences`).
  - `primary_health_goal` is stored in both `patient_pep.primary_focus` and `patient_profiles.health_goals`.
  - Resolution: Maintain `patient_pep_slots` and `patient_pep` as the authoritative source of clinical truth, deprecating raw text fields on `patient_profiles`.
- **Dangling Destination Mapping**:
  - `JOURNEY_FIELDS["personalisation_readiness"]` maps to `FieldDestination.PEP_CORE` column `is_personalized`, which is not present in PostgreSQL `patient_pep` schema.
  - Resolution: Store readiness directly in `patient_journey_state.overall_status` or add an explicit boolean column.
- **Habit Hysteresis Staging Gap**:
  - In `commit_habit_slot`, when an established habit (`confirm_count >= 2`) receives a conflicting mention without an explicit permanence cue ("ab se", "from now on"), the engine flags `status="pending_confirmation"` without storing the candidate new value in a persistent staging row. Subsequent mentions cannot confirm the unstaged value.
  - Resolution: Use `patient_pep_slots` with `verification_status="unconfirmed"` as the staging buffer.

---

## Recently Resolved Issues (Verified in Test Suite)

- **Journey Acceptance 502 Bad Gateway**: Resolved by configuring `DISHA_HTTP_URL` to the direct backend endpoint and aligning Docker bridge network aliases (`dishaai_disha_internal`).
- **Replay Journal Turn XML Idempotency Discrepancy**: Resolved by ordering habit consolidation prior to rehydration in `test_acceptance_resilience.py`.
- **Gastrointestinal Transliteration Retrieval Gap**: Resolved by updating `ingest_open_datasets.py` to index colloquial Hinglish trigger terms (`pet`, `gas`, `bloating`) under approved clinical home remedies.
- **Recommendation Grounding Repair Count Alignment**: Resolved by aligning mock LLM completion responses to comply with F6 follow-up constraints in `test_recommendation_grounding.py`.
