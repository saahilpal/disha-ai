"""Align the migrated database with the schema used by the live application.

Revision ID: 0005_runtime_schema_alignment
Revises: 0004_approved_condition_tag_index
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005_runtime_schema_alignment"
down_revision: Union[str, None] = "0004_approved_condition_tag_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE patient_profiles ADD COLUMN IF NOT EXISTS language VARCHAR(32) DEFAULT 'hinglish';
    ALTER TABLE patient_profiles ADD COLUMN IF NOT EXISTS health_focuses TEXT[] DEFAULT '{}';
    ALTER TABLE patient_profiles ADD COLUMN IF NOT EXISTS health_focus_other TEXT DEFAULT '';
    ALTER TABLE patient_profiles ADD COLUMN IF NOT EXISTS health_conditions TEXT[] DEFAULT '{}';

    ALTER TABLE patient_pep ADD COLUMN IF NOT EXISTS primary_focus VARCHAR(128) DEFAULT '';
    ALTER TABLE patient_pep ADD COLUMN IF NOT EXISTS secondary_focuses TEXT[] DEFAULT '{}';
    ALTER TABLE patient_pep ADD COLUMN IF NOT EXISTS user_reported_concerns TEXT DEFAULT '';
    ALTER TABLE patient_pep ADD COLUMN IF NOT EXISTS diagnosed_conditions TEXT[] DEFAULT '{}';
    ALTER TABLE patient_pep ADD COLUMN IF NOT EXISTS language VARCHAR(32) DEFAULT 'hinglish';
    ALTER TABLE patient_pep ADD COLUMN IF NOT EXISTS habits JSONB NOT NULL DEFAULT '{}'::jsonb;
    ALTER TABLE patient_pep ADD COLUMN IF NOT EXISTS habits_version INT NOT NULL DEFAULT 1;
    ALTER TABLE patient_pep ADD COLUMN IF NOT EXISTS is_dirty BOOLEAN NOT NULL DEFAULT FALSE;
    ALTER TABLE patient_pep ADD COLUMN IF NOT EXISTS habits_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    ALTER TABLE patient_pep ADD COLUMN IF NOT EXISTS clinician_verified_at TIMESTAMPTZ;

    ALTER TABLE patient_diet_schedules ADD COLUMN IF NOT EXISTS approval_status VARCHAR(24) NOT NULL DEFAULT 'pending_review';
    ALTER TABLE patient_temporal_facts ADD COLUMN IF NOT EXISTS source VARCHAR(16) NOT NULL DEFAULT 'unknown';
    """)
    op.execute("""
    DO $$ BEGIN
        ALTER TABLE patient_diet_schedules ADD CONSTRAINT patient_diet_schedules_approval_status_check
            CHECK (approval_status IN ('pending_review', 'approved', 'rejected'));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    DO $$ BEGIN
        ALTER TABLE patient_temporal_facts ADD CONSTRAINT patient_temporal_facts_source_check
            CHECK (source IN ('chat', 'voice', 'unknown'));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS habit_current_state (
        id BIGSERIAL PRIMARY KEY, patient_id VARCHAR(64) NOT NULL, slot_key VARCHAR(64) NOT NULL,
        value_norm TEXT NOT NULL, value_raw TEXT NOT NULL, raw_lang VARCHAR(16) NOT NULL DEFAULT 'hinglish',
        first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), last_confirmed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        confirm_count INT NOT NULL DEFAULT 1, confidence NUMERIC(4,3) NOT NULL DEFAULT 1.000,
        source VARCHAR(32) NOT NULL DEFAULT 'call', evidence_ref TEXT, valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        valid_to TIMESTAMPTZ, supersedes BIGINT REFERENCES habit_current_state(id), version INT NOT NULL DEFAULT 1,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE UNIQUE INDEX IF NOT EXISTS uq_habit_current_active ON habit_current_state(patient_id, slot_key) WHERE valid_to IS NULL;
    CREATE INDEX IF NOT EXISTS idx_habit_current_patient_slot ON habit_current_state(patient_id, slot_key);

    CREATE TABLE IF NOT EXISTS habit_observations (
        id BIGSERIAL, patient_id VARCHAR(64) NOT NULL, slot_key VARCHAR(64) NOT NULL,
        observed_at TIMESTAMPTZ NOT NULL, value NUMERIC(10,2), unit VARCHAR(32), source VARCHAR(32) DEFAULT 'call',
        evidence_ref TEXT, dedupe_key VARCHAR(128), created_at TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (id, observed_at)
    ) PARTITION BY RANGE (observed_at);
    CREATE TABLE IF NOT EXISTS habit_observations_default PARTITION OF habit_observations DEFAULT;
    CREATE INDEX IF NOT EXISTS idx_habit_obs_brin ON habit_observations USING BRIN(observed_at);
    CREATE INDEX IF NOT EXISTS idx_habit_obs_pt_slot_time ON habit_observations(patient_id, slot_key, observed_at DESC);
    CREATE INDEX IF NOT EXISTS idx_habit_obs_dedupe ON habit_observations(dedupe_key, observed_at);

    CREATE TABLE IF NOT EXISTS habit_rollups (
        id BIGSERIAL PRIMARY KEY, patient_id VARCHAR(64) NOT NULL, slot_key VARCHAR(64) NOT NULL,
        period_type VARCHAR(16) NOT NULL CHECK (period_type IN ('day', 'week', 'month')), period_start DATE NOT NULL,
        count INT NOT NULL DEFAULT 0, min_val NUMERIC(10,2), max_val NUMERIC(10,2), mean_val NUMERIC(10,2),
        last_val NUMERIC(10,2), trend VARCHAR(32) NOT NULL DEFAULT 'stable', created_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(patient_id, slot_key, period_type, period_start)
    );
    CREATE INDEX IF NOT EXISTS idx_habit_rollups_lookup ON habit_rollups(patient_id, slot_key, period_type, period_start DESC);

    CREATE TABLE IF NOT EXISTS habit_episodes (
        id BIGSERIAL PRIMARY KEY, patient_id VARCHAR(64) NOT NULL, episode_type VARCHAR(64) NOT NULL,
        description TEXT NOT NULL, status VARCHAR(32) NOT NULL DEFAULT 'active'
            CHECK (status IN ('active', 'resolved', 'expired')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), due_at TIMESTAMPTZ, expires_at TIMESTAMPTZ,
        resolved_at TIMESTAMPTZ, evidence_ref TEXT, clinician_verified_at TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_habit_episodes_pt_status ON habit_episodes(patient_id, status);

    CREATE TABLE IF NOT EXISTS patient_journey_state (
        patient_id VARCHAR(64) PRIMARY KEY, current_stage INT NOT NULL DEFAULT 1 CHECK (current_stage BETWEEN 1 AND 5),
        stage_status JSONB NOT NULL DEFAULT '{}'::jsonb, overall_status VARCHAR(32) NOT NULL DEFAULT 'in_progress'
            CHECK (overall_status IN ('not_started', 'in_progress', 'completed', 'post_onboarding')),
        completed_fields TEXT[] NOT NULL DEFAULT '{}', missing_fields TEXT[] NOT NULL DEFAULT '{}',
        uncertain_fields TEXT[] NOT NULL DEFAULT '{}', conflicting_fields TEXT[] NOT NULL DEFAULT '{}',
        skipped_fields TEXT[] NOT NULL DEFAULT '{}', last_interaction_ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_interaction_channel VARCHAR(16) NOT NULL DEFAULT 'chat' CHECK (last_interaction_channel IN ('chat', 'voice')),
        last_completed_stage INT NOT NULL DEFAULT 0, journey_version INT NOT NULL DEFAULT 1,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_pjs_status ON patient_journey_state(overall_status);
    CREATE INDEX IF NOT EXISTS idx_pjs_stage ON patient_journey_state(current_stage);

    CREATE TABLE IF NOT EXISTS journey_question_history (
        id BIGSERIAL PRIMARY KEY, patient_id VARCHAR(64) NOT NULL, question_id VARCHAR(64) NOT NULL,
        stage INT NOT NULL CHECK (stage BETWEEN 1 AND 5), target_field VARCHAR(64) NOT NULL,
        channel VARCHAR(16) NOT NULL DEFAULT 'chat' CHECK (channel IN ('chat', 'voice')),
        status VARCHAR(32) NOT NULL DEFAULT 'asked'
            CHECK (status IN ('asked', 'answered', 'skipped', 'clarification_requested', 'superseded')),
        question_text TEXT NOT NULL, asked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), answered_at TIMESTAMPTZ,
        response_text TEXT, extracted_value JSONB, attempts INT NOT NULL DEFAULT 1, skip_reason TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_jqh_patient_qid ON journey_question_history(patient_id, question_id);
    CREATE INDEX IF NOT EXISTS idx_jqh_patient_field ON journey_question_history(patient_id, target_field, status);
    CREATE INDEX IF NOT EXISTS idx_jqh_patient_stage ON journey_question_history(patient_id, stage);
    """)


def downgrade() -> None:
    raise RuntimeError(
        "0005 is additive and may contain patient data. Roll back by restoring the pre-migration database backup."
    )
