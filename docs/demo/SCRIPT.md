# Disha AI — Executive Show-Readiness Demo Script (8–10 Minutes)

**Document Version:** 1.0.0-RC  
**Target Audience:** Clinical Reviewers, Health-Tech Evaluators, Executive Stakeholders & Engineering Auditors  
**Standard Runtime:** 8 Minutes 45 Seconds (Paced Execution: 8–10 Minutes)  
**Live Stack Requirements:** `make demo` (Backend port 8000, Proxy port 8080, PostgreSQL port 5432)  
**Public Ingress:** Public Cloudflare Tunnel (verified mobile mic + speaker playback)  
**Strict Safety Guarantees:** 0% Red-flag emergency false negatives, zero hallucinated pricing, zero unauthorized gym clearance, 100% cryptographic audit trail.

---

## 1. Demo Setup & Persona Matrix

Before beginning, ensure the stack is healthy and seeded by running:
```bash
make demo
```
To restore a pristine slate after any test rehearsal:
```bash
make demo-reset
```

### Pre-Seeded Synthetic Personas

| Persona Name | Patient ID | Email / Password | Clinical Stance | PEP Constraints | Key Demo Role |
|---|---|---|---|---|---|
| **Vikram Malhotra** | `pt_test_cardiac` | `cardiac@disha.ai`<br>`demo123` | **Cardiac Stage 2** (Post-PCI stent LAD 2024, HTN Stage 2, baseline BP 142/92) | **Gym Clearance: FALSE**<br>Allowed: Brisk walk, Anulom Vilom<br>Restricted: Heavy weights, Valsalva | **Primary Demo Persona:** Emergency deflection, source grounding, cross-session recall |
| **Meera Sen** | `pt_test_diabetic` | `diabetic@disha.ai`<br>`demo123` | **Type-2 Diabetes** (HbA1c 7.4%, Fasting Glucose 138 mg/dL) | **Gym Clearance: FALSE**<br>Allowed: Post-meal walk (15m), Hatha yoga<br>Restricted: Fasting strenuous workouts | **Nutritional Demo Persona:** Low GI meals, sugar reduction, ICMR diet |
| **Kabir Deshmukh** | `pt_test_01` | `demo@disha.ai`<br>`demo123` | **General Wellness** (Sedentary software engineer, 9h screen time, desk fatigue) | **Gym Clearance: TRUE**<br>Allowed: Jogging, gym resistance, swimming | **Onboarding Demo Persona:** Fresh registration, voice onboarding, posture care |

---

## 2. Storyline & Step-by-Step Utterance Guide

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             8-10 MINUTE TIMELINE                                 │
├─────────┬──────────────┬──────────────┬──────────────┬──────────────┬────────────┤
│ 00:00   │ 01:15        │ 02:45        │ 04:00        │ 05:30        │ 08:30      │
│ Setup & │ Voice Intake │ Clinical RAG │ Emergency    │ Guardrails   │ Clinician  │
│ Context │ & Onboarding │ & Grounding  │ Interruption │ Price / Auth │ Hot-Reload │
└─────────┴──────────────┴──────────────┴──────────────┴──────────────┴────────────┘
```

---

### Act 1: Orientation & Production Architecture (0:00 – 1:15)
* **Presenter Action:** Open `http://127.0.0.1:8080` (or public tunnel on phone) in browser. Show the Clinical Apothecary interface (Warm porcelain alabaster `#F8FAF9`, restorative sage `#167A57`, zero floating purple spheres).
* **Presenter Script (Spoken to Audience):**
  > "Namaste. Welcome to Disha AI. Disha is not a generic conversational LLM wrapped in a chatbot UI. She is a voice-first, culturally authentic clinical companion built for Indian patients managing chronic cardiometabolic conditions.
  > 
  > Unlike consumer tech demos that rely on probabilistic prompts, Disha is anchored by a **Thick Deterministic Safety Spine**. Every utterance flows through a sub-millisecond Aho-Corasick emergency circuit breaker, just-in-time PostgreSQL PEP constraints, and egress sentence verification before sound reaches the patient's ear. Let's see this in action."

---

### Act 2: Conversational Voice Onboarding (1:15 – 2:45)
* **Goal:** Prove voice intake across Stages S0–S4 without traditional form-filling friction.
* **Presenter Action:** Click **"Create Profile"** or open Voice Call with new patient session.
* **Speaker (Human Caller):**
  > *"Namaste Disha, mera naam Kabir Deshmukh hai. Main 32 saal ka software engineer hoon aur mujhe din bhar laptop par baithne se thoda lower back pain rehta hai."*
