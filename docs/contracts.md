# DISHA AI — SYSTEM CONTRACTS & SHARED INTERFACES

## 1. HTTP REST & SSE API Contracts

### Authentication (`POST /api/auth/login`)
- **Request Body**:
  ```json
  { "phone_number": "+919876543210" }
  ```
- **Response** (HTTP 200):
  ```json
  { "token": "<JWT_TOKEN>", "patient_id": "pt_..." }
  ```
- **Rate Limit**: 20 requests per IP per minute.

### Chat Inference (`POST /api/chat`)
- **Headers**: `Authorization: Bearer <JWT_TOKEN>`
- **Request Body**:
  ```json
  { "message": "Daily kitna paani peena chahiye?" }
  ```
- **Response** (HTTP 200):
  ```json
  {
    "response": "Normally 2.5 se 3.5 liters paani daily peena safe rehta hai.",
    "status": "completed",
    "intent": "GENERAL_COACHING",
    "pep_risk": 0
  }
  ```
- **Rate Limit**: 60 requests per IP per minute. Payload limit: 2 MB.

---

## 2. WebSocket Real-Time Voice Contract (`/ws/voice`)

- **Protocol**: Binary PCM audio chunks (`16 kHz, 16-bit mono`).
- **Heartbeat**: Ping/pong every 30 seconds; 300-second idle disconnect timeout.
- **Events**:
  - `start_session`: client sends session metadata.
  - `audio_chunk`: binary PCM stream from microphone.
  - `transcript_interim`: partial ASR text from Whisper/Groq.
  - `transcript_final`: committed user utterance.
  - `audio_tts_stream`: binary synthesized audio chunks from Qwen3-TTS / Kokoro.
  - `barge_in`: triggers immediate cancellation of pending TTS and LLM tasks within 100ms.

---

## 3. Database Persistence Contracts (PostgreSQL)

### `patient_turn_journal`
```sql
CREATE TABLE IF NOT EXISTS patient_turn_journal (
    id BIGSERIAL PRIMARY KEY,
    patient_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    turn_no INT NOT NULL,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    intent VARCHAR(32),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### `patient_temporal_facts`
```sql
CREATE TABLE IF NOT EXISTS patient_temporal_facts (
    id BIGSERIAL PRIMARY KEY,
    patient_id VARCHAR(64) NOT NULL,
    category VARCHAR(32) NOT NULL,
    fact_key VARCHAR(64) NOT NULL,
    fact_value JSONB NOT NULL,
    status VARCHAR(16) DEFAULT 'active',
    valid_from TIMESTAMPTZ DEFAULT NOW(),
    valid_to TIMESTAMPTZ,
    superseded_by BIGINT
);
```

### `patient_pep`
```sql
CREATE TABLE IF NOT EXISTS patient_pep (
    patient_id VARCHAR(64) PRIMARY KEY,
    hypertension_stage VARCHAR(32),
    gym_clearance BOOLEAN DEFAULT FALSE,
    allowed_modalities TEXT[] DEFAULT '{}',
    restricted_modalities TEXT[] DEFAULT '{}',
    verified_by VARCHAR(64),
    verified_at TIMESTAMPTZ
);
```

---

## 5. Knowledge Store & Provenance Contracts

### `knowledge_sources`
```sql
CREATE TABLE IF NOT EXISTS knowledge_sources (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    license VARCHAR(64) NOT NULL,
    url TEXT NOT NULL,
    version VARCHAR(32) NOT NULL,
    ingest_date DATE NOT NULL DEFAULT CURRENT_DATE,
    language VARCHAR(16) NOT NULL DEFAULT 'en',
    domain VARCHAR(64) NOT NULL,
    trust_tier VARCHAR(16) NOT NULL CHECK (trust_tier IN ('CLINICAL_GOLD', 'REGULATORY', 'ACADEMIC', 'PRODUCT'))
);
```

### `knowledge_chunks`
```sql
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id BIGSERIAL PRIMARY KEY,
    source_id VARCHAR(64) REFERENCES knowledge_sources(id),
    domain VARCHAR(64) NOT NULL,
    condition_tags TEXT[] DEFAULT '{}',
    diet_tags TEXT[] DEFAULT '{}',
    language VARCHAR(16) NOT NULL,
    script VARCHAR(16) NOT NULL DEFAULT 'latin',
    content TEXT NOT NULL,
    fts_vector TSVECTOR,
    derived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Zero-Hardcoding Contract:
- No nutrition rules, food lists, remedy texts, or exercise restrictions in Python constants.
- All clinical guidelines must reference `source_id` in `knowledge_sources`.
- If an unverified fact or ingredient is queried, retriever must yield 0 chunks and fallback safely rather than hallucinating.

---

## 6. Slot Registry & Patient Habit Authority Contract

### Authority Separation:
| Authority Tier | Source | Permitted Slot Keys | Overwrite Policy |
|---|---|---|---|
| `PEP_DOCTOR` | Verified Clinical Record (`patient_pep`) | `gym_clearance`, `allowed_modalities`, `restricted_modalities`, `hypertension_stage` | IMMUTABLE by patient or LLM |
| `PATIENT_REPORTED` | Chat / Voice extraction | `wake_time`, `sleep_time`, `water_intake_target`, `daily_steps_target`, `tea_coffee_frequency` | Updated with provenance turn_id |

- **Strict Invariant**: Any LLM attempt to modify a `PEP_DOCTOR` slot results in an immediate rejection and flagged contradiction in `patient_temporal_facts`.

---

## 7. Voice Pipeline & Language Routing Contract

### Supported Languages:
- `en-IN` / `en-US`: English
- `hi-IN` (Devanagari): Hindi
- `hi-Latn` / Hinglish: Romanized Hindi

### TTS Routing Policy:
```
Turn Language Detection:
  ├── Devanagari script detected OR Hindi/Hinglish tokens ≥ 20%
  │     └── Route to Edge-TTS: hi-IN-SwaraNeural / hi-IN-MadhurNeural
  └── Pure English OR medical terminology heavy
        └── Route to Qwen3-TTS / local MPS neural engine
```

### Barge-In / Interruption SLA:
- On user audio arrival during TTS playback:
  1. Abort sentence generator stream immediately.
  2. Send WebSocket `{"event": "stop_audio"}` frame to client.
  3. Client stops audio buffer playback within ≤ 50ms.

---

## 8. Token Budgets & Cost Ledger Contract

### Context Assembly Budget (~2,000 tokens total):
- System Identity & Boundaries: **≤ 500 tokens** (fixed)
- Patient PEP & Clinical Restrictions: **≤ 200 tokens**
- Patient Habits & Long-Term Memory: **≤ 250 tokens**
- Retrieved Knowledge Chunks (top 2-3): **≤ 450 tokens**
- Conversation History (last 3-4 turns): **≤ 400 tokens**
- User Input & Safety Metadata: **≤ 200 tokens**


