# Changelog

All notable changes to the Disha AI platform are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Style Standard: Strict technical precision, zero emojis.

---

## [1.3.0] - 2026-11-10

### Added
- **Behavior Spec v1 (Owner-Provided Implementation)**:
  - Added `data/behavior_rules.yaml` as the canonical single source of truth for all 18 rules (P1-P6, F1-F5, C1-C4, M1-M3).
  - Added deterministic system prompt generation rendering `data/behavior_rules.yaml` into ≤600-token prompt (585 tokens) with version hash (`v1-9f113b222df1`) in `disha_core/llm/client.py`.
  - Added `TurnPerception` schema and deterministic precedence move selector in `disha_core/harness/perception.py`.
  - Added multilingual behavior rule verifiers in `disha_core/harness/verifier.py`: P3 (script & language mode), P4 (banned honorifics), P6/F3 (sentence count ≤3, char cap ≤450), F1 (zero-echo cross-script), F2 (at most 1 question), F4 (selective empathy gated on distress), and C2 (clinical boundary table).
  - Added `tests/test_behavior_spec_v1.py` with 25 unit tests validating all rules, precedence chain, and flag rollback.
  - Added first-run one-tap language choice modal in `disha_core/frontend/app.js` with localized options for Hinglish, हिन्दी, and English.
  - Added D5 silent 2-turn language switch in `disha_core/harness/harness.py`.
  - Added unified persistence endpoints `GET /chat/conversation` and `POST /chat/conversation/new` in `disha_core/main.py`.
  - Wired message and conversation recording for SSE streams (`POST /chat/stream`), sync turns (`POST /chat`), and voice WebSocket (`/voice`).
  - Added `data/i18n/{en,hi,hinglish}.yaml` and `data/c2_boundary.yaml` data catalogs.

### Changed
- Replaced 1,446-token prompt with 585-token versioned prompt, achieving a 59.5% token reduction.
- Replaced sentence-by-sentence chat streaming verification with whole-draft verification, guaranteeing turn-level conformance.
- Replaced canned answer-shaped fallback strings with LLM-only repair loop (max 2 attempts + 1 strict constrained regeneration).

---

## [1.2.0] - 2026-11-09

### Added
- **Onboarding State, Repetition Elimination & Conversational Empathy Suite**:
  - Added 10-scenario regression test suite in `tests/test_onboarding_conversation_rep.py` covering negative medical history, repeated meal requests, acknowledgments, direct demands, previously collected information deduplication, Hinglish phonetic parsing, cross-session persistence, stage progression UI isolation, emotional empathy for struggles, and token-efficient prompt discipline.
  - Added non-hardcoded provider API rate-limit advisory pill (`#call-advisory-pill`) on voice call screen with localized strings in `disha_core/frontend/locales/` (`en.json`, `hi.json`, `hinglish.json`).
  - Added granular field state classification in `load_or_create_journey`: `not_asked`, `asked_unanswered`, `answered_negatively`, `answered_positively`, `needs_clarification`.

### Fixed
- **Critical Medical Condition Question Loop & State Loss**:
  - Resolved root cause where negative responses (`"nhi"`, `"nahi"`, `"no"`, `"nope"`, `"na"`, `"nothing"`, `"kuch nahi"`) to pending onboarding questions were dropped by the disclosure extractor.
  - `extract_patient_disclosures` now resolves negative answers against `pending_field` contextually, storing `{"diagnosed_conditions": ["none"]}`.
  - `sync_known_fields_from_db` now queries `journey_question_history` for confirmed answered fields, preventing empty lists or missing fields from triggering repeated questions.
  - `record_field_answer` now updates both `patient_pep` and `patient_profiles` and marks all asked questions for the target field as `status = 'answered'`.
  - Question scheduler now enforces strict deduplication: answered questions (required or optional) are permanently excluded from candidate selection, preventing repeated questions.
  - Suppressed onboarding questions during active health/coaching inquiries (meal queries, symptoms, exercise) to address user's immediate need first.
- **Conversational Tone, Empathy & Response Discipline**:
  - Enhanced Structured Turn Planner in `disha_core/harness/planner.py` to perceive emotional struggles (stress, low motivation, guilt, cheat meals, setbacks) and schedule validation with genuine empathy while avoiding toxic positivity or blame.
  - Added repetition avoidance move: when user repeats inquiries (e.g. repeated "breakfast" requests), planner instructs fresh variety and alternatives rather than echoing identical food items.
  - Added clean handling for simple acknowledgments ("okay", "theek hai") to avoid re-explaining advice or spamming questions.
  - Added immediate execution for direct demands ("nhi jo hai de do") with concrete recommendations and zero follow-up preference questions.
  - Updated `SYSTEM_PROMPT` in `disha_core/llm/client.py` enforcing concise, token-efficient responses (2–4 focused sentences), sincere concern, warm Indian coaching voice, and zero robotic canned intros.
