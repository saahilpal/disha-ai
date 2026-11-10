CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS clinical_knowledge_base (
    chunk_id BIGSERIAL PRIMARY KEY,
    condition_tag VARCHAR(64) NOT NULL,
    trigger_terms TEXT NOT NULL CHECK (btrim(trigger_terms) <> ''),
    context_header TEXT NOT NULL DEFAULT '',
    guideline_content TEXT NOT NULL,
    required_remedy_tokens TEXT[] NOT NULL DEFAULT '{}',
    source_citation VARCHAR(256) NOT NULL CHECK (btrim(source_citation) <> ''),
    approval_status VARCHAR(16) NOT NULL DEFAULT 'draft'
        CHECK (approval_status IN ('draft', 'approved', 'rejected')),
    clinician_id VARCHAR(64),
    approved_at TIMESTAMPTZ,
    tsv_content tsvector GENERATED ALWAYS AS (
        to_tsvector('simple'::regconfig, trigger_terms || ' ' || context_header || ' ' || guideline_content)
    ) STORED,
    CHECK (btrim(guideline_content) <> ''),
    CHECK (cardinality(regexp_split_to_array(btrim(guideline_content), E'\\s+')) < 50),
    CHECK (approval_status <> 'approved' OR (clinician_id IS NOT NULL AND approved_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_clinical_tsv ON clinical_knowledge_base USING GIN(tsv_content);
CREATE INDEX IF NOT EXISTS idx_clinical_trgm ON clinical_knowledge_base USING GIN(trigger_terms gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_clinical_tsv_approved ON clinical_knowledge_base USING GIN(tsv_content) WHERE approval_status = 'approved';
CREATE INDEX IF NOT EXISTS idx_clinical_trgm_approved ON clinical_knowledge_base USING GIN(trigger_terms gin_trgm_ops) WHERE approval_status = 'approved';
CREATE INDEX IF NOT EXISTS idx_clinical_condition_approved ON clinical_knowledge_base(condition_tag) WHERE approval_status = 'approved';

CREATE TABLE IF NOT EXISTS patient_profiles (
    patient_id VARCHAR(64) PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(128) NOT NULL,
    name VARCHAR(128) NOT NULL,
    age INT,
    gender VARCHAR(32),
    height_cm NUMERIC,
    weight_kg NUMERIC,
    dietary_preference VARCHAR(64),
    health_goals TEXT[],
    language VARCHAR(32) DEFAULT 'hinglish',
    health_focuses TEXT[] DEFAULT '{}',
    health_focus_other TEXT DEFAULT '',
    health_conditions TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS patient_pep (
    patient_id VARCHAR(64) PRIMARY KEY,
    hypertension_stage VARCHAR(16),
    gym_clearance BOOLEAN NOT NULL DEFAULT FALSE,
    allowed_modalities TEXT[] NOT NULL DEFAULT '{}',
    restricted_modalities TEXT[] NOT NULL DEFAULT '{}',
    primary_focus VARCHAR(128) DEFAULT '',
    secondary_focuses TEXT[] DEFAULT '{}',
    user_reported_concerns TEXT DEFAULT '',
    diagnosed_conditions TEXT[] DEFAULT '{}',
    language VARCHAR(32) DEFAULT 'hinglish',
    dietary_preference VARCHAR(64),
    habits JSONB DEFAULT '{}'::jsonb NOT NULL,
    habits_version INT DEFAULT 1 NOT NULL,
    is_dirty BOOLEAN DEFAULT FALSE NOT NULL,
    habits_updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    clinician_verified_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- PEP Habits Scale Engine (Loop 2 Architecture)
-- ============================================================================

-- 1. Current-state habit slots with partial unique index & hysteresis tracking
CREATE TABLE IF NOT EXISTS habit_current_state (
    id BIGSERIAL PRIMARY KEY,
    patient_id VARCHAR(64) NOT NULL,
    slot_key VARCHAR(64) NOT NULL,
    value_norm TEXT NOT NULL,
    value_raw TEXT NOT NULL,
    raw_lang VARCHAR(16) NOT NULL DEFAULT 'hinglish',
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_confirmed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirm_count INT NOT NULL DEFAULT 1,
    confidence NUMERIC(4,3) NOT NULL DEFAULT 1.000,
    source VARCHAR(32) NOT NULL DEFAULT 'call',
    evidence_ref TEXT,
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMPTZ,
    supersedes BIGINT REFERENCES habit_current_state(id),
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_habit_current_active 
    ON habit_current_state (patient_id, slot_key) 
    WHERE valid_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_habit_current_patient_slot 
    ON habit_current_state (patient_id, slot_key);

-- View: patient_habits with explicit provenance mapping
CREATE OR REPLACE VIEW patient_habits AS
SELECT
    id,
    patient_id,
    slot_key,
    value_norm,
    value_raw,
    raw_lang,
    source,
    CASE
        WHEN source IN ('user_reported', 'chat', 'voice', 'call') THEN 'user_reported'
        ELSE source
    END AS provenance,
    first_seen_at,
    last_confirmed_at,
    confirm_count,
    confidence,
    evidence_ref,
    valid_from,
    valid_to,
    supersedes,
    version,
    created_at
FROM habit_current_state;

-- 2. Append-only habit observations partitioned by month with BRIN index
CREATE TABLE IF NOT EXISTS habit_observations (
    id BIGSERIAL,
    patient_id VARCHAR(64) NOT NULL,
    slot_key VARCHAR(64) NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    value NUMERIC(10,2),
    unit VARCHAR(32),
    source VARCHAR(32) DEFAULT 'call',
    evidence_ref TEXT,
    dedupe_key VARCHAR(128),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (id, observed_at)
) PARTITION BY RANGE (observed_at);

CREATE TABLE IF NOT EXISTS habit_observations_default 
    PARTITION OF habit_observations DEFAULT;

CREATE INDEX IF NOT EXISTS idx_habit_obs_brin 
    ON habit_observations USING BRIN(observed_at);
CREATE INDEX IF NOT EXISTS idx_habit_obs_pt_slot_time 
    ON habit_observations (patient_id, slot_key, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_habit_obs_dedupe 
    ON habit_observations (dedupe_key, observed_at);

-- 3. Incremental habit rollups (day/week/month)
CREATE TABLE IF NOT EXISTS habit_rollups (
    id BIGSERIAL PRIMARY KEY,
    patient_id VARCHAR(64) NOT NULL,
    slot_key VARCHAR(64) NOT NULL,
    period_type VARCHAR(16) NOT NULL CHECK (period_type IN ('day', 'week', 'month')),
    period_start DATE NOT NULL,
    count INT NOT NULL DEFAULT 0,
    min_val NUMERIC(10,2),
    max_val NUMERIC(10,2),
    mean_val NUMERIC(10,2),
    last_val NUMERIC(10,2),
    trend VARCHAR(32) NOT NULL DEFAULT 'stable',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(patient_id, slot_key, period_type, period_start)
);
CREATE INDEX IF NOT EXISTS idx_habit_rollups_lookup 
    ON habit_rollups (patient_id, slot_key, period_type, period_start DESC);

-- 4. Transient symptoms and commitments (episodes)
CREATE TABLE IF NOT EXISTS habit_episodes (
    id BIGSERIAL PRIMARY KEY,
    patient_id VARCHAR(64) NOT NULL,
    episode_type VARCHAR(64) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'resolved', 'expired')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    due_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    evidence_ref TEXT,
    clinician_verified_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_habit_episodes_pt_status 
    ON habit_episodes (patient_id, status);

-- Backward and forward compatibility view for clinical guideline retrieval
CREATE OR REPLACE VIEW clinical_guideline_chunks AS
SELECT * FROM clinical_knowledge_base;

CREATE TABLE IF NOT EXISTS patient_diet_schedules (
    schedule_id BIGSERIAL PRIMARY KEY,
    patient_id VARCHAR(64) NOT NULL,
    day_of_week VARCHAR(16) NOT NULL
        CHECK (day_of_week IN ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')),
    meal_type VARCHAR(16) NOT NULL CHECK (meal_type IN ('breakfast', 'lunch', 'dinner')),
    prescribed_items TEXT NOT NULL CHECK (btrim(prescribed_items) <> ''),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    approval_status VARCHAR(24) NOT NULL DEFAULT 'pending_review'
        CHECK (approval_status IN ('pending_review', 'approved', 'rejected')),
    UNIQUE(patient_id, day_of_week, meal_type)
);

CREATE TABLE IF NOT EXISTS patient_access_tokens (
    token_hash CHAR(64) PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    patient_id VARCHAR(64) NOT NULL CHECK (btrim(patient_id) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS idx_patient_access_tokens_patient_active
    ON patient_access_tokens(patient_id, expires_at) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS audit_claim_ledger (
    turn_id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    patient_id VARCHAR(64) NOT NULL,
    user_input TEXT NOT NULL,
    llm_output TEXT NOT NULL,
    breaker_status VARCHAR(32) NOT NULL,
    validator_status VARCHAR(32) NOT NULL,
    prev_hash VARCHAR(64) NOT NULL,
    current_hash VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_chain_head (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    current_hash VARCHAR(64) NOT NULL
);
INSERT INTO audit_chain_head(singleton, current_hash)
VALUES (TRUE, repeat('0', 64)) ON CONFLICT (singleton) DO NOTHING;

-- Persistent multi-turn conversation journal across sessions
CREATE TABLE IF NOT EXISTS patient_turn_journal (
    turn_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NOT NULL DEFAULT 'default',
    call_id VARCHAR(128),
    turn_index INT NOT NULL DEFAULT 0,
    speaker VARCHAR(16) NOT NULL CHECK (speaker IN ('user', 'assistant', 'patient', 'coach', 'system')),
    timestamp_utc TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(),
    raw_utterance TEXT NOT NULL CHECK (btrim(raw_utterance) <> ''),
    normalized_utterance TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE patient_turn_journal ADD COLUMN IF NOT EXISTS call_id VARCHAR(128);
CREATE INDEX IF NOT EXISTS idx_journal_patient_time 
    ON patient_turn_journal(patient_id, timestamp_utc DESC);
CREATE INDEX IF NOT EXISTS idx_journal_session_turn 
    ON patient_turn_journal(session_id, turn_index ASC);
CREATE INDEX IF NOT EXISTS idx_journal_call_turn 
    ON patient_turn_journal(call_id, turn_index ASC);

-- Updatable view for turn_journal
CREATE OR REPLACE VIEW turn_journal AS SELECT * FROM patient_turn_journal;

-- Structured temporal fact graph for patient lifestyle, disclosures, and habit facts
CREATE TABLE IF NOT EXISTS patient_temporal_facts (
    fact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id VARCHAR(64) NOT NULL,
    category VARCHAR(64) NOT NULL DEFAULT 'lifestyle',
    fact_key VARCHAR(64) NOT NULL,
    fact_value TEXT NOT NULL,
    source VARCHAR(16) NOT NULL DEFAULT 'unknown' CHECK (source IN ('chat', 'voice', 'unknown')),
    epistemic_status VARCHAR(24) NOT NULL DEFAULT 'active'
        CHECK (epistemic_status IN ('active', 'superseded', 'resolved', 'contradicted', 'flagged_review')),
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_facts_patient_key_active 
    ON patient_temporal_facts(patient_id, fact_key)
    WHERE epistemic_status = 'active';

-- Granular slot memory items
CREATE TABLE IF NOT EXISTS memory_items (
    item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id VARCHAR(64) NOT NULL,
    slot_key VARCHAR(64) NOT NULL,
    slot_value JSONB NOT NULL,
    category VARCHAR(64) NOT NULL DEFAULT 'lifestyle',
    source_authority VARCHAR(32) NOT NULL DEFAULT 'PATIENT_REPORTED'
        CHECK (source_authority IN ('PEP_DOCTOR', 'PATIENT_REPORTED', 'CLINICIAN')),
    epistemic_status VARCHAR(24) NOT NULL DEFAULT 'active'
        CHECK (epistemic_status IN ('active', 'superseded', 'resolved', 'contradicted', 'flagged_review')),
    sensitive_flag BOOLEAN NOT NULL DEFAULT FALSE,
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 1.000 CHECK (confidence >= 0.000 AND confidence <= 1.000),
    raw_quote TEXT NOT NULL DEFAULT '',
    language VARCHAR(32) NOT NULL DEFAULT 'hinglish',
    session_id VARCHAR(64) DEFAULT 'default',
    call_id VARCHAR(128),
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_memory_items_patient_key_active
    ON memory_items(patient_id, slot_key)
    WHERE epistemic_status = 'active';
CREATE INDEX IF NOT EXISTS idx_memory_items_patient_time
    ON memory_items(patient_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_items_call
    ON memory_items(call_id);

-- Persistent call session summaries
CREATE TABLE IF NOT EXISTS call_summaries (
    summary_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id VARCHAR(128) NOT NULL UNIQUE,
    session_id VARCHAR(64) NOT NULL DEFAULT 'default',
    patient_id VARCHAR(64) NOT NULL,
    start_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    end_time TIMESTAMPTZ,
    duration_seconds INT DEFAULT 0,
    summary_text TEXT NOT NULL DEFAULT '',
    action_items JSONB NOT NULL DEFAULT '[]'::jsonb,
    habits_disclosed JSONB NOT NULL DEFAULT '{}'::jsonb,
    contradictions_detected JSONB NOT NULL DEFAULT '[]'::jsonb,
    sentiment VARCHAR(32) DEFAULT 'neutral',
    language VARCHAR(32) DEFAULT 'hinglish',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_call_summaries_patient
    ON call_summaries(patient_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_call_summaries_session
    ON call_summaries(session_id);

-- Authoritative Knowledge Sources (Provenanced Registry)
CREATE TABLE IF NOT EXISTS knowledge_sources (
    id VARCHAR(64) PRIMARY KEY,
    name TEXT NOT NULL,
    license VARCHAR(128) NOT NULL,
    url TEXT,
    version VARCHAR(64) NOT NULL,
    ingest_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    language VARCHAR(32) NOT NULL DEFAULT 'en',
    domain VARCHAR(64) NOT NULL,
    trust_tier VARCHAR(16) NOT NULL CHECK (trust_tier IN ('tier_1', 'tier_2', 'tier_3'))
);
CREATE INDEX IF NOT EXISTS idx_ksources_domain ON knowledge_sources(domain);
CREATE INDEX IF NOT EXISTS idx_ksources_trust ON knowledge_sources(trust_tier);

-- Granular Knowledge Chunks with Strict Provenance Foreign Key
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id BIGSERIAL PRIMARY KEY,
    source_id VARCHAR(64) NOT NULL REFERENCES knowledge_sources(id) ON DELETE RESTRICT,
    domain VARCHAR(64) NOT NULL,
    condition_tags TEXT[] NOT NULL DEFAULT '{}',
    diet_tags TEXT[] NOT NULL DEFAULT '{}',
    language VARCHAR(32) NOT NULL DEFAULT 'hinglish',
    script VARCHAR(32) NOT NULL DEFAULT 'latin',
    content TEXT NOT NULL CHECK (btrim(content) <> ''),
    fts_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, content)) STORED,
    embedding REAL[] DEFAULT NULL,
    derived BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_kchunks_source ON knowledge_chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_kchunks_domain ON knowledge_chunks(domain);
CREATE INDEX IF NOT EXISTS idx_kchunks_fts ON knowledge_chunks USING GIN(fts_vector);
CREATE INDEX IF NOT EXISTS idx_kchunks_condition_tags ON knowledge_chunks USING GIN(condition_tags);
CREATE INDEX IF NOT EXISTS idx_kchunks_diet_tags ON knowledge_chunks USING GIN(diet_tags);

-- Commercial, Channel, Persona, and Clinical Clearance Product Facts
CREATE TABLE IF NOT EXISTS product_facts (
    fact_key VARCHAR(64) PRIMARY KEY,
    category VARCHAR(64) NOT NULL,
    title VARCHAR(128) NOT NULL,
    fact_value JSONB NOT NULL,
    description TEXT,
    owner VARCHAR(64) NOT NULL DEFAULT 'product_team',
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    verification_status VARCHAR(64) NOT NULL DEFAULT 'unknown',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_product_facts_category ON product_facts(category);

-- ============================================================================
-- Patient Onboarding Journey and Question Scheduler State
-- ============================================================================

CREATE TABLE IF NOT EXISTS patient_journey_state (
    patient_id VARCHAR(64) PRIMARY KEY,
    current_stage INT NOT NULL DEFAULT 1 CHECK (current_stage BETWEEN 1 AND 5),
    stage_status JSONB NOT NULL DEFAULT '{}'::jsonb,
    overall_status VARCHAR(32) NOT NULL DEFAULT 'in_progress' 
        CHECK (overall_status IN ('not_started', 'in_progress', 'completed', 'post_onboarding')),
    completed_fields TEXT[] NOT NULL DEFAULT '{}',
    missing_fields TEXT[] NOT NULL DEFAULT '{}',
    uncertain_fields TEXT[] NOT NULL DEFAULT '{}',
    conflicting_fields TEXT[] NOT NULL DEFAULT '{}',
    skipped_fields TEXT[] NOT NULL DEFAULT '{}',
    last_interaction_ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_interaction_channel VARCHAR(16) NOT NULL DEFAULT 'chat'
        CHECK (last_interaction_channel IN ('chat', 'voice')),
    last_completed_stage INT NOT NULL DEFAULT 0,
    journey_version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pjs_status ON patient_journey_state(overall_status);
CREATE INDEX IF NOT EXISTS idx_pjs_stage ON patient_journey_state(current_stage);

CREATE TABLE IF NOT EXISTS journey_question_history (
    id BIGSERIAL PRIMARY KEY,
    patient_id VARCHAR(64) NOT NULL,
    question_id VARCHAR(64) NOT NULL,
    stage INT NOT NULL CHECK (stage BETWEEN 1 AND 5),
    target_field VARCHAR(64) NOT NULL,
    channel VARCHAR(16) NOT NULL DEFAULT 'chat'
        CHECK (channel IN ('chat', 'voice')),
    status VARCHAR(32) NOT NULL DEFAULT 'asked'
        CHECK (status IN ('asked', 'answered', 'skipped', 'clarification_requested', 'superseded')),
    question_text TEXT NOT NULL,
    asked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    answered_at TIMESTAMPTZ,
    response_text TEXT,
    extracted_value JSONB,
    attempts INT NOT NULL DEFAULT 1,
    skip_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jqh_patient_qid ON journey_question_history(patient_id, question_id);
CREATE INDEX IF NOT EXISTS idx_jqh_patient_field ON journey_question_history(patient_id, target_field, status);
CREATE INDEX IF NOT EXISTS idx_jqh_patient_stage ON journey_question_history(patient_id, stage);

-- ============================================================================
-- Unified Conversations, Messages & Dialogue State Ledger
-- ============================================================================

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(64) NOT NULL REFERENCES patient_profiles(patient_id) ON DELETE CASCADE,
    channel VARCHAR(16) NOT NULL DEFAULT 'chat',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_active_user_conversation 
ON conversations (user_id) 
WHERE (archived = FALSE);

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL REFERENCES patient_profiles(patient_id) ON DELETE CASCADE,
    seq INT NOT NULL,
    role VARCHAR(16) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    channel VARCHAR(16) NOT NULL CHECK (channel IN ('chat', 'voice')),
    content TEXT NOT NULL DEFAULT '',
    status VARCHAR(16) NOT NULL CHECK (status IN ('streaming', 'complete', 'aborted')),
    client_msg_id VARCHAR(128),
    meta JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT uq_conversation_seq UNIQUE (conversation_id, seq),
    CONSTRAINT uq_conversation_client_msg UNIQUE (conversation_id, client_msg_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_user_conv ON messages (user_id, conversation_id, seq ASC);

CREATE TABLE IF NOT EXISTS dialogue_state (
    conversation_id UUID PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL REFERENCES patient_profiles(patient_id) ON DELETE CASCADE,
    state JSONB NOT NULL DEFAULT '{}'::jsonb,
    version INT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
