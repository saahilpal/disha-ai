# Disha AI — Feature Inventory & Architectural Audit Baseline

**Execution Date:** 2026-11-07  
**Branch:** `redesign/v2`  
**Audit Standard:** Zero-Trust Empirical Verification

---

## 1. Laya Decision Engine Audit Map

| Component / Path | Question / Primitive | What the Answer Drives | Status | Evidence / Code Location |
|:---|:---|:---|:---:|:---|
| `disha_core/pipeline/router.py` | Intent Classification | Classifies turn as `MEAL_QUERY`, `SYMPTOM_COMPLAINT`, `GENERAL_COACHING` | **STUBBED (FAKE)** | Uses regex `RuleIntentClassifier` with keywords (`dinner`, `breakfast`, `dard`, `bloating`). |
| `disha_core/pipeline/router.py` | `OnnxIntentClassifier` | Local ONNX runtime intent classification | **DEAD / UNUSED** | Class exists as empty boilerplate requiring manual `encode` / `decode` functions; never instantiated in production. |
| `disha_core/main.py:165` | `app.state.router` | Intent router instance on application state | **STUBBED (FAKE)** | Instantiates `IntentRouter()` with default `RuleIntentClassifier()`. No Laya code or package is loaded. |
| `disha_core/voice.py` | Speech Intent Routing | Audio turn intent triage | **MISSING** | `voice.py` does not reference or call `router` or any intent classification model. |
| Live Dependencies | `laya` package | Python library from `NandhaKishorM/laya` | **MISSING** | `importlib.util.find_spec('laya')` returns `False`. Neither `laya` nor `laya[serve]` is installed. |
| `/ready` endpoint | Health & Dependency Gate | Checks PostgreSQL and Laya model readiness | **MISSING** | Endpoint does not exist in `disha_core/main.py`. |
| `/internal/classifier` | Model Telemetry | Inspects loaded checkpoint, device, threads, counter, last latency | **MISSING** | Endpoint does not exist in `disha_core/main.py`. |

### Summary of Laya Usage
* **Verdict:** **100% MISSING / STUBBED**.
* The codebase previously claimed *"Laya AI Non-Autoregressive ONNX (~33ms ONNX)"* in `docs/HLD.md`, but the live runtime actually executes a simple regex (`RuleIntentClassifier`).
* **Prescribed Fix:** Wire `laya` as an isolated microservice (`laya-serve` on internal port, `POST /v1/systemone`) and as an in-process fallback adapter using model `"multilingual"`. Question schemas versioned in `disha_core/classifier/schemas.py`.

---

## 2. API & Endpoint Inventory

| Endpoint | Method | Expected Purpose | Production Status | Empirical Proof / Observation |
|:---|:---:|:---|:---:|:---|
| `/` | GET | Clinical consultation web client | **WORKING (Local)** / **BROKEN (Vercel)** | Served by NGINX & FastAPI on `:8080`. On Vercel, static HTML is served but API routes 404. |
| `/health` | GET | Database healthcheck | **WORKING** | Returns `{"ok":true,"database":true}` with HTTP 200. |
| `/ready` | GET | Readiness check (DB + Laya) | **MISSING** | Returns 404. Must check both DB pool and Laya socket. |
| `/auth/login` | POST | Authenticate patient session | **PARTIAL / FAKE FALLBACK** | Queries PostgreSQL for user password hash; if not found, falls back to hardcoded mock tokens (`pt_test_01`, `pt_test_cardiac`). |
| `/auth/register` | POST | Complete patient intake | **WORKING** | Inserts patient vitals into `patient_profiles`, `patient_pep`, and `patient_diet_schedules`. |
| `/patient/profile` | GET | Retrieve patient baseline & diet | **WORKING** | Queries `patient_profiles`, `patient_pep`, and `patient_diet_schedules`. |
| `/chat` | POST | Synchronous textual turn | **WORKING** | Runs Aho-Corasick breaker, retrieves diet context, generates LLM response, asserts safety invariants. |
| `/chat/stream` | POST | SSE streamed textual turn | **WORKING** | Streams individual sentences as SSE events. |
| `/ws/conversation` | WS | Real-time voice/text WebSocket | **WORKING** | Handles audio/text frames, Groq Whisper STT, Edge-TTS audio streaming, barge-in cancellation. |
| `/internal/classifier` | GET | Classifier diagnostics | **MISSING** | Returns 404. Must be implemented for admin model observability. |
| `/client-errors` | POST | Client error logging | **MISSING** | Client errors in browser currently only output to `console.error`. |

---

## 3. Frontend & UI Control Inventory

