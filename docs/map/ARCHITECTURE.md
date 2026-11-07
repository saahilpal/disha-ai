# Disha AI — System Architecture & Component Cartography

**Document Status:** Production Authoritative  
**Source Code Baseline:** `disha_core/` (Commit `458caf1` / `db200a7`)  
**Architecture Doctrine:** Thick Deterministic Spine vs. Untrusted Probabilistic Leaf (`senior-ai-systems-engineer`)

---

## 1. Executive Architectural Doctrine

In conventional conversational AI implementations, developers treat the Large Language Model (LLM) as the core system and wrap it in loose procedural scripts. **Disha AI inverts this model completely**:

> **"The intelligence is an untrusted, probabilistic leaf node. The system is a deterministic, authenticated, falsifiable state machine."**

Autoregressive language models hallucinate commercial pricing, attempt empathetic clinical counseling during acute medical crises, and fabricate dietary plans when database records are missing. In Disha AI, the model is strictly quarantined:
1. **The LLM Never Decides Clinical Triage:** Emergency detection is executed pre-LLM by compiled phrase automata (`EmergencyBreaker`) in `<0.05ms`.
2. **The LLM Never Accesses Raw State:** Context is pre-filtered, strictly bound by Physical Exertion Protocols (PEP) and 7-day diet schedules, and injected as escaped XML structures.
3. **The LLM Never Emits Raw Unvalidated Tokens:** Streamed tokens pass through a punctuation-boundary buffer (`SentenceBuffer`), a multi-rule validator (`SentenceValidator`), and a pronunciation sanitizer before hitting Text-to-Speech (TTS).
4. **The LLM Never Certifies Correctness:** All claims, breaker trips, and validator rewrites are cryptographically grounded into a SHA-256 Merkle audit chain (`AuditLedger`).

---

## 2. Component Topology Diagram

