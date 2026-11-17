# Low-Level Design (LLD)

This document details the internal components, class hierarchies, sequence lifecycles, and data contracts that govern Disha AI.

## 1. Component Architecture and Class Hierarchy

```mermaid
classDiagram
    class EmergencyBreaker {
        -Automaton _automaton
        -dict red_flag_map
        +check(text: str) BreakerResult
        +reload() void
    }

    class BreakerResult {
        +bool triggered
        +str category
        +str matched_phrase
        +str action
    }

    class LayaClassifierAdapter {
        -str server_url
        -float min_confidence
        -ClassifierCircuitBreaker circuit_breaker
        -OrderedDict _cache
        -EmergencyBreaker breaker
        +classify(text: str) LayaClassificationResult
        +is_ready() bool
        +get_status() dict
    }

    class ClassifierCircuitBreaker {
        -int failure_threshold
        -float reset_timeout_seconds
        -int failure_count
        -bool is_open
        +record_success() void
        +record_failure() void
        +allow_request() bool
    }

    class ConsecutiveFailureCircuitBreaker {
        -int threshold
        -float cooldown
        -int failures
        -float opened_at
        +allow_primary() bool
        +record_success() void
        +record_failure() void
    }

    class DualProviderClient {
        -ConsecutiveFailureCircuitBreaker breaker
        -AsyncClient primary_client
        -AsyncClient secondary_client
        +generate_stream(prompt, messages) AsyncIterator
    }

    class SentenceValidator {
        -set allowed_prices
        +validate_sentence(sentence, context) ValidationResult
        +sanitize_for_tts(text) str
    }

    class ResponseHarness {
        -DualProviderClient llm
        -SentenceValidator validator
        +execute_turn(request, patient_id, payload) AsyncIterator
        +repair_turn(llm, prompt, draft, violations) tuple
    }

    EmergencyBreaker --> BreakerResult
    LayaClassifierAdapter --> ClassifierCircuitBreaker
    LayaClassifierAdapter --> EmergencyBreaker
    DualProviderClient --> ConsecutiveFailureCircuitBreaker
    ResponseHarness --> DualProviderClient
    ResponseHarness --> SentenceValidator
```

## 2. Core Modules

### 2.1 Emergency Breaker (`disha_core/pipeline/breaker.py`)
- **Algorithm**: Aho-Corasick string matching compiled using `pyahocorasick`.
- **Latency**: Measured median latency of 3.69 µs across 100 benchmark emergency prompts.
- **Precedence**: Runs on raw input text prior to ML classification and LLM invocation across both chat and voice endpoints.
- **Trigger Behavior**: If triggered, immediately aborts pipeline execution and returns the standardized 112 emergency escalation response.

### 2.2 Classifier Adapter (`disha_core/classifier/adapter.py`)
- **Model**: ConvAI Innovations Laya multilingual model (`laya==0.4.27`).
- **Execution Mode**:
  - Remote HTTP dispatch via `httpx` when `LAYA_SERVER_URL` is set.
  - In-process PyTorch CPU execution (`torch.inference_mode()`) when `LAYA_SERVER_URL` is empty.
  - Deterministic safety fallback (`_fallback_classification`) when dependencies or server are offline.
- **Gating**:
  - Minimum confidence gate: `0.40`. Scores below 0.40 trigger conservative rule fallback.
  - Audit threshold: `0.70`. Scores below 0.70 or with ambiguous margin (< 0.15) enqueue turns to `ReviewQueueManager` for clinician audit.
- **Circuit Breaker**: `ClassifierCircuitBreaker` opens after 3 consecutive failures; reset timeout is 30.0 seconds.
- **Cache**: LRU `OrderedDict` with capacity of 2,048 entries. Measured cache hit lookup is 0.04 µs.

### 2.3 Context Builder & Clinical Retriever (`disha_core/engine/`)
- **Retriever (`retriever.py`)**:
  - Queries the PostgreSQL view `clinical_guideline_chunks`.
  - Tri-level search: Exact trigger terms match, PostgreSQL full-text search (`tsvector`), and Trigram fuzzy similarity (`pg_trgm`).
  - Cache: Compound LRU cache keyed by `(patient_id, sha256(query))` with capacity of 1,024 entries.
- **Context Builder (`context_builder.py`)**:
  - Loads patient biometrics (`patient_profiles`), active prescriptions (`patient_pep`), and recent conversation history (`patient_turn_journal`).
  - Renders XML-bounded context blocks (`<PATIENT_PROFILE>`, `<PEP_PERMISSIONS>`, `<CLINICAL_GROUNDING>`).
  - Strips internal stage checklists to prevent conversational lectures.

