"""Disha AI — Open Dataset Ingestion Script (CLI Entrypoint).

Canonical implementation lives in `disha_core.db.ingest_open_datasets`.
"""

from __future__ import annotations

import asyncio

from disha_core.db.ingest_open_datasets import main

if __name__ == "__main__":
    asyncio.run(main())
