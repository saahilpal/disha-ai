# High-Level Design (HLD) — Disha AI System Architecture

## 1. The Core Architectural Philosophy
Disha AI enforces the **"Thick Deterministic Spine with a Thin Probabilistic Leaf"**.

```
             +-----------------------------------------------+
             |        UNTRUSTED PROBABILISTIC LEAF           |
             |      Groq Llama-3.3-70B / Gemini Flash        |
             | (Empathetic Hinglish Generation, Turn Length) |
             +-----------------------+-----------------------+
                                     ^
                                     | Structured Lean XML Payload (<400 tokens)
=====================================|=========================================
                                     v Guarded Execution Boundary
             +-----------------------------------------------+
             |          THICK DETERMINISTIC SPINE            |
             |               (100% Code & Rules)             |
             |  Pre-Turn Breaker      | Laya AI Decision     |
             |  (<0.05ms Aho-Corasick)| (~33ms Local ONNX)   |
             |  ----------------------+--------------------- |
             |  pg_trgm Lexical Match | Boundary Validator   |
             |  (<2.0ms PostgreSQL)   | (<2.0ms Assertion)   |
             +-----------------------------------------------+
```

* **The Problem:** Autoregressive LLMs hallucinate pricing, attempt conversational sympathy during acute medical crises, and fabricate meal items when data is missing.
* **The Solution:** The LLM is never trusted with clinical triage, commercial pricing, identity declarations, or data presence. Every input passes through pre-turn deterministic circuit breakers, and all generated tokens pass through post-generation assertion gates before reaching text-to-speech.

---

## 2. System Topology & Infrastructure ($0 Stack)

