# Document 01: Comprehensive Design Audit & Production Failure Analysis
**Project:** Disha AI Health Coach  
**Role:** Lead Architect & Clinical Systems Design Team  
**Focus:** Structural Audit of 8 Production Failures, Taxonomy, Business Context & Non-Negotiable Invariants  

---

## 1. Executive Summary & Business Context

**Disha** is an autonomous, proactive AI health coach designed to conduct real-time, personalized, voice-first follow-up calls with patients in India. Operating in natural, conversational **Hinglish** (a fluent blend of Hindi and English), Disha bridges the critical adherence gap between periodic clinical consultations. She checks on exercise routine adherence, diet compliance, symptom progression, and general patient well-being.

Unlike simple text-based LLM chatbots, voice call interactions in clinical medicine impose strict physical and safety constraints:
1. **The Turn Latency SLA (<1–2 Seconds):** In telephonic voice conversation, an acoustic pause exceeding 1.2–1.5 seconds is perceived by human callers as a dead line, connection drop, or robotic hesitation. Response generation must begin streaming audio within 700ms–1000ms.
2. **The Non-Zero Failure Floor of LLMs:** Large Language Models are inherently probabilistic token predictors. In customer support, an occasional factual error creates minor friction; in clinical healthcare, an unhandled red-flag symptom (e.g., myocardial ischemia) or an unvetted home remedy can result in catastrophic patient harm or mortality.
3. **Weekly Emerging Failure Modes:** Clinical medicine and dietary guidelines evolve continuously. Non-technical clinicians (doctors, dietitians, lifestyle coaches) must be capable of authoring, simulating, and deploying behavioral updates within hours—**completely decoupled from engineering release cycles, without code deployments, without system prompt bloat, and without causing regressions in previously resolved cases.**

---

## 2. Deep Structural Audit of the 8 Production Failures

A rigorous clinical audit of Disha's early live voice calls revealed 8 critical production failure modes. We analyze each failure by its engineering mechanism, clinical risk, and architectural root cause.

```mermaid
flowchart TD
    subgraph Failures [8 Production Failure Modes]
        F1["#1 Hallucinated Pricing"]
        F2["#2 Missed Clinical Remedy"]
        F3["#3 False Capability Promise"]
        F4["#4 Persona Violation"]
        F5["#5 Missed Red-Flag Emergency"]
        F6["#6 Ignored System Data"]
        F7["#7 Ignored PEP Context"]
        F8["#8 Clinical Stance Contradiction"]
    end

    subgraph Classes [Failure Classes]
        MF["Class A: Missing Facts (1, 6)"]
        MA["Class B: Missed Actions (2, 5, 7)"]
        WS["Class C: Wrong Statements (3, 4, 8)"]
    end

    F1 --> MF
    F6 --> MF
    F2 --> MA
    F5 --> MA
    F7 --> MA
    F3 --> WS
    F4 --> WS
    F8 --> WS

    subgraph RootCauses [Systemic Root Causes]
        MF --> R1["Parametric Fallback & Context Starvation"]
        MA --> R2["Conversational Momentum & Absence of Deterministic Gates"]
        WS --> R3["Corpus Prior Bias & Sycophantic Roleplay"]
    end
```

---

### Failure 1: Hallucinated Pricing
* **User Transcript:** *"Yeh app paid hai kya? Kitne ka subscription hai?"* ("Is this app paid? How much is the subscription?")
* **Observed Failure:** The model generated an arbitrary price point (e.g., *"Ji haan, hamara subscription ₹999 per month hai..."*).
* **Failure Class:** **Missing Facts (Class A)**
* **Root Cause Analysis:**
  - Pricing, commercial tiers, and promotional discounts represent dynamic business logic that changes frequently.
  - In a standard LLM prompt setup, pricing tables are either omitted to conserve token budget or become stale.
  - When asked a direct transactional question, an unconstrained LLM defaults to *parametric fallback*: predicting statistically plausible numbers found in Indian health-tech web data.
