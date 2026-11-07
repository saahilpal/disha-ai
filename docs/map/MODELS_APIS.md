# Disha AI — Models, APIs & Token Quota Cartography

**Document Status:** Production Authoritative  
**Source Code Baseline:** `disha_core/llm/client.py`, `disha_core/voice.py`, `disha_core/classifier/adapter.py`  
**Cost Target:** Sustainable $0 Free-Tier Stack with Enterprise Fallbacks

---

## 1. Complete Model Inventory

| Capability | Model Identifier | Provider / Engine | Context Window | Max Output Tokens | Measured Latency (P50) | Primary Responsibility |
|---|---|---|---|---|---|---|
| **Voice STT** | `whisper-large-v3-turbo` | Groq Cloud | 25 MB Audio | Transcribed Text | ~220ms | Low-latency audio-to-text transcription |
| **Primary LLM** | `openai/gpt-oss-120b` | Groq Cloud | 131,072 tokens | 256 tokens | ~280ms First Token | Empathetic Hinglish dialogue generation |
| **Fallback LLM** | `gemini-3.6-flash` | Google Gemini | 1,048,576 tokens | 256 tokens | ~340ms First Token | High-reliability failover generation |
| **Voice TTS** | `hi-IN-SwaraNeural`<br/>`en-IN-NeerjaNeural` | Microsoft Edge-TTS | Unlimited Text | Streaming MP3 | ~140ms First Chunk | Natural Hindi and Indian English audio synthesis |
| **System 1 Triage** | `convaiinnovations/laya` | Laya (421M ModernBERT) | 8,192 tokens | Structured Answers | ~35ms (Serve) / ~98ms (Local) | Non-autoregressive intent & emergency scoring |
| **Client VAD** | Web Audio AnalyserNode | Client Browser | 64 FFT Bins | Real-time Energy (0-255) | < 16ms (1 Frame) | Speech activity detection & barge-in |

---

## 2. Model Specifications & Configuration Details

### 2.1 Speech-to-Text: Groq Whisper Large v3 Turbo
* **Model ID:** `whisper-large-v3-turbo`
* **API Endpoint:** `https://api.groq.com/openai/v1/audio/transcriptions`
* **Audio Constraints:** Maximum 10 MB per turn (`MAX_VOICE_TURN_BYTES = 10 * 1024 * 1024`). Supported formats: WebM Opus, WAV, MP3.
* **Rate Limits (Groq Free Tier):**
  * **RPM:** 20 Requests Per Minute
  * **RPD:** 2,000 Requests Per Day
  * **Audio Quota:** 7,200 Audio Seconds Per Hour
* **Fail-Closed Gate:** Gated by `GROQ_HEALTH_DATA_PROCESSING_APPROVED="true"`.
* **Language Support:** Native multilingual transcription; accurately transcribes colloquial Hinglish, Devanagari Hindi, and Indian English idioms.

---

### 2.2 Primary LLM: Groq `openai/gpt-oss-120b`
* **Model ID:** `openai/gpt-oss-120b`
* **API Endpoint:** `https://api.groq.com/openai/v1/chat/completions`
* **Retired ID Mapping:** The codebase automatically maps retired `llama-3.3-70b-versatile` to `openai/gpt-oss-120b` (`client.py:15`).
* **Generation Parameters:**
  * `temperature: 0.2` (Low entropy to prevent clinical hallucinations)
  * `max_completion_tokens: 256` (Concise 2-3 sentence conversational turns)
  * `stream: true` (Immediate Server-Sent Events token streaming)
* **Rate Limits (Groq Developer Tier):**
  * **RPM:** 30 Requests Per Minute
  * **RPD:** 1,000 Requests Per Day
  * **TPM:** 6,000 Tokens Per Minute
* **Prompt Token Budget:** Average prompt consumes `<380` tokens (System prompt ~110 tokens, XML context ~180 tokens, user utterance ~90 tokens).

---

### 2.3 Fallback LLM: Google `gemini-3.6-flash`
* **Model ID:** `gemini-3.6-flash`
* **API Endpoint:** `https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:streamGenerateContent?alt=sse`
* **Retired ID Mapping:** The codebase automatically maps retired `gemini-2.0-flash` to `gemini-3.6-flash` (`client.py:16`).
* **Generation Parameters:**
  * `temperature: 0.2`
  * `maxOutputTokens: 256`
* **Failover Circuit Breaker:**
  * `threshold: 2` consecutive transient failures (HTTP 429, 500, 502, 503, 504, or timeout).
  * `cooldown: 30.0` seconds before half-open probe.
