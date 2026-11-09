"""Database Migration for Patient Onboarding Journey and Question Scheduler.

Adds:
- patient_journey_state: persistent state machine across chat and voice.
- journey_question_history: tracks asked/answered questions, attempts, channels, deduplication.
"""

from __future__ import annotations

import asyncio
import os

import asyncpg

DEFAULT_PG_URL = os.getenv("DATABASE_URL", "postgresql://disha:disha_secure_pass_123@127.0.0.1:5432/disha")


async def apply_journey_schema(pg_url: str = DEFAULT_PG_URL) -> None:
    conn = await asyncpg.connect(pg_url)
    try:
        # 1. patient_journey_state
        await conn.execute("""
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
        """)

        # 2. journey_question_history
        await conn.execute("""
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
        """)

        print("Successfully applied patient journey and scheduler schema to PostgreSQL.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(apply_journey_schema())
