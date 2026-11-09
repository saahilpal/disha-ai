# Security Notes: Current Implementation and Historical Proposal

**Document Path:** `docs/SECURITY.md`  
**Status:** Code-grounded observations followed by retained, unverified historical design material.

---

## Current code-grounded notes

These are implementation observations, not a penetration test, security certification, or compliance determination. See [Deployment](DEPLOYMENT.md) for the current host and Compose configuration.

- Passwords are stored as PBKDF2-HMAC-SHA256 hashes with per-password random salts and 310,000 iterations. Login retains a legacy fixed-salt SHA-256 verification path that upgrades a successful legacy login.
- Patient bearer tokens are stored as SHA-256 digests and registration sets a 365-day expiry. The chat emergency-text shortcut runs before patient-token authentication; regular chat and voice paths authenticate.
- The application has in-process sliding-window limits: the auth helper allows 20 requests/minute per client IP and chat allows 60/minute per token-prefix or client-IP key. These counters are not shared across worker processes and can be disabled with `RATE_LIMIT_ENABLED=false`.
- The HTTP request middleware rejects requests whose `Content-Length` exceeds the configured limit (2 MiB by default); it does not count streaming bodies without that header. Voice processing also rejects an individual audio payload over 10 MiB. These limits are not a complete denial-of-service defense.
- Audit text passes through a finite set of regex redactions. Records are queued, written to a local SQLite WAL, and persisted in a PostgreSQL SHA-256 hash chain. Pattern redaction is not guaranteed de-identification; a hash chain is not proof of immutability, complete durability, or regulatory compliance.
- The root and production-sketch Compose files set wildcard CORS and contain default database-password fallbacks. CORS is not authentication; do not expose these defaults as a production security boundary. The deployment guide describes these configuration caveats.
- No assertion of HIPAA, DPDP, ICMR, or other regulatory compliance is made. Provider authorization, secret management, network exposure, operational monitoring, and clinical safety need deployment-specific review.

## Historical design material (unverified)

The remainder of this document is retained for context only. Its claims and test results have not been independently validated against the current code; statements about guaranteed isolation, zero-PHI handling, cryptographic immutability, reliability, compliance, and test-suite status must not be relied on as current evidence.

## 1. Security Architecture & Threat Model

In clinical AI telephony and conversational medicine, security spans traditional cyber defense (confidentiality, integrity, availability, least privilege) and clinical safety (zero-PHI telemetry, non-negotiable patient data isolation, prompt-injection defense, and instant emergency deflection).

Disha AI addresses these threat surfaces through a layered defense-in-depth model:

```
[Edge Ingress]            -> Cloudflare TLS 1.3 / Nginx Reverse Proxy (Bufferless SSE)
      ↓
[Request Size & DoS Gate] -> 2MB Request Body Size Guard (HTTP 413) + Sliding-Window Rate Limiter (HTTP 429)
      ↓
[Authentication Gate]     -> Cryptographic SHA-256 Digest Token Lookup (HTTP 401 on missing/expired/forged)
      ↓
[Multi-Tenant Isolation]  -> Patient ID bound strictly from verified token; zero cross-patient data access
      ↓
[Pre-Turn Ingress Gate]   -> Aho-Corasick Deterministic Clinical Breaker (<0.02ms, Zero LLM Exposure)
      ↓
[Deterministic Spine]     -> Parameterized asyncpg pool queries ($1, $2) + Cache partitioned by (patient_id, hash)
      ↓
[Post-Turn Egress Gate]   -> SentenceValidator AST/Regex Rewrite Gate (Diagnostic, Medication, Dietary Bounds)
      ↓
[Zero-PHI Audit Chain]    -> Instant Regex Scrubber + SHA-256 Merkle Ledger + Append-Only SQLite WAL
```

---

## 2. Patient Isolation & Multi-Tenant Boundary Enforcement

Disha AI implements strict multi-tenant patient isolation. Under no circumstances can patient A access, modify, or observe data belonging to patient B.

