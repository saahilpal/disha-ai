# 🚀 Disha AI — Deployment, Infrastructure & Operations Guide

**Document Path:** `docs/DEPLOYMENT.md`  
**Classification:** Core Infrastructure & Operations Specification  
**Version:** 2.0.0 (Production Verified)  
**Maintained by:** Agent A (Backend Lead), Agent E (Telephony Engineer) & Agent H (Learning Tracker)  
**Last Updated:** 2026-11-08  

---

## 1. Executive Summary

Disha AI is designed for containerized deployment across local development, edge appliances, and production cloud infrastructure. It requires:
1. **FastAPI Backend (`disha_core`):** Python 3.12+ ASGI application running via Uvicorn.
2. **PostgreSQL 16 Database:** Containerized PostgreSQL with `pg_trgm` extension for sub-2.0ms lexical retrieval.
3. **Cloudflare Tunnel Ingress:** TLS 1.3 reverse proxy satisfying browser W3C Secure Context requirements for `getUserMedia()`.
4. **NGINX Reverse Proxy:** High-performance static asset server and WebSocket proxy.
5. **Vercel Serverless (Optional Edge Static Host):** Static frontend deployment with serverless Node.js API bridges.

---

## 2. Infrastructure Architecture & Container Topology

```mermaid
flowchart TD
    subgraph Internet ["Public Edge Ingress"]
        ClientBrowser["Mobile / Desktop Web Browser"]
        CFTunnel["Cloudflare Tunnel (TLS 1.3 Edge)\n*.trycloudflare.com / custom domain"]
    end

    subgraph HostContainerNetwork ["Docker Host Network (compose.yaml)"]
        Nginx["NGINX Reverse Proxy (Port 80)\nStatic Assets + WebSocket Buffering"]
        
        subgraph BackendService ["FastAPI App (disha_core:8080)"]
            Uvicorn["Uvicorn ASGI Server"]
            LayaEngine["In-Process Laya Decision Head\n(PyTorch / MPS / CPU)"]
            VoicePipeline["Voice Session Handler\n(Groq STT + Edge-TTS)"]
        end

        subgraph DatabaseService ["PostgreSQL 16 Alpine (Port 5432)"]
            PG["PostgreSQL 16 Engine"]
            PGTRGM["pg_trgm Trigram Extension"]
            PGData[("postgres_data Managed Volume")]
        end
    end

    ClientBrowser -->|HTTPS / WSS| CFTunnel
    CFTunnel -->|HTTP / WS| Nginx
    Nginx -->|Static HTML/CSS/JS| ClientBrowser
    Nginx -->|Proxy Pass /chat, /ws, /auth| Uvicorn
    Uvicorn --> LayaEngine
    Uvicorn --> VoicePipeline
    Uvicorn -->|asyncpg Pool (Port 5432)| PG
    PG --> PGTRGM
    PG --> PGData
```

---

## 3. Environment Configuration Matrix

Configuration is dynamically read from shell environment variables in `disha_core/config.py`:

| Variable Name | Default Value | Description / Required Format |
|---|---|---|
| `DATABASE_URL` | `None` | Full PostgreSQL connection URL (e.g. `postgresql://disha:password@localhost:5432/disha`) |
| `DB_HOST` | `"localhost"` | PostgreSQL hostname or container service name (`postgres` in compose) |
| `DB_PORT` | `5432` | PostgreSQL TCP port |
| `DB_NAME` | `"disha"` | Database name |
| `DB_USER` | `"disha"` | Database user account |
| `DB_PASSWORD` | `""` | Database password |
| `DB_POOL_MIN` | `2` | Minimum asyncpg connections in pool |
| `DB_POOL_MAX` | `30` | Maximum asyncpg connections in pool |
| `GROQ_API_KEY` | `""` | Groq Cloud API key for Whisper STT and Llama-3.3 LLM |
| `GROQ_MODEL` | `"openai/gpt-oss-120b"` | Groq LLM model identifier |
| `GROQ_HEALTH_DATA_AUTHORIZED` | `"true"` | Explicit compliance flag for health data processing |
| `GEMINI_API_KEY` | `""` | Google Gemini API key for secondary LLM failover |
| `GEMINI_MODEL` | `"gemini-3.6-flash"` | Gemini model identifier |
| `GEMINI_HEALTH_DATA_AUTHORIZED`| `"true"` | Explicit compliance flag for Gemini health processing |
| `ADMIN_API_KEY` | `""` | Secret key required to query `/internal/classifier` and admin routes |
| `PASSWORD_SALT` | `"disha_salt_v1"` | Cryptographic salt for password hashing |
| `CORS_ALLOWED_ORIGINS` | `""` | Comma-delimited list of allowed CORS origins (e.g. `https://example.com`) |
| `MAX_VOICE_TURN_BYTES` | `10485760` | Maximum byte size for a single audio turn frame (10MB) |
| `VOICE_TRANSCRIBE_TIMEOUT` | `8.0` | Timeout in seconds for Groq Whisper transcription |

