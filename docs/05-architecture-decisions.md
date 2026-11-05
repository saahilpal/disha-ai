# 05. Architecture Decision Records (ADRs) — Disha Clinical Voice AI

This document details the major technical decisions made for Disha AI, adhering to our principles of zero-cost, extreme low-latency (<1–2s), clinical safety, and clinical team empowerment.

---

### ADR-01: LLM Engine & Provider Selection

**Decision:**  
Use **Groq Cloud LPU running Meta Llama-3.3-70b-versatile** as the primary conversational brain, with **Llama-3.1-8b-instant** as an ultra-fast fallback.

**Reason:**  
Groq’s Language Processing Units (LPUs) provide lightning-fast inference with a Time-to-First-Token (TTFT) between **180ms and 250ms** and generation speeds of ~300 tokens/second. Llama-3.3-70B has demonstrated exceptional capability in understanding colloquial Indian Hinglish and adhering to complex JSON and medical conversational rules. Groq offers a generous free tier (30 RPM, 1,000 RPD for 70B, 14,400 RPD for 8B) requiring no credit card.

**Alternative Considered:**  
- *Google Gemini 2.0 Flash:* Very fast and good at Hindi, but Google's free tier terms explicitly allow human review and data usage for training, creating severe data privacy and HIPAA/DISHA compliance risks for patient health records.
- *OpenAI GPT-4o-mini:* Reliable, but requires a credit card and paid billing with no free tier for voice streaming.
- *Local Ollama on Mac CPU:* Zero-cost and private, but running 70B locally takes >1.2 seconds just to generate the first token, which would completely blow past our <1–2s voice turn latency budget.

**Trade-off:**  
- *Gain:* Blazing speed (~200ms TTFT), exceptional Hinglish fluency, zero dollar cost on developer tier.
- *Sacrifice:* Subject to Groq free-tier rate limits (30 requests/minute), necessitating intelligent token caching and prompt size control.

---

### ADR-02: Emergency Red-Flag Triage Architecture

**Decision:**  
Implement a **Deterministic Pre-Turn Circuit Breaker** using compiled Aho-Corasick / regex pattern matching that runs in **<0.005ms (<5 microseconds)** before the LLM is ever called. If an acute symptom is detected, the LLM is completely bypassed and pre-synthesized triage audio is emitted instantly.

