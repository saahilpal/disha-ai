"""Database adapter for PostgreSQL pool connection management."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger("disha_core.adapters.db")


async def create_database_pool(
    database_url: str | None = None,
    min_size: int = 2,
    max_size: int = 30,
    timeout: float = 5.0,
    command_timeout: float = 30.0,
    max_inactive_connection_lifetime: float = 300.0,
    retries: int = 3,
    retry_delay: float = 1.0,
) -> Any | None:
    """Initialize asyncpg connection pool with connection bounds, timeout, and reconnect resilience."""
    try:
        import asyncpg
    except ImportError:
        logger.warning("asyncpg not installed; database pool unavailable")
        return None

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            if database_url:
                pool = await asyncpg.create_pool(
                    database_url,
                    min_size=min_size,
                    max_size=max_size,
                    timeout=timeout,
                    command_timeout=command_timeout,
                    max_inactive_connection_lifetime=max_inactive_connection_lifetime,
                    max_queries=50000,
                )
                logger.info("Database connection pool initialized (min=%d, max=%d)", min_size, max_size)
                return pool

            required = ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")
            if all(os.getenv(name) for name in required):
                pool = await asyncpg.create_pool(
                    host=os.environ["DB_HOST"],
                    port=int(os.getenv("DB_PORT", "5432")),
                    database=os.environ["DB_NAME"],
                    user=os.environ["DB_USER"],
                    password=os.environ["DB_PASSWORD"],
                    min_size=min_size,
                    max_size=max_size,
                    timeout=timeout,
                    command_timeout=command_timeout,
                    max_inactive_connection_lifetime=max_inactive_connection_lifetime,
                    max_queries=50000,
                )
                logger.info("Database connection pool initialized (min=%d, max=%d)", min_size, max_size)
                return pool
            break
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Database pool connection attempt %d/%d failed: %s",
                attempt,
                retries,
                type(exc).__name__,
            )
            if attempt < retries:
                await asyncio.sleep(retry_delay * attempt)

    if last_error is not None:
        logger.error("Could not establish database pool after %d attempts", retries)
    return None
