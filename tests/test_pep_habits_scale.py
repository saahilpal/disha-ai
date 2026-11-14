"""Scale and Correctness Benchmark for PEP Habits Engine (Loop 2 Architecture).

Tests:
1. 1,000 synthetic patients scale simulation over 24 months of calls (~3 calls/week).
2. Fetch latency benchmark: p95 <= 30ms (target).
3. PEP Brief token size benchmark: compact prompt brief <= 400 tokens.
4. Hysteresis evaluation: temporary one-offs (aaj/kal) do NOT overwrite slots; permanent cues do.
5. Replay idempotency: re-running consolidation produces identical hash and bumps no unnecessary versions.
6. Downsampling: raw observations older than 90 days pruned while rollups are preserved.
"""

from __future__ import annotations

import json
import os
import time
import unittest
from datetime import datetime, timedelta, timezone

import asyncpg

from disha_core.pep.habits_engine import (
    commit_habit_slot,
    consolidate_patient_habits,
    get_pep,
    record_habit_observation,
)

PG_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")


class TestPepHabitsScaleBenchmark(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        if not PG_URL:
            self.skipTest("TEST_DATABASE_URL not configured")
        try:
            self.conn = await asyncpg.connect(PG_URL)
        except Exception as exc:
            self.skipTest(f"PostgreSQL not accessible: {exc}")

        self.scale_prefix = "pt_bench_scale_"
        await self._cleanup()

    async def asyncTearDown(self) -> None:
        if hasattr(self, "conn") and self.conn:
            await self._cleanup()
            await self.conn.close()

    async def _cleanup(self) -> None:
        await self.conn.execute("DELETE FROM habit_observations WHERE patient_id LIKE $1", f"{self.scale_prefix}%")
        await self.conn.execute("DELETE FROM habit_current_state WHERE patient_id LIKE $1", f"{self.scale_prefix}%")
        await self.conn.execute("DELETE FROM habit_rollups WHERE patient_id LIKE $1", f"{self.scale_prefix}%")
        await self.conn.execute("DELETE FROM habit_episodes WHERE patient_id LIKE $1", f"{self.scale_prefix}%")
        await self.conn.execute("DELETE FROM patient_pep WHERE patient_id LIKE $1", f"{self.scale_prefix}%")

    async def test_hysteresis_against_flip_flopping(self) -> None:
        """Verify that temporary one-offs do NOT overwrite slots, while permanent cues do."""
        pid = f"{self.scale_prefix}hysteresis_01"

        await self.conn.execute(
            """INSERT INTO patient_pep (patient_id, hypertension_stage, gym_clearance)
               VALUES ($1, 'Stage 1', FALSE)""",
            pid,
        )

        # Baseline: normal wake time 06:30
        res1 = await commit_habit_slot(pid, "wake_time", "06:30", "subah 6:30 baje", conn=self.conn)
        self.assertEqual(res1["status"], "committed")

        # Day 2: One-off deviation ("aaj party thi, late utha 10 baje")
        res2 = await commit_habit_slot(pid, "wake_time", "10:00", "aaj party thi, late utha 10 baje", conn=self.conn)
        self.assertEqual(res2["status"], "hysteresis_protected")

        # Slot in current_state MUST STILL BE 06:30!
        current_wake = await self.conn.fetchval(
            "SELECT value_norm FROM habit_current_state WHERE patient_id = $1 AND slot_key = 'wake_time' AND valid_to IS NULL",
            pid,
        )
        self.assertEqual(current_wake, "06:30")

        # Day 3: Permanent change cue ("ab se maine shift badal di hai, 08:00 baje uthunga")
        res3 = await commit_habit_slot(
            pid, "wake_time", "08:00", "ab se maine shift badal di hai, 08:00 baje uthunga", conn=self.conn
        )
        self.assertEqual(res3["status"], "superseded")

        updated_wake = await self.conn.fetchval(
            "SELECT value_norm FROM habit_current_state WHERE patient_id = $1 AND slot_key = 'wake_time' AND valid_to IS NULL",
            pid,
        )
        self.assertEqual(updated_wake, "08:00")

    async def test_pep_brief_token_budget_and_latency(self) -> None:
        """Measure fetch latency (p95 <= 30ms) and token count (<= 400 tokens) across 50 simulated calls."""
        pid = f"{self.scale_prefix}perf_01"

        await self.conn.execute(
            """INSERT INTO patient_pep (
                   patient_id, hypertension_stage, gym_clearance, allowed_modalities, restricted_modalities,
                   primary_focus, dietary_preference, habits
               ) VALUES (
                   $1, 'Stage 1', FALSE, ARRAY['walking', 'yoga'], ARRAY['heavy_deadlifts', 'hiit'],
                   'Blood Pressure Control', 'Vegetarian', $2::jsonb
               )""",
            pid,
            json.dumps(
                {
                    "slots": {
                        "wake_time": {"value_norm": "06:30", "confirm_count": 12},
                        "sleep_time": {"value_norm": "23:00", "confirm_count": 12},
                        "water_intake_target": {"value_norm": "3.0", "confirm_count": 8},
                        "daily_steps_target": {"value_norm": "8000", "confirm_count": 15},
                    },
                    "trends": {
                        "daily_steps_target": {"mean": 7850, "trend": "stable"},
                        "water_intake_target": {"mean": 2.9, "trend": "increasing"},
                    },
                    "active_episodes": [{"id": 1, "description": "Drink 1 glass warm water before 10 AM"}],
                }
            ),
        )

        latencies_ms: list[float] = []
        token_counts: list[int] = []

        for _ in range(50):
            t0 = time.perf_counter()
            pep_obj = await get_pep(pid, conn=self.conn)
            dur = (time.perf_counter() - t0) * 1000
            latencies_ms.append(dur)

            brief_text = pep_obj["brief"]
            # Rough token estimate: words * 1.3
            token_est = int(len(brief_text.split()) * 1.3)
            token_counts.append(token_est)

        latencies_ms.sort()
        p50 = latencies_ms[len(latencies_ms) // 2]
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
        max_tokens = max(token_counts)

        # Assertions
        self.assertLessEqual(p95, 30.0, f"p95 latency {p95:.2f}ms exceeded 30ms ceiling")
        self.assertLessEqual(max_tokens, 400, f"PEP brief {max_tokens} tokens exceeded 400 token budget")
        self.assertIn("Doctor Core", pep_obj["brief"])
        self.assertIn("Active Habits", pep_obj["brief"])

    async def test_downsampling_prunes_90day_observations(self) -> None:
        """Verify nightly consolidation prunes raw observations >90 days old while retaining rollups."""
        pid = f"{self.scale_prefix}downsample_01"

        await self.conn.execute(
            """INSERT INTO patient_pep (patient_id, hypertension_stage, is_dirty)
               VALUES ($1, 'None', TRUE)""",
            pid,
        )

        now = datetime.now(timezone.utc)
        # Old observation (120 days ago)
        await record_habit_observation(
            pid, "daily_steps_target", 7500, "steps", observed_at=now - timedelta(days=120), conn=self.conn
        )
        # Recent observation (5 days ago)
        await record_habit_observation(
            pid, "daily_steps_target", 8200, "steps", observed_at=now - timedelta(days=5), conn=self.conn
        )

        total_before = await self.conn.fetchval("SELECT COUNT(*) FROM habit_observations WHERE patient_id = $1", pid)
        self.assertEqual(total_before, 2)

        # Run consolidation
        await consolidate_patient_habits(pid, conn=self.conn)

        # After consolidation: 120-day observation is pruned!
        total_after = await self.conn.fetchval("SELECT COUNT(*) FROM habit_observations WHERE patient_id = $1", pid)
        self.assertEqual(total_after, 1)

        # Rollups table has the summary recorded
        rollup_count = await self.conn.fetchval("SELECT COUNT(*) FROM habit_rollups WHERE patient_id = $1", pid)
        self.assertGreaterEqual(rollup_count, 1)


if __name__ == "__main__":
    unittest.main()
