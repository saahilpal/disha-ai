# Disha AI

Disha AI is a real-time, full-duplex conversational voice and text lifestyle health coach designed for patients managing hypertension and type-2 diabetes across India. It grounds everyday diet, physical activity, and habit modification advice in verified clinical guidelines from the Indian Council of Medical Research (ICMR), National Institute of Nutrition (NIN), and the Ministry of Ayush.

---

## Documentation Map

- [High-Level Architecture (HLD)](docs/HLD.md) — System context, end-to-end request flows, and deployment topology.
- [Low-Level Design (LLD)](docs/LLD.md) — Class hierarchies, turn context contracts, response harness, and verification pipelines.
- [Clinical & Knowledge Data Reference (DATA)](docs/DATA.md) — Schema definitions, clinical guideline chunk provenance, and ingestion pipelines.
- [System Evaluation & Verification (EVALUATION)](docs/EVALUATION.md) — Automated test suites, benchmark methodologies, latency profiles, and safety guarantees.
- [Known Issues & Technical Debt (KNOWN_ISSUES)](docs/KNOWN_ISSUES.md) — Documented architectural defects, migration notes, and tracking.

---

## Core System Architecture & Features

```mermaid
flowchart TD
    subgraph Client ["Client Interface"]
        WebUI["Web Interface (Tailwind CSS / Vanilla JS)"]
        VoiceWS["Full-Duplex Audio (WebSocket / VAD)"]
    end

    subgraph Edge ["Edge & Reverse Proxy"]
        Nginx["NGINX 1.28 Alpine (Port 8080)"]
    end

    subgraph Core ["FastAPI Application (Port 8000)"]
        Router["Chat & Voice Ingress"]
        Breaker["Emergency Breaker (Aho-Corasick)"]
        Classifier["Laya Intent Classifier & Risk Gating"]
        Context["Context Builder & Patient Rehydrator"]
        Retriever["Clinical Retriever (pg_trgm + tsvector)"]
        Harness["Response Harness (PERCEIVE-PLAN-GEN-VERIFY-REPAIR-COMMIT)"]
        DualLLM["Dual Provider Client (Groq Primary / Gemini Failover)"]
        Validator["SentenceValidator & Verifier Guardrails"]
    end

    subgraph Storage ["Persistence Layer"]
        Postgres[("PostgreSQL 16 (Relational & Clinical RAG)")]
        Ledger[("Merkle Audit Ledger (Zero-PHI)")]
    end

    Client -->|HTTP / WS| Nginx
    Nginx --> Router
    Router --> Breaker
    Breaker -->|Red Flag 112 Protocol| Ledger
    Breaker -->|Safe Turn| Classifier
    Classifier --> Context
    Context --> Retriever
    Retriever <--> Postgres
    Context <--> Postgres
    Context --> Harness
    Harness <--> DualLLM
    Harness --> Validator
    Validator --> Ledger
    Validator -->|Validated Stream| Client
```

### 1. Deterministic Emergency Breaker (<10µs Latency)
- **Zero-ML Dependency**: Uses compiled Aho-Corasick string matching against clinician-curated red-flag symptoms in `data/red_flags.yaml`.
- **Immediate Triage**: Intercepts acute myocardial infarction, stroke (FAST criteria), acute dyspnea, and hypertensive crises before any LLM inference or classifier call.
- **Clinician Negation Awareness**: Distinguishes true crises from negated assertions (e.g., handles *"no chest pain"* or *"seene mein dard nahi hai"* without false alarms).
- Emits immediate emergency escalation advice directing the user to dial 112 or visit an emergency room.

### 2. Intent Routing & Triage
- **Laya Classifier**: Sub-millisecond intent classification categorizing turns into symptoms, diet, physical activity, habit logging, or out-of-scope interactions.
- **PEP Risk Scoring**: Flags high-risk requests (e.g., queries attempting medication alterations or dosage advice) and triggers strict constraint gating.
- **Circuit Breaker Fallback**: In-process regex and keyword heuristics ensure graceful continuity if the classifier service is unavailable.

