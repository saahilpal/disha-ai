# 🎯 Disha AI — Laya Classifier Integration & Self-Learning Architecture

**Document Path:** `docs/LAYA_INTEGRATION.md`  
**Classification:** Core Machine Learning Systems Specification  
**Status:** Historical integration notes; see `docs/architecture/04_rag_ingestion_and_retrieval.md` for current knowledge and recommendation behavior.
**Maintained by:** Agent B (Laya Integration Specialist) & Agent H (Learning Tracker)  
**Last Updated:** 2026-11-08  

---

## 1. Executive Summary & Core Role

Disha AI employs the genuine open-source **Laya** classifier ([`github.com/NandhaKishorM/laya`](https://github.com/NandhaKishorM/laya)) as its **System 1 non-autoregressive neural decision head**.

Unlike generative LLMs that require 1–3 seconds and high token costs to understand intent and assess safety, Laya performs zero-shot multi-head triage in non-autoregressive forward passes, extracting:
1. **Clinical Intent Understanding** (6 categories: `meal_query`, `symptom_complaint`, `general_coaching`, `exercise_query`, `emergency_escalation`, `app_meta`).
2. **Deterministic Emergency Triage** (acute life-threatening event probability).
3. **PEP Cardiovascular Strain & Risk Score** (`pep_risk`: 0=low, 1=moderate, 2=high).

By executing System 1 ahead of prompt generation, Disha AI achieves:
- **Retrieval routing:** Pure greetings and app-meta questions can bypass health retrieval. Health-related coaching (including meals, exercise, hydration, sleep, and habits) requires approved knowledge retrieval even when classified as general coaching. The active search is PostgreSQL full-text and trigram, not pgvector.
- **Early PEP Safety Bounds:** High-risk exercise queries (e.g., deadlifts, sprinting) from restricted patients trigger safety bounds early, eliminating unsafe LLM exercise recommendations.
- **Continuous Clinical Audit:** Sub-threshold (<0.70) or ambiguous intent turns are asynchronously enqueued into a zero-PHI review queue.

---

## 2. Classification Schema & Question Taxonomy

Defined in `disha_core/classifier/schemas.py` (`SCHEMA_VERSION = "2026-11-08.v2"`):

```python
CLINICAL_QUESTIONS: dict[str, dict[str, Any]] = {
    "intent": {
        "type": "choice",
        "instructions": "What is the primary category of the user's statement?",
        "criteria": {
            "meal_query": "food, eating, meals, what to eat, dinner, lunch, breakfast, recipes, diet plan, calories, prescribed food",
            "symptom_complaint": "illness, stomach ache, pain, gas, bloating, fever, acidity, nausea, vomiting, discomfort",
            "general_coaching": "wellness, greeting, walking, steps, daily exercise, sleep, water intake, routine check-in, habit tracking",
            "emergency_escalation": "urgent life-threatening emergency, chest pain, heart attack, severe difficulty breathing, stroke, collapse, heavy bleeding",
        },
    },
    "emergency_triage": {
        "type": "noul",
        "instructions": "Does this message report an acute life-threatening medical emergency?",
    },
    "pep_risk": {
        "type": "score",
        "instructions": "Evaluate the cardiovascular strain and physical exertion intensity of the physical activity mentioned.",
        "criteria": [
            "low risk: brisk walking, gentle stretching, restorative yoga, breathing exercises",
            "moderate risk: light jogging, bodyweight squats, low-impact aerobics, resistance band work",
            "high risk: heavy deadlifts, max-effort weightlifting, competitive CrossFit, high-intensity sprinting",
        ],
    },
}
```

### 2.1 The 6 Production Intent Categories

| Intent | Description | Examples | Routing Action |
|---|---|---|---|
| `meal_query` | Prescribed diet, recipes, nutritional queries, food timing | *"What should I eat for dinner?"*, *"Aaj khane mein kya hai?"* | Route to Diet Schedule + Dietary Knowledge Retrieval |
| `symptom_complaint` | Functional gastrointestinal issues, pain, reflux, acidity | *"Pet mein bohot gas aur bloating hai"*, *"Mild nausea"* | Route to Clinical KB with Approved ICMR Remedy Tokens |
| `exercise_query` | Workouts, gym activities, weightlifting, deadlifts, cardio | *"Can I do heavy deadlifts at gym?"*, *"Aaj workout karun?"* | PEP Cardiovascular Exertion Check + Exercise Guidelines |
| `general_coaching` | Daily habits, walking, sleep, hydration, motivation | *"How many steps should I walk?"*, *"Tips for deep sleep"* | Retrieve approved guidance for health recommendations; non-health conversation may skip |
| `app_meta` | App features, navigation, subscription fees, profile settings | *"How much is subscription fee?"*, *"Where is My Plan tab?"* | **SKIP DB Retrieval**; Stream app guidance |
| `emergency_escalation` | Acute chest pain, shortness of breath, collapse, stroke | *"Chhati mein tez dard hai"*, *"Crushing chest tightness"* | **HALT Pipeline**; Immediate 112 emergency escalation |

---

## 3. End-to-End Routing & Retrieval Architecture

```mermaid
flowchart TD
    Utterance["Patient Utterance"] --> Breaker["Tier 1: Emergency Breaker (Aho-Corasick)"]
    Breaker -->|Acute Trigger (0.01ms)| Direct112["Direct 112 Emergency Message\n(Short-circuit entire pipeline)"]
    Breaker -->|Clear| CacheCheck{"LRU Query Cache\n(<0.5ms)"}
    
    CacheCheck -->|Cache Hit| LayaRes["LayaClassificationResult"]
    CacheCheck -->|Cache Miss| LayaInf["Laya System 1 Inference\n(ModernBERT-large / Multilingual)"]
    LayaInf --> CacheStore["Store in LRU Cache"]
    CacheStore --> LayaRes
    
    LayaRes --> PEPCheck{"High PEP Risk (pep_risk >= 2)\n& Patient Restricted?"}
    PEPCheck -->|Yes| EarlyPEP["Early PEP Safety Guardrail\nYield PEP_REPLACEMENT\n(Bypass DB & LLM)"]
    
    PEPCheck -->|No| IntentBranch{"Intent Classification"}
    
    IntentBranch -->|Greeting / App Meta / Non-health chat| SkipRetrieval["Health retrieval may be skipped"]
    IntentBranch -->|Health / Meal / Exercise| DomainRetrieval["Approved PostgreSQL FTS + trigram retrieval"]
    
    SkipRetrieval --> LLM["LLM Sentence Buffer & Validator"]
    DomainRetrieval --> LLM
    
    LayaRes --> ConfCheck{"Confidence < 0.70\nOR Ambiguous Margin < 0.15?"}
    ConfCheck -->|Yes| AuditQueue["Async Enqueue to Zero-PHI Review Queue\n(SQLite WAL)"]
    ConfCheck -->|No| Done["Done"]
```

### 3.1 Retrieval Short-Circuiting Mechanics

Pure greetings and app-meta turns may skip health retrieval. Classification as `general_coaching` alone does not skip it: meal and exercise domains and other grounded health advice still query the approved knowledgebase. The runtime can avoid irrelevant chunks through bounded lexical retrieval and thresholds.

When the turn is a `symptom_complaint`, `meal_query`, or `exercise_query`, the pipeline targets domain-specific tags:
- `SYMPTOM_COMPLAINT`: targets `["GI_BLOATING"]` or clinical tags.
- `MEAL_QUERY`: targets `["FRUIT_MODERATION"]` or diet tags.
- `EXERCISE_QUERY`: targets `["EXERCISE_GUIDELINES"]` or PEP tags.

---

## 4. PEP Risk Triage & Early Safety Bounds

Patients with cardiovascular risk factors (e.g., Stage 1/2 Hypertension, lack of gym clearance, or specific restricted modalities like heavy deadlifts/valsalva maneuvers) must never receive advice that encourages dangerous physical exertion.

### 4.1 System 1 Early Detection
Laya's `pep_risk` head scores cardiovascular exertion:
- **`0` (Low Risk):** Brisk walking, gentle stretching, restorative yoga.
- **`1` (Moderate Risk):** Light jogging, bodyweight squats, resistance bands.
- **`2` (High Risk):** Heavy deadlifts, max-effort weightlifting, competitive CrossFit, high-intensity sprinting.

### 4.2 Early Pipeline Guardrail
When `pep_risk >= 2` (or the text matches high-risk exertion patterns) AND patient PEP records indicate restrictions:
```python
pep = context.get("pep") or {}
restricted = {str(item).replace("_", " ").casefold() for item in pep.get("restricted_modalities") or ()}
has_cardiac_htn = bool(pep.get("hypertension_stage")) or not pep.get("gym_clearance", True)

if pep_risk >= 2 and (restricted or has_cardiac_htn):
    state.validator_status = "rewritten:pep_restriction"
    yield PEP_REPLACEMENT
    return
```
- **Outcome:** The user immediately receives `PEP_REPLACEMENT` (*"Main aapke exercise permissions ke andar safe activity chunne mein madad kar sakti hoon."*).
- **Safety Guarantee:** Generative LLM inference is completely bypassed, eliminating any possibility of LLM hallucination approving unsafe exercises.

---

## 5. Zero-PHI Review Queue & Self-Learning Audit

Implemented in `disha_core/classifier/review_queue.py` and connected via `disha_core/classifier/adapter.py`:

### 5.1 Automatic Clinical Audit Trigger
In accordance with clinical protocol:
- Any turn where intent confidence is **$< 0.70$**
- OR where the margin between the top two predicted intents is **$< 0.15$** (ambiguous classification)
- OR where classifier fallback is engaged

The adapter automatically dispatches the turn to `ReviewQueueManager`:
```python
if intent_conf < 0.70 or is_ambiguous:
    self._enqueue_review_trigger(
        raw_text=text,
        trigger_type="LOW_CONFIDENCE",
        predicted_intent=final_intent,
        confidence=intent_conf,
        emergency=is_emergency,
        pep_risk=pep_risk_idx,
        raw_answers=answers,
        fallback_reason=audit_reason,
    )
```

### 5.2 Deterministic Privacy (Zero-PHI)
Before persistence into SQLite WAL (`review_queue.db`):
- **Phone Numbers:** Redacted to `[PHONE_REDACTED]`.
- **Aadhaar Numbers:** Redacted to `[AADHAAR_REDACTED]`.
- **Emails / MRN IDs:** Redacted to `[EMAIL_REDACTED]` / `[MRN_REDACTED]`.
- **Direct Names:** Regex-scrubbed to `[NAME_REDACTED]`.
- **Patient Tokenization:** Irreversibly pseudonymized using HMAC-SHA256 with secret salt (`pt_...`).

---

## 6. Performance Benchmarks & Latency SLA

Measured on Apple Silicon hardware (macOS, Python 3.12, PyTorch 2.x):

| Execution Path | Measured P50 Latency | Latency SLA | Invariant Status |
|---|---|---|---|
| **High-Speed Cache Hit** | **$0.02\text{ ms}$** | $< 25.0\text{ ms}$ | **PASS** |
| **Deterministic Fallback Path** | **$0.05\text{ ms}$** | $< 25.0\text{ ms}$ | **PASS** |
| **In-Process Inference (CPU, 4 threads)** | **$157.3\text{ ms}$** | $< 260.0\text{ ms}$ | **PASS** |
| **Emergency Recall** | **$100.0\%$** ($8/8$) | $100.0\%$ | **PASS** |
| **Curated Domain Accuracy** | **$93.8\%$** ($30/32$) | $\ge 90.0\%$ | **PASS** |
| **Indian Health 6-Intent Accuracy** | **$100.0\%$** ($24/24$) | $\ge 95.0\%$ | **PASS** |

### 6.1 Thread Optimization
On multi-core architectures, running CPU inference without thread clamping induces cross-core context-switching overhead. Setting `torch.set_num_threads(4)` with `torch.inference_mode()` reduced CPU inference latency from **$392\text{ms}$** to **$157\text{ms}$** (a **$2.5\times$** speedup).

---

## 7. Verification Evidence & Automated Tests

All tests run deterministically via pytest:
```bash
.venv/bin/pytest disha_core/tests/test_laya_integration.py \
                 disha_core/tests/test_invariants.py \
                 tests/test_laya_contract.py \
                 tests/test_laya_integration.py \
                 tests/test_self_learning_and_review.py -q
```
**Output:**
```
77 passed in 44.29s
```

### Covered Test Invariants
1. `test_accurate_intent_classification_indian_health_queries`: Verifies 100% accuracy on English, Hinglish, and Hindi queries across all 6 clinical intents.
2. `test_retrieval_routing_and_short_circuiting`: Confirms `skip_retrieval=True` on greetings, coaching, and app meta, and targeted retrieval on symptoms, meals, and exercise.
3. `test_pipeline_skips_database_retrieval_on_coaching_and_meta`: Verifies 0 database connection pool acquisitions when retrieval is unneeded.
4. `test_pep_risk_flagging_for_high_risk_exercise`: Confirms `pep_risk=2` detection and early `PEP_REPLACEMENT` guardrail without LLM synthesis.
5. `test_review_queue_captures_subthreshold_and_ambiguous_turns`: Validates automatic asynchronous ingestion of low-confidence turns into the zero-PHI review queue.
6. `test_laya_cache_and_fallback_latency_under_25ms`: Confirms cache and fallback execution are strictly under 25ms.
