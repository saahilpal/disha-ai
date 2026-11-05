# 04 — End-to-End User Flows & Interaction Workflows

This document details the primary user journeys and data execution flows across Disha AI, covering patients, clinicians, and Care Ops coordinators.

---

## 1. Flow 1: Proactive Patient Voice Follow-Up Turn

The patient receives a scheduled proactive follow-up voice call from Disha.

```
[Patient Speaks]
       │
       ▼ (Audio Streaming via Web Audio / Telephony)
[VAD & Silence Detection (<120ms)]
       │
       ▼
[Groq Whisper-large-v3-turbo STT (<250ms)]
       │
       ▼ (Hinglish Transcript)
┌──────────────────────────────────────────────────┐
│ Step 1: Pre-Turn Emergency Circuit Breaker       │
│ (<0.005ms Aho-Corasick / Compiled Regex)        │
└────────┬─────────────────────────────────────────┘
         │
         ├───► [RED FLAG DETECTED] ──► (Branch to Flow 2: Emergency Halt)
         │
         ▼ [CLEAR: 0 RED FLAGS]
┌──────────────────────────────────────────────────┐
│ Step 2: Patient Context & Deterministic RAG      │
│ • Resolve PEP Permissions (Gym, Diet, Conditions)│
│ • Fetch Today's Scheduled Meal (Dinner/Lunch DB) │
│ • FTS5 BM25 match on active Clinical Rules       │
│ • Match Clinical Stances & Capability Bounds     │
│ • De-identify Patient Name -> [PATIENT_FIRST_NAME]
└────────┬─────────────────────────────────────────┘
         │
         ▼ (Grounding Context + Bounded Prompt <320 tokens)
┌──────────────────────────────────────────────────┐
│ Step 3: Bounded LLM Reasoning (<280ms)           │
│ • Groq LPU (Llama-3.3-70B-versatile)             │
│ • Fallback: Offline Mock Conversational Engine   │
└────────┬─────────────────────────────────────────┘
         │
         ▼ (Raw Model Text Stream)
┌──────────────────────────────────────────────────┐
│ Step 4: Atomic Sentence Barrier & Sanitizer     │
│ • Buffer first complete sentence                │
│ • Intercept false channel promises (WhatsApp)    │
│ • Enforce AI coach identity (Persona check)      │
│ • Enforce mandatory doctor-vetted remedy tokens  │
│ • EgressGate credential & ABHA ID scrubbing      │
│ • Re-hydrate patient name                        │
└────────┬─────────────────────────────────────────┘
         │
         ▼ (Sanitized Hinglish Text)
┌──────────────────────────────────────────────────┐
│ Step 5: Streaming Neural Audio Synthesis         │
│ • edge-tts (hi-IN-SwaraNeural)                   │
│ • Stream MP3 binary chunks (<250ms TTFB)         │
└────────┬─────────────────────────────────────────┘
         │
         ▼
[Patient Hears Conversational Hinglish Reply]
```

---

## 2. Flow 2: Acute Red-Flag Emergency Triage (<0.005ms Circuit Breaker)

Triggered when a patient reports acute cardiac, respiratory, neurological, obstetric, or psychiatric symptoms (e.g., *"Workout karte waqt seene mein dard aur left hand numb ho raha hai"* or *"Chhati mein dabav hai aur ulta haath sunn ho gaya"*).

```
[Patient Utterance Ingestion]
       │
       ▼
[PreTurnEmergencyCircuitBreaker.evaluate()]
       │
       ▼
[MATCH FOUND: 'cardiovascular' (seene mein dard, left hand numb)]
       │
       ├─────────────────────────────────────────┐
       ▼                                         ▼
[ABORT IN-CALL LLM GENERATION]        [PERSIST EMERGENCY RECORD]
(0ms LLM cost, 0 tokens emitted)      • Turn audit ledger: EMERGENCY_HALTED
       │                              • emergency_escalations: PENDING
       ▼                              • Dispatch Care Ops Webhook (Slack/SMS)
[EMIT CLINICAL 112 TRIAGE AUDIO]                 │
"Yeh symptoms serious ho sakte hain.             ▼
Kripya turant exercise band karein,   [CARE OPS COORDINATOR ALERTED]
112 par call karein ya hospital jayein." • Immediate on-duty doctor callback
```

---

## 3. Flow 3: Clinician Rule Authoring & Zero-Regression Pre-Publishing Gate

Enables non-technical doctors, dietitians, and fitness coaches to add or modify clinical rules within hours without engineering deployments or prompt bloat.

```
[Clinician opens Clinical Rule Studio UI]
       │
       ▼
[Inputs Rule Code, Category, Trigger Keywords, Approved Remedy, Clinical Rationale]
(e.g., RULE_ACIDITY_REMEDY: "Advise cold milk or chewing a basil leaf")
       │
       ▼
[Clicks 'Save Rule' (Triggers Pre-Publishing Gate)]
       │
       ▼
[AUTOMATED ZERO-REGRESSION SIMULATION GATE]
• Runs all 17 pinned golden benchmarks across the 8 production failure classes
• Asserts 100% Pass Rate
• Asserts 100% Emergency Recall
• Asserts P95 Turn Latency <1,200ms
       │
       ├───► [REGRESSION DETECTED]
       │     • Reject rule publication
       │     • Display exact failure diff to clinician
       │     • DB remains unmutated
       │
       ▼ [100% BENCHMARKS PASSED]
[COMMIT TO PRODUCTION SQLITE DATABASE]
• Trigger FTS5 index update
• Bump rule version number
• Rule active in live voice turns immediately
```

---

## 4. Flow 4: Patient Encounter Profile (PEP) & Dynamic Meal Plan Grounding

Prevents Failure #6 (hallucinating dinner) and Failure #7 (ignoring gym permissions).

```
[User Asks: "Aaj dinner mein kya hai mere diet chart ke hisaab se?"]
       │
       ▼
[PatientContextResolver.get_meal_plan(patient_id='pt_101', meal_type='dinner')]
       │
       ▼ (Queries patient_diet_plans in SQLite)
[Record Found: Wednesday Dinner]
"Paneer bhurji (150g), 2 multigrain rotis, cucumber salad (~420 kcal)"
       │
       ▼
[Prompt Builder Injects Structured Fact]
"Today's Dinner from DB: High-Protein Light Dinner: Paneer bhurji (150g)..."
       │
       ▼
[Model / Mock Engine Grounds Reply in Database Fact]
"Aaj aapke dinner mein 150g paneer bhurji, 2 multigrain rotis..."
```

---

## 5. Flow 5: Care Ops Escalation & Triage Dispatch

Ensures human-in-the-loop clinical governance when acute emergencies or out-of-scope conditions arise.

```
[Emergency Escalation Event Emitted]
       │
       ▼
[Webhook Dispatcher -> Care Ops Dashboard]
• Payload: {patient_id, phone, red_flag_category, detected_phrases, timestamp}
       │
       ▼
[Care Ops On-Call Nurse Screen]
• Audio recording of trigger turn highlighted in red
• One-click direct dial to patient and emergency contact (+919811002200)
• Status updated: PENDING -> DOCTOR_CALLED -> RESOLVED in SQLite audit ledger
```