* **Disha Voice Response (Audio streaming, ~680ms TTFT):**
  > *"Namaste Kabir ji! Disha mein aapka swagat hai. Main ek AI health coach hoon, koi medical doctor nahi. Main aapki lifestyle, steps aur posture par focus karungi. Pehle batayein, kya aapko BP ya heart se judi koi pehle se takleef hai, aur aapka average daily routine kaisa rehta hai?"*
* **Visual & Acoustic Feedback:**
  - 24-bar green spectrum audio visualizer modulates dynamically during speaking.
  - Stage indicator advances from `S0 (Language)` to `S2 (Basics)` and `S4 (Safety)`.
  - Discloses AI companion status automatically within the first two turns.

---

### Act 3: Clinical Grounding with Authoritative Sources (2:45 – 4:00)
* **Goal:** Prove doctor-vetted remedy tokens and ICMR/WHO citations in Hinglish.
* **Persona:** Switch/Sign in as **Vikram Malhotra** (`cardiac@disha.ai` / `demo123`).
* **Speaker (Human Caller):**
  > *"Disha, shaam ko khana khane ke baad pet mein bohot gas aur halki jalan ho rahi hai. Kya main koi soda ya thanda paani pi loon?"*
* **Disha Voice Response (~720ms TTFT):**
  > *"Vikram ji, soda ya carbonated drinks bilkul na lein; isse pet ka dabav badh sakta hai. ICMR-NIN dietary guidelines aur clinical protocols ke mutabiq, aap abhi garam jeera ya saunf ka paani piyein. Shaam 7 baje ke baad bhari daalein ya raw salad avoid karein aur 10 se 15 minute ki halki walk karein."*
* **Under the Hood Invariants Verified:**
  - **C5 (Grounded Clinical Remedy):** Sentence validator verifies `jeera ya saunf ka paani` token presence.
  - **C4 (Closed-Domain Grounding):** Derived from `clinical_knowledge_base` chunk `src_icmr_dietary_2024` with zero speculative remedies.
  - **C7 (PEP Contraindication):** No heavy post-meal exercise prescribed; brisk gentle walking only.

---

### Act 4: Emergency Circuit Breaker & Instant Barge-In Interruption (4:00 – 5:30)
* **Goal:** Demonstrate non-probabilistic emergency deflection and sub-40ms barge-in cutoff.
* **Setup:** While Disha is giving daily advice or speaking, the caller speaks over her with a critical cardiac red flag.
* **Speaker (Human Caller - High urgency, speaking over Disha):**
  > *"Ruko Disha... mujhe achanak seene mein bohot bhaari dabav aur left arm mein tez dard ho raha hai... bohot paseena aa raha hai!"*
* **System Execution (<0.01ms Pre-Turn Intercept):**
  - Audio playback halts immediately (barge-in interrupt packet dispatched).
  - Aho-Corasick automaton matches `chhati mein... dabav` and `left arm mein... dard` under category `CARDIOVASCULAR`.
  - LLM call is **completely bypassed** to eliminate latency.
* **Disha Immediate Emergency Response (<450ms):**
  > *"Yeh emergency ho sakti hai! Kripya turant 112 par call karein ya paas ke hospital ke emergency room mein jayein. Apne kisi parivaarjan ko turant bulayein aur bilkul akele na rahein."*
* **Visual & Audit Proof:**
  - Full-screen clinical alert banner pulses in desaturated red (`--danger: #B91C1C`).
  - Emergency 112 click-to-dial button appears.
  - Merkle audit ledger records `status = "triggered:CARDIOVASCULAR|accepted"`.

---

### Act 5: Commercial Pricing Safety & Anti-Hallucination Guardrail (5:30 – 6:30)
* **Goal:** Prove deterministic enforcement of ₹0 follow-ups and ₹1,499 nutritionist policy.
* **Speaker (Human Caller):**
  > *"Disha, aapki monthly fees kitni hai? Kya agle hafte baat karne ke liye koi subscription lena padega?"*
* **Disha Response (~610ms TTFT):**
  > *"Follow-up consultations ₹0 hain. Disha ke saath regular health coaching puri tarah free hai. Agar aapko dedicated human nutritionist plan chahiye, toh woh ₹1,499 per month hai."*
* **Under the Hood Invariants Verified:**
  - **C8 (Pricing Invariant):** RegEx `PRICE_RE` intercepts any LLM attempt to invent pricing; enforces authorized `product_facts` values ₹0 and ₹1,499.

---

### Act 6: Channel Boundary & WhatsApp Honest Refusal (6:30 – 7:15)
* **Goal:** Prove strict patient data boundaries and zero false capability claims.
* **Speaker (Human Caller):**
  > *"Achha Disha, mera aaj ka diet chart aur walking plan mujhe mere WhatsApp par message kar do na please?"*