### 2.1 Cryptographic Identity Binding
- **Client Identity is Derived, Never Trusted:** The API rejects any user-supplied `patient_id` in request payloads. `TurnRequest` uses `model_config = ConfigDict(extra="forbid")`, automatically rejecting requests attempting to pass `patient_id` with HTTP 422.
- **Server-Side Token Resolution:** All endpoints invoke `_authenticated_patient(request, authorization)`, which hashes the Bearer token using SHA-256 and retrieves the `patient_id` from `patient_access_tokens` where `revoked_at IS NULL AND (expires_at IS NULL OR expires_at > NOW())`.

### 2.2 Strict Database Query Parameterization
All database interactions bind `patient_id` explicitly as a parameterized SQL variable (`$1`, `$2`):
- **Clinical Profile:** `SELECT ... FROM patient_profiles WHERE patient_id = $1`
- **PEP Constraints:** `SELECT ... FROM patient_pep WHERE patient_id = $1`
- **Diet Schedules:** `SELECT ... FROM patient_diet_schedules WHERE patient_id = $1 AND day_of_week = $2 AND meal_type = $3 AND is_active = TRUE`
- **Profile Updates:** `UPDATE patient_profiles SET ... WHERE patient_id = $idx`

### 2.3 Retrieval Cache Partitioning
The semantic retrieval cache (`_RETRIEVAL_CACHE` in `disha_core/engine/retriever.py`) uses a compound key:
$$\text{CacheKey} = (\text{patient\_id}, \text{query\_hash})$$
Even if two patients issue the exact same nutritional or medical query, their retrieval cache slots remain strictly partitioned, preventing cross-tenant cache snooping or leakage.

### 2.4 In-Memory Conversation History Isolation
Multi-turn context memory (`app.state.conversation_history`) is stored as a keyed map `dict[patient_id, list[turn]]`. Turns belonging to Patient A are never accessible or injected into prompts for Patient B.

---

## 3. Authentication & Credential Security

### 3.1 Patient Access Token Storage
Bearer tokens are never stored in plaintext. Disha AI stores only 64-character SHA-256 hexadecimal digests in PostgreSQL:

```sql
CREATE TABLE IF NOT EXISTS patient_access_tokens (
    token_hash CHAR(64) PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    patient_id VARCHAR(64) NOT NULL CHECK (btrim(patient_id) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS idx_patient_access_tokens_patient_active
    ON patient_access_tokens(patient_id, expires_at) WHERE revoked_at IS NULL;
```

- **Hash Computation:** `access_token_hash(token) = hashlib.sha256(token.encode("utf-8")).hexdigest()`.
- **Validation:** Queries strictly require `token_hash = $1 AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at > NOW())`.
- **Rejection (HTTP 401):** Missing, malformed, non-Bearer, expired, or non-existent tokens are rejected immediately with HTTP 401.

### 3.2 Password Hashing
- User passwords require minimum 6 characters and are salted with `PASSWORD_SALT` and hashed with cryptographic SHA-256 before persistence.
- Plaintext passwords are never logged, exported, or retained in heap memory.

### 3.3 Administrative Access
- Sensitive administrative routes (`/internal/classifier`, retraining triggers) require `ADMIN_API_KEY` header verification.

---

## 4. Zero-PHI Logging & Cryptographic Audit Ledger

To comply with the Indian Digital Personal Data Protection (DPDP) Act 2023, ICMR guidelines, and HIPAA standards, all telemetry and audit logs are scrubbed of direct identifiers and credentials.

