# Onboarding and Conversation Contracts

**Status:** Active contracts for state tracking, topic-shift deferral, and conversation continuity. Browser and database evidence is tracked in `docs/design/DEFECTS.md`.

**Product:** Disha AI health coach for users.

**Storage naming:** Existing SQL identifiers such as `patient_id` and `patient_journey_state` are legacy internal names for a signed-in user. Do not expose them in UI copy.
**Constraint:** No persistent page that displays stored habits.

## Goals

- One deterministic stage cursor shared by chat, voice, refresh, and session resume.
- The LLM may phrase a question or answer a side question; it does not choose the slot, infer its status, or authorize clinical facts.
- Capture user-reported details with provenance and keep them separate from clinician-verified PEP data.
- Ask one onboarding question at a time; never interrupt distress, emergency handling, or unrelated user requests.
- Support English, Hindi, and Hinglish only. UI language is independent from coaching language and script.

## Stage registry

Stage and slot definitions are data, not prompt instructions. The registry is the source for order, localized question text, widget, branching, skip/defer policy, sensitivity, consent, reason, and estimated time. The initial registry should be a versioned file in the backend package and loaded deterministically at startup. Database state stores answers and progress, not a competing copy of the static registry. S0–S4 are the first-session target (estimated at 5–7 minutes); that timing is a design estimate and must be checked in browser usability work.

| Stage | Purpose and initial slots | Special handling |
|---|---|---|
| S0 Language | `coaching_language`, `script` | Values: English, Hindi, Hinglish; Devanagari/Latin script as applicable. Keep separate from UI locale. |
| S1 Consent | `ai_disclosure_ack`, `data_use_ack`, `voice_processing_consent` | Explain AI health coach, not a doctor. Microphone permission, sending audio for transcription, and persistent audio storage are distinct; disclose the configured processing path and do not imply audio is stored unless it is. Ask for voice processing consent only when voice starts; sensitive-purpose consent remains separate and revocable. |
| S2 Basics | `preferred_name`, `age`, `sex`, `height`, `weight` | Name is required for account identity; age/sex/height/weight are optional. Number and unit answers receive explicit confirmation. |
| S3 Goals | `primary_goal`, `goal_target`, `goal_timeframe` | Target and timeframe may be skipped. Never promise a clinical outcome. |
| S4 Safety | `conditions`, `medications`, `allergies`, conditional `pregnancy_lactation`, `injury_surgery`, `red_flag_symptoms` | Ask sensitive items only with just-in-time consent. Never infer pregnancy, lactation, or cycle relevance from gender/sex. Red flags invoke emergency handling and suspend onboarding. Self-report is never clinician clearance. |
| S5 Diet | `diet_pattern`, `intolerances`, `dislikes`, `meal_times`, `meal_preparation`, `eating_out` | No default diet. “None” is distinct from unknown or declined. |
| S6 Activity | `current_activity`, `movement_limits`, `location`, `equipment`, `steps` | Missing safety details never mean exercise is safe. No gym-clearance question or UI. |
| S7 Sleep and routine | `wake_time`, `sleep_time`, `work_pattern`, `stress_level` | Normalize time locally before accepting; ask one slot at a time. |
| S8 Preferences | `call_window`, `reminder_style`, `answer_length`, `coaching_language`, `script` | Do not imply outbound calls/reminders unless a working scheduler exists. |
| S9 Hand-off | `safety_recap_confirmation`, optional `follow_up_preference` | Recap only safety items, ask the user to correct/confirm, then offer one clear next action. No habit-display page. |

S0–S4 are the first-session priority. S5–S8 may continue in later chat or voice sessions. Progressive lifestyle questions (for example caffeine, hydration, alcohol/tobacco, cycle, wellbeing, adherence barriers) are not part of the required first pass; sensitive questions require separate consent and must not be asked during distress.

Each slot definition must include:

- stable `slot_id`, `stage_id`, order, and registry version;
- question templates in English, Hindi, and Hinglish;
- widget type (chips, number/unit, time, date, text, or voice-only);
- deterministic `ask_if` predicate and completion rule;
- skip/defer/decline policy, sensitivity, and consent scope;
- one-line “why I’m asking” text and estimated answer time;
- value authority, normalizer, validator, confirmation rule, and destination.

## Persisted state and ownership

Use the existing user-scoped journey cursor and question history as the starting point. Do not add a second cursor table. Current database checks constrain journey stages to 1–5 and question history to a smaller status set; the migration must safely replace those checks and preserve/backfill every existing row before the new registry becomes active. Stage IDs in the service are `S0`–`S9`; the storage migration must map existing rows from their completed slot history, not by blindly adding a numeric offset. An additive migration may extend `patient_journey_state` with:

- `registry_version`, `resume_cursor`, `pending_slot`, and `slot_statuses JSONB`;
- `last_channel`, `last_asked_at`, and per-slot attempt counters if not already represented.

Allowed slot states: `unasked`, `asked`, `answered`, `skipped`, `declined`, `deferred`, `needs_clinician`, `conflicted`, `pending_confirmation`. Store one canonical slot-status map; derive legacy completed/missing/skipped arrays from it or retain those columns as read-only migration history. Do not update two active representations. Store status separately from value: “unknown”, “none”, “declined”, and “later” are not interchangeable values.

