"""Tests for Cloudflare Tunnel Watchdog and Live Telephony Verification.

Author: Staff SRE & Edge Infrastructure Lead for Disha AI
Standard: cloudflare-architect, senior-ai-systems-engineer
"""
import json
import os
import plistlib
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
INFRA_DIR = REPO_ROOT / "infra"
AGENT_DIR = REPO_ROOT / "agent"


def test_watchdog_script_exists_and_executable():
    """Verify scripts/tunnel-watchdog.sh is present and executable."""
    watchdog_script = SCRIPTS_DIR / "tunnel-watchdog.sh"
    assert watchdog_script.exists(), "scripts/tunnel-watchdog.sh does not exist"
    assert os.access(watchdog_script, os.X_OK), "scripts/tunnel-watchdog.sh is not executable"


def test_verify_telephony_script_exists_and_executable():
    """Verify scripts/verify-telephony-live.sh is present and executable."""
    verify_script = SCRIPTS_DIR / "verify-telephony-live.sh"
    assert verify_script.exists(), "scripts/verify-telephony-live.sh does not exist"
    assert os.access(verify_script, os.X_OK), "scripts/verify-telephony-live.sh is not executable"


def test_launchd_plist_syntax_and_keys():
    """Verify infra/com.disha.tunnel.plist syntax and required launchd keys."""
    plist_path = INFRA_DIR / "com.disha.tunnel.plist"
    assert plist_path.exists(), "infra/com.disha.tunnel.plist does not exist"

    # Validate plist parsing
    with open(plist_path, "rb") as f:
        plist_data = plistlib.load(f)

    assert plist_data["Label"] == "com.disha.tunnel"
    assert plist_data["KeepAlive"] is True
    assert plist_data["RunAtLoad"] is True
    assert "ProgramArguments" in plist_data
    assert "scripts/tunnel-watchdog.sh" in " ".join(plist_data["ProgramArguments"])
    assert "StandardOutPath" in plist_data
    assert "StandardErrorPath" in plist_data
    assert "EnvironmentVariables" in plist_data
    assert plist_data["EnvironmentVariables"]["TARGET_URL"] == "http://127.0.0.1:8080"


def test_tunnel_url_file_and_https_scheme():
    """Verify agent/TUNNEL_URL.txt contains a live HTTPS URL."""
    tunnel_file = AGENT_DIR / "TUNNEL_URL.txt"
    assert tunnel_file.exists(), f"Missing {tunnel_file}"

    url = tunnel_file.read_text().strip()
    assert url.startswith("https://"), f"Tunnel URL must start with https://, got {url}"
    assert ".trycloudflare.com" in url or "disha.ai" in url


def test_telephony_verification_report_audit():
    """Verify agent/TELEPHONY_VERIFICATION_REPORT.json audit data."""
    report_file = AGENT_DIR / "TELEPHONY_VERIFICATION_REPORT.json"
    assert report_file.exists(), f"Missing {report_file}"

    with open(report_file) as f:
        data = json.load(f)

    assert data["checks_passed"] == data["total_checks"] == 5
    assert data["tls_verification"]["trusted"] is True
    assert data["tls_verification"]["browser_microphone_allowed"] is True
    assert data["endpoints"]["/health"]["status_code"] == 200
    assert data["endpoints"]["/health"]["passed"] is True
    assert data["endpoints"]["/ready"]["status_code"] == 200
    assert data["endpoints"]["/ready"]["passed"] is True
    assert data["endpoints"]["/auth/login"]["passed"] is True
    assert data["endpoints"]["/internal/classifier"]["status_code"] == 200
    assert data["endpoints"]["/internal/classifier"]["passed"] is True


def test_watchdog_cli_status():
    """Verify that watchdog status CLI command executes cleanly."""
    result = subprocess.run(
        [str(SCRIPTS_DIR / "tunnel-watchdog.sh"), "--status"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "DISHA AI — CLOUDFLARE TUNNEL WATCHDOG STATUS" in result.stdout
    assert "Live Tunnel URL:" in result.stdout
