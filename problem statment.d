### Round 3 — Voice Call Systems Design Take-Home (60 mins: 20m presentation + 40m stress-test & culture)

**Context:**

- Disha runs proactive **real-time Hinglish voice follow-up calls** (STT → LLM → TTS) under a **<1–2s turn latency budget**.
- Current prompt inputs: Persona + Call Plan + User PEP + Recent chat/call history.
- **Real production failures found in clinical review:**
    1. **Hallucinated pricing:** User asks *"Yeh app paid hai kya? Kitne ka subscription hai?"* Model invents a price.
    2. **Missed clinical remedy:** User mentions period bloating. Disha gives generic empathy instead of our doctors' approved remedy (jeera/saunf water).
    3. **False capability promise:** Disha says *"Main aapko WhatsApp par diet chart bhej deti hoon."* We do not support WhatsApp.
    4. **Persona violation:** User jokes *"Aap insaan ho ya robot?"* Disha claims to be human (must always state she is an AI health coach).
    5. **Missed red-flag emergency:** User mentions chest pain and left-hand numbness during a workout chat. Disha replies politely and continues the workout topic.
    6. **Ignored system data:** User asks *"Aaj dinner mein kya hai mere diet chart ke hisaab se?"* Diet chart exists in our DB, but the model guesses wrong.
    7. **Ignored PEP context:** User says she joined a gym. Disha pushes home workouts, ignoring that her PEP explicitly allows gym workouts.
    8. **Clinical stance contradiction:** User asks about mangoes for weight loss. Model bans them; our clinical stance is seasonal moderation.

**Core requirement:**
New failure modes appear every week. Non-technical clinicians (doctors, dietitians, coaches) must be able to add or update system behaviors within hours—without engineer deploys, without bloating the system prompt, and without regressing prior fixes.

**Your design must cover:**

1. **Knowledge & retrieval:** Where vetted clinical knowledge lives and how it reaches the model mid-call without stuffing the prompt.
2. **Architecture by failure class:** How you handle wrong statements (3, 4), missed actions (2, 5, 7), and missing facts (1, 6).
3. **Latency & cost:** What runs per turn vs. asynchronously, model selection per component, and cost per call minute.
4. **Safety bar:** How you guarantee near-zero misses on emergencies like #5.
5. **Clinical authoring workflow:** How clinicians author, test, and ship rules safely without breaking existing behaviors.
6. **Evaluation:** Pre-launch and continuous post-launch evaluation on live Hinglish calls.

*Note: Ask clarifying questions before the session if anything is ambiguous.*