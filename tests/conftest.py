import tempfile
import pytest
from pathlib import Path
from app.config import settings
from app.db import init_db

@pytest.fixture(autouse=True)
def isolated_test_db(monkeypatch):
    """Provides a fresh isolated SQLite database for each test run."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        test_db_path = tmp.name

    monkeypatch.setattr(settings, "DATABASE_PATH", test_db_path)
    init_db(test_db_path)

    yield test_db_path

    # Clean up temporary test file
    Path(test_db_path).unlink(missing_ok=True)