* **Contractual Gates:** Requires `GEMINI_HEALTH_DATA_AUTHORIZED="true"` and `GEMINI_PAID_OR_CONTRACTED="true"`.

---

### 2.4 Text-to-Speech: Microsoft Edge Neural Voices
* **Voices Deployed:**
  1. `hi-IN-SwaraNeural`: Warm, empathetic Hindi female neural voice.
  2. `en-IN-NeerjaNeural`: Natural Indian English female neural voice.
* **Selection Algorithm (`voice.py:24-38`):**
  ```python
  def select_tts_voice(text: str, language: str | None = None) -> str:
      if language and language.casefold().startswith(("hi", "hing", "hng")):
          return HINDI_VOICE
      letters = [char for char in text if char.isalpha()]
      devanagari = sum("\u0900" <= char <= "\u097f" for char in letters)
      if letters and devanagari / len(letters) >= 0.15:
          return HINDI_VOICE
      words = set(re.findall(r"(?u)\b[\w']+\b", text.casefold()))
      return HINDI_VOICE if len(words & HINDI_MARKERS) >= 2 else ENGLISH_VOICE
  ```
* **Output Format:** High-fidelity MPEG-1 Layer 3 (MP3) audio packets streamed directly over WebSockets.

---

### 2.5 System 1 Decision Classifier: Laya (`convaiinnovations/laya`)
* **Package Version:** `laya==0.4.27`
* **Backbone Architecture:** 421M parameter ModernBERT-large backbone fine-tuned for structured decision inference.
* **Subfolder:** `multilingual`
* **Execution Options:**
  1. *Containerized Microservice:* `laya-serve` on port `8005` (`POST /v1/systemone`).
  2. *In-Process Agent:* `laya.Agent("convaiinnovations/laya", device="cpu"|"mps")` run in a background worker thread (`asyncio.to_thread`).
* **Question Schemas (`disha_core/classifier/schemas.py`):**
  ```python
  CLINICAL_QUESTIONS = {
      "intent": {
          "type": "choice",
          "instructions": "What is the primary category of the patient statement?",
          "criteria": {
              "meal_query": "food, eating, meals, what to eat, dinner, lunch, breakfast...",
              "symptom_complaint": "illness, stomach ache, pain, gas, bloating, fever...",
              "general_coaching": "wellness, greeting, walking, steps, daily exercise...",
              "emergency_escalation": "urgent life-threatening emergency, chest pain...",
          },
      },
      "emergency_triage": {
          "type": "noul",
          "instructions": "Does this message report an acute life-threatening medical emergency?",
      },
      "pep_risk": {
          "type": "score",
          "instructions": "Evaluate the cardiovascular strain and physical exertion intensity...",
          "criteria": [
              "low risk: brisk walking, gentle stretching, restorative yoga...",
              "moderate risk: light jogging, bodyweight squats, low-impact aerobics...",
              "high risk: heavy deadlifts, max-effort weightlifting, competitive CrossFit...",
          ],
      },
  }
  ```
* **Confidence Gate:** Rejects classification if confidence `< 0.40`, falling back to safe deterministic routing.

---

### 2.6 Client Voice Activity Detection (VAD)
* **Architecture:** In-browser Web Audio API `AnalyserNode` connected to the active microphone media stream (`frontend/app.js:1454-1556`).
* **FFT Size:** 64 frequency bins (`frequencyBinCount = 32`).
* **Smoothing Time Constant:** 0.3.
* **Energy Threshold:** `20` (computed as `sum(dataArray) / bufferLength`).
* **Barge-In Hook:** If speech energy exceeds `20` while `isPlayingAudio == true`, the client immediately cancels local speaker playback and dispatches `{"type": "interrupt"}` over the WebSocket.

---

## 3. Token Economics & Cost Optimization ($0 Stack Strategy)

```
Turn Input Budget:
  System Prompt:        110 tokens
  Escaped XML Context:  180 tokens (PEP + Meal Slot + Top-2 Chunks)
  User Utterance:        40 tokens
  ─────────────────────────────────
  Total Input / Turn:   330 tokens

Turn Output Budget:
  Hard Sentence Cap:      3 sentences
  Total Output / Turn:   65 tokens (Avg 22 tokens / sentence)
  ─────────────────────────────────
  Total Cost / Turn:     $0.00 (within Groq & Gemini developer tiers)
```

* **Database Queries:** PostgreSQL trigram and full-text searches execute entirely in-process on the local host with 0 external network token cost.
* **ASR & TTS Costs:** Groq Whisper and Microsoft Edge-TTS provide zero-marginal-cost voice streaming within nominal clinical usage caps.
