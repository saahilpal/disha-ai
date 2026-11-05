# 07 — Zero-Cost Technology Selection & Trade-Off Matrix

This document provides a rigorous, cost-audited evaluation of all technology selections powering Disha AI. Every choice strictly adheres to the **$0.00/min Zero-Cost Mandate** without requiring paid API subscriptions or credit cards.

---

## 1. Zero-Cost Technology Evaluation Matrix

| Category | Selected Technology | Why Chosen | Alternative Considered | Trade-Off & Risk Mitigation | Cost & Free-Tier Quota |
|---|---|---|---|---|---|
| **Cloud LLM Inference** | **Groq LPU (Llama-3.3-70B-versatile)** | Ultra-low TTFT (~280ms), native code-mixed Hinglish support, generous developer tier | OpenAI GPT-4o / Anthropic Claude 3.5 Sonnet | Rate limits (30 req/min). Mitigated by automatic fallback to `llama-3.1-8b-instant` and local `MockEngine`. | **$0.00** (Free Developer Tier: 14,400 req/day) |
| **Offline CI/CD Brain** | **Deterministic Mock Engine** | Instant zero-latency responses for headless unit testing, PR validation, and offline execution | Local Ollama / vLLM | Does not handle unbounded novel queries. Mitigated by strict regex routing matching production prompts. | **$0.00** (100% in-memory Python, 0 dependencies) |
| **Speech-to-Text (STT)** | **Groq Whisper-large-v3-turbo** | Hinglish phoneme recognition, sub-300ms latency, zero cloud cost | Deepgram Nova-2 / Whisper API | Requires internet connectivity. Mitigated by Web Audio API fallback in browser. | **$0.00** (Free Developer Tier: 2,000 audio sec/min) |
| **Text-to-Speech (TTS)** | **Microsoft Edge TTS (`edge-tts`)** | Natural Indian English & Hindi neural voices (`hi-IN-SwaraNeural`, `en-IN-NeerjaNeural`), streaming chunk support | ElevenLabs / Google Cloud TTS | Edge endpoint availability. Mitigated by local sentence buffering and MP3 streaming cache. | **$0.00** (Open-source python wrapper over public Edge service) |
| **Database & Vector/BM25 Search** | **Embedded SQLite with FTS5 (WAL Mode)** | Zero network latency (<2ms), zero infrastructure cost, embedded ACID transactions, BM25 ranker | Pinecone / Qdrant / Weaviate | Single-writer limit. Mitigated by SQLite WAL mode enabling non-blocking concurrent reads during writes. | **$0.00** (Embedded local C library, zero ops) |
| **Public Founder Demo Tunnel** | **Cloudflare Tunnel (`cloudflared`)** | Instant public HTTPS URL (`*.trycloudflare.com`), full WebSocket support, DDoS protection, no account needed | ngrok (free tier limited to 1GB/mo) / Render | Tunnel requires running host. Mitigated by auto-restart script and optional Render/Docker deployment. | **$0.00** (Free tier, zero credit card) |
| **Backend Framework** | **FastAPI (Python 3.10+)** | Native async ASGI, sub-millisecond execution, WebSocket streaming, automatic OpenAPI documentation | Node.js Express / Django | None. FastAPI is industry standard for async Python AI backends. | **$0.00** (Open-source Apache 2.0) |
| **Frontend Architecture** | **Tailwind CSS + Vanilla JS + Web Audio** | Zero compilation overhead, instant static serving, low memory footprint, native Web Audio API | React / Next.js | Manual DOM manipulation. Mitigated by clean modular JS controllers and component helpers. | **$0.00** (Zero build cost, runs in any browser) |
| **Automated Testing & QA** | **Pytest + AnyIO + Mutation Engine** | Async coroutine testing, sub-second execution (31 tests in 0.44s), defect injection verification | Jest / Postman | Requires python environment. Mitigated by committed venv scripts and pytest.ini. | **$0.00** (Open-source) |

---

## 2. In-Depth Architectural Justifications

### 2.1 Groq LPU vs. Local Ollama vs. Paid APIs
- **Decision:** Groq Developer Tier (`llama-3.3-70b-versatile`) with offline `MockConversationalEngine` failover.
- **Reason:** In voice follow-up calls, turn latency is the critical user experience barrier. Standard cloud APIs (OpenAI/Anthropic) incur 900–1,500ms TTFT and cost $0.01–$0.03 per turn. Groq delivers 70B parameter inference at 750 tokens/sec with ~280ms TTFT for **$0.00**.
- **Alternative Considered:** Running Ollama locally on CPU. On standard dev machines without dual 48GB GPUs, 70B quantization takes 15–20 seconds per turn, violating the `<1–2s` SLA budget.
- **Trade-off:** Groq developer tier imposes rate limits of 30 requests/minute. We mitigate this with an automatic cascade:
  1. Primary: `llama-3.3-70b-versatile` (high clinical reasoning capacity)
  2. Fallback: `llama-3.1-8b-instant` (higher rate limit, ~120ms TTFT)
  3. CI/Offline: `MockConversationalEngine` (deterministic zero-cost backup)

### 2.2 Embedded SQLite + FTS5 vs. Vector Databases
- **Decision:** SQLite with FTS5 full-text indexing and BM25 ranker.
- **Reason:** Clinical rules and patient meal plans are crisp, keyword-anchored facts (e.g., *"bloating"*, *"dinner"*, *"mangoes"*). Vector similarity on short 3-word Hinglish queries often suffers from semantic drift (e.g., matching *"pet dard"* to *"chest pain"*). FTS5 provides sub-1.5ms exact and token-prefix matching with zero network latency, zero operational overhead, and zero hosting cost.
- **Alternative Considered:** Pinecone / Weaviate / Qdrant Cloud. These require paid tiers after 30 days, introduce 40–120ms network round-trip overhead per turn, and add external failure modes.

### 2.3 Edge-TTS vs. ElevenLabs
- **Decision:** Microsoft Edge TTS (`hi-IN-SwaraNeural`).
- **Reason:** ElevenLabs charges $22/month after a tiny 10,000-character free quota (depleted in ~15 test calls). Edge-TTS provides high-fidelity, natural Indian accent neural speech in Hinglish with streaming byte support at **$0.00** with zero quota expiration.

### 2.4 Cloudflare Tunnel vs. Localhost / Ngrok
- **Decision:** Cloudflare Tunnel (`cloudflared`).
- **Reason:** The founder requires testing a public application from their own smartphone or laptop without developer assistance. Cloudflare Tunnel provides an authenticated, SSL-encrypted public domain (`https://*.trycloudflare.com`) with full WebSocket streaming support at **$0.00** without session time limits or bandwidth caps.

