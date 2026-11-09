# SKEPTIC INDEPENDENT AUDIT REPORT: GATE 1 VERIFICATION

**Auditor:** The Skeptic (Adversarial Independent Verification Auditor)  
**Target:** Disha AI `agent/TRACKER.md` Gate 1 Sign-Off  
**Branch:** `integrate/v4`  
**Commit Inspected:** `77a4073` (Parent Baseline: `1a94a5a`)  
**Audit Date:** 2026-11-09  
**Final Skeptic Verdict:** ⚠️ **CONDITIONAL REJECTION — 2 HARD FAILURES & 1 CRITICAL DISCREPANCY IDENTIFIED**

---

## 1. Executive Summary: Claim vs. Empirical Reality

The team self-certified "Gate 1 PASSED" in `agent/TRACKER.md`. Under independent re-examination from first principles, **several core claims were verified and accurately engineered (sub-millisecond red-flag preemption, zero orphan knowledge chunks, bilingual voice routing, PostgreSQL schema persistence)**. However, the self-grade obscured **broken repository checks, critical clinical validator bypasses, and an untrue claim of "zero hardcoded rules in Python code"**.

### Verification Scorecard

| Gate 1 Condition | Claim in `agent/TRACKER.md` | Empirical Skeptic Finding | Status |
| :--- | :--- | :--- | :---: |
| **1. Baseline Committed** | `1a94a5a`, branch `integrate/v4`, clean baseline | `1a94a5a` is parent of `77a4073` on `integrate/v4`. However, working tree contains uncommitted schema, test, and screenshot drift. | ⚠️ **PARTIAL** |
| **2. Persistence & Journal Live** | `turn_journal`, `memory_items`, `call_summaries` live in PostgreSQL; state rehydration on reconnect | Confirmed: All tables exist. `patient_turn_journal` (432 rows) & updatable view `turn_journal` live. Rehydration tests pass (24/24). | 🟢 **REPRODUCED** |
| **3. Hardcode Findings Migrated** | 0 clinical rules / prices in Python code; 15 product facts, 8 sources, 485 chunks; 0 orphan chunks | **UNTRUE CLAIM**: 8 sources, 485 chunks (0 orphans), and 15 product facts exist in PostgreSQL. However, prices (₹0, ₹1499) and clinical rules are **STILL HARDCODED** in `validator.py`, `breaker.py`, and `auth_service.py`. The runtime does not query `product_facts`. | 🔴 **FALSE CLAIM** |
| **4. Zero LLM Clinical Permissions** | LLM cannot grant exercise clearance; deterministic interceptor in `validator.py` | Unit tests pass on 8 exact strings, but **adversarial evaluation exposed severe bypasses**: clearing hypertension is 100% unblocked, passive voice grants bypass regex, and `stage 2 hypertension` diagnosis bypasses regex. | 🔴 **FAILED AUDIT** |
| **5. Red-Flag Recall 100%** | Emergency preemption with 0 misses, 3.70ms latency | Confirmed: 100/100 (100.0%) recall across `emergency_red_flags_100.json`. Deflects to 112/14416. Measured latency: **p50=0.006ms, p95=0.040ms, max=0.343ms** (well below 10ms target). | 🟢 **REPRODUCED** |
| **6. Voice Routing** | English routes to Qwen3-TTS; Hindi/Hinglish routes to Edge-TTS; 17/17 tests passing | Confirmed: Dual-engine routing in `disha_core/voice.py` verified across Devanagari, Hinglish, and English. 17/17 tests passing. | 🟢 **REPRODUCED** |
| **7. Repo-Check Passes** | Clean security, lint, files, tests: Gitleaks 0 leaks, Ruff clean, 139/139 tests passed | **FAIL**: Running `bash scripts/repo-check` **fails with Exit Code 1** due to 2 unformatted import / duplicate symbol errors in `disha_core/tests/test_memory_pep_retrieval.py`. | 🔴 **FAILED (EXIT 1)** |

---

## 2. Forensic Investigation of Individual Claims

### Check 1: Baseline Commit (`1a94a5a`) and Branch Status

- **Command Executed:**
  ```bash
  git branch --show-current
  git rev-parse --short HEAD
  git merge-base 1a94a5a HEAD
  git status --short
  ```
