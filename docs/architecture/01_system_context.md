# 01. Runtime System Context

```mermaid
flowchart LR
    User["User"]
    Browser["Browser UI\n(static assets mounted by FastAPI)"]

    subgraph LocalHost["Application host"]
        TunnelAgent["Optional cloudflared process"]
        Proxy["NGINX loopback proxy\nhost :8080"]
        API["FastAPI\nhost :8000 in root Compose"]
        DB[("PostgreSQL 16\nhost :5432 in root Compose")]
        Ollama["Optional Ollama\nhost :11434"]
        MLX["Optional local audio service\nhost :8880"]
    end

    Cloudflare["Cloudflare edge\npublic HTTPS / WSS"]
    Providers["Optional Groq / Gemini APIs"]

    User --> Browser
    Browser -->|"local HTTP / WS"| Proxy
    Browser -->|"public HTTPS / WSS"| Cloudflare
    Cloudflare --> TunnelAgent
    TunnelAgent -->|"default TARGET_URL :8080"| Proxy
    Proxy --> API
    API --> DB
    API -.->|"if enabled"| Ollama
    API -.->|"if configured and authorized"| Providers
    API -.->|"LOCAL_ONLY audio path"| MLX
```

In the root Compose setup, NGINX forwards requests to FastAPI; FastAPI mounts the browser assets and owns the API/WebSocket routes. Cloudflare is an optional ingress path, not an application host or model service. The actual host mappings and the separate `disha_core/compose.yaml` stack are documented in [Deployment](../DEPLOYMENT.md).

The backend has no direct emergency-services integration. A triggered pattern can return a prepared response telling the user to contact emergency services.

Health guidance uses approved PostgreSQL records and lexical full-text/trigram retrieval. User records, prescribed meals, and general health knowledge are separate sources. The active runtime does not use embeddings or pgvector; see [RAG ingestion and retrieval](04_rag_ingestion_and_retrieval.md).