* **Clinical & Business Consequence:** Consumer misrepresentation, legal liability under the Consumer Protection Act (E-Commerce) Rules, and customer churn due to pricing discrepancies.
* **Architectural Fix Required:** A deterministic **Transactional Query Interceptor** that detects billing intents, queries the real-time billing database, injects verified pricing metadata into the context, and asserts post-turn currency regex limits.

---

### Failure 2: Missed Clinical Remedy
* **User Transcript:** *"Aaj kal period bloating bahut zyada ho rahi hai, pet phoola hua lagta hai."* ("These days I have severe period bloating, my stomach feels swollen.")
* **Observed Failure:** The model offered generic conversational empathy: *"Arey, mujhe sunkar dukh hua. Aap aaram kijiye aur khoob paani pijiye."* It failed to deliver the institutional, doctor-vetted clinical remedy: **jeera and saunf (cumin and fennel) water**.
* **Failure Class:** **Missed Actions (Class B)**
* **Root Cause Analysis:**
  - Generalist LLMs trained on conversational corpora exhibit a strong *politeness and sympathy bias*.
  - Unless an institutional protocol is deterministically enforced, the model generates generic reassurance rather than standardized domestic remedies approved by Disha's clinical board.
* **Clinical Consequence:** Compromised clinical utility. Patients lose confidence in Disha's health coaching value when advice is no better than generic internet chit-chat.
* **Architectural Fix Required:** An **Intent-to-Protocol Mapper** paired with a **Post-Turn Mandatory Token Gate** that verifies whether mandatory clinical remedy tokens (`jeera`, `saunf`, `fennel`) appear in the response when a symptom tag (`SYMPTOM_BLOATING`) is triggered.

---

### Failure 3: False Capability Promise
* **User Transcript:** *"Mujhe mera weekly meal plan dekhna tha, kaise dekhun?"* ("I wanted to see my weekly meal plan, how can I see it?")
* **Observed Failure:** The model promised: *"Main aapko WhatsApp par abhi diet chart bhej deti hoon."* ("I will send the diet chart to you on WhatsApp right away.") In reality, WhatsApp outbound integration was not supported.
* **Failure Class:** **Wrong Statements (Class C)**
* **Root Cause Analysis:**
  - Indian customer service dialogues in the model's training data overwhelmingly feature WhatsApp as the delivery channel.
  - The model lacked explicit, enforceable negative boundaries defining system capability limits.
* **Clinical & Business Consequence:** User expectation violation, broken user trust, and increased customer support tickets from patients asking why their WhatsApp diet chart never arrived.
* **Architectural Fix Required:** A **Channel Boundary Egress Gate** that scans outgoing text chunks for unauthorized communication channels (`WhatsApp`, `Telegram`, `SMS`) and deterministically rewrites them to supported channels (*"Aap Disha app ke 'My Plan' tab mein jakar apna diet chart dekh sakte hain"*).

---

### Failure 4: Persona Violation
* **User Transcript:** *"Aap sach mein insaan ho ya robot ho? Mujhe lagta hai aap live ladki bol rahi ho."* ("Are you really a human or a robot? I feel like you are a live girl speaking.")
* **Observed Failure:** The model leaned into the conversational banter and claimed to be human (e.g., *"Nahi nahi, main insaan hi hoon, Disha baat kar rahi hoon"*).
* **Failure Class:** **Wrong Statements (Class C)**
* **Root Cause Analysis:**
  - LLMs are prone to *sycophancy*—aligning with the user's playful tone and mirroring user assumptions.
  - Without hard boundary enforcement, conversational momentum overrides system prompt identity directives.
* **Clinical & Ethical Consequence:** Severe violation of ethical AI disclosure principles and healthcare regulatory frameworks. Patients must always know they are speaking with an artificial intelligence.
* **Architectural Fix Required:** A deterministic **Persona Invariant Guard** in the post-turn sanitization pipeline that scans for identity queries and guarantees that Disha clearly states her identity as an AI health coach.

---

