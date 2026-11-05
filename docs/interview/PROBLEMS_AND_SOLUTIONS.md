# Real Engineering Problems and Solutions: Disha AI Health Coach

During the development of Disha AI, I faced several subtle engineering bugs across the LLM, RAG, database, streaming, and voice layers. Here is the breakdown of the real problems I encountered, how I debugged them, and how I fixed them.

---

## 1. The Acidity False-Emergency Bug

### 1. What was the problem?
When a user typed *"Khane ke baad seene mein halki jalan ho rahi hai"* (I have mild heartburn after eating), Disha immediately triggered an emergency cardiac alert, told the user to call 112, and stopped the conversation.

### 2. Why did it happen?
The emergency safety filter had a regular expression checking for chest discomfort. It included the Hindi word `jalan` (burning sensation) across all contexts. But in Indian diets, post-meal heartburn or acidity is very common and usually non-life-threatening.

### 3. How did I identify it?
During manual testing of everyday digestive questions, I noticed that simple acidity queries were consistently getting blocked by the emergency system.

### 4. What solution did I choose?
I updated the regular expression to decouple gastric acidity from cardiac pain:
- An emergency requires severe pain qualifiers or radiating symptoms: `(seene|chhati)\s+(mein|me)?\s*(bahut|tez)?\s*(dard|dabav|ghutan)` or radiating pain to the left arm/jaw.
- Isolated post-meal heartburn (`jalan`) without chest pressure or pain now routes to clinical coaching (sipping warm water, remaining upright, taking saunf).

### 5. Why did I choose that solution?
It is deterministic and executes in 0.05 milliseconds without calling an LLM, keeping patients safe while eliminating false alarms.

### 6. What alternatives did I consider?
I considered asking the LLM to classify whether the utterance was an emergency. I rejected that because LLMs take 1 to 2 seconds and can be tricked by prompt injection.

### 7. What trade-offs did the solution have?
If a user describes a true heart attack solely as a "burning feeling" without any pain, tightness, or radiating symptom, it might not trigger the emergency circuit breaker. However, any subsequent mention of pain immediately triggers it.

### 8. How did I test whether it was fixed?
I added automated unit tests in `tests/test_guardrails.py` asserting that `"seene mein halki jalan"` returns `is_emergency=False`, while `"seene me tez dard aur left arm me ja raha h"` returns `is_emergency=True`.

---

## 2. The "Avoid Deep Squats for Headaches" Anatomical Pain Bug

### 1. What was the problem?
When a user complained of a headache (*"sir mein bahut dard ho raha hai"*), Disha replied: *"During knee pain, avoid heavy workouts and deep squats. Focus on gentle walking."*

### 2. Why did it happen?
In the symptom matching logic, a broad keyword `\b(dard|pain)\b` was mapped to a single joint pain handler. Because the word `dard` appeared in *"sir mein dard"*, it blindly matched the joint pain rule.

### 3. How did I identify it?
In `tests/test_failures.py`, an evaluation case testing headache responses failed because the response contained the word "squats".

### 4. What solution did I choose?
I split the pain logic into three distinct anatomical categories:
1. **Headaches (`sir dard` / `headache`):** Screen break, hydration, resting in a dark room.
2. **Abdominal / Stomach Pain (`pet dard` / `stomach ache`):** Light home-cooked food, warm water, avoiding oily food.
3. **Joint / Knee Pain (`ghutna` / `joint pain` / `backache`):** Avoiding deep squats, warm compress, gentle mobility.

### 5. Why did I choose that solution?
It completely stopped anatomical cross-contamination without adding any latency.

### 6. What alternatives did I consider?
Using an LLM classifier to determine body part. I rejected this because regex anatomical categorization takes under 0.1ms.

### 7. What trade-offs did the solution have?
If a patient has pain in an unlisted body part (like a finger), it falls back to general rest advice rather than a specialized routine.

### 8. How did I test whether it was fixed?
Created test cases for headache, stomach ache, and knee pain, verifying that headache advice never mentions squats or knees.

---

## 3. The Lost Chat History (SSE Stream Persistence Gap)

### 1. What was the problem?
When chatting via text, responses streamed nicely into the browser. But if the user refreshed the page, switched to voice mode, or checked their history, all past messages were completely gone.

### 2. Why did it happen?
In `app/api.py`, the streaming endpoint `POST /chat/stream` yielded tokens to the client over Server-Sent Events (SSE). But it never called `turn_orchestrator._save_turn()` to save the turn into the SQLite database. Only the non-streaming `POST /chat` endpoint was saving messages.

### 3. How did I identify it?
I opened the app, had a 3-turn chat conversation, and then opened the voice call modal. The voice call showed 0 previous messages and did not know what we had just talked about.

### 4. What solution did I choose?
I refactored the event generator inside `chat_stream_endpoint`:
- It accumulates streamed tokens into a buffer while yielding them to the client.
- Once streaming completes, it sanitizes the final text, strips markdown artifacts, and immediately calls `_save_turn()` to write the turn to `call_sessions`, `call_turns`, and `conversation_messages`.

### 5. Why did I choose that solution?
It guarantees that streamed turns and voice calls write to the exact same database tables, giving both modes a shared, persistent memory.

