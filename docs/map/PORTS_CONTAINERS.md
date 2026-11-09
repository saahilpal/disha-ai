# Disha AI — Ports, Containers & Networking Cartography

**Document Status:** Historical generated snapshot — not current runtime authority

> Port and container details vary by Compose file. Use [Deployment](../DEPLOYMENT.md) for the checked-in configurations and the timestamped host snapshot.
**Target Environments:** Local Docker Engine & Cloud Linux VMs (`deploy-vm.sh`)  
**Base Configurations:** `docker-compose.yml`, `docker-compose.prod.yml`, `disha_core/compose.yaml`

---

## 1. Network Topologies & Exposed Ports

```mermaid
graph LR
    subgraph Public_Internet ["Public Internet & Edge Network"]
        BrowserClient["Browser Web Client (Desktop / Mobile)<br/>WSS / HTTPS"]
        Cloudflare["Cloudflare Edge / Tunnel<br/>- TLS 1.3 Termination<br/>- DDoS Shield &amp; WAF<br/>- Zero Port Forwarding"]
        BrowserClient -->|TLS 1.3 (Port 443)| Cloudflare
    end

    subgraph Host_Network ["Host Machine / Cloud VM"]
        Port80["Port 80 (HTTP / Proxy Pass)"]
        Port443["Port 443 (HTTPS)"]
        Port8080["Port 8080 (Local Dev Ingress)"]
        Port5432["Port 5432 (Postgres Bind: 127.0.0.1)"]
        Port8000["Port 8000 (Backend Direct: 127.0.0.1)"]
    end

    Cloudflare -->|Encrypted Tunnel / Reverse Proxy| Port80
    Cloudflare -->|Encrypted Tunnel / Reverse Proxy| Port443

    subgraph Docker_Bridge_Network ["Docker Isolated Bridge: disha_network / disha_internal"]
        subgraph Proxy_Container ["Container: proxy (nginx:1.28-alpine)"]
            NGINX_Internal[":80 Listening"]
        end

        subgraph Backend_Container ["Container: backend (python:3.12-slim)"]
            FastAPI_Internal[":8000 Uvicorn<br/>(Non-root UID: 10001)"]
        end

        subgraph Laya_Container ["Container: laya (python:3.12-slim)"]
            Laya_Internal[":8005 laya.serve"]
        end

        subgraph Postgres_Container ["Container: postgres (postgres:16-alpine)"]
            PG_Internal[":5432 PostgreSQL 16"]
        end
    end

    Port8080 -->|Dev Ingress| NGINX_Internal
    Port80 -->|Prod Ingress| NGINX_Internal
    Port443 -->|Prod Ingress| NGINX_Internal
    Port5432 -.->|Local Debug| PG_Internal
    Port8000 -.->|Direct API Debug| FastAPI_Internal

    NGINX_Internal -->|Reverse Proxy /ws/, /chat, /health| FastAPI_Internal
    FastAPI_Internal -->|pgwire (pool max: 30)| PG_Internal
    FastAPI_Internal -->|POST /v1/systemone| Laya_Internal
```

---

## 2. Port Mapping Matrix

| Container Service | Container Internal Port | Host Bound Port | Protocol | Binding Scope | Purpose |
|---|---|---|---|---|---|
| **NGINX Proxy (Dev)** | `80` | `8080` | TCP / HTTP / WSS | `127.0.0.1:8080` | Local developer ingress proxy |
| **NGINX Proxy (Prod)** | `80`, `443` | `80`, `443` | TCP / HTTP / HTTPS | `0.0.0.0:80`, `0.0.0.0:443` | Public production ingress gateway |
| **FastAPI Core Backend** | `8000` | `8000` | TCP / HTTP / WSS | `127.0.0.1:8000` (Dev only) | Direct Uvicorn ASGI application server |
| **Laya Decision Server** | `8005` | None (Internal) | TCP / HTTP | Internal Bridge Only (`http://laya:8005`) | Containerized System 1 intent classifier |
| **PostgreSQL 16** | `5432` | `5432` | TCP / pgwire | `127.0.0.1:5432` (Dev only) | Database server and Merkle audit storage |

---

## 3. Container Topology Specifications

