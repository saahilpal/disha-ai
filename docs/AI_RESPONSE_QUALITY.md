# AI Response Quality, Anti-Echo, and Length Control Architecture

## Executive Overview

The current response lifecycle is designed for patient-centred coaching without robotic clichés, mechanical question parroting, or a rigid length constraint. Model quality still depends on the configured provider and is evaluated with controlled multi-turn cases.

### Core Architectural Principles
1. **Zero Mechanical Echo**: The assistant avoids parroting the patient's wording, while allowing a brief contextual reference when it helps resolve a correction or follow-up.
2. **Direct Answer First**: Sentence 1 must deliver the substantive answer or primary actionable advice directly, eliminating introductory empathy fluff and repetitive greetings.
3. **Dynamic Response Length Targeting**: Response length is tailored dynamically based on user intent and query complexity rather than forcing every turn into a rigid sentence count.
4. **Context Relevance Discipline**: Meals and diet schedules are only discussed if the patient explicitly asked about food; workouts and gym routines are only brought up if the patient asked about physical activity.
5. **Single Behaviour Source**: `data/behavior_rules.yaml` supplies the model-facing behavior and clinical policy. Python keeps only deterministic safety, persistence, validation, and response-delivery checks; it does not choose a scripted onboarding move.

The five-stage PEP journey is an internal completeness measure. The live harness now asks the existing scheduler for one pending discovery opportunity after disclosures are applied. The scheduler can surface a later-stage detail when the user's current wording makes it relevant, while preserving the current-stage fallback otherwise. The candidate is recorded as pending for deterministic answer extraction, but remains optional model context: the model answers the current request first and may let the topic settle. Stages and checklist fields are not exposed in the prompt.

The investigation found four causes of shallow or mechanical turns: the scheduler was implemented but never called by the shared chat/voice harness; discovery context only listed required fields from the lowest incomplete stage, hiding useful optional and later-stage details; the active behavior policy asked for one-to-three sentences even when a thread needed a little more development; and the final verifier still rejected the four-sentence coaching policy, triggering unnecessary repairs. The fix reuses the existing scheduler, makes relevance outrank stage order when supported by the user's wording, makes discovery optional and intent-scoped, and aligns final verification with the per-turn response target.

---

## Response Lifecycle Architecture

```mermaid
sequenceDiagram
    autonumber
    actor Patient as Patient / Client
    participant Router as IntentRouter & Breaker
    participant Norm as Normalizer
    participant Context as ContextBuilder
    participant LLM as DualProviderClient (Groq/Gemini/Ollama)
    participant Buffer as SentenceBuffer (Dynamic Length)
    participant AntiEcho as Anti-Echo & Direct-Answer Engine
    participant Val as SentenceValidator
    participant Egress as WebSocket / Voice TTS

    Patient->>Router: TurnRequest (text or speech)
    Router->>Norm: Pre-turn Breaker & Intent Classification
    Norm-->>Context: NormalizedText (tags, domain flags, complexity)
    Context->>Context: determine_length_policy(query)
    Context->>Context: Select relevant patient profile & clinical grounding
    Context->>LLM: Stream prompt with <RESPONSE_TARGET> & <RESPONSE_DISCIPLINE>
    LLM-->>Buffer: Stream tokens
    Buffer->>Buffer: Punctuation Boundary Detection
    Buffer->>AntiEcho: Evaluate Opening Sentence (Pure Filler / Echo Detection)
    alt Opening sentence is pure empathy filler / echo
        AntiEcho-->>Buffer: Drop filler, advance substantive sentence to Sentence 1
    end
    Buffer->>Val: validate_turn / validate_sentence
    Val-->>Buffer: Validated & TTS-sanitized sentence
    Buffer->>Egress: Yield sentence (egress latency < 600ms)
    alt Sentence limit reached (LengthPolicy.max_sentences)
        Buffer->>Buffer: Check for pending clinical safety statement
        opt Pending clinical safety statement exists
            Buffer->>Egress: Yield clinical safety statement
        end
        Buffer-->>LLM: aclose() stream
    end
```

---

## Detailed Component Implementation

### 1. Anti-Echo Engine (`disha_core/engine/anti_echo.py`)

The Anti-Echo Engine provides two layers of protection: **clause-level stripping** and **turn-level filler removal**.

#### A. Clause-Level Echo Stripping (`strip_echo_prefix`)
Removes introductory inquiry prefixes and parroting dependent clauses across English, Hinglish, and Hindi (Devanagari):
- **Hinglish / Hindi**:
  - `Aapne poocha ki...`
  - `Aapne bataya ki...`
  - `Aapne kaha ki...`
  - `Jaise ki aapne poocha...`
  - `Aap keh rahe hain ki...`
  - `Jahan tak aapke sawaal ki baat hai...`
  - `आपने पूछा कि...`
- **English**:
  - `Regarding your question about...`
  - `To answer your question regarding...`
  - `As you mentioned...`
  - `You asked about / if / whether...`
  - `In response to your question...`

When a match is stripped, any trailing conjunction (e.g. *", toh"*, *", so"*, *", therefore"*) is removed, and the remaining substantive clause is capitalized cleanly:
> **Input:** *"Aapne poocha ki pet mein dard hai, toh sabse pehle thoda gunguna paani piyein."*  
> **Output:** *"Sabse pehle thoda gunguna paani piyein."*

