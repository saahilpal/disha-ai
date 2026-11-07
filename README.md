# Disha AI — Deterministic Voice-Enabled Clinical Health Coach

Disha AI is a production-grade, zero-recurring-cost ($0/month) conversational health coaching engine designed for voice telephony and real-time interactive health management. It operates on the architectural doctrine of the **"Thick Deterministic Spine with a Thin Probabilistic Leaf"**.

Deterministic code, compiled state machines, local ONNX decision models, and PostgreSQL execute all safety-critical triage, clinical stance retrieval, and policy validation. Generative LLMs function strictly as presentation layers for empathetic Hinglish dialogue synthesis.

---

### Key Operational Guarantees
- **Turnaround Latency:** Total internal processing budget `< 650ms` (Whisper STT ~225ms + Core Spine ~2ms + LLM TTFT & Boundary Validation ~338ms). End-to-end voice turnaround `< 1,100ms`.
- **Platform Infrastructure Cost:** $0/month software infrastructure recurring cost. Runs on local containerized PostgreSQL 16 (`pg_trgm`), Dockerized FastAPI, NGINX proxy, Edge-TTS, and developer free-tier inference APIs.
- **Clinical Safety Assurance:** Zero critical escapes verified through an automated 16-constraint deterministic judge (`/audit/judge.py`), scoring **100.0/100.0** with mathematical regression guarantees ($FVR < 0.001$, $p < 0.05$ over 2,703 trials).

---

### Architecture Overview

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

For complete architectural documentation:
- [High-Level Design (HLD)](docs/HLD.md)
- [Low-Level Design (LLD)](docs/LLD.md)
- [Automated Audit Changelog](audit/changelog.md)

---

### Quick Start & Docker Deployment

#### 1. Requirements & Secrets
Ensure your `.env` contains:
```bash
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
POSTGRES_USER=disha
POSTGRES_PASSWORD=your_password
POSTGRES_DB=disha
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
EDGE_TTS_VOICE=hi-IN-SwaraNeural
```

#### 2. Launch Stack
```bash
docker compose up -d --build
```

#### 3. Health Check
```bash
curl -i http://127.0.0.1:8080/health
# Returns: {"ok": true, "database": true}
```

#### 4. Run Automated Invariant Audit & Latency Profiling
```bash
python -m audit.judge
python tests/benchmark_live_turn.py
```

