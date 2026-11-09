# Disha AI — Frame-by-Frame WebSocket Protocol Specification

**Document Status:** Historical generated snapshot — not current runtime authority
**Target Endpoints:** `/ws/conversation` and `/voice`  
**Source Code Baseline:** `disha_core/main.py:546-688`, `disha_core/voice.py:96-135`, `frontend/app.js:1054-1248`

> The protocol and streaming claims below are not current runtime guarantees. Use [Voice Pipeline](../VOICE_PIPELINE.md) for the implemented message contract.

---

## 1. Protocol Architecture & Connection Lifecycle

The Disha AI Telephony WebSocket protocol manages bidirectional full-duplex communication between the patient's browser and the FastAPI Core backend orchestrator. It supports interleaved text and binary audio streaming, stateful barge-in interruption, and non-blocking audit logging.

```mermaid
stateDiagram-v2
    [*] --> CONNECTING: Client opens WSS connection
    CONNECTING --> AUTHENTICATING: Check query / header / auth frame
    AUTHENTICATING --> CLOSED_4401: Token missing or invalid
    AUTHENTICATING --> STANDBY_LISTENING: Token verified (pt_id resolved)

    state STANDBY_LISTENING {
        [*] --> Idle
        Idle --> ReceivingAudio: Binary audio frame (< 10MB)
        Idle --> ReceivingText: Inbound JSON text payload
    }

    ReceivingAudio --> Transcribing: Send to Groq Whisper
    Transcribing --> Routing_Grounding: Breaker check and Context lookup
    ReceivingText --> Routing_Grounding: Breaker check and Context lookup

    state ACTIVE_TURN_GENERATION {
        Routing_Grounding --> StreamingLLM: DualProviderClient (Groq/Gemini)
        StreamingLLM --> SentenceBuffering: Feed token chunks
        SentenceBuffering --> ValidatingSentence: Punctuation boundary reached
        ValidatingSentence --> SynthesizingTTS: validate_sentence passed
        SynthesizingTTS --> StreamingAudioToClient: Edge-TTS binary packets
    }

    ACTIVE_TURN_GENERATION --> INTERRUPTING: Client dispatches interrupt frame
    INTERRUPTING --> STANDBY_LISTENING: Cancel tasks, drain playback, emit interrupted frame

    ACTIVE_TURN_GENERATION --> TURN_COMPLETED: 3 sentences emitted or stream closed
    TURN_COMPLETED --> STANDBY_LISTENING: Emit done frame, enqueue Merkle audit

    STANDBY_LISTENING --> [*]: Client disconnect or socket close
```

---

## 2. Authentication Handshake Schemes

Authentication is evaluated immediately upon socket acceptance (`disha_core/main.py:549-563`). The server accepts credentials through three distinct channels:

### Scheme A: URL Query Parameter (Preferred by Native WebSocket API)
```http
GET /ws/conversation?token=pt_live_9a7f34c2b810... HTTP/1.1
Host: 127.0.0.1:8080
Upgrade: websocket
Connection: Upgrade
```

### Scheme B: HTTP Authorization Header
```http
GET /ws/conversation HTTP/1.1
Host: 127.0.0.1:8080
Upgrade: websocket
Connection: Upgrade
Authorization: Bearer pt_live_9a7f34c2b810...
```

### Scheme C: Immediate In-Band JSON Auth Frame
If no token is supplied in the URL or headers, the server suspends turn processing for up to `5.0` seconds waiting for an initial JSON handshake frame:
```json
{
  "type": "auth",
  "token": "pt_live_9a7f34c2b810..."
}
```

* **Authentication Success:** Server acknowledges with an authentication confirmation frame:
  ```json
  {
    "type": "authenticated",
    "patient_id": "pt_test_01"
  }
  ```
* **Authentication Failure:** If the token hash is invalid, unverified in `patient_access_tokens`, or times out after 5.0 seconds, the socket closes with code `4401`.

---

## 3. Frame Catalog & Schema Definitions

### 3.1 Client-to-Server Frames (Inbound)

| Frame Format | Type Field | Payload Schema | Maximum Size | Behavioral Effect |
|---|---|---|---|---|
| **Binary** | `N/A` | Raw audio bytes (WebM Opus / PCM) | 10 MB (`10 * 1024 * 1024`) | Initiates ASR transcription via Groq Whisper and triggers full turn execution. |
| **JSON** | `"text"` | `{"type": "text", "text": "..."}` | 5,000 chars | Bypasses ASR; routes raw user text directly through emergency breaker and retrieval engine. |
| **JSON** | `"audio"` | `{"type": "audio", "data": "<base64>"}` | 10 MB (decoded) | Decodes base64 string to audio bytes and routes to Groq Whisper. |
| **JSON** | `"interrupt"` | `{"type": "interrupt"}` (or `"interrupted"`, `"barge_in"`) | < 100 bytes | **Barge-In:** Immediately cancels active generation and TTS stream tasks. |
| **JSON** | `"auth"` | `{"type": "auth", "token": "..."}` | 256 bytes | Handshake frame for late authentication. |

