"""Add persistent patient turn journal, temporal facts, and guideline view

Revision ID: 0002_memory_and_pep
Revises: 0001_initial_schema
Create Date: 2026-11-08 22:30:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002_memory_and_pep"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add dietary_preference column to patient_pep
    op.execute("""
    ALTER TABLE patient_pep ADD COLUMN IF NOT EXISTS dietary_preference VARCHAR(64) DEFAULT 'Vegetarian';
    """)

    # 2. Add clinical_guideline_chunks view for RAG retrieval
    op.execute("""
    CREATE OR REPLACE VIEW clinical_guideline_chunks AS
    SELECT * FROM clinical_knowledge_base;
    """)

    # 3. Persistent patient turn journal and turn_journal view
    op.execute("""
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
    CREATE INDEX IF NOT EXISTS idx_journal_patient_time 
        ON patient_turn_journal(patient_id, timestamp_utc DESC);
    CREATE INDEX IF NOT EXISTS idx_journal_session_turn 
        ON patient_turn_journal(session_id, turn_index ASC);
    CREATE INDEX IF NOT EXISTS idx_journal_call_turn 
        ON patient_turn_journal(call_id, turn_index ASC);
    CREATE OR REPLACE VIEW turn_journal AS SELECT * FROM patient_turn_journal;
    """)

    # 4. Structured temporal fact graph
    op.execute("""
    CREATE TABLE IF NOT EXISTS patient_temporal_facts (
        fact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        patient_id VARCHAR(64) NOT NULL,
        category VARCHAR(64) NOT NULL DEFAULT 'lifestyle',
        fact_key VARCHAR(64) NOT NULL,
        fact_value TEXT NOT NULL,
        epistemic_status VARCHAR(24) NOT NULL DEFAULT 'active'
            CHECK (epistemic_status IN ('active', 'superseded', 'resolved', 'contradicted', 'flagged_review')),
        valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        valid_to TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_facts_patient_key_active 
        ON patient_temporal_facts(patient_id, fact_key)
        WHERE epistemic_status = 'active';
    """)

    # 5. Granular slot memory items
    op.execute("""
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
    """)

    # 6. Persistent call session summaries
    op.execute("""
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
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS call_summaries CASCADE;")
    op.execute("DROP TABLE IF EXISTS memory_items CASCADE;")
    op.execute("DROP TABLE IF EXISTS patient_temporal_facts CASCADE;")
    op.execute("DROP VIEW IF EXISTS turn_journal CASCADE;")
    op.execute("DROP TABLE IF EXISTS patient_turn_journal CASCADE;")
    op.execute("DROP VIEW IF EXISTS clinical_guideline_chunks CASCADE;")
    op.execute("ALTER TABLE patient_pep DROP COLUMN IF EXISTS dietary_preference;")