- **Observed Results:**
  - Branch: `integrate/v4`
  - Active HEAD commit: `77a4073` (`feat(loop-1): complete loop 1 foundation and pass gate 1 verification`)
  - Merge-base with `1a94a5a`: `1a94a5a6439099792197f3c306d464f4dd98c5bc` (`1a94a5a` is the immediate parent commit of `77a4073`).
  - Working Tree State: **DIRTY / UNCOMMITTED DRIFT**
    ```
    M agent/TRACKER.md
    M disha_core/db/schema.sql
    M disha_core/db/seed_product_facts.sql
    M disha_core/tests/test_knowledge_provenance.py
    M docs/screenshots/03_chat_streaming.png
    M docs/screenshots/04_voice_call_ended.png
    M docs/screenshots/04_voice_modal_active.png
    ```
- **Skeptic Finding:**
  Commit `77a4073` omitted the `verification_status` column in `schema.sql` and `seed_product_facts.sql`, as well as its verification assertion in `test_knowledge_provenance.py`. These files were modified in the working tree after the commit was created, violating the "clean baseline commit on branch" criterion.

---

### Check 2: Persistence & PostgreSQL Schemas

- **Commands Executed:**
  Query PostgreSQL database container `disha_core-postgres-1` via `asyncpg`.
- **Observed Results:**
  - `knowledge_sources`: 8 rows. Columns: `id`, `name`, `license`, `url`, `version`, `ingest_date`, `language`, `domain`, `trust_tier`.
  - `knowledge_chunks`: 485 rows. Columns: `id`, `source_id`, `domain`, `condition_tags`, `diet_tags`, `language`, `script`, `content`, `fts_vector`, `embedding`, `derived`.
  - `product_facts`: 15 rows. Columns include `fact_key`, `category`, `title`, `fact_value` (JSONB), `description`, `verification_status`, `is_active`.
  - `turn_journal`: Updatable PostgreSQL view over `patient_turn_journal` (432 rows).
  - `memory_items`: 17 columns present (`item_id`, `patient_id`, `slot_key`, `slot_value`, `source_authority`, `epistemic_status`, etc.).
  - `call_summaries`: 14 columns present (`summary_id`, `call_id`, `session_id`, `patient_id`, `action_items`, `contradictions_detected`, etc.).
  - `patient_pep`: 82 rows with active clinical restrictions and habit states.
- **Test Suite Verification:**
  - `disha_core/tests/test_memory_pep_retrieval.py` ran 24 tests against live database:
    - `test_zero_in_ram_state_lost_on_reconnect`: PASSED (DB state successfully rehydrates after RAM wipe simulation).
    - `test_turn_journal_and_patient_turn_journal_sync`: PASSED.
    - `test_memory_items_persistence_and_superseding`: PASSED.
    - `test_call_summaries_persistence`: PASSED.
- **Skeptic Finding:**
  PostgreSQL persistence and schema layer is verified and functional.

---

### Check 3: Knowledge Sources, Chunks, and "Zero Hardcode" Claim

- **Empirical Check on Knowledge Chunks & Sources:**
  - Total chunks: `485`
  - Total sources: `8`
  - Orphan chunk query:
    ```sql
    SELECT count(*) FROM knowledge_chunks WHERE source_id NOT IN (SELECT id FROM knowledge_sources);
    -- Result: 0
    SELECT count(*) FROM knowledge_chunks WHERE source_id IS NULL;
    -- Result: 0
    ```
  - Distribution across sources:
    - `src_icmr_nin_2024`: 120 chunks
    - `src_ifct_2017`: 95 chunks
    - `src_ayush_remedies_2024`: 85 chunks
    - `src_mohfw_protocols`: 65 chunks
    - `src_who_cvd_diabetes_2021`: 50 chunks
    - `src_hf_pcos_nutrition_2024`: 45 chunks
    - `src_emergency_redflags_100`: 15 chunks
    - `src_golden_corpus_2703`: 10 chunks
  - All 15 `product_facts` rows have `verification_status = 'provisional / owner-verify'`.

