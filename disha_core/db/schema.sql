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

CREATE TABLE IF NOT EXISTS patient_pep (
    patient_id VARCHAR(64) PRIMARY KEY,
    hypertension_stage VARCHAR(16),
    gym_clearance BOOLEAN NOT NULL DEFAULT FALSE,
    allowed_modalities TEXT[] NOT NULL DEFAULT '{}',
    restricted_modalities TEXT[] NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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
