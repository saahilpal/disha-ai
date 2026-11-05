# 07. API Design & Streaming Protocols — Disha Clinical Voice AI

## 1. Interface Overview

Disha AI provides two communication interfaces:
1. **Real-Time Streaming WebSocket (`/ws/call/{patient_id}`):** Ultra-low-latency bidirectional channel for speech audio chunks, turn status, and live TTS audio streaming.
2. **Clinical Management & Simulation REST API (`/api/v1/*`):** Standard JSON endpoints for clinician rule authoring, stance configuration, patient data management, and automated regression testing.

---

## 2. Real-Time WebSocket Streaming Protocol

### Endpoint: `ws://localhost:8000/ws/call/{patient_id}`

```
Client (User / Browser / Telephony)                     Server (FastAPI Engine)
     │                                                               │
     ├──────────── Handshake & Session Initialization ──────────────>┤
     │<─────────── Connection Established (session_id) ──────────────┤
     │                                                               │
     ├──────────── Audio / Utterance Frame ─────────────────────────>┤
     │                                                               ├─> Pre-Turn Guard (<2µs)
     │                                                               ├─> JIT Hybrid RAG (<5ms)
     │                                                               ├─> Groq LPU Inference (TTFT 200ms)
     │<─────────── Event: 'turn_metadata' (retrieved rules) ─────────┤
     │                                                               ├─> Post-Turn Sanitizer (<1ms)
     │<─────────── Binary Frame: Audio Chunk 1 (MP3/Opus) ───────────┤
     │<─────────── Binary Frame: Audio Chunk 2 (MP3/Opus) ───────────┤
     │<─────────── Event: 'turn_complete' (Latency waterfall) ───────┤
```

### 2.1. Client-to-Server Messages

#### 1. Audio Data Frame (Raw Binary or Base64 PCM)
```json
{
  "type": "audio_chunk",
  "data": "<base64_encoded_pcm16_chunk>",
  "is_final": false
}
```

#### 2. Text Utterance Frame (Simulator / Direct STT Mode)
```json
{
  "type": "user_utterance",
  "text": "Mujhe periods ke chalte bahut bloating ho rahi hai"
}
```

#### 3. Barge-In / Interruption Frame
```json
{
  "type": "interrupt",
  "timestamp": 1730800000.12
}
```

### 2.2. Server-to-Client Messages

#### 1. Turn Metadata & Context Inspection
```json
{
  "type": "turn_metadata",
  "turn_id": "turn_987123",
  "stt_transcript": "Mujhe periods ke chalte bahut bloating ho rahi hai",
  "pre_guardrail": "PASS",
  "retrieved_rules": [
    {
      "code": "RULE_BLOATING_REMEDY",
      "remedy": "Warm jeera-saunf water twice daily"
    }
  ],
  "pep_context": {
    "dietary_preference": "Vegetarian",
    "allowed_exercise": ["gym", "home"]
  }
}
```

#### 2. Emergency Halt Event (Instant Red Flag)
```json
{
  "type": "emergency_halt",
  "turn_id": "turn_987124",
  "red_flag_category": "cardiovascular",
  "detected_symptoms": ["chest pain", "left arm numbness"],
  "action": "LLM_ABORTED_EMERGENCY_AUDIO_TRIGGERED",
  "triage_message": "Yeh symptoms serious ho sakte hain. Kripya turant workout band karein aur hospital ya 112 par call karein."
}
```

#### 3. Streaming Audio Chunk (Binary Frame)
Binary WebSocket message containing 16kHz MP3/Opus audio bytes, streamed sentence-by-sentence as synthesis completes.

#### 4. Turn Completion & Latency Breakdown
```json
{
  "type": "turn_complete",
  "turn_id": "turn_987123",
  "assistant_text": "Periods ke dauran bloating common hai. Aap din mein do baar gungune paani mein jeera aur saunf ubaal kar pijiye, isse kaafi aaram milega.",
  "latency": {
    "vad_silence_ms": 180,
    "stt_ms": 135,
    "guardrail_ms": 0.005,
    "rag_retrieval_ms": 3.8,
    "llm_ttft_ms": 210,
    "tts_ttfb_ms": 195,
    "total_turn_latency_ms": 723.8
  }
}
```

---

## 3. Clinical Management & Simulation REST API

### 3.1. Clinical Rules & Stances