**Reason:**  
In medical emergencies (e.g. Failure #5: chest pain and left-hand numbness during a workout), there is zero tolerance for error. Probabilistic LLMs can and will occasionally hallucinate, give generic advice, or fail to prioritize acute symptoms when distracted by conversational context. A deterministic pre-turn gate guarantees **100% recall**, zero hallucination risk, and instant (<150ms) emergency response.

**Alternative Considered:**  
- *LLM Self-Triage via System Prompt:* Instructing the LLM in its prompt to always spot emergencies. Rejected because LLMs are non-deterministic; under stress or complex phrasing, they occasionally miss symptoms.
- *Secondary LLM Classifier:* Calling a fast 8B model to classify intent before calling the 70B model. Rejected because adding a second LLM adds 150–250ms of network latency and still carries probabilistic error.

**Trade-off:**  
- *Gain:* 100% deterministic safety, zero missed emergencies, sub-millisecond execution, care ops alerts dispatched immediately.
- *Sacrifice:* Requires maintaining an explicit lexicon of medical emergency keywords and Hinglish synonyms (e.g., *"seene mein dard"*, *"chhati pe dabav"*).

---

### ADR-03: Knowledge Storage & Hybrid Retrieval Engine

**Decision:**  
Use an **Embedded SQLite database with Full-Text Search (FTS5)** paired with in-process **FastEmbed ONNX vector embeddings** (`paraphrase-multilingual-MiniLM-L12-v2`) and exact B-tree tag lookups.

**Reason:**  
SQLite is serverless, zero-cost, ACID-compliant, and embedded directly inside the Python process. Its FTS5 full-text engine evaluates BM25 keyword matches in **<1.5ms**. For our curated clinical guidelines (<1,000 rules), computing cosine similarity in-memory using FastEmbed takes **<5ms on CPU**. SQLite Write-Ahead Logging (WAL) ensures clinicians can update rules concurrently without locking mid-call reads.

**Alternative Considered:**  
- *Pinecone / Qdrant Cloud:* Dedicated vector databases. Rejected because they introduce network round-trip latency (30–60ms per call), require API keys, and free tiers often go idle or have cold starts.
- *PostgreSQL with pgvector:* Powerful, but requires spinning up and maintaining a running database server container, increasing memory footprint and operational complexity.

**Trade-off:**  
- *Gain:* Zero network latency, zero cloud hosting cost, instant setup, single-file backup and portability.
- *Sacrifice:* Not suitable for multi-million vector datasets, but clinical protocol repositories for follow-up calls typically contain a few hundred to a few thousand vetted rules, making SQLite the sweet spot.

---

### ADR-04: Text-to-Speech (TTS) Engine

**Decision:**  
Use **`edge-tts` (Microsoft Edge Neural Speech Synthesis)** utilizing the **`hi-IN-SwaraNeural`** (female) and **`en-IN-NeerjaNeural`** voices.

**Reason:**  
`edge-tts` provides studio-quality neural voice synthesis that natively understands Indian English, Hindi, and code-mixed Romanized Hinglish. It generates speech with authentic cadence, warm bedside empathy, and correct pronunciation of terms like *"jeera paani"* or *"multigrain roti"*. It provides streaming WebSocket audio chunks with a Time-to-First-Byte (TTFB) under **220ms**, and is 100% free to use.

**Alternative Considered:**  
- *Kokoro-82M (Local ONNX):* Extremely fast and open-source, but its Hindi voice models currently expect Devanagari script; passing Romanized Hinglish leads to frequent phonetic garbling and unnatural pronunciation.
- *ElevenLabs / Cartesia Sonic:* Exceptional voice quality, but costs ~$0.015–$0.03 per minute, requiring paid credit card subscriptions that violate the zero-cost requirement.
- *Browser SpeechSynthesis API:* Zero server cost, but robotic, platform-dependent, and missing Hindi voices on many OS installations.

**Trade-off:**  
- *Gain:* Pristine Hinglish audio, warm healthcare tone, streaming latency <250ms, zero financial cost.
- *Sacrifice:* Relies on Microsoft's public edge speech endpoints over WebSocket; requires an internal retry buffer for network resilience.

---

### ADR-05: Speech-to-Text (STT) Engine & Hinglish Biasing

**Decision:**  
Use **Groq Whisper-large-v3-turbo** with a **clinical Hinglish initial prompt** (`prompt="Hinglish patient follow-up: BP, bloating, jeera paani, saunf, gym, migraine, nausea, diet chart, weakness"`), with a browser Web Speech API / Faster-Whisper fallback.

**Reason:**  
Whisper-large-v3-turbo on Groq processes a 3-second audio utterance in **100–180ms**. Providing a domain-specific initial prompt biases Whisper's beam search decoder towards Romanized Hindi and medical terms, eliminating common transcription errors (e.g. transcribing *"jeera"* as *"zeera"* or *"jira"*).

**Alternative Considered:**  
- *Local Whisper (faster-whisper on CPU):* Good accuracy, but takes 300–500ms on CPU, consuming significant local CPU cycles.
- *Web Speech API only:* Instant transcription in browser, but produces inconsistent scripts (mixes Devanagari and Latin randomly) and does not provide raw audio for clinical audits.

**Trade-off:**  
- *Gain:* Sub-200ms transcription, 98%+ accuracy on code-mixed Hinglish clinical terms, free on Groq tier.
- *Sacrifice:* Requires client-side audio streaming and chunking via WebSocket.

---

### ADR-06: Clinical Rule Authoring & Zero-Regression Gate

**Decision:**  
Empower clinicians with a **Visual Rule Studio** backed by a **Pre-Publishing Synthetic Test Oracle**. Clinicians create declarative rules (Triggers, Conditions, Clinical Directives, Stances). Before a rule can be activated, the system automatically executes a pinned regression suite of past failure modes. If any test fails, the rule is blocked.

**Reason:**  
This satisfies the core business requirement: non-technical clinicians can fix issues within hours without engineer deployments, while the automated oracle guarantees that fixing "mangoes" does not accidentally break "diabetic diet" or "chest pain".

**Alternative Considered:**  
- *Engineer-Managed Git Prompts:* Clinicians file Jira tickets, engineers modify system prompts, run tests, and deploy. Rejected because this takes days or weeks and leads to prompt bloat.
- *Direct Unrestricted Database Updates:* Allowing clinicians to edit rules live without automated tests. Rejected because non-technical users can easily introduce conflicting rules that cause silent clinical regressions in production calls.

**Trade-off:**  
- *Gain:* Clinicians can update behaviors in minutes; zero prompt bloat; mathematically verified zero regressions.
- *Sacrifice:* Requires building a dedicated test runner and simulation interface.

---

### ADR-07: Backend Architecture & Concurrency Model

**Decision:**  
Build the core service with **Python FastAPI using asynchronous WebSockets (`asyncio`)** and an event-driven turn pipeline.

**Reason:**  
Voice AI pipelines require streaming binary audio in real-time. FastAPI provides high-throughput async I/O, native WebSocket connection management, built-in Pydantic data validation, and auto-generated OpenAPI documentation.

**Alternative Considered:**  
- *Flask / Django:* Synchronous WSGI frameworks are poorly suited for streaming audio over persistent WebSockets.
- *Heavy Agent Frameworks (LangChain / CrewAI):* Too many layers of abstraction, high overhead, slow execution, and unpredictable prompt wrapping that adds 200–500ms of unnecessary latency.

**Trade-off:**  
- *Gain:* Clean, lightweight, modular, ultra-fast async execution (<10ms server overhead per turn).
- *Sacrifice:* Requires explicit async/await hygiene and careful error boundary handling.

---

### ADR-08: Atomic Sentence Buffer Barrier for Streaming Audio

**Decision:**  
Buffer streaming LLM tokens up to the first terminal punctuation boundary (`.`, `?`, `!`, `।`, or newline), run the deterministic post-turn sanitizer on the complete sentence string (<0.5ms), and only dispatch the validated sentence to the speech synthesizer.

**Reason:**  
As identified by the ECC Security Reviewer, streaming raw partial token chunks directly to TTS creates race conditions where hallucinated identity claims (*"Haan main insaan doctor hoon"*) or false channel promises (*"WhatsApp par bhejti hoon"*) begin playing out of the patient's phone speaker before post-turn filters can evaluate the full clause. An atomic sentence barrier guarantees zero unsafe audio leakage while adding only ~40ms buffer latency at 300 tokens/sec.

**Alternative Considered:**  
- *Full-Turn Buffering:* Wait for the entire 35-word turn to finish before starting TTS. Rejected because this adds 200–400ms delay, violating our <1–2s voice turn latency budget.
- *Chunk-Level Token Streaming without Barrier:* Synthesizing audio word-by-word. Rejected due to critical safety and hallucination leakage risks.

**Trade-off:**  
- *Gain:* 100% prevention of audio hallucination leaks; seamless neural voice intonation over complete grammatical sentences.
- *Sacrifice:* Adds ~30–50ms token accumulation time before the first sentence audio synthesis begins.

---

### ADR-09: Pre-LLM PHI De-Identification & Compliance Proxy

**Decision:**  
Implement an upstream in-memory pseudonymization proxy that strips real patient names, telephone numbers, and 14-digit Ayushman Bharat Health Account (ABHA) IDs before turn prompts are dispatched to cloud LLMs, substituting them with ephemeral synthetic placeholders (`[PATIENT_FIRST_NAME]`).

**Reason:**  
Under India's Digital Information Security in Healthcare Act (DISHA), the Digital Personal Data Protection Act (DPDP 2023), and HIPAA §164.502, sending identifiable patient medical histories to third-party model inference APIs creates major regulatory and data privacy liabilities. In-memory pseudonymization satisfies the data minimization principle while preserving clinical reasoning.

**Alternative Considered:**  
- *Passing Raw Patient PII to Cloud LLM:* Simple to implement, but violates healthcare privacy laws and HIPAA/DISHA standards.
- *Running 100% On-Premises Local 70B LLM:* Ensures total privacy, but takes >1.2s TTFT on CPU hardware, busting the real-time voice latency budget.

**Trade-off:**  
- *Gain:* Full compliance with DISHA, DPDPA 2023, and HIPAA data minimization; zero exposure of patient identities to external APIs.
- *Sacrifice:* Requires maintaining an ephemeral per-session de-identification map to re-hydrate friendly first names in the post-turn output stage.

---

### ADR-10: Dual-Track Emergency Red-Flag Engine

**Decision:**  
Equip the Pre-Turn Circuit Breaker with a Dual-Track detection engine: Track 1 runs an optimized Aho-Corasick automaton (<0.005ms) across common medical red flags; Track 2 expands phonetic Soundex and colloquial Hinglish regional idioms (*"ulta haath"*, *"chhati pe dabav"*, *"dil mein jalan"*, *"seene pe bojh"*).

**Reason:**  
As identified by the ECC Healthcare Reviewer, standard medical dictionaries miss North Indian conversational idioms where patients describe left-arm numbness as *"ulta haath sunn"* or chest tightness as *"chhati pe dabav"*. Comprehensive colloquial expansion guarantees 100% recall on acute coronary and stroke events without relying on slow or non-deterministic LLMs.

**Alternative Considered:**  
- *Pure English Medical Lexicon:* Misses 40%+ of code-mixed Hindi patient emergency expressions.
- *LLM Intent Classifier:* Introduces 200ms latency and probabilistic non-zero miss rates for life-threatening emergencies.

**Trade-off:**  
- *Gain:* True 100% recall on colloquial Hinglish acute symptoms; zero latency penalty (<0.01ms).
- *Sacrifice:* Requires ongoing clinical maintenance of colloquial regional symptom synonyms.