### 4.1 Automated Zero-PHI & Secret Scrubbing
`AuditRecord` automatically scrubs all fields in `__post_init__` before any persistence or hashing:
- **Auth Tokens:** `Bearer [REDACTED]`, `pt_live_[REDACTED]`, `pt_test_[REDACTED]`
- **Credentials & API Keys:** `password=[REDACTED]`, `token=[REDACTED]`, `[GOOGLE_API_KEY_REDACTED]`, `[GROQ_API_KEY_REDACTED]`, `[API_KEY_REDACTED]`
- **National Biometric IDs:** Indian Aadhaar 12-digit patterns -> `[AADHAAR_REDACTED]`
- **Contact Information:** 10-digit Indian mobile numbers and international prefixes -> `[PHONE_REDACTED]`, RFC emails -> `[EMAIL_REDACTED]`
- **Clinical IDs:** Hospital identifiers (MRN, UHID, IPD, OPD) -> `[MRN_REDACTED]`

### 4.2 Cryptographic Merkle Hash Chain
Every turn is appended to an immutable SHA-256 Merkle chain in `audit_claim_ledger`:
$$\text{CurrentHash}_i = \text{SHA-256}(\text{PrevHash}_{i-1} \parallel \text{PatientID} \parallel \text{UserInput} \parallel \text{LLMOutput} \parallel \text{BreakerStatus} \parallel \text{ValidatorStatus})$$
- **Genesis Block:** Initialized in PostgreSQL `audit_chain_head` as 64 zeros.
- **Tamper Evidence:** Modifying any single byte in historical turns breaks all downstream digests, making unauthorized record alteration mathematically provable.

### 4.3 SQLite Write-Ahead Log (WAL) Sidecar
To protect against power failure, process termination, or network interruption, `AuditLedger` synchronously commits each event to an append-only SQLite WAL database (`disha_core/audit_wal.db`) before asynchronous batch persistence to PostgreSQL. On server reboot or container cycling, uncommitted WAL records are replayed to PostgreSQL automatically.

---

## 5. API Hardening, Input Validation & DoS Protection

### 5.1 Request Body Size Limits
- An ASGI middleware enforces `MAX_REQUEST_BODY_BYTES` (default: 2 MB for JSON HTTP requests).
- Payloads exceeding 2 MB are rejected immediately with HTTP 413 Payload Too Large without allocating heap memory.
- Voice binary WebSocket chunks enforce a strict 10 MB limit (`MAX_VOICE_TURN_BYTES`), closing the connection with code 1009 if exceeded.

### 5.2 Strict Pydantic v2 Boundary Validation
- `TurnRequest`:
  - `min_length=1`, `max_length=5000`
  - Rejects empty strings and whitespace-only utterances with HTTP 422.
  - Rejects embedded null bytes (`\x00`) to prevent database escape vulnerabilities.
  - `extra="forbid"` rejects unauthorized parameter injection.
- `LoginRequest`:
  - Enforces email RFC structure (`@` and `.`), max 255 chars, and null-byte rejection.
- `OnboardingRequest` & `ProfileUpdateRequest`:
  - Explicit bounds on numeric health metrics (age: 1-120, height: 40-280 cm, weight: 10-400 kg).
  - Explicit string max lengths (name: 128 chars, focus: 255 chars, concerns: 2000 chars).
  - Null-byte scanning on all incoming string attributes.

### 5.3 Sliding-Window Rate Limiting
Disha AI includes an in-memory sliding-window rate limiter (`disha_core/security/rate_limiter.py`):
- **Authentication Routes (`/auth/login`, `/auth/register`):** 20 requests/minute per client IP (prevents credential stuffing).
- **Conversational Routes (`/chat`, `/chat/stream`):** 60 requests/minute per client key/IP (prevents provider quota exhaustion).
- **Quota Exceeded Behavior:** Returns HTTP 429 Too Many Requests with a standardized `Retry-After: <seconds>` response header.

---

## 6. Resilience & Reliability Hardening

