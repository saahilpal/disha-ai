# Disha AI — Critical Product, Voice & AI System Investigation Report

**Lead AI Systems & Product Engineer Investigation**  
**Repository:** `github.com/saahilpal/disha-ai`  
**Host Hardware:** Apple Silicon M5 (10-core, 16.0 GB Unified Memory, Metal GPU `mps:0`, macOS 27.2 arm64)  
**Date:** 2026-11-07  

---

## 1. Executive Summary & Critical Problems Ranked

| Priority | Defect / Failure Mode | User Experience Impact | Root Cause Domain | Primary Component Responsible |
|:---:|:---|:---|:---|:---|
| **P0** | **AI Obsessively Recommends Diet Plans & Guesses** | User says "I'm tired", AI immediately diagnoses it as dinner tofu/rice. Does not ask follow-ups. Ignores topic changes. | Context Injection & Prompt Architecture | `disha_core/models/schemas.py`, `context_builder.py`, `llm/client.py` |
| **P0** | **Stateless Single-Turn Amnesia** | AI forgets previous turns; each chat/voice turn is isolated. Cannot maintain natural conversation continuity. | LLM Orchestration | `disha_core/llm/client.py`, `routers/chat.py` |
| **P1** | **Voice Pipeline Breaking & Self-Cutting** | Spoken audio is chopped, cuts off mid-sentence, mic audio never reaches server, transcription fails. | Client Audio Architecture & VAD | `frontend/app.js` (`setupMicAnalyserAndVad`), `disha_core/voice.py` |
| **P1** | **Cluttered Clinical Dashboard in Chat** | Chat is squished next to medical cards displaying HTN Stage 2, Merkle hashes, BMI, PEP restrictions, and diet tables. | UI Architecture | `frontend/index.html` (`clinical-drawer`), `style.css` |
| **P2** | **Intrusive 112 SOS Buttons During Normal Chat** | Bright red 112 SOS buttons permanently pinned in header and stage dock, making normal chats alarming. | Frontend Layout & Safety Wiring | `frontend/index.html` (`emergency-quick-btn`, `emergency-alert-card`) |
| **P2** | **Rigid Keyword Overrides & Scripted Fallbacks** | Hardcoded regex triggers and intent overrides replace the LLM's natural conversational intelligence. | Pipeline Validator & Router | `disha_core/pipeline/validator.py`, `router.py` |

---

## 2. In-Depth Root-Cause Analysis (With Verified Code Evidence)

### 2.1 Why the AI Repeatedly Selects Diet Plans
**Verified Root Causes:**
1. **Schema Hardcoded Default (`meal_type = "dinner"`):**  
   In `disha_core/models/schemas.py` lines 25-28:
   ```python
   meal_type: Literal["breakfast", "lunch", "dinner"] = Field(default="dinner", description="Prescribed meal window")
   ```
   When a user sends *any* query (e.g. "I had a stressful day" or "I have a headache"), `meal_type` is missing from the payload and automatically defaults to `"dinner"`.

2. **Unconditional Context Injection on Every Turn:**  
   In `disha_core/services/chat_service.py` line 62 and `disha_core/engine/context_builder.py` lines 48-59:
   `build_patient_context` unconditionally executes `SELECT prescribed_items FROM patient_diet_schedules WHERE meal_type = 'dinner'`.

3. **XML Context Forced into User Prompt:**  
   In `disha_core/engine/context_builder.py` lines 85-88:
   ```python
   diet_xml = context.get("diet_slot_xml") or diet_slot_xml(context.get("meal_type", "dinner"), context.get("diet_items"))
   return f"<PATIENT_PROFILE>{pep_xml}{diet_xml}</PATIENT_PROFILE>{clinical_xml}"
   ```
   On every turn, the user's message is prefixed with:
   `<PATIENT_PROFILE><DIET_SLOT meal="dinner" status="FOUND">Grilled tofu with sauteed broccoli, bell peppers, and half cup brown rice (approx 380 kcal)</DIET_SLOT></PATIENT_PROFILE><USER_UTTERANCE>I feel tired</USER_UTTERANCE>`.

4. **Stateless LLM Invocation:**  
   In `disha_core/llm/client.py` lines 90-94:
   ```python
   "messages": [
       {"role": "system", "content": SYSTEM_PROMPT},
       {"role": "user", "content": prompt},
   ]
   ```
   The LLM receives **only one single turn with zero conversation history**. Seeing the dinner diet schedule as the only provided context, the model hallucinates an association between the user's symptom and their prescribed dinner.

---

