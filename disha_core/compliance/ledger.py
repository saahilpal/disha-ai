from __future__ import annotations

import asyncio
import atexit
import hashlib
import logging
import os
import signal
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuditRecord:
    patient_id: str
    user_input: str
    llm_output: str
    breaker_status: str
    validator_status: str
    event_id: uuid.UUID = field(default_factory=uuid.uuid4)

    @property
    def status(self) -> str:
        return f"{self.breaker_status}|{self.validator_status}"


def current_hash(prev_hash: str, record: AuditRecord) -> str:
    payload = (
        f"{prev_hash}|{record.patient_id}|{record.user_input}|"
        f"{record.llm_output}|{record.status}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LedgerPool(Protocol):
    def acquire(self) -> Any: ...


def _resolve_wal_path(wal_path: str | Path | None) -> Path | None:
    if wal_path is None:
        env_path = os.getenv("AUDIT_WAL_PATH")
        if env_path:
            return Path(env_path)
        wal_path = "audit_wal.db"
    path = Path(wal_path)
    if path.is_absolute():
        return path
    try:
        cwd = Path.cwd()
        if os.access(cwd, os.W_OK):
            return cwd / path
    except Exception:
        pass
    package_root = Path(__file__).resolve().parent.parent
    if os.access(package_root, os.W_OK):
        return package_root / path
    home = Path.home()
    if os.access(home, os.W_OK):
        return home / path
    return path


class AuditLedger:
    """Volatile single-process queue; PostgreSQL serializes hash-chain writes.

    `enqueue` is non-blocking and returns False on overflow, so callers must surface
    that audit event as unsaved. A process crash can also lose queued, uncommitted rows.
    """

    def __init__(
        self,
        pool: LedgerPool,
        *,
        max_queue_size: int = 2048,
        wal_path: str | Path | None = "audit_wal.db",
    ) -> None:
        if max_queue_size < 1:
            raise ValueError("max_queue_size must be positive")
        self.pool = pool
        self.queue: asyncio.Queue[AuditRecord] = asyncio.Queue(maxsize=max_queue_size)
        self._worker: asyncio.Task[None] | None = None
        self.dropped_count = 0
        self.wal_path = _resolve_wal_path(wal_path)
        self._loop: asyncio.AbstractEventLoop | None = None
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        if self.wal_path:
            self._init_wal()
        self._register_shutdown_hooks()

    def _register_shutdown_hooks(self) -> None:
        atexit.register(self.flush_to_wal)
        try:
            prev_handler = signal.getsignal(signal.SIGTERM)

            def _sigterm_handler(signum: int, frame: Any) -> None:
                self.flush_to_wal()
                if callable(prev_handler) and prev_handler not in (signal.SIG_DFL, signal.SIG_IGN):
                    prev_handler(signum, frame)
                elif prev_handler == signal.SIG_DFL:
                    signal.signal(signal.SIGTERM, signal.SIG_DFL)
                    os.kill(os.getpid(), signal.SIGTERM)

            signal.signal(signal.SIGTERM, _sigterm_handler)
        except (ValueError, AttributeError):
            pass

    def _init_wal(self) -> None:
        if not self.wal_path:
            return
        try:
            with sqlite3.connect(str(self.wal_path), timeout=5.0) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS wal_audit_records (
                        event_id TEXT PRIMARY KEY,
                        patient_id TEXT,
                        user_input TEXT,
                        llm_output TEXT,
                        breaker_status TEXT,
                        validator_status TEXT,
                        created_at REAL
                    )"""
                )
                conn.commit()
                # Recover uncommitted records from previous crash/restart
                cursor = conn.execute(
                    """SELECT event_id, patient_id, user_input, llm_output, breaker_status, validator_status
                       FROM wal_audit_records
                       ORDER BY created_at ASC"""
                )
                for row in cursor.fetchall():
                    ev_id = uuid.UUID(row[0]) if row[0] else uuid.uuid4()
                    rec = AuditRecord(
                        patient_id=row[1],
                        user_input=row[2],
                        llm_output=row[3],
                        breaker_status=row[4],
                        validator_status=row[5],
                        event_id=ev_id,
                    )
                    try:
                        self.queue.put_nowait(rec)
                    except asyncio.QueueFull:
                        break
        except Exception as exc:
            logger.warning("WAL initialization error: %s", exc)

    def _write_wal(self, record: AuditRecord) -> None:
        if not self.wal_path:
            return
        try:
            with sqlite3.connect(str(self.wal_path), timeout=5.0) as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO wal_audit_records
                       (event_id, patient_id, user_input, llm_output, breaker_status, validator_status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(record.event_id),
                        record.patient_id,
                        record.user_input,
                        record.llm_output,
                        record.breaker_status,
                        record.validator_status,
                        time.time(),
                    ),
                )
                conn.commit()
        except Exception as exc:
            logger.warning("WAL write error: %s", exc)

    def flush_to_wal(self) -> None:
        """Persist all uncommitted records in the queue to the WAL."""
        if not self.wal_path:
            return
        try:
            if not self.wal_path.parent.exists():
                return
            pending = list(self.queue._queue)
            if not pending:
                return
            with sqlite3.connect(str(self.wal_path), timeout=5.0) as conn:
                conn.executemany(
                    """INSERT OR IGNORE INTO wal_audit_records
                       (event_id, patient_id, user_input, llm_output, breaker_status, validator_status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    [
                        (
                            str(rec.event_id),
                            rec.patient_id,
                            rec.user_input,
                            rec.llm_output,
                            rec.breaker_status,
                            rec.validator_status,
                            time.time(),
                        )
                        for rec in pending
                    ],
                )
                conn.commit()
        except Exception as exc:
            logger.warning("WAL flush error: %s", exc)

    def _remove_wal(self, event_id: uuid.UUID) -> None:
        if not self.wal_path:
            return
        try:
            with sqlite3.connect(str(self.wal_path), timeout=5.0) as conn:
                conn.execute("DELETE FROM wal_audit_records WHERE event_id = ?", (str(event_id),))
                conn.commit()
        except Exception as exc:
            logger.warning("WAL remove error: %s", exc)

    def start(self) -> None:
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run(), name="disha-audit-ledger")

    def enqueue(self, record: AuditRecord) -> bool:
        """Queue an event without waiting; False means it was not recorded in-memory."""
        self.start()
        # Persist to WAL immediately so record is never lost
        self._write_wal(record)
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if current_loop is not None and current_loop == self._loop:
            try:
                self.queue.put_nowait(record)
            except asyncio.QueueFull:
                self.dropped_count += 1
                return False
        else:
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._threadsafe_put, record)
            else:
                try:
                    self.queue.put_nowait(record)
                except asyncio.QueueFull:
                    self.dropped_count += 1
                    return False
        return True

    def _threadsafe_put(self, record: AuditRecord) -> None:
        try:
            self.queue.put_nowait(record)
        except asyncio.QueueFull:
            self.dropped_count += 1

    def _refill_from_wal(self) -> int:
        if not self.wal_path:
            return 0
        loaded = 0
        try:
            with sqlite3.connect(str(self.wal_path), timeout=5.0) as conn:
                space = self.queue.maxsize - self.queue.qsize()
                if space <= 0:
                    return 0
                cursor = conn.execute(
                    """SELECT event_id, patient_id, user_input, llm_output, breaker_status, validator_status
                       FROM wal_audit_records
                       ORDER BY created_at ASC
                       LIMIT ?""",
                    (space,),
                )
                existing_in_queue = {rec.event_id for rec in list(self.queue._queue)}
                for row in cursor.fetchall():
                    ev_id = uuid.UUID(row[0]) if row[0] else uuid.uuid4()
                    if ev_id in existing_in_queue:
                        continue
                    rec = AuditRecord(
                        patient_id=row[1],
                        user_input=row[2],
                        llm_output=row[3],
                        breaker_status=row[4],
                        validator_status=row[5],
                        event_id=ev_id,
                    )
                    try:
                        self.queue.put_nowait(rec)
                        loaded += 1
                    except asyncio.QueueFull:
                        break
        except Exception:
            pass
        return loaded

    async def close(self, *, drain_timeout: float = 10.0) -> None:
        if drain_timeout <= 0:
            raise ValueError("drain_timeout must be positive")
        try:
            atexit.unregister(self.flush_to_wal)
        except Exception:
            pass
        self.flush_to_wal()
        if self._worker is None:
            if not self.queue.empty():
                self.start()
            else:
                return
        try:
            try:
                await asyncio.wait_for(self.queue.join(), timeout=drain_timeout)
            except (TimeoutError, asyncio.TimeoutError) as exc:
                self.flush_to_wal()
                raise TimeoutError("audit queue did not drain; worker remains active") from exc
        finally:
            self.flush_to_wal()
            if self._worker is not None:
                self._worker.cancel()
                try:
                    await self._worker
                except asyncio.CancelledError:
                    pass
                self._worker = None

    async def _run(self) -> None:
        while True:
            if self.queue.qsize() < (self.queue.maxsize // 2):
                self._refill_from_wal()

            try:
                record = await asyncio.wait_for(self.queue.get(), timeout=0.5)
            except (asyncio.TimeoutError, TimeoutError):
                self._refill_from_wal()
                if self.queue.empty():
                    await asyncio.sleep(0.05)
                continue

            delay = 0.1
            try:
                while True:
                    try:
                        await self._persist(record)
                        break
                    except Exception:
                        await asyncio.sleep(delay)
                        delay = min(delay * 2, 5.0)
            finally:
                self.queue.task_done()

    async def _persist(self, record: AuditRecord) -> None:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                prev_hash = await connection.fetchval(
                    "SELECT current_hash FROM audit_chain_head WHERE singleton = TRUE FOR UPDATE"
                )
                if prev_hash is None:
                    raise RuntimeError("audit_chain_head is not initialized")
                already_written = await connection.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM audit_claim_ledger WHERE event_id = $1)",
                    record.event_id,
                )
                if already_written:
                    self._remove_wal(record.event_id)
                    return
                digest = current_hash(str(prev_hash), record)
                await connection.execute(
                    """INSERT INTO audit_claim_ledger
                       (event_id, patient_id, user_input, llm_output, breaker_status,
                        validator_status, prev_hash, current_hash)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                    record.event_id, record.patient_id, record.user_input,
                    record.llm_output, record.breaker_status, record.validator_status,
                    str(prev_hash), digest,
                )
                await connection.execute(
                    "UPDATE audit_chain_head SET current_hash = $1 WHERE singleton = TRUE", digest
                )
        self._remove_wal(record.event_id)


