<div align="center">

# 🌿 Disha AI (दिशा एआई)
### Production-Grade Deterministic Voice Health Coach for Rural & Semi-Urban India

[![CI Status](https://img.shields.io/badge/CI-Passing-059669?style=flat-square&logo=githubactions&logoColor=white)](.github/workflows/ci.yml)
[![Deterministic Judge Score](https://img.shields.io/badge/Judge%20Audit-100%2F100%20(Unconstrained)-10b981?style=flat-square&logo=speedtest&logoColor=white)](audit/reports/)
[![Laya AI Real Model](https://img.shields.io/badge/Laya%20Classifier-Real%20Weights%20(90.6%25)-6366f1?style=flat-square&logo=pytorch&logoColor=white)](docs/research/laya-brief.md)
[![Emergency Recall](https://img.shields.io/badge/Emergency%20Recall-100%25%20(112%20Triage)-ef4444?style=flat-square)](disha_core/pipeline/breaker.py)
[![Infrastructure Cost](https://img.shields.io/badge/Infrastructure%20Cost-%240%20%2F%20month-3b82f6?style=flat-square)](docker-compose.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square)](LICENSE)

**[Live Web App Deployment](https://disha-ai-gray.vercel.app)** • **[System Architecture](ARCHITECTURE.md)** • **[Engineering Manual](ENGINEERING.md)** • **[Security Ledger](docs/security/key-rotation.md)**

</div>

---

## 📖 Executive Summary

**Disha AI** is a conversational voice telephony engine designed to deliver personalized, culturally grounded lifestyle and metabolic health coaching across Hindi and Hinglish.

Unlike conventional conversational AI systems that rely on unconstrained Large Language Models, Disha AI operates on the doctrine of the **"Thick Deterministic Spine with a Thin Probabilistic Leaf"**:

> **"The intelligence is an untrusted, probabilistic leaf node. The system is a deterministic, authenticated, falsifiable state machine."**

Every clinical claim, dietary rule, exercise clearance constraint, and emergency red-flag is strictly enforced in compiled native code, local ONNX neural decision classifiers, and relational database constraints. The LLM functions purely as a presentation layer for warm, colloquial Hinglish dialogue synthesis within an immutable clinical envelope.

```
       +-------------------------------------------------------------+
       |             UNTRUSTED PROBABILISTIC LEAF (LLM)              |
       |      Groq Llama-3.3-70B-Versatile / Google Gemini Flash      |
       |  (Synthesizes empathetic Hinglish response; length-bounded) |
       +------------------------------+------------------------------+
                                      ^
        Structured Lean XML Envelope  |  Post-Generation Sentence Stream
        (<400 tokens, strict bounds)  |  (Intercepted at Egress Gate)
                                      v
=============================================================================
                  THICK DETERMINISTIC SPINE (100% Code)
=============================================================================
   Level 1: Pre-Turn Emergency Breaker (<0.05ms Aho-Corasick Automaton)
   Level 2: NandhaKishorM/laya Multi-Head Classifier (~33ms Local ONNX)
   Level 3: Closed-Domain Lexical Retrieval (<2.0ms pg_trgm in PostgreSQL)
   Level 4: Post-Turn SentenceValidator (<2.0ms AST / Regex Replacement Gate)
   Level 5: Hash-Chained Merkle Audit Ledger (SHA-256 Provenance in SQLite WAL)
=============================================================================
```

---

## ⚡ Key System Guarantees

- **Sub-Second Voice Turnaround:** Total internal processing budget `< 650ms` (Whisper STT ~225ms + Deterministic Spine ~35ms + LLM TTFT & Boundary Validation ~338ms). End-to-end round-trip audio delivery `< 1,100ms`.
- **Zero-Recurring Cloud Software Bill ($0/month):** Powered entirely by containerized PostgreSQL 16 (`pg_trgm`), Dockerized FastAPI, NGINX proxy, Edge-TTS, and developer-tier inference APIs.
- **100% Emergency Deflection:** Cardiovascular (crushing chest pain, radiation to left arm), respiratory, neurological (FAST stroke symptoms), and acute trauma phrases trigger sub-millisecond 112 emergency diversion without initiating LLM turns.
- **Closed-Domain Clinical Safety:** Mathematical False Verification Rate ($FVR < 0.001$, $p < 0.05$ over 2,703 test trials). Zero unauthorized diagnoses, zero prescription changes, zero ungrounded remedies.
- **Tamper-Evident Merkle Provenance:** Every conversational turn is cryptographically hash-chained (`SHA-256(prev_hash | patient_id | user_input | llm_output | status)`) with zero-data-loss SQLite WAL sidecars.

---

## 🚀 Quickstart in 3 Commands

### 1. System Doctor Check
Verify all required developer runtimes (Python 3.12, Node 20, Docker, Cloudflared, Gitleaks, UV):
```bash
git clone https://github.com/disha-ai/disha-ai.git
cd "disha ai"
make doctor
```

### 2. Launch Local Stack
Boot PostgreSQL 16 with preloaded clinical datasets, FastAPI Core backend, and NGINX edge proxy:
```bash
make dev
```
Once healthy, access the local system:
- **Clinical Telephony Web App:** `http://127.0.0.1:8080`
- **Healthcheck & Database Status:** `http://127.0.0.1:8080/health`
- **Direct FastAPI OpenAPI Docs:** `http://127.0.0.1:8000/docs`
- **WebSocket Voice Endpoint:** `ws://127.0.0.1:8080/ws/conversation`

### 3. Run Test & Audit Suites
```bash
make test    # 105+ pytest invariants + 32 frontend diagnostics
make audit   # Multi-dimensional judge score (/audit/judge.py)
make qa      # Playwright multi-viewport crawler + mechanical adversary
```

---

## 🌐 Production Edge Deployments

| Component | Target URL | Description |
|:---|:---|:---|
| **Production Web Client** | [https://disha-ai-gray.vercel.app](https://disha-ai-gray.vercel.app) | Single-page clinical telephony SPA with Web Audio 24-bar visualizer and real-time barge-in. |
| **Local NGINX Edge Proxy** | `http://127.0.0.1:8080` | Local production mirror with HTTP/WS reverse proxying, rate limiting, and gzip compression. |
| **Public Cloudflare Tunnel** | `make tunnel` | Instant public edge access (`https://*.trycloudflare.com`) supervised by `scripts/tunnel-watchdog.sh`. |

---

## ⚙️ Environment Variables Specification

Disha AI loads settings from `.env` (copy from `.env.example`). All keys are documented below:

| Variable Name | Default Value | Required | Purpose & Constraints |
|:---|:---|:---:|:---|
| `GROQ_API_KEY` | *(None)* | **Yes** | Groq Cloud API key for ultra-fast Llama-3.3-70B-Versatile streaming inference. |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | No | Model ID for primary generation. Fallbacks handled automatically. |
| `GEMINI_API_KEY` | *(None)* | **Yes** | Google Gemini API key used for secondary failover and semantic extraction. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | No | Secondary LLM fallback provider model ID. |
| `POSTGRES_USER` | `disha` | No | PostgreSQL database username. |
| `POSTGRES_PASSWORD` | `postgres` | No | PostgreSQL database password. Must be rotated in production. |
| `POSTGRES_DB` | `disha` | No | Primary database name containing clinical grounding corpus & PEP records. |
| `POSTGRES_HOST` | `postgres` (or `127.0.0.1`) | No | Hostname of PostgreSQL container or managed instance. |
| `POSTGRES_PORT` | `5432` | No | PostgreSQL connection port. |
| `EDGE_TTS_VOICE` | `hi-IN-SwaraNeural` | No | High-naturalness Hindi female neural voice profile for Edge-TTS. |
| `AUDIT_WAL_PATH` | `disha_core/audit_wal.db` | No | Filepath for append-only SQLite Write-Ahead Log sidecar. |
| `CLOUDFLARE_TUNNEL_TOKEN` | *(None)* | No | Optional token for named Cloudflare Tunnel in `make tunnel`. |

---

## 🛠️ Developer Make Targets

Disha AI provides standard one-command workflows via `Makefile`:

```bash
make help       # Print list of available targets and descriptions
make doctor     # Verify presence of python, node, docker, cloudflared, gitleaks, uv
make dev        # Start Postgres + FastAPI + NGINX proxy and poll health
make test       # Execute full pytest suite and Node.js diagnostic checks
make audit      # Execute the 16-constraint deterministic judge (python -m audit.judge)
make qa         # Run Playwright visual crawler (30 screenshots) and mechanical adversary
make tunnel     # Launch supervised Cloudflare edge tunnel watchdog
make lint       # Fast linting via ruff across disha_core, audit, and tests
make typecheck  # Static type analysis via mypy
make format     # Auto-format Python codebase with ruff
make clean      # Clean __pycache__, .pytest_cache, and test artifacts
make status     # Display Docker container status and proxy health
```

---

## 🛡️ The 16 Immutable System Invariants (C1–C16)

Disha AI enforces sixteen non-negotiable safety and architectural invariants verified on every build:

| ID | Invariant Name | Enforcement Layer | Behavior on Breach |
|:---|:---|:---|:---|
| **C1** | Pre-Turn Emergency Deflection | Aho-Corasick Automaton (<0.05ms) | Immediate deflection to 112 emergency message; LLM turn aborted. |
| **C2** | Zero Unsupported Diagnoses | Regex & AST SentenceValidator | Prohibits "Aapko [X] bimari hai"; rewrites to safe lifestyle disclaimer. |
| **C3** | Zero Prescription Changes | SentenceValidator Rule | Prohibits dose alteration ("dawai band/double karein"); rewrites to physician consult. |
| **C4** | Closed-Domain Meal Grounding | PostgreSQL `patient_pep` Slot Match | Ungrounded food queries outside active diet slot receive `MEAL_NOT_FOUND_REPLACEMENT`. |
| **C5** | PEP Mobility & Gym Boundary | Context Builder & Sentence Gate | Blocks unapproved strenuous exercise for Stage 2 HTN / post-MI patients. |
| **C6** | Mandatory Clinical Assertion | Egress Buffer Token Gate | Empathy responses missing clinician-approved home remedies (jeera/saunf) are rewritten. |
| **C7** | Channel Deflection Boundary | Egress Regex Validator | Deflects external channel requests ("WhatsApp par bhej do") to in-app "My Plan". |
| **C8** | Commercial Pricing Integrity | Currency Symbol & Digit Parser | Prohibits unauthorized charges; strictly asserts ₹0 or ₹1,499 authorized tier. |
| **C9** | Persona Invariant | Strict Identity Matcher | Prevents model from claiming human doctor status; asserts AI Health Coach identity. |
| **C10**| Cryptographic Audit Provenance | SHA-256 Merkle Ledger | Computes unbroken tamper-evident hash chain for 100% of dialog turns. |
| **C11**| Sub-35ms Core Overhead | Synchronous Benchmarking Harness | Total deterministic pipeline latency must remain under 35.0ms P95. |
| **C12**| Zero Stranded WAL Records | SQLite Atomic Transaction Manager | Database network partition recovers and flushes all uncommitted turns on restart. |
| **C13**| Fail-Closed LLM Circuit | Two-Failure Circuit Breaker | 2 consecutive timeouts switch traffic immediately to secondary LLM provider. |
| **C14**| Client Voice Barge-In | WebSocket Control Frame Handler | Client audio detection triggers immediate `stop_stream` frame and halts Edge-TTS. |
| **C15**| Zero Secret Leakage | Gitleaks Engine | Zero API tokens or private keys tolerated in commit history or build output. |
| **C16**| Real Laya AI Execution | NandhaKishorM/laya Adapter | Prevents mock stubs; requires real PyTorch/ONNX multi-head classification. |

---

## 📂 Repository Anatomy

```text
disha-ai/
├── Makefile                          # Unified developer workflow (doctor, dev, test, qa, audit, tunnel)
├── pyproject.toml                    # Ruff and Mypy configuration
├── README.md                         # Project documentation and quickstart
├── ARCHITECTURE.md                   # Architectural doctrine and dataflow specifications
├── ENGINEERING.md                    # Engineering standards, testing doctrine, and runbooks
├── docker-compose.yml                # Multi-container local stack (Postgres, Backend, NGINX)
├── docker-compose.prod.yml           # Production VM stack with persistent volumes
├── .github/
│   └── workflows/
│       └── ci.yml                    # Automated GitHub Actions CI (lint, typecheck, test, security, audit)
├── disha_core/                       # Core Deterministic Spine
│   ├── main.py                       # FastAPI application and WebSocket event loop
│   ├── pipeline/
│   │   ├── breaker.py                # Pre-Turn Emergency Aho-Corasick Automaton (<0.05ms)
│   │   ├── router.py                 # Intent router and language classifier
│   │   └── validator.py              # Post-turn SentenceValidator and Egress Gate
│   ├── classifier/
│   │   ├── adapter.py                # Real Laya AI (NandhaKishorM/laya) classifier adapter
│   │   ├── retrain_oracle.py         # Self-learning continuous improvement engine
│   │   └── review_queue.py           # Human-in-the-loop clinical review queue
│   ├── engine/
│   │   ├── context_builder.py        # Structured Lean XML prompt constructor (<400 tokens)
│   │   ├── normalizer.py             # Hinglish & Devanagari text canonicalization
│   │   └── retriever.py              # pg_trgm clinical database query engine
│   ├── compliance/
│   │   └── ledger.py                 # SHA-256 Merkle Audit Ledger and SQLite WAL sidecar
│   ├── db/
│   │   ├── schema.sql                # Relational schema (patients, PEP, clinical chunks, audit)
│   │   └── ingest_autonomous_datasets.py
│   └── frontend/                     # Canonical Web Client assets (HTML5, Vanilla ES6, CSS)
├── audit/                            # Deterministic Judge Evaluation Framework
│   ├── judge.py                      # Multi-dimensional evaluation harness with mutation testing
│   ├── suites/                       # Safety, latency, reliability, conformance, telemetry suites
│   └── reports/                      # Timestamped immutable JSON/Markdown audit scorecards
├── qa/                               # Playwright Automated QA Suite
│   ├── capture_redesign.js           # Multi-viewport (360-1440px) visual regression crawler
│   └── screenshots/                  # High-resolution UI captures
├── scripts/                          # Operational & Deployment Automation
│   ├── deploy-vm.sh                  # Bare-metal / Cloud VM provisioning script
│   └── tunnel-watchdog.sh            # Supervised Cloudflare ingress tunnel manager
└── tests/                            # Automated Testing Matrix
    ├── test_invariants.py            # 48 Core Invariant unit tests
    ├── test_clinical_safety_and_ledger.py # Adversarial safety & Merkle ledger tests
    ├── test_frontend_diagnostics.js  # 32 Web Audio and UI lifecycle diagnostic checks
    ├── test_laya_integration.py      # Real Laya weights evaluation & latency benchmark
    └── test_audit_security_and_edge_cases.py # SQL injection, auth, and boundary tests
```

---

## 🔒 Security & Key Rotation Policy

Disha AI maintains a **Zero-Secret Policy**:
- Version control history is continuously scanned via Gitleaks with zero permitted secret leaks.
- All secrets are injected dynamically via system environment variables.
- Compromised credentials are cataloged in [docs/security/key-rotation.md](docs/security/key-rotation.md) with step-by-step revocation procedures.
- ABHA identification numbers and phone numbers are scrubbed at the egress boundary before any network transmission.

---

## 📜 License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.