Keep `journey_question_history` as the append-only event record for question issue, answer, correction, skip, defer, undo, and channel. Add fields only when the current schema cannot represent the event. Every answer event records user ID, slot, raw text, normalized value, channel, timestamp, registry version, and source authority.

Profile and memory ownership:

- Account identity and user-editable preferences live in the profile.
- Clinician-verified conditions and exercise permissions live in the clinician-owned PEP core.
- Low-risk lifestyle answers may update the existing current-habit store with raw/normalized value, `user_reported` provenance, channel, evidence, and effective dates.
- Clinical self-reports, sensitive details, and contradictions are stored as explicitly user-reported proposals with a review-needed marker. They never write clinician diagnosis, prescription, clearance, or medication instructions. Existing `memory_items.flagged_review` is storage only, not a working clinician notification/review workflow; do not promise a clinician will see or approve a proposal until that workflow exists. Every read path must exclude proposed/flagged rows from verified context.
- Never apply a default when normalization fails. Keep the previous value and cursor unchanged on validation or database failure.

Sensitive consent must have durable version, purpose, accepted/revoked time, and user ownership. A localStorage boolean alone is not consent evidence.

## API

All routes require the same bearer authentication and user isolation as `/patient/profile`. The server derives the user ID from the token; clients cannot supply a different owner. Voice and chat call the same service functions used by these routes.

### `GET /onboarding/state`

Returns the saved cursor and statuses without health-value display:

```json
{
  "registry_version": "1",
  "status": "in_progress",
  "stage_id": "S4",
  "pending_slot": "allergies",
  "resume_cursor": {"stage_id": "S4", "slot_id": "allergies"},
  "last_channel": "chat",
  "progress": {"completed": 6, "total": 18},
  "slots": {"conditions": "answered", "medications": "answered", "allergies": "asked"}
}
```

Progress counts only applicable slots and may be incomplete; it does not represent medical clearance or reveal answers in a separate profile page.

### `POST /onboarding/next`

Request:

```json
{"channel":"chat"}
```

Response:

```json
{
  "slot": "allergies",
  "stage_id": "S4",
  "question": "Do you have any allergies you want to share?",
  "language": "en",
  "script": "latin",
  "widget": {"type":"text"},
  "why_asking": "This helps me avoid suggesting something that may not suit you.",
  "skippable": true,
  "sensitive": true,
  "consent_required": true,
  "progress": {"completed": 6, "total": 18}
}
```

The engine persists the `asked` event and pending cursor before returning. Concurrent calls for the same user serialize on the journey row and return the same pending slot.

### `POST /onboarding/answer`

Request:

```json
{"slot":"allergies","raw":"I have a peanut allergy","channel":"voice","turn_id":"opaque-id"}
```

Response:

```json
{
  "accepted": true,
  "slot":"allergies",
  "status":"pending_confirmation",
  "confirmation":"I heard that you have a peanut allergy. Is that right?",
  "next": null
}
```

The server checks emergency and supported-language policy before extraction. It validates the supplied slot against the saved cursor or an explicit correction. Normalize deterministic numerals, units, Devanagari digits, and time phrases first. Ambiguous safety-critical answers receive a clarification question; an LLM must not extract or approve them. A constrained local parse may be considered only for low-risk free-text habits after deterministic normalization cannot parse a supported answer; it cannot set authority or bypass validation. Use `turn_id` or an equivalent idempotency key to prevent duplicate writes on replay.

### `POST /onboarding/{skip|defer|edit|undo}`

- `skip`: mark `skipped`; the scheduler must not re-ask until the user explicitly reopens it.
- `defer`: mark `deferred` and preserve the cursor for a later session.
- `edit`: replace a saved answer with a validated, versioned correction; keep the prior event.
- `undo`: revert the latest answer/correction event for that slot and restore the prior value/status.

Request fields: `slot`, `channel`, and for `edit`, `raw` plus `turn_id`.

## Chat and voice policy

The shared turn sequence is:

1. Authenticate the user and load the same user-scoped journey state.
2. Run emergency detection first. If triggered, return emergency guidance, stop extraction and questions, and leave the cursor resumable.
3. Check supported language. If unsupported, give one brief deflection; do not extract or advance.
4. If the user is answering the pending slot, run targeted deterministic normalization and validation, persist answer/status/event atomically, then confirm critical values.
5. If the user asks an unrelated question, answer through the regular coaching path. Do not replace the saved cursor. Return to onboarding only when appropriate.
6. Ask at most one next slot in a turn. Never ask during distress. Session/call question caps are enforced by the engine and covered in tests.
7. For voice: acknowledge briefly while parsing; “repeat”, “skip”, “later”, and “don’t know” map to explicit state actions; after two failed recognitions, offer visible chat/chips. Barge-in cancels playback. Switching to chat stops mic capture or preserves an explicit active-call indicator; no silent background microphone.

Success responses are returned only after durable commit. Database errors produce a recoverable error and do not claim the answer was saved.