### 3. Evidence-Grounded Clinical RAG
- **Curated Knowledge Chunks**: 478 approved/draft clinical guideline chunks in `clinical_knowledge_base` and 482 structured domain reference chunks in `knowledge_chunks` (960 total across both tables) ingested from ICMR-NIN Dietary Guidelines, WHO Hypertension Protocols, and Ministry of Ayush lifestyle advisories.
- **Hybrid Retrieval**: Combines PostgreSQL Full-Text Search (`tsvector`) with trigram fuzzy matching (`pg_trgm`) over condition and dietary tags.
- **Strict Anti-Hallucination**: Queries without clinical guideline matches default to conservative lifestyle boundaries and refuse ungrounded clinical claims.

### 4. Longitudinal Patient Empowerment Plan (PEP)
- **Multi-Session Continuity**: Rehydrates patient profile, biometric history (BMI, blood pressure targets), dietary restrictions (vegetarian, low-sodium), and physical limitations.
- **Separation of Medical & User State**: Clinician-prescribed PEP goals remain immutable; lifestyle disclosures (e.g., *"I walked 20 minutes"*, *"had khichdi for dinner"*) are recorded with explicit `user_reported` provenance.

### 5. Response Harness & Turn Lifecycle
Executes a unified 6-stage turn lifecycle:
1. **PERCEIVE**: Assesses user intent, conversational boundary controls (closing vs. acknowledgment), and language mode.
2. **PLAN**: Synthesizes a structured turn plan enforcing domain constraints and coaching goals.
3. **GENERATE**: Streams candidate tokens via the dual-provider LLM client.
4. **VERIFY**: Evaluates output against behavioral policies (max 1 question per turn, no unverified pricing, no doctor impersonation).
5. **REPAIR**: Automatically prompts the model to self-correct boundary violations before emission.
6. **COMMIT**: Writes audited turn exchanges to the patient journal.

### 6. Streaming Safety Guardrails
- **SentenceValidator**: Real-time streaming sanitizer that redacts accidental prescription terms, unapproved dosage changes, doctor impersonations, or contact delivery promises (WhatsApp/SMS).
- **ResponseVerifier**: Turn-level verification engine that checks for question spam, repetitive phrasing, and selective empathetic alignment.

### 7. Full-Duplex Voice Engine
- **Voice Activity Detection (VAD)**: Browser-side audio engine tuned to human speech frequency bands (80Hz–2500Hz) with natural barge-in interruption.
- **Optimized Silence Sampling**: RMS silence detection processes audio in <0.05ms to prevent audio pipeline bottlenecks.
- **Multilingual Speech**: High-accuracy speech-to-text via Groq Whisper Large v3; natural neural voice synthesis via Microsoft Edge-TTS (`hi-IN-SwaraNeural`, `en-IN-NeerjaNeural`).

### 8. Zero-PHI Compliance & Cryptographic Audit Ledger
- **DPDP Act Section 8 Compliance**: Automatic redaction of Indian phone numbers, Aadhaar IDs, ABHA numbers, passwords, and bearer tokens before storage.
- **Tamper-Evident Merkle Chain**: Every turn transition computes a cryptographic SHA-256 hash linked to the previous turn in `audit_claim_ledger`.

### 9. Dual-Provider LLM Gateway
- Primary provider: Groq (`openai/gpt-oss-120b` or configured `qwen/qwen3.8-27b`).
- Secondary provider: Google Gemini (`gemini-3.6-flash` or configured `gemini-3.1-flash-lite`) as instant failover.
- Equipped with `ConsecutiveFailureCircuitBreaker` with automatic cooldown to guarantee 99.9% availability.

---

## Core Invariants

1. **Identity**: Disha identifies as an AI lifestyle coach, never as a medical doctor or human clinician.
2. **Prescriptions**: Disha never prescribes medications or alters clinical dosages.
3. **Pricing & Billing**: Disha never quotes unverified subscription fees or payment plans.
4. **Channel Boundaries**: Disha operates strictly within the active session and never promises external delivery via WhatsApp, SMS, or phone calls.
5. **Red-Flag Emergencies**: Critical cardiac and acute symptoms trigger immediate emergency escalation protocols within 10 microseconds, prior to any ML inference.

---

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

---

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
