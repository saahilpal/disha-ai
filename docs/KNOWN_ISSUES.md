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

---

## 5. Free-Tier Cloud Hosting & Operational Constraints

1. **Render Free-Tier Idle Sleep & Cold Start**:
   - Web services on Render's free tier sleep automatically after 15 minutes without active incoming requests.
   - Waking a sleeping instance incurs a 30 to 50 second cold start delay.
   - Render's Terms of Service strictly prohibit automated external cron/bot keep-alive pings.
   - Resolution: The Vercel frontend embeds `checkBackendWarmup()`, displaying a non-blocking amber warmup indicator (`#warmup-banner`) with retry polling on cold page load.

2. **Supabase Direct Host IPv6 & Transaction Pooler Configuration**:
   - Supabase direct database connection hosts (`db.<ref>.supabase.co:5432`) resolve only via IPv6 on modern clusters. Free Render compute environments operate on IPv4-only networks.
   - Resolution: Application connects exclusively through Supavisor IPv4 Pooler (`aws-0-<region>.pooler.supabase.com:6543`).
   - Transaction poolers do not support prepared statement caches across multiplexed connections; `PG_STATEMENT_CACHE_SIZE=0` is required and enforced in `disha_core/adapters/db.py`.

3. **Supabase Inactivity Pausing**:
   - Supabase projects on the free plan pause automatically after 7 consecutive days of inactivity. Unpausing requires opening the Supabase dashboard.

4. **Synthetic Demo Privacy Scope**:
   - Because cloud model providers on free tiers (e.g., Google AI Studio) may use submitted inputs for service improvement unless covered by enterprise agreements, the app displays a mandatory disclaimer banner: `"Demo: Synthetic data only. Do not enter real medical details."` Real patient identifiers are prohibited on the demo instance.

- **Habit Hysteresis Staging Gap**:
  - In `commit_habit_slot`, when an established habit (`confirm_count >= 2`) receives a conflicting mention without an explicit permanence cue ("ab se", "from now on"), the engine flags `status="pending_confirmation"` without storing the candidate new value in a persistent staging row. Subsequent mentions cannot confirm the unstaged value.
  - Resolution: Use `patient_pep_slots` with `verification_status="unconfirmed"` as the staging buffer.

---

## Recently Resolved Issues (Verified in Test Suite & Production)

- **Robotic Customer Support Fillers & Follow-Up Question Suppression (BUG-008)**: Resolved in current hotfix. System prompt and behavior rules upgraded from rigid procedural lecturing to perceptive, emotionally intelligent questioning. Classified answers to assistant inquiries (including short replies "no", "nahi", "okay", "don't know") as valid conversational turns rather than suppressing follow-ups. Cleared pending journey question upon resolution/uncertainty to prevent deadlock in question scheduler.
- **Chat Hydration TDZ & Blocking Guard (BUG-006)**: Resolved in commit `38d29b4`. Uncaught ReferenceError in `navigate` accessing `views` before initialization blocked page boot and chat hydration on reload. Hoisted `views` as dynamic getters, moved initial session restore after router setup, and added 404/403 recovery and auto-retry to `dispatchTurn`.
- **Voice Stutter, Mechanical Fallback & False Barge-In (BUG-007)**: Resolved in commit `38d29b4`. Replaced micro-chunk `decodeAudioData` onended chaining with Web Audio timeline clock scheduling `source.start(scheduledTime)`. Removed premature 1500ms `speechSynthesis` fallback watchdog. Increased VAD silence hangover to 750ms and raised barge-in echo rejection threshold. Added Safari/iOS MP4 audio container detection in `transcribe_groq`.
- **Journey Acceptance 502 Bad Gateway**: Resolved by configuring `DISHA_HTTP_URL` to the direct backend endpoint and aligning Docker bridge network aliases (`dishaai_disha_internal`).
- **Replay Journal Turn XML Idempotency Discrepancy**: Resolved by ordering habit consolidation prior to rehydration in `test_acceptance_resilience.py`.
- **Gastrointestinal Transliteration Retrieval Gap**: Resolved by updating `ingest_open_datasets.py` to index colloquial Hinglish trigger terms (`pet`, `gas`, `bloating`) under approved clinical home remedies.
- **Recommendation Grounding Repair Count Alignment**: Resolved by aligning mock LLM completion responses to comply with F6 follow-up constraints in `test_recommendation_grounding.py`.
