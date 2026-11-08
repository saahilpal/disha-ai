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
    dietary_preference VARCHAR(64) DEFAULT 'Vegetarian',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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
    turn_index INT NOT NULL DEFAULT 0,
    speaker VARCHAR(16) NOT NULL CHECK (speaker IN ('user', 'assistant', 'patient', 'coach', 'system')),
    timestamp_utc TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(),
    raw_utterance TEXT NOT NULL CHECK (btrim(raw_utterance) <> ''),
    normalized_utterance TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_journal_patient_time 
    ON patient_turn_journal(patient_id, timestamp_utc DESC);
CREATE INDEX IF NOT EXISTS idx_journal_session_turn 
    ON patient_turn_journal(session_id, turn_index ASC);

-- Structured temporal fact graph for patient lifestyle, disclosures, and habit facts
CREATE TABLE IF NOT EXISTS patient_temporal_facts (
    fact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id VARCHAR(64) NOT NULL,
    category VARCHAR(64) NOT NULL DEFAULT 'lifestyle',
    fact_key VARCHAR(64) NOT NULL,
    fact_value TEXT NOT NULL,
    epistemic_status VARCHAR(24) NOT NULL DEFAULT 'active'
        CHECK (epistemic_status IN ('active', 'superseded', 'resolved', 'contradicted')),
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_facts_patient_key_active 
    ON patient_temporal_facts(patient_id, fact_key)
    WHERE epistemic_status = 'active';
