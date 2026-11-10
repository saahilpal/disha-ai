#!/usr/bin/env python3
"""Disha AI — Show-Readiness Demo Environment Reset Utility.

Resets all demo patient interactions, clears ephemeral conversation journals,
resets Merkle audit ledger entries for demo personas, and reseeds pristine
clinical PEPs, diet schedules, and habits.

Ensures zero state leakage between demo runs.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

import asyncpg

from scripts.demo_seed import DEMO_PATIENTS, seed_demo_patients

DEFAULT_PG_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://disha:disha_secure_pass_123@127.0.0.1:5432/disha",
)


async def reset_demo_environment(db_url: str = DEFAULT_PG_URL) -> dict[str, Any]:
    """Wipe transient demo interactions and restore pristine baseline state."""
    print(f"[+] Connecting to PostgreSQL at {db_url} for demo environment reset...")
    conn = await asyncpg.connect(db_url)
    demo_pids = [p["patient_id"] for p in DEMO_PATIENTS]

    try:
        async with conn.transaction():
            print(f"[*] Purging ephemeral journals and turn history for demo personas: {demo_pids}...")
            # 1. Clear turn journal for demo patients
            deleted_turns = await conn.execute(
                "DELETE FROM patient_turn_journal WHERE patient_id = ANY($1)",
                demo_pids,
            )

            # 2. Clear journey question history and journey state
            deleted_history = await conn.execute(
                "DELETE FROM journey_question_history WHERE patient_id = ANY($1)",
                demo_pids,
            )
            deleted_journey = await conn.execute(
                "DELETE FROM patient_journey_state WHERE patient_id = ANY($1)",
                demo_pids,
            )

            # 3. Clear call summaries
            deleted_summaries = await conn.execute(
                "DELETE FROM call_summaries WHERE patient_id = ANY($1)",
                demo_pids,
            )

            # 4. Remove transient/dirty habit observations
            deleted_obs = await conn.execute(
                "DELETE FROM habit_observations WHERE patient_id = ANY($1)",
                demo_pids,
            )

            print(
                f"[✓] Purged: {deleted_turns}, {deleted_history}, {deleted_journey}, {deleted_summaries}, {deleted_obs}"
            )

        # Reseed pristine state
        stats = await seed_demo_patients(db_url)
        print("\n[✓] Demo environment successfully reset to pristine showroom state!")
        return stats
    finally:
        await conn.close()


def main() -> int:
    try:
        asyncio.run(reset_demo_environment())
        return 0
    except Exception as exc:
        print(f"[-] Error resetting demo environment: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