## Failure and status semantics

- `401`: no/expired session; preserve server-side cursor and return to sign-in.
- `403`: consent missing/revoked for a sensitive operation. The user may skip/defer instead.
- `409`: slot is not pending, stale cursor, or conflicting concurrent edit; return current state.
- `422`: invalid answer; no write and no cursor advance.
- `429`: rate limit; preserve answer text for explicit retry.
- `503`: persistence/model unavailable; no success claim. Emergency path remains available without onboarding writes.
- Connection loss during answer: client retries with the same `turn_id`; server returns the original result if already committed.

## Test contract

Database-backed tests must prove user isolation, atomic answer+cursor writes, every status transition, duplicate replay idempotency, correction/undo, restart/channel resume, English/Hindi/Hinglish normalizers, clinical proposal separation, low-risk current-state writes, red-flag interruption, unsupported-language no-write, and DB failure recovery. Browser tests must prove onboarding works in chat and voice, keyboard/phone widths, consent, mic-denied fallback, and the visible resume cursor after reload.

## TurnContext Pipeline Component Contract

Each conversational turn across Voice and Chat executes through a single strongly-typed `TurnContext` (Pydantic v2 in `disha_core/models/turn_context.py`). Each pipeline stage reads strictly upstream sections and writes exclusively to its assigned downstream section, recording provenance and stage latency:

| Stage Component | Reads From Upstream | Writes To Downstream | Timing & Provenance |
|---|---|---|---|
| **1. STT / Input Ingestion** | Raw WebSocket audio frames or HTTP JSON `TurnRequest` | `TurnContext.transcript` (`interim`, `final`, `audio_duration_ms`) | Tracks ASR confidence, chunk duration, and final vs interim mode |
| **2. Language Detector** | `TurnContext.transcript` | `TurnContext.language` (`code`, `script`, `is_supported`, `deflected`) | Latn / Deva script boundary; detects supported tier (en/hi/hinglish) |
| **3. Safety & Emergency Gate** | `TurnContext.transcript`, `TurnContext.language` | `TurnContext.safety` (`breaker_triggered`, `category`, `pep_risk`, `pep_restricted`) | Fails closed on red-flag symptoms (112 triage); evaluates Laya PEP risk |
| **4. Router & Stage Engine** | `TurnContext.transcript`, `TurnContext.safety` | `TurnContext.stage_intent` (`intent`, `stage_id`, `slot_id`, `scheduled_question`, `skip_retrieval`) | Deterministic slot selection, off-topic detection, RAG retrieval bypass |
| **5. Context & Patient Brief** | `TurnContext.stage_intent`, Database Pool | `TurnContext.patient_brief` (`day_ist`, `meal_type`, `diet_status`, `profile_summary`) | Single acquired DB connection context load; cached PEP profile |
| **6. Memory & Turn Brief** | `TurnContext.transcript`, `TurnContext.stage_intent`, DB | `TurnContext.memory_brief` (`history_turns`, `disclosed_slots`, `contradictions`, `has_history`) | 8-turn sliding window + extracted slot disclosures; cross-turn contradiction check |
| **7. RAG Evidence Retriever** | User turn, intent/domain, relevant user context | Evidence chunk IDs and retrieval state | Approved PostgreSQL full-text + trigram search; skipped only where health grounding is not needed |
| **8. Clinical Rules Engine** | `TurnContext.patient_brief`, `TurnContext.retrieval` | `TurnContext.rules` (`rules_fired`) | Enforces anti-echo, fruit moderation, zero-pricing, safe exercise constraints |
| **9. Dual Provider LLM** | `TurnContext.patient_brief`, `TurnContext.memory_brief`, `TurnContext.retrieval`, `TurnContext.rules` | `TurnContext.draft` (`raw_text`, `model`, `prompt_tokens`, `completion_tokens`, `latency_ms`) | Primary Ollama/Groq with fallback; streaming token emission |
| **10. Sentence Validator** | `TurnContext.draft`, `TurnContext.rules`, `TurnContext.safety` | `TurnContext.validator` (`status`, `is_rewritten`, `replacement_reason`, `validated_sentences`, `violations`) | Incremental sentence boundary validation; clinical bounds; zero-pricing invariant |
| **11. TTS Audio Synthesizer** | `TurnContext.validator.validated_sentences` | `TurnContext.spoken` (`spoken_text`, `sentence_count`, `audio_bytes_len`, `tts_latency_ms`) | Sentence-chunked speech synthesis (Svara 4-bit / Qwen3-TTS); streams 20ms frames |
| **12. Client Playback Ack** | Client WebSocket ACK / Barge-in | `TurnContext.playback` (`completed`, `interrupted`, `interrupted_at_ms`) | Playback cancellation on barge-in; turn completion acknowledgement |

### PHI-Safe Observability & Tracing
Every turn produces a serialized telemetry dictionary via `TurnContext.to_phi_safe_dict()`. User utterances, names, and explicit clinical text are hashed (SHA-256 prefixes) or redacted, preserving latency metrics, token consumption, rule activations, and stage status for system monitoring without exposing sensitive data.
