# DISHA AI — ENGINEERING TASK TRACKER

| Task ID | Task Description | Owner | Status | Dependencies | Test Evidence / Metrics |
|---------|------------------|-------|--------|--------------|--------------------------|
| W0-01 | Baseline Inventory & Secret Scrub | Boss / Agent F | DONE | None | `audit/disha-fit/evidence/blog_raw.html` key scrubbed, 0 secrets in repo |
| W0-02 | Invariant Testing & Unit Test Suite | Agent H | DONE | W0-01 | 113/113 passing across 6 suites in 27.76s |
| W0-03 | Local Ollama (`qwen2.5:7b`) Failover | Agent G | DONE | W0-01 | `docker-compose.yml` configured, `host.docker.internal:11434` responsive |
| W1-01 | Dynamic Length Policy & Anti-Echo Filter | Agent A | DONE | W0-02 | `disha_core/engine/anti_echo.py`, 17/17 tests passing in `test_reasoning_and_quality.py` |
| W1-02 | Laya Clinical Intent Classifier v2 & Routing | Agent B | DONE | W0-02 | `2026-11-08.v2` schema, non-clinical DB bypass, early PEP triage |
| W1-03 | Hybrid Database Retrieval & PEP Persistence | Agent C | DONE | W0-02 | PostgreSQL `patient_turn_journal`, `patient_temporal_facts`, 7/7 tests passing |
| W1-04 | Qwen3-TTS & Speech Pipeline Real-Time | Agent D | DONE | W0-02 | `stream_qwen3_tts`, Hinglish phonetic normalizer, 12/12 tests passing |
| W1-05 | 25-Scenario Golden Dataset & Benchmark Runner | Agent E / Boss | DONE | W0-02 | `golden_dataset.json` (25 clinical scenarios), `run_eval.py` (12 dimensions) |
| W2-01 | Backend Security Limiting & Zero-PHI Scrubbing | Agent F | DONE | W0-02 | 20 auth/min, 60 chat/min, 2MB body limit, 23/23 tests passing |
| W2-02 | Responsive UI/UX Centering & Dose Theme | Agent I | DONE | W0-02 | Hallmark sloplint `0 FAIL, 0 REFLEX, 0 WARN`, Playwright 8/8 passing |
| W2-03 | Validator Sentence Deduplication & False Positives | Boss | DONE | W1-01 | Deduplication in `sentence_buffer.py`, specific workout regex in `validator.py` |
| W3-01 | Golden Benchmark Execution & Baseline Scoring | Boss / Agent H | DONE | W2-03 | 25/25 passed (100.0%), avg latency 4.05s, 0 hallucinations |

## Master Order v4 — Loop 1 Tracking (Foundation & Persistence)

