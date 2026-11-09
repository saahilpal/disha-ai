# Disha AI — Endpoint Catalog & Interface Cartography

**Document Status:** Historical generated snapshot — not current runtime authority
**Source Code Baseline:** Earlier snapshot; validate against `disha_core/main.py` and `disha_core/routers/`

> For current chat, voice, and auth routes use [Runtime Components](../architecture/02_runtime_components.md). The route claims below are retained for historical context only.
**Authentication Standard:** Cryptographic SHA-256 Token Hashes (`patient_access_tokens`)

---

## 1. Catalog Summary Table

| Method | Path | Protocol | Authentication | Primary Responsibility |
|---|---|---|---|---|
| `GET` | `/health` | HTTP/1.1 | None | Liveness check (PostgreSQL connectivity) |
| `GET` | `/ready` | HTTP/1.1 | None | Readiness check (DB + Laya Classifier status) |
| `GET` | `/internal/classifier` | HTTP/1.1 | Bearer `ADMIN_API_KEY` (if set) | Diagnostic telemetry for Laya decision engine |
| `POST` | `/client-errors` | HTTP/1.1 | None | Client-side frontend error ingestion |
| `POST` | `/auth/register` | HTTP/1.1 | None | Patient onboarding, PEP initialization, 7-day diet generation |
| `POST` | `/auth/onboarding` | HTTP/1.1 | None | Alias to `/auth/register` |
| `POST` | `/auth/login` | HTTP/1.1 | None | Authenticate patient; issue bearer token |
| `GET` | `/patient/profile` | HTTP/1.1 | Bearer Token (`patient_access_tokens`) | Return patient vitals, PEP constraints, and today's diet |
| `POST` | `/chat` | HTTP/1.1 | Bearer Token (`patient_access_tokens`) | Synchronous text turn execution |
| `POST` | `/chat/stream` | HTTP/1.1 (SSE) | Bearer Token (`patient_access_tokens`) | Server-Sent Events streaming validated sentences |
| `WS` | `/voice` | WebSocket (WSS) | Bearer Token (Query, Header, or Handshake) | Full-duplex voice turn & barge-in telephony stream |
| `WS` | `/ws/conversation` | WebSocket (WSS) | Bearer Token (Query, Header, or Handshake) | Full-duplex voice/text conversation stream |

---

## 2. Endpoint Specifications (FastAPI Core)

### 2.1 `GET /health`
* **File:** `disha_core/main.py:231-241`
* **Auth:** None.
* **Description:** Verifies database pool health by executing `SELECT 1` on PostgreSQL.
* **Response 200 OK:**
  ```json
  {
    "ok": true,
    "database": true
  }
  ```
* **Response 503 Service Unavailable:**
  ```json
  {
    "detail": "Database unavailable"
  }
  ```

---

### 2.2 `GET /ready`
* **File:** `disha_core/main.py:243-264`
* **Auth:** None.
* **Description:** Kubernetes/orchestrator readiness probe. Checks both PostgreSQL connectivity and Laya classifier availability (`classifier.is_ready()`).
* **Response 200 OK:**
  ```json
  {
    "ok": true,
    "database": true,
    "classifier": true,
    "schema_version": "2026-11-07.v1"
  }
  ```
* **Response 503 Service Unavailable:**
  * When DB fails: `{"detail": "Database pool not initialized"}` or `{"detail": "Database connectivity failure"}`
  * When Laya fails: `{"detail": "Laya classifier not ready"}`

---

### 2.3 `GET /internal/classifier`
* **File:** `disha_core/main.py:266-276`
* **Auth:** Header `Authorization: Bearer <ADMIN_API_KEY>` (enforced if `ADMIN_API_KEY` is set in env).
* **Description:** Returns live telemetry, latency statistics, inference count, fallback rate, and circuit breaker state.
* **Response 200 OK:**
  ```json
  {
    "service": "laya_decision_engine",
    "schema_version": "2026-11-07.v1",
    "server_url": "in-process",
    "checkpoint": "convaiinnovations/laya",
    "device": "mps",
    "threads": 8,
    "min_confidence_gate": 0.40,
    "inference_count": 142,
    "fallback_count": 3,
    "last_latency_ms": 94.21,
    "circuit_breaker_open": false,
    "uptime_seconds": 1845.3
  }
  ```
* **Response 403 Forbidden:** `{"detail": "Admin authorization required"}`

