# DISHA AI — ENGINEERING LESSONS LEARNED

## [LESSON-001] Do Not Over-Constrain Token Matching in Clinical Regex Guards
- **Problem**: In `SentenceValidator`, `WORKOUT_RE.search(text) and not mentioned` matched any sentence containing "exercise" or "workout", rewriting innocent advice like "Khana khane ke baad turant exercise na karein" into generic PEP refusal strings.
- **Root Cause**: The pattern checked generic activity words without distinguishing between prohibitive/safety counsel vs. prescription of unapproved gym activities.
- **Resolution**: Refined `PRESCRIPTIVE_WORKOUT_RE` to require affirmative calls-to-action (`roj exercise karein`, `workout shuru karein`) and checked for negative/timing context (`mat karein`, `turant nahi`, `timing`).

## [LESSON-002] Enforce Strict Sentence-Level Deduplication on Guard Rewrites
- **Problem**: When a multi-sentence model response triggered validator replacement across consecutive sentences, the replacement message was repeated 2-3 times consecutively.
- **Root Cause**: `validated_sentences` yielded each rewritten sentence independently without checking if the previous yielded sentence was identical.
- **Resolution**: Implemented `last_emitted` check in `sentence_buffer.py` to unconditionally suppress duplicate adjacent sentences.

## [LESSON-003] Short-Circuit Database Retrieval on Non-Clinical Intents
- **Problem**: Every turn (including simple greetings and thank-yous) ran full PostgreSQL hybrid text and vector queries, adding 150-300ms unnecessary latency.
- **Resolution**: Laya classifier schema `2026-11-08.v2` tags `requires_retrieval=False` for chit-chat, meta-questions, and general greetings, cutting p50 latency down to <200ms.

## [LESSON-004] Never Embed Python Comments Inside SQL Strings in SQLite
- **Problem**: Synapse MCP and CLI crashed with `OperationalError: unrecognized token: "#"` when calculating blast radius.
- **Root Cause**: An inline `# nosec B608` python comment was placed inside a multi-line SQL string passed directly to SQLite driver.
- **Resolution**: Extracted the SQL query string to a clean variable with the security lint comment placed in Python code outside the SQL text.

## [LESSON-005] Alembic Migration Version Column Must Exceed 32 Characters
- **Problem**: Migration failed with `DataError: value too long for type character varying(32)` during `alembic upgrade head`.
- **Root Cause**: Descriptive migration revisions like `0004_approved_condition_tag_index` exceed default 32 characters.
- **Resolution**: Widen `alembic_version.version_num` to `VARCHAR(64)` in the database schema setup.

## [LESSON-006] Strict Zero-Pricing Invariant: Disallow Commercial Inventions
- **Problem**: System previously allowed fallback regex matching for ₹0 consultations or ₹1,499 subscriptions.
- **Root Cause**: Hardcoded pricing assumptions in prompts and validators violated the product invariant that Disha AI is free and has no commercial pricing.
- **Resolution**: Any price occurrence is strictly rewritten to `Disha AI ke paas koi paid plans ya pricing nahi hai` and demo prices removed from codebase.

## [LESSON-007] Voice Privacy Consent Gate Must Precede Frame Amplitude Checks
- **Problem**: Silent test audio raised `RuntimeError: silent audio frame filtered` rather than raising `VoicePrivacyError`.
- **Root Cause**: Amplitude calculation ran before evaluating `GROQ_HEALTH_DATA_PROCESSING_APPROVED`.
- **Resolution**: Enforce fail-closed privacy consent gate at the outermost entry point before processing any audio bytes.