### 2.4 Response Harness, Validator & Verifier
- **ResponseHarness (`disha_core/harness/harness.py`)**:
  - Orchestrates prompt assembly, dual-provider streaming, streaming sentence validation, and turn-level verification.
- **SentenceValidator (`disha_core/pipeline/validator.py`)**:
  - Operates on streaming sentence chunks.
  - Replaces doctor claims, drug dosage alterations, ungrounded pricing, and channel boundary leaks using compiled regex substitutions.
- **Response Verifier (`disha_core/harness/verifier.py`)**:
  - Operates on the full accumulated turn text.
  - Enforces 6 structural invariants:
    1. Identity: No claims of being a doctor or human physician.
    2. Capabilities: No offers of external channels (WhatsApp/email/phone call).
    3. Grounding: No ungrounded pricing or diagnostic claims.
    4. Memory: No invented recollection of unrecorded patient history.
    5. Question discipline: Maximum of one question per turn.
    6. Non-repetition: Prevention of n-gram repetition loops.
  - Triggers `repair_turn` with specific feedback if any invariant fails.

### 2.5 LLM Gateway (`disha_core/llm/client.py`)
- **Client**: `DualProviderClient` manages dual-provider routing with Groq (`openai/gpt-oss-120b` or configured `qwen/qwen3.8-27b`) as primary provider and Google Gemini (`gemini-3.6-flash` or configured `gemini-3.1-flash-lite`) as instant secondary failover.
- **Circuit Breaker**: `ConsecutiveFailureCircuitBreaker` opens after 2 consecutive provider errors, enforcing a 30-second cooldown before testing a half-open probe.

### 2.6 Voice Session Handler & Real-Time Pipeline (`disha_core/voice.py`)
- **Protocol**: Bidirectional WebSocket connection on `/voice` and `/ws/conversation` with 25s ping-pong keep-alives.
- **Client-Side VAD & Turn-Taking**:
  - Web Audio Analyser computes speech-band RMS energy across frequency bins 0-8.
  - Exponential moving average (EMA, $\alpha=0.03$) tracks ambient room noise floor ($6.0 \le \text{noiseFloor} \le 32.0$).
  - Speech onset dynamically triggers at $\max(12.0, \text{noiseFloor} + 8.0)$.
  - Silence hangover timeout calibrated to **500 ms** (reduced from 850 ms, saving 350 ms of turn-taking latency).
- **Audio Pre-Roll Buffer**: Client maintains a 200 ms rolling buffer of recent audio slices, prepended on speech onset to prevent clipping initial syllables (*"kya"*, *"namaste"*, *"poha"*).
- **STT Transcription**: Groq Whisper Large v3 Turbo conditioned with `GROQ_WHISPER_PROMPT_VOCABULARY` containing 38 Indian clinical, vital, symptom, and dietary terms. Auto-detects `audio/wav`, `audio/webm`, and `audio/ogg`.
- **Audio Synthesis**: Sentence-level streaming pipeline. Completed punctuation sentences stream immediately to Edge-TTS (`hi-IN-SwaraNeural` for Hindi/Hinglish, `en-IN-NeerjaExpressiveNeural` / `en-IN-NeerjaNeural` for English).
- **Instant Emergency Audio Fallback**: Pre-rendered neural audio files stored in `disha_core/data/emergency_audio/` and RAM cache deliver red-flag responses in **0.012 ms**, completely bypassing cloud TTS latency. Browser `speechSynthesis` acts as client-side backup.
- **Fast Barge-In Cancellation**: User speech during audio playback instantly drains `state.audioQueue`, stops Web Audio buffer sources, pauses HTML5 audio, and dispatches `{"type": "interrupt"}` over WebSocket. Cancellation completes in **0.015 ms** (target $< 300\text{ ms}$).

## 3. Wire Formats and Schemas

### 3.1 Chat Stream Request & Event Protocol

#### Request (`POST /chat/stream`)
```json
{
  "text": "Maine subah 30 minute walk ki.",
  "conversation_id": "conv_4f81c9a2"
}
```

#### Response Stream (Server-Sent Events)
```text
event: sentence
data: {"index": 0, "text": "Bahut badiya! Daily walk blood pressure control mein madad karti hai."}

event: done
data: {"status": "accepted", "evidence_ids": ["chunk_icmr_102"], "conversation_id": "conv_4f81c9a2"}
```

