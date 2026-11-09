# Disha AI — Master Autonomous Engineering Plan (PLAN.md)

**Studio Head:** Executive AI Architect & Boss  
**Target:** World-Class Voice Clinical Consultation Platform  
**Standard:** 100/100 Judge, Zero AI Slop, 100% Emergency Recall, Cloudflare HTTPS Telephony, Mathematical Invariant Safety  
**Durable State Lead:** Chief Knowledge Officer & Librarian (`librarian`)  

---

## Master Autonomous Phase Roadmap & Execution Status

### Phase 0: Safety Net & Complete Forensic Remap (COMPLETED)
- **Tag:** `pre-agent-audit` at commit `458caf1`
- **Branch:** `v2/remap`
- **Lead:** `cartographer`
- **Status:** Complete. Forensic inventory documented across:
  - `docs/map/CHANGES.md` (Forensic change log)
  - `docs/map/HARDWARE.md` (Host hardware discovery: Apple M5, 10 Cores, 16GB RAM)
  - `docs/map/LAYA_CONSUMPTION.md` (Laya consumption & call sites)
  - `docs/map/ARCHITECTURE.md` (System components & boundaries)
  - `docs/map/DATA_FLOWS.md` (Audio and text turn flows)
  - `docs/map/ENDPOINTS.md` (HTTP & WebSocket endpoints)
  - `docs/map/WEBSOCKET_PROTOCOL.md` (Real-time binary & text frames)
  - `docs/map/DB_SCHEMA.md` (PostgreSQL 16 relational & Merkle ledger schema)
  - `docs/map/OUTBOUND_CALLS.md` (External API catalog with safety gates)
  - `docs/map/PORTS_CONTAINERS.md` (Docker compose networking & volumes)
  - `docs/map/MODELS_APIS.md` (Model inventory & limits)

### Phase 1: Laya Deep-Dive, Drift Migration & Usefulness Benchmark (COMPLETED)
- **Lead:** `laya-specialist`
- **Status:** Complete.
  - `docs/research/laya-brief.md` (Architecture, ModernBERT backbone, RLCD, calibration analysis)
  - `docs/research/laya-usefulness.md` (Empirical latency, accuracy, ECE, memory benchmarks)
  - Contract test for Laya API drift prevention: `tests/test_laya_contract.py` (9/9 passed)
  - 32-case domain benchmark: 93.8% accuracy, 100% emergency recall, P50 latency 103.95ms

### Phase 2: Best Model Stack, Local-First (COMPLETED)
- **Lead:** `model-engineer`
- **Status:** Complete.
  - Voice pipeline evaluation (STT, LLM, TTS, VAD) on Apple M5 hardware
  - Benchmarks: faster-whisper (local MPS) vs Groq Whisper; Kokoro-82M vs Edge-TTS; Qwen2.5-7B/Llama-3.1 (MLX/llama.cpp) vs Groq/Gemini
  - `docs/engineering/model-bakeoff.md` (Latency TTFT, WER, audio naturalness, RAM footprint, offline capability)

### Phase 3: Full Clean Refactor (COMPLETED)
- **Lead:** `backend-engineer` & `frontend-engineer`
- **Status:** Complete.
  - Canonical frontend unified; synchronization script `scripts/sync-frontend.sh`
  - Layered backend architecture: `disha_core/adapters/`, `disha_core/services/`, `disha_core/models/`, `disha_core/config.py`, `disha_core/logging_config.py`
  - Pydantic v2 strict models, Alembic migrations (`migrations/`, `alembic.ini`)
  - Clean Docker compose configuration: `docker-compose.yml`, `docker-compose.prod.yml`

### Phase 4: Product Usefulness & "Clinical Apothecary" UI/UX (COMPLETED)
- **Lead:** `art-director` & `ux-architect`
- **Status:** Complete.
  - `docs/product/usefulness.md` (JTBD, personas, 50+ synthetic scenario test suite with 100% emergency recall)
  - `docs/design/brief.md`, `docs/design-system.md`, and `docs/design/visual-critique.md` (Design tokens, OKLCH herbal palette, typography)
  - Visual critique of screenshots across viewports: zero neon halos, zero purple gradients, zero decorative floating orbs
  - Playwright real-browser mechanical crawl: 32/32 diagnostics passed