```
[ Patient Voice Client / Browser ]
│
│ TLS / WebSockets (Audio Chunk Streaming)
▼
┌─────────────────────────────────────────────────────────────┐
│ INGRESS LAYER: NGINX Container (Port 8080 -> 80)           │
│ - SSL Termination & CORS Enforcement                        │
│ - Connection Persistence & WebSocket Protocol Upgrades      │
└──────────────────────────────┬──────────────────────────────┘
│ Docker Bridge
▼
┌─────────────────────────────────────────────────────────────┐
│ BACKEND ORCHESTRATOR: FastAPI Monolith (Container: 8000)    │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ 1. Voice Ingestion: Groq Whisper Large v3 Turbo     │   │
│   └──────────────────────────┬──────────────────────────┘   │
│                              │ Transcribed Text             │
│                              ▼                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ 2. Pre-Turn Safety Breaker (Aho-Corasick: <0.05ms)  │   │
│   └──────────┬──────────────────────────────────────────┘   │
│              │ (Non-Emergency)                              │
│              ▼                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ 3. Canonical Normalizer (In-Memory Hinglish Map)    │   │
│   └──────────┬──────────────────────────────────────────┘   │
│              │ Normalized Tag                               │
│              ▼                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ 4. Laya AI Intent & Triage Classifier (~33ms ONNX)  │   │
│   └──────────┬──────────────────────────────────────────┘   │
│              │ Intent Classification                        │
│              ▼                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ 5. Context Builder & pg_trgm Hybrid RAG (<2ms)      │   │
│   └──────────┬──────────────────────────────────────────┘   │
│              │ Lean XML Grounding Payload                   │
│              ▼                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ 6. Dual Inference Core (Groq 70B / Gemini Failover) │   │
│   └──────────┬──────────────────────────────────────────┘   │
│              │ Token Stream                                 │
│              ▼                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ 7. Atomic Sentence Buffer & Assertion Validator     │   │
│   └──────────┬──────────────────────────────────────────┘   │
│              │ Validated Sentence Text                      │
│              ▼                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ 8. Audio Egress: Microsoft Edge-TTS Stream          │   │
│   └──────────────────────────┬──────────────────────────┘   │
│                              │ Audio Bytes Out              │
└──────────────────────────────┼──────────────────────────────┘
│
├─► Asynchronous asyncio.Queue
▼
┌─────────────────────────────────────────────────────────────┐
│ AUDIT & STORAGE LAYER: PostgreSQL 16 (Local Volume)         │
│ - Extension: pg_trgm (Trigram text indexing)                │
│ - Knowledge Base: 112 Clinician Micro-Chunks (<50 words)    │
│ - Multi-Tenant Schemas: patient_pep, patient_diet_schedules │
│ - Cryptographic Non-Repudiation: audit_claim_ledger         │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. End-to-End Latency Budget

Voice interactivity requires total turnaround under 1,100ms.

| Stage | Subsystem / Model | SLA / Target | Observed Production Runtime |
|:---|:---|:---:|:---:|
| **1. Speech-to-Text** | Groq Whisper Large v3 Turbo | `< 300ms` | **~225ms** |
| **2. Emergency Breaker** | Compiled Aho-Corasick Automaton | `< 0.05ms` | **~0.01ms** |
| **3. Canonical Normalizer**| In-memory dictionary regex | `< 0.10ms` | **~0.02ms** |
| **4. Fast Triage Router** | Laya AI Non-Autoregressive ONNX | `< 35ms` | **~33ms** |
| **5. Database Retrieval** | PostgreSQL `pg_trgm` GIN Index | `< 2.0ms` | **~1.36ms** |
| **6. LLM TTFT** | Groq `llama-3.3-70b-versatile` | `< 300ms` | **~260ms** |
| **7. Sentence Validator** | Regex & Token Assertion Gates | `< 2.0ms` | **~0.04ms** |
| **SUBTOTAL (Engine)** | **Internal Engine Turnaround** | **`< 650ms`** | **~563ms** |
| **8. Audio Synthesis** | Microsoft Edge-TTS (`hi-IN-SwaraNeural`)| `< 450ms` (WAN) | **~350–450ms** |
| **TOTAL MOUTH-TO-EAR** | **End-to-End Voice Turnaround** | **`< 1,100ms`** | **~913–1,013ms** |

---

## 4. The 7 Core Production Failure Modes & Architectural Resolutions

| # | Production Failure Mode | Root Vulnerability | Architectural Subsystem Owner | Concrete Resolution Mechanism |
|---|---|---|---|---|
| **1** | **Missed Red-Flag Emergency** | LLM attempts conversational empathy during acute crisis | `pipeline/breaker.py` (Aho-Corasick Automaton) | Evaluates raw input in `<0.05ms`. Matches cardio, respiratory, neuro, and trauma patterns; halts execution, bypasses LLM, and emits hardcoded 112 emergency script. |
| **2** | **Ignored PEP Context** | LLM defaults to generic advice, ignoring clinical exercise clearance | `engine/context_builder.py` (PEP Resolver) | Queries `patient_pep`; injects active permissions (`gym_clearance: true`) as negative prompt bounds; validator blocks conflicting advice. |
| **3** | **Ignored System Data** | LLM fabricates recipes when DB record is unassigned | `engine/context_builder.py` + `validator.py` | Parameterized query injects `<DIET_SLOT status="NOT_FOUND"/>`. Post-turn validator blocks all recipe generation when status is `NOT_FOUND`. |
| **4** | **Clinical Stance Contradiction** | Generic LLM biases (e.g., banning fruit sugar in weight loss) | `engine/retriever.py` (`pg_trgm` Retrieval) | Exact trigram match injects institutional micro-chunk (e.g., *Mango: seasonal moderation up to 100g/day*) directly into context, overriding generic model pretraining. |
| **5** | **Missed Clinical Remedy** | LLM gives generic conversational comfort instead of protocol remedy | `pipeline/validator.py` (Token Assertion) | Detects clinical condition (e.g., *period bloating*); asserts that doctor-approved remedy tokens (e.g., *jeera*, *saunf*, *warm water*) exist in output before dispatch. |
| **6** | **False Capability Promise** | LLM promises delivery over unsupported channels (WhatsApp/SMS) | `pipeline/validator.py` (Channel Regex Gate) | Scans for external channel keywords (`whatsapp`, `sms`, `email`). Rewrites response to point users strictly to the in-app **'My Plan'** tab. |
| **7** | **Persona Violation** | LLM claims to be a human doctor or clinician | `pipeline/validator.py` (Identity Assertion) | Prompt invariant mandates *"I am Disha, an AI health coach"*. Validator blocks first-person medical authority claims ("I am your doctor"). |

