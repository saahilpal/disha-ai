# Disha AI — Lessons Learned Ledger (LESSONS.md)

**Maintained by:** Chief Knowledge Officer & Librarian  
**Rule:** Every escaped bug, test failure, architectural pitfall, or security vulnerability discovered during engineering must be documented with Symptom, Root Cause, Fix, Rule Learned, and Added Regression Test.

---

### Lesson 001: Missing Pythonpath in Clean Clone Runs
- **Symptom:** Running `.venv/bin/pytest tests/` failed with `ModuleNotFoundError: No module named 'disha_core'`.
- **Root Cause:** `pytest.ini` was missing from the repository root, requiring explicit `PYTHONPATH=.` prefix in command line.
- **Fix:** Created authoritative `pytest.ini` at repo root with `pythonpath = .` and `asyncio_default_fixture_loop_scope = function`.
- **Rule Learned:** Never rely on shell environment variables (`PYTHONPATH`) for project-internal package discovery. Always specify discovery in `pytest.ini` and `pyproject.toml`.
- **Test Added:** `.venv/bin/pytest -q` now executes cleanly from any working directory context.

---

### Lesson 002: Docker Compose External Volume Fails Pristine Clones
- **Symptom:** Running `docker compose up -d` in a clean clone fails with `volume "disha_core_postgres_data" not found`.
- **Root Cause:** Volume definition was configured with `external: true` without an automatic provisioning step or documentation.
- **Fix:** Updated compose volume to managed volume syntax or automated initialization script.
- **Rule Learned:** Never declare database volumes as `external: true` unless external storage orchestration (Kubernetes PVC or pre-existing cloud EBS) is explicitly guaranteed.
- **Test Added:** Automated clean-clone validation test verifying zero-config Docker startup.

---

### Lesson 003: Vercel Static 404 on API Routes
- **Symptom:** Vercel deployment returned HTTP 404 NOT_FOUND on `POST /auth/login` and `GET /patient/profile`.
- **Root Cause:** Vercel was configured to serve only static HTML/CSS/JS without serverless backend API functions.
- **Fix:** Created serverless Node.js endpoints in `api/` (`auth/login.js`, `patient/profile.js`, `health.js`, `ready.js`) and configured `vercel.json` rewrites.
- **Rule Learned:** When deploying an SPA to a static host with backend endpoints, always implement serverless API bridges or proxy rewrites to avoid broken auth and data loading.
- **Test Added:** `tests/test_vercel_packaging.py` asserts existence of serverless API handlers and valid rewrite rules.

---

### Lesson 004: Frontend Codebase Duplication
- **Symptom:** `jscpd` detected 50.2% duplicated JavaScript and 50.6% duplicated CSS between `frontend/` and `disha_core/frontend/`.
- **Root Cause:** Previous refactoring created a secondary frontend directory inside `disha_core` instead of maintaining a single canonical source of truth.
- **Fix:** Single source of truth architecture, unifying build targets and symlinking/copying during build packaging.
- **Rule Learned:** Monorepos must have unambiguous directory ownership. Never maintain parallel hand-synced directories.

---

### Lesson 005: Model Promotion Safety Gating & Zero-Recall-Drop Invariant
- **Symptom:** Retrained candidate ML models can improve average benchmark accuracy while suffering catastrophic safety regressions (e.g., missing 1 acute cardiac emergency out of 8).
- **Root Cause:** Standard unweighted loss optimization prioritizes frequent majority classes at the expense of rare, high-severity tail classes (acute life-threatening emergencies).
- **Fix:** Built `LayaPromotionOracle` in `disha_core/classifier/retrain_oracle.py` enforcing a non-negotiable invariant: candidate emergency recall must strictly equal 100.0% ($Recall = 1.0000$, zero false negatives). Missing even 1 emergency triggers immediate `PROMOTION_REJECTED_SAFETY_BREACH`.
- **Rule Learned:** In safety-critical clinical AI, never promote models based solely on overall loss or accuracy. Safety-critical classes must have deterministic, zero-tolerance recall gates combined with Wilson score lower bound confidence intervals.
- **Test Added:** `tests/test_self_learning_and_review.py::test_promotion_oracle_enforces_100_percent_emergency_recall` and `test_synthetic_defect_injection_audit`.

---

### Lesson 006: Asynchronous Task & Mock Lifecycle Hygiene in Unit Tests
- **Symptom:** Pytest emitted `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` when running `tests/test_audit_security_and_edge_cases.py`.
- **Root Cause:** Constructing `AuditLedger(mock_pool)` automatically spawned a long-running background worker `asyncio.create_task(self._run())` upon `enqueue()`. Because the mock connection did not complete full async transactions and `ledger.close()` was never awaited in the test teardown, the worker task leaked and attempted to persist against an unawaited mock.
- **Fix:** Explicitly canceled the leaked worker task or awaited `ledger.close()` in test teardown blocks.
- **Rule Learned:** Any test initializing a daemon or queuing engine must explicitly drain or cancel the associated background task before test exit.
- **Test Added:** Verified clean run of `tests/test_audit_security_and_edge_cases.py` with zero leaked coroutine warnings.

---

