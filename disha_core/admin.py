from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def issue_token(patient_id: str, expires_days: int) -> str:
    if not patient_id.strip() or expires_days < 1:
        raise ValueError("patient_id and a positive expires_days value are required")
    import asyncpg

    token = secrets.token_urlsafe(32)
    expiry = datetime.now(UTC) + timedelta(days=expires_days)
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=1)
    else:
        required = ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")
        missing = [name for name in required if not os.getenv(name)]
        if missing:
            raise RuntimeError(f"Missing runtime database variables: {', '.join(missing)}")
        pool = await asyncpg.create_pool(
            host=os.environ["DB_HOST"],
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            min_size=1,
            max_size=1,
        )
    try:
        await pool.execute(
            "INSERT INTO patient_access_tokens(token_hash, patient_id, expires_at) VALUES($1, $2, $3)",
            token_hash(token),
            patient_id.strip(),
            expiry,
        )
    finally:
        await pool.close()
    return token


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue a one-time Disha patient API token")
    parser.add_argument("patient_id")
    parser.add_argument("--expires-days", type=int, default=30)
    args = parser.parse_args()
    print(asyncio.run(issue_token(args.patient_id, args.expires_days)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
