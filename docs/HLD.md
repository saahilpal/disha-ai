# High-Level Architecture (HLD)

Disha AI provides real-time conversational lifestyle coaching across text and voice channels for patients managing hypertension and type-2 diabetes. The platform grounds conversational responses in clinical guidelines from the Indian Council of Medical Research (ICMR) and the Ministry of Ayush.

## 1. System Context and Component Boundaries

The system separates deterministic clinical boundary enforcement from probabilistic natural language generation. Safety checks, intent routing, and patient profile retrieval execute before language model invocation. Post-generation validators inspect responses before transmission to the user.

```mermaid
flowchart TD
    subgraph ClientLayer ["Client Layer"]
        BrowserClient["Web Browser Client (Desktop / Mobile)"]
        VoiceClient["Voice WebSocket Client (Audio Ingress / Egress)"]
    end

    subgraph EdgeLayer ["Edge & Ingress Layer"]
        NginxProxy["NGINX Reverse Proxy (Port 8080)"]
    end

    subgraph CoreBackend ["FastAPI Core Application (Port 8000)"]
        ChatRouter["Chat Router (/chat, /chat/stream)"]
        VoiceRouter["Voice Router (/ws/conversation)"]
        EmergencyBreaker["Emergency Breaker (Aho-Corasick)"]
        ClassifierAdapter["Laya Classifier Adapter (Intent & Risk)"]
        ContextBuilder["Context Builder & Memory Rehydrator"]
        ClinicalRetriever["Clinical Retriever (FTS + Trigram)"]
        ResponseHarness["Response Harness & Repair Engine"]
        SentenceValidator["Sentence Validator (Streaming)"]
        ResponseVerifier["Response Verifier (Turn Level)"]
    end

    subgraph Persistence ["Persistence Layer"]
        PostgresDB[("PostgreSQL 16 (Port 5432)")]
    end

    subgraph ExternalServices ["External Model Providers"]
        GroqSTT["Groq Whisper Large v3 (STT)"]
        PrimaryLLM["Groq Primary LLM (openai/gpt-oss-120b)"]
        SecondaryLLM["Google Gemini Secondary LLM (gemini-3.6-flash)"]
        EdgeTTS["Microsoft Edge-TTS (Neural Audio)"]
    end

    BrowserClient -->|HTTP / SSE| NginxProxy
    VoiceClient -->|WebSocket| NginxProxy
    NginxProxy -->|HTTP / WS| ChatRouter
    NginxProxy -->|HTTP / WS| VoiceRouter

    ChatRouter --> EmergencyBreaker
    VoiceRouter --> EmergencyBreaker

    EmergencyBreaker -->|Safe Turn| ClassifierAdapter
    EmergencyBreaker -->|Red Flag Trigger| PostgresDB

    ClassifierAdapter --> ContextBuilder
    ContextBuilder --> ClinicalRetriever
    ClinicalRetriever --> PostgresDB
    ContextBuilder --> PostgresDB

    ContextBuilder --> ResponseHarness
    ResponseHarness --> PrimaryLLM
    PrimaryLLM -.->|Failover| SecondaryLLM
    ResponseHarness --> SentenceValidator
    SentenceValidator --> ResponseVerifier

    VoiceRouter --> GroqSTT
    ResponseHarness --> EdgeTTS
    ResponseVerifier --> PostgresDB
```

## 2. End-to-End Request Path

Both text chat and voice streams follow an identical deterministic spine. Emergency safety evaluation occurs at ingress prior to classification or retrieval.

```mermaid
sequenceDiagram
    autonumber
    actor User as Patient
    participant Edge as NGINX (8080)
    participant Core as FastAPI App (8000)
    participant Breaker as Emergency Breaker
    participant Classifier as Laya Classifier
    participant DB as PostgreSQL 16
    participant LLM as LLM Provider (Gemini / Groq)
    participant Guards as Validator & Verifier
    participant TTS as Edge-TTS Audio

    alt Voice Request
        User->>Edge: Stream Raw Audio Chunks (WebSocket)
        Edge->>Core: Forward Audio Packets
        Core->>Core: VAD & Groq Whisper STT Transcription
    else Chat Request
        User->>Edge: POST /chat/stream (Bearer Token)
        Edge->>Core: Forward JSON Payload
    end

    Core->>Breaker: Evaluate Raw Text against Red-Flag Dictionary
    alt Red-Flag Emergency Detected
        Breaker-->>Core: Emergency Triggered (Cardiac / Stroke / Dyspnea)
        Core->>DB: Log Emergency Event in Audit Ledger
        Core-->>User: Emit Immediate 112 Protocol Escalation Message
    else Non-Emergency
        Core->>Classifier: Classify Intent, PEP Risk, and Urgency
        Classifier->>Classifier: LRU Cache Lookup (2048 entries)
        Classifier-->>Core: Intent (meal_query, exercise_query, etc.)
        Core->>DB: Fetch Patient Profile & Clinical Guidelines (FTS/Trigram)
        DB-->>Core: Verified Knowledge Chunks & Allowed PEP Actions
        Core->>Core: Build XML Context Payload
        Core->>LLM: Stream Prompt with Context Bounds
        loop Streaming Generation
            LLM-->>Core: Token Chunks
            Core->>Guards: SentenceValidator Streaming Inspection
            Guards-->>Core: Validated Sentence
            opt Voice Channel
                Core->>TTS: Synthesize Sentence Audio
                TTS-->>User: Binary Audio Stream
            end
            Core-->>User: SSE Sentence Stream
        end
        Core->>Guards: verify_response(Full Response Text)
        opt Invariant Violation Detected
            Guards->>LLM: Execute repair_turn with Targeted Feedback
            LLM-->>Core: Repaired Response
        end
        Core->>DB: Commit Turn Journal & Cryptographic Ledger Entry
    end
```

