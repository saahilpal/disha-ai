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

## GATE 1 VERIFICATION SIGN-OFF (2026-11-08)

| Gate 1 Condition | Target Standard | Measured Verification Status | Evidence Path |
|---|---|---|---|
| **Baseline Committed** | Clean baseline commit on branch | ✅ PASSED (`1a94a5a`, branch `integrate/v4`) | `git status`, `git branch` |
| **Persistence & Journal Live** | DB-backed session journal & memory | ✅ PASSED (`turn_journal`, `memory_items`, `call_summaries` live in PostgreSQL; state rehydration on reconnect) | `disha_core/engine/context_builder.py`, `disha_core/db/schema.sql` |
| **Hardcode Findings Migrated** | 0 clinical rules / prices in Python code | ✅ PASSED (15 product facts, 8 sources, 485 chunks seeded; 0 orphan chunks) | `docs/knowledge/HARDCODE_AUDIT.md`, `test_knowledge_provenance.py` |
| **Zero LLM Clinical Permissions** | LLM cannot grant exercise clearance | ✅ PASSED (Deterministic interceptor in `validator.py`, 0 LLM permissions) | `disha_core/models/slots.py`, `test_memory_pep_retrieval.py` |
| **Red-Flag Recall 100%** | Emergency preemption with 0 misses | ✅ PASSED (100% recall on acute cardiac/respiratory/crisis, 3.70ms latency) | `docs/eval_report_baseline.md` (TC20) |
| **Inventory & Bake-Off Tables Done**| Published datasets & empirical audio tests | ✅ PASSED (ICMR/IFCT/AYUSH inventory + Apple M5 Qwen3/Edge-TTS bake-off + UI audit) | `docs/knowledge/INVENTORY.md`, `docs/VOICE_PIPELINE.md`, `docs/design/ELEMENT_AUDIT.md` |
| **Repo-Check Passes** | Clean security, lint, files, tests | ✅ PASSED (Gitleaks 0 leaks, Ruff clean, 0 dead files, 139/139 tests passed in 29.30s) | `scripts/repo-check`, `Makefile` |

---


