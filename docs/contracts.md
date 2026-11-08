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

## 4. Laya Clinical Intent Classifier Schema (`2026-11-08.v2`)

```json
{
  "intent": "CHIT_CHAT | SYMPTOM | DIET | WORKOUT | PLAN_LOOKUP | EMERGENCY | GENERAL_COACHING | APP_META",
  "confidence": 0.95,
  "pep_risk": 0,
  "requires_retrieval": true,
  "red_flag": false
}
```
- Short-circuits DB retrieval when `requires_retrieval == false` (latency drops to <200ms).
- Early PEP risk triage triggers replacement when `pep_risk >= 2`.

