# Trade-offs and Learnings: Disha AI Health Coach

Building Disha AI taught me that building real-world AI applications is very different from following simple tutorials. Here is an honest breakdown of what worked, what failed, what I learned, and what I would improve with more time.

---

## 1. What Worked Really Well

1. **The Thick Deterministic Spine:**
   - Inverting the architecture—treating the LLM as an untrusted leaf node and writing the core logic in deterministic Python—solved almost all of our early reliability issues.
   - Emergency checks, database queries, and data scrubbing run in under 2 milliseconds with 100% predictability.
2. **Deterministic Tri-Lingual Language Matching:**
   - Instead of letting the LLM randomly guess whether to reply in Hindi, English, or Hinglish, detecting the script and keywords deterministically and injecting an explicit directive worked flawlessly.
   - Users get answers in the exact language they typed.
3. **In-Process Hybrid Search (BM25 + 512D MD5 Vectorizer):**
   - We did not need an expensive cloud vector database. Combining SQLite FTS5 for exact keyword matching with an in-memory 512-dimensional vector projection using MD5 hashes gave sub-2ms search with zero cloud bills.
4. **Shared Chat and Voice Context:**
   - Using a unified SQLite `conversation_messages` table and shared `patient_id` allowed seamless transitions between typing a message and tapping the voice call button.

---

## 2. What Did Not Work (And What I Changed)

1. **Relying on Python's Built-in `hash()` for Embeddings:**
   - *Failed Attempt:* I used `hash(word) % 256` to build dense vectors.
   - *Why it failed:* Python randomizes hash seeds on every restart (`PYTHONHASHSEED`), so search scores changed every time the server restarted.
   - *What I changed:* Switched to standard MD5 hashing (`hashlib.md5`), which is 100% deterministic across all restarts.
2. **Stuffing Raw Conversation History into Every Turn:**
   - *Failed Attempt:* Sending the entire transcript of all past turns to the LLM.
   - *Why it failed:* As conversations grew beyond 15 turns, responses became slow, token costs multiplied, and the model suffered from "lost-in-the-middle"—it brought up food preferences from 10 turns ago that were no longer relevant.
   - *What I changed:* Sliced active dialogue history to the last 4 to 6 turns and stored durable facts into a separate `user_memories` table.
3. **Unconditional Keyword Attachment in RAG:**
   - *Failed Attempt:* The retriever automatically added `["jeera", "saunf"]` to mandatory tokens whenever a top-retrieved document contained those words.
   - *Why it failed:* Even when a user asked a dinner question, if the RAG chunk mentioned jeera water, the post-turn sanitizer forced bloating advice into a dinner reply!
   - *What I changed:* Scoped mandatory clinical tokens to questions that actually contained digestive symptom keywords.
4. **Hardcoded Fallbacks and Demo Profiles:**
   - *Failed Attempt:* Defaulting missing users to "Ramesh" and defaulting offline speech to *"What should I eat for dinner?"*.
   - *Why it failed:* It masked real errors during automated testing and assumed fresh users were named Ramesh with diabetic diet charts.
   - *What I changed:* Deleted all fake mock strings. If a user is new, they get a fresh ID and a clean slate.

---

## 3. What Are the Current Limitations?

1. **Single-Instance Database (SQLite):**
   - SQLite is fast and zero-cost for a single server, but it does not support high-concurrency multi-instance scaling. If Disha scales to thousands of simultaneous calls, we would need to migrate to PostgreSQL.
2. **Sliding Window vs. Full Episodic Compression:**
   - Currently, we use the last 4 to 6 turns. If a user has a 50-turn conversation about several topics, earlier topics fall out of the working window (though atomic facts are saved in `user_memories`).
3. **Voice Latency on Unstable Mobile Networks:**
   - Streaming raw audio chunks over WebSockets works great on broadband, but on poor 2G/3G mobile connections, network jitter can cause occasional audio buffering.

---

## 4. What Would I Improve With More Time?

1. **Background Episodic Summarization Worker:**
   - Add a lightweight background worker that runs every 10 turns to generate a 2-sentence summary of previous topics and store it in `conversation_summaries`.
2. **On-Device Voice Recognition (Web Speech API / Whisper.wasm):**
   - Transcribe voice directly inside the user's browser for simple commands. This would eliminate audio upload latency completely.
3. **User Memory Management UI:**
   - Give users a simple screen in settings where they can see all the personal facts Disha has remembered about them and tap "Delete" on any fact they want removed.

---

## 5. What I Learned as an Engineer

1. **"Prompt engineering" is only 10% of the work:**
   - You cannot fix architectural problems by simply adding more rules to a system prompt. Real reliability comes from data schemas, routing logic, and software guardrails.
2. **Failures must be handled honestly:**
   - Never write fake fallbacks to hide an offline API. It is much better for the software to say *"I could not record your audio"* or *"No meal scheduled"* than to hallucinate a fake interaction.
3. **Keep the architecture as simple as possible:**
   - You do not need expensive vector databases, complex multi-agent frameworks, or paid voice APIs to build a fast, reliable AI application. Simple Python, clean SQLite, and standard WebSockets are faster, easier to debug, and free to operate.
