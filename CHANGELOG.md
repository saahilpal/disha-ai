# Changelog

All notable changes to the Disha AI platform are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Style Standard: Strict technical precision, zero emojis.

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