## 3. Data Flow Architecture

The data flow separates administrative configuration, patient profile updates, clinical guideline indexing, and runtime telemetry.

```mermaid
flowchart LR
    subgraph DataIngestion ["Data Ingestion"]
        ICMR["ICMR-NIN 2024 Guidelines"]
        AYUSH["Ayurvedic Pharmacopoeia (API)"]
        WHO["WHO Clinical Protocols"]
        IngestScript["Ingest Scripts (ingest_open_datasets.py)"]
    end

    subgraph Storage ["PostgreSQL Storage"]
        CKB["clinical_knowledge_base (478 guidelines)"]
        KC["knowledge_chunks (482 provenance chunks)"]
        Profiles["patient_profiles & patient_pep"]
        Journal["patient_turn_journal"]
        Ledger["audit_claim_ledger (Tamper-evident)"]
    end

    subgraph RuntimeEngine ["Runtime Engine"]
        ContextEngine["Context Engine"]
        LLMClient["DualProviderClient"]
        AuditEngine["AuditLedger Worker"]
    end

    ICMR --> IngestScript
    AYUSH --> IngestScript
    WHO --> IngestScript
    IngestScript --> CKB
    IngestScript --> KC

    KC --> ContextEngine
    Profiles --> ContextEngine
    Journal --> ContextEngine

    ContextEngine --> LLMClient
    LLMClient --> AuditEngine
    AuditEngine --> Ledger
    AuditEngine --> Journal
```

## 4. Network Topology and Port Allocations

The service runs across three containers defined in `docker-compose.yml`:

| Port | Service | Protocol | Access Scope | Purpose |
|---|---|---|---|---|
| 8080 | proxy (NGINX) | HTTP / WebSocket | Public / Local Host | Reverse proxy, static web asset hosting, rate limiting, and SSL termination |
| 8000 | backend (FastAPI) | HTTP / WebSocket | Internal Container Network | Core application runtime and API router |
| 5432 | postgres (PostgreSQL 16) | PostgreSQL Wire | Local Host / Internal | Database storing knowledge chunks, patient profiles, turn journal, and audit ledger |

### External Network Dependencies

| Destination | Protocol | Purpose | Timeout | Failure Mode |
|---|---|---|---|---|
| `generativelanguage.googleapis.com` | HTTPS | Primary LLM generation (Google Gemini 1.5 Flash) | 10.0s | Fallback to Groq secondary model via circuit breaker |
| `api.groq.com` | HTTPS | STT transcription (Whisper) & Secondary LLM (Llama 3.3 70B) | 8.0s | Return deterministic offline error response |
| Microsoft Edge-TTS Service | WebSocket / WSS | Streaming speech audio synthesis | 5.0s | Silent fallback to client text display |

## 5. Free-Tier Cloud Deployment Architecture

The production-ready demo deploys across three complimentary free-tier cloud platforms:

```mermaid
flowchart TD
    subgraph ClientLayer ["Client Devices"]
        MobileClient["Mobile Browser (PWA)"]
        DesktopClient["Desktop Browser"]
    end

    subgraph VercelEdge ["Vercel Edge Network (Region: bom1 - Mumbai)"]
        StaticFrontend["Static Assets (HTML5, JS, CSS, Locales)"]
        WarmupHandler["Client Health & Warmup Poller"]
    end

    subgraph RenderCloud ["Render Cloud Web Service (Region: singapore)"]
        FastAPIApp["FastAPI Runtime (Python 3.12, 512MB RAM)"]
        WebSocketHandler["Stateful WebSocket Voice Handler (/voice)"]
        LayaClassifier["Laya Multilingual Classifier"]
        BreakerSpine["Emergency Breaker Spine"]
    end

    subgraph SupabaseDB ["Supabase Managed PostgreSQL 16"]
        SupavisorPooler["Supavisor IPv4 Transaction Pooler (Port 6543)"]
        ClinicalKnowledge[("Clinical Knowledge Tables (RLS Protected)")]
    end

    MobileClient -->|HTTPS / Static Assets| StaticFrontend
    DesktopClient -->|HTTPS / Static Assets| StaticFrontend
    WarmupHandler -->|HTTP /health Ping| FastAPIApp
    MobileClient -->|WSS /voice| WebSocketHandler
    DesktopClient -->|WSS /voice| WebSocketHandler
    FastAPIApp -->|AsyncPG statement_cache_size=0| SupavisorPooler
    SupavisorPooler --> ClinicalKnowledge
```

### Free-Tier Split & Boundary Rationale:
1. **Frontend on Vercel (`bom1` Mumbai)**: Delivers sub-30ms static asset delivery across India, zero cold start for UI, and clean HTTPS termination. Vercel Hobby tier is personal/non-commercial, ideal for this demo.
2. **Backend on Render (`singapore`)**: Provides stateful WebSocket support through its reverse proxy for bidirectional streaming voice. Handles 15-minute idle spindowns via client-side warmup banner (`#warmup-banner`) rather than illegal keep-alive pings.
3. **Database on Supabase**: Provides managed PostgreSQL 16 with full `pg_trgm` support. Accessed exclusively via IPv4 Supavisor Transaction Pooler (`aws-0-ap-southeast-1.pooler.supabase.com:6543`) with `statement_cache_size=0` to ensure compatibility with Render's IPv4 routing. Row-Level Security (RLS) is enabled on all tables to prevent public PostgREST exposure.