### 3.1 Production Stack (`docker-compose.prod.yml`)
Designed for Cloud Linux VMs (Ubuntu 22.04 / Debian 12) with 4+ vCPU and 8+ GB RAM:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: disha-prod-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: disha
      POSTGRES_USER: disha
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./disha_core/db/schema.sql:/docker-entrypoint-initdb.d/001-schema.sql:ro
      - ./disha_core/db/seed_icmr_data.sql:/docker-entrypoint-initdb.d/002-icmr.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U disha -d disha"]
      interval: 5s
      timeout: 3s
      retries: 20
    networks:
      - disha_network

  laya:
    image: python:3.12-slim
    container_name: disha-prod-laya
    restart: unless-stopped
    environment:
      LAYA_HOST: "0.0.0.0"
      LAYA_PORT: "8005"
      LAYA_MODELS: "multilingual"
      LAYA_DEFAULT_MODEL: "multilingual"
      LAYA_PRELOAD: "1"
    command: >
      sh -c "pip install --no-cache-dir laya==0.4.27 && python -m laya.serve"
    healthcheck:
      test: ["CMD-SHELL", "python -c 'import urllib.request; urllib.request.urlopen(\"http://127.0.0.1:8005/health\")'"]
      interval: 10s
      timeout: 5s
      retries: 10
    networks:
      - disha_network

  backend:
    build:
      context: ./disha_core
    container_name: disha-prod-backend
    restart: unless-stopped
    environment:
      DB_HOST: postgres
      DB_PORT: "5432"
      DB_NAME: disha
      DB_USER: disha
      DB_PASSWORD: ${POSTGRES_PASSWORD}
      LAYA_URL: "http://laya:8005"
      GROQ_API_KEY: ${GROQ_API_KEY}
      GROQ_MODEL: ${GROQ_MODEL:-openai/gpt-oss-120b}
      GEMINI_API_KEY: ${GEMINI_API_KEY}
      GEMINI_MODEL: ${GEMINI_MODEL:-gemini-3.6-flash}
      CORS_ALLOWED_ORIGINS: "*"
    depends_on:
      postgres:
        condition: service_healthy
      laya:
        condition: service_healthy
    networks:
      - disha_network

  proxy:
    image: nginx:1.28-alpine
    container_name: disha-prod-proxy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./disha_core/nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - backend
    networks:
      - disha_network
```

---

## 4. Volume Mounts & Data Persistence

| Volume Identifier | Mount Point in Container | Host Path | Mode | Lifecycle & Persistence Rule |
|---|---|---|---|---|
| `postgres_data` | `/var/lib/postgresql/data` | Managed Docker Volume | `rw` | Persistent; survives container restarts and upgrades. |
| Schema Init DDL | `/docker-entrypoint-initdb.d/001-schema.sql` | `./disha_core/db/schema.sql` | `ro` | Read-only initialization; executed on first container boot. |
| Seed Data DDL | `/docker-entrypoint-initdb.d/002-icmr.sql` | `./disha_core/db/seed_icmr_data.sql` | `ro` | Seeds ICMR clinical stances, test profiles, and tokens. |
| NGINX Config | `/etc/nginx/conf.d/default.conf` | `./disha_core/nginx.conf` | `ro` | Declarative reverse proxy rules, timeouts, and headers. |
| Audit WAL | `/srv/audit_wal.db` | Host working directory | `rw` | Ephemeral crash buffer; persists uncommitted records. |

---

## 5. Security & Container Hardening Invariants

1. **Rootless Backend Execution:** `disha_core/Dockerfile` provisions a non-root system user:
   ```dockerfile
   RUN useradd --system --uid 10001 --create-home disha
   USER 10001
   ```
   The backend container executes without root capabilities, mitigating container breakout vulnerabilities.
2. **Network Isolation:** PostgreSQL and Laya are attached only to the internal bridge network (`disha_network` / `disha_internal`). They cannot be directly reached from the public internet.
3. **Buffering Disabled for Streaming:** In `nginx.conf`, `proxy_buffering off;` and `add_header X-Accel-Buffering no;` are explicitly set on `/chat/stream` and `/voice` to prevent NGINX from buffering chunked speech and SSE tokens.
4. **Proxy Timeouts:** WebSocket routes (`/ws/` and `/voice`) enforce persistent timeouts:
   - `proxy_read_timeout 3600s;`
   - `proxy_send_timeout 3600s;`
   - `client_max_body_size 10m;`