| UI Element / Feature | Location | Claimed Function | Current Real Status | Defect / Failure Mode |
|:---|:---|:---|:---:|:---|
| "Sign In" Tab | `index.html` | Switch to login mode | **WORKING** | Accessible tab switching, resets form state. |
| "New Patient Intake" Tab | `index.html` | Switch to clinical intake | **WORKING** | Collects vitals, BMI, PEP conditions, goals. |
| Login Form Submission | `index.html` | Authenticate patient | **WORKING** | Submits to `/auth/login`, saves token to `localStorage`. |
| Intake Form Submission | `index.html` | Save profile to DB | **WORKING** | Submits to `/auth/register`, updates drawer data. |
| Start Call Button | Telephony Dock | Connect audio & stream | **WORKING (Local)** | Connects to `ws://127.0.0.1:8080/ws/conversation`. |
| Mute Mic Button | Telephony Dock | Toggle microphone stream | **WORKING** | Toggles `state.micStream.getAudioTracks()[0].enabled`. |
| End Call Button | Telephony Dock | Terminate call session | **WORKING** | Cleans up audio nodes, stops timer, sends close frame. |
| Speaker Toggle Button | Telephony Dock | Toggle speaker output | **WORKING** | Mutes HTMLAudioElement queue. |
| Text Chat Fallback Input | Chat Container | Send text over WebSocket | **WORKING** | Sends JSON `{"type": "text", "text": "..."}` over WS. |
| Prescribed Diet Drawer | Aside Panel | Display 7-day schedule | **WORKING** | Renders breakfast, lunch, and dinner from DB. |
| Merkle Audit Trail Chip | Aside Panel | Show current ledger hash | **WORKING** | Displays SHA-256 hash formatted in monospace. |
| Settings Page / Modal | Navigation | Mic & speaker device picker | **MISSING / DEAD** | No device picker exists; relies on browser default audio device. |
| Summary & Transcript Page | Navigation | Post-call summary & export | **MISSING / DEAD** | No post-call export or summary screen exists. Call ends back on idle. |
| Privacy & Consent Notice | Footer / Modal | Explicit medical disclaimer | **PARTIAL** | Text note present in header/footer, but no explicit modal consent gate. |
| Server-Waking / Offline Banner | Header | Alert user if VM sleeping | **MISSING** | No offline detection banner or reconnect countdown modal. |

---

## 4. Constraint Register (C1–C16)

| ID | Type | Constraint Name | Implementing Code / Artifact | Status |
|:---|:---:|:---|:---|:---:|
| **C1** | HARD | Pre-Turn Emergency Deflection | `disha_core/pipeline/breaker.py` (`EmergencyBreaker`) | **IMPLEMENTED** |
| **C2** | HARD | Zero Unsupported Diagnoses | `disha_core/pipeline/validator.py` (`SentenceValidator`) | **IMPLEMENTED** |
| **C3** | HARD | Zero Prescription Alteration | `disha_core/pipeline/validator.py` (`SentenceValidator`) | **IMPLEMENTED** |
| **C4** | HARD | Closed-Domain Meal Grounding | `disha_core/main.py:136`, `validator.py` | **IMPLEMENTED** |
| **C5** | HARD | PEP Mobility & Clearance Boundary | `disha_core/pipeline/validator.py` (`PEP_REPLACEMENT`) | **IMPLEMENTED** |
| **C6** | HARD | Mandatory Clinical Remedy Assertion | `disha_core/engine/context_builder.py` | **IMPLEMENTED** |
| **C7** | HARD | Channel & Delivery Boundary | `disha_core/pipeline/validator.py` (`CHANNEL_RE`) | **IMPLEMENTED** |
| **C8** | HARD | Authorized Commercial Pricing | `disha_core/pipeline/validator.py` (`PRICE_RE`) | **IMPLEMENTED** |
| **C9** | HARD | Persona Invariant ("AI health coach") | `disha_core/pipeline/validator.py` (`IDENTITY_RE`) | **IMPLEMENTED** |
| **C10** | HARD | Audit Provenance (Merkle Hash) | `disha_core/compliance/ledger.py` | **IMPLEMENTED** |
| **C11** | HARD | Multi-Tenant Data Isolation | `disha_core/engine/retriever.py` | **IMPLEMENTED** |
| **C12** | HARD | Clinical Stance Length (<50 words) | `disha_core/db/schema.sql` (`CHECK constraint`) | **IMPLEMENTED** |
| **C13** | SOFT | Latency Budget (<35ms Core Overhead) | `audit/suites/latency_profiler.py` | **IMPLEMENTED** |
| **C14** | SOFT | Spoken Cadence & Plain TTS | `disha_core/pipeline/validator.py:sanitize_for_tts` | **IMPLEMENTED** |
| **C15** | SOFT | Dual-Provider LLM Failover | `disha_core/llm/client.py` (`DualProviderClient`) | **IMPLEMENTED** |
| **C16** | NON-GOAL | No Autonomous Clinical Prescriptions | `disha_core/llm/client.py` (`SYSTEM_PROMPT`) | **IMPLEMENTED** |

---

## 5. Baseline UX Defect Register

1. **Architecture Duplication:**
   * `frontend/` and `disha_core/frontend/` are parallel copies synced manually by scripts, leading to drift risk and testing divergence.
   * `app.js` is a 1,400-line monolithic JavaScript file with tightly coupled state, audio rendering, DOM querying, and WebSocket logic.
   * `style.css` is a 1,500-line monolithic CSS stylesheet without modular design token imports or scoped component structures.
2. **Missing Product Information Architecture:**
   * No dedicated multi-view SPA router. All screens (Login, Intake, Telephony Stage, Clinical Drawer) are packed into a single scrollable container toggled by hidden CSS classes.
   * Missing Post-Call Summary screen with clinical transcript download (PDF/JSON/Text).
   * Missing Audio Input/Output Device Picker (crucial for patients on Bluetooth headsets or mobile speakerphone).
   * Missing explicit Medical Consent modal gate before starting the microphone stream.
3. **Visual Hierarchy & Creative Direction:**
   * Flat typography without clear typographic rhythm or expressive editorial clinical typography.
   * Generic card containers without intentional depth layers or purposeful motion.
   * Call screen lacks dedicated focus mode (when on a call, background forms and intake inputs still clutter the viewport).
4. **Vercel & Production Ingress:**
   * Deploying `frontend/` alone to Vercel fails on `/auth/login` because it lacks backend API routing.
   * In Docker, port `:8080` works locally, but there is no public HTTPS deployment or TLS certificate configuration for remote mobile testing.