#### `GET /api/v1/rules`
Retrieve all clinician rules, searchable by category or keyword.
- **Response:**
```json
[
  {
    "id": "rule_01",
    "rule_code": "RULE_BLOATING_REMEDY",
    "category": "symptom_remedy",
    "trigger_keywords": ["bloating", "pet phoolna", "gas", "distension"],
    "clinical_remedy": "Advise drinking warm jeera-saunf (cumin-fennel) water twice daily.",
    "rationale": "Proven carminative botanical remedy approved by Disha clinical nutrition board.",
    "author_name": "Dr. Ananya Sharma (Lead Dietitian)",
    "status": "active",
    "version": 1
  }
]
```

#### `POST /api/v1/rules`
Create or update a clinical rule. **Automatically runs the pre-publishing regression test suite.**
- **Request Body:**
```json
{
  "rule_code": "RULE_MANGO_WEIGHT_LOSS",
  "category": "diet_protocol",
  "trigger_keywords": ["mango", "aam", "fruits in diet"],
  "clinical_remedy": "Advise seasonal moderation: 1/2 mango (100g) mid-morning; do not prohibit.",
  "rationale": "High fiber and micronutrient density; strict bans cause diet fatigue.",
  "author_name": "Dr. Ramesh Patel (Chief Medical Officer)"
}
```
- **Response (Success - Regression Passed):**
```json
{
  "success": true,
  "rule_id": "rule_02",
  "regression_results": {
    "total_tests": 50,
    "passed": 50,
    "failed": 0,
    "emergency_pass_rate": 1.0,
    "status": "PUBLISHED_TO_PRODUCTION"
  }
}
```

---

### 3.2. Patient Encounter Profile (PEP) & Dynamic Data

#### `GET /api/v1/patients/{patient_id}`
Retrieve complete patient context including active PEP and today's meal plan.
- **Response:**
```json
{
  "patient_id": "pt_101",
  "full_name": "Pooja Verma",
  "phone": "+919876543210",
  "primary_goal": "PCOS & Weight Management",
  "pep": {
    "allowed_exercise_locations": ["gym", "home", "outdoors"],
    "target_activity": "Strength training 3x/week + 10k steps",
    "dietary_preference": "Vegetarian",
    "medical_conditions": ["PCOS", "Mild Gastritis"],
    "emergency_contact": "+919811223344"
  },
  "today_diet_chart": {
    "day": "Wednesday",
    "dinner": {
      "meal_name": "High-Protein Light Dinner",
      "items": "Paneer bhurji (150g), 2 multigrain rotis, cucumber salad with flax seeds",
      "calories": 420
    }
  }
}
```

---

### 3.3. Simulation & Automated Regression Testing

#### `POST /api/v1/simulation/turn`
Simulate an end-to-end conversation turn without placing a live phone call. Returns comprehensive execution trace (guardrail verdicts, retrieved rules, raw vs sanitized LLM output, timing breakdown).
- **Request:**
```json
{
  "patient_id": "pt_101",
  "utterance": "Workout karte waqt seene mein dard aur left hand numb ho raha hai"
}
```
- **Response:**
```json
{
  "turn_status": "EMERGENCY_HALTED",
  "pre_guardrail": {
    "triggered": true,
    "red_flag": "cardiovascular",
    "detected_keywords": ["seene mein dard", "left hand numb"],
    "execution_time_ms": 0.003
  },
  "llm_called": false,
  "emergency_action": "DISPATCH_AMBULANCE_NOTIFICATION",
  "synthesized_response": "Yeh symptoms serious ho sakte hain. Kripya turant workout rokein, aaram karein aur emergency hospital ya 112 par call karein. Hum aapki care team ko alert bhej rahe hain."
}
```

#### `POST /api/v1/simulation/run-regression-suite`
Executes all 50+ benchmark cases across the 8 production failure classes, measuring accuracy, hallucinations, and safety.
- **Response:**
```json
{
  "timestamp": "2026-11-05T07:22:15Z",
  "total_benchmarks": 52,
  "passed": 52,
  "pass_rate": 100.0,
  "failure_breakdown": {
    "wrong_statements": {"tested": 16, "passed": 16},
    "missed_actions": {"tested": 20, "passed": 20},
    "missing_facts": {"tested": 16, "passed": 16}
  },
  "emergency_recall": 1.0,
  "average_latency_ms": 782.4
}
```
