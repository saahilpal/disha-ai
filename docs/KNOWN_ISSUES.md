# Known Issues and Deferred Technical Debt (KNOWN_ISSUES)

This document catalogs known architectural defects, test limitations, and deferred migrations identified during the repository audit.

---

## 1. Alembic Version Column String Truncation
- **Severity**: P1
- **Location**: `migrations/versions/0004_approved_condition_tag_index.py` and PostgreSQL `alembic_version` table.
- **Description**: Standard Alembic `alembic_version` tables define `version_num VARCHAR(32)`. Revision ID `0004_approved_condition_tag_index` contains 33 characters. Running `alembic upgrade head` throws `psycopg2.errors.StringDataRightTruncation: value too long for type character varying(32)`.
- **Reproduction**:
  ```bash
  alembic upgrade head
  ```
- **Why Deferred**: Bypassed safely in test and production setup by applying schema scripts directly (`apply_conversations_schema.py`, `apply_journey_schema.py`, `apply_pep_habits_schema.py`). Altering the revision hash requires a coordinated migration reset across production environments.

---

## 2. Journey Acceptance Tests Return 502 Bad Gateway
- **Severity**: P1
- **Location**: `tests/test_journey_memory_acceptance.py:152,525,570`
- **Description**: Acceptance tests calling `http://127.0.0.1:8080/patient/profile` fail with `502 Bad Gateway`. The NGINX proxy container forwards requests to `disha_core-backend-1`, which fails when dependent internal container networking is partitioned or dev database is stopped.
- **Reproduction**:
  ```bash
  pytest tests/test_journey_memory_acceptance.py
  ```
- **Why Deferred**: Running unit tests against a local test container (`disha-test-pg`) intentionally isolates database connections from background Docker Compose proxy routing. Addressing this requires updating the Docker Compose test runner network topology.

---

## 3. Replay Journal Turn XML Idempotency Mismatch
- **Severity**: P2
- **Location**: `tests/test_acceptance_resilience.py:667` in `test_resilience_06_replay_journal_turns_idempotently`
- **Description**: Replaying journal turns produces an XML context discrepancy (`assert xml_1 == xml_2 == xml_3`). The initial replay includes `<PEP_BRIEF>`, whereas the second replay excludes it due to in-memory caching in the habit consolidation engine.
- **Reproduction**:
  ```bash
  pytest tests/test_acceptance_resilience.py -k test_resilience_06
  ```
- **Why Deferred**: Does not cause conversational drift in live user sessions because `rehydrate_session_state` always queries the latest committed database state on new turns. Requires refactoring cache invalidation hooks in `habits_engine.py`.

---

## 4. Bloating and Acidity Transliteration Retrieval Gap
- **Severity**: P2
- **Location**: `tests/test_memory_pep_retrieval.py:344` in `test_retrieval_for_symptoms_bloating_acidity_knee_pain`
- **Description**: Query `"mujhe pet me bohot gas aur bloating ho rahi hai"` returns 0 chunks in `retrieve_chunks`. The clinical knowledge base indexes gastrointestinal guidelines under terms like `acidity`, `pet dard`, and `indigestion`, but lacks explicit trigger tokens for colloquial transliterated `gas aur bloating`.
- **Reproduction**:
  ```bash
  pytest tests/test_memory_pep_retrieval.py -k test_retrieval_for_symptoms_bloating_acidity_knee_pain
  ```
- **Why Deferred**: Lifestyle guidance for gastrointestinal symptoms is safely handled by general coaching fallback without inventing unverified facts. Requires enriching `trigger_terms` in `clinical_knowledge_base` with broader Hinglish colloquialisms.

---

## 5. Prompt Count Discrepancy During Response Repair
- **Severity**: P2
- **Location**: `tests/test_recommendation_grounding.py:311,394`
- **Description**: Tests assert `len(llm.prompts) == 1`, but observe `len(llm.prompts) == 4`. The response harness invokes the verification repair loop (`repair_turn`), which executes up to 3 subsequent prompt attempts to self-correct ungrounded clinical statements before emitting output.
- **Reproduction**:
  ```bash
  pytest tests/test_recommendation_grounding.py -k test_missing_knowledge_still_uses_the_coach
  ```
- **Why Deferred**: The repair loop functions as designed by correcting ungrounded draft text. Updating the test assertion to account for repair attempts requires aligning test mock expectations with current `ResponseHarness` repair semantics.