#### B. Turn-Opening Filler Removal (`is_pure_echo_or_filler`)
Detects sentences that contain only empathy fluff or question repetitions without actionable advice:
- *"I understand you have been feeling tired after work."*
- *"Main samajh sakti hoon ki aap kaisa mehsoos kar rahe hain."*
- *"Sunkar bura laga ki aapki tabiyat theek nahi hai."*

In `validated_sentences`, if the opening sentence is identified as pure filler, it is omitted from streaming egress, promoting the substantive guidance in sentence 2 to **Sentence 1**.

#### C. Redundant Greeting Suppression (`strip_all_greetings`)
On turns where conversation history exists (`has_history=True`), robotic and redundant greetings (*"Namaste! Main Disha hoon"*, *"Aapka swagat hai"*) are stripped automatically.

---

## Dynamic Response Length Policy

Rather than forcing all turns into an arbitrary 3-sentence limit, Disha AI implements dynamic length targeting via `LengthPolicy`.

| Query Category | Trigger Conditions | Min Sentences | Max Sentences | Purpose |
| :--- | :--- | :---: | :---: | :--- |
| **Emergency** | `is_emergency=True` or triage trigger | 1 | 2 | Immediate, direct life-safety instructions without conversational fluff. |
| **Factual / Lookup** | Pricing, identity, definitions, simple yes/no queries (`is_simple_factual`) | 1 | 2 | Crisp, accurate direct answer (e.g. ₹0 follow-ups, ₹1,499 nutritionist plan). |
| **Everyday Coaching** | Habit building, walking, sleep tips, hydration, routines (default) | 2 | 4 | Actionable, empathetic step-by-step coaching guidance. |
| **Complex Health** | Multiple symptoms, chronic condition interactions, unexplained severe symptoms | 3 | 5 | Structured explanation with clinical safety guidance and practical next steps. |
| **Detailed Request** | Explicit request for detail (*"explain in detail"*, *"vistar se samjhao"*, *"step by step"*) | 3 | 7 | Comprehensive breakdown honoring the user's explicit request. |

### Essential Clinical Safety Invariant
When the sentence budget (`max_sentences`) is reached, `sentence_buffer.py` checks if the immediate next sentence from the model is a clinical safety referral (e.g. *"Agar dard badhta hai toh turant doctor se consult karein"* or hospital/112 referral). If present, the clinical safety disclaimer is **always emitted** before aborting the stream. Clinical safety information is never truncated.

---

## Context Relevance & Direct-Answer Discipline

To keep the LLM focused on answering the patient's immediate question without unprompted lectures:

1. **Domain Relevance Detection** (`disha_core/engine/normalizer.py`):
   - `is_meal_query`: Detects if the user asked about food, meals, recipes, or nutrition.
   - `is_exercise_query`: Detects if the user asked about workouts, gym, running, or exercise.

2. **Lean Context XML Injection** (`disha_core/engine/context_builder.py`):
   - If `meal_relevant` is `False`, specific meal items from `patient_diet_schedules` are omitted from the prompt.
   - If `exercise_relevant` is `False`, `PEP_PERMISSIONS` are annotated as background safety bounds only.
   - Injected discipline instruction:
     ```xml
     <RESPONSE_DISCIPLINE answer_first="true" prompted_for_meals="false" prompted_for_exercise="false"/>
     <RESPONSE_TARGET category="coaching" min_sentences="2" max_sentences="4"/>
     ```

3. **No Prompt Bloat**:
   - The root system prompt (`SYSTEM_PROMPT`) remains clean, concise, and focused on Disha's voice and essential safety invariants.
   - Dynamic operational boundaries are passed in structured turn payloads and enforced by deterministic Python pipeline validators.

---

## Automated Verification & Test Coverage

All quality, anti-echo, and length control directives are verified through automated unit and integration tests in `disha_core/tests/test_reasoning_and_quality.py`:

```
disha_core/tests/test_reasoning_and_quality.py::AntiEchoQualityTests
  - test_strip_echo_prefix_hinglish_inquiry                PASSED
  - test_strip_echo_prefix_english_inquiry                 PASSED
  - test_strip_echo_prefix_hindi_devanagari                PASSED
  - test_pure_empathy_filler_detection                     PASSED
  - test_filter_response_sentences_promotes_direct_answer  PASSED
  - test_filter_response_sentences_suppresses_greetings    PASSED
  - test_affirmative_answers_not_mutilated                 PASSED

disha_core/tests/test_reasoning_and_quality.py::ResponseLengthPolicyTests
  - test_factual_query_length_policy                       PASSED
  - test_coaching_query_length_policy                      PASSED
  - test_complex_health_query_length_policy                PASSED
  - test_detailed_query_length_policy                     PASSED
  - test_emergency_length_policy                           PASSED

disha_core/tests/test_reasoning_and_quality.py::StreamingSentenceBufferQualityTests
  - test_factual_query_streaming_enforces_max_length       PASSED
  - test_anti_echo_in_stream_skips_filler_and_answers      PASSED
  - test_safety_disclaimer_preserved_at_boundary           PASSED

disha_core/tests/test_reasoning_and_quality.py::ContextRelevanceTests
  - test_user_query_domain_detection                       PASSED
  - test_render_payload_includes_discipline_tags           PASSED
```

**Full Test Suite Status**:
- `disha_core/tests/test_invariants.py`: 48/48 PASSED
- `disha_core/tests/test_reasoning_and_quality.py`: 17/17 PASSED
- `disha_core/tests/test_voice_pipeline.py`: 12/12 PASSED
- **Total `disha_core` test suite: 77/77 PASSED (100%)**.
