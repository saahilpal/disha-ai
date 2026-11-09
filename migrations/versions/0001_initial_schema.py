"""Initial Disha AI Core PostgreSQL schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-11-07 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Trigram extension for fuzzy clinical symptom matching
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # 2. Clinical Knowledge Base
    op.execute("""
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
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_clinical_tsv ON clinical_knowledge_base USING GIN(tsv_content);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_clinical_trgm ON clinical_knowledge_base USING GIN(trigger_terms gin_trgm_ops);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_clinical_tsv_approved ON clinical_knowledge_base USING GIN(tsv_content) WHERE approval_status = 'approved';")
    op.execute("CREATE INDEX IF NOT EXISTS idx_clinical_trgm_approved ON clinical_knowledge_base USING GIN(trigger_terms gin_trgm_ops) WHERE approval_status = 'approved';")

    # 3. Patient Profiles
    op.execute("""
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
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """)

    # 4. Patient PEP (Personalized Exercise Prescription)
    op.execute("""
    CREATE TABLE IF NOT EXISTS patient_pep (
        patient_id VARCHAR(64) PRIMARY KEY,
        hypertension_stage VARCHAR(16),
        gym_clearance BOOLEAN NOT NULL DEFAULT FALSE,
        allowed_modalities TEXT[] NOT NULL DEFAULT '{}',
        restricted_modalities TEXT[] NOT NULL DEFAULT '{}',
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """)

    # 5. Patient Diet Schedules
    op.execute("""
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
    """)

    # 6. Patient Access Tokens
    op.execute("""
    CREATE TABLE IF NOT EXISTS patient_access_tokens (
        token_hash CHAR(64) PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
        patient_id VARCHAR(64) NOT NULL CHECK (btrim(patient_id) <> ''),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        expires_at TIMESTAMPTZ NOT NULL,
        revoked_at TIMESTAMPTZ,
        CHECK (expires_at > created_at)
    );
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_patient_access_tokens_patient_active
        ON patient_access_tokens(patient_id, expires_at) WHERE revoked_at IS NULL;
    """)

    # 7. Audit Claim Ledger
    op.execute("""
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
    """)

    # 8. Audit Chain Head
    op.execute("""
    CREATE TABLE IF NOT EXISTS audit_chain_head (
        singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
        current_hash VARCHAR(64) NOT NULL
    );
    """)
    op.execute("""
    INSERT INTO audit_chain_head(singleton, current_hash)
    VALUES (TRUE, repeat('0', 64)) ON CONFLICT (singleton) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_chain_head CASCADE;")
    op.execute("DROP TABLE IF EXISTS audit_claim_ledger CASCADE;")
    op.execute("DROP TABLE IF EXISTS patient_access_tokens CASCADE;")
    op.execute("DROP TABLE IF EXISTS patient_diet_schedules CASCADE;")
    op.execute("DROP TABLE IF EXISTS patient_pep CASCADE;")
    op.execute("DROP TABLE IF EXISTS patient_profiles CASCADE;")
    op.execute("DROP TABLE IF EXISTS clinical_knowledge_base CASCADE;")