---

### 2.4 `POST /client-errors`
* **File:** `disha_core/main.py:278-283`
* **Auth:** None.
* **Request Schema:**
  ```json
  {
    "message": "AudioContext suspended after user gesture",
    "source": "browser"
  }
  ```
* **Response 200 OK:**
  ```json
  {
    "logged": true
  }
  ```

---

### 2.5 `POST /auth/register` & `POST /auth/onboarding`
* **File:** `disha_core/main.py:285-400`
* **Auth:** None.
* **Request Schema (`OnboardingRequest`):**
  ```json
  {
    "name": "Priya Sharma",
    "email": "priya.sharma@example.com",
    "password": "securepassword123",
    "age": 38,
    "gender": "female",
    "height_cm": 165.0,
    "weight_kg": 68.0,
    "conditions": ["stage 1 hypertension"],
    "hypertension_stage": "stage 1",
    "gym_clearance": false,
    "activity_level": "light",
    "movement_restrictions": ["heavy lifting"],
    "dietary_preference": "Vegetarian",
    "health_goals": ["Reduce BP", "Weight loss"]
  }
  ```
* **Processing & Side Effects:**
  1. Validates email format (`@` and `.`) and minimum password length (>= 6 characters).
  2. Generates patient ID (`pt_<hex10>`) and raw bearer token (`pt_live_<hex32>`).
  3. Inserts into `patient_profiles` with SHA-256 password hash salted with `disha_salt_v1`.
  4. Stores token hash into `patient_access_tokens` (expires in 365 days).
  5. Computes Physical Exertion Protocol (`patient_pep`) permissions based on hypertension stage:
     - Stage 1/2 or no clearance: allowed modalities = `["brisk walking", "gentle yoga", "stretching", "breathing exercises", "light cycling"]`; restricted modalities = `["heavy deadlifts", "max weight lifting", "valsalva maneuver", "high-intensity sprinting"]`.
  6. Automatically populates 7 days (Monday through Sunday) of breakfast, lunch, and dinner records in `patient_diet_schedules`.
* **Response 200 OK:**
  ```json
  {
    "token": "pt_live_9a7f34c2b810...",
    "patient_id": "pt_8e4d2a1b9c",
    "patient_name": "Priya Sharma",
    "status": "authenticated",
    "pep": {
      "hypertension_stage": "stage 1",
      "gym_clearance": false,
      "allowed_modalities": ["brisk walking", "gentle yoga", "stretching", "breathing exercises", "light cycling"],
      "restricted_modalities": ["heavy deadlifts", "max weight lifting", "valsalva maneuver", "high-intensity sprinting"]
    }
  }
  ```
* **Response 400 Bad Request:** `{"detail": "Invalid email format"}` or `{"detail": "Password must be at least 6 characters"}`
* **Response 409 Conflict:** `{"detail": "An account with this email address already exists. Please sign in."}`

---

### 2.6 `POST /auth/login`
* **File:** `disha_core/main.py:402-456`
* **Auth:** None.
* **Request Schema (`LoginRequest`):**
  ```json
  {
    "email": "priya.sharma@example.com",
    "password": "securepassword123"
  }
  ```
* **Processing:**
  1. Hashes password using SHA-256 (`password + "disha_salt_v1"`).
  2. Queries `patient_profiles` for matching email and hash.
  3. If found, issues a fresh token in `patient_access_tokens` valid for 365 days.
  4. Supports fallback deterministic demo accounts: `cardiac` -> `pt_test_cardiac`, `diabetic` -> `pt_test_diabetic`, default -> `pt_test_01`.
* **Response 200 OK:**
  ```json
  {
    "token": "pt_live_4f6a1e8c9d0b...",
    "patient_id": "pt_8e4d2a1b9c",
    "patient_name": "Priya Sharma",
    "status": "authenticated"
  }
  ```
* **Response 400 Bad Request:** Invalid email or password length.

---

