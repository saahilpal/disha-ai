# Disha AI — Codebase Hardcode Knowledge & Rule Audit

**Auditor:** Knowledge Engineer (Master Order v4)  
**Target Codebase:** `disha_core/`  
**Governing Standard:** Loop 1 Foundation & Database Migration  
**Date:** 2026-11-08  

---

## 1. Audit Scope & Objective

This audit identifies all clinical rules, home remedies, food lists, workout/exercise clearance mappings, product pricing, feature capabilities, and persona constraints hardcoded into Python source files (`.py`) or system prompts instead of being dynamically loaded from PostgreSQL tables (`clinical_guideline_chunks`, `product_facts`, `knowledge_chunks`).

Hardcoded business and clinical logic creates compliance risks, impedes runtime updates, prevents clinician audits, and duplicates data across modules.

---

## 2. Hardcode Findings by Module

### Finding 1: Commercial Pricing & Subscription Plan Facts
- **Source File:** `disha_core/pipeline/validator.py` (Lines 18–26, 100, 121–133) and `disha_core/llm/client.py` (Line 14)
- **Hardcoded Content:**
  - `PRICING_REPLACEMENT = "Follow-up consultations ₹0 hain; dedicated nutritionist plan ₹1,499 per month hai."`
  - In `_allowed_price()`: `value == 1499 and bool(MONTHLY_RE.search(text))` and `value == 0`.
  - In `SYSTEM_PROMPT`: `"Never invent prices: follow-ups with Disha are ₹0, and a dedicated nutritionist plan is ₹1,499/month."`
- **Category:** Commercial / Pricing Facts.
- **Risk / Architectural Issue:** If Disha launches a seasonal discount, regional pricing tier, or annual subscription, updating prices requires modifying Python regexes and redeploying the Docker image.
- **Migration Target:** `product_facts` (`fact_key = 'pricing_followup_consultations'`, `fact_key = 'pricing_dedicated_nutritionist'`).

---

### Finding 2: Application Access Boundaries & Channel Restrictions
- **Source File:** `disha_core/pipeline/validator.py` (Lines 15, 97) and `disha_core/llm/client.py` (Line 14)
- **Hardcoded Content:**
  - `CHANNEL_REPLACEMENT = "Aap apna plan sirf app ke 'My Plan' tab mein dekh sakte hain."`
  - `CHANNEL_RE = re.compile(r"\b(?:whatsapp|sms|email|telegram)\b|व्हाट्स?ऐप|व्हाट्स?एप", re.I)`
  - In `SYSTEM_PROMPT`: `"Never promise external delivery; all plans and exercise guides are accessed in the app's My Plan tab."`
- **Category:** Product Capability & Access Channel Guardrails.
- **Risk / Architectural Issue:** If WhatsApp notifications or PDF email exports are added as authorized enterprise features, hardcoded replacements will overwrite valid responses.
- **Migration Target:** `product_facts` (`fact_key = 'channel_policy_my_plan'`, `fact_key = 'channel_forbidden_transports'`).

---

### Finding 3: AI Persona Identity & Clinical Disclaimer Boundaries
- **Source File:** `disha_core/pipeline/validator.py` (Lines 37–61, 98, 103–104) and `disha_core/llm/client.py` (Lines 14, 49)
- **Hardcoded Content:**
  - `IDENTITY_REPLACEMENT = "Main Disha hoon, aapki AI health coach."`
  - `DIAGNOSIS_REPLACEMENT = "Main ek AI coach hoon aur koi medical diagnosis nahi de sakti; kripya diagnosis ke liye clinician se consult karein."`
  - `PRESCRIPTION_REPLACEMENT = "Main dawaiyon ki dose ya prescription badalne ke liye authorized nahi hoon; kripya apne prescribing clinician se salah lein."`
- **Category:** Clinical Governance & Identity Invariants.
- **Risk / Architectural Issue:** Clinical safety scripts must be versioned, attributed to a legal/clinical compliance signoff, and easily updated across multi-lingual locales.
- **Migration Target:** `product_facts` (`fact_key = 'persona_identity'`, `fact_key = 'clinical_diagnosis_disclaimer'`, `fact_key = 'clinical_prescription_disclaimer'`).

---