### 2.2 Why the AI Keeps Guessing Instead of Asking
1. **Lack of Active Listening Directives:**  
   The current `SYSTEM_PROMPT` in `disha_core/llm/client.py` line 11 instructs Disha to be concise and respect PEP restrictions, but contains **zero guidelines on information gathering, asking follow-up questions, or acknowledging uncertainty**.
2. **Missing Information Classification:**  
   The system does not distinguish between:
   - User-asserted statements (e.g. "I haven't slept").
   - Verified EHR records (e.g. "Hypertension Stage 2").
   - Doctor prescriptions (e.g. "Metformin 500mg").
   - Model inferences vs. unknown parameters.
3. **Absence of Memory Extraction:**  
   Prior conversations are dumped into PostgreSQL audit logs (`audit_claim_ledger`), but are **never retrieved or summarized** for future turns.

---

### 2.3 Why Voice is Breaking and Interrupted
1. **Missing Audio Recording Pipeline:**  
   In `frontend/app.js` line 31:
   `mediaRecorder: null` is defined in state, but **is never initialized, started, or connected to `state.ws`**. The client opens the microphone strictly to feed an `AnalyserNode` for canvas animation. Real microphone audio bytes are **never streamed to the backend**.
2. **Fatal Acoustic Feedback Loop (Self-Interruption):**  
   In `frontend/app.js` lines 1583-1634:
   ```javascript
   const ENERGY_THRESHOLD = 20; // Out of 255
   ...
   if (avg > ENERGY_THRESHOLD) {
       if (state.isPlayingAudio) {
           onUserSpeechDetected(); // Kills audio and sends {"type": "interrupt"}
       }
   }
   ```
   When Disha speaks through the laptop speakers, the laptop microphone picks up Disha's own voice. Because `ENERGY_THRESHOLD = 20` is extremely low, **Disha's own speech trips the barge-in detector, stops playback, sends an interrupt to the server, and cuts herself off mid-sentence**.
3. **Asynchronous Audio Chunk Crackle:**  
   Incoming TTS audio buffers from WebSocket events are fed into `state.audioQueue` and played sequentially using raw `AudioBufferSourceNode` without jitter buffering or sample-rate alignment.

---

### 2.4 Why Emergency 112 Information Appears Unnecessarily
1. **Hardcoded UI Banners:**  
   In `frontend/index.html` line 74, `#emergency-112-btn` is permanently pinned in the top navigation header and within the telephony dock. It is visible 100% of the time, creating an alarming clinical atmosphere during casual wellness conversations.
2. **Robotic Breaker Over-Reaction:**  
   When an acute symptom is detected, the breaker returns a robotic boilerplate: `"Yeh emergency ho sakti hai. Abhi 112 par call karein."` rather than engaging as a calm, compassionate clinical triage assistant who checks if someone is with the patient and provides supportive guidance.

---

### 2.5 Why the UI is Cluttered
1. **Clinical Context Drawer:**  
   `frontend/index.html` lines 350-435 render a 4-card clinical dashboard directly adjacent to the chat:
   - Patient Clinical Baseline (Age, Height, Weight, BMI)
   - PEP Exercise Clearance (HTN Stage 2, Gym Clearance, Allowed/Restricted Modalities)
   - Today's Prescribed Diet Schedule (Breakfast, Lunch, Dinner tables)
   - Immutable Audit Ledger State (Merkle Root SHA-256 Hash, Sequence Number)
2. **Unified Chat and Call Screen Confusion:**  
   The chat interface is squashed at the bottom of an active telephony stage with canvas visualizers, call timers, and spectrum equalizers. Users cannot simply have a quiet, clean WhatsApp-like chat without feeling like they are on a live emergency dispatch call.

---

## 3. Local LLM Research, Comparison & Ranking

### 3.1 Hardware Reality on MacBook Air M5 (16GB Unified RAM)
- **Host RAM Budget:** 16.0 GB total.
  - macOS System & WindowServer: ~3.5 GB
  - Docker (Postgres, NGINX): ~1.0 GB
  - Working Application Headroom: **~11.5 GB available for inference & KV cache**.
- **Ollama Engine:** Runs native Metal GPU acceleration (`ggml-metal`) on Apple Silicon.

### 3.2 Model Comparison Matrix

