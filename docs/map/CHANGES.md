# Disha AI — Forensic Change Audit (CHANGES.md)

**Generated:** 2026-11-07  
**Branch:** `v2/remap` (branched from `pre-agent-audit` tag at commit `458caf1`)  
**Base:** `db200a7` (origin/main)

---

## 1. Commit and Reflog Trajectory

1. **Commit `4a825d6` (Initial Prototype):**
   - Author: Sahil Pal
   - Added `app/`, `docs/01-12`, `tests/`.
   - SQLite database (`data/disha_clinical.db`), vanilla JS frontend in `app/static/`, static prompt templates, naive guardrails.

2. **Commit `73f009e` (Architecture Docs):**
   - Expanded system architecture diagrams (`docs/01-15`).

3. **Commit `a9cbf46` (Transition to `disha_core`):**
   - Introduced `disha_core/` replacing `app/`.
   - Transitioned from SQLite to PostgreSQL 16 with `pg_trgm` lexical search.
   - Introduced SHA-256 Merkle audit chain ledger (`disha_core/compliance/ledger.py`).
   - Split frontend into duplicate roots: `frontend/` and `disha_core/frontend/`.

4. **Commit `db200a7` (UI Sync & Telephony Tokens):**
   - Refactored frontend styling to use clinical color palette tokens.
   - Replaced old green gradients with muted sage and warm alabaster.
   - Added byte-for-byte synchronization between `frontend/` and `disha_core/frontend/`.

5. **Commit `458caf1` / `pre-agent-audit` Tag:**
   - **Laya Integration:** Added `disha_core/classifier/adapter.py`, `schemas.py`, and `__init__.py`. Replaced dummy classifier with genuine `laya==0.4.27` adapter supporting both containerized `laya-serve` and in-process `laya.Agent`.
   - **Vercel API Routes:** Added `frontend/api/auth/login.js`, `patient/profile.js`, `health.js`, `ready.js` to resolve 404 NOT_FOUND on Vercel deployment.
   - **Judge Upgrade:** Upgraded `audit/judge.py` to 10 weighted dimensions totaling 100%, with hard caps for constraint violations, stubbed Laya, and blocking UX defects.
   - **Clinical Apothecary UI:** Rebuilt SPA routing (`#/home`, `#/consultation`, `#/signin`, `#/summary`, `#/settings`, `#/privacy`), added acoustic stethoscope canvas, wake lock, device selector, consent modal, and consultation summary view.

---

## 2. File-by-File Behavioral Impact Analysis

| File | Nature of Change | Prior Behavior | Current Behavior | Risk / Regression Note |
|---|---|---|---|---|
| `disha_core/classifier/adapter.py` | Added | Non-existent; pipeline router used regex or stub | Full Laya System 1 decision engine with 32-case verified domain test | Requires `torch` and `transformers` or running `laya-serve` container |
| `disha_core/pipeline/router.py` | Modified | Hardcoded rule classifier | `LayaIntentClassifier` delegating to `LayaClassifierAdapter` | Safe fallback to regex on exception or event loop conflict |
| `disha_core/main.py` | Modified | Router only checked regex | Initialized with Laya adapter in lifespan | Voice WebSocket checks breaker directly; router injected in `_turn_sentences` |
| `frontend/app.js` & `disha_core/frontend/app.js` | Modified | Monolithic script (~950 lines) | Modular SPA controller (~2096 lines) handling 7 routes | Duplicate files across two roots (`jscpd` detects 50.2% duplication) |
| `frontend/index.html` & `disha_core/frontend/index.html` | Modified | Basic landing page | Complete Clinical Apothecary UI with consent modal, audio visualizers, summary view | Retains legacy DOM IDs for backward test compatibility |
| `frontend/style.css` & `disha_core/frontend/style.css` | Modified | Minimal styles (~65 lines) | High-craft design token system (~2575 lines) with light/dark themes | Zero neon halos, zero purple gradients; verified WCAG contrast |
| `frontend/api/*` & `disha_core/frontend/api/*` | Added | None (Vercel returned 404 on API calls) | Node.js Serverless handlers for `/auth/login`, `/patient/profile`, `/health`, `/ready` | Deployed and verified on `https://disha-ai-gray.vercel.app` |
| `docker-compose.yml` | Existing | References external volume | Fails on clean clone without manual volume creation | Needs fix: remove `external: true` for automatic volume provisioning |
| `docker-compose.prod.yml` | Added | None | Multi-service production stack with `laya-classifier` container | Runs Laya on port 8005 with health checks |

---

## 3. Clean-Clone Failures Identified

1. **Missing `.env`:** Fresh clone does not copy `.env.example` automatically; running `python -m audit.judge` fails with `ModuleNotFoundError: No module named 'dotenv'` if virtual environment is not activated.
2. **Docker External Volume Error:** `docker-compose.yml` defines `disha_core_postgres_data` with `external: true`. On a pristine host, running `docker compose up -d` immediately crashes because Docker cannot find an existing external volume.
3. **Frontend Duplication:** `frontend/` and `disha_core/frontend/` are 100% duplicated, requiring dual maintenance.