### Phase 5: The Master Evaluation Loop & Breaker Chaos (COMPLETED)
- **Lead:** `breaker-lead` & `skeptic`
- **Status:** Complete.
  - Upgraded 10-dimension `/audit/judge.py` with hard caps (C1-C16 constraints, fake Laya, blocking UX defects)
  - Live Judge Audit Score: **98.33 / 100.0** (`PASSED_UNCONSTRAINED`), 16/16 constraints passed, core latency overhead 1.68ms
  - Breaker chaos suite: `tests/adversarial_patient_jailbreak.py`, `tests/blackbox_qa_adversary.py`
  - Synthetic mutation self-testing proving the judge catches planted failures

### Phase 6: Cloudflare Tunnel Deployment & Watchdog (COMPLETED)
- **Lead:** `sre-lead`
- **Status:** Complete.
  - Cloudflare Tunnel script and configuration: `scripts/tunnel-watchdog.sh`, `infra/`
  - Persistent host watchdog and launchd service definition
  - Live telephony verification script: `scripts/verify-telephony-live.sh`
  - Vercel production deploy: HTTP 200 on `/auth/login`, `/patient/profile`, `/ready` (`https://disha-ai-gray.vercel.app`)

### Phase 7: Self-Healing & Self-Learning (COMPLETED)
- **Lead:** `librarian` (Chief Knowledge Officer)
- **Status:** Complete.
  - **Review Queue Schema:** `docs/engineering/self-learning.md` with strict Zero-PHI HMAC-SHA256 patient pseudonymization and deterministic regex scrubbing.
  - **Review Queue Engine:** `disha_core/classifier/review_queue.py` with SQLite WAL persistence, indexing, clinician annotation signatures, and JSONL training dataset export.
  - **Offline Review CLI:** `scripts/review_tool.py` supporting `list`, `show`, `annotate`, `approve`, `export`, `stats`, and `evaluate`.
  - **Model Promotion Oracle:** `disha_core/classifier/retrain_oracle.py` enforcing 5 strict invariants:
    1. 100.0% Emergency Recall (zero false negatives allowed on red flags; failure triggers `REJECTED_SAFETY_BREACH`).
    2. Accuracy monotonicity ($\ge$ baseline).
    3. Wilson score 95% confidence bounds verification.
    4. ECE calibration stability ($ECE \le ECE_{\text{base}} + 0.03$).
    5. Latency SLA compliance (P50 $\le 150$ms, P95 $\le 300$ms).
  - **Synthetic Defect Injection:** Built-in mutation testing proving the Promotion Oracle strictly rejects defective models.
  - **Test Suite:** `tests/test_self_learning_and_review.py` (7/7 passed in 0.16s).
  - **Lessons Ledger:** `agent/LESSONS.md` updated with root cause analyses for lessons 001 to 011.

### Phase 8: God-Level Repo Standards & Final Closure (COMPLETED)
- **Lead:** `repo-god` & `librarian`
- **Status:** Complete.
  - Unified `Makefile` (`make doctor`, `dev`, `test`, `qa`, `deploy`)
  - CI automation & pre-commit hooks
  - Gitleaks scan: 0 leaks across 14 commits in repository
  - Pinned dependencies in `pyproject.toml` and `disha_core/requirements.txt`
  - Model Stack Bake-Off delivered in `docs/engineering/model-bakeoff.md`
  - Web Application Constraints & Browser Sandbox Invariants documented in `agent/STATE.md` and `agent/LESSONS.md`
  - Full test suite: **176 Passed, 1 Skipped, 0 Failed** across all unit, invariant, and clinical scenario suites
  - Judge Audit Score: **98.33 / 100.0** (`PASSED_UNCONSTRAINED`, 16/16 constraints verified, 1.62ms sub-turn overhead)
