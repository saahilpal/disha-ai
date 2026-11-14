# Disha AI

Disha AI is a real-time voice and text lifestyle coach for hypertension and type-2 diabetes management, grounded in verified clinical guidelines.

## Quickstart

### Prerequisites
- Python 3.12+
- Node.js 20+
- Docker & Docker Compose
- PostgreSQL 16 (with `pg_trgm`)

### Setup and Execution

1. Configure environment:
```bash
cp .env.example .env
```

2. Start database, backend, and proxy:
```bash
docker compose up -d postgres backend proxy
```

3. Ingest clinical datasets and apply schemas:
```bash
PYTHONPATH=. uv run python disha_core/db/apply_conversations_schema.py
PYTHONPATH=. uv run python disha_core/db/apply_journey_schema.py
PYTHONPATH=. uv run python disha_core/db/apply_pep_habits_schema.py
PYTHONPATH=. uv run python disha_core/db/ingest_open_datasets.py
PYTHONPATH=. uv run python disha_core/db/ingest_autonomous_datasets.py
```

4. Run test suite:
```bash
export TEST_DATABASE_URL="postgresql://disha:disha_secure_pass_123@127.0.0.1:5432/disha"
uv run pytest tests/
```

5. Access web interface:
Open `http://127.0.0.1:8080` in your browser.

## Core Invariants

1. Identity: Disha identifies as an AI lifestyle coach, never as a medical doctor or human clinician.
2. Prescriptions: Disha never prescribes medication or alters clinical dosages.
3. Pricing & Billing: Disha never quotes unverified subscription fees or payment plans.
4. Channel Boundaries: Disha operates strictly within the active session and never promises external delivery via WhatsApp, SMS, or phone calls.
5. Red-Flag Emergencies: Critical cardiac and acute symptoms trigger immediate emergency escalation protocols within 4 microseconds, prior to any ML inference.

## Architecture at a Glance

```text
[ Client (Web / WebSocket) ]
             |
             v
[ NGINX Proxy (Port 8080) ]
             |
             v
[ FastAPI Ingress (Port 8000) ]
             |
             +---> [ Emergency Breaker (Aho-Corasick) ] (Triggers 112 Protocol)
             |
             +---> [ Laya System 1 Classifier ] (Intent & Risk Scoring)
             |
             +---> [ Clinical Retriever ] (PostgreSQL FTS + Trigram)
             |
             +---> [ Dual Provider LLM ] (Gemini / Groq Streaming)
             |
             +---> [ SentenceValidator + Verifier ] (Output Sanitization & Repair)
             |
             v
[ Streaming Response (SSE / Audio via Edge-TTS) ]
```

## Tech Stack

| Component | Technology | Rationale |
|---|---|---|
| Ingress & Orchestration | FastAPI / Uvicorn | High-concurrency async Python runtime with low overhead |
| Reverse Proxy | NGINX 1.28 Alpine | Static asset delivery, rate limiting, and WebSocket proxying |
| Primary Database | PostgreSQL 16 Alpine | Relational integrity, full-text search (`tsvector`), and trigram fuzzy matching (`pg_trgm`) |
| Intent Classification | Laya / PyTorch | Sub-millisecond non-autoregressive clinical triage and risk scoring |
| LLM Gateway | Google Gemini & Groq | Dual-provider streaming LLM client with automatic failover circuit breaker |
| Speech-to-Text | Groq Whisper Large v3 | High-accuracy transcription for multilingual Indian Hinglish speech |
| Text-to-Speech | Microsoft Edge-TTS | Low-latency neural speech synthesis (`en-IN-NeerjaNeural`, `hi-IN-SwaraNeural`) |
| Client Interface | Vanilla JS / Tailwind CSS | Zero-dependency responsive client with streaming SSE and WebSocket audio handling |