```mermaid
graph TD
    subgraph Web_Client_Tier ["Tier 0: Browser Web Application (Chrome / Safari / Firefox / Edge)"]
        BrowserUI["Single Page Web App (HTML5 / Vanilla CSS / ES6 JS)<br/>Acoustic Stethoscope Canvas, Screen Wake Lock API"]
        WebAudio["Web Audio API Engine<br/>- getUserMedia Microphone Stream<br/>- AnalyserNode Real-Time VAD (Energy &gt; 20)<br/>- AudioBufferSourceNode MP3 Playback Queue"]
        BrowserWS["Browser WebSocket Client<br/>(WSS Full-Duplex Voice &amp; JSON Framing)"]
        BrowserUI --- WebAudio
        WebAudio --- BrowserWS
    end

    subgraph Edge_and_Ingress ["Tier 1: Cloudflare Edge &amp; Ingress Proxy"]
        Cloudflare["Cloudflare Edge / Tunnel<br/>- Global TLS 1.3 Termination<br/>- DDoS Mitigation &amp; WAF<br/>- Public Endpoint Routing"]
        NGINX["NGINX Reverse Proxy (1.28-alpine)<br/>- Ports 80/443 &amp; 8080<br/>- WebSocket Upgrade (Connection: Upgrade)<br/>- Streaming Buffering Disabled (X-Accel-Buffering: no)<br/>- 10 MB Payload Quota Enforced"]
        Cloudflare -->|TLS 1.3 Encrypted Tunnel| NGINX
    end

    subgraph Deterministic_Spine ["The Thick Deterministic Spine (Python 3.12 / FastAPI / asyncpg)"]
        Router["FastAPI Application Core<br/>(disha_core/main.py)"]
        
        subgraph Pre_Execution_Guards ["Pre-Execution Safety &amp; Routing"]
            Breaker["EmergencyBreaker<br/>(Aho-Corasick + Regex Automaton)<br/>&lt;0.05ms Latency"]
            LayaAdapter["LayaClassifierAdapter<br/>(System 1 Non-Autoregressive)<br/>Confidence Gate: 0.40"]
            RuleClassifier["RuleIntentClassifier<br/>(Deterministic Fallback)"]
        end

        subgraph Grounding_Engine ["Retrieval &amp; Context Assembler"]
            Normalizer["Lexical Normalizer<br/>(NFKC + Clinical Tag Aliases)"]
            Retriever["Lexical Trigram Retriever<br/>(pg_trgm + tsvector GIN)<br/>Compound Cache (patient_id, query_hash)"]
            ContextBuilder["Context XML Serializer<br/>(PEP Permissions + Diet Slot)"]
        end

        subgraph Post_Execution_Guards ["Post-Generation Boundary Verification"]
            SentenceBuf["SentenceBuffer<br/>(Punctuation Boundaries &amp; Decimal Guard)"]
            Validator["SentenceValidator<br/>(Pricing, Identity, Prescription, Sodium, PEP)"]
            TTSSanitizer["TTS Pronunciation Sanitizer<br/>(Strip Markdown, Unicode Emojis)"]
        end

        subgraph Audit_Subsystem ["Cryptographic Audit Subsystem"]
            LocalWAL["SQLite WAL Buffer<br/>(audit_wal.db - Zero Data Loss)"]
            MerkleWorker["AuditLedger Worker<br/>(FOR UPDATE Chain Serializer)"]
        end
    end

    subgraph Data_Storage_Tier ["Isolated Data Storage Tier"]
        Postgres[("PostgreSQL 16 Database<br/>- clinical_knowledge_base<br/>- patient_profiles<br/>- patient_pep<br/>- patient_diet_schedules<br/>- patient_access_tokens<br/>- audit_claim_ledger<br/>- audit_chain_head")]
    end

    subgraph Untrusted_Probabilistic_Leaves ["Untrusted Probabilistic Leaves (External Egress)"]
        DualLLM["DualProviderClient<br/>Circuit Breaker (thresh=2, cool=30s)"]
        GroqLLM["Primary: Groq API<br/>(openai/gpt-oss-120b)<br/>temp: 0.2, max_tokens: 256"]
        GeminiLLM["Fallback: Google Gemini<br/>(gemini-3.6-flash)<br/>temp: 0.2, max_tokens: 256"]
        GroqSTT["Voice ASR: Groq Whisper<br/>(whisper-large-v3-turbo)"]
        EdgeTTS["Voice TTS: Microsoft Edge-TTS<br/>(hi-IN-SwaraNeural / en-IN-NeerjaNeural)"]
        LayaServe["Laya Server / Agent<br/>(convaiinnovations/laya 421M)"]
    end

    %% Web Client to Ingress
    BrowserWS -->|WSS / HTTPS (TLS 1.3)| Cloudflare
    NGINX -->|Reverse Proxy :8000| Router

    %% Voice & Turn Orchestration
    Router -->|1. Binary Audio Chunk| GroqSTT
    GroqSTT -->|Transcript| Router
    Router -->|2. Input String| Breaker
    
    %% Pre-turn Safety Trip
    Breaker -->|Triggered Emergency| Router
    Breaker -->|Clear| LayaAdapter
    LayaAdapter -.->|HTTP / In-Process| LayaServe
    LayaAdapter -->|Open Breaker / Error| RuleClassifier
    
    %% Context & Retrieval
    LayaAdapter -->|Intent + PEP Risk| Normalizer
    Normalizer --> Retriever
    Retriever -->|pg_trgm Query| Postgres
    Postgres -->|Clinical Chunks| Retriever
    Retriever --> ContextBuilder
    ContextBuilder -->|Lean Escaped XML| DualLLM

    %% LLM Dispatch
    DualLLM --> GroqLLM
    DualLLM -.->|Failover on 429/5xx| GeminiLLM
    GroqLLM -->|Streamed Chunks| SentenceBuf
    GeminiLLM -->|Streamed Chunks| SentenceBuf

    %% Validation & TTS
    SentenceBuf -->|Complete Sentence| Validator
    Validator -->|Validated / Rewritten| TTSSanitizer
    TTSSanitizer -->|Plain Text| EdgeTTS
    EdgeTTS -->|Audio Packets| Router
    Router -->|WSS Binary Frames| BrowserWS

    %% Audit Pipeline
    Router -->|Audit Record| LocalWAL
    LocalWAL --> MerkleWorker
    MerkleWorker -->|SHA-256 Merkle Chain| Postgres
```
```

---

## 3. Trust Boundaries & Web Application Architecture Fidelity

Disha AI enforces a strictly web-native architecture. **There are zero native operating system binaries (no iOS Swift app, no Android Kotlin/Java app, no desktop Electron bundle).** The client is 100% standard web technologies (HTML5, Vanilla CSS design tokens, ES6 JavaScript) executing within modern browser sandboxes across Desktop and Mobile devices.

The system implements a six-tier trust isolation model:

```
[ Tier 0: Web Application Client (Browser Sandbox) ]
  - HTML5 / CSS3 / ES6 Modular SPA (`frontend/app.js`)
  - Web Audio API (AudioContext, AnalyserNode, AudioBufferSourceNode)
  - Screen Wake Lock API (`navigator.wakeLock`)
  - Standard Browser WebSocket API (`new WebSocket()`)
  - Cookie-less Bearer Token Auth via Headers / Query / Handshake
       │  (Encrypted WSS / HTTPS over Web PKI)
