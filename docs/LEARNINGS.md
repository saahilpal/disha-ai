# Disha AI — Consolidated Engineering Learnings

- **Source:** `.agent/LESSONS.md`, `docs/changes/WHY.md`, `docs/DELETIONS.md`, git commit history
- **Date:** 2026-11-10
- **Audience:** Core Systems Engineering & Safety Architecture

---

## 1. Safety & Clinical Invariant Learnings

### [LEARNING-001] Avoid Over-Constrained Keyword Matching in Clinical Sentence Guards
- **Incident:** `SentenceValidator` previously matched any sentence containing "exercise" or "workout", rewriting innocent advice like *"Khana khane ke baad turant exercise na karein"* into generic PEP refusal strings.
- **Root Cause:** Regex evaluated generic activity keywords without contextual awareness of prohibitive or timing advice (`mat karein`, `turant nahi`).
- **Resolution:** Refined `PRESCRIPTIVE_WORKOUT_RE` to require affirmative calls-to-action (`roj exercise karein`, `workout shuru karein`) and check negative contexts.
- **Permanent Rule:** Clinical validators must never match naked nouns; they must match prescriptive verb phrases.

### [LEARNING-002] Eradicate Invented Claims & False Clearances
- **Incident:** Frontend contained badges like `"Gym Clearance: Approved"` and commercial plans with prices (₹1,499).
- **Root Cause:** Prototyping mockups left ungrounded clinical authorizations and commercial tiers in the client bundle.
- **Resolution:** Completely purged `#profile-page-gym-clearance` from DOM; replaced pricing claims with strict zero-pricing invariant (`PRICING_REPLACEMENT = "Disha AI ke paas koi paid plans ya pricing nahi hai"`).
- **Permanent Rule:** An AI agent cannot certify clinical gym clearance or make commercial promises not verified in database facts.

### [LEARNING-003] Voice Privacy Consent Gates Must Precede Processing
- **Incident:** Silent test audio frames raised `RuntimeError: silent audio frame filtered` instead of privacy error.
- **Root Cause:** Audio amplitude checks executed prior to evaluating HIPAA/Egress authorization flags (`GROQ_HEALTH_DATA_PROCESSING_APPROVED`).
- **Resolution:** Re-ordered checks to fail closed on privacy authorization before inspecting audio bytes.
- **Permanent Rule:** Privacy and consent authorization checks sit at the outermost network perimeter.

---

## 2. Conversational Architecture & Prompt Engineering Learnings

### [LEARNING-004] Render System Prompts from Single-Source Policy Files
- **Incident:** System prompt drifted across `client.py`, `context_builder.py`, and test mocks, ballooning to 1,446 tokens with duplicate and contradictory guidance.
- **Root Cause:** Manual prompt editing without programmatic validation against policy specifications.
- **Resolution:** Centralized rules in `data/behavior_rules.yaml` and render `SYSTEM_PROMPT` deterministically in `client.py`, hashed and versioned (`v1-9f113b222df1`) at ≤600 tokens.
- **Permanent Rule:** Prompts must be rendered from versioned YAML files and gated by automated token and rule-id tests.

### [LEARNING-005] Whole-Draft Verification Prevents Sentence-Level Echo & Fragment Splitting
- **Incident:** Sentence-by-sentence streaming verification yielded rewritten sentences that lost context-dependent words and created repetition loops.
- **Root Cause:** Validating isolated sentence fragments prevented inspecting turn-level sentence counts (P6 ≤ 3 sentences) and cross-sentence echoes.
- **Resolution:** In chat mode, accumulate the complete draft, run whole-draft verification (`verify_response`), and yield verified sentences cleanly.

### [LEARNING-006] The Danger of Canned Answer-Shaped Fallbacks
- **Incident:** Repair loops used hardcoded strings (`apply_constrained_fallback`) that spoke in Disha's persona with static text, violating conversational dynamism (P5).
- **Root Cause:** Reusing static deflection strings when LLMs failed validation.
- **Resolution:** Enforce LLM-only repair (max 2 attempts + 1 strict constrained regeneration). If all models fail, output an explicit `[System Error]` rather than a disguised fake persona utterance.

---

## 3. Database, Migrations & Infrastructure Learnings

### [LEARNING-007] Alembic Revision Identifiers Require Wide Column Storage
- **Incident:** `alembic upgrade head` crashed with `DataError: value too long for type character varying(32)`.
- **Root Cause:** Descriptive migration slugs like `0004_approved_condition_tag_index` exceeded standard 32-character limits.
- **Resolution:** Widened `alembic_version.version_num` to `VARCHAR(64)` in database migrations.

### [LEARNING-008] Unmounted Route Traps in Layered Frameworks
- **Incident:** `disha_core/routers/chat.py` duplicated endpoints from `disha_core/main.py` but was not mounted in FastAPI, causing persistence fixes to have zero effect until mapped to `main.py`.
- **Root Cause:** Unused router files lingering in repo without clear module ownership.
- **Resolution:** Traced live FastAPI app mounts and placed active persistence endpoints directly on `app` in `main.py`.

