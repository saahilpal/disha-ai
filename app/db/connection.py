import sqlite3
import os
from pathlib import Path
from contextlib import contextmanager
from typing import Generator
from app.config import settings

def get_connection(db_path: str = None) -> sqlite3.Connection:
    """Creates an optimized SQLite connection with WAL mode and foreign keys enabled."""
    target_path = db_path or settings.DATABASE_PATH
    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(target_path, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    
    # Enable WAL mode for non-blocking concurrent reads during writes
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    
    return conn

@contextmanager
def get_db(db_path: str = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for safe transactional database operations."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