═══════╪══════════════════════════════════════════════════════════════════════ [ Boundary 1: Transport & Auth ]
[ Tier 1: Cloudflare Edge & Ingress Proxy (NGINX) ]
  - Cloudflare Edge / Tunnel: TLS 1.3 Termination, DDoS Mitigation, WAF
  - NGINX Proxy (1.28-alpine): WebSocket Upgrade, 10 MB Payload Quota
  - Streaming Buffering Disabled (`proxy_buffering off; X-Accel-Buffering no;`)
       │  (Internal Container Bridge: `disha_network` / `disha_internal`)
═══════╪══════════════════════════════════════════════════════════════════════ [ Boundary 2: Process Boundary ]
[ Tier 2: The Deterministic Spine (FastAPI Monolith) ]
  - Token Hash Verification against `patient_access_tokens`
  - Emergency Breaker (<0.05ms Aho-Corasick Automaton)
  - Sentence Validator & Stream Gatekeeper
       ├───────────────────────────────────────────────┐
       │ (SQL via asyncpg Connection Pool)             │ (Egress with Gate Flags)
═══════╪═══════════════════════════════════════   ══════╪════════════════════ [ Boundary 3 & 4 ]
[ Tier 3: Isolated Database (PostgreSQL 16) ]   [ Tier 4: Egress Gateways ]
  - Row-Level FOR UPDATE Merkle Lock              - Fail-closed Consent Checks
  - Word Count Check (<50 words)                  - Non-PHI Classification
                                                  │
                                          ════════╪════════════════════════════ [ Boundary 5 ]
                                          [ Tier 5: Untrusted AI Providers ]
                                            - Groq (US Cloud)
                                            - Google Cloud Gemini
                                            - Microsoft Edge Speech
