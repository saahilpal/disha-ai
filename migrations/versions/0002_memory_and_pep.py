"""Add persistent patient turn journal, temporal facts, and guideline view

Revision ID: 0002_memory_and_pep
Revises: 0001_initial_schema
Create Date: 2026-11-08 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


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

    # 3. Persistent patient turn journal
    op.execute("""
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
            CHECK (epistemic_status IN ('active', 'superseded', 'resolved', 'contradicted')),
        valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        valid_to TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_facts_patient_key_active 
        ON patient_temporal_facts(patient_id, fact_key)
        WHERE epistemic_status = 'active';
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS patient_temporal_facts CASCADE;")
    op.execute("DROP TABLE IF EXISTS patient_turn_journal CASCADE;")
    op.execute("DROP VIEW IF EXISTS clinical_guideline_chunks CASCADE;")
    op.execute("ALTER TABLE patient_pep DROP COLUMN IF EXISTS dietary_preference;")
