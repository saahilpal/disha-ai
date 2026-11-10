"""Apply conversations, messages, and dialogue_state schema additions idempotently."""

import asyncio
import logging
import asyncpg
from disha_core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("apply_conversations_schema")

SQL = """
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
"""

async def main():
    import os
    settings = get_settings()
    db_url = os.getenv("DATABASE_URL") or getattr(settings, "database_url", None)
    if not db_url or "nitrousoxide" in db_url:
        db_url = "postgresql://disha:disha_secure_pass_123@127.0.0.1:5432/disha"
    logger.info("Connecting to database: %s", db_url)
    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute(SQL)
        logger.info("Successfully applied conversations, messages, and dialogue_state schema.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