| Task ID | Task Description | Owner | Status | Dependencies | Target / Evidence Path |
|---|---|---|---|---|---|
| L1-01 | Capability Discovery & Machine Audit | BossEmployee | DONE | None | `agent/CAPABILITIES.md` (CLI, Apple M5 Metal, Ollama, Docker) |
| L1-02 | 14-Agent Specialist Roster Launch | BossEmployee | DONE | L1-01 | `agent/ROSTER.md` (Target branch: `integrate/v4`) |
| L1-03 | Knowledge Dataset Inventory & Provenance | `knowledge-eng` | DONE | L1-02 | `docs/knowledge/INVENTORY.md`, `knowledge_sources` (8 sources), `knowledge_chunks` (485 chunks, 100% provenance verified), 4/4 tests passing in `test_knowledge_provenance.py` |
| L1-04 | Hardcode Knowledge Audit & Migration Script | `knowledge-eng` | DONE | L1-02 | `docs/knowledge/HARDCODE_AUDIT.md`, `migrations/versions/0003_knowledge_and_product_facts.py`, `seed_product_facts.sql` (15 rows), `seed_knowledge_chunks.sql` |
| L1-05 | 12-Dimension Baseline Eval Run & JSON | `eval-qa-eng` | DONE | L1-02 | `docs/eval_report_baseline.json`, `docs/eval_report_baseline.md` (25/25 100%, avg 2273ms, p50 1566ms, p95 3634ms, safety 3.7ms, PEP 13.55ms) |
| L1-06 | Slot Registry & Turn Journal Persistence | `memory-pep-eng` | DONE | L1-02 | `disha_core/models/slots.py` (8 canonical slots, trilingual EN/HI/Hinglish), `turn_journal`, `memory_items`, `call_summaries`, 0 LLM permissions guard, 24/24 tests passing in `test_memory_pep_retrieval.py` |
| L1-07 | TTS Bake-Off & Language-Routed Engine | `speech-eng` | DONE | L1-02 | `docs/VOICE_PIPELINE.md`, language routing in `voice.py`, barge-in <50ms, 17/17 tests passing |
| L1-08 | UI Element Audit & Design Brief (Zero Slop) | `art-director` | DONE | L1-02 | `docs/design/ELEMENT_AUDIT.md`, `docs/design/brief.md` (WCAG AAA, 3-language copy, zero slop) |
| L1-09 | Repo Clean Pass 1 & `scripts/repo-check` | `repo-cleaner` | DONE | L1-02 | `scripts/repo-check`, `Makefile` `repo-check` target, `.gitleaks.toml` (0 secrets across 23 commits + working tree), frontend symlink consolidation (`frontend -> disha_core/frontend`), `.gitignore` hardened, ruff 100% clean, 139/139 tests passing |
| L1-10 | Loop 1 Integration & Gate 1 Verification | BossEmployee | DONE | L1-03..09 | Gate 1 Checklist PASSED: Baseline committed, persistence/journal live in PostgreSQL, 485 chunks + 15 product facts migrated with 0 orphan chunks, 0 LLM clinical permissions, 100% red-flag recall (3.7ms), inventory & bake-off docs complete, `make repo-check` passed (139/139 tests green, 0 secrets, 0 lint errors, 0 dead files). |

---

## Master Order v4 — Loop 2 Tracking (PEP Habits Engine, Ground-Up Frontend & Policy)

| Task ID | Task Description | Owner | Status | Dependencies | Target / Evidence Path |
|---|---|---|---|---|---|
| L2-01 | Decide-Then-Speak & Follow-Up Question Policy | `conv-policy-eng` | DONE | L1-10 | `disha_core/services/chat_service.py`, max 1 follow-up, progressive profiling, unsupported language deflection |
| L2-02 | PEP Habits Scale Architecture & Storage Engines | `pep-habits-eng` | DONE | L1-10 | 3 shapes (current_state with partial index & hysteresis, time_series with BRIN & rollups, episodes), unified `get_pep(patient_id)`, nightly consolidation job `scripts/consolidate_pep_habits.py` |
| L2-03 | 1,000 Patient × 24-Month Scale Benchmark | `pep-habits-eng` | DONE | L2-02 | `tests/test_pep_habits_scale.py`: p95 = 0.58ms fetch (<= 30ms required), <= 400 tokens brief, 24-month stability |
| L2-04 | Ground-Up Slop-Free Frontend Rebuild & Journey View | `frontend-eng` | DONE | L1-10 | `docs/design/refs.md`, `docs/design/spec.md`, flat tokens, 1 font, 1 accent, `GET /patient/journey` stage view, profile edit modal with vitals, gender & language |
| L2-05 | Breaker Chaos Suite & 8 Failure Scenarios Benchmark | `breaker` / `eval-qa-eng` | DONE | L1-10 | `tests/test_breaker_chaos.py` (65/65 passing: language deflection, prompt injection defense, contradiction quarantine, barge-in <50ms [0.35ms], DB downtime circuit breaker, 8 failure scenarios 100%), `tests/test_pep_exercise_suitability.py` (10/10 passing) |
| L2-06 | Skeptic Independent Gate 1 Re-Verification | `skeptic` | DONE | L1-10 | Clean checkout reproduction of all Gate 1 checks in `docs/gate1_skeptic_audit.md` |
| L2-07 | Loop 2 Integration & Gate 2 Verification | BossEmployee | DONE | L2-01..06 | Gate 2 Checklist in `agent/TRACKER.md` |

## GATE 1 VERIFICATION SIGN-OFF (2026-11-08)

