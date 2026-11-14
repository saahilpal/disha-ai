"""Shared pytest configuration and database fixtures for Disha AI.
Provides clean connection lifecycle and skips tests cleanly when TEST_DATABASE_URL is unset.
"""

from __future__ import annotations

import os
from typing import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio


def get_test_database_url() -> str | None:
    """Return the configured test database connection URL."""
    return os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")


async def get_test_pg_connection(timeout: float = 5.0) -> asyncpg.Connection | None:
    """Acquire a live PostgreSQL connection or return None if unavailable."""
    url = get_test_database_url()
    if not url:
        return None
    try:
        return await asyncpg.connect(url, timeout=timeout)
    except Exception:
        return None


@pytest.fixture(scope="session")
def test_db_url() -> str:
    """Session fixture returning TEST_DATABASE_URL, or skipping if unset."""
    url = get_test_database_url()
    if not url:
        pytest.skip("TEST_DATABASE_URL not set; skipping live PostgreSQL test")
    return url


@pytest_asyncio.fixture
async def pg_conn(test_db_url: str) -> AsyncIterator[asyncpg.Connection]:
    """Function-scoped fixture providing an active asyncpg Connection."""
    try:
        conn = await asyncpg.connect(test_db_url, timeout=5.0)
    except Exception as exc:
        pytest.skip(f"Live PostgreSQL required at {test_db_url}: {exc}")
    try:
        yield conn
    finally:
        await conn.close()