### 6.1 Server-Sent Events (SSE) Streaming Hardening
- **Cancellation Detection:** During `/chat/stream`, the generator monitors `await request.is_disconnected()` at sentence boundaries. If the client closes the tab or aborts the connection, the streaming generator terminates immediately, freeing LLM provider resources.
- **Exception Cleanliness:** Catches `asyncio.CancelledError` and `GeneratorExit` cleanly without logging unhandled traceback errors.
- **Durability Guarantee:** The `finally:` block logs whatever partial turn was emitted directly to the `AuditLedger`.
- **Proxy Compatibility:** Injects `Cache-Control: no-cache`, `Connection: keep-alive`, and `X-Accel-Buffering: no` to prevent intermediate Nginx / CDN buffering.

### 6.2 Full-Duplex Voice & WebSocket Resilience
- **Inactivity Timeout:** Idle WebSocket connections automatically close after 300 seconds (5 minutes) with code 1000, preventing orphaned connection leaks.
- **Turn Execution Timeout:** Voice and text processing per turn are bounded by `asyncio.timeout(30.0)`. Runaway Whisper or LLM provider stalls abort gracefully with an error frame rather than hanging worker processes.
- **Barge-In Task Teardown:** When a user interrupts ("barge-in"), the active TTS task is cancelled, unblocking audio buffers and resetting telephony VAD state immediately.
- **Clean Disconnects:** `WebSocketDisconnect` is caught cleanly, ensuring worker threads and audio sessions terminate without uncaught server exceptions.

### 6.3 Database Connection Pool (`asyncpg`) Resilience
- **Pool Bounds:** Configured via `DB_POOL_MIN` (default 2) and `DB_POOL_MAX` (default 30).
- **Query Timeout:** Configured with `command_timeout=30.0s` to prevent slow queries from starving pool connections.
- **Connection Recycling:** Sets `max_inactive_connection_lifetime=300.0s` and `max_queries=50000` to prevent stale connections across cloud NAT routers and avoid connection memory bloat.
- **Startup Reconnection Backoff:** `create_database_pool` retries transient startup connection failures up to 3 times with exponential backoff before failing closed safely.
- **Graceful Lifespan Teardown:** During container shutdown, `AuditLedger.close()` drains pending records to WAL (10s timeout), followed by `pool.close()`, guaranteeing zero lost records and zero leaked connections.

---

## 7. Zero Hardcoded Secrets & Verification

- **Codebase Cleanliness:** Automated regression test `test_zero_hardcoded_secrets_in_codebase` recursively scans all tracked Python, JavaScript, and HTML files against known secret signatures (Google AI Studio, Groq Cloud, OpenAI, GitHub, Slack tokens).
- **Strict Environment Segregation:** All sensitive keys (`GROQ_API_KEY`, `GEMINI_API_KEY`, `DB_PASSWORD`, `ADMIN_API_KEY`) are dynamically resolved from `os.environ` via `Settings.from_env()`.
- **Gitignore Protection:** Local `.env` files and deployment artifacts are strictly gitignored.

---

## 8. Automated Security & Reliability Test Suite

All security and reliability guarantees are verified via automated tests in `disha_core/tests/test_security_reliability.py`:

| Test Suite | Assertions Verified | Status |
|:---|:---|:---:|
| **PatientIsolationTests** | SQL queries strictly parameterized by patient ID; cache partitioned by (patient, query); zero cross-patient context leakage | **PASS** |
| **AuthenticationSecurityTests** | Missing/malformed/expired tokens rejected with HTTP 401; WebSocket closes with 4401 | **PASS** |
| **InputValidationTests** | Empty utterances, oversized payloads (>5000 chars), null bytes, and body > 2MB rejected (413/422) | **PASS** |
| **ZeroPHIScrubbingTests** | Tokens, passwords, API keys, Aadhaar, phone numbers, emails, and MRNs scrubbed from ledger and WAL | **PASS** |
| **RateLimiterTests** | Sliding window allows within quota, blocks bursts with HTTP 429 and Retry-After header | **PASS** |
| **SSECancellationTests** | Client disconnection during streaming handled gracefully without leaking resources | **PASS** |
| **ZeroSecretsScanTests** | Automated scan confirms zero hardcoded API keys or secrets in repository | **PASS** |