### Finding 4: Emergency Red-Flag Lexicon & Escalation Scripts
- **Source File:** `disha_core/pipeline/breaker.py` (Lines 17–97)
- **Hardcoded Content:**
  - `EMERGENCY_PATTERNS`: Lexicon arrays for `CARDIOVASCULAR`, `RESPIRATORY`, `NEUROLOGICAL`, `CRISIS`, `TRAUMA` totaling 150+ terms in Python strings.
  - `EMERGENCY_SCRIPTS`:
    - `CARDIOVASCULAR` / `RESPIRATORY` / `NEUROLOGICAL`: `"Yeh emergency ho sakti hai. Abhi 112 par call karein ya kisi paas ke vyakti se call karne ko kahein."`
    - `CRISIS`: `"Agar aap turant khatre mein hain, 112 par call karein ya kisi bharosemand vyakti ke paas jaayen. Tele-MANAS se 14416 par bhi baat kar sakte hain."`
    - `TRAUMA`: `"Yeh emergency ho sakti hai. Abhi 112 par call karein aur paas ke kisi vyakti se madad lein."`
- **Category:** Emergency Triage Protocols & Emergency Helplines.
- **Risk / Architectural Issue:** Helplines (112, Tele-MANAS 14416) are national Indian standards; regional emergency numbers or state-specific helplines cannot be dynamically configured.
- **Migration Target:** `product_facts` (`fact_key = 'emergency_helpline_national'`, `fact_key = 'emergency_helpline_telemanas'`) and `knowledge_chunks` (`domain = 'emergency_triage'`).

---

### Finding 5: Personalized Exercise Prescription (PEP) Clearance Rules
- **Source File:** `disha_core/services/auth_service.py` (Lines 71–84), `disha_core/pipeline/validator.py` (Lines 70–83, 240–252), and `disha_core/engine/context_builder.py` (Lines 185–199)
- **Hardcoded Content:**
  - If `htn_stage in ("stage 1", "stage 2")` or not `gym_clearance` or restriction:
    - `allowed = ["brisk walking", "gentle yoga", "stretching", "breathing exercises", "light cycling"]`
    - `restricted = ["heavy deadlifts", "max weight lifting", "valsalva maneuver", "high-intensity sprinting"]`
  - In `context_builder.py`:
    - Hardcoded string: `"heavy weightlifting, heavy deadlifts, hiit, valsalva maneuver, high intensity sprinting"` appended if CAD or Stage 2 HTN.
  - In `patient_service.py` fallbacks:
    - Default allowed: `["Brisk walking", "Gentle yoga"]`
    - Default restricted: `["Heavy deadlifts", "Max weight lifting"]`
- **Category:** Clinical Exercise Physiology & Contraindication Rules.
- **Risk / Architectural Issue:** Exercise clearance protocols should follow WHO and sports medicine standards stored in the database with clinical lead attribution.
- **Migration Target:** `product_facts` (`fact_key = 'pep_clearance_hypertension_stage1'`, `fact_key = 'pep_clearance_cardiac_severe'`) and `knowledge_chunks` (`domain = 'exercise_prescription'`).

---

### Finding 6: Onboarding 7-Day Diet Menu Templates & Meal Strings
- **Source File:** `disha_core/services/auth_service.py` (Lines 170–184)
- **Hardcoded Content:**
  - Hardcoded menu item strings:
    - Jain: `"2 moong dal chillas with mint chutney (no root veg)..."`, `"1 bowl yellow moong dal, 2 phulkas, steamed lauki sabzi..."`, `"150g fresh paneer sabzi (jain prep)..."`
    - Non-veg / Egg: `"2 boiled eggs or egg scramble..."`, `"1 bowl grilled chicken curry/dal with 1 cup brown rice..."`, `"150g grilled chicken/paneer with steamed broccoli..."`
    - Vegetarian: `"2 moong dal chillas with mint chutney..."`, `"1 bowl dal tadka, 2 multigrain rotis..."`, `"150g paneer bhurji, 2 multigrain rotis, and cucumber salad (approx 420 kcal)"`
- **Category:** Clinical Dietetics & Meal Schedules.
- **Risk / Architectural Issue:** Clinical nutritionists cannot update default seasonal menu plans or adjust caloric macros without modifying backend Python code.
- **Migration Target:** `knowledge_chunks` (`diet_tags`, `domain = 'diet_schedule_template'`) and `product_facts` (`category = 'diet_template'`).

---

### Finding 7: Vegetarian Invariant & Protein Substitute Lists
- **Source File:** `disha_core/pipeline/validator.py` (Lines 140, 176–181) and `disha_core/engine/context_builder.py` (Lines 205–209)
- **Hardcoded Content:**
  - `VEG_MEAT_RE = re.compile(r"\b(?:grilled\s+)?(?:chicken|mutton|fish|meat|poultry|seafood|prawns|beef|pork)\b", re.I)`
  - Replacement: `paneer ya tofu`
  - In `context_builder.py`: `FORBIDDEN="chicken, meat, poultry, fish, seafood, mutton, eggs"`
