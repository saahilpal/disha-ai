"""In-memory rate limiter with sliding window tracking for Disha AI Core.

Enforces per-client and per-patient quotas to prevent credential brute-forcing,
resource exhaustion, and denial of service.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Any, Callable

from fastapi import HTTPException, Request


class SlidingWindowRateLimiter:
    """Sliding-window in-memory rate limiter."""

    def __init__(self) -> None:
        # Map: (bucket, key) -> list of request timestamps
        self._history: dict[tuple[str, str], list[float]] = defaultdict(list)
        self.enabled: bool = os.getenv("RATE_LIMIT_ENABLED", "true").casefold() != "false"

    def is_allowed(
        self,
        key: str,
        bucket: str = "default",
        limit: int = 60,
        window_seconds: float = 60.0,
    ) -> tuple[bool, int, float]:
        """Check if a request is permitted under the rate limit window.

        Returns:
            tuple[bool, int, float]: (allowed, remaining, retry_after)
        """
        if not self.enabled:
            return True, limit, 0.0

        now = time.time()
        window_start = now - window_seconds
        cache_key = (bucket, key)

        timestamps = self._history[cache_key]
        valid_timestamps = [t for t in timestamps if t > window_start]
        self._history[cache_key] = valid_timestamps

        if len(valid_timestamps) >= limit:
            oldest = valid_timestamps[0]
            retry_after = max(1.0, round(window_seconds - (now - oldest), 1))
            return False, 0, retry_after

        valid_timestamps.append(now)
        remaining = max(0, limit - len(valid_timestamps))
        return True, remaining, 0.0

    def reset(self) -> None:
        """Clear all rate limit histories (for tests)."""
        self._history.clear()


limiter = SlidingWindowRateLimiter()


def rate_limit_guard(
    bucket: str = "default",
    limit: int = 60,
    window_seconds: float = 60.0,
) -> Callable[[Request], Any]:
    """FastAPI dependency for per-client sliding-window rate limiting."""
    async def dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "127.0.0.1"
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        key = f"t_{token[:16]}" if token else f"ip_{client_ip}"

        allowed, _, retry_after = limiter.is_allowed(
            key=key,
            bucket=bucket,
            limit=limit,
            window_seconds=window_seconds,
        )
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": str(int(retry_after))},
            )

    return dependency
