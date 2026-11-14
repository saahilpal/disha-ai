# System Evaluation & Empirical Verification (EVALUATION)

This document details the test suites, benchmark methodologies, empirical latency measurements, and continuous safety guarantees implemented in Disha AI.

## 1. Evaluation Suites Overview

The repository enforces safety invariants through multi-layered automated evaluation suites:

1. **Rule-Based Golden Suite (`tests/golden/*.yaml`)**:
   - 70 frozen behavioral assertions covering five rule families:
     - `c_rules_clinical_safety.yaml` (19 cases): Prescriptions, diagnosis, emergency triage, sodium advice.
     - `p_rules_persona_tone.yaml` (20 cases): Doctor disclaimers, empathy, coaching tone, identity boundaries.
     - `f_rules_flow.yaml` (16 cases): Single-question limit, closure handling, acknowledgment handling.
     - `d_rules_long_conversation.yaml` (8 cases): Multi-turn consistency across 30+ exchanges.
     - `m_rules_memory_backend.yaml` (7 cases): Habit disclosure retention, session hydration, cross-channel recall.
2. **Golden Corpus (`tests/golden_corpus_2703.jsonl`)**:
   - 2,703 test prompts evaluating multilingual Hinglish, Devanagari Hindi, and English variations.
3. **Emergency Red-Flag Benchmark (`tests/fixtures/emergency_red_flags_100.json`)**:
   - 100 acute clinical emergencies spanning cardiovascular (acute myocardial infarction, crushing chest pain), cerebrovascular (facial droop, slurred speech), and acute respiratory distress.
4. **Adversarial & Chaos Suites (`tests/test_breaker_chaos.py`, `tests/test_adversarial_conversational.py`)**:
   - Evaluates jailbreak attempts, prompt injection, persona manipulation ("admit you are a doctor"), and simulated network latency.
5. **Longitudinal Journey Simulation (`tests/test_multi_session_30day_simulation.py`)**:
   - Simulates 30 consecutive days of patient interactions with variable blood pressure readings, exercise disclosures, and dietary questions.

## 2. Empirical System Measurements

Measurements taken on local execution environment (macOS Apple Silicon, Python 3.12, PostgreSQL 16 on Docker).

### 2.1 Emergency Breaker Benchmark
Evaluated across 100 benchmark emergency prompts (`emergency_red_flags_100.json`) and 20 benign conversational queries:

| Metric | Result | Target | Pass / Fail |
|---|---|---|---|
| True Positives (TP) | 100 / 100 (100.0%) | 100% | PASS |
| False Negatives (FN) | 0 / 100 (0.0%) | 0% | PASS |
| False Positives (FP) | 0 / 20 (0.0%) | 0% | PASS |
| True Negatives (TN) | 20 / 20 (100.0%) | 100% | PASS |
| Median Latency (p50) | 3.69 µs | < 1,000 µs | PASS |
| 95th Percentile (p95) | 26.01 µs | < 2,000 µs | PASS |
| 99th Percentile (p99) | 64.22 µs | < 5,000 µs | PASS |
| Latency Range | 2.83 µs - 171.92 µs | < 10,000 µs | PASS |

### 2.2 Micro-Benchmark Latencies (10,000 Iterations, 50-Word Input)

| Component / Operation | Min (µs) | Median p50 (µs) | p95 (µs) | p99 (µs) | Max (µs) |
|---|---|---|---|---|---|
| Aho-Corasick Emergency Scan | 134.25 | 143.13 | 151.46 | 164.17 | 307.62 |
| Regex Intent Refinement | 52.17 | 54.67 | 59.63 | 122.25 | 1498.79 |
| LRU Cache Hit Lookup | 0.00 | 0.04 | 0.08 | 0.13 | 7.58 |

### 2.3 Output Checkers Catch Rates (50 Sentence Evaluation)

Evaluated across 50 adversarial and standard coaching sentences:

| Category | Total Tested | Caught by SentenceValidator (Streaming) | Caught by ResponseVerifier (Holistic) |
|---|---|---|---|
| Pricing & Subscriptions | 6 | 6 / 6 (100%) | 6 / 6 (100%) |
| Channel Leaks (WhatsApp/SMS) | 6 | 4 / 6 (67%) | 4 / 6 (67%) |
| Prescription Modifications | 6 | 3 / 6 (50%) | 4 / 6 (67%) |
| Doctor Identity Claims | 6 | 2 / 6 (33%) | 2 / 6 (33%) |
| Diagnostic Pronouncements | 6 | 2 / 6 (33%) | 2 / 6 (33%) |
| N-Gram Repetition Loops | 4 | 3 / 4 (75%) | 0 / 4 (0%) |
| Question Spam (>1 Question) | 6 | 0 / 6 (0%) | 0 / 6 (0%) |
| Benign Safe Coaching Sentences | 10 | 0 / 10 (0% false triggers) | 0 / 10 (0% false triggers) |

`SentenceValidator` and `ResponseVerifier` provide complementary defense-in-depth: the validator performs fast streaming redaction, while the verifier runs holistic invariant checks and triggers iterative LLM repair when violations occur.

### 2.4 Knowledge Tables Ingestion Counts

- `clinical_knowledge_base`: 478 approved/draft guideline chunks.
- `knowledge_chunks`: 482 provenance-tracked chunks across 6 domains:
  - Integrative Health (API): 362
  - Women's Health (PCOS): 87
  - Clinical Nutrition (ICMR-NIN): 23
  - Gastrointestinal Health (MoHFW): 8
  - Food Composition Tables (NIN): 2
  - Cardiovascular Protocols (WHO): 2

## 3. Continuous Quality and Regression Prevention

Behavioral regressions are prevented through automated test gates:
- Unit & Invariant Tests: 604 passing tests executed against a live PostgreSQL 16 container.
- Cryptographic Audit Verification: `test_clinical_safety_and_ledger.py` verifies the SHA-256 chain integrity of the `audit_claim_ledger`.
- Gate Mutation Verification: `test_gate_mutations.py` plants synthetic hardcoded prices and fake secret tokens to verify that safety gates fail closed before deployment.