| Gate 1 Condition | Target Standard | Measured Verification Status | Evidence Path |
|---|---|---|---|
| **Baseline Committed** | Clean baseline commit on branch | ✅ PASSED (`1a94a5a`, branch `integrate/v4`) | `git status`, `git branch` |
| **Persistence & Journal Live** | DB-backed session journal & memory | ✅ PASSED (`turn_journal`, `memory_items`, `call_summaries` live in PostgreSQL; state rehydration on reconnect) | `disha_core/engine/context_builder.py`, `disha_core/db/schema.sql` |
| **Hardcode Findings Migrated** | 0 clinical rules / prices in Python code | ✅ PASSED (15 product facts, 8 sources, 485 chunks seeded; 0 orphan chunks; marked provisional / owner-verify) | `docs/knowledge/HARDCODE_AUDIT.md`, `test_knowledge_provenance.py` |
| **Zero LLM Clinical Permissions** | LLM cannot grant exercise clearance | ✅ PASSED (Deterministic interceptor in `validator.py`, 0 LLM permissions) | `disha_core/models/slots.py`, `test_memory_pep_retrieval.py` |
| **Red-Flag Recall 100%** | Emergency preemption with 0 misses | ✅ PASSED (100% recall on acute cardiac/respiratory/crisis, 3.70ms latency) | `docs/eval_report_baseline.md` (TC20) |
| **Inventory & Bake-Off Tables Done**| Published datasets & empirical audio tests | ✅ PASSED (ICMR/IFCT/AYUSH inventory + Apple M5 Qwen3/Edge-TTS bake-off + UI audit) | `docs/knowledge/INVENTORY.md`, `docs/VOICE_PIPELINE.md`, `docs/design/ELEMENT_AUDIT.md` |
| **Repo-Check Passes** | Clean security, lint, files, tests | ✅ PASSED (Gitleaks 0 leaks, Ruff clean, 0 dead files, 139/139 tests passed in 29.30s) | `scripts/repo-check`, `Makefile` |

---

## GATE 2 VERIFICATION SIGN-OFF (2026-11-09)

| Gate 2 Condition | Target Standard | Measured Verification Status | Evidence Path |
|---|---|---|---|
| **PEP Habits Scale Architecture** | 1,000 pt × 24-mo p95 fetch <= 30ms, brief <= 400 tok | ✅ PASSED (Measured p95 = 0.58ms, brief ~310 tokens, nightly consolidation 2.33ms/pt) | `tests/test_pep_habits_scale.py`, `scripts/consolidate_pep_habits.py` |
| **5-Stage Patient Journey & Scheduler** | Progressive onboarding, max 1 q/turn, deduplicated | ✅ PASSED (17/17 tests passing, clinical priority sorting, 0 questions during off-topic/emergency, future stage capture) | `tests/test_patient_journey_scheduler.py`, `disha_core/journey/` |
| **8 Failure Scenarios Benchmark** | >= 90.0% pass rate across chaos scenarios | ✅ PASSED (8/8 scenarios passing at 100.0%, barge-in 0.35ms, 100% red-flag recall) | `tests/test_breaker_chaos.py` (Pillar 11) |
| **Skeptic Independent Audit** | Independent verification from clean checkout | ✅ PASSED (100% red flag recall, 485 chunks verified, regex bypasses closed) | `docs/gate1_skeptic_audit.md` |
| **Provisional Product Facts** | Verified or marked `provisional / owner-verify` | ✅ PASSED (15/15 rows in `product_facts` marked provisional / owner-verify) | `disha_core/db/schema.sql`, `test_knowledge_provenance.py` |
| **Zero Slop Frontend & Profile Journey** | WCAG AAA, no habit-viewing UI slop, journey stage | ✅ PASSED (`#memory-transparency-view` removed; `GET /patient/journey` wired to profile; edit modal expanded) | `disha_core/frontend/index.html`, `disha_core/frontend/app.js` |
| **Full Repo Check & Test Suite** | 0 secrets, 0 lint errors, 0 dead files, 100% green | ✅ PASSED (Gitleaks 0 leaks, Ruff 100% clean, 0 dead files, 224/224 automated tests green) | `bash scripts/repo-check` |

---

## Master Order v4 — Loop 3 Tracking (Harden, Unified RAG & Production Delivery)

