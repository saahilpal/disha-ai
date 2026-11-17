"""Test suite enforcing zero hardcoded ephemeral hosts, tunnels, or external cloud URLs in source code."""

from __future__ import annotations

import re
from pathlib import Path

FORBIDDEN_PATTERNS = [
    re.compile(r"trycloudflare\.com", re.IGNORECASE),
    re.compile(r"ngrok(-free)?\.app", re.IGNORECASE),
    re.compile(r"localtunnel\.me", re.IGNORECASE),
    re.compile(r"[a-zA-Z0-9-]+\.onrender\.com", re.IGNORECASE),
]

# Source files to scan: all python and js/json files in disha_core excluding tests and generated artifacts
REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIRS = [
    REPO_ROOT / "disha_core",
]


def test_zero_hardcoded_tunnel_or_ephemeral_hosts():
    """Verify no hardcoded ephemeral tunnels, ngrok URLs, or hardcoded render project URLs exist in source code."""
    offending_lines: list[str] = []

    for source_dir in SOURCE_DIRS:
        for path in source_dir.rglob("*"):
            if not path.is_file():
                continue
            if "tests" in path.parts or "__pycache__" in path.parts or ".pytest_cache" in path.parts:
                continue
            if path.suffix not in {".py", ".js", ".json", ".yaml", ".yml", ".html"}:
                continue

            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue

            for idx, line in enumerate(content.splitlines(), start=1):
                # Skip comments explaining forbidden hosts or documentation headers
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
                    continue

                for pattern in FORBIDDEN_PATTERNS:
                    if pattern.search(line):
                        offending_lines.append(f"{path.relative_to(REPO_ROOT)}:{idx}: {line.strip()}")

    assert not offending_lines, (
        f"Found {len(offending_lines)} hardcoded tunnel/cloud host references:\n"
        + "\n".join(offending_lines)
    )


def test_settings_dynamic_configuration():
    """Verify that Settings in disha_core.config reads host/port/keys from environment."""
    from disha_core.config import Settings

    settings = Settings.from_env()
    assert hasattr(settings, "db_host")
    assert hasattr(settings, "db_port")
    assert hasattr(settings, "qwen3_tts_url")
    assert hasattr(settings, "database_url")
