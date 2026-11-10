"""Database Migration and Setup for PEP Habits Scale Architecture (Loop 2).

Adds:
- patient_pep habits JSONB snapshot + versioning
- habit_current_state (partial unique index, hysteresis tracking)
- habit_observations (partitioned by month, BRIN index)
- habit_rollups (incremental daily/weekly/monthly stats)
- habit_episodes (transient symptoms and commitments)
"""

import asyncio
import os

import asyncpg

DEFAULT_PG_URL = os.getenv("DATABASE_URL", "postgresql://disha:disha_secure_pass_123@127.0.0.1:5432/disha")


async def apply_pep_habits_schema(pg_url: str = DEFAULT_PG_URL) -> None:
    conn = await asyncpg.connect(pg_url)
    try:
        # 1. Update patient_pep
        await conn.execute("""
            ALTER TABLE patient_pep
            ADD COLUMN IF NOT EXISTS habits JSONB DEFAULT '{}'::jsonb NOT NULL,
            ADD COLUMN IF NOT EXISTS habits_version INT DEFAULT 1 NOT NULL,
            ADD COLUMN IF NOT EXISTS is_dirty BOOLEAN DEFAULT FALSE NOT NULL,
            ADD COLUMN IF NOT EXISTS habits_updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            ADD COLUMN IF NOT EXISTS clinician_verified_at TIMESTAMPTZ;
        """)

        # 2. habit_current_state
        await conn.execute("""
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
        """)

        # 3. habit_observations (partitioned)
        await conn.execute("""
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
        """)

        # 4. habit_rollups
        await conn.execute("""
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
        """)

        # 5. habit_episodes
        await conn.execute("""
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
                evidence_ref TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_habit_episodes_pt_status 
                ON habit_episodes (patient_id, status);
        """)

        print("Successfully applied PEP Habits scale schema to PostgreSQL.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(apply_pep_habits_schema())
