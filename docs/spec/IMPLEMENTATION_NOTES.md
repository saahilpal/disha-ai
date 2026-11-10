# Behavior Spec v1 — Implementation Notes & Risk Ledger

- **Author:** BossEmployee (Lead AI Systems Engineer)
- **Date:** 2026-11-10
- **Status:** APPROVED & IMPLEMENTED
- **Target Architecture:** Behavior Spec v1 on `feat/behavior-spec-v1`

---

## 1. Decision D2: Zero-Echo (F1) vs Confirming Safety-Critical Values

### Specification
Rule F1 dictates that the assistant must never repeat back facts the user provided (e.g. stating "Aapka weight 62kg hai"). 

### Implementation & Configuration
A dedicated setting `confirm_critical_values: bool = False` is added to `disha_core/config.py:59`, defaulting to `False` as ordered.

### Risk Analysis
- **Risk:** When a patient discloses critical clinical numbers (e.g., blood glucose level "240 mg/dL", medication dosage "Metformin 500mg", or acute blood pressure "180/110"), not echoing or confirming the recognized number leaves open the risk that ASR (Automatic Speech Recognition) or OCR transcribed a misheard digit, and Disha proceeds on corrupted clinical premises.
- **Mitigation:** Emergency red flags (C3) bypass coaching logic entirely via deterministic keyword/table-driven circuit breaker (<5ms), so acute cardiac/stroke thresholds are handled regardless. For sub-acute lifestyle coaching, Disha acknowledges user intent without echoing numerical quantities. If the owner enables `CONFIRM_CRITICAL_VALUES=true`, critical medication and allergy disclosures will trigger an explicit confirmation turn.

---

## 2. Decision D3: Clinical Boundary (C2) vs Lifestyle Coaching

### Specification
Disha must never prescribe medications, provide definitive diagnoses, or formulate medical treatment plans in chat.

### Implementation
Externalized into an owner-editable YAML catalog: `data/c2_boundary.yaml`.
- **Forbidden Categories:**
  - `medication`: Exact dosages (`mg`, `ml`, `mcg`), prescription altering phrases, pharmaceutical names (`metformin`, `paracetamol`, `atorvastatin`, etc.).
  - `diagnosis`: Definitive pathology assertions ("you have diabetes", "aapko hypertension hai").
  - `treatment_plan`: Medical intervention sequences ("double the dose", "start taking", "ilaj", "surgery").
- **Allowed Categories (after C1 History Triangle is satisfied):**
  - General dietary guidance (balanced hydration, vegetable intake, whole grains).
  - Sleep hygiene recommendations.
  - Everyday exercise suggestions (walking, gentle mobility, stretching).
  - Stress reduction practices (paced breathing, routine regularity).

### Risk Analysis
- **Risk:** Blurred line between clinical lifestyle medicine and formal medical treatment (e.g., nutritional therapy for severe chronic kidney disease or insulin-dependent diabetes).
- **Mitigation:** Deterministic verifier `check_c2_clinical_boundary` in `verifier.py:509-543` scans all generated drafts before display and strictly blocks any draft containing pharmaceutical terms or dose instructions.

---

## 3. Decision D4: 10-Minute Expert Call Pivot & Product Capabilities

### Specification
Rule C4 orders Disha to drive the chat toward recommending a 10-minute expert call as the final clinical outcome.

### Current Code & Database Reality
- **Product Facts Entry:** Added `expert_call` row to `disha_core/db/seed_product_facts.sql`:
  ```json
  {"duration_minutes": 10, "contact": null, "link": null, "status": "unconfigured"}
  ```
- **Capability Truth:** There is currently **NO** booking engine, calendaring integration, or active telephony dispatch for human clinicians in the codebase.
- **Behavior Rule:** Disha recommends the 10-minute expert call **in words only** (e.g. *"Ek 10-minute expert call se aapko better guidance mil sakti hai"*). She **never** claims she booked, scheduled, or transferred the call. The UI displays **no action button** until the owner populates a valid `link` or `contact` in the `product_facts` table.

---

## 4. Decision D5: Multilingual Policy & Silent 2-Turn Language Switch

### Specification
Supports Hinglish (Roman script default), English (casual plain English, no Hindi words), and Hindi (Devanagari script with everyday words). First-run choice is presented via a one-tap modal before Disha's first message.

### Implementation
- **First-Run Modal:** Implemented in `disha_core/frontend/app.js:1260-1340`. Checks `localStorage['disha_language_chosen']`. If unselected, displays an interactive modal showing English, हिन्दी, and Hinglish. Selecting updates `patient_profiles.language` via `PUT /patient/profile`.
- **Silent Switch Threshold:** `language_switch_threshold: int = 2` in `config.py:60`.
- **Switch Logic:** In `disha_core/harness/harness.py:618-632`, if a user sends 2 consecutive messages in another supported language (tracked across turns), the backend updates `patient_profiles.language` and `patient_pep.language` silently without verbal deflection or questioning.