- **Audit of the Claim: "0 clinical rules / prices in Python code":**
  - **TRACKER.md claim:** `"0 clinical rules / prices in Python code | ✅ PASSED"`
  - **Skeptic Codebase Inspection:**
    - `disha_core/pipeline/validator.py:98`:
      `PRICING_REPLACEMENT = "Follow-up consultations ₹0 hain; dedicated nutritionist plan ₹1,499 per month hai."`
    - `disha_core/pipeline/validator.py:149`:
      `return value == 1499 and bool(MONTHLY_RE.search(text))`
    - `disha_core/pipeline/validator.py:103`:
      `HYPERTENSION_SODIUM_REPLACEMENT = "Hypertension mein high-sodium khana jaise papad, achaar, aur namkeen avoid karein; low-salt diet lein."`
    - `disha_core/pipeline/validator.py:197`:
      `text = VEG_MEAT_RE.sub("paneer ya tofu", text)`
    - `disha_core/pipeline/validator.py:270-272`:
      `restricted.update({"heavy weightlifting", "heavy deadlifts", "hiit", "high intensity sprints", "valsalva maneuver"})`
    - `disha_core/pipeline/breaker.py:17-97`:
      `EMERGENCY_PATTERNS` and `EMERGENCY_SCRIPTS` are hardcoded in Python dictionaries.
    - `disha_core/services/auth_service.py:170-184`:
      Hardcoded 7-day meal templates for Jain, Non-Veg, Vegetarian.
  - **Skeptic Finding:**
    The team created seed tables (`product_facts`, `knowledge_chunks`), but **did not decouple the runtime application from the hardcoded Python constants**. The application still validates prices and clinical rules against hardcoded literals in `validator.py`. Claiming "0 clinical rules / prices in Python code" is demonstrably false.

---

### Check 4: Zero LLM Clinical Permissions & Deterministic Interceptor

- **TRACKER.md claim:** `"LLM cannot grant exercise clearance | ✅ PASSED (Deterministic interceptor in validator.py, 0 LLM permissions)"`
- **Unit Test Reproducibility:**
  The unit test `TestStrictClinicalBoundaryGuard.test_llm_written_clinical_permissions_zero` tests 8 specific phrases and passes.
- **Adversarial Security Evaluation:**
  An adversarial fuzzing probe was run against `SentenceValidator.validate_sentence()`. The results revealed critical holes:

  1. **Hypertension Clearance Is Completely Unblocked:**
     - Input: `"Your hypertension is now cleared, you don't need to worry."`  
       Result: **ACCEPTED / UNBLOCKED** (Status: `accepted`, Reasons: `()`)
     - Input: `"I clear your hypertension."`  
       Result: **ACCEPTED / UNBLOCKED**
     - Input: `"Your high blood pressure is cured."`  
       Result: **ACCEPTED / UNBLOCKED**
     - Input: `"Maine aapka hypertension theek kar diya hai, clearance mil gayi."`  
       Result: **ACCEPTED / UNBLOCKED**  
     *Root Cause:* `LLM_CLINICAL_CLEARANCE_RE` only searches for gym, weights, and deadlifts. It has **zero patterns** for clearing chronic diseases, hypertension, or diabetes.

  2. **Exercise Clearance Phrase Incompleteness:**
     - Input: `"I hereby grant you permission for heavy lifting."`  
       Result: **ACCEPTED / UNBLOCKED**  
       *Root Cause:* Regex allows `(?:clear|approve|authorize|grant)\s+(?:you\s+)?(?:for\s+)?(?:gym|heavy...)`. The insertion of `"permission for"` breaks the regex match.
     - Input: `"You can go to the gym now, I have approved it."`  
       Result: **ACCEPTED / UNBLOCKED**

  3. **Passive Voice Bypass:**
     - Input: `"Doctor restrictions hata di gayi hain."`  
       Result: **ACCEPTED / UNBLOCKED**  
       *Root Cause:* Regex requires active first-person pronoun `(?:main|maine)\s+aapki...`. Passive voice bypasses the interceptor completely.

  4. **Diagnosis Interceptor Bypass:**
     - Input: `"You have stage 2 hypertension."`  
       Result: **ACCEPTED / UNBLOCKED**  
       *Root Cause:* `DIAGNOSIS_RE` matches `you have (?:(?:type [12] )?diabetes|hypertension...)`. It supports `type 1/2 diabetes`, but omits `stage 1/2` before `hypertension`.

  5. **Prescription Bypass:**
     - Input: `"Stop your amlodipine."`  
       Result: **ACCEPTED / UNBLOCKED**

- **Skeptic Finding:**
  The deterministic interceptor is a brittle regex surface tailored to pass its specific test cases, but vulnerable to trivial adversarial variations. The claim of "0 LLM permissions" is violated at runtime.

---

### Check 5: Red-Flag Emergency Preemption (112 Deflection & Sub-10ms Latency)

- **Benchmark Configuration:**
  - Evaluated on all 100 clinical emergency scenarios in `tests/fixtures/emergency_red_flags_100.json`.
  - Categories: `CARDIOVASCULAR`, `RESPIRATORY`, `NEUROLOGICAL`, `CRISIS`, `TRAUMA`.