- **Chat UI Cleanliness & Telemetry Metadata Removal**:
  - Removed visible 5-stage onboarding progress indicator (`#chat-journey-banner`) from the chat shell; progression is now purely backend-driven.
  - Stripped internal retrieval and telemetry metadata (`Retrieval: ...`, `Sources: ...`) from user-facing chat bubbles via `.source-trace { display: none !important; }` and DOM suppression in `renderMessageProvenance`.

---

## [1.1.0] - 2026-11-09

### Added
- **Repository Architecture, Git Hygiene & CI/CD Hardening**:
  - Consolidated canonical test matrix into unified top-level `tests/` tree, deprecating scattered `disha_core/tests/` hierarchy.
  - Multi-stage GitHub Actions CI workflow in `.github/workflows/ci.yml` executing lint (Ruff), static typing (Pyright), tests (Pytest), secret audit (Gitleaks), vulnerability scan (Trivy), hardcode hygiene, docs drift, and architecture diagram checks.
  - Extended `scripts/hardcode-check` with an AST scanner flagging unexternalized user-facing natural language string literals in Python code outside `data/` and `i18n/`.
  - Added repository-wide code review governance in `.github/CODEOWNERS` and `CODEOWNERS`.
  - Added root `SECURITY.md` with vulnerability triage SLAs, responsible disclosure guidelines, and key rotation protocols.
  - Documented complete GitHub branch protection policy and click-path in `docs/runbooks/branch_protection.md`.
  - Prepared `main-clean` orphan branch structured with clean logical conventional commits.
- **Final Fix Order v5 Execution Framework**:
  - Expanded 16-specialist strike team roster in `agent/ROSTER.md` with owned globs, assigned skills, and step budgets.
  - Asynchronous agent coordination board in `agent/board/board.jsonl`, `scripts/board`, and auto-updating `agent/BOARD.md`.
  - Unified typed Pydantic v2 `TurnContext` in `disha_core/models/turn_context.py` with sectioned pipeline contract in `docs/contracts.md`.
  - PHI-safe per-turn telemetry traces (`to_phi_safe_dict()`) with SHA-256 utterance prefix hashing.
  - Living architecture Mermaid diagrams (01 through 07) in `docs/architecture/` verified by automated `scripts/diagram-check`.
  - Comprehensive documentation drift mapping in `docs/OWNERS.yaml` and change logs in `docs/changes/WHY.md` and `docs/DELETIONS.md`.
  - Turnkey local models script `scripts/local-models.sh` for Apple Silicon MLX audio and local Ollama inference.

### Changed
- **Zero-Pricing and Commercial Claims Invariant**:
  - Eradicated all hardcoded pricing assumptions (₹1,499 subscriptions and ₹0 consults) across configs, prompt builders, and validators.
  - Enforced strict replacement rule `Disha AI ke paas koi paid plans ya pricing nahi hai` on any detected currency or pricing claims.
- **Gym Clearance Terminology Purge**:
  - Completely purged invented `#profile-page-gym-clearance` elements and claims from the user interface.
- **Hardcode and Secrets Hygiene**:
  - Implemented `scripts/hardcode-check` detecting credentials, passwords, and commercial strings across 180 files.
  - Integrated hardcode-check into `scripts/repo-check` pre-commit and CI gates with zero violations.

### Fixed
- **Synapse MCP SQLite Parser Bug**:
  - Fixed syntax error in SQLite queries caused by Python comment strings inside multi-line SQL literals in `synapse/src/synap_git/storage/sqlite.py:894`.
- **Alembic Version Identifier Truncation**:
  - Widened `alembic_version.version_num` column from `VARCHAR(32)` to `VARCHAR(64)` in PostgreSQL, enabling successful application of migration revisions `0004` and `0005`.
- **Voice Privacy Consent Evaluation Order**:
  - Enforced `GROQ_HEALTH_DATA_PROCESSING_APPROVED` consent evaluation before calculating audio amplitude in `disha_core/voice.py`.

---

## [1.0.0-rc1] - 2026-11-08

### Added

- **Multi-Tier Memory Topology (L1 / L2 / L3):**
  - **Tier 1 (`patient_turn_journal`):** Immutable, append-only dialogue journal storing raw utterances, speaker labels, session identifiers, timestamps, verbatim quote spans, and cryptographic SHA-256 Merkle chain linkages. Replaces ephemeral RAM history.
  - **Tier 2 (`patient_temporal_facts`):** Bitemporal Entity-Attribute-Value (EAV-T) knowledge graph storing clinical and lifestyle facts across orthogonal Valid Time (`valid_time`) and Transaction Time (`transaction_time`) dimensions using PostgreSQL `tstzrange` and `btree_gist` indexing.
  - **Tier 3 (`patient_clinical_safety_profile`):** Deterministic, tamper-evident clinical safety store maintaining clinician-certified hypertension staging, gym clearance flags, exercise contraindications, allergies, and red-flag symptom patterns. Hardened with cryptographic SHA-256 integrity signatures verified on insert/update.
