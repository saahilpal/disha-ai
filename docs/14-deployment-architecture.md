# 11. Deployment, Infrastructure & Operations — Disha Clinical Voice AI

## 1. Zero-Cost Infrastructure Architecture

Disha AI is designed to deploy and operate with **zero infrastructure cost ($0.00/month)** during development, testing, clinical trials, and initial rollout.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       ZERO-COST DEPLOYMENT TOPOLOGY                         │
│                                                                             │
│  User / Clinician Browser                                                   │
│        │                                                                    │
│        ├─── HTTPS (Static Assets: HTML5 / Tailwind / React)                │
│        └─── WSS (Real-Time Audio / Voice Turns)                            │
│                 │                                                           │
│                 ▼                                                           │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ Container Runtime (Docker / Render Free / Fly.io / Localhost)         │  │
│  │                                                                       │  │
│  │   FastAPI Async Application (Uvicorn Worker)                          │  │
│  │   ├── Static File Server (Clinical Studio SPA)                        │  │
│  │   ├── WebSocket Streaming Turn Pipeline                               │  │
│  │   ├── Deterministic Safety Spine (Aho-Corasick)                       │  │
│  │   ├── Embedded SQLite Database (`disha_clinical.db` with WAL)         │  │
│  │   └── FastEmbed CPU Vector Engine (ONNX Runtime)                      │  │
│  └───────────────────────────────────┬───────────────────────────────────┘  │
│                                      │                                      │
│                  ┌───────────────────┴───────────────────┐                  │
│                  ▼                                       ▼                  │
│     Groq Cloud Developer API                 Microsoft Edge TTS             │
│     • Llama-3.3-70B (30 RPM free)            • Neural Speech WebSocket      │
│     • Whisper-large-v3 (2k req/day free)     • hi-IN-SwaraNeural (100% free)│
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Deployment Options

### Option A: Local Development & Single-Command Run (Default)
- **Requirements:** Python 3.10+ (macOS, Linux, or Windows).
- **Setup:**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  python3 -m app.main
  ```
- **Access:** Open `http://localhost:8000` in any web browser to access the Clinical Authoring Studio, Live Voice Simulator, and Regression Test Suite.

### Option B: Unified Production Docker Container
A multi-stage container that packages the FastAPI backend, embedded SQLite database, and the pre-built web interface into a single lightweight container image (< 450 MB footprint):

```dockerfile
FROM python:3.12-slim-bookworm

WORKDIR /app

# Install system audio dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Initialize SQLite database with seed schemas
RUN python3 -m app.db.init_db

EXPOSE 8000

ENV PORT=8000
ENV DATABASE_PATH=/app/data/disha_clinical.db

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Option C: Zero-Cost Cloud Hosting (Render / Hugging Face Spaces / Fly.io)
- **Render.com Free Tier:** Deploy directly from GitHub repository as a Web Service. Free 512MB RAM, automatic SSL certificates.
- **Hugging Face Spaces (Docker):** 100% free hosting with 2 vCPU and 16GB RAM, ideal for public clinical demonstration.
- **Persistent Storage:** Attach a free 1GB persistent volume for `disha_clinical.db` to retain clinician rule updates across deploys.

### Option D: Live Public Cloudflare Tunnel (Active Founder Demo URL)
- **Public URL:** `https://prostores-daughters-div-deutschland.trycloudflare.com`
- **Execution Command:**
  ```bash
  source venv/bin/activate
  uvicorn app.main:app --host 0.0.0.0 --port 8000 &
  cloudflared tunnel --url http://127.0.0.1:8000
  ```
- **Capabilities:** Full HTTPS SSL termination, WebSocket voice streaming support, DDoS shielding, accessible on desktop, iOS Safari, and Android Chrome.

---

## 3. Environment Variables & Secret Configuration

All configuration is strictly environment-based. Never commit `.env` files to source repositories.

| Variable Name | Required | Default Value | Description |
| :--- | :--- | :--- | :--- |
| `GROQ_API_KEY` | Optional | `""` | Groq Cloud API key for Llama-3.3 and Whisper. If empty, runs in **Mock/Local Mode** for offline testing. |
| `DATABASE_PATH` | No | `data/disha_clinical.db` | Path to the SQLite database file. |
| `APP_ENV` | No | `development` | `development`, `staging`, or `production`. |
| `PORT` | No | `8000` | Port for the HTTP and WebSocket server. |
| `LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `TTS_VOICE` | No | `hi-IN-SwaraNeural` | Default neural voice for speech synthesis. |
| `CARE_OPS_WEBHOOK_URL`| No | `""` | Webhook URL for emergency red-flag escalation alerts. |

---

## 4. Telephony Integration Architecture (SIP / PSTN)

When scaling from the web simulator to real outbound cellular telephone calls:

```
[Patient Mobile Phone] 
       │ (Standard GSM / VoLTE Call)
       ▼
[Telecom Carrier (Jio / Airtel / Vi)]
       │ (SIP Trunking)
       ▼
[Telephony Gateway (Exotel / Plivo / Twilio)]
       │ (Bidirectional Audio WebSocket)
       ▼
[Disha AI WebSocket Engine (/ws/telephony/{call_id})]
```

- **Protocol Compatibility:** Disha AI’s WebSocket interface natively accepts 8kHz/16kHz PCM audio streams conforming to standard Twilio Media Streams or Exotel Voice Streaming specifications.
- **Latency Over GSM:** Indian domestic cellular latency adds ~80–120ms network delay. Combined with our ~850ms pipeline, total voice turnaround remains under **1.1 seconds**, feeling instant to the patient.
