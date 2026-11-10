# Memory, onboarding, and PEP

This is a description of the current code path and its limits, not a medical-record guarantee or a clinical-certification statement. Database names retain historical `patient_*` terminology.

## Separate data responsibilities

| Information | Runtime source | Boundary |
|---|---|---|
| General food, nutrition, exercise, or lifestyle guidance | Approved `clinical_knowledge_base` rows, exposed as `clinical_guideline_chunks` | Retrieved only when approved; corpus quality and reviewer identity are not established by code alone. |
| “What is my prescribed dinner?” | Active, approved `patient_diet_schedules` row for this user, weekday, and meal | Not interchangeable with general meal guidance. Missing/pending schedules are not filled with generated prescriptions. |
| Preferences, goals, conditions, symptoms, and limitations | `patient_profiles`, `patient_pep`, active memory items and temporal facts | User disclosures remain user-reported unless separately verified; absent information is not proof of safety. |
| Exercise suitability | Relevant approved knowledge plus selected deterministic checks | The checks do not calculate complete individual suitability or prescribe routines. |
| Conversation continuity | `patient_turn_journal` plus a process-local history cache | This is conversational context, not a complete longitudinal medical record. |

## Account registration and onboarding

`POST /auth/register` and `POST /auth/onboarding` share the registration service. It writes the account/profile, a hashed bearer token, and a `patient_pep` row for focus, concern, language, and dietary-preference context. Registration accepts patient-reported conditions and goals; it does not verify them with a clinician. Passwords are stored as PBKDF2-SHA256 hashes and access tokens are stored by SHA-256 digest.

The request schema also accepts fields such as `hypertension_stage`, `gym_clearance`, `activity_level`, and `movement_restrictions`; the registration function currently does not write those values into the corresponding safety fields. Do not assume those values have been captured or verified by account creation. The later journey extractor uses field mappings to persist disclosures, but its source is still the user's report.

During chat/voice turns, `disha_core.journey` may extract multiple answers, update journey state, and write mapped values into profile, PEP, `memory_items`, `patient_temporal_facts`, or habit/episode tables. These mappings and database constraints do not create an authenticated clinician-review workflow.

## Short-term conversation context

`patient_turn_journal` stores user and assistant utterances in PostgreSQL. On every turn, `build_patient_context` loads up to the latest sixteen messages and the prompt path supplies them chronologically to the LLM. All turns (including normal generation, safety deflections, meal prompts, and provider errors) commit to `patient_turn_journal` and update in-memory state. Older relevant exchanges outside the recent active window are supplemented via conversation history RAG without duplicating recent turns.

The shared turn path uses PostgreSQL `patient_turn_journal` as the single authoritative source of truth across sessions, chat, and voice calls. The frontend `/chat/history` endpoint hydrates the visible conversation stream on login or page refresh, eliminating context loss.

## Persistent context tables

The current context builder reads:

- `patient_pep` for recorded preferences, focus, concern, and selected exercise-related fields.
- Active `patient_temporal_facts` for structured disclosures.
- Active `memory_items` for saved slots.
- Recent `patient_turn_journal` rows for short-term dialogue.
- `patient_diet_schedules` only for a requested prescribed meal.

The schema also contains journey state/history and habit-state/episode tables. Their presence does not mean every field is loaded into every prompt or has been clinically validated. See [`disha_core/db/schema.sql`](../disha_core/db/schema.sql).

## Prescribed meals versus suggestions

The prescribed-meal path queries an active approved row for the user's weekday and `breakfast`, `lunch`, or `dinner`. If the user does not specify a meal window, the turn asks which one; an unavailable or missing record is reported rather than replaced with a generic meal. The profile read uses the same approval/active filters.

General meal or recipe suggestions require relevant approved knowledge records. This repository does not establish a validated recipe-composition or food-composition service for constructing complete meal plans or calculating exact calories/macronutrients. Seed/import content being present is not evidence that it is reviewed or licensed.

## Knowledge retrieval and evidence

Chat/voice health retrieval is implemented in `disha_core.engine.retriever`: PostgreSQL full-text rank and `pg_trgm` similarity over approved rows, with bounded results and deduplication. No embeddings, pgvector, or reciprocal-rank fusion are used in this active path. Retrieved knowledge chunk IDs and retrieval status are carried through response metadata; prescribed meal rows are separate and have no knowledge chunk ID. A chunk ID indicates which row was supplied, not that every generated sentence is semantically entailed by it.

See [Knowledge inventory](knowledge/INVENTORY.md) and [retrieval details](architecture/04_rag_ingestion_and_retrieval.md).

## Exercise safety

`disha_core.pep.exercise_safety` extracts selected risk tags, blocks an explicit recorded restriction that matches the requested exercise, and otherwise returns an insufficient-information result rather than choosing an exercise. The shared turn pipeline also withholds personalized exercise recommendations when it finds selected risk signals or lacks essential safety context. This is a conservative partial check—not a complete eligibility engine, medical clearance, or routine/alternative generator. A retrieved exercise passage is not proof of an individual's suitability.

## What this implementation does not prove

- That deployed knowledge has accurate source provenance, licensing, qualified review, or fresh clinical approval.
- That every user-reported condition, symptom, injury, or limitation was persisted or verified.
- That a recommendation is clinically appropriate or effective.
- That memory has complete temporal arbitration, guaranteed durability, or a clinical audit trail.
- That a model response is fully supported by the retrieved records.
- That behavior has been validated against a live deployment or database beyond the checks explicitly reported in [`DEPLOYMENT.md`](DEPLOYMENT.md).
