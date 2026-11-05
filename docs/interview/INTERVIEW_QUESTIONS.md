# Technical Interview Questions & Answers: Disha AI Health Coach

Here are the questions an interviewer might ask about Disha AI, along with concise, natural answers you can speak with confidence.

---

## Architecture & System Design

### Q1: Can you give me a high-level overview of the architecture of Disha AI?
> **Answer:**
> "I designed Disha AI using what I call a **Thick Deterministic Spine with a Thin Probabilistic Leaf**. 
> In simple terms, the backend (built with FastAPI and SQLite) handles all the critical rules deterministically—such as emergency triage, patient record lookups, exercise constraints, and data scrubbing. The LLM is only called at the very end to format those verified facts into a warm, conversational response. This keeps responses fast, safe, and factual, while avoiding hallucinations."

### Q2: Why did you separate the deterministic spine from the LLM?
> **Answer:**
> "In clinical healthcare, you cannot rely on an LLM to reliably obey safety rules 100% of the time. If someone has acute chest pain radiating to their arm, waiting for an LLM to decide what to do is too slow and risky. By putting safety checks and database lookups in deterministic Python code before the LLM, emergency checks happen in less than 0.1 milliseconds every single time."

---

## Backend & API Design

### Q3: Why did you choose FastAPI for the backend?
> **Answer:**
> "FastAPI gives me native Python `async/await` support, which was essential for handling streaming tokens over Server-Sent Events (SSE) and managing bidirectional WebSockets for voice calls. It also provides automatic Pydantic data validation and OpenAPI interactive documentation out of the box."

### Q4: How did you implement real-time streaming for chat responses?
> **Answer:**
> "I used HTTP POST with **Server-Sent Events (SSE)** via FastAPI's `StreamingResponse`. When the user sends a message, the backend immediately begins yielding tokens as they arrive from the LLM client. On the frontend, vanilla JavaScript reads the chunks using a `ReadableStream` and `TextDecoder`, rendering a smooth typing animation in under 400 milliseconds."

### Q5: How do chat and voice calls share conversation history?
> **Answer:**
> "Both chat and voice share the exact same `patient_id` and `session_id`. When a chat turn streams or a voice turn finishes, the backend writes both the user's message and the final assistant response to a shared SQLite table called `conversation_messages`. When a user opens the voice modal, it preloads the last several turns from that table, so the voice coach immediately knows what was discussed in chat."

---

## Database & Data Isolation

### Q6: What database did you use, and how did you design the schema?
> **Answer:**
> "I used **SQLite** because it is lightweight, runs in-process with zero network latency, and requires zero external database hosting fees. 
> I created isolated tables for different types of data:
> - `patients` for structured physical metrics (age, height, weight).
> - `patient_pep` for doctor-prescribed exercise plans and conditions.
> - `patient_meals` for scheduled weekly diet plans.
> - `conversation_messages` for the raw, immutable chat history.
> - `user_memories` for long-term personal preferences extracted from conversations.
> - `clinical_rules` for doctor-vetted home remedies and protocols."

### Q7: How do you prevent personal health records from being confused with general medical knowledge?
> **Answer:**
> "I use a strict retrieval routing strategy:
> - If a user asks *'What is my dinner tonight?'*, the system queries only the `patient_meals` table. It never runs a RAG search across medical articles for personal diet questions.
> - If a user asks *'Can I go to the gym?'*, it checks the `allowed_exercise` array in `patient_pep`.
> - RAG retrieval is only triggered when the user asks a clinical symptom question, like what to do for bloating or acidity."

---

## RAG & Vector Search

### Q8: How does your RAG system work?
> **Answer:**
> "I built a **Two-Tier Hybrid Search** without external vector databases:
> 1. **BM25 keyword search** using SQLite FTS5 with common stopword filtering.
> 2. **Dense semantic search** using an in-memory 512-dimensional vectorizer built with deterministic MD5 hashing (combining unigrams, bigrams, and character 5-grams).
> 3. I combine both rankings using **Reciprocal Rank Fusion (RRF)** and filter out chunks with similarity below 0.25. This runs in under 1.5 milliseconds with zero external cloud dependencies."

### Q9: Why didn't you use an external vector database like Pinecone?
> **Answer:**
> "For Disha's current scale (hundreds of clinical guidelines and rules), an external vector database adds unnecessary network latency (50 to 100ms per search) and monthly cloud costs. Running hybrid search in-process inside SQLite and Python executes in under 2ms, costs zero dollars, and is much simpler to deploy."

