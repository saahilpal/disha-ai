# 03. Non-Functional Requirements Document (NFR) — Disha Clinical Voice AI

## 1. Latency & Performance Engineering

Voice conversations operate under strict human psychological latency tolerances. Delays exceeding 1.5 seconds feel unnatural; delays exceeding 2.0 seconds cause awkward conversational collisions (user begins speaking again just as the bot answers).

### NFR-1.1: Turn Latency Budget Allocation

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                  TOTAL TURN LATENCY BUDGET: < 1,200 ms (P95)                 │
├─────────────────┬──────────────┬──────────────┬──────────────┬───────────────┤
│ VAD & Audio Cut │ Groq Whisper │ Guard + RAG  │ Groq LLM TTFT│ edge-tts TTFB │
│    150–200 ms   │  100–180 ms  │   3–10 ms    │  180–250 ms  │  180–250 ms   │
└─────────────────┴──────────────┴──────────────┴──────────────┴───────────────┘
```

| Pipeline Segment | Target (P50) | Upper Bound (P95) | Degradation Strategy |
| :--- | :--- | :--- | :--- |
| **Silence / VAD Trigger** | 180 ms | 220 ms | Dynamic noise-floor thresholding |
| **STT Transcription** | 120 ms | 190 ms | Fallback to Faster-Whisper or Web Speech |
| **Pre-Turn Guardrail** | **0.005 ms** | **0.5 ms** | In-memory compiled Aho-Corasick automaton |
| **Hybrid Knowledge RAG** | 3.5 ms | 10.0 ms | SQLite FTS5 index + In-memory vector cache |
| **LLM Time-to-First-Token** | 190 ms | 280 ms | Fallback to `llama-3.1-8b-instant` if 70B spikes |
| **Sentence Chunking** | 40 ms | 70 ms | Token buffer flushes on first punctuation |
| **TTS Audio Synthesis TTFB** | 180 ms | 260 ms | Streaming MP3 chunks over WebSocket |
| **Audio Jitter Buffer** | 30 ms | 50 ms | Adaptive jitter buffer in client audio node |
| **TOTAL TURN LATENCY** | **743.5 ms** | **1,070 ms** | **Comfortably under 1.2s target** |

### NFR-1.2: Emergency Halt Latency
- When an emergency red-flag utterance is received (*"seene mein dard"*), the emergency bypass response must begin audio playback within **< 300 ms** total, completely bypassing the LLM.

---

## 2. Safety, Precision & Clinical Verification

### NFR-2.1: Red-Flag Recall Guarantee
- **Invariant:** The emergency circuit breaker must achieve **100.0% recall** on acute cardiac, respiratory, stroke, and psychiatric emergency symptom keywords in English and Hinglish.
- **Verification:** Continuous mutation testing and synthetic defect injection must run against the emergency lexicon on every commit.

### NFR-2.2: False Verification Rate (FVR)
- The rate at which the system allows a hallucinated price, false channel capability (WhatsApp), or persona violation through to TTS must be **$< 0.5\%$**.
- Post-turn deterministic regex filters enforce hard blocks before text reaches the audio synthesis buffer.

### NFR-2.3: Zero-Regression Gate for Clinical Rules
- Clinicians must not be able to activate any rule that drops the regression pass rate below **98.0%** across the Golden Clinical Test Suite.

---

## 3. Data Privacy, Healthcare Compliance & Security

### NFR-3.1: Patient Health Information (PHI) Protection
- All patient identifiers (name, phone number, address) must be segregated from conversation training pipelines.
- **DISHA / HIPAA Compliance Alignment:** In accordance with India's Digital Information Security in Healthcare Act (DISHA) and the Digital Personal Data Protection Act (DPDPA 2023):
  - Patient transcripts must be stored encrypted at rest (AES-256).
  - No identifiable patient voice data or transcripts may be submitted to public model training queues.
  - Ephemeral in-memory turn contexts must be sanitized after call termination.

### NFR-3.2: Secret Management & Zero Hardcoding
- Zero API keys, database credentials, or secret tokens shall ever be committed to git repositories.
- All secrets are loaded through environment variables (`.env` with `.env.example` templates).
- Autonomous egress gates (Tier 1 AI Safety Guardrail) scrub credential leaks before data is written to disk or logs.

---

## 4. Scalability & Concurrent Call Capacity

### NFR-4.1: Concurrency Architecture
- The backend must be completely asynchronous (Python `asyncio` + FastAPI WebSockets).
- A single core instance (2 vCPU, 4GB RAM) must support at least **50 concurrent live audio streaming sessions** without audio degradation or dropped WebSocket frames.
- Read operations for clinical guidelines and patient diet charts must be non-blocking using SQLite Write-Ahead Logging (WAL) mode.

---

## 5. Zero-Cost Infrastructure & Resource Constraints

### NFR-5.1: Zero Dollar Operational Budget ($0.00/month)
- The complete development, testing, clinical simulation, and evaluation system must operate with zero out-of-pocket spend and zero credit-card requirements.
- Uses:
  - **Free LLM/STT:** Groq Cloud Developer Tier (free 30 RPM, 14.4k RPD, 2,000 Whisper calls/day).
  - **Free Speech Synthesis:** `edge-tts` (Microsoft Edge neural speech synthesis, 0 cost).
  - **Free Database:** Embedded SQLite (zero cloud hosting, zero maintenance).
  - **Free Embeddings:** FastEmbed running locally on CPU via ONNX Runtime.
  - **Free Hosting:** Localhost / Docker / Render free tier / Vercel for UI.

### NFR-5.2: Memory & Compute Footprint
- Local memory usage of the entire backend service (including embedded vector index and FastAPI runtime) must not exceed **800 MB RAM**, allowing smooth execution on low-cost VPS or developer laptops.

---

## 6. Maintainability & Clinical Autonomy

### NFR-6.1: Zero-Code Deployments for Clinicians
- Non-technical clinical team members must be able to add a new symptom remedy or update a dietary stance without opening a pull request, editing Python code, or redeploying Docker containers.
- All clinical changes take effect in live calls within **< 5 seconds** of passing the automated regression test gate.

### NFR-6.2: Auditability & Observability
- 100% of calls, turns, latencies, guardrail trigger events, and clinician edits must produce structured JSON log events with correlation IDs (`call_id`, `turn_id`, `patient_id`).
