# DISHA AI — CAPABILITY DISCOVERY & ENVIRONMENT AUDIT
**Date**: 2026-11-08  
**Platform**: macOS Darwin arm64 (Apple M5, Metal / MPS Supported)  
**Orchestrator**: BossEmployee (Lead AI Architect & Engineering Manager)

---

## 1. Machine & CLI Tools

| Capability / Category | Tool / Binary | Location | Smoke-Test Command | Result / Status | Assigned Roles |
|---|---|---|---|---|---|
| **Structural Code Index** | Synapse (`synap`) | `/Users/nitrousoxide/.local/bin/synap` | `synap status` | ✓ Active (284 files, 742 symbols indexed) | Architect, Skeptic, All Agents |
| **Container Engine** | Docker & Compose | `/usr/local/bin/docker` | `docker ps` | ✓ Healthy (Postgres 5432, Backend 8000, Nginx 8080) | Backend/DB Engineer, Breaker |
| **Local LLM Runtime** | Ollama | `/usr/local/bin/ollama` | `ollama list` | ✓ Running (`qwen2.5:7b`, `llama3.2:3b`, `qwen2.5-coder:14b`, `nomic-embed-text`) | Architect, Conv Policy, Eval |
| **Python Package / Env** | uv | `/Users/nitrousoxide/.local/bin/uv` | `uv run python --version` | ✓ Python 3.12.13 in isolated uv venv | All Python Builders |
| **Test Runner** | pytest | uv managed | `uv run pytest --version` | ✓ pytest 9.2.0 (anyio, asyncio plugins) | Eval/QA Engineer, Breaker |
| **Python Linter / Formatter** | ruff | `/Users/nitrousoxide/.local/bin/ruff` | `ruff --version` | ✓ ruff 0.17.4 | Repo Cleaner, Backend |
| **Static Type Checker** | pyright | `/Users/nitrousoxide/.local/bin/pyright` | `pyright --version` | ✓ pyright 1.1.408 | Backend, Architect |
| **Secret Scanner** | gitleaks | `/opt/homebrew/bin/gitleaks` | `gitleaks version` | ✓ v8.30.0 | Repo Cleaner, Safety |
| **Vulnerability Scanner** | trivy | `/opt/homebrew/bin/trivy` | `trivy --version` | ✓ Installed | Safety, Backend |
| **Dockerfile Linter** | hadolint | `/opt/homebrew/bin/hadolint` | `hadolint --version` | ✓ v2.14.0 | Repo Cleaner |
| **Load Testing** | k6 | `/opt/homebrew/bin/k6` | `k6 version` | ✓ v1.6.1 | Breaker |
| **Audio Processing** | ffmpeg | `/opt/homebrew/bin/ffmpeg` | `ffmpeg -version` | ✓ ffmpeg 8.1 | Speech Engineer |
| **Web Performance Audit** | lighthouse | `/opt/homebrew/bin/lighthouse` | `lighthouse --version` | ✓ v13.0.3 | Art Director, Frontend |
| **Accessibility Audit** | axe CLI | `/opt/homebrew/bin/axe` | `axe --version` | ✓ Installed | Frontend, Art Director |
| **Edge Tunnel / Proxy** | cloudflared | `/opt/homebrew/bin/cloudflared` | `cloudflared --version` | ✓ Installed | Backend, Breaker |
| **Browser Automation** | Playwright | npx managed | `npx playwright --version` | ✓ v1.65.0 (Chromium, Firefox, WebKit) | Frontend, Eval/QA |
| **Hardware Acceleration** | Apple Metal MPS | PyTorch MPS | `torch.backends.mps.is_available()` | ✓ True (M5 GPU Acceleration Active) | Speech, Eval, Architect |

---

## 2. Model & Voice Capabilities

| Modality | Engine / Model | Hardware Target | Supported Languages | Status / Role |
|---|---|---|---|---|
| **Local LLM (Fast)** | Ollama `qwen2.5:7b` | Apple M5 Metal | EN, HI, Hinglish | ✓ Verified healthy on `host.docker.internal:11434` |
| **Local LLM (Coder/Judge)**| Ollama `qwen2.5-coder:14b` | Apple M5 Metal | Code, Eval Judge | ✓ Verified available in local Ollama |
| **Speech-to-Text (STT)** | Whisper / Cloud STT | Local / Hosted | EN, HI, Hinglish | ✓ VAD + interim transcription pipeline verified |
| **Text-to-Speech (TTS) - HI**| Edge-TTS `hi-IN-SwaraNeural` | Async / Cloud | Hindi (Devanagari & Romanized), Hinglish | ✓ Tested & verified (~230ms streaming packet) |
| **Text-to-Speech (TTS) - EN**| Qwen3-TTS / Local TTS | MPS / Metal | EN, Technical terms | ⚠ Note: Official card lacks Hindi; dual-engine routed |
| **Embeddings** | `nomic-embed-text` | Ollama Local | 768-dim multi-lingual | ✓ Available for hybrid semantic search |

---

## 3. Database & Persistence Capabilities

| Subsystem | Technology | Port / URI | Smoke Test |
|---|---|---|---|
| **RDBMS** | PostgreSQL 16 Alpine | 5432 (`localhost:5432`) | ✓ Docker container running healthy, tables seeded |
| **Full-Text Search** | PostgreSQL `tsvector` + GIN index | Internal DB | ✓ Supports Hindi / English stemming & keyword queries |
| **Connection Pool** | `asyncpg` | Async Pool (20 conns) | ✓ Verified in `disha_core/adapters/db.py` |

---

## 4. MCP Servers & IDE Tooling

- **Synapse CLI (`synap`)**: Codebase structural AST indexing, token-efficient `skeleton`, `outline`, and `search`.
- **Chrome DevTools / Playwright**: Real headless & headed browser test harness with visual screenshots and axe accessibility.
- **Agent Skills**: `frontend-design`, `backend-patterns`, `python-patterns`, `python-testing`, `security-review`, `coding-standards`.