```

### Trust Boundary Invariants:
1. **Boundary 1 (Browser Client to Cloudflare / Ingress):** Client executes strictly in browser sandboxes. Microphone capture requires user gesture and Secure Context (HTTPS/localhost) enforced by the browser. Cloudflare terminates TLS 1.3, forwarding traffic through a secure tunnel or NGINX reverse proxy. NGINX enforces `client_max_body_size 10m` to prevent voice buffer exhaustion attacks.
2. **Boundary 2 (Ingress to Spine):** Every WebSocket and HTTP API call requires a 64-character SHA-256 token hash verified against `patient_access_tokens`. Bearer tokens are never logged in plaintext.
3. **Boundary 3 (Spine to Storage):** Database access is parameterized via `asyncpg`. No dynamic SQL generation occurs. Trigram similarity thresholds are locally scoped within transactions (`set_config('pg_trgm.similarity_threshold', ...)`).
4. **Boundary 4 (Spine to Egress Gateways):** Outbound provider calls (Groq, Gemini, Edge-TTS) are gated by fail-closed environment variables (`*_HEALTH_DATA_AUTHORIZED`, `*_HEALTH_DATA_PROCESSING_APPROVED`). If false, egress is blocked with `VoicePrivacyError` or `ProviderError`.
5. **Boundary 5 (Spine to Probabilistic Leaves):** Model output is treated as hostile input. It is never emitted directly to the patient. It must be chunked into sentences, stripped of Markdown and emojis, checked against clinical constraints, and rewritten if rules are violated.

---

## 4. Component Inventory & Responsibilities

| Component Name | Source File | Responsibility | Determinism Level | SLA / Latency Target |
|---|---|---|---|---|
| **EmergencyBreaker** | `disha_core/pipeline/breaker.py` | Detects acute life-threatening phrases (cardiac, respiratory, neuro, crisis, trauma). | 100% Deterministic (Aho-Corasick + Regex) | `<0.05ms` |
| **LayaClassifierAdapter** | `disha_core/classifier/adapter.py` | System 1 triage, intent routing, and Physical Exertion Protocol (PEP) risk scoring. | Probabilistic ML with Deterministic Circuit Breaker | `~35ms` (container) / `~98ms` (in-process) |
| **SentenceValidator** | `disha_core/pipeline/validator.py` | Post-generation assertion gate: rewrites pricing hallucinations, clinical claims, prescription tampering, and sodium violations. | 100% Deterministic Rule Engine | `<2.0ms` |
| **SentenceBuffer** | `disha_core/llm/sentence_buffer.py` | Accumulates streaming LLM tokens into grammatically sound sentences; handles decimal numbers (`1.5 mg`). | 100% Deterministic State Machine | `<0.1ms` |
| **Lexical Retriever** | `disha_core/engine/retriever.py` | Queries institutional clinical guidelines via `pg_trgm` and `tsvector` full-text search. | 100% Deterministic SQL / Trigram | `<2.5ms` |
| **Context Builder** | `disha_core/engine/context_builder.py` | Builds sanitized XML payloads with patient dietary and PEP permissions. | 100% Deterministic XML Serializer | `<0.5ms` |
| **DualProviderClient** | `disha_core/llm/client.py` | Manages primary (Groq) and fallback (Gemini) LLM streaming with consecutive failure circuit breaker. | Probabilistic Leaf Node | `<1200ms` First Token Timeout |
| **VoiceSession** | `disha_core/voice.py` | Manages duplex voice streaming, barge-in task cancellation, and Edge-TTS audio chunk emission. | 100% Deterministic Async Task Controller | `<15ms` Interruption Latency |
| **AuditLedger** | `disha_core/compliance/ledger.py` | Non-blocking audit queue backed by SQLite WAL with PostgreSQL SHA-256 Merkle chain writer. | 100% Deterministic Cryptographic Chain | `<5.0ms` DB Persistence |

---

## 5. Architectural Invariants Enforced in Code

1. **Finite Bounded State Machine:** Turn execution is guaranteed to terminate. Streaming loops enforce a hard limit of `3` emitted sentences (`sentence_buffer.py:79-81`).
2. **Double-Safety Gate for Emergencies:** Emergency phrases are caught **before** the LLM is invoked (`router.py:108` and `main.py:501`). An emergency response is returned in `<1ms`, short-circuiting the entire pipeline.
3. **Fail-Safe Fallback:** If the primary LLM fails 2 consecutive times, `ConsecutiveFailureCircuitBreaker` trips, automatically routing turns to Gemini Flash for a 30-second cooldown period (`client.py:165-202`).
4. **Zero Unpersisted Audit Data:** In the event of a sudden container shutdown or `SIGTERM`, an `atexit` hook and signal handler flush all queued turns to the local SQLite WAL (`ledger.py:99-115`).
5. **Multi-Tenant Cache Partitioning:** The retrieval cache in `retriever.py` keys on `(patient_id, query_hash)` to prevent cross-patient clinical data leakage.