### 2.7 `GET /patient/profile`
* **File:** `disha_core/main.py:458-495`
* **Auth:** Header `Authorization: Bearer <token>`
* **Description:** Retrieves the authenticated patient's demographics, Physical Exertion Protocol (PEP), and current day's active dietary schedule.
* **Response 200 OK:**
  ```json
  {
    "patient_id": "pt_test_01",
    "patient_name": "Aarav Sharma",
    "day": "monday",
    "profile": {
      "name": "Aarav Sharma",
      "age": 35,
      "gender": "male",
      "height_cm": 172.0,
      "weight_kg": 74.0,
      "dietary_preference": "Vegetarian",
      "health_goals": ["Manage blood pressure", "Regular walking"]
    },
    "pep": {
      "hypertension_stage": "Stage 1",
      "gym_clearance": true,
      "allowed_modalities": ["gym", "walking"],
      "restricted_modalities": ["heavy_deadlifts", "valsalva_maneuver"]
    },
    "today_diet": {
      "dinner": "150g paneer bhurji, 2 multigrain rotis, cucumber salad (approx 420 kcal)"
    }
  }
  ```
* **Response 401 Unauthorized:** Invalid or expired token hash.

---

### 2.8 `POST /chat`
* **File:** `disha_core/main.py:499-514`
* **Auth:** Header `Authorization: Bearer <token>`
* **Request Schema (`TurnRequest`):**
  ```json
  {
    "text": "Aaj dinner mein kya prescribed hai?",
    "meal_type": "dinner"
  }
  ```
  *(Note: `meal_type` is automatically inferred from text if omitted, e.g. "nashta" -> "breakfast", "dopahar" -> "lunch", "raat" -> "dinner").*
* **Response 200 OK:**
  ```json
  {
    "response": "Aaj dinner mein aapke plan ke mutabik 150g paneer bhurji aur 2 multigrain rotis lijiye. Saath mein cucumber salad le sakte hain.",
    "status": "validated"
  }
  ```
* **Possible Status Codes in JSON Body:**
  - `"validated"`: Successfully grounded and passed through sentence assertions.
  - `"triggered:<category>"`: Caught by pre-turn emergency breaker.
  - `"rewritten:channel_boundary"`: Blocked WhatsApp/SMS claim.
  - `"rewritten:meal_not_found"`: Diet slot missing from DB.
  - `"provider_unavailable"`: LLM providers failed and fallback engaged.

---

### 2.9 `POST /chat/stream`
* **File:** `disha_core/main.py:516-544`
* **Auth:** Header `Authorization: Bearer <token>`
* **Protocol:** Server-Sent Events (`text/event-stream`), `Cache-Control: no-cache`
* **Stream Structure:**
  ```http
  data: {"sentence": "Aaj dinner mein aapke plan ke mutabik paneer bhurji lijiye."}

  data: {"sentence": "Saath mein 2 multigrain rotis aur salad shamil karein."}

  event: done
  data: {"status": "validated"}
  ```
* **Emergency Breaker Stream Response:**
  ```http
  data: {"sentence": "Yeh emergency ho sakti hai. Abhi 112 par call karein."}

  event: done
  data: {"status": "triggered:CARDIOVASCULAR"}
  ```

---

### 2.10 `WS /voice` & `WS /ws/conversation`
* **File:** `disha_core/main.py:546-688`
* **Auth Schemes Accepted:**
  1. URL Query parameter: `?token=<token>`
  2. Connection header: `Authorization: Bearer <token>`
  3. First incoming JSON frame: `{"type": "auth", "token": "<token>"}`
* **Frame Protocol:** Detailed in [WEBSOCKET_PROTOCOL.md](file:///Users/nitrousoxide/Code/disha%20ai/docs/map/WEBSOCKET_PROTOCOL.md).

---

## 3. Vercel Static-Preview Endpoints (`frontend/api/`)

These handlers do not connect to the Disha backend or its database. The static preview is not an authenticated application deployment:

### 3.1 `POST /api/auth/login` (`frontend/api/auth/login.js`)
* **Method:** `POST`, `OPTIONS`
* **Response:** `503 Service Unavailable`; the handler does not issue demo tokens.

### 3.2 `GET /api/patient/profile` (`frontend/api/patient/profile.js`)
* **Method:** `GET`, `OPTIONS`
* **Auth:** Bearer Token Header
* **Response:** `503 Service Unavailable`; configure the authenticated backend API for profile access.

### 3.3 `GET /api/health` (`frontend/api/health.js`)
* **Response:** `200 OK` means only that the static-preview function is reachable; it does not check backend or database health.

### 3.4 `GET /api/ready` (`frontend/api/ready.js`)
* **Response:** `503 Service Unavailable`; backend/model readiness is not available in the static preview.
