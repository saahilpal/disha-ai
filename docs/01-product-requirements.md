# 01. Product Requirements Document (PRD) — Disha Clinical Voice AI

## 1. Executive Summary & Problem Context

Disha is an AI-powered conversational health coach designed to conduct proactive, real-time voice follow-up calls in **Hinglish** (code-switched Hindi and English). These calls help patients manage chronic conditions, adhere to personalized eating and exercise plans (PEP), and stay engaged with their healthcare journeys.

To feel natural, conversational, and effective over standard cellular phone calls or WebRTC audio streams, Disha must operate under a strict **<1.0–2.0 second turn latency budget** (from user speech completion to Disha's first audio token).

### The Core Clinical & Operational Challenge
In live production reviews conducted by doctors and care coaches, critical failures were observed:
1. **Hallucinated Business Facts:** Inventing subscription prices when users inquire about pricing.
2. **Missed Clinical Remedies:** Providing generic platitudes for period bloating rather than the care team's verified clinical remedy (*jeera/saunf* water).
3. **False Capability Promises:** Promising to send diet charts over WhatsApp when WhatsApp is not an integrated delivery channel.
4. **Persona Violations:** Claiming to be a human coach when jokingly questioned by users, violating ethical and regulatory transparency requirements.
5. **Catastrophic Red-Flag Misses:** Treating acute symptoms (chest pain and left-arm numbness during a workout) as casual conversation instead of initiating an immediate medical emergency halt.
6. **Ignored Structured Data:** Guessing what is for dinner when the user's specific diet chart is already present in the database.
7. **Ignored Patient Encounter Profile (PEP):** Discouraging gym workouts despite the user's profile explicitly approving gym training.
8. **Clinical Stance Contradictions:** Arbitrarily banning fruits like mangoes for weight loss despite the clinical consensus advocating seasonal moderation.

### The Dynamic Invariant
New clinical nuances, food questions, and user conversational habits emerge every week. **Non-technical clinicians (doctors, dietitians, and coaches) must be able to add, update, and test system behaviors within hours—without waiting for software engineering deployments, without bloating the system prompt, and without regressing previous clinical fixes.**

---

## 2. Target Users & Stakeholders

| Persona | Role | Key Jobs to be Done | Needs & Pain Points |
| :--- | :--- | :--- | :--- |
| **Patient / End User** | Receiving proactive follow-up voice calls | Discuss diet adherence, log symptoms, get motivation, ask health questions in natural Hinglish. | Wants empathetic, clear, culturally attuned guidance without awkward delays or robotic hallucinations. |
| **Non-Technical Clinician** (Doctor, Dietitian, Coach) | Clinical Knowledge Author & Reviewer | Define vetted remedies, set dietary stances, establish red flags, review flagged call logs. | Cannot write code; needs an intuitive portal to create rules and preview them safely with zero fear of breaking other rules. |
| **Care Ops / Emergency Triage Team** | Safety Escalation Monitor | Receive immediate alerts when patients exhibit red flags (chest pain, severe dyspnea, acute distress). | Needs real-time, deterministic alerts with patient context and call recordings for immediate human handover. |
| **Engineering & AI Systems Lead** | Platform Reliability & Governance | Maintain system latency (<1.5s), zero-cost infrastructure, high availability, and regression-proof deployments. | Needs deterministic guardrails ("Thick Deterministic Spine"), prompt isolation, and automated CI/CD evaluation test harnesses. |

---

## 3. Product Goals & Success Metrics

### Primary Goals
1. **Zero Clinical Harm:** 100% recall on critical emergency symptoms (chest pain, left-arm numbness, respiratory distress, fainting). Zero tolerance for missed red flags.
2. **Strict Turn Latency Budget:** Total conversational turn latency (STT + Guardrail/Retrieval + LLM TTFT + TTS playback start) maintained strictly below **1.2 seconds** at P50 and **1.8 seconds** at P95.
3. **Clinician Autonomy:** Non-technical doctors and dietitians can author, simulate, regression-test, and publish a new clinical rule within **<30 minutes** with **zero engineering assistance**.
4. **Context-Grounded Precision:** Zero hallucinated pricing, zero capability hallucinations (e.g. WhatsApp), zero contradiction of PEP profile, and accurate retrieval of patient DB records (diet charts).
5. **Zero-Cost Production-Ready Architecture:** 100% feasible on free-tier infrastructure, open-source local inference, and zero credit-card dependencies during development, testing, and initial rollout.

### Key Performance Indicators (KPIs)

| Metric | Target | Measurement Method |
| :--- | :--- | :--- |
| **Emergency Red-Flag Catch Rate** | **100.0%** (Zero misses) | Deterministic keyword/Aho-Corasick & regex pre-turn circuit breaker. |
| **P95 Turn Latency (Text-to-Audio)** | **< 1,200 ms** | Turn timestamp logs (Audio end $\rightarrow$ Audio playback). |
| **Clinical Rule Regression Rate** | **0.0%** | Automated synthetic oracle test suite run before rule publishing. |
| **Factual Hallucination Rate** | **< 0.5%** | Post-turn schema assertion and ground-truth verification audits. |
| **Clinician Publishing Velocity** | **< 15 minutes** | Time from clinical review observation to verified live rule rollout. |
| **Infrastructure Cost per Call Minute** | **$0.00** (Free Tier / Local) | Free-tier usage tracking and unit economics projection. |

---

## 4. Problem Decomposition & Failure Classes

To prevent ad-hoc prompt patches, all system failures are partitioned into three fundamental technical classes:

```
                          ┌─────────────────────────────────────┐
                          │    Production Clinical Failures     │
                          └──────────────────┬──────────────────┘
                                             │
         ┌───────────────────────────────────┼──────────────────────────────────┐
         │                                   │                                  │
         ▼                                   ▼                                  ▼
 ┌───────────────┐                   ┌───────────────┐                  ┌───────────────┐
 │ Class A:      │                   │ Class B:      │                  │ Class C:      │
 │ Wrong         │                   │ Missed        │                  │ Missing       │
 │ Statements    │                   │ Actions       │                  │ Facts         │
 └───────┬───────┘                   └───────┬───────┘                  └───────┬───────┘
         │                                   │                                  │
   • False capabilities (WhatsApp)     • Missed remedies (Bloating)       • Hallucinated pricing
   • Persona violation (Claims human)  • Missed red flags (Chest pain)    • Ignored DB diet chart
   • Stance conflict (Banning mangoes) • Ignored PEP status (Gym access)  • Patient history gap
```

### Class A: Wrong Statements (Active Hallucinations & Boundary Violations)
- **Problem:** The model asserts false facts, unauthorized channel capabilities, or violates its AI identity.
- **Architectural Solution:** Dual-layer defense: Negative constraint prompt injection + Deterministic Post-Turn Interceptor (Regex & keyword sanitizer that halts or rewrites violating sentences before TTS synthesis).

### Class B: Missed Actions (Clinical Protocols, Emergencies, Personalization)
- **Problem:** The model acts as a passive conversationalist, failing to enforce clinical care plans, red-flag escalation, or prescribed lifestyle remedies.
- **Architectural Solution:** Pre-turn Intent & Symptom Detector. Emergency triggers completely bypass the probabilistic LLM with a 0ms deterministic safety script. Clinical remedy triggers inject mandatory directives (*"Advise warm jeera-saunf water"*).

### Class C: Missing Facts (Static System Truths & Dynamic Patient Context)
- **Problem:** The model is asked about user-specific data (dinner chart) or business specifics (pricing) that were never provided in the turn context.
- **Architectural Solution:** Just-in-Time (JIT) Context Retrieval. The system dynamically queries the Patient DB (today's dinner) and the Business Knowledge Base (pricing tiers) and injects structured key-value facts into the turn prompt.

---

## 5. Scope & Functional Boundaries

### In Scope
1. **Real-Time Voice Pipeline Simulation & Execution:** Full end-to-end processing across STT, Pre-Turn Guardrails, Context Assembler, LLM Inference, Post-Turn Sanitizer, and TTS Audio Generation.
2. **Hinglish Conversational Understanding:** Semantic recognition of Romanized Hinglish idioms, symptoms, food items, and conversational turns (*"pet phoolna"*, *"seene mein dard"*, *"aam kha sakte hain kya"*, *"WhatsApp par bhej do"*).
3. **Clinical Rule Authoring Studio:** A web-based visual portal enabling clinicians to create, edit, test, and activate clinical protocols, stances, and symptom remedies without code deployments.
4. **Zero-Regression Simulation Harness:** An automated test runner that executes historical conversation suites against candidate clinical rules to guarantee no existing behaviors regress.
5. **Emergency Circuit Breaker:** Instant deterministic triage (<5ms) for emergency symptoms with automatic audio override and care team escalation webhook generation.
6. **Patient Data & PEP Grounding:** Structured schema for Patient Encounter Profiles (PEPs), dietary records, and meal plans with automatic turn-level grounding.

### Out of Scope (Explicitly Excluded)
1. **Diagnostic Medical Decisions:** Disha is an adherence and habit coach. She explicitly never diagnoses illnesses or prescribes prescription pharmaceuticals.
2. **Telephony Hardware (PBX/PSTN Trunks):** The system provides standard WebSocket/WebRTC audio streams compatible with Twilio/Exotel/Plivo, but physical telecom contracts are external.
3. **Payment Processing:** Disha provides official pricing information but does not execute credit card transactions on the voice call.