#### Inbound JSON Frame Samples:
```json
// 1. Text Turn Submission
{
  "type": "text",
  "text": "Aaj subah ke nashte mein kya prescribed hai?"
}

// 2. Real-Time Barge-In Interruption
{
  "type": "interrupt"
}

// 3. Base64 Audio Chunk Submission
{
  "type": "audio",
  "data": "GkXfo59ChoEBQveBAULygQ88t..."
}
```

---

### 3.2 Server-to-Client Frames (Outbound)

| Frame Format | Type Field | Payload Schema | Behavioral Effect on Client |
|---|---|---|---|
| **JSON** | `"authenticated"` | `{"type": "authenticated", "patient_id": "..."}` | Confirms verified session; client transitions UI from connecting to active. |
| **JSON** | `"transcript"` | `{"type": "transcript", "text": "..."}` | Displays user utterance in the conversation stream; switches status to `processing`. |
| **JSON** | `"sentence"` | `{"type": "sentence", "text": "..."}` | Displays validated assistant response sentence; switches status to `speaking`. |
| **Binary** | `N/A` | MP3 audio stream chunk | Direct ingestion into Web Audio API `AudioContext.decodeAudioData()` queue for speaker playback. |
| **JSON** | `"interrupted"` | `{"type": "interrupted"}` | Confirms barge-in; client drains local audio queue and stops speaker playback. |
| **JSON** | `"done"` | `{"type": "done", "status": "validated", "merkle_hash": "..."}` | Signals turn completion; client switches status from `speaking` to `listening`. |
| **JSON** | `"error"` | `{"type": "error", "message": "..."}` | Informs patient of transient failure without breaking connection. |

#### Outbound Frame Samples:
```json
// 1. Real-Time Transcription Confirmation
{
  "type": "transcript",
  "text": "Aaj dinner mein kya khana hai?"
}

// 2. Validated Sentence Emission
{
  "type": "sentence",
  "text": "Aaj dinner mein aapke plan ke mutabik 150g paneer bhurji aur 2 multigrain rotis lijiye."
}

// 3. Barge-In Interruption Acknowledgment
{
  "type": "interrupted"
}

// 4. Turn Completion Marker with Status
{
  "type": "done",
  "status": "validated",
  "merkle_hash": "4a58b29e0f6c12ba8314..."
}

// 5. Transient Error Notice
{
  "type": "error",
  "message": "Voice turn unavailable; please try again."
}
```

---

## 4. Barge-In & Interruption Lifecycle

Disha AI guarantees responsive speech interruption using a three-phase barge-in loop:

```
[ Active Synthesis: Sentence 2 streaming audio ]
                      │
                      ▼
[ 1. Client VAD Detection ]
  - Web Audio AnalyserNode detects microphone energy > 20
  - Client calls stopAudioPlayback(): drains local audioQueue, pauses audio context
  - Client sends WebSocket frame: {"type": "interrupt"}
                      │
                      ▼
[ 2. Server-Side Cancellation (disha_core/main.py:577-586) ]
  - cancel_active_turn() executes:
      if turn_task is not None and not turn_task.done():
          turn_task.cancel()
          await turn_task  # suppress asyncio.CancelledError
      await session.barge_in()  # cancels active Edge-TTS asyncio Task
  - Server sends: {"type": "interrupted"}
                      │
                      ▼
[ 3. Resumption of Standby ]
  - Client receives {"type": "interrupted"}
  - UI visualizer transitions from active-speaking to active-listening
  - Socket remains open, fully primed for the patient's new utterance
```

---

## 5. WebSocket Close Codes & Error Handling

The server enforces standard and clinical-specific WebSocket close codes:

| Code | Reason String | Trigger Condition | Recommended Client Action |
|---|---|---|---|
| `1000` | Normal Closure | Patient clicked "End Call" or closed browser tab. | Do not reconnect. Return to dashboard. |
| `1008` | Policy Violation | Client violated protocol invariants or security constraints. | Report security alert to patient. |
| `1009` | Audio turn exceeds 10 MB | Inbound audio frame exceeds `MAX_VOICE_TURN_BYTES` (`10485760` bytes). | Inform patient that audio chunk was too long; re-prompt. |
| `4401` | Unauthorized | Bearer token hash missing, revoked, expired, or invalid. | Transition to sign-in view; prompt user to re-authenticate. |

---

## 6. Client Reconnection & Backoff Policy

Implemented in `frontend/app.js:1124-1143` (`scheduleWebSocketReconnect`):
* **Max Attempts:** 5 consecutive retries before terminating consultation.
* **Backoff Algorithm:** Exponential backoff with random jitter:
  $$\text{delay} = \min(16000, 1000 \times 2^{\text{attempts}}) + \text{Uniform}(0, 500)\,\text{ms}$$