- **Category:** Dietary Guardrails & Allergen / Preference Filters.
- **Risk / Architectural Issue:** Hardcoded replacement string `"paneer ya tofu"` does not consider dairy intolerance or vegan preferences.
- **Migration Target:** `product_facts` (`fact_key = 'diet_vegetarian_forbidden_terms'`, `fact_key = 'diet_vegetarian_default_substitutes'`).

---

### Finding 8: Colloquial Patient Disclosure Detection Lexicons
- **Source File:** `disha_core/services/chat_service.py` (Lines 184–228)
- **Hardcoded Content:**
  - Shift work keywords: `("night shift", "raat ki shift", "night duty", "rotational shift", "shift worker")`
  - Food dislike regexes: `r"\b(?:don['’]?t\s+like|dislike|hate|cannot\s+eat|avoid)\s+([a-zA-Z\s]{3,25})"`
  - Knee pain keywords: `("knee pain", "ghutno ka dard", "ghutne me dard", "joint pain", "knee surgery", "arthritis")`
  - Hypertension terms: `("high bp", "hypertension", "bp high rehta", "heart patient", "cardiac")`
- **Category:** Natural Language Understanding & Temporal Fact Graph Triggers.
- **Risk / Architectural Issue:** Expanding symptom terminology requires editing Python lists instead of managing vocabulary in database lexicons.
- **Migration Target:** `knowledge_chunks` (trigger_terms) and `product_facts` (`category = 'disclosure_lexicon'`).

---

### Finding 9: Speech Phonetic Pronunciation Mappings
- **Source File:** `disha_core/voice.py` (Lines 28–75)
- **Hardcoded Content:**
  - `HINGLISH_PHONETIC_MAP`: 50+ Roman Hindi words mapped for speech synthesis (e.g., `jeera`, `saunf`, `khichdi`, `daliya`, `kamzori`, `bukhar`).
- **Category:** Voice & Audio Synthesis Optimization.
- **Risk / Architectural Issue:** Adding new regional food names or Ayurvedic formulations to the speech pipeline requires code changes.
- **Migration Target:** `product_facts` (`category = 'phonetic_dictionary'`, `fact_key = 'tts_hinglish_phonetic_map'`).

---

## 3. Summary of Hardcode Findings

| Finding ID | Source Module | Logic Type | Hardcoded Values | Database Target |
|---|---|---|---|---|
| **HC-01** | `validator.py`, `client.py` | Pricing & Subscription | ₹0 follow-ups, ₹1,499/mo nutritionist plan | `product_facts` (`category = 'pricing'`) |
| **HC-02** | `validator.py`, `client.py` | Channel Boundaries | "My Plan" tab only; ban WhatsApp/SMS/Email | `product_facts` (`category = 'access_channel'`) |
| **HC-03** | `validator.py`, `client.py` | AI Identity & Persona | "Main Disha hoon, aapki AI health coach" | `product_facts` (`category = 'identity'`) |
| **HC-04** | `breaker.py` | Emergency Numbers | 112 (Ambulance), 14416 (Tele-MANAS) | `product_facts` (`category = 'emergency_helpline'`) |
| **HC-05** | `auth_service.py`, `validator.py` | PEP Clearance Rules | Allowed: walking/yoga; Restricted: deadlifts/HIIT | `product_facts` (`category = 'exercise_clearance'`) |
| **HC-06** | `auth_service.py` | Onboarding Diet Menus | 7-day Jain, Vegetarian, Non-veg meal strings | `knowledge_chunks`, `product_facts` |
| **HC-07** | `validator.py`, `context_builder.py` | Vegetarian Guardrail | Forbidden: chicken/meat/fish; Repl: paneer/tofu | `product_facts` (`category = 'diet_rules'`) |
| **HC-08** | `chat_service.py` | Disclosure Lexicon | Hardcoded tuple sets for shift, knee, BP terms | `product_facts` (`category = 'disclosure_lexicon'`) |
| **HC-09** | `voice.py` | TTS Pronunciation | 50+ Roman Hindi phonetic dictionary entries | `product_facts` (`category = 'phonetics'`) |

---

## 4. Remediation Architecture & Database Seed Plan

To eliminate hardcoded data, we establish:
1. `knowledge_sources` table for authoritative institutional provenance.
2. `knowledge_chunks` table for granular clinical guidelines, diet templates, and symptom remedies with FTS and condition tags.
3. `product_facts` table with JSONB values for pricing, channels, clinical clearance bounds, and persona disclaimers.
4. SQL migration and seed scripts:
   - `migrations/versions/0003_knowledge_and_product_facts.py`
   - `disha_core/db/seed_product_facts.sql`
   - `disha_core/db/seed_knowledge_chunks.sql`
   - Synchronized update in `disha_core/db/schema.sql`.
