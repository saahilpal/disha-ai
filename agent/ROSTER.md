# DISHA AI — ENGINEERING ROSTER (MASTER ORDER v4)
**Branch Target**: `integrate/v4`  
**Orchestrator**: BossEmployee (AI Architecture Lead & Engineering Manager)  
**Status Policy**: Active heartbeats tracked in `agent/TRACKER.md`  

---

| ID | Handle | Role | Worktree / Path | Branch | Owned Globs | Assigned Skills | Status | Last Check-In |
|---|---|---|---|---|---|---|---|---|
| **01** | `architect` | Architect | `.` (Core Engine) | `integrate/v4` | `disha_core/engine/**`, `disha_core/pipeline/**`, `disha_core/config.py` | `agentic-engineering`, `cost-aware-llm-pipeline`, `python-patterns` | ACTIVE | 2026-11-08 23:23 |
| **02** | `knowledge-eng` | Knowledge Engineer | `.` (Data Engine) | `integrate/v4` | `disha_core/db/seed*`, `disha_core/db/ingest*`, `docs/knowledge/**` | `postgres-patterns`, `python-patterns` | ACTIVE (Spawned) | 2026-11-08 23:23 |
| **03** | `retrieval-eng` | Retrieval Engineer | `.` (Search & Index) | `integrate/v4` | `disha_core/engine/retriever.py`, `disha_core/adapters/db.py` | `postgres-patterns`, `python-patterns` | STANDBY | 2026-11-08 23:23 |
| **04** | `memory-pep-eng` | Memory & PEP Engineer | `.` (Memory Subsystem) | `integrate/v4` | `disha_core/engine/context_builder.py`, `disha_core/pipeline/validator.py`, `disha_core/models/**` | `postgres-patterns`, `python-patterns` | DONE (Loop 1 Verified) | 2026-11-08 23:40 |
| **05** | `conv-policy-eng` | Conversation Policy Engineer | `.` (Coaching Quality) | `integrate/v4` | `disha_core/services/chat_service.py`, `disha_core/engine/anti_echo.py`, `disha_core/llm/**` | `bengali-nlp`, `python-patterns` | ACTIVE (Loop 1 Prep) | 2026-11-08 23:23 |
| **06** | `safety-eng` | Safety Engineer | `.` (Safety Layer) | `integrate/v4` | `disha_core/pipeline/validator.py`, `disha_core/security/**` | `security-review`, `python-testing` | ACTIVE (Loop 1 Prep) | 2026-11-08 23:23 |
| **07** | `speech-eng` | Speech Engineer | `.` (Audio & Voice) | `integrate/v4` | `disha_core/routers/voice.py`, `disha_core/voice.py`, `docs/VOICE_PIPELINE.md` | `python-patterns` | ACTIVE (Bake-off Prep) | 2026-11-08 23:23 |
| **08** | `backend-db-eng` | Backend/DB Engineer | `.` (API & Database) | `integrate/v4` | `disha_core/main.py`, `disha_core/adapters/db.py`, `disha_core/db/**` | `backend-patterns`, `postgres-patterns` | ACTIVE (Persistence) | 2026-11-08 23:23 |
| **09** | `art-director` | Art Director & UX Writer | `.` (Product & Brand) | `integrate/v4` | `docs/design/**`, `frontend/*.html`, `disha_core/frontend/*.html` | `frontend-design`, `frontend-design-direction`, `brand-voice` | ACTIVE (Audit) | 2026-11-08 23:23 |
| **10** | `frontend-eng` | Frontend Engineer | `.` (Client Application) | `integrate/v4` | `frontend/**`, `disha_core/frontend/**` | `make-interfaces-feel-better`, `webapp-testing` | ACTIVE (Purge & Clean) | 2026-11-08 23:23 |
| **11** | `eval-qa-eng` | Eval/QA Engineer | `.` (Quality & Evaluation) | `integrate/v4` | `disha_core/tests/eval/**`, `docs/eval*` | `python-testing`, `agent-self-evaluation` | DONE (Loop 1 Verified) | 2026-11-08 23:35 |
| **12** | `breaker` | Breaker (Chaos & Edge-Cases) | `.` (Adversarial Testing) | `integrate/v4` | `tests/test_breaker*`, `tests/chaos/**` | `python-testing` | ACTIVE (Chaos Prep) | 2026-11-08 23:23 |
| **13** | `repo-cleaner` | Repo Cleaner & Docs Engineer | `.` (Hygiene & Docs) | `integrate/v4` | `docs/**`, `Makefile`, `.gitignore`, `scripts/repo-check` | `coding-standards`, `conventional-commit-review` | ACTIVE (Pass 1) | 2026-11-08 23:23 |
| **14** | `skeptic` | Skeptic (Contrarian Auditor) | `.` (Verification & Audit) | `integrate/v4` | `agent/LESSONS.md`, `agent/TRACKER.md` | `council`, `agent-introspection-debugging` | ACTIVE (Audit) | 2026-11-08 23:23 |

