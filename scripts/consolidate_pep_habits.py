#!/usr/bin/env python3
"""Nightly 'Sleep-Time' Consolidation Job for Patient Habits in the PEP.

Processes dirty patients:
1. Calculates daily/weekly/monthly rollups and trends.
2. Downsamples and prunes raw habit observations older than 90 days.
3. Folds and expires transient episodes into historical counters.
4. Materializes a compact JSONB habits snapshot on patient_pep.
5. Clears the is_dirty flag.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import asyncpg

from disha_core.pep.habits_engine import consolidate_patient_habits

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("disha_consolidator")

DEFAULT_PG_URL = os.getenv("DATABASE_URL", "postgresql://disha:disha_secure_pass_123@127.0.0.1:5432/disha")


async def run_consolidation(pg_url: str = DEFAULT_PG_URL, all_patients: bool = False, specific_patient: str | None = None) -> int:
    conn = await asyncpg.connect(pg_url)
    try:
        if specific_patient:
            patient_ids = [specific_patient]
        elif all_patients:
            rows = await conn.fetch("SELECT patient_id FROM patient_pep")
            patient_ids = [r["patient_id"] for r in rows]
        else:
            rows = await conn.fetch("SELECT patient_id FROM patient_pep WHERE is_dirty = TRUE")
            patient_ids = [r["patient_id"] for r in rows]

        logger.info("Found %d patient(s) requiring PEP habits consolidation.", len(patient_ids))
        if not patient_ids:
            return 0

        t0 = time.perf_counter()
        processed = 0
        errors = 0

        for pid in patient_ids:
            try:
                res = await consolidate_patient_habits(pid, conn=conn)
                processed += 1
                logger.debug("Consolidated %s: %s", pid, res)
            except Exception as e:
                errors += 1
                logger.error("Failed to consolidate patient %s: %s", pid, e, exc_info=True)

        elapsed = time.perf_counter() - t0
        logger.info(
            "Consolidation complete: processed %d patients (%d errors) in %.2fs (%.2f ms/patient)",
            processed,
            errors,
            elapsed,
            (elapsed * 1000 / processed) if processed else 0,
        )
        return 0 if errors == 0 else 1
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Nightly PEP Habits Consolidation")
    parser.add_argument("--all", action="store_true", help="Consolidate all patients regardless of is_dirty")
    parser.add_argument("--patient-id", type=str, help="Consolidate a specific patient ID")
    parser.add_argument("--db-url", type=str, default=DEFAULT_PG_URL, help="PostgreSQL connection string")
    args = parser.parse_args()

    sys.exit(asyncio.run(run_consolidation(args.db_url, args.all, args.patient_id)))


if __name__ == "__main__":
    main()