| Task ID | Task Description | Owner | Status | Dependencies | Target / Evidence Path |
|---|---|---|---|---|---|
| L3-01 | Thin System Prompt Ablation (343 tokens) | `policy-eng` | DONE | L2-07 | Reduced `SYSTEM_PROMPT` in `disha_core/llm/client.py` from 1,155 tokens to 343 tokens (70.3% reduction, 0 hardcoded remedies) |
| L3-02 | 30-Day Multi-Session Longitudinal Simulation | `eval-qa-eng` | DONE | L2-07 | `tests/test_multi_session_30day_simulation.py` (8 sessions, Vikram Patel, schedule changes, hysteresis, symptom decay, 100% green) |
| L3-03 | Unified Indian Gov & WHO Exercise RAG | `knowledge-eng` | DONE | L3-02 | Fit India Movement (MoHFW), Ministry of AYUSH & MDNIY (Common Yoga Protocol), and WHO Guidelines 2020 ingested into `clinical_knowledge_base` and `knowledge_chunks` |
| L3-04 | Dataset-Driven PEP Exercise Engine | `pep-habits-eng`| DONE | L3-03 | Zero hardcoded dictionaries; dynamic JSON & PostgreSQL querying; deterministic clinical safety rules; 10/10 tests green in `test_pep_exercise_suitability.py` |
| L3-05 | Cloudflare Tunnel Watchdog & Public Ingress | `sre-lead` | DONE | L2-07 | Host watchdog daemon running (`PID 3991`), persistent edge ingress live at `https://constitution-maria-watts-fancy.trycloudflare.com`, 6/6 tests green in `test_tunnel_watchdog.py` |
| L3-06 | Full Quality, Security & Repo Clean Passes | `repo-cleaner` | DONE | L3-01..05 | 245/245 tests green, Gitleaks 0 leaks across 25 commits, Ruff 100% clean, 2 consecutive passes of `repo-check` |
| L3-07 | Loop 3 Integration & Gate 3 Final Sign-Off | BossEmployee | DONE | L3-01..06 | Production delivery sign-off in `agent/TRACKER.md` |

---

## GATE 3 VERIFICATION SIGN-OFF (2026-11-09)

| Gate 3 Condition | Target Standard | Measured Verification Status | Evidence Path |
|---|---|---|---|
| **30-Day Longitudinal Simulation** | 8 sessions across 30 days on single patient state | ✅ PASSED (Day 1 baseline to Day 30 consolidation; shift change archival; transient symptom decay; gym override rejection) | `tests/test_multi_session_30day_simulation.py` |
| **Thin System Prompt Policy** | System prompt <= 500 tokens, 0 hardcoded remedies | ✅ PASSED (343 tokens, 70.3% reduction, zero hardcoded remedies like jeera or mango) | `disha_core/llm/client.py` |
| **Unified RAG Knowledge Base** | Single fast retrieval over health, AYUSH & exercise | ✅ PASSED (14 official Fit India, AYUSH Yoga CYP & WHO 2020 exercise chunks ingested into PostgreSQL, <2ms hybrid trgm+FTS retrieval) | `disha_core/db/seed_unified_exercise_rag.sql`, `disha_core/engine/retriever.py` |
| **Dataset-Driven Exercise Engine** | 0 hardcoded rules in Python code | ✅ PASSED (Dynamic dataset loader with official citations from Fit India, AYUSH & WHO; 10/10 tests passing) | `disha_core/pep/exercise_engine.py`, `tests/test_pep_exercise_suitability.py` |
| **Cloudflare Edge Ingress** | Supervised tunnel watchdog, 0ms cold starts | ✅ PASSED (Watchdog PID 3991, edge URL `https://constitution-maria-watts-fancy.trycloudflare.com`, verified `/health` and UI) | `scripts/tunnel-watchdog.sh`, `agent/TUNNEL_URL.txt` |
| **Repository Invariants & Clean Passes** | 2 consecutive clean passes of `repo-check` | ✅ PASSED (2 consecutive full clean passes; Gitleaks 0 secrets, Ruff clean, 0 dead files, 245/245 automated tests passing) | `scripts/repo-check` |



