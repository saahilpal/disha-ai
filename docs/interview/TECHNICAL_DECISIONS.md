# Technical Decisions: Disha AI Health Coach

Here are the key technical decisions I made while building Disha AI, along with the alternatives I considered and why I chose what I did.

---

## 1. System Architecture: Thick Deterministic Spine vs. LLM Agent Frameworks

### The Decision
I built a **Thick Deterministic Spine** in FastAPI and Python. The backend software handles all authentication, safety checks, database queries, and data validation deterministically. The LLM is only called at the very end to format verified facts into friendly conversational sentences.

### Alternatives Considered
- **LangChain / CrewAI multi-agent frameworks:** I considered building multi-agent loops where an LLM agent decides what database to call, another agent critiques the answer, and another agent checks safety.

### Why I Chose My Approach
- **Speed & Latency:** In voice calls, every second matters. Multi-agent loops make 3 to 4 sequential LLM calls, taking 3 to 6 seconds per turn. That makes voice conversations feel broken. My deterministic spine runs in under 15 milliseconds.
- **Predictability & Safety:** In healthcare, you cannot gamble on whether an agent decides to check an emergency rule. A deterministic regex check executes in 0.05 milliseconds with 100% reliability.
- **Simplicity:** A junior developer can trace the complete code in standard Python without getting lost in framework abstractions.

---

## 2. Knowledge Retrieval: Two-Tier Hybrid RAG vs. Vector Databases

### The Decision
I used a **Two-Tier Hybrid Search** directly inside Python and SQLite:
1. **Tier 1 (Lexical):** SQLite FTS5 with BM25 keyword matching.
2. **Tier 2 (Semantic):** An in-memory 512-dimensional vectorizer using deterministic MD5 hashing (unigrams, bigrams, and character 5-grams).
3. **Combination:** Reciprocal Rank Fusion (RRF) to merge and rank the results.

### Alternatives Considered
- **External Vector Databases (Pinecone, Weaviate, Qdrant Cloud):** Connecting to an external cloud vector database.
- **Heavy Embedding Models (OpenAI `text-embedding-3-small` or HuggingFace models):** Downloading large multi-gigabyte models or paying per API call.

### Why I Chose My Approach
- **Zero Cost & Free Tier:** External vector databases cost monthly subscription fees or have strict free-tier quotas that sleep when idle.
- **Sub-2ms Latency:** Because the vectorizer and SQLite run directly in the same Python process, there are zero network round-trips.
- **No Python Process Drift:** Originally, I tried Python's built-in `hash()`, but Python randomizes hash seeds on every restart. Replacing it with MD5 gave completely deterministic vector coordinates that never drift across restarts.

---

## 3. Conversation Memory: 5 Isolated Layers vs. Context Window Stuffing

### The Decision
I split memory into 5 clearly separated layers:
1. **Raw Conversation History (`conversation_messages`):** The full, untouched record of all turns.
2. **Short-Term Context:** Only the last 4 to 6 turns passed in the prompt for pronouns and follow-up questions.
3. **Long-Term Memory (`user_memories`):** Atomic facts like food preferences and workout times extracted from conversations.
4. **Structured Health Profile (`patients`):** Verified biometrics like age, weight, and height.
5. **Prescribed Plans (`patient_pep` & `patient_meals`):** Doctor-authorized exercise clearance and scheduled diet charts.

### Alternatives Considered
- **Context Stuffing:** Sending the entire conversation history (50+ turns) into every LLM prompt because modern models have large context windows.
- **Single Summary Field:** Periodically replacing conversation history with an LLM summary stored in one text field.

### Why I Chose My Approach
- **Prevents Hallucinations:** When you stuff 50 turns into a prompt, models suffer from "lost-in-the-middle"—they mix up old requests with new ones.
- **Clear Source of Truth:** A diet chart question is answered *only* from the `patient_meals` table. It never confuses a personal dinner with general clinical advice found in a medical article.
- **Fast and Inexpensive:** Keeping prompts compact (under 500 tokens) keeps generation latency low and token costs within free-tier limits.

---

## 4. Chat Streaming: HTTP POST + Server-Sent Events (SSE) vs. WebSockets

### The Decision
For text chat, I chose **HTTP POST with Server-Sent Events (SSE)** (`POST /chat/stream`).

### Alternatives Considered
- **Full WebSockets for both chat and voice.**
- **Standard synchronous REST (waiting for the full response before replying).**

### Why I Chose My Approach
- **Instant Feedback:** Waiting 2 to 3 seconds for a full answer feels slow. Streaming tokens gives the user a typing effect in under 400 milliseconds.
- **Simpler Reliability:** WebSockets for simple text chat require complex reconnect logic, connection keep-alives, and proxy configurations. SSE runs over standard HTTP, easily passes through firewalls and Cloudflare tunnels, and is simple to consume in vanilla JavaScript (`ReadableStream` / `TextDecoder`).

---

## 5. Voice Architecture: Real WebSockets + Edge-TTS vs. Paid Voice APIs

### The Decision
For voice calls, I used:
- **WebSocket (`/ws/call`):** Bidirectional real-time channel.
- **Groq Whisper Large v3 Turbo:** Fast Hinglish speech-to-text.
- **Microsoft Edge-TTS (`en-IN-NeerjaNeural`):** Natural Indian English speech synthesis.
- **Dynamic Barge-In Handler:** Detects when the user interrupts and syncs the exact audio position to the database.

### Alternatives Considered
- **OpenAI Realtime API or ElevenLabs:** Commercial voice-to-voice APIs.
- **Simulated Voice:** Generating audio on the server, saving an MP3 file, and sending a URL back over REST.

### Why I Chose My Approach
- **Cost:** Commercial voice APIs cost \$0.06 to \$0.20 per minute. A 10-minute call would cost \$1.00 to \$2.00, making a free student or demo deployment impossible. Edge-TTS is completely free and sounds natural.
- **True Two-Way Experience:** WebSockets allow the user to speak, see the live transcript, hear streaming audio, and interrupt Disha at any time.

---

## 6. Offline Fallback: Built-In OfflineEngine vs. Generic Error Messages

### The Decision
I created an intelligent, contextual `OfflineEngine` in Python. If Google Gemini or Groq APIs are unreachable, network times out, or API keys are missing, the system does not crash or say *"Error 500"*. It answers using database facts, RAG rules, and tri-lingual templates.

### Alternatives Considered
- **Generic Error Screen:** Showing *"Service temporarily unavailable. Please try again."*

### Why I Chose My Approach
- **High Availability:** In demos and interviews, third-party APIs can hit rate limits or experience network drops. The offline engine ensures every feature, guardrail, and test case continues to function seamlessly without external dependencies.
