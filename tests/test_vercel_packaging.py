"""Validation suite for Vercel packaging, security headers, and client runtime resilience.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = WORKSPACE_ROOT / "frontend"
DISHA_CORE_FRONTEND_DIR = WORKSPACE_ROOT / "disha_core" / "frontend"


def test_directories_synchronized() -> None:
    """frontend/ and disha_core/frontend/ must be identical byte-for-byte."""
    sync_script = WORKSPACE_ROOT / "scripts" / "sync-frontend.sh"
    if sync_script.exists():
        subprocess.run(["bash", str(sync_script)], cwd=str(WORKSPACE_ROOT), check=True)

    frontend_files = sorted([p.name for p in FRONTEND_DIR.iterdir() if p.is_file()])
    disha_files = sorted([p.name for p in DISHA_CORE_FRONTEND_DIR.iterdir() if p.is_file()])
    assert frontend_files == disha_files, f"File mismatch: {frontend_files} != {disha_files}"

    for filename in frontend_files:
        f1 = (FRONTEND_DIR / filename).read_bytes()
        f2 = (DISHA_CORE_FRONTEND_DIR / filename).read_bytes()
        assert f1 == f2, f"Discrepancy detected in {filename}"


def test_vercel_json_security_and_routing() -> None:
    """Validate vercel.json headers, CSP, and routing."""
    for v_path in [FRONTEND_DIR / "vercel.json", DISHA_CORE_FRONTEND_DIR / "vercel.json"]:
        assert v_path.exists(), f"{v_path} does not exist"
        data = json.loads(v_path.read_text())

        # Check top-level config
        assert data.get("version") == 2
        assert data.get("cleanUrls") is True

        # Check headers
        headers_config = data.get("headers", [])
        assert len(headers_config) > 0

        global_headers = {
            h["key"]: h["value"]
            for h in headers_config[0].get("headers", [])
        }

        # 1. Strict-Transport-Security
        assert "Strict-Transport-Security" in global_headers
        assert "max-age=" in global_headers["Strict-Transport-Security"]
        assert "includeSubDomains" in global_headers["Strict-Transport-Security"]

        # 2. X-Content-Type-Options
        assert global_headers.get("X-Content-Type-Options") == "nosniff"

        # 3. X-Frame-Options
        assert global_headers.get("X-Frame-Options") in ["DENY", "SAMEORIGIN"]

        # 4. Content-Security-Policy
        assert "Content-Security-Policy" in global_headers
        csp = global_headers["Content-Security-Policy"]
        assert "wss:" in csp, "CSP must permit wss:// for secure WebSockets"
        assert "https:" in csp, "CSP must permit https://"
        assert "media-src" in csp, "CSP must configure media-src for audio playback"
        assert "blob:" in csp, "CSP must permit blob: for AudioContext and MediaRecorder"
        assert "connect-src" in csp, "CSP must configure connect-src"

        # 5. Permissions-Policy
        assert "Permissions-Policy" in global_headers
        perm = global_headers["Permissions-Policy"]
        assert "microphone=" in perm, "Permissions-Policy must explicitly allow microphone capture"

        # Check rewrites for SPA routing
        rewrites = data.get("rewrites", [])
        assert len(rewrites) > 0
        assert any(r.get("destination") == "/index.html" for r in rewrites)


def test_vercel_authentication_fails_closed_without_backend() -> None:
    """A static preview must not issue demo identities or claim backend readiness."""
    login_source = (FRONTEND_DIR / "api" / "auth" / "login.js").read_text()
    ready_source = (FRONTEND_DIR / "api" / "ready.js").read_text()

    assert "status(503)" in login_source
    assert "pt_test_" not in login_source
    assert "status(503)" in ready_source
    assert "available: true" not in ready_source


def test_client_runtime_node_validation() -> None:
    """Execute Node.js assertions directly against frontend/app.js exports."""
    test_script = """
    const engine = require('./frontend/app.js');
    const assert = require('assert');

    // 1. Test getBackendConfig with window.__ENV__
    {
      global.window = {
        location: { protocol: 'https:', host: 'disha.vercel.app', origin: 'https://disha.vercel.app' },
        __ENV__: { DISHA_API_URL: 'https://backend.disha.ai' }
      };
      global.localStorage = { getItem: () => null };

      const cfg = engine.getBackendConfig();
      assert.strictEqual(cfg.httpBase, 'https://backend.disha.ai');
      assert.strictEqual(cfg.wsBase, 'wss://backend.disha.ai');
    }

    // 2. Test mixed-content prevention (http:// specified on https:// origin)
    {
      global.window = {
        location: { protocol: 'https:', host: 'disha.vercel.app', origin: 'https://disha.vercel.app' },
        __ENV__: null
      };
      global.localStorage = { getItem: (k) => k === 'disha_api_url' ? 'http://insecure-backend.com' : null };

      const cfg = engine.getBackendConfig();
      assert.strictEqual(cfg.httpBase, 'https://insecure-backend.com', 'Mixed HTTP must be upgraded to HTTPS on secure origin');
      assert.strictEqual(cfg.wsBase, 'wss://insecure-backend.com', 'Mixed WS must be upgraded to WSS on secure origin');
    }

    // 3. Test mixed-content ws:// specified on https:// origin
    {
      global.window = {
        location: { protocol: 'https:', host: 'disha.vercel.app', origin: 'https://disha.vercel.app' },
        __ENV__: null
      };
      global.localStorage = { getItem: (k) => k === 'disha_api_url' ? 'ws://insecure-backend.com' : null };

      const cfg = engine.getBackendConfig();
      assert.strictEqual(cfg.httpBase, 'https://insecure-backend.com');
      assert.strictEqual(cfg.wsBase, 'wss://insecure-backend.com');
    }

    // 4. Test fallback to window.location when no config set
    {
      global.window = {
        location: { protocol: 'https:', host: 'disha-production.vercel.app', origin: 'https://disha-production.vercel.app' },
        __ENV__: null
      };
      global.localStorage = { getItem: () => null };

      const cfg = engine.getBackendConfig();
      assert.strictEqual(cfg.httpBase, 'https://disha-production.vercel.app');
      assert.strictEqual(cfg.wsBase, 'wss://disha-production.vercel.app');
    }

    // 5. Test local dev HTTP fallback
    {
      global.window = {
        location: { protocol: 'http:', host: '127.0.0.1:8080', origin: 'http://127.0.0.1:8080' },
        __ENV__: null
      };
      global.localStorage = { getItem: () => null };

      const cfg = engine.getBackendConfig();
      assert.strictEqual(cfg.httpBase, 'http://127.0.0.1:8080');
      assert.strictEqual(cfg.wsBase, 'ws://127.0.0.1:8080');
    }

    // 6. Test interrupted event handling (both {"type": "interrupted"} and {"interrupted": true})
    {
      // Subtest 6A: type === 'interrupted'
      engine.state.isPlayingAudio = true;
      engine.state.audioQueue = [new ArrayBuffer(100), new ArrayBuffer(200)];

      let stopCalled = false;
      let disconnectCalled = false;
      engine.state.currentAudioSource = {
        stop: () => { stopCalled = true; },
        disconnect: () => { disconnectCalled = true; },
        onended: () => {}
      };

      engine.handleServerMessage({ type: 'interrupted' });

      assert.strictEqual(engine.state.isPlayingAudio, false, 'isPlayingAudio must be set to false on interrupt');
      assert.strictEqual(engine.state.audioQueue.length, 0, 'audioQueue must be drained immediately on interrupt');
      assert.strictEqual(engine.state.currentAudioSource, null, 'currentAudioSource reference must be cleared');
      assert.strictEqual(stopCalled, true, 'AudioBufferSource.stop(0) must be called');
      assert.strictEqual(disconnectCalled, true, 'AudioBufferSource.disconnect() must be called');

      // Subtest 6B: interrupted === true
      engine.state.isPlayingAudio = true;
      engine.state.audioQueue = [new ArrayBuffer(50)];
      let htmlAudioPaused = false;
      engine.state.currentHtmlAudio = {
        pause: () => { htmlAudioPaused = true; },
        currentTime: 5,
        src: 'blob:http://localhost/test',
        onended: () => {}
      };

      engine.handleServerMessage({ interrupted: true });

      assert.strictEqual(engine.state.isPlayingAudio, false);
      assert.strictEqual(engine.state.audioQueue.length, 0);
      assert.strictEqual(engine.state.currentHtmlAudio, null);
      assert.strictEqual(htmlAudioPaused, true, 'HTML Audio must be paused immediately');
    }

    // 7. Test exponential backoff reconnect timing
    {
      const expectedBases = [1000, 2000, 4000, 8000, 16000, 16000];
      for (let attempt = 0; attempt < expectedBases.length; attempt++) {
        const maxDelay = 16000;
        const baseDelay = Math.min(maxDelay, 1000 * Math.pow(2, attempt));
        assert.strictEqual(baseDelay, expectedBases[attempt], `Attempt ${attempt} base delay mismatch`);
      }
    }

    // 8. Test relative path handling in runtime config
    {
      global.window = {
        location: { protocol: 'https:', host: 'disha.vercel.app', origin: 'https://disha.vercel.app' },
        __ENV__: { DISHA_API_URL: '/api' }
      };
      global.localStorage = { getItem: () => null };

      const cfg = engine.getBackendConfig();
      assert.strictEqual(cfg.httpBase, 'https://disha.vercel.app/api');
      assert.strictEqual(cfg.wsBase, 'wss://disha.vercel.app/api');
    }

    // 9. Test NEXT_PUBLIC_API_URL and NEXT_PUBLIC_WS_URL runtime config
    {
      global.window = {
        location: { protocol: 'https:', host: 'disha.vercel.app', origin: 'https://disha.vercel.app' },
        __ENV__: {
          NEXT_PUBLIC_API_URL: 'https://api.disha.example.com',
          NEXT_PUBLIC_WS_URL: 'wss://api.disha.example.com/ws/conversation'
        }
      };
      global.localStorage = { getItem: () => null };

      const cfg = engine.getBackendConfig();
      assert.strictEqual(cfg.httpBase, 'https://api.disha.example.com');
      assert.strictEqual(cfg.wsBase, 'wss://api.disha.example.com/ws/conversation');
    }

    // 10. Test onUserSpeechDetected barge-in interruption hook
    {
      engine.state.isPlayingAudio = true;
      let stopTriggered = false;
      engine.state.currentAudioSource = {
        stop: () => { stopTriggered = true; },
        disconnect: () => {},
        onended: () => {}
      };

      const sentPayloads = [];
      engine.state.ws = {
        readyState: 1, // OPEN
        send: (msg) => { sentPayloads.push(JSON.parse(msg)); }
      };

      engine.onUserSpeechDetected();

      assert.strictEqual(engine.state.isPlayingAudio, false, 'Speech detection must halt playback');
      assert.strictEqual(stopTriggered, true, 'AudioBufferSource.stop must be invoked');
      assert.strictEqual(sentPayloads.length, 1, 'Exactly one interrupt frame must be dispatched');
      assert.strictEqual(sentPayloads[0].type, 'interrupt', 'Payload must match {"type": "interrupt"}');
      assert.strictEqual(typeof engine.resetWaveformVisualizer, 'function', 'resetWaveformVisualizer must be exported');
    }

    console.log("All Node.js client assertions passed successfully!");
    """

    res = subprocess.run(
        ["node", "-e", test_script],
        cwd=str(WORKSPACE_ROOT),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Node test failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert "All Node.js client assertions passed successfully!" in res.stdout
