"""
Rate limiting and API usage protection for Disha AI Health Coach.
Strictly protects Google Gemini free-tier quota (15 RPM, 1500 RPD).
Prevents accidental duplicate requests, concurrency races, and exhaustion.
"""

import asyncio
import random
import time
from typing import Dict, Optional, Tuple
from app.config import settings
from app.db import get_connection

class UsageProtector:
    def __init__(self):
        # In-memory sliding window: user_id -> list of float timestamps
        self._user_request_times: Dict[str, list] = {}
        # Per-user concurrency locks to prevent race conditions & duplicate submissions
        self._user_locks: Dict[str, asyncio.Lock] = {}
        # Debouncing last submission per user: user_id -> (timestamp, text_hash)
        self._last_submissions: Dict[str, Tuple[float, str]] = {}
        # Global request tracker
        self._global_request_count = 0
        self._budget_warning_emitted = False

    def get_user_lock(self, user_id: str) -> asyncio.Lock:
        if user_id not in self._user_locks:
            self._user_locks[user_id] = asyncio.Lock()
        return self._user_locks[user_id]

    def check_rate_limit(self, user_id: str) -> Tuple[bool, Optional[str]]:
        """
        Validates whether user exceeds the 15 RPM limit or daily budget.
        Returns (is_allowed, error_message).
        """
        now = time.time()
        window_start = now - 60.0

        # Prune old timestamps
        times = self._user_request_times.get(user_id, [])
        times = [t for t in times if t > window_start]
        self._user_request_times[user_id] = times

        if len(times) >= settings.RATE_LIMIT_RPM:
            return False, f"Rate limit reached ({settings.RATE_LIMIT_RPM} requests/min). Kripya thoda wait karke dobara puchein."

        # Check daily budget
        daily_count = self.get_daily_usage_count()
        if daily_count >= settings.DAILY_REQUEST_BUDGET:
            return False, "Daily free-tier request quota reached for today. System is operating in offline mode."

        return True, None

    def record_request(self, user_id: str, model: str, call_type: str = "chat", in_tokens: int = 0, out_tokens: int = 0):
        """Records a successful API call for sliding window and persistent audit."""
        now = time.time()
        if user_id not in self._user_request_times:
            self._user_request_times[user_id] = []
        self._user_request_times[user_id].append(now)

        try:
            conn = get_connection()
            conn.execute("""
                INSERT INTO api_usage_logs (id, user_id, model, call_type, input_tokens, output_tokens)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (f"use_{int(now*1000)}_{random.randint(100,999)}", user_id, model, call_type, in_tokens, out_tokens))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def get_daily_usage_count(self) -> int:
        """Returns total API requests made in the last 24 hours."""
        try:
            conn = get_connection()
            row = conn.execute("""
                SELECT COUNT(*) as cnt FROM api_usage_logs
                WHERE created_at >= datetime('now', '-1 day')
            """).fetchone()
            conn.close()
            return row["cnt"] if row else 0
        except Exception:
            return 0

    def is_background_budget_available(self) -> bool:
        """Checks if there is sufficient quota left for non-essential background tasks."""
        daily = self.get_daily_usage_count()
        # Reserve the last 15% of the daily budget strictly for direct user conversations
        return daily < (settings.DAILY_REQUEST_BUDGET * 0.85)

    def is_duplicate_submission(self, user_id: str, utterance: str) -> bool:
        """Debounces exact duplicate clicks submitted within 400ms."""
        now = time.time()
        last = self._last_submissions.get(user_id)
        if last:
            last_time, last_text = last
            if (now - last_time < 0.4) and (last_text == utterance.strip()):
                return True
        self._last_submissions[user_id] = (now, utterance.strip())
        return False

    async def execute_with_backoff(self, async_func, *args, **kwargs):
        """
        Executes an asynchronous API call with exponential backoff and jitter.
        Handles HTTP 429 and ResourceExhausted gracefully.
        """
        max_retries = 2
        delay = 0.5

        for attempt in range(max_retries + 1):
            try:
                return await async_func(*args, **kwargs)
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = "429" in err_str or "resource_exhausted" in err_str or "quota" in err_str

                if is_rate_limit and attempt < max_retries:
                    # Exponential backoff with random jitter
                    jitter = random.uniform(0.1, 0.3)
                    await asyncio.sleep(delay + jitter)
                    delay *= 2
                    continue
                # If retries exhausted or other error, raise
                raise e

usage_protector = UsageProtector()
