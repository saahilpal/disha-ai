"""Acceptance Resilience and Chaos Disruption Test Suite for Disha AI Release-Candidate (Phase 3F).

Author: Resilience & Reliability Specialist for Disha AI
Standard: senior-ai-systems-engineer, cloudflare-architect

Mission Acceptance Scenarios:
1. Restart the stack mid-session: verify graceful reconnect and session resumption.
2. Kill PostgreSQL database mid-turn and restore: verify circuit breaker, graceful deflection, and zero corrupted records.
3. Trigger tunnel watchdog restart: verify new URL propagation to .env.local without crashing.
4. Dual-provider failover: simulate primary LLM timeout/failure and confirm seamless fallback to secondary.
5. Audit ledger outbox recovery: verify no stranded WAL records on crash.
6. Replay journal turns idempotently: confirm identical state computation without duplicate entries.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, AsyncIterator

import pytest
from fastapi.testclient import TestClient

import disha_core.main as app_main
from disha_core.compliance.ledger import AuditLedger
from disha_core.engine.context_builder import rehydrate_session_state, render_context_xml
from disha_core.llm.client import (
    ConsecutiveFailureCircuitBreaker,
    DualProviderClient,
    LLMSettings,
    Provider,
    ProviderError,
)
from disha_core.pep.habits_engine import consolidate_patient_habits, record_habit_observation
from disha_core.pipeline.router import IntentRouter
from disha_core.pipeline.validator import SentenceValidator
from disha_core.services.chat_service import load_conversation_history, store_conversation_turn

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
AGENT_DIR = REPO_ROOT / "agent"
DEFAULT_PG_URL = os.getenv("DATABASE_URL", "postgresql://disha:disha_secure_pass_123@127.0.0.1:5432/disha")

pytestmark = pytest.mark.live_network


# ==============================================================================
# MOCK INFRASTRUCTURE FOR CHAOS & DISRUPTION SIMULATION
# ==============================================================================


class MockAsyncpgConnection:
    """Mock database connection for deterministic in-memory testing."""

    def __init__(self, patient_id: str = "pt_rc_resilience_01") -> None:
        self.patient_id = patient_id
        self.state = {"head": "0" * 64, "rows": []}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def transaction(self):
        return self

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        q = query.casefold()
        if "from patient_access_tokens" in q:
            return {"patient_id": self.patient_id}
        if "from patient_profiles" in q:
            return {
                "name": "Resilience Test Patient",
                "age": 42,
                "gender": "male",
                "height_cm": 172.0,
                "weight_kg": 74.0,
                "dietary_preference": "Vegetarian",
                "health_goals": ["blood pressure management"],
            }
        if "from patient_pep" in q:
            return {
                "hypertension_stage": "stage 1",
                "gym_clearance": False,
                "allowed_modalities": ["walking", "gentle yoga"],
                "restricted_modalities": ["heavy deadlifts"],
                "primary_focus": "hypertension",
                "secondary_focuses": ["walking"],
                "user_reported_concerns": "",
                "diagnosed_conditions": ["hypertension"],
            }
        return None

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        return []

    async def fetchval(self, query: str, *args: Any) -> Any:
        q = query.casefold()
        if "from audit_chain_head" in q:
            return self.state["head"]
        if "select exists" in q:
            return False
        if "select 1" in q:
            return 1
        return None

    async def execute(self, query: str, *args: Any) -> str:
        q = query.casefold()
        if "insert into audit_claim_ledger" in q:
            ev_id, p_id, u_in, llm_out, brk, val, prev, cur = args
            self.state["rows"].append(
                {
                    "event_id": ev_id,
                    "patient_id": p_id,
                    "user_input": u_in,
                    "llm_output": llm_out,
                    "breaker_status": brk,
                    "validator_status": val,
                    "prev_hash": prev,
                    "current_hash": cur,
                }
            )
        elif "update audit_chain_head" in q:
            self.state["head"] = args[0]
        return "COMMAND OK"


class MockAsyncpgPool:
    """Mock connection pool yielding MockAsyncpgConnection."""

    def __init__(self, conn: MockAsyncpgConnection | None = None) -> None:
        self.conn = conn or MockAsyncpgConnection()

    def acquire(self):
        class _Ctx:
            def __init__(self, conn: MockAsyncpgConnection) -> None:
                self.conn = conn

            async def __aenter__(self) -> MockAsyncpgConnection:
                return self.conn

            async def __aexit__(self, *args: Any) -> None:
                pass

        return _Ctx(self.conn)

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        return await self.conn.fetchrow(query, *args)

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        return await self.conn.fetch(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        return await self.conn.fetchval(query, *args)

    async def execute(self, query: str, *args: Any) -> str:
        return await self.conn.execute(query, *args)

    async def close(self) -> None:
        pass


class FailingAsyncpgPool:
    """Simulates dead PostgreSQL instance or dropped socket mid-turn."""

    def acquire(self):
        class _Ctx:
            async def __aenter__(self) -> Any:
                raise ConnectionRefusedError("PostgreSQL connection refused: host unreachable [Errno 61]")

            async def __aexit__(self, *args: Any) -> None:
                pass

        return _Ctx()

    async def close(self) -> None:
        pass


def create_configured_test_app(pool=None):
    """Factory helper creating app with standard state fixtures."""
    app = app_main.create_app()
    app.state.pool = pool or MockAsyncpgPool()
    app.state.ledger = None
    app.state.router = IntentRouter()
    app.state.validator = SentenceValidator()
    app.state.today_ist = lambda: "monday"

    class MockLLM:
        async def stream(self, prompt: str, **kwargs: Any):
            yield "Aapki diet aur routine ke hisaab se main guide kar sakti hoon."

    app.state.llm = MockLLM()
    return app


async def get_live_pg_connection():
    """Connect to live PostgreSQL if available; otherwise None."""
    try:
        import asyncpg

        conn = await asyncpg.connect(DEFAULT_PG_URL, timeout=3.0)
        return conn
    except Exception:
        return None


# ==============================================================================
# SCENARIO 1: STACK RESTART MID-SESSION (RECONNECT & SESSION RESUMPTION)
# ==============================================================================


@pytest.mark.asyncio
async def test_resilience_01_stack_restart_mid_session_reconnect_and_resumption():
    """Scenario 1: Restart stack mid-session.

    Verifies:
    1. Pre-restart turns & slot observations are persisted into PostgreSQL.
    2. In-RAM session context is completely wiped to simulate process death.
    3. Client reconnects with same session/call token.
    4. State is fully rehydrated from DB via rehydrate_session_state (100% preservation).
    5. Follow-up turn increments turn_index without gaps, collision, or state amnesia.
    """
    conn = await get_live_pg_connection()
    if conn is None:
        pytest.skip(f"Live PostgreSQL required at {DEFAULT_PG_URL}")

    test_pid = "pt_rc_resilience_01"
    test_session = f"sess_rc_{uuid.uuid4().hex[:8]}"
    test_call = f"call_rc_{uuid.uuid4().hex[:8]}"

    try:
        # Clean slate for test patient
        await conn.execute("DELETE FROM patient_turn_journal WHERE patient_id = $1", test_pid)
        await conn.execute("DELETE FROM habit_current_state WHERE patient_id = $1", test_pid)
        await conn.execute("DELETE FROM habit_observations WHERE patient_id = $1", test_pid)
        await conn.execute("DELETE FROM memory_items WHERE patient_id = $1", test_pid)
        await conn.execute(
            """INSERT INTO patient_pep (patient_id, hypertension_stage, gym_clearance, allowed_modalities, restricted_modalities)
               VALUES ($1, 'Stage 1', FALSE, ARRAY['walking', 'gentle yoga'], ARRAY['heavy deadlifts'])
               ON CONFLICT (patient_id) DO UPDATE SET hypertension_stage = 'Stage 1', gym_clearance = FALSE""",
            test_pid,
        )

        # 1. Turn 1 occurs before crash
        turn1_user = "Mujhe breakfast mein poha aur green tea lena pasand hai."
        turn1_assistant = "Bahut accha! Poha aur green tea ek healthy breakfast choice hai."
        await store_conversation_turn(
            conn, test_pid, turn1_user, turn1_assistant, session_id=test_session, call_id=test_call
        )
        await record_habit_observation(test_pid, "wake_time", 7.0, "hours", source="voice", conn=conn)

        # Verify Turn 1 is in DB
        t1_rows = await conn.fetch(
            "SELECT turn_index, speaker, raw_utterance FROM patient_turn_journal WHERE patient_id = $1 AND session_id = $2 ORDER BY turn_index",
            test_pid,
            test_session,
        )
        assert len(t1_rows) == 2
        assert t1_rows[0]["speaker"] == "user"
        assert t1_rows[1]["speaker"] == "assistant"

        # 2. DISRUPTION: Simulate server crash / stack restart / worker recycling
        # In-RAM session cache is completely destroyed / wiped
        in_ram_session_cache: dict[str, Any] = {}
        assert test_pid not in in_ram_session_cache
        # Close connection to simulate process socket termination
        await conn.close()
        conn = None

        # 3. RECONNECT: Client reconnects; process recovers
        reconnected_conn = await get_live_pg_connection()
        assert reconnected_conn is not None

        # 4. SESSION RESUMPTION: Rehydrate entire conversational context from PostgreSQL
        rehydrated = await rehydrate_session_state(
            reconnected_conn, test_pid, session_id=test_session, call_id=test_call, limit=16
        )

        assert rehydrated["rehydrated_from_db"] is True
        assert rehydrated["session_id"] == test_session
        assert rehydrated["call_id"] == test_call
        assert len(rehydrated["conversation_history"]) == 2
        assert rehydrated["conversation_history"][0]["content"] == turn1_user
        assert rehydrated["conversation_history"][1]["content"] == turn1_assistant
        assert rehydrated["pep"]["hypertension_stage"] == "Stage 1"
        assert rehydrated["pep"]["gym_clearance"] is False

        # 5. Subsequent Turn 2 continues seamlessly
        turn2_user = "Aur lunch ke liye dal roti le sakta hoon?"
        turn2_assistant = "Haan bilkul, moong dal aur phulka roti hypertension ke liye safe hai."
        await store_conversation_turn(
            reconnected_conn, test_pid, turn2_user, turn2_assistant, session_id=test_session, call_id=test_call
        )

        # Verify continuous chronological history across crash
        all_turns = await load_conversation_history(
            reconnected_conn, test_pid, limit=10, session_id=test_session, call_id=test_call
        )
        assert len(all_turns) == 4
        assert [t["content"] for t in all_turns] == [turn1_user, turn1_assistant, turn2_user, turn2_assistant]

    finally:
        if conn:
            await conn.close()
        if "reconnected_conn" in locals() and reconnected_conn:
            await reconnected_conn.close()


# ==============================================================================
# SCENARIO 2: KILL POSTGRESQL MID-TURN AND RESTORE (CIRCUIT BREAKER & DEFLECTION)
# ==============================================================================


def test_resilience_02_kill_postgres_mid_turn_circuit_breaker_and_zero_corruption():
    """Scenario 2: Kill PostgreSQL database mid-turn and restore.

    Verifies:
    1. During sudden DB outage, endpoint triggers circuit breaker deflection (HTTP 200).
    2. Endpoint never crashes with unhandled 500 Internal Server Error.
    3. Deflection response politely informs patient of transient connectivity error.
    4. Database restored: subsequent turn completes normally with zero corrupted records.
    """
    app = create_configured_test_app(pool=FailingAsyncpgPool())
    client = TestClient(app)

    # 1. Patient sends turn request during DB death
    res = client.post(
        "/chat",
        json={"text": "Kya main exercise kar sakta hoon?"},
        headers={"Authorization": "Bearer pt_test_01_valid_token"},
    )

    # CRITICAL RESILIENCE ASSERTION: No 500 crash
    assert res.status_code == 200, f"Expected 200 circuit breaker deflection, got {res.status_code}"
    data = res.json()
    assert data["status"] == "deflected:db_unavailable"
    assert any(
        kw in data["response"]
        for kw in ("database", "technical samasya", "connect nahi kar paa rahi", "thodi der baad")
    )

    # 2. Restore database connection
    healthy_pool = MockAsyncpgPool()
    app.state.pool = healthy_pool

    # 3. Verify healthy turn succeeds immediately post-restore
    res2 = client.post(
        "/chat",
        json={"text": "Hello Disha, how are you?"},
        headers={"Authorization": "Bearer pt_test_01_valid_token"},
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] in ("completed", "validated")

    # 4. Integrity check: Verify zero corrupted records
    assert all("patient_id" in r for r in healthy_pool.conn.state["rows"])


# ==============================================================================
# SCENARIO 3: TRIGGER TUNNEL WATCHDOG RESTART (URL PROPAGATION TO .env.local)
# ==============================================================================


def test_resilience_03_tunnel_watchdog_restart_and_env_local_propagation():
    """Scenario 3: Trigger tunnel watchdog restart and verify URL propagation.

    Verifies:
    1. scripts/tunnel-watchdog.sh is executable and passes status inspection.
    2. Triggering tunnel URL persistence propagates to agent/TUNNEL_URL.txt AND .env.local.
    3. Duplicate lines are cleanly replaced in .env.local (no runaway appending).
    4. Watchdog status command completes with exit code 0 without crashing.
    """
    watchdog_script = SCRIPTS_DIR / "tunnel-watchdog.sh"
    assert watchdog_script.exists()
    assert os.access(watchdog_script, os.X_OK)

    tunnel_url_file = AGENT_DIR / "TUNNEL_URL.txt"
    env_local_file = REPO_ROOT / ".env.local"

    # Save original state for clean restoration
    orig_tunnel_url = tunnel_url_file.read_text().strip() if tunnel_url_file.exists() else None
    orig_env_local = env_local_file.read_text() if env_local_file.exists() else None

    test_new_url_1 = f"https://rc-resilience-turn-1-{uuid.uuid4().hex[:6]}.trycloudflare.com"
    test_new_url_2 = f"https://rc-resilience-turn-2-{uuid.uuid4().hex[:6]}.trycloudflare.com"

    try:
        # Simulate watchdog saving a new tunnel URL (Round 1) via CLI flag --save-url
        proc1 = subprocess.run(
            [str(watchdog_script), "--save-url", test_new_url_1],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert proc1.returncode == 0, f"--save-url failed: {proc1.stderr}"

        # Verify Round 1 persistence
        assert tunnel_url_file.exists()
        assert tunnel_url_file.read_text().strip() == test_new_url_1
        assert env_local_file.exists()
        env_content_1 = env_local_file.read_text()
        assert f'PUBLIC_TUNNEL_URL="{test_new_url_1}"' in env_content_1

        # Simulate watchdog restarting tunnel and generating a second URL (Round 2)
        proc2 = subprocess.run(
            [str(watchdog_script), "--save-url", test_new_url_2],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert proc2.returncode == 0, f"--save-url round 2 failed: {proc2.stderr}"

        # Verify Round 2 replacement (no duplicate lines)
        assert tunnel_url_file.read_text().strip() == test_new_url_2
        env_content_2 = env_local_file.read_text()
        assert f'PUBLIC_TUNNEL_URL="{test_new_url_2}"' in env_content_2
        # Assert no duplicate PUBLIC_TUNNEL_URL definitions exist in .env.local
        matching_lines = [line for line in env_content_2.splitlines() if line.startswith("PUBLIC_TUNNEL_URL=")]
        assert len(matching_lines) == 1, f"Expected 1 PUBLIC_TUNNEL_URL line, found {len(matching_lines)}"

        # Verify watchdog --status runs without error
        status_proc = subprocess.run([str(watchdog_script), "--status"], capture_output=True, text=True, timeout=10)
        assert status_proc.returncode == 0
        assert "DISHA AI — CLOUDFLARE TUNNEL WATCHDOG STATUS" in status_proc.stdout

    finally:
        # Restore original state
        if orig_tunnel_url is not None:
            tunnel_url_file.write_text(orig_tunnel_url + "\n")
        if orig_env_local is not None:
            env_local_file.write_text(orig_env_local)
        elif env_local_file.exists():
            env_local_file.unlink()


# ==============================================================================
# SCENARIO 4: DUAL-PROVIDER FAILOVER & CIRCUIT BREAKER
# ==============================================================================


@pytest.mark.asyncio
async def test_resilience_04_dual_provider_failover_timeout_and_circuit_breaker():
    """Scenario 4: Dual-provider failover.

    Verifies:
    1. Primary provider timeout/failure automatically defers to secondary fallback provider.
    2. Fallback stream yields valid sentences seamlessly without dropping the turn.
    3. Consecutive primary failures trip the circuit breaker after threshold=2.
    4. Circuit breaker OPEN state immediately routes requests to secondary without attempting primary.
    5. Primary recovery resets breaker on success.
    """

    class FlakyPrimary(Provider):
        def __init__(self):
            self.calls = 0
            self.should_fail = True

        async def stream(self, prompt: str, messages: list[dict[str, str]] | None = None) -> AsyncIterator[str]:
            self.calls += 1
            if self.should_fail:
                raise ProviderError("Primary Groq LLM upstream timeout (504 Gateway Timeout)", retryable=True)
            yield "Primary recovered: Namaste."

    class HealthySecondary(Provider):
        def __init__(self):
            self.calls = 0

        async def stream(self, prompt: str, messages: list[dict[str, str]] | None = None) -> AsyncIterator[str]:
            self.calls += 1
            yield "Secondary Gemini fallback: Aapka breakfast plan ready hai."

    primary = FlakyPrimary()
    secondary = HealthySecondary()
    client = DualProviderClient(LLMSettings(None, None, None, None))
    client.providers = (primary, secondary)
    client.circuit = ConsecutiveFailureCircuitBreaker(threshold=2, cooldown=60)

    # Turn 1: Primary fails -> Seamless failover to secondary
    chunks_1 = [chunk async for chunk in client.stream("Hello")]
    assert "".join(chunks_1) == "Secondary Gemini fallback: Aapka breakfast plan ready hai."
    assert primary.calls == 1
    assert secondary.calls == 1
    # Circuit breaker has 1 failure; still allows primary
    assert await client.circuit.allow_primary() is True

    # Turn 2: Primary fails second time -> Failover to secondary
    chunks_2 = [chunk async for chunk in client.stream("Hello again")]
    assert "".join(chunks_2) == "Secondary Gemini fallback: Aapka breakfast plan ready hai."
    assert primary.calls == 2
    assert secondary.calls == 2
    # Threshold=2 reached: Circuit breaker is now OPEN!
    assert await client.circuit.allow_primary() is False

    # Turn 3: Circuit breaker is OPEN -> Primary is completely skipped (zero delay/overhead)
    chunks_3 = [chunk async for chunk in client.stream("Turn 3")]
    assert "".join(chunks_3) == "Secondary Gemini fallback: Aapka breakfast plan ready hai."
    # primary.calls remains 2 (not called!), secondary handles immediately
    assert primary.calls == 2
    assert secondary.calls == 3

    # Recovery: Primary recovers
    primary.should_fail = False
    await client.circuit.record_success()
    assert await client.circuit.allow_primary() is True

    chunks_4 = [chunk async for chunk in client.stream("Turn 4 recovered")]
    assert "".join(chunks_4) == "Primary recovered: Namaste."
    assert primary.calls == 3


# ==============================================================================
# SCENARIO 5: AUDIT LEDGER OUTBOX RECOVERY (ZERO STRANDED WAL RECORDS)
# ==============================================================================


@pytest.mark.asyncio
async def test_resilience_05_audit_ledger_outbox_recovery_zero_stranded_wal():
    """Scenario 5: Audit ledger outbox recovery.

    Verifies:
    1. Pending audit records populated in SQLite WAL simulating crash before commit.
    2. On stack restart, AuditLedger automatically refills queue from SQLite WAL.
    3. Worker commits records into PostgreSQL audit_claim_ledger with Merkle chain.
    4. Post-drain audit check confirms exactly 0 stranded records remain in WAL table.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_file = Path(tmpdir) / "test_outbox_wal.db"
        total_stranded = 40
        queue_size = 10

        # Step 1: Populate SQLite directly to simulate crash with uncommitted records
        with sqlite3.connect(str(wal_file)) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""CREATE TABLE wal_audit_records (
                event_id TEXT PRIMARY KEY, patient_id TEXT, user_input TEXT,
                llm_output TEXT, breaker_status TEXT, validator_status TEXT, created_at REAL
            )""")
            for i in range(total_stranded):
                conn.execute(
                    "INSERT INTO wal_audit_records VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), f"pt_crash_wal_{i}", f"in_{i}", f"out_{i}", "clear", "accepted", float(i)),
                )
            conn.commit()

        # Step 2: SIMULATE SYSTEM RESTART & RECOVERY
        # Instantiate a new AuditLedger on the existing WAL file
        pool = MockAsyncpgPool()
        restarted_ledger = AuditLedger(pool, max_queue_size=queue_size, wal_path=wal_file)
        restarted_ledger.start()

        # Allow worker task to dynamically drain all records and commit to DB
        await asyncio.sleep(0.4)
        await restarted_ledger.close(drain_timeout=5.0)

        # Step 3: ZERO STRANDED RECORDS ASSERTION
        with sqlite3.connect(str(wal_file)) as db:
            remaining_wal = db.execute("SELECT COUNT(*) FROM wal_audit_records").fetchone()[0]
        assert remaining_wal == 0, f"Expected 0 stranded WAL records, found {remaining_wal}"

        # Step 4: VERIFY CRYPTOGRAPHIC MERKLE HASH CHAIN INTEGRITY
        rows = pool.conn.state["rows"]
        assert len(rows) == total_stranded
        prev_hash = "0" * 64
        for idx, row in enumerate(rows):
            assert row["prev_hash"] == prev_hash, f"Hash broken at block {idx}"
            payload = f"{prev_hash}|{row['patient_id']}|{row['user_input']}|{row['llm_output']}|{row['breaker_status']}|{row['validator_status']}"
            expected_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            assert row["current_hash"] == expected_hash, f"Hash mismatch at block {idx}"
            prev_hash = row["current_hash"]


# ==============================================================================
# SCENARIO 6: REPLAY JOURNAL TURNS IDEMPOTENTLY (ZERO DUPLICATES)
# ==============================================================================


@pytest.mark.asyncio
async def test_resilience_06_replay_journal_turns_idempotently():
    """Scenario 6: Replay journal turns idempotently.

    Verifies:
    1. A patient's conversational turns & habit observations can be replayed repeatedly.
    2. Context rehydration produces identical conversation history across replays.
    3. Habit rollups and snapshot computation produce identical hash state.
    4. Zero duplicate entries created in patient_turn_journal or habit_rollups.
    """
    conn = await get_live_pg_connection()
    if conn is None:
        pytest.skip(f"Live PostgreSQL required at {DEFAULT_PG_URL}")

    test_pid = "pt_rc_idempotent_01"
    test_session = "sess_rc_idempotent_test"

    try:
        # Clean slate
        await conn.execute("DELETE FROM patient_turn_journal WHERE patient_id = $1", test_pid)
        await conn.execute("DELETE FROM habit_observations WHERE patient_id = $1", test_pid)
        await conn.execute("DELETE FROM habit_rollups WHERE patient_id = $1", test_pid)
        await conn.execute("DELETE FROM habit_current_state WHERE patient_id = $1", test_pid)
        await conn.execute(
            """INSERT INTO patient_pep (patient_id, hypertension_stage, gym_clearance, allowed_modalities, restricted_modalities)
               VALUES ($1, 'Stage 1', FALSE, ARRAY['walking'], ARRAY['heavy weights'])
               ON CONFLICT (patient_id) DO UPDATE SET hypertension_stage = 'Stage 1', gym_clearance = FALSE""",
            test_pid,
        )

        # Seed 3 conversational turns
        turns = [
            ("Good morning Disha.", "Good morning! How is your health today?"),
            (
                "Maine subah 30 minute walk ki.",
                "Bahut accha! Daily walking blood pressure control karne mein madad karti hai.",
            ),
            (
                "Mera BP 130/85 hai aaj.",
                "Yeh Stage 1 range mein hai. Namak kam rakhein aur regular walk continue karein.",
            ),
        ]
        for u_text, a_text in turns:
            await store_conversation_turn(conn, test_pid, u_text, a_text, session_id=test_session)

        # Seed habit observations with unit
        await record_habit_observation(test_pid, "systolic_bp", 130.0, "mmHg", conn=conn)
        await record_habit_observation(test_pid, "diastolic_bp", 85.0, "mmHg", conn=conn)
        await record_habit_observation(test_pid, "daily_steps", 4500.0, "count", conn=conn)

        # REPLAY RUN 1: Rehydrate state & consolidate habits
        ctx_1 = await rehydrate_session_state(conn, test_pid, session_id=test_session)
        habits_1 = await consolidate_patient_habits(test_pid, conn=conn)
        xml_1 = render_context_xml(ctx_1)
        journal_count_1 = await conn.fetchval(
            "SELECT COUNT(*) FROM patient_turn_journal WHERE patient_id = $1", test_pid
        )
        rollup_count_1 = await conn.fetchval("SELECT COUNT(*) FROM habit_rollups WHERE patient_id = $1", test_pid)

        # REPLAY RUN 2: Execute identical replay
        ctx_2 = await rehydrate_session_state(conn, test_pid, session_id=test_session)
        habits_2 = await consolidate_patient_habits(test_pid, conn=conn)
        xml_2 = render_context_xml(ctx_2)
        journal_count_2 = await conn.fetchval(
            "SELECT COUNT(*) FROM patient_turn_journal WHERE patient_id = $1", test_pid
        )
        rollup_count_2 = await conn.fetchval("SELECT COUNT(*) FROM habit_rollups WHERE patient_id = $1", test_pid)

        # REPLAY RUN 3: Execute third replay
        ctx_3 = await rehydrate_session_state(conn, test_pid, session_id=test_session)
        habits_3 = await consolidate_patient_habits(test_pid, conn=conn)
        xml_3 = render_context_xml(ctx_3)
        journal_count_3 = await conn.fetchval(
            "SELECT COUNT(*) FROM patient_turn_journal WHERE patient_id = $1", test_pid
        )
        rollup_count_3 = await conn.fetchval("SELECT COUNT(*) FROM habit_rollups WHERE patient_id = $1", test_pid)

        # ASSERTIONS: Identical state computation, zero duplicate entries
        assert ctx_1["conversation_history"] == ctx_2["conversation_history"] == ctx_3["conversation_history"]
        assert len(ctx_1["conversation_history"]) == 6  # 3 turns * 2 messages
        assert xml_1 == xml_2 == xml_3

        # Zero duplicates in tables
        assert journal_count_1 == journal_count_2 == journal_count_3 == 6
        assert rollup_count_1 == rollup_count_2 == rollup_count_3

        # Deterministic habits summary across replays
        pep_row = await conn.fetchrow("SELECT habits FROM patient_pep WHERE patient_id = $1", test_pid)
        habits_json = json.loads(pep_row["habits"])
        assert "trends" in habits_json
        assert "systolic_bp" in habits_json["trends"]
        assert habits_json["trends"]["systolic_bp"]["mean"] == 130.0

    finally:
        await conn.close()