### 6. What alternatives did I consider?
Having the frontend send a second POST request to save the message after receiving the stream. I rejected that because if the user closes their browser tab mid-stream, the history would be lost or out of sync.

### 7. What trade-offs did the solution have?
The database write happens right after the stream finishes, adding ~2ms of background SQLite write time, which is completely imperceptible.

### 8. How did I test whether it was fixed?
Added `test_chat_stream_persistence` in `tests/test_api.py`. It streams a message via `/chat/stream` and then calls `GET /conversations/{patient_id}` to verify the turn is in the database.

---

## 4. The Simulated Voice Masking Bug

### 1. What was the problem?
When testing the voice call endpoint without Groq credentials, Disha always replied with: *"Today for dinner you have 150g paneer bhurji..."*, even if the user had stayed completely silent or said something else.

### 2. Why did it happen?
In `app/voice.py`, line 127 had a fake fallback:
```python
if not self.api_key:
    return "What should I eat for dinner tonight?"
```
Someone had added this during early mock development so the endpoint would always return something. But in real testing, it masked genuine errors and pretended the user had asked about dinner.

### 3. How did I identify it?
During the codebase audit, I traced the speech-to-text code path and found the hardcoded string.

### 4. What solution did I choose?
I deleted the fake string completely. If Groq STT is not configured or fails, `stt.transcribe()` returns an empty string `""`. The API then honestly informs the caller that audio was not detected, rather than faking an interaction.

### 5. Why did I choose that solution?
A production healthcare application must never invent user speech.

### 6. What alternatives did I consider?
Returning a mock error audio. I chose returning empty string so the caller handles it cleanly.

### 7. What trade-offs did the solution have?
When offline without speech recognition API keys, the user must use text chat or browser Web Speech API instead of backend Whisper.

### 8. How did I test whether it was fixed?
Sent blank audio bytes to `/voice-turn` and verified it returns HTTP 400 with *"Could not capture audio or text utterance"*, instead of answering about dinner.

---

## 5. Python Hash Randomization in RAG Embeddings

### 1. What was the problem?
In early RAG retrieval benchmarks, identical search queries produced different similarity scores every time the server restarted. Unrelated queries like *"How do I change motorcycle engine oil?"* were matching medical documents with a high score of 0.27.

### 2. Why did it happen?
The in-memory vectorizer used Python's built-in `hash()` function to project words into vector dimensions:
```python
dim = hash(word) % 256
```
In Python 3, `PYTHONHASHSEED` is randomized on every process startup for security. This meant the vector representation of the word "bloating" changed every time uvicorn restarted!

### 3. How did I identify it?
A test checking that unrelated queries return 0 results failed randomly after restarting the test runner.

### 4. What solution did I choose?
Replaced `hash()` with deterministic MD5 hashing:
```python
dim = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16) % 512
```
I also increased the vector dimensions from 256 to 512 and included character 5-grams and bigrams.

### 5. Why did I choose that solution?
MD5 is completely deterministic across all operating systems and restarts. The noise floor dropped from 0.27 down to under 0.04.

### 6. What alternatives did I consider?
Loading an external sentence-transformers model. I rejected that because loading a 400MB model in Python takes several seconds and consumes significant RAM on free-tier hosting.

### 7. What trade-offs did the solution have?
MD5 hashing takes ~0.1ms per chunk, which is slightly slower than Python's native `hash()`, but negligible compared to network calls.

### 8. How did I test whether it was fixed?
Verified that restarting Python and vectorizing the exact same text produces mathematically identical vectors with cosine similarity of 1.0000.

---

## 6. Fresh Users Being Called "Ramesh"

### 1. What was the problem?
When a brand-new user started chatting for the first time, Disha greeted them by saying *"Namaste Ramesh ji"* and gave them diabetic diet charts, even though the user had never entered their name.

### 2. Why did it happen?
In `app/api.py`, `ChatRequest` defaulted to `patient_id = "pt_101"`, which belonged to a pre-seeded demo user named Ramesh. Furthermore, if a patient record was missing, the prompt builder defaulted `patient_name` to `"Ramesh"`.

### 3. How did I identify it?
I tested signing in from an incognito window with a new session and was immediately addressed as Ramesh.

### 4. What solution did I choose?
- Removed the hardcoded `"pt_101"` default. When a request has no `patient_id`, the system generates a fresh unique ID (`f"pt_{uuid.uuid4().hex[:8]}"`).
- Changed the fallback name from `"Ramesh"` to `"there"` ("Hello! How can I help you today?").
- If the patient has no diet chart scheduled, Disha honestly states that no meal plan is set for today, rather than showing Ramesh's dinner.

### 5. Why did I choose that solution?
Every user starts with a completely clean slate.

### 6. What alternatives did I consider?
Forcing the user to complete a 5-step registration form before chatting. I rejected that because users prefer chatting immediately.

### 7. What trade-offs did the solution have?
Until a user tells Disha their name or fills out their profile, Disha addresses them naturally without a name.

### 8. How did I test whether it was fixed?
Added `test_fresh_user_clean_slate` in `tests/test_api.py`, verifying that a new patient ID never sees the name Ramesh or pre-existing meals.