---

## LLM Integration & Prompt Engineering

### Q10: Which LLMs are you using, and how do you handle rate limits?
> **Answer:**
> "The system supports **Google Gemini (free tier)** and **Groq Llama 3.3 70B (free tier)**. If both cloud providers are unreachable or rate-limited, the system automatically falls back to an intelligent local `OfflineEngine`. This offline engine uses the RAG facts, patient PEP, and tri-lingual response templates to provide full answers without crashing or showing error messages."

### Q11: How do you handle language matching in English, Hindi, and Hinglish?
> **Answer:**
> "I built a deterministic language detector that inspects the latest user message:
> - If it contains Devanagari Unicode characters, it detects Hindi.
> - If it contains common Roman Hindi words (like `kya`, `hai`, `kaise`, `dard`), it detects Hinglish.
> - Otherwise, it detects English.
> The prompt builder injects an explicit language directive instructing the model to reply in that exact language. If the user asks in Hinglish, Disha responds in natural Hinglish; if in English, she responds in English."

---

## Voice Architecture & Audio Processing

### Q12: How does real-time voice communication work in Disha AI?
> **Answer:**
> "When the user opens the voice call modal, a bidirectional **WebSocket** connects to `/ws/call`. The browser captures microphone audio via the Web Audio API and streams WebM Opus chunks. The backend transcribes audio using Groq Whisper Large v3 Turbo, processes the turn through the deterministic spine, synthesizes spoken audio using Microsoft Edge-TTS (`en-IN-NeerjaNeural`), and streams the audio payload back to the browser for playback."

### Q13: What happens if a user interrupts Disha while she is speaking?
> **Answer:**
> "This is called **barge-in**. When the user starts speaking or clicks interrupt, the browser immediately pauses playback and calculates how much of the audio was heard: `currentAudio.currentTime / currentAudio.duration`. It sends a `barge_in` event over the WebSocket with this fraction. 
> The backend then truncates the assistant's message in the database to only the words the user actually heard before interrupting, adding an ellipsis (`...`). This ensures that future turns do not assume the user heard advice that was cut off."

---

## Safety & Security

### Q14: How do you prevent medical hallucinations?
> **Answer:**
> "I use a multi-stage approach:
> 1. **Factual Grounding:** Specific facts (meals, prices, clearance) are injected directly from the database into the prompt as ground truth.
> 2. **Post-Turn Sanitizer:** After the LLM generates a response, a deterministic sanitizer checks for mandatory remedy tokens (like jeera and saunf for bloating) and catches any contraindicated advice.
> 3. **Egress Scrubbing:** An egress gate strips internal tags (like `[Approved Reference...]`) and masks any sensitive personal data (Indian phone numbers, Aadhaar numbers, email addresses) before sending the response to the user."

### Q15: How do you handle emergency detection?
> **Answer:**
> "Emergency detection happens pre-turn before any LLM is called. A regex-based circuit breaker checks for critical red-flag patterns: cardiac symptoms (crushing chest pain radiating to the left arm), respiratory distress, stroke symptoms, acute bleeding, and self-harm. If any match is found, the turn is immediately aborted in under 0.05ms, and the system issues an immediate 112 emergency helpline response."

---

## Testing & Quality Assurance

### Q16: How did you test Disha AI?
> **Answer:**
> "I built an automated test suite with **60 unit and integration tests** using `pytest` covering API endpoints, RAG retrieval accuracy, guardrails, and voice mechanics. 
> Additionally, I used an independent QA evaluation harness that tested **109 realistic conversational scenarios** across 6 weighted categories: Medical Safety (100%), Grounding (92%), Context & Personalization (85%), Intent Understanding (100%), Language (100%), and Conciseness (100%), achieving an overall score of 95.0%."

---

## Scalability & Limitations

### Q17: What are the current limitations of Disha AI, and what would you improve with more time?
> **Answer:**
> "Currently:
> 1. **SQLite concurrency:** SQLite works great for single-instance deployments, but for horizontal scaling across multiple servers, I would migrate to PostgreSQL with pgvector.
> 2. **Episodic Summarization:** Currently, the system uses a sliding window of the last 4 to 6 turns. For very long conversations lasting dozens of turns, I would implement background episodic summarization every 10 turns.
> 3. **Voice Latency on Mobile Web:** On slower mobile networks, sending audio chunks over WebSockets can add latency. Moving speech recognition client-side using Web Speech API or on-device Whisper would reduce turn latency even further."