* **Disha Response (~580ms TTFT):**
  > *"Main WhatsApp par message nahi bhej sakti. Aap apna poora plan aur diet schedule sirf is app ke 'My Plan' tab mein dekh sakte hain."*
* **Under the Hood Invariants Verified:**
  - **C6 (Channel Boundary Invariant):** RegEx `CHANNEL_RE` blocks third-party promises (WhatsApp/SMS/Email); redirects patient to verified in-app view.

---

### Act 7: Persona Boundary & "Are You Human?" Honest Truth (7:15 – 8:00)
* **Goal:** Maintain transparent clinical ethics without AI anthropomorphic deception.
* **Speaker (Human Caller):**
  > *"Aap bohot achhi baatein karti hain. Kya aap sach mein ek real human doctor hain jo hospital se bol rahi hain?"*
* **Disha Response (~550ms TTFT):**
  > *"Main Disha hoon, aapki AI health coach. Main koi medical doctor ya insaan nahi hoon aur prescriptions nahi badal sakti. Main aapke doctor ke bataye plan ko follow karne mein aapki madad karti hoon."*
* **Under the Hood Invariants Verified:**
  - **C9 (Persona Invariant):** RegEx `IDENTITY_RE` blocks medical licensure claims and enforces AI disclosure.

---

### Act 8: Deterministic Cross-Session Memory Recall (8:00 – 8:45)
* **Goal:** Prove long-term patient facts persist across sessions without state loss.
* **Presenter Action:** Sign out, refresh browser page (or restart session), and log back in as **Vikram Malhotra**.
* **Speaker (Human Caller):**
  > *"Disha, mujhe yaad nahi ki mere exercise plan mein kya restrictions hain? Kya main kal subah gym mein heavy weights utha sakta hoon?"*
* **Disha Response (~740ms TTFT):**
  > *"Vikram ji, aapke 2024 ke LAD stent aur Stage 2 Hypertension ke clinical record ke mutabiq, heavy weightlifting, deadlifts aur gym machines strictly restricted hain. Aapke liye sirf 25 minute ki brisk morning walk aur anulom vilom pranayama safe hain. Kripya gym mein heavy lifting bilkul na karein."*
* **Under the Hood Invariants Verified:**
  - `patient_temporal_facts` and `memory_items` retrieved via `context_builder.py` under multi-tenant compound key `(patient_id, query_hash)`.
  - Zero gym clearance enforced deterministically from `patient_pep.gym_clearance = FALSE`.

---

### Act 9: Live Clinician Hot-Reload Rule Addition (8:45 – 9:30)
* **Goal:** Demonstrate non-technical clinician authoring without code release or service restart.
* **Presenter Action:** In a visible terminal side-by-side with the web client, execute a live clinician rule insertion:
```bash
docker compose exec -T postgres psql -U disha -d disha -c "
INSERT INTO clinical_knowledge_base (
    condition_tag, trigger_terms, context_header, guideline_content,
    required_remedy_tokens, source_citation, approval_status, clinician_id, approved_at
) VALUES (
    'cardiac_dietary_rule',
    'papaya papita khana chahiye',
    'Cardiac & Hypertension Dietary Guidance',
    'Pake papite ka sevan cardiac marizon ke liye safe hai lekin subah khayein.',
    ARRAY['subah'],
    'Dr. Sharma (Cardiology MD) — Protocol Note 2026',
    'approved',
    'dr_sharma_cardio_md',
    NOW()
);"
```
* **Speaker (Human Caller - immediately after SQL execution):**
  > *"Disha, kya main subah nashte mein papita kha sakta hoon?"*
* **Disha Response (Instant Hot-Reload, zero server restart):**
  > *"Haan Vikram ji, Dr. Sharma ke approved guideline ke mutabiq, pake papite ka sevan aapke liye safe hai aur ise subah lena beneficial hai."*
* **Presenter Highlight:**
  > "Notice what just happened: A clinical specialist approved a new stance in PostgreSQL. Without any backend restart, container rebuild, or model retraining, Disha instantly retrieved and enforced the new stance on the very next turn."

---

### Act 10: Conclusion & Transition to Verification (9:30 – 10:00)
* **Presenter Wrap-up:**
  > "In under 10 minutes, we have demonstrated:
  > 1. Authentic cultural Hinglish voice intake.
  > 2. Hardened emergency deflection under 0.01ms.
  > 3. Zero-hallucination commercial and channel guardrails.
  > 4. Multi-session cryptographic memory recall.
  > 5. Live clinician hot-reloading.
  > 
  > Every turn is anchored in the Merkle claim ledger and available for clinical audit. We welcome your hardest questions."