- **Formal State Transition Operators:**
  - Implemented finite state machine supporting five deterministic algebraic operators: `ADD`, `UPDATE`, `SUPERSEDE`, `NOOP`, and `CONTRADICT`.
  - Prohibits direct, uncurated SQL updates. Enforces atomic valid-time closure on predecessor facts during state updates.
- **Bi-Temporal Validity and Fact Taxonomy:**
  - Distinct categorization of facts into `acute` (24–72 hour TTL), `episodic` (24–48 hour TTL), `subacute` (7–14 day TTL), and `chronic` (indefinite validity).
  - Background asynchronous TTL Decay Daemon transitioning expired acute facts to `resolved` status without blocking real-time voice turns.
- **Core Memory Tools & API Interfaces:**
  - `fetchinformation`: Context-time selective memory and clinical guideline retrieval engine with domain filtering, temporal scoping, and guaranteed L3 safety injection.
  - `executeaction`: Deterministic lifestyle and scheduling execution engine with idempotency keys and pre-execution safety constraint validation.
  - `update_patient_memory`: Structured turn-completion writeback tool proposing candidate mutations grounded in L1 turn provenance.
- **Sub-400 Token JIT XML Serialization Engine:**
  - High-density, attribute-compact XML grammar (`<MEMORY>`, `<SAFETY>`, `<CHRONIC>`, `<ACUTE>`, `<GOALS>`, `<ANCHOR>`).
  - Benchmarked at 325 tokens (GPT-2 vocabulary) and 232 tokens (Llama-3 vocabulary), executing in 0.082ms on Apple Silicon M5 hardware.
- **Compliance and Privacy Modules (DPDP Act 2023):**
  - Explicit patient consent logging with timestamped proof.
  - Row-level patient isolation enforced via cryptographically signed JWT tokens.
  - Atomic stored procedure `purge_patient_memory` supporting the statutory Right to Erasure while preserving non-repudiation cryptographic audit logs.
  - Zero third-party cloud vector database dependencies; 100% data sovereignty within local PostgreSQL 16 Alpine container.
- **Longitudinal Golden Evaluation Suite:**
  - Integrated 7-day longitudinal benchmark suite (`audit/memory_golden_suite.json`) evaluating Information Retention Rate (IRR), Contradiction Resolution Accuracy (CRA), Temporal Validity Precision (TVP), and Safety Invariant Preservation (SIP).

### Changed

- **Session Context Pipeline:**
  - Migrated session memory from in-memory dictionary `app_state.conversation_history` in `disha_core/main.py` to persistent L1/L2 database storage. Eliminates total memory loss on server restart or container cycling.
- **Conversational Coaching Binding:**
  - Bound long-term memory retrieval and writeback directly into Disha's 5-Phase Coaching Lifecycle (Phase 1 Empathy, Phase 2 Triage, Phase 3 Grounding, Phase 4 Guidance, Phase 5 Confirmation).
- **Prompt Envelope Assembly:**
  - Deprecated flat context stuffing (~1200+ tokens) in favor of intent-directed JIT XML injection (<400 tokens), preserving the internal sub-650ms end-to-end voice latency target.

### Research Integrations

- **MedGraph (Knowledge Graph Grounding):**
  - Integrated structured entity-attribute relational graph semantics for medical dialogue state tracking and causal symptom-intervention trajectory maintenance.
- **Dual-Stream Reconciliation:**
  - Decoupled fast, synchronous turn reading (<15ms latency) from slow, asynchronous background memory consolidation ("Dreaming") to guarantee voice interactivity.
- **STAM (State-Transition-Aware Memory, Haghifam et al., 2024–2025):**
  - Implemented Active vs. History dual-store partitioning with explicit predecessor links (`superseded_by_fact_id`).
  - Enforced query-dependent store gating and conservative deletion policies to preserve longitudinal medical reasoning.

---

## [0.9.5] - 2026-11-07

### Added
- Multi-agent simulation audit suite (`scripts/run_15min_realistic_rohan.py`, `scripts/run_15min_adversarial_meera.py`, `scripts/run_15min_complex_kabir.py`).
- Laya System 1 intent classifier adapter (`disha_core/classifier/adapter.py`).
- 10-dimension automated judge and audit scorer (`audit/judge.py`).

### Changed
- Rebuilt frontend SPA with Clinical Apothecary theme and acoustic canvas visualizer.
- Hardened Merkle audit ledger with persistent SQLite WAL sidecar fallback (`audit_wal.db`).