---

## 4. Local Development Deployment (Docker Compose)

### 4.1 Starting the Services
From the repository root:
```bash
# 1. Ensure .env is populated with valid API keys
cp .env.example .env
# Edit .env to add your GROQ_API_KEY

# 2. Start PostgreSQL and Disha Core
docker compose up -d

# 3. Check container status
docker compose ps
```

### 4.2 Running Database Migrations
Migrations are managed via Alembic:
```bash
# Run latest database migrations
.venv/bin/alembic upgrade head

# Seed initial ICMR guidelines and demo patient records
.venv/bin/python3 disha_core/db/ingest_open_datasets.py
```

### 4.3 Verifying Health Probes
```bash
# General health probe
curl -sS http://localhost:8080/health | jq .

# System readiness (database + classifier)
curl -sS http://localhost:8080/ready | jq .

# In-process Laya classifier telemetry
curl -sS -H "Authorization: Bearer dev-admin-secret" http://localhost:8080/internal/classifier | jq .
```

---

## 5. Cloudflare Tunnel Ingress (Web Audio Secure Context)

### 5.1 Why Cloudflare Tunnel is Mandatory
Modern browsers (iOS Safari, Android Chrome, desktop browsers) enforce the **Secure Context Invariant**. Access to the device microphone via `navigator.mediaDevices.getUserMedia()` is permanently blocked on non-secure origins (`http://192.168.x.x`).

Cloudflare Tunnel provides an authenticated, zero-config public HTTPS ingress with TLS 1.3 certificates, satisfying the Secure Context Invariant.

### 5.2 Starting the Tunnel Watchdog Daemon
```bash
# Start Cloudflare tunnel watchdog daemon
./scripts/tunnel-watchdog.sh --start

# Check tunnel status and retrieve active public URL
./scripts/tunnel-watchdog.sh --status

# Stop tunnel daemon
./scripts/tunnel-watchdog.sh --stop
```
The public ingress URL is logged to `agent/TUNNEL_URL.txt` (e.g., `https://cached-developed-collectors-kerry.trycloudflare.com`).

---

## 6. Vercel Static Frontend Deployment (`vercel.json`)

Disha AI can deploy its frontend statically to Vercel for high-speed CDN delivery:

- **Configuration:** [`vercel.json`](file:///Users/nitrousoxide/Code/disha%20ai/disha_core/frontend/vercel.json)
- **Static Assets:** Serves `frontend/index.html`, `style.css`, `app.js`.
- **Serverless API Bridges:** [`api/`](file:///Users/nitrousoxide/Code/disha%20ai/disha_core/frontend/api/) contains Node.js serverless functions (`auth/login.js`, `patient/profile.js`, `health.js`, `ready.js`) enabling authentication on the static preview.
- **WebSocket Backend Requirement:** Note that Vercel serverless functions cannot host persistent WebSockets. For live voice consultations, the frontend automatically routes WebSocket connections to the configured backend host or Cloudflare Tunnel URL.

---

## 7. Frontend Byte Synchronization (`scripts/sync-frontend.sh`)

To eliminate code drift between `frontend/` (root) and `disha_core/frontend/` (container package):

```bash
# Run automated byte sync
./scripts/sync-frontend.sh
```
This script runs `rsync` with checksum verification, ensuring 100% byte-for-byte SHA-256 parity across both directories.

---

## 8. Operational Runbook & Troubleshooting

### Issue 1: `TypeError: navigator.mediaDevices is undefined`
- **Cause:** User is accessing the app over plain `http://` on a LAN IP.
- **Fix:** Connect via the HTTPS Cloudflare Tunnel URL or `http://localhost`.

### Issue 2: `The AudioContext was not allowed to start`
- **Cause:** Audio was initialized without a direct physical click gesture on the DOM.
- **Fix:** Ensure the user clicks the `#start-call-btn` or `#consent-accept-btn` directly.

### Issue 3: Classifier Latency Variance in Tests
- **Cause:** In-process PyTorch classifier running concurrently on multi-threaded CPU.
- **Fix:** For production, configure `LAYA_SERVER_URL` to point to a dedicated container or ensure Metal GPU (`mps:0`) acceleration is active.
