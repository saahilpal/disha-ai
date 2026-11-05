# Project Story: Disha AI Health Coach

## What is Disha AI?
Disha AI is a conversational health coach that talks with users through text chat and real-time voice calls. It helps people with everyday questions about their nutrition, daily workouts, simple domestic remedies, and lifestyle routines. It can talk in English, Hindi, and everyday Hinglish (Hindi written in Roman letters).

## What problem does it solve?
In India, many people want to live healthier lives, but they face two big problems:
1. **The consultation gap:** A doctor or dietitian creates a plan during a visit. But after leaving the clinic, patients struggle with everyday decisions—like what to eat for dinner, what to do when they feel bloated, or whether they can still eat mangoes on a diet.
2. **Generic, robotic chatbots:** Most medical chatbots either speak in stiff textbook English, hallucinate fake advice, or repeat the same pre-written scripts over and over. They do not remember the user's past conversations, and they do not know what actual meals or workouts the doctor prescribed.

Disha solves this by acting like an attentive personal health companion. She knows your prescribed health plan, remembers your personal details, and answers your questions naturally.

## Why did I build it?
I wanted to build a practical, full-stack AI application that solves a real everyday problem. Most AI projects are just simple wrappers around OpenAI or Gemini APIs that send a user message directly to an LLM.

I quickly realized that in healthcare, you cannot simply trust an LLM to generate answers on its own:
- An LLM can hallucinate fake diet plans.
- It might guess a random subscription price.
- It might not catch a medical emergency like chest pain.
- It might forget what the user said two minutes ago.

I wanted to build a system where the AI is helpful and friendly, but the underlying software keeps strict control over safety, user records, and factual accuracy.

## What was the biggest technical challenge?
The biggest technical challenge was **balancing natural conversation with strict clinical safety and accuracy**:

1. **Safety cannot be an afterthought:** If a user types *"seene mein tez dard ho raha hai"* (severe chest pain radiating to the arm), the system cannot wait 3 seconds for an LLM to think. It must catch that emergency in less than 1 millisecond and tell the user to call 112 immediately.
2. **Context isolation:** I had to make sure the AI does not mix up general medical knowledge with personal user records. For example, if someone asks *"What is my dinner tonight?"*, the answer must come directly from their database record, not from a random search through nutrition articles.
3. **Dual-channel continuity:** A user should be able to start chatting on their phone, tap the voice call button, and continue the conversation seamlessly with shared memory and zero delay.

## How does the complete system work?
Here is the simple step-by-step journey of a message:

1. **User speaks or types:** The user sends a text message or speaks into their microphone.
2. **Pre-turn Safety Check:** Before any AI model is called, a fast safety filter checks for medical emergencies (like chest pain, stroke symptoms, or self-harm). If an emergency is found, it immediately stops the AI and shows emergency numbers (112 / 108).
3. **Intent and Language Detection:** The system detects the language (English, Hindi, or Hinglish) and the intent (greeting, clarification, or health question).
4. **Data Retrieval:**
   - If they ask about dinner $\to$ it fetches their actual meal from the database.
   - If they ask about gym workouts $\to$ it checks their exercise clearance from their prescribed plan.
   - If they ask about remedies $\to$ it retrieves doctor-approved guidelines.
5. **Prompt Assembly:** The system builds a short, compact prompt containing only the verified facts and recent conversation history.
6. **AI Response Generation:** Google Gemini or Groq Llama generates the natural response. If the internet or API is down, a built-in offline engine answers.
7. **Post-Turn Safety Check:** A sanitizer checks the output to ensure no false claims or unsafe suggestions were made.
8. **Delivery & Persistence:** The text streams to the user using Server-Sent Events (SSE). If on voice, Edge-TTS synthesizes natural audio. The entire turn is saved to the SQLite database so history is never lost.

## What makes this project technically interesting?
1. **Thick Spine, Thin Leaf Architecture:** Instead of letting the LLM run the application, the backend software acts as a strong, deterministic spine that controls the data and safety. The LLM is only used as a creative leaf node for language translation and phrasing.
2. **Hybrid RAG without Expensive Services:** I combined SQLite FTS5 (BM25 keyword search) with an in-memory 512-dimensional vector search. This runs in under 2 milliseconds on a free-tier server with zero extra hosting bills.
3. **Real Voice Interruption (Barge-in):** In voice mode, if the user speaks while Disha is talking, the system immediately cuts off Disha's speech and updates the conversation history to only what the user actually heard.
4. **Zero-Cost Deployment:** The entire system—backend, database, RAG, and voice calling—runs 100% on free-tier infrastructure.
