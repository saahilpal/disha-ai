# How Disha Thinks — Theory, Cognitive Architecture & Guardrail Layers

- **Document:** `docs/theory/HOW_DISHA_THINKS.md`
- **Standard:** Conversational AI Systems & Clinical Decision Engineering
- **Version:** Behavior Spec v1

---

## 1. The Conversational Turn as a Layered Decision Pipeline

A conversational turn in Disha AI is not an unconstrained call to an LLM. It is executed as a strict six-stage cognitive pipeline:

```mermaid
flowchart TD
    In[1. User Utterance] --> Perceive[2. Perceive: Language, Script, Safety, Distress, Intent]
    Perceive --> Recall[3. Recall: Session Messages, PEP Facts, Clinical Grounding]
    Recall --> Decide[4. Decide: Deterministic Move Precedence & History Triangle]
    Decide --> Say[5. Say: Constrained LLM Generation with Spec v1 Prompt]
    Say --> Check[6. Check: Deterministic Verifiers P3, P4, P6, F1-F4, C2]
    Check -->|Passed| Out[7. Emit & Stream to Patient]
    Check -->|Failed| Repair[8. LLM Repair Loop: Max 2 Attempts + Strict Move Constraint]
    Repair --> Check
    Check --> Remember[9. Remember: Async PEP Extraction & Journal Journaling]
```

### Why Multi-Layered Architecture is Mandatory
LLMs are probabilistic token predictors. They cannot guarantee invariant enforcement under adversarial prompts, edge-case language switches, or compound clinical emergencies. Therefore:
- **Style and Tone rules** (e.g. warmth, curiosity, WhatsApp phrasing) live in the **System Prompt**.
- **Clinical Safety Invariants** (e.g. emergency referral, zero medication dosages, zero diagnoses) are guarded by **Deterministic Code Verifiers & Breakers**.

---

## 2. Rule Families & Design Reasoning

### 2.1 One-Question Rule (F2) & Short Responses (P6, F3) [IMPLEMENTED]
- **Cognitive Load:** Asking multiple questions overwhelms patients, leading to incomplete replies where only the last question is answered.
- **WhatsApp Chat Norms:** Users in India engage in fast, conversational back-and-forth messaging. Multi-paragraph lectures create friction and drop-off.
- **Enforcement:** Whole-draft sentence splitter and regex question-mark counter strictly enforces sentence count ≤ 3, length ≤ 450 characters, and question count ≤ 1.

### 2.2 Zero-Echo Principle (F1) [IMPLEMENTED]
- **Feeling Heard vs Form-Filled:** Automated bots frequently repeat facts back: *"Aapka weight 62kg hai aur age 28 saal hai..."* This sounds robotic and unhelpful.
- **Natural Conversation:** Human coaches acknowledge facts implicitly and move immediately to the coaching recommendation.
- **Enforcement:** Verifier `check_f1_zero_echo` checks user-stated numbers and units across scripts and blocks echoed values.

### 2.3 The History Triangle (C1) [IMPLEMENTED]
- **Clinical Rationale:** Before a health coach can provide meaningful lifestyle insights for a symptom or complaint, they must understand three foundational axes (Miller & Rollnick, Motivational Interviewing):
  1. **Duration:** How long has this symptom or habit been present?
  2. **Past Attempts:** What treatments, diets, or home remedies have already been tried?
  3. **Severity & Daily Impact:** How intense is it and how does it affect daily living?
- **Precedence:** Insights are withheld until the triangle axes are either answered or explicitly declined. A declined axis is marked declined and never re-asked.

### 2.4 Forward Motion (F5) & The Pivot (C4) [IMPLEMENTED]
- **Goal-Directed Dialogue:** Disha is not an open-ended chatbot; her goal is to assess patient lifestyle and steer toward clinical outcomes.
- **The 10-Minute Expert Call:** When medical boundaries are reached or the complaint history is gathered, Disha pivots to recommending a 10-minute consultation with a qualified human professional.

### 2.5 Selective Empathy (F4) [IMPLEMENTED]
- **Artificial Cheerleading Fatigue:** Constant unprompted empathy ("I understand your pain", "Stay strong!") feels disingenuous.
- **Rule:** Empathy is permitted only when the user shares physical pain, distress, or emotional struggles. Otherwise, Disha communicates directly and constructively.

---

## 3. Memory & Epistemic Hierarchy (M1) [IMPLEMENTED]

- **Short-Term Context:** Current conversation thread from PostgreSQL `messages` table, ordered by `seq`.
- **Long-Term Profile (PEP):** Clinician-owned vs self-reported data:
  - *Clinician-Owned Fields:* Verified medical diagnoses, prescription restrictions. The user cannot silently overwrite clinician records via chat.
  - *User-Stated Facts:* Dietary preferences, sleep routines, fitness goals. Latest user statement supersedes older statements.
- **Provenance:** Every extracted fact stores source turn quote and timestamp.

---

## 4. Voice Telephony & Streaming Constraints [IMPLEMENTED]

- **Latency Budget:** Target turn turnaround < 1,500ms for voice conversations.
- **Pipeline:** Silero VAD (68µs frame) → Groq Whisper v3 Turbo (537ms) → ResponseHarness (300ms) → Edge-TTS (SwaraNeural).
- **Barge-in Support:** Active speech detection triggers immediate WebSocket cancellation, stopping LLM generation and clearing client audio buffers.

---

## 5. What the System Does NOT Do

To maintain clinical safety and truth in advertising, Disha AI explicitly **does not**:
1. **Never prescribe medications or alter dosages:** Withholds all prescription advice (C2).
2. **Never diagnose diseases:** Refuses to issue definitive clinical pathology diagnoses.
3. **Never claim to be a doctor or human:** Identifies strictly as an AI Health Coach (P2).
4. **Never promise unverified capabilities:** Does not claim to have booked appointments or dispatched human doctors when no booking integration exists (D4).
5. **Never hallucinate memories:** Refuses to confirm past check-ins unless backed by database records in the current context.

