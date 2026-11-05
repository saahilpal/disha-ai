# 02. Functional Requirements Document — Disha Clinical Voice AI

## 1. System Modules Overview

The Disha AI platform is divided into five core functional subsystems:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DISHA CLINICAL VOICE AI                            │
├──────────────────────┬──────────────────────┬───────────────────────────────┤
│ 1. Voice Turn Engine │ 2. Knowledge & RAG   │ 3. Clinical Authoring Studio  │
│    • VAD & Silence   │    • SQLite FTS5     │    • Rule & Remedy Editor     │
│    • Groq Whisper STT│    • Hybrid Embeddings│    • Stance & Persona Manager │
│    • Pre/Post Guards │    • Dynamic DB Fetch│    • Visual Simulator         │
│    • Llama-3.3 LLM   │    • PEP Profile Sync│    • Zero-Regression Gate     │
│    • edge-tts Stream │    • Grounding Cache │                               │
├──────────────────────┴──────────────────────┴───────────────────────────────┤
│ 4. Deterministic Guardrails & Safety     │ 5. Care Ops & Escalations        │
│    • Red-Flag Circuit Breaker (<2µs)     │    • Emergency Webhook Dispatch  │
│    • Persona Identity Enforcer           │    • Call Audit & Review Ledger  │
│    • Capability Filter (No WhatsApp)     │    • Clinician Feedback Loop     │
│    • Price Sanity Checker                │                                  │
└──────────────────────────────────────────┴──────────────────────────────────┘
```

---

## 2. Subsystem 1: Real-Time Voice Turn Pipeline

### FR-1.1: Audio Ingestion & Silence Detection (VAD)
- The system shall ingest PCM audio stream chunks (16kHz, 16-bit mono) via WebSockets.
- The Voice Activity Detector (VAD) shall detect speech completion with a configurable trailing silence window (default **200ms**, dynamic range 150ms–300ms) to accommodate natural Hinglish speech cadence.
- Audio chunks shall be accumulated in-memory and immediately passed to the STT module upon speech completion.

### FR-1.2: Speech-to-Text (STT) Transcription
- The STT module shall convert user speech to text with a P95 latency under **200ms**.
- The primary STT engine shall be Groq Whisper-large-v3-turbo.
- The STT request must include an initial clinical Hinglish context prompt (`prompt="Hinglish patient follow-up: BP, bloating, jeera paani, saunf, gym, migraine, nausea, diet chart, weakness"`) to bias phonetic decoding towards medical and dietary vocabulary.
- The system must support local fallback (Faster-Whisper or browser Web Speech API) in offline or rate-limited environments.

### FR-1.3: Conversational LLM Reasoning
- The conversational intelligence engine shall generate empathetic, concise, clinically grounded Hinglish responses.
- Primary LLM: `llama-3.3-70b-versatile` (or `llama-3.1-8b-instant`) on Groq LPU, targeting a Time-To-First-Token (TTFT) under **250ms**.
- Response length shall be constrained to 1–2 conversational sentences (15–35 words) per turn to maintain conversational turn speed and natural dialogue pacing.
- The LLM must strictly output conversational Hinglish without Markdown asterisks, bold tags, or list bullets that degrade TTS pronunciation.

### FR-1.4: Text-to-Speech (TTS) Streaming
- The TTS engine shall synthesize natural-sounding Indian voice audio using `edge-tts` (`hi-IN-SwaraNeural` for Hindi/Hinglish, `en-IN-NeerjaNeural` for Indian English).
- The engine shall stream audio chunks via WebSocket as soon as the first sentence boundary (`.`, `?`, `!`, or newline) is emitted by the LLM.
- First audio chunk latency (TTFB) must be under **250ms**.

---

## 3. Subsystem 2: Knowledge Base & Just-in-Time Context Retrieval

### FR-2.1: Multi-Tier Knowledge Hierarchy
The system prompt shall never be bloated with static clinical textbooks or full menus. Knowledge must be retrieved Just-in-Time (JIT) into an ephemeral turn context across three tiers:
1. **Tier 1: Ground Truth Business Facts** (Pricing, subscriptions, trial limits, support channels).
2. **Tier 2: Vetted Clinical Protocols & Stances** (Remedies for symptoms, approved food stances, exercise guidelines).
3. **Tier 3: Dynamic Patient Context** (Patient PEP, today's meal plan, workout status, medical constraints).

### FR-2.2: Hybrid Search Pipeline (SQLite FTS5 + Tag + Vector)
- **Deterministic Tag Matching:** Direct index lookup for explicit symptom or food tags (e.g., `tag:bloating`, `tag:mango`, `tag:pricing`). Latency: **<0.2ms**.
- **Full-Text BM25 Search:** SQLite FTS5 table indexing clinician rules, triggers, and remedies. Latency: **<1.5ms**.
- **Semantic Vector Re-Ranking:** FastEmbed ONNX embedding (`paraphrase-multilingual-MiniLM-L12-v2`) computing cosine similarity against top candidate rules. Latency: **<5ms**.
- **Token Budget Guarantee:** Total retrieved knowledge injected into the prompt must never exceed **250 tokens per turn**, preventing context bloat and latency spikes.

### FR-2.3: Dynamic Patient Database Grounding
- When a user asks about personal schedule data (*"Aaj dinner mein kya hai?"*), the system must query `patient_diet_plans` for the specific `patient_id`, current weekday, and meal type.
- The retrieved database record (`"Paneer bhurji (150g), 2 multigrain rotis, green salad"`) must be injected into the turn prompt under a `[VERIFIED_SYSTEM_DATA]` delimiter.
- If no record exists, the system must instruct the model to state that the diet plan is being reviewed by the dietitian, rather than guessing.

### FR-2.4: Patient Encounter Profile (PEP) Grounding
- Each patient session must load the active PEP schema containing:
  - `allowed_exercise_locations`: `["gym", "home", "outdoors"]`
  - `dietary_preference`: `"vegetarian" | "eggetarian" | "non-vegetarian"`
  - `medical_flags`: `["hypertension", "PCOS", "Type-2-Diabetes"]`
- When the user mentions gym or workouts, the system must reinforce PEP permissions and prevent the AI from defaulting to contradictory home-workout tropes.

---

## 4. Subsystem 3: Deterministic Guardrails & Safety Architecture

### FR-3.1: Pre-Turn Red-Flag Circuit Breaker (Zero-LLM Bypass)
- **Requirement:** 100% recall on medical emergencies with **<5ms latency**.
- **Execution:** Before calling the LLM, the raw transcript is scanned against a compiled Aho-Corasick / regex pattern dictionary containing red flags in English and Romanized Hinglish.
- **Emergency Categories Covered:**
  - *Cardiovascular:* Chest pain (`seene mein dard`), left-arm pain/numbness (`baaye haath mein dard/sunn`), heavy pressure (`chhati pe dabav`).
  - *Respiratory:* Severe shortness of breath (`saans lene mein takleef`), choking (`dam ghutna`).
  - *Neurological:* Sudden facial droop, slurred speech (`bolne mein ladkhadahat`), fainting/loss of consciousness (`behosh`).
  - *Psychiatric:* Suicidal ideation, self-harm.
- **Action upon trigger:**
  1. The LLM call is **aborted immediately** (0 tokens generated).
  2. Pre-recorded/pre-synthesized emergency triage audio is returned instantly (<150ms):
     *"Yeh symptoms serious ho sakte hain. Kripya turant exercise band karein, rest karein aur turant emergency hospital ya 112/108 par consult karein. Hum aapke emergency contact aur doctor ko bhi notify kar rahe hain."*
  3. Session state transitions to `EMERGENCY_HALT`.
  4. An asynchronous high-priority escalation webhook is dispatched to the Care Ops Dashboard.

### FR-3.2: Post-Turn Output Interceptor & Sanitizer
- Every response generated by the LLM must pass through a deterministic post-turn sanitizer before audio streaming to TTS:
  - **Persona Protection Check (Failure #4):** If the model claims to be human, female human, or denies being an AI, the sanitizer replaces the turn with:
    *"Main Disha hoon, aapki AI health coach. Main aapke doctor ke care plan ke sath aapko healthy habits build karne mein guide karti hoon."*
  - **Capability Boundary Check (Failure #3):** If the model promises delivery via unsupported channels (`WhatsApp`, `SMS`, `Email`, `Post`), the sanitizer rewrites the message to reference the Disha App:
    *"Aapka diet chart Disha mobile app ke 'My Plan' tab mein already available hai, aap wahan se directly dekh sakte hain."*
  - **Pricing Sanity Check (Failure #1):** If the model emits arbitrary currency figures (e.g. ₹999, ₹2000) not matching the authorized pricing table, the sanitizer substitutes the verified pricing factsheet.

---

## 5. Subsystem 4: Clinical Authoring Studio & Zero-Regression Gate

### FR-4.1: No-Code Clinician Interface
- Clinicians (doctors, dietitians, wellness coaches) shall have access to a clean web portal allowing them to:
  - **Add/Edit Clinical Rules:** Specify trigger keywords/phrases (Hinglish + English), condition criteria (e.g. `symptom == bloating`), approved clinical advice (`"Advise warm jeera/saunf water twice daily"`), and rationale.
  - **Manage Dietary & Clinical Stances:** Define organization-wide stances on controversial foods (e.g., *Mangoes: Allowed in seasonal moderation, 100g daytime, do not ban*).
  - **Update System Boundaries:** Toggle allowed delivery channels and service capabilities.
  - **Preview in Real-Time Simulator:** Test the rule immediately inside an interactive chat/voice sandbox.

### FR-4.2: Automated Regression Test Gate (Pre-Publishing Oracle)
- To prevent a new rule from regressing prior clinical behaviors, the system must execute an automated test suite before any rule is published to production.
- **The Golden Test Suite:** A suite of 50+ historical benchmark turns covering all past failure modes (pricing, bloating, WhatsApp, persona, chest pain, diet chart, gym PEP, mangoes).
- **Gate Threshold:**
  - Emergency red-flag pass rate must be **100%**.
  - Overall clinical guideline alignment must be **$\ge 98\%$**.
  - Turn latency must remain **$< 1.5$ seconds**.
- If a proposed rule causes any existing test to fail, publishing is blocked with a visual diff explaining the conflict to the clinician.

---

## 6. Subsystem 5: Care Ops, Audit & Evaluation Ledger

### FR-6.1: Immutable Call Audit Ledger
- Every voice call turn must be logged with:
  - User utterance audio & STT transcript.
  - Pre-turn guardrail outcome (PASS / EMERGENCY_TRIGGERED).
  - Retrieved knowledge snippets and PEP attributes.
  - Raw LLM output and Post-turn sanitizer modifications.
  - Turn latency breakdown (VAD ms, STT ms, Retrieval ms, LLM TTFT ms, TTS TTFB ms).
  - Clinician feedback tags (Thums up/down, Clinical Error Flag).

### FR-6.2: Post-Call Asynchronous Evaluation Worker
- After call completion, an asynchronous evaluator assesses the conversation for:
  - Clinical protocol compliance.
  - Patient satisfaction and sentiment.
  - Emerging failure modes or novel Hinglish slang not present in the dictionary.
  - Generating weekly clinician review batches.