* **Exemptions:** Reconnection is immediately aborted if the close code is `1000`, `1008`, or `4401`.

---

## 7. Web Browser Client Audio Streaming Format & Lifecycle

Disha AI's telephony audio pipeline executes entirely within modern web browsers using standard W3C Web APIs without requiring any native plugins, native OS binaries, or browser extensions.

### 7.1 Acoustic Ingestion & Web Audio Graph
Implemented in `frontend/app.js:1257-1323, 1454-1557`:
1. **User Gesture Initialization:** To satisfy browser autoplay security policies, `AudioContext` is created or resumed immediately upon user interaction (clicking "Start Voice Consultation"):
   ```javascript
   if (!state.audioContext) state.audioContext = new (window.AudioContext || window.webkitAudioContext)();
   if (state.audioContext.state === 'suspended') await state.audioContext.resume();
   ```
2. **Microphone Capture:** Accesses user hardware via `navigator.mediaDevices.getUserMedia({ audio: true })`.
3. **Audio Routing Graph:**
   ```
   [ MediaStream (Microphone) ]
                │
                ▼
   [ MediaStreamAudioSourceNode ]
                │
                ▼
   [ AnalyserNode (fftSize=64, smoothingTimeConstant=0.3) ]
         │                                    │
         ▼                                    ▼
   [ 24-Bar Spectrum UI ]             [ VAD Energy Analysis ]
   (requestAnimationFrame)           (avg amplitude > 20)
   ```
4. **Screen Wake Lock:** Prevents screen dimming and tab throttling during clinical consultations via `navigator.wakeLock.request('screen')`.

### 7.2 Inbound Audio Payload Structure
The web client dispatches voice input to the FastAPI backend over the active WebSocket:
* **Audio Format:** Binary WebM Opus or 16-bit linear PCM encoded as a binary frame or base64 JSON payload:
  ```json
  {
    "type": "audio",
    "data": "<base64_encoded_webm_or_pcm>"
  }
  ```
* **Payload Boundary:** Maximum 10 MB per turn (`MAX_VOICE_TURN_BYTES = 10 * 1024 * 1024`). Turns exceeding this limit are terminated with close code `1009`.

### 7.3 Outbound Audio Reception, Decoding & Playback Lifecycle
Implemented in `frontend/app.js:1579-1675`:
1. **Frame Reception:** Server yields binary MP3 audio packets generated sentence-by-sentence via Microsoft Edge-TTS (`stream_edge_tts`).
2. **Queue Management:** Incoming binary frames (`ArrayBuffer` or `Blob.arrayBuffer()`) are pushed to `state.audioQueue`.
3. **Hardware Decoding:** If `isPlayingAudio` is false, `playNextAudio()` dequeues the first buffer and decodes it directly via the browser's hardware-accelerated audio subsystem:
   ```javascript
   const audioBuffer = await state.audioContext.decodeAudioData(buffer.slice(0));
   ```
4. **Playback & Telephony Visualization Graph:**
   ```
   [ AudioBufferSourceNode (Decoded PCM) ]
                │
                ▼
   [ TTS AnalyserNode (fftSize=64) ] ──> [ Acoustic Stethoscope Canvas ]
                │
                ▼
   [ AudioContext.destination (Speakers / Headphones) ]
   ```
5. **Seamless Chaining:** The `source.onended` event triggers `playNextAudio()` to sequentially play subsequent sentences without audible jitter or latency gaps.

### 7.4 Client-Side Real-Time VAD & Barge-In Hook
Implemented in `frontend/app.js:1529-1577`:
1. **Continuous Energy Sampling:** Every visualizer frame computes the average amplitude across frequency bins:
   $$\text{energy} = \frac{1}{N} \sum_{i=0}^{N-1} \text{dataArray}[i]$$
2. **Interruption Trigger:** If `energy > 20` (`ENERGY_THRESHOLD`) while `state.isPlayingAudio == true`:
   - Immediately invokes `stopAudioPlayback()`: drains `audioQueue`, calls `source.stop(0)`, and pauses speaker playback.
   - Dispatches barge-in WebSocket frame: `{"type": "interrupt"}`.
   - Updates UI telephony status to `interrupted` and resets spectrum bars.
3. **Server Cancellation:** The FastAPI backend catches `{"type": "interrupt"}` (`main.py:661-664`), immediately cancels `turn_task` and the active Edge-TTS synthesis task, and responds with `{"type": "interrupted"}`.

### 7.5 Teardown & Resource Disposal
Upon consultation termination (`endCall()` or browser `beforeunload` / `pagehide` events):
* Media tracks stopped: `state.micStream.getTracks().forEach(t => t.stop())`.
* Web Audio nodes disconnected: `sourceNode.disconnect()`, `analyserNode.disconnect()`.
* Animation frame cancelled: `cancelAnimationFrame(state.spectrumAnimId)`.
* Screen Wake Lock released: `state.wakeLock.release()`.
* `AudioContext` closed: `state.audioContext.close()`.
