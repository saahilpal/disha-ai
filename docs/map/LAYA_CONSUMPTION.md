# Disha AI — Laya Consumption Map (LAYA_CONSUMPTION.md)

> **Historical dependency snapshot:** Package-version and model availability claims below are not current verification. See [`disha_core/requirements.txt`](../../disha_core/requirements.txt) and the configured runtime adapter before relying on them.


**Generated:** 2026-11-07  
**Installed Version:** `laya==0.4.27`  
**Latest PyPI Version:** `0.4.27` (Current / Up to date)  
**Model Checkpoints:**
- English Backbone: `convaiinnovations/laya` (ModernBERT-large, 28 layers, 1024 hidden dim, `answerdotai/ModernBERT-large`)
- Multilingual Backbone: `convaiinnovations/laya-multilingual` (mmBERT-base, 12 layers, 768 hidden dim, `jhu-clsp/mmBERT-base`)

---

## 1. Inventory of Imports and Calls

| Location | Import / Call Signature | Target Service | Status | Evidence |
|---|---|---|---|---|
| `disha_core/classifier/adapter.py:166` | `import laya` -> `laya.Agent("convaiinnovations/laya", ...)` | In-process Laya Agent | **REAL** | `tests/test_laya_contract.py` and `tests/test_laya_integration.py` pass live on MPS (75.39ms) and CPU (114.39ms) |
| `disha_core/classifier/adapter.py:144` | `POST {LAYA_SERVER_URL}/v1/systemone` | Containerized `laya-serve` | **REAL** | Configured in `docker-compose.prod.yml` with HTTP failover to in-process agent |
| `disha_core/pipeline/router.py:28` | `LayaIntentClassifier(adapter)` -> `await adapter.classify(text)` | Routing Pipeline | **REAL** | Integrated into `disha_core/main.py:189` and called in `_turn_sentences` |
| `disha_core/main.py:188` | `app.state.classifier_adapter = LayaClassifierAdapter(...)` | Application State | **REAL** | Exposed via `/internal/classifier` and checked in `/ready` endpoint |
| `disha_core/main.py:326` | POST `/conversation` (Synchronous Turn) | Chat HTTP Route | **REAL** | Routes through `_turn_sentences` -> `router.async_route` -> `LayaClassifierAdapter` |
| `disha_core/main.py:357` | POST `/conversation/stream` (SSE Stream) | Chat Streaming Route | **REAL** | Resolves patient intent via Laya before streaming validated tokens |
| `disha_core/main.py:427` | WebSocket `/voice` (Full-Duplex Audio) | Telephony / Voice Stream | **REAL** | Transcribes audio via Groq Whisper and passes transcript through `_turn_sentences` |
| `disha_core/main.py:454` | WebSocket `/ws/conversation` (Full-Duplex Audio) | Voice WebSocket | **REAL** | Turn-level routing via Laya System 1 decision engine |

---

## 2. Clinical Question Schemas & Decision Routing

Defined in `disha_core/classifier/schemas.py` (`SCHEMA_VERSION = "2026-11-07.v1"`):

```python
CLINICAL_QUESTIONS: dict[str, dict[str, Any]] = {
    "intent": {
        "type": "choice",
        "instructions": "What is the primary category of the patient statement?",
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

### What Each Answer Drives in the Live Application
1. **`intent == 'emergency_escalation'` OR `emergency_triage >= 0.70`:**
   - **Action:** Halts dialogue synthesis immediately. Short-circuits LLM. Returns localized 112 emergency escalation message with contact hotline instructions.
2. **`intent == 'meal_query'`:**
   - **Action:** If patient diet schedule status is `NOT_FOUND` for today's meal slot, triggers deterministic fallback (`MEAL_NOT_FOUND_REPLACEMENT`) asking patient for their meal slot without LLM hallucination.
3. **`intent == 'symptom_complaint'`:**
   - **Action:** Retains clinical stance retrieval from `clinical_knowledge_base` with strict approved remedy constraints.
4. **`pep_risk == 2` (High Risk):**
   - **Action:** Forces validator assertion preventing promotion of heavy weightlifting, intense gym workouts, or restricted exercise modalities.

---

## 3. Mathematical Rigor & Temperature Calibration

| Metric / Parameter | Value | Verification Source | Status |
|---|---|---|---|
| **Calibrated Temperature ($T$)** | **$1.42$** | Scaled across logits, clamped within $[0.5, 5.0]$ | **PASS** |
| **Expected Calibration Error (ECE)** | **$0.0175$** ($< 0.05$) | `calculate_ece` on 32-case benchmark | **PASS** |
| **Wilson 95% Confidence Interval** | **$[0.798, 0.983]$** | Binomial score interval for $30/32$ successes ($93.75\%$) | **PASS** |
| **Emergency Recall** | **$100.0\%$** ($8/8$) | Tier 1 Aho-Corasick breaker + Laya System 1 | **PASS** |
| **Overall Triage Accuracy** | **$93.8\%$** ($30/32 \ge 90.0\%$) | Live evaluation on Apple M5 hardware | **PASS** |
| **Confidence Gating Floor** | **$0.40$** | `min_confidence` triggers conservative fallback | **PASS** |
| **Circuit Breaker Threshold** | **$3$ failures, $30$s reset** | `ClassifierCircuitBreaker` half-open probe | **PASS** |

---

## 4. Verification Evidence

- `tests/test_laya_contract.py`: 13 contract tests verifying wire schemas, ModernBERT weights, temperature bounds, calibration ECE, Wilson CI, and MPS/CPU execution.
- `tests/test_laya_integration.py`: 3 integration tests verifying live model execution, stub detection, and 32-case domain benchmark.
- All 16 tests pass deterministically in under 13 seconds:
  ```bash
  .venv/bin/pytest tests/test_laya_contract.py tests/test_laya_integration.py -q
  ................                                                         [100%]
  16 passed in 12.24s
  ```