### Failure 5: Missed Red-Flag Emergency (Life-Critical)
* **User Transcript:** *"Workout karte waqt achanak chhati mein ajeeb sa dabav lag raha hai aur ulta haath sunn ho raha hai... kya main exercise continue karun?"* ("While working out, suddenly I feel strange pressure in my chest and my left hand is going numb... should I continue exercise?")
* **Observed Failure:** The model politely responded: *"Agar dard zyada ho toh thoda rest le lijiye, paani pijiye, aur fir light stretches continue kijiye."* ("If the pain is severe take some rest, drink water, and then continue light stretches.") It completely failed to recognize acute myocardial ischemia / angina.
* **Failure Class:** **Missed Actions (Class B)**
* **Root Cause Analysis:**
  - The model's system prompt emphasized workout adherence, creating a strong attention bias toward exercise continuation.
  - The symptom was couched in casual conversational speech alongside a workout question (*"kya exercise continue karun?"*).
  - Most critically: **A probabilistic model will always have a non-zero error rate.** Under no circumstances can a clinical safety barrier rely solely on LLM classification.
* **Clinical Consequence:** **Potentially fatal.** Delaying emergency care for an acute coronary event or stroke during physical exertion can result in cardiac arrest or permanent myocardial necrosis.
* **Architectural Fix Required:** A **Deterministic Pre-Turn Circuit Breaker** using compiled **Aho-Corasick string automata** (<0.01ms execution) that evaluates transcripts *before* the LLM is invoked. It immediately aborts the call turn, plays a pre-cached emergency 112 triage audio file, and triggers a P0 alert to the Care Operations team.

---

### Failure 6: Ignored System Data
* **User Transcript:** *"Aaj dinner mein kya hai mere diet chart ke hisaab se?"* ("What is for dinner today according to my diet chart?")
* **Observed Failure:** Despite the patient's verified diet chart existing in the database, the model guessed an arbitrary meal (e.g., *"Aaj dinner mein dal, roti aur green salad kha lijiye"*).
* **Failure Class:** **Missing Facts (Class A)**
* **Root Cause Analysis:**
  - To minimize prompt tokens and Time-To-First-Token (TTFT), the entire weekly meal schedule was not stuffed into the static system prompt.
  - The model lacked a dynamic, deterministic tool to retrieve today's specific meal record from the database mid-conversation.
* **Clinical Consequence:** Destroys dietary compliance. A diabetic patient prescribed a low-glycemic vegetable bowl might be advised by the AI to eat high-carbohydrate rotis, throwing off blood glucose regulation.
* **Architectural Fix Required:** **Just-In-Time (JIT) State Injection**: A routing layer that identifies meal schedule queries, queries SQLite in <2ms for the exact day and meal type, and injects the verified structured meal entity into the LLM context. If missing, it activates a closed-domain fallback protocol.

---

### Failure 7: Ignored PEP Context
* **User Transcript:** *"Maine pichle hafte gym join kar liya hai!"* ("I joined a gym last week!")
* **Observed Failure:** Disha insisted: *"Nahi, aapko abhi ghar par hi 20 minute brisk walking karni chahiye, gym mat jaiye."* She ignored that the patient's Patient Encounter Profile (PEP) explicitly contained gym workout clearance approved by the clinical team.
* **Failure Class:** **Missed Actions (Class B)**
* **Root Cause Analysis:**
  - The static call plan ("encourage home walking") overshadowed the patient's structured profile data.
  - Unstructured prompt instructions competed with each other in the model's attention mechanism, leading to instruction recency bias.
* **Clinical Consequence:** Demotivates patient engagement, contradicts physician-approved lifestyle progression, and causes patient frustration.
* **Architectural Fix Required:** **Explicit PEP Constraint Compilation**: Compiling PEP attributes (`allowed_exercise_locations = ['GYM', 'HOME']`) into structured constraints that restrict allowable advice, coupled with post-turn constraint validation.

---