### 3.2 Turn State Model (`disha_core/models/schemas.py`)
```python
class TurnState(BaseModel):
    patient_id: str
    user_input: str
    predicted_intent: str = "general_coaching"
    confidence: float = 1.0
    breaker_status: str = "passed"
    validator_status: str = "accepted"
    retrieval_status: str = "hit"
    evidence_ids: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
```

### 3.3 Audit Ledger Schema (`disha_core/compliance/ledger.py`)
```sql
CREATE TABLE audit_claim_ledger (
    turn_id BIGSERIAL PRIMARY KEY,
    event_id VARCHAR(64) UNIQUE NOT NULL,
    patient_id VARCHAR(64) NOT NULL,
    user_input TEXT NOT NULL,
    llm_output TEXT NOT NULL,
    breaker_status VARCHAR(32) NOT NULL,
    validator_status VARCHAR(32) NOT NULL,
    prev_hash VARCHAR(64) NOT NULL,
    current_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
Each entry computes `current_hash = SHA256(event_id + patient_id + user_input + llm_output + breaker_status + validator_status + prev_hash)`, providing a cryptographic tamper-evident verification chain.

## 4. Prompt Assembly and Token Budget

### 4.1 Prompt Assembly Pipeline
The runtime prompt assembly follows a cache-friendly static-to-dynamic layout:
1. **Static System Prompt (`_SPEC_V1_PROMPT`)**: Compiled from `data/behavior_rules.yaml` (474 tokens). Contains role persona, clinical safety constraints (C1-C4), core behavior rules (P1-P6, F1-F6, M1-M3), and language mode. Forms an immutable static prefix at the head of every request for hardware KV prefix caching (Groq 50% read discount, Gemini up to 90% read discount).
2. **Just-In-Time (JIT) Per-Intent XML Blocks**: Rendered by `render_context_xml()`. Dynamically injects only intent-relevant blocks while strictly preserving essential clinical safety facts (allergies, diagnoses, medications, pregnancy, age band, PEP limits) on all coaching turns. Conversational turns (greetings, chitchat, app meta) omit `<PEP>`, `<DIET_SLOT>`, and `<CLINICAL_GROUNDING>`.
3. **Retrieved Clinical Knowledge**: Verified guidelines from `retrieve_chunks()` (fusing pg_trgm and tsvector with Reciprocal Rank Fusion, $k=60$) capped to Top-1 or Top-2 chunks formatted as `<CLINICAL_GROUNDING>`. When zero chunks meet relevance thresholds, `<CLINICAL_GROUNDING status="NOT_FOUND"/>` is injected to prevent ungrounded hallucinations.
4. **Conversation Discipline & History**: Response length target (`<RESPONSE_TARGET>`), active conversation turns windowed to the last 4 turns (8 messages), and current `<USER_UTTERANCE>`.

### 4.2 Empirical Token Budget (Before vs. After Optimization)

Measured across real simulated turns (intents × patients × history lengths × languages) using Qwen2.5 BPE *(see [System Evaluation & Verification](EVALUATION.md) for full benchmark breakdown)*:

| Payload Section | Before (Tokens) | % Contribution | After (Tokens) | Net Savings | Primary Optimization Mechanism |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Conversation History** | 471.7 | 25.3% | 185.0 | -60.8% | Tightened rolling window to last 4 turns (8 messages); stripped verbose note attributes |
| **Slot Values & Facts** | 380.3 | 20.4% | 140.0 | -63.2% | JIT per-intent pruning; omitted lifestyle slots on pure conversational turns |
| **Behaviour Policies** | 323.0 | 17.3% | 150.0 | -53.6% | Deduplicated overlapping rules; consolidated P2/P7 and F2/F6; free-app alignment |
| **Safety Constraints** | 180.0 | 9.7% | 110.0 | -38.9% | Consolidated C1-C4 rules with deterministic code enforcement in `breaker.py` |
| **Patient Profile & PEP** | 232.3 | 12.5% | 115.0 | -50.5% | Compressed PEP permissions; pruned empty tags; JIT omission on non-coaching turns |
| **Retrieved RAG Chunks** | 158.0 | 8.5% | 45.0 | -71.5% | Capped to Top 1–2 chunks with 0.06 text score threshold; RRF (k=60) ranking |
| **System Persona / Prompt** | 83.0 | 4.5% | 75.0 | -9.6% | Deduplicated persona lines; immutable prefix cached across turns |
| **User Utterance & Bounds** | 34.5 | 1.8% | 34.5 | 0.0% | Preserved verbatim |
| **Total Prompt Input (Avg)** | **1,862.8** | **100%** | **812.0** | **-56.4%** | **Overall prompt reduction: 1,050.8 tokens/turn saved** |
| **Greetings / Chitchat Input** | **1,795.3** | **100%** | **689.0** | **-61.6%** | **Stripped non-conversational XML; lightweight language context only** |
| **Configured Max Output Tokens**| **256** | — | **120** | **-53.1%** | **Aligned with real completion distribution (median 72 tokens, P90 123 tokens)** |

## 5. PEP, Habits & Onboarding Architecture

### 5.1 Onboarding State Machine & Field Processing (`disha_core.journey`)
The onboarding system manages a structured 5-stage onboarding flow across chat and voice channels:
- Stage 1: Basic Patient Profile (name, age, gender, height, weight, preferred language).
- Stage 2: Health Background and Clinical Safety (diagnosed conditions, active medications, allergies/intolerances, transient symptoms, physical limitations, doctor exercise clearance).
- Stage 3: Lifestyle and Daily Routine (work shift schedule, wake time, sleep time, daily movement level, exercise habits, water intake target, tea/coffee frequency).
- Stage 4: Goals, Diet, and Personal Preferences (primary health goal, secondary goals, dietary style, disliked foods, regional cuisine, meal prep habits).
- Stage 5: Coaching Personalisation Readiness (verification that essential health safety parameters are recorded before unrestricted coaching).

Onboarding disclosures are recorded directly by `record_field_answer` with `source="onboarding"` and `verification_status="confirmed"`, bypassing LLM extraction entirely to ensure 100% deterministic fidelity. Question attempts and answers are tracked in `journey_question_history` to prevent repeated questions and double-writing.

### 5.2 Habits Engine & Hysteresis (`disha_core.pep.habits_engine`)
Lifestyle metrics follow three storage shapes:
1. **Current-State Habit Slots (`habit_current_state`)**: Active baseline metrics with partial unique index (`WHERE valid_to IS NULL`). Hysteresis rules require either an explicit permanence cue ("ab se", "from now on", "maine shuru kiya") or two reinforcing mentions before updating established baselines.
2. **Time-Series Observations (`habit_observations`)**: Periodic numeric disclosures (steps, blood pressure readings, water intake) partitioned by observation date with BRIN indexes for efficient analytical rollups.
3. **Transient Episodes (`habit_episodes`)**: Ephemeral symptoms (bloating, headache, loose motions) and short-term commitments tagged with automated expiration dates (default 48 hours for transient complaints).

### 5.3 Shared PEP Update Interface (`disha_core.pep.shared_interface`)
The PEP update lifecycle is unified across two competing strategies selected by `PEP_UPDATE_MODE`:
- `PEP_UPDATE_MODE=classifier`: Dispatches to classifier-gated turn-level extraction (Agent A), executing fast regex/keyword gating on each turn with zero LLM overhead on routine chat, and queueing background extraction jobs for health-relevant turns.
- `PEP_UPDATE_MODE=summary`: Dispatches to summary-then-update batch extraction (Agent B), executing a single structured LLM patch extraction upon session close or 10-minute idle timeout.
- `PEP_UPDATE_MODE=off`: Passthrough mode where experimental extractors are inactive.

Both strategies operate on the shared canonical slot schema (`PEPSlotRecord`): `slot`, `value`, `source` (`onboarding`, `chat_user`, `clinician`, `system`), `clinical_status` (`active`, `inactive`, `resolved`), `verification_status` (`unconfirmed`, `confirmed`, `entered_in_error`), `valid_from`, `valid_until`, and `evidence`.

### 5.4 Clinical Boundary & Contradiction Protection (`disha_core.models.slots`)
Clinical constraints are protected by deterministic gatekeepers before any slot is persisted:
- **Authority Validation (`validate_authority`)**: Prevents patient self-reports or LLM extraction from granting medical clearance or altering clinician-governed parameters (`SourceAuthority.PEP_DOCTOR`).
- **Contradiction Detection (`check_pep_contradiction`)**: Intercepts claims contradicting official doctor restrictions (e.g., patient claiming heavy weightlifting clearance while PEP restricts gym activity, or reporting high salt intake during clinical stage 2 hypertension). Detected contradictions are quarantined for clinician review with `epistemic_status="flagged_review"` and never silently applied.