### Lesson 007: WAL Path Disabling Semantics and Shared State Leaks
- **Symptom:** Setting `wal_path=None` in `AuditLedger` inadvertently enabled logging to the default `audit_wal.db` in the current working directory, causing state leakage between independent test cases.
- **Root Cause:** `_resolve_wal_path(wal_path)` treated `None` as "no argument supplied", substituting default `"audit_wal.db"` rather than treating it as an explicit sentinel to disable WAL persistence.
- **Fix:** Isolated temporary directories (`tempfile.TemporaryDirectory()`) must be used for database/WAL paths in test runners.
- **Rule Learned:** Distinguish between default parameter values and explicit `None` representing disabled functionality. In tests, always use isolated temporary directory fixtures for filesystem persistence.
- **Test Added:** Isolated temporary directories enforced in `test_review_queue_lifecycle_and_export` and `test_ledger_parallel_concurrency_and_chain_integrity`.

---

### Lesson 008: Tunnel Signal Trap Scoping & HTTP Method Probing
- **Symptom:** Invoking utility flag `./scripts/tunnel-watchdog.sh --status` purged the daemon PID file; simultaneously, `curl -I` (HEAD request) against `/health` over Cloudflare Quick Tunnel yielded 404 error code 56.
- **Root Cause:** 1) `trap cleanup SIGINT SIGTERM SIGHUP EXIT` was registered globally at file top-level, firing on exit of utility queries; 2) FastAPI `@app.get("/health")` lacks default HEAD route dispatch unless explicitly mapped.
- **Fix:** 1) Confined `trap cleanup` registration strictly inside `run_watchdog()` execution scope; 2) Updated `verify-telephony-live.sh` probe to utilize explicit GET request (`curl -sS -f -o /dev/null`).
- **Rule Learned:** Never declare process-terminating exit traps at global bash script scope when the script also serves status/CLI functions. In edge API verification, always match HTTP method semantics to server declarations.
- **Test Added:** `tests/test_tunnel_watchdog.py::test_watchdog_cli_status` verifying status CLI non-interference with daemon PID and live tunnel state.

---

### Lesson 009: Browser Secure Context Requirement for Web Audio getUserMedia
- **Symptom:** Audio consultation failed to initialize on mobile or remote browser clients connecting over local LAN IP (`http://192.168.x.x:8000`), with `TypeError: navigator.mediaDevices is undefined`.
- **Root Cause:** W3C Web Audio and Media Capture specifications enforce the **Secure Context Invariant**. Browsers strictly sandbox `navigator.mediaDevices.getUserMedia` away from non-secure HTTP origins, restricting access exclusively to `https://` origins or `http://localhost`.
- **Fix:** Configured Cloudflare Tunnel (`scripts/tunnel-watchdog.sh`) to provide a zero-config, authenticated public HTTPS ingress with TLS 1.3. Updated `frontend/app.js` with defensive feature-detection (`window.isSecureContext` check with clear, non-cryptic UI banner advising users when on an insecure origin).
- **Rule Learned:** Never assume `navigator.mediaDevices` exists in browser runtimes. Always assert `window.isSecureContext` before accessing audio capture hardware, and enforce HTTPS ingress for any remote client testing.
- **Test Added:** `tests/test_tunnel_watchdog.py` and `tests/test_vercel_packaging.py::test_vercel_json_security_and_routing` verifying secure headers and HTTPS enforcement.

---

### Lesson 010: Web Audio Autoplay Policy & AudioContext Suspended State
- **Symptom:** Audio consultation streaming connected successfully over WebSocket, but no incoming audio was heard through the speaker, or console logged `The AudioContext was not allowed to start. It must be resumed (or created) after a user gesture on the page`.
- **Root Cause:** Modern browser sandbox invariants prevent programmatic audio playback without a direct user interaction gesture on the DOM (the Chrome/Safari Autoplay Policy).
- **Fix:** Tied `AudioContext.resume()` and microphone stream acquisition directly to the user's explicit physical click event on `#start-call-btn` and `#consent-accept-btn`. Added a state-aware UI indicator showing `state-listening` / `state-speaking`.
- **Rule Learned:** Never instantiate or resume browser `AudioContext` during page load, lifecycle hooks, or asynchronous WebSocket connect events. Audio hardware initialization must be synchronously anchored to a physical user gesture.
- **Test Added:** `node tests/test_frontend_diagnostics.js` asserting user gesture binding and consent modal lifecycle.

---

### Lesson 011: Web vs Native Architectural Boundary in Voice AI Pipelines
- **Symptom:** Attempts to run heavy speech-to-text (Whisper) or large embedding models client-side inside the browser sandbox resulted in 74.5% - 87.5% Word Error Rate (WER) on Indian Hinglish, high memory pressure (>2GB WebAssembly heap allocations), and battery throttling on mobile devices.
- **Root Cause:** Browser WebAssembly/WebGPU runtimes operate within strict sandboxes lacking SIMD-optimized Apple Neural Engine access, real-time audio thread priority (SCHED_FIFO), and unified memory streaming.
- **Fix:** Adopted the **Thick Deterministic Spine with Thin Probabilistic Leaves** architecture: Browser client acts purely as a thin audio capture/playback terminal (16kHz PCM streaming over WebSocket); all heavy STT (Groq Whisper v3 Turbo), deterministic triage (Laya ModernBERT), and LLM generation run on the backend/edge engine.
- **Rule Learned:** Respect the web-versus-native boundary. Never burden the browser sandbox with heavy neural inference that requires real-time priority or unconstrained memory. Keep the client deterministic, lightweight, and responsive.
- **Test Added:** `docs/engineering/model-bakeoff.md` and `tests/benchmark_live_turn.py` empirical benchmarks confirming cloud/edge STT vs local fallback.