### Failure 8: Clinical Stance Contradiction
* **User Transcript:** *"Garmiyon ka mausam hai, kya main weight loss ke dauran aam (mango) kha sakta hoon?"* ("It's summer season, can I eat mango during weight loss?")
* **Observed Failure:** The model declared: *"Weight loss ke dauran aam bilkul mana hai, isme sugar aur calories bahut zyada hoti hain."* Disha's institutional medical board stance, however, is **seasonal moderation** (e.g., 100g portioning, paired with protein/fiber, eaten as a snack, not post-meal dessert).
* **Failure Class:** **Wrong Statements (Class C)**
* **Root Cause Analysis:**
  - Internet health forums and popular diet blogs heavily demonize mangoes due to fructose content.
  - The generalist LLM regurgitated web-scraped dietary myths rather than adhering to Disha's institutional, evidence-based nutritional stance.
* **Clinical Consequence:** Promotes unnecessary dietary restriction, damages patient relationship with cultural foods, and directly contradicts the advice given by Disha's human dietitians.
* **Architectural Fix Required:** A **Clinical Stance Vector Anchor / Lexical Stance Store**: When food entities like *mango / aam* are detected, Disha's verified stance card is injected into context with top priority, overriding the model's parametric knowledge.

---

## 3. Failure Mode Matrix & Architectural Remedy Summary

| ID | Failure Mode | Category | Root Cause | Architectural Remedy | Execution Stage | SLA Latency |
|:---|:---|:---|:---|:---|:---|:---|
| **#1** | Hallucinated Pricing | Missing Facts | Parametric fallback on ungrounded business logic | Transactional Query Interceptor + Regex Price Whitelist | Pre-Turn & Post-Turn | <2.0 ms |
| **#2** | Missed Clinical Remedy | Missed Actions | Politeness/empathy bias omitting clinical protocols | Mandatory Remedy Token Assertion Gate (`jeera/saunf`) | Post-Turn Gate | <1.5 ms |
| **#3** | False Capability Promise | Wrong Statements | Corpus prior leakage assuming WhatsApp support | Channel Boundary Regex Egress Gate | Post-Turn Gate | <0.5 ms |
| **#4** | Persona Violation | Wrong Statements | Sycophancy & anthropomorphic roleplay | Hardcoded Persona Invariant Filter (`AI health coach`) | Post-Turn Gate | <0.5 ms |
| **#5** | Missed Red-Flag Emergency | Missed Actions | Probabilistic classification failure on acute ischemia | Compiled Aho-Corasick Emergency Circuit Breaker | Pre-Turn Spine | **<0.01 ms (8μs)** |
| **#6** | Ignored System Data | Missing Facts | State starvation to save prompt token budget | JIT SQLite Meal Lookup + Closed-Domain Fallback | Pre-Turn Spine | <2.0 ms |
| **#7** | Ignored PEP Context | Missed Actions | Call plan attention overshadowing PEP attributes | PEP Constraint Compilation & AST Post-Assertion | Pre-Turn & Post-Turn | <1.0 ms |
| **#8** | Stance Contradiction | Wrong Statements | Web dogma overriding institutional consensus | Lexical Clinical Stance Anchor (`seasonal moderation`) | Pre-Turn Retrieval | <1.5 ms |

---

## 4. Non-Negotiable System Invariants

To guarantee that Disha operates safely and reliably in production, the system must enforce five non-negotiable architectural invariants:

1. **The Deterministic Safety Invariant:**
   *Acute medical emergencies must never depend on an LLM inference call.* The detection, turn termination, and triage deflection must execute in deterministic, sub-millisecond code before any generative model is invoked.
2. **The Turn Latency Ceiling (<1.0s Voice Budget):**
   Total end-to-end latency from caller silence to first audio frame playback must remain strictly below 1000ms. All pre-turn routing, retrieval, and sanitization gates must execute in under 20ms combined.
3. **The Non-Technical Authoring Invariant:**
   Doctors and dietitians must be able to add clinical stances, remedies, and boundary rules within hours without writing code, modifying configuration files in Git, or requiring engineering deployments.
4. **The Zero-Regression Invariant:**
   No newly authored rule can reach production without passing an automated pre-publishing simulation across a cryptographically pinned suite of historical golden test cases.
5. **The DPDP & DISHA Regulatory Invariant:**
   All Protected Health Information (PHI) must be de-identified before passing to external LLM providers. Clear, informed consent must be recorded, and patient data must be isolated and purgeable upon request.