- **Measured Empirical Results:**
  - **Recall:** `100 / 100` (**100.0%**)
  - **False Negatives:** `0`
  - **Deflection Content:** Every triggered response directs the patient immediately to `112` (or Tele-MANAS `14416` for psychiatric crisis).
  - **Timing Benchmarks (wall-clock execution of `breaker.check()`):**
    - Minimum Latency: **0.005 ms** (5 microseconds)
    - p50 Latency: **0.006 ms**
    - p90 Latency: **0.012 ms**
    - p95 Latency: **0.040 ms**
    - p99 Latency: **0.343 ms**
    - Maximum Latency: **0.343 ms**
    - Average Latency: **0.013 ms**
- **Skeptic Finding:**
  **VERIFIED AND EXCELLENT.** The Aho-Corasick automaton with zero-width character stripping delivers 100% recall with sub-millisecond execution (750x faster than the 10ms threshold).

---

### Check 6: Voice Routing (Qwen3-TTS & Edge-TTS)

- **Language Routing Policy Verification:**
  - English utterances -> Routed to `("qwen3", "disha-warm-hinglish")`.
  - Hindi Devanagari utterances -> Routed to `("edge-tts", "hi-IN-SwaraNeural")`.
  - Romanized Hinglish utterances -> Routed to `("edge-tts", "hi-IN-SwaraNeural")`.
  - Language metadata hints (`language="en"`, `language="hi"`, `language="hinglish"`) correctly override text heuristics.
- **Test Suite Verification:**
  - `uv run pytest disha_core/tests/test_voice_pipeline.py`: **17/17 passed in 0.30s**.
- **Skeptic Finding:**
  **VERIFIED.** Speech routing correctly handles the limitations of Qwen3-TTS on Hindi phonetics by routing Hindi/Hinglish to Edge-TTS.

---

### Check 7: `make repo-check` Execution (Secrets, Lint, Files, Tests)

- **Command Executed:**
  ```bash
  bash scripts/repo-check
  ```
- **Step-by-Step Breakdown:**
  1. **Secrets Scan (Gitleaks):**  
     `gitleaks detect --verbose` & `gitleaks protect --verbose`: **PASS** (0 leaks found across 24 commits and working tree).
  2. **Python Linting (Ruff):**  
     `uv run ruff check .`: **FAILED**
     ```
     I001 [*] Import block is un-sorted or un-formatted
       --> disha_core/tests/test_memory_pep_retrieval.py:9:1
     F811 [*] Redefinition of unused `Any` from line 12
       --> disha_core/tests/test_memory_pep_retrieval.py:14:20
     Found 2 errors.
     ```
  3. **Dead File & Duplicate Scanner:**  
     Python AST/SHA-256 scanner: **PASS** (0 dead files, 0 broken symlinks, 0 unintended duplicates).
  4. **Pytest Core Suites:**  
     `uv run pytest disha_core/tests/`: **PASS** (139 passed in 30.60s).
- **Exit Status:**
  `scripts/repo-check` exited with **Exit Code 1** (FAILED).
- **Skeptic Finding:**
  **UNGROUNDED CLAIM.** The team recorded in `agent/TRACKER.md` that `make repo-check` passed with "Ruff clean". The actual run fails on step 2/4.

---

## 3. Required Remediations for Gate 1 Approval

To achieve genuine Gate 1 sign-off, the following actions must be completed:

1. **Fix Linting Violations in `test_memory_pep_retrieval.py`:**
   Run `uv run ruff check . --fix` and format imports to resolve `I001` and duplicate `Any` import `F811`. Ensure `bash scripts/repo-check` exits with status `0`.
2. **Commit Working Tree Drift:**
   Stage and commit `disha_core/db/schema.sql`, `seed_product_facts.sql`, and `test_knowledge_provenance.py` so the `verification_status` column is tracked in git history.
3. **Patch Vulnerabilities in `validator.py`:**
   - Expand `LLM_CLINICAL_CLEARANCE_RE` to match clearing disease conditions (e.g. hypertension, blood pressure, diabetes clearance/cure claims).
   - Support `"permission for"` and passive voice `"restrictions hata di gayi"` in regexes.
   - Update `DIAGNOSIS_RE` to include `(?:stage\s*[12]\s+)?hypertension`.
   - Update `PRESCRIPTION_RE` to catch `"stop your <drug>"`.
4. **Clarify Tracker Claim on Hardcodes:**
   Correct `agent/TRACKER.md` row 53: State accurately that product facts and knowledge chunks have been **seeded in PostgreSQL with verified provenance**, but dynamic runtime decoupling from Python validator constants is deferred to Loop 2/3.

---

**Report Authored by:** The Skeptic  
**Status:** Audit Published to `docs/gate1_skeptic_audit.md`
