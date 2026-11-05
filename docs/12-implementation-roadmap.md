# 12. Implementation Roadmap & Milestones — Disha Clinical Voice AI

## 1. Milestone Breakdown & Phased Execution

The implementation plan is structured into eight logical, testable milestones to ensure continuous verification:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          IMPLEMENTATION ROADMAP                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ Milestone 1: Database & Seed Data Layer (SQLite, FTS5, Schemas)             │
│ Milestone 2: Deterministic Safety Spine (Pre/Post Guardrails & Circuit Breaker)│
│ Milestone 3: Hybrid Knowledge Retrieval Engine (FTS5 + FastEmbed + JIT)     │
│ Milestone 4: Conversational Brain & Voice Turn Orchestrator (Groq / Offline) │
│ Milestone 5: Audio Ingestion & Streaming Speech Synthesis (Whisper + edge-tts)│
│ Milestone 6: Clinical Authoring Studio & Interactive Simulator UI           │
│ Milestone 7: Automated Golden Regression Test Suite & Mutation Harness      │
│ Milestone 8: Latency Benchmarks, End-to-End Stress Testing & Review         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Milestone Details & Deliverables

### Milestone 1: Database & Seed Data Layer
- **Deliverables:**
  - `app/db/connection.py`: Thread-safe SQLite connection manager with WAL mode.
  - `app/db/schema.sql`: Complete DDL definitions for rules, stances, capabilities, patients, PEPs, diet charts, and audit logs.
  - `app/db/init_db.py`: Database initializer with rich clinical seed data addressing all 8 known production failure modes.
- **Verification Criteria:**
  - Automated database creation runs without errors.
  - FTS5 virtual table queries return sub-millisecond BM25 matches.

### Milestone 2: Deterministic Safety Spine
- **Deliverables:**
  - `app/guardrails/pre_turn_emergency.py`: Pre-turn emergency regex & Aho-Corasick circuit breaker (<0.5ms).
  - `app/guardrails/post_turn_sanitizer.py`: Post-turn regex interceptor for persona protection, WhatsApp filtering, and pricing bounds.
  - `app/guardrails/lexicon.py`: Comprehensive Hinglish & English red-flag dictionary.
- **Verification Criteria:**
  - 100% detection of chest pain, left arm numbness, shortness of breath, and suicidal ideation.
  - Automatic interception of WhatsApp promises and fake prices.

### Milestone 3: Hybrid Knowledge Retrieval Engine
- **Deliverables:**
  - `app/knowledge/retriever.py`: Hybrid search engine combining exact tag matching, SQLite FTS5 BM25, and semantic vector similarity.
  - `app/knowledge/patient_grounding.py`: Dynamic resolver pulling today's dinner from `patient_diet_plans` and gym permissions from `patient_pep`.
- **Verification Criteria:**
  - Query for "period bloating" returns warm jeera/saunf water protocol in <5ms.
  - Query for "dinner" fetches exact patient meal record.

### Milestone 4: Conversational Brain & Turn Orchestrator
- **Deliverables:**
  - `app/llm/client.py`: Groq Cloud client supporting `llama-3.3-70b-versatile` with automatic failover to `llama-3.1-8b-instant`.
  - `app/llm/offline_fallback.py`: Zero-dependency mock LLM engine for 100% offline development and testing.
  - `app/orchestrator/turn_manager.py`: End-to-end turn execution coordinating guardrails, retrieval, LLM, and audit persistence.
- **Verification Criteria:**
  - Turn execution generates empathetic 1–2 sentence Hinglish responses adhering to retrieved clinical remedies.

### Milestone 5: Audio Ingestion & Streaming Speech Synthesis
- **Deliverables:**
  - `app/audio/stt.py`: Groq Whisper client with clinical vocabulary prompt biasing.
  - `app/audio/tts.py`: `edge-tts` async streaming wrapper (`hi-IN-SwaraNeural`).
- **Verification Criteria:**
  - Speech transcription correctly spells Hinglish clinical terms (*"jeera"*, *"bloating"*).
  - Audio synthesis produces streaming MP3 chunks in <250ms.

### Milestone 6: Clinical Authoring Studio & Simulator UI
- **Deliverables:**
  - `app/static/index.html` & `app/static/app.js`: Clean, modern web application providing:
    1. **Live Voice & Text Simulator:** Real-time microphone input, audio playback, latency waterfall, and guardrail telemetry.
    2. **Clinical Rule Authoring Studio:** Form to add/edit rules and stances without code changes.
    3. **Patient Encounter Profile (PEP) Viewer:** Live inspection of patient diet charts and exercise permissions.
    4. **Care Ops Alert Console:** Real-time log of emergency escalations.
- **Verification Criteria:**
  - Clinician can type a Hinglish utterance and see immediate audio playback and step-by-step debug traces.

### Milestone 7: Automated Golden Regression Test Suite
- **Deliverables:**
  - `tests/test_clinical_failures.py`: Pinned test suite explicitly verifying all 8 production failure modes.
  - `tests/test_guardrails.py`: Sub-millisecond latency and recall tests for safety gates.
  - `tests/test_regression_runner.py`: Pre-publishing simulation gate preventing regressions.
  - `tests/test_defect_injection.py`: Mutation test auditing the test harness.
- **Verification Criteria:**
  - 100% pass rate across the 8 production failure test cases.

### Milestone 8: Latency Benchmarks, Documentation & Final Review
- **Deliverables:**
  - `tests/benchmark_latency.py`: End-to-end turn latency profiling under simulated call load.
  - Architecture Draw.io diagrams (.drawio).
  - Final comprehensive project documentation.
- **Verification Criteria:**
  - P95 turn latency verified under 1,200ms.
  - Complete test suite passing with zero defects.
