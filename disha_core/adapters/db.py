"""Database adapter for PostgreSQL pool connection management."""
from __future__ import annotations

import os
from typing import Any


async def create_database_pool(
    database_url: str | None = None,
    min_size: int = 2,
    max_size: int = 30,
    timeout: float = 5.0,
) -> Any | None:
    """Initialize asyncpg connection pool with connection bounds and timeout."""
    try:
        import asyncpg
    except ImportError:
        return None

    try:
        if database_url:
            return await asyncpg.create_pool(
                database_url,
                min_size=min_size,
                max_size=max_size,
                timeout=timeout,
            )

        required = ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")
        if all(os.getenv(name) for name in required):
            return await asyncpg.create_pool(
                host=os.environ["DB_HOST"],
                port=int(os.getenv("DB_PORT", "5432")),
                database=os.environ["DB_NAME"],
                user=os.environ["DB_USER"],
                password=os.environ["DB_PASSWORD"],
                min_size=min_size,
                max_size=max_size,
                timeout=timeout,
            )
    except Exception:
        return None

    return None
