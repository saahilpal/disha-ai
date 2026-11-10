# Disha AI — Change Rationale Ledger (docs/changes/WHY.md)

Every non-trivial modification to the repository must be recorded in this ledger with its architectural justification, evidence/metric delta, affected paths, and safety classification.

---

### [CHANGE-001] Synapse MCP SQLite Comment Syntax Fix
- **Date**: 2026-11-09
- **Reason**: Synapse MCP was crashing on `OperationalError: unrecognized token: "#"` when calculating caller blast radius, blocking token-saving navigation for all agent sessions.
- **Evidence/Metric**: Fixed SQL string extraction in `synapse/src/synap_git/storage/sqlite.py:894`. `synap mcp verify` succeeded 100% across all 5 verification checks.
- **Files**: `/Users/nitrousoxide/Code/synapse/src/synap_git/storage/sqlite.py`
- **Safety**: Pure syntax correction; eliminates runtime crashes.

---

### [CHANGE-002] Alembic Version Table Column Widening
- **Date**: 2026-11-09
- **Reason**: Alembic failed with `DataError: value too long for type character varying(32)` during `alembic upgrade head` because migration revisions exceed 32 characters.
- **Evidence/Metric**: Widened `alembic_version.version_num` to `VARCHAR(64)` and applied migrations `0004_approved_condition_tag_index` and `0005_runtime_schema_alignment` with clean exit code 0.
- **Files**: PostgreSQL schema, `migrations/versions/0004_approved_condition_tag_index.py`, `migrations/versions/0005_runtime_schema_alignment.py`
- **Safety**: Safe additive DDL modification.

---

### [CHANGE-003] Strict Zero-Pricing Invariant & Disallowed Commercial Inventions
- **Date**: 2026-11-09
- **Reason**: User explicitly demanded complete removal of invented prices (₹1,499, ₹0) and commercial consultation claims. Disha AI is free and has no paid tiers.
- **Evidence/Metric**: Updated `disha_core/config.py` and `disha_core/pipeline/validator.py` (`PRICING_REPLACEMENT = "Disha AI ke paas koi paid plans ya pricing nahi hai."`). Zero pricing claims emitted across all tests.
- **Files**: `disha_core/config.py`, `disha_core/pipeline/validator.py`, `disha_core/tests/test_invariants.py`, `disha_core/tests/test_reasoning_and_quality.py`
- **Safety**: Clinical and business truth preservation; protects users from commercial deception.

---

### [CHANGE-004] Gym Clearance Claims Eradication
- **Date**: 2026-11-09
- **Reason**: User strictly forbade any mention or claim of "gym clearance", which is a clinical certification requiring physician sign-off and cannot be self-asserted or granted by AI.
- **Evidence/Metric**: Removed `#profile-page-gym-clearance` and `Gym Clearance:` DOM badges from frontend. Verified in Playwright and diagnostic checks.
- **Files**: `disha_core/frontend/index.html`, `tests/test_frontend_diagnostics.js`
- **Safety**: Critical patient safety invariant.

---

### [CHANGE-005] Hardcode & Secrets Hygiene Checker
- **Date**: 2026-11-09
- **Reason**: Security requirement that zero credentials, hardcoded passwords, or unapproved commercial strings ever reach git or production.
- **Evidence/Metric**: Built `scripts/hardcode-check` and integrated into `scripts/repo-check`. Scanned 180 files: 0 violations found.
- **Files**: `scripts/hardcode-check`, `scripts/repo-check`
- **Safety**: Eliminates credential leakage risk.

---

### [CHANGE-006] Unified Pydantic TurnContext Schema
- **Date**: 2026-11-09
- **Reason**: Final Fix Order v5 Section 1.3: replace scattered per-component context dictionaries with a single typed Pydantic v2 `TurnContext` flowing from ASR through TTS.
- **Evidence/Metric**: Created `disha_core/models/turn_context.py` with sectioned models, stage timing telemetry, and PHI-safe redaction (`to_phi_safe_dict()`). Added component contract to `docs/contracts.md`.
- **Files**: `disha_core/models/turn_context.py`, `disha_core/models/__init__.py`, `docs/contracts.md`
- **Safety**: Type-safe context passing, eliminates race conditions and global state leakage.

---

### [CHANGE-007] Architecture Living Diagrams & Automated Validation
- **Date**: 2026-11-09
- **Reason**: Final Fix Order v5 Section 3: living Mermaid diagrams for all 7 core architectures with an automated verification script.
- **Evidence/Metric**: Created 7 diagrams in `docs/architecture/` and built `scripts/diagram-check` validating all diagrams and components against real code symbols.
- **Files**: `docs/architecture/*.md`, `scripts/diagram-check`
- **Safety**: Eliminates architectural drift between documentation and production code.

---

### [CHANGE-008] Behavior Spec v1 Implementation & Zero-Drift Single Source of Truth
- **Date**: 2026-11-10
- **Reason**: Owner provided final Behavior Spec v1. Replaces bloated 1,446-token prompt, removes canned fallbacks, enforces History Triangle (C1), no-advice boundaries (C2), zero-echo (F1), single question (F2), and WhatsApp length (P6/F3).
- **Evidence/Metric**: Created `data/behavior_rules.yaml`. Prompt rendered dynamically at 585 tokens (59.5% reduction) with version hash (`v1-9f113b222df1`). Added 25 unit tests in `tests/test_behavior_spec_v1.py` (all passing). Full test suite: 164 passed in 9.03s.
- **Files**: `data/behavior_rules.yaml`, `disha_core/llm/client.py`, `disha_core/harness/perception.py`, `disha_core/harness/verifier.py`, `disha_core/harness/repair.py`, `disha_core/harness/harness.py`, `disha_core/services/chat_service.py`, `disha_core/main.py`, `disha_core/frontend/app.js`, `tests/test_behavior_spec_v1.py`, `docs/spec/*`.
- **Safety**: Clinical safety invariants enforced deterministically; emergency breaker (<5ms) and C2 boundary tables validated before display. Gated by `BEHAVIOR_SPEC_V1` flag for instant rollback.