| Model Name & Version | Parameter Count | Quantization | RAM Usage | Speed (Tokens/s) | Hinglish Fluency | Instruction & Follow-up | Context Window | Project Fit Rank |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Qwen 2.5 Instruct** (`qwen2.5:7b`) | 7.61 B | `Q4_K_M` | **4.7 GB** | **38–45 tok/s** | **9.4 / 10** | **9.5 / 10** | 32k – 128k | **#1 (Primary Conversational)** |
| **Gemma 2 Instruct** (`gemma2:9b`) | 9.24 B | `Q4_K_M` | **5.8 GB** | 28–34 tok/s | 7.8 / 10 | 9.0 / 10 | 8k | **#2 (Alternative)** |
| **Llama 3.1 Instruct** (`llama3.1:8b`) | 8.03 B | `Q4_K_M` | **4.9 GB** | 35–40 tok/s | 7.2 / 10 | 9.2 / 10 | 128k | **#3 (Strong English, Weaker Hinglish)** |
| **Llama 3.2** (`llama3.2:3b`) | 3.21 B | `Q4_K_M` | **2.0 GB** | 65–75 tok/s | **4.1 / 10 (Gibberish)** | 6.5 / 10 | 128k | **#5 (Unsuitable for Hinglish)** |
| **Nomic Embed Text** (`nomic-embed-text`) | 137 M | `F16` | **0.27 GB** | > 500 docs/s | N/A (Semantic) | N/A | 8k | **#1 (Local Embedding Model)** |

---

## 4. Recommended Target Architecture

### 4.1 Two Distinct User Experiences

1. **Mode A — WhatsApp-Style Chat Interface:**
   - Dedicated clean chat canvas with soft message bubbles.
   - Header contains: Patient Avatar, "Disha Health Coach", connection indicator, and a prominent Call button.
   - Clean message input bar with mic and send button.
   - **Zero dashboard widgets, zero clinical cards, zero Merkle hashes.**
2. **Mode B — Fullscreen Dedicated Calling Experience:**
   - Triggered *only* when the user clicks the Call button.
   - The chat is hidden; the screen transitions to a clean, focused calling view:
     - Calming acoustic stethoscope breathing indicator.
     - Spoken subtitles of Disha's speech.
     - Controls: Mute Microphone, Speaker, End Call.
   - **Call-to-Chat Continuity:** When the call ends, the audio transcript turns are automatically saved into the chat history. The user returns to the WhatsApp chat with the full conversation preserved.
3. **Mode C — Simple Patient Profile Section:**
   - Accessible via a discrete profile icon in the top right.
   - Allows viewing and editing: Name, Age, Gender, Height, Weight, Diet Preference, Health Goals.
   - Displays verified clinical constraints (PEP permissions, hypertension staging) without dominating the chat.

---

### 4.2 Intelligent Context Decoupling (Fixing the Diet Fixation)

1. **Rule 1 (Context Isolation):**  
   If the user does *not* ask about meals, food, or nutrition, `DIET_SLOT` is omitted from the prompt.
2. **Rule 2 (Multi-Turn History):**  
   The last 6 conversation turns (`role: "user"` and `role: "assistant"`) are passed to the LLM on every turn.
3. **Rule 3 (Active Listening):**  
   The system prompt explicitly commands:
   > *"If the user shares a symptom or feeling (such as fatigue or headache) without enough context, do NOT assume a cause. Ask a natural, caring follow-up question first."*

---

### 4.3 Intelligent Groq Reviewer vs. Deterministic Gate (Trade-Off Analysis)

- **In-flight (Sync):** Deterministic safety breaker (<1ms) guarantees zero red-flag escapes and blocks Schedule H/X drug requests without adding latency.
- **Post-flight (Async / Low-Confidence):** If model confidence is low, or if the user asks a complex medication query, Groq (`qwen-3.8-27b`) reviews the response in the background, logging any clinical drift into `disha_core/classifier/review_queue.py`.

---

### 4.4 Cloudflare Tunnel & Hybrid Local/Cloud Architecture

1. **Local Development:** Backend connects to `http://127.0.0.1:11434` (Ollama) directly.
2. **Remote Deployed Access:** Local Ollama is exposed via Cloudflare Tunnel behind an `Authorization: Bearer <SECRET_TOKEN>` header.
3. **Failover Invariant:** If the laptop is closed or times out (>3.0s), the backend automatically falls back to Groq Cloud or Gemini Flash without interrupting the user.

---

## 5. Practical Phased Implementation Plan

- **Phase 1: Conversation Intelligence & Context Decoupling** (Remove schema defaults, implement multi-turn buffer, overhaul system prompt).
- **Phase 2: UI/UX Simplification** (WhatsApp-like chat, dedicated call mode, profile view, removal of dashboard clutter).
- **Phase 3: Voice Pipeline & Echo-Safe VAD** (Real client-side audio streaming, fix self-interruption feedback loop, call-to-chat continuity).
- **Phase 4: Local Model (Ollama Qwen 2.5 7B) & Provider Cascade** (Ollama client, authenticated Cloudflare Tunnel remote access, Groq/Gemini cascade).
- **Phase 5: Verification & Testing** (Automated scenarios A through H).

