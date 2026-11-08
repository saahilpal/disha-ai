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
