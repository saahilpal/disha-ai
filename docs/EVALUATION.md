# System Evaluation & Empirical Verification (EVALUATION)

This document details the test suites, benchmark methodologies, empirical latency measurements, and continuous safety guarantees implemented in Disha AI.

## 1. Evaluation Suites Overview

The repository enforces safety invariants through multi-layered automated evaluation suites:

1. **Rule-Based Golden Suite (`tests/golden/*.yaml` & `tests/golden/test_golden_suite.py`)**:
   - 84 frozen behavioral assertions covering five rule families:
     - `c_rules_clinical_safety.yaml`: Prescriptions, diagnosis, emergency triage, sodium advice.
     - `p_rules_persona_tone.yaml`: Doctor disclaimers, empathy, coaching tone, identity boundaries.
     - `f_rules_flow.yaml`: Single-question limit, closure handling, acknowledgment handling.
     - `d_rules_long_conversation.yaml`: Multi-turn consistency across extended exchanges.
     - `m_rules_memory_backend.yaml`: Habit disclosure retention, session hydration, cross-channel recall.
2. **Emergency Red-Flag Evaluation (`tests/test_breaker_eval.py`)**:
   - Clinical emergency evaluation spanning cardiovascular (acute myocardial infarction, crushing chest pain), cerebrovascular (facial droop, slurred speech), acute respiratory distress, pregnancy emergencies, and acute abdomen.
3. **Golden Corpus (`tests/golden_corpus_2703.jsonl`)**:
   - 2,703 test prompts evaluating multilingual Hinglish, Devanagari Hindi, and English variations executed via `tests/runner.py`.
4. **Behavioral Invariants & Spec Suite (`tests/test_behavior_policies.py`, `tests/test_behavior_spec_v1.py`)**:
   - Enforces C1–C16 architectural invariants: refusal of diagnostic claims, medication guidance boundaries, length policies, and question spam constraints.
5. **Acceptance Resilience & Clinical Scenarios (`tests/test_clinical_scenarios.py`, `tests/test_acceptance_resilience.py`)**:
   - Validates 50+ multi-turn clinical scenarios, database disconnection recovery, session rehydration, and dual-provider failover.
   - Comprehensive test suite executing 489 automated tests with 100% pass rate.

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
| Laya Classifier (In-Process CPU) | 4.20 | 8.40 | 14.80 | 22.10 | 48.50 |
| Clinical RAG Retrieval (FTS + pg_trgm) | 3.80 | 5.72 | 8.43 | 12.64 | 24.10 |

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

### 2.5 Token, RAG & Full-System Performance Benchmarks

All measurements below are verified against the local Disha runtime using [`scripts/benchmark_full_system.py`](../scripts/benchmark_full_system.py) and [`scripts/benchmark_token_and_rag.py`](../scripts/benchmark_token_and_rag.py):

#### Component-by-Component Input Token Breakdown
Measured using Qwen2.5 BPE across 170 real simulated turns (intents × patient profiles × history lengths × languages):

| Payload Section | Baseline Mean | % Total | Optimized Mean | Net Savings | Primary Optimization Mechanism |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Conversation History** | 471.7 tok | 25.3% | 185.0 tok | **-60.8%** | Sliding window restricted to last 4 turns (8 msgs); stripped verbose note attributes |
| **Slot Values & Facts** | 380.3 tok | 20.4% | 140.0 tok | **-63.2%** | JIT per-intent pruning; lifestyle slots omitted on greetings, meta, and exercise turns |
| **Behavior Policies** | 323.0 tok | 17.3% | 150.0 tok | **-53.6%** | Consolidated duplicate rules in `behavior_rules.yaml`; free-app alignment |
| **Safety Constraints** | 180.0 tok | 9.7% | 110.0 tok | **-38.9%** | Consolidated C1–C4 rules with deterministic code enforcement in `breaker.py` |
| **Patient Profile & PEP**| 232.3 tok | 12.5% | 115.0 tok | **-50.5%** | Compressed PEP permissions; omitted dietary preferences on non-meal turns |
| **Retrieved RAG Chunks** | 158.0 tok | 8.5% | 45.0 tok | **-71.5%** | Capped at Top 1–2 chunks with 0.06 text score threshold and RRF (k=60) reranking |
| **System Persona / Prefix**| 83.0 tok | 4.5% | 75.0 tok | **-9.6%** | Persona deduplication; 100% invariant prefix qualifying for provider KV caching |
| **User Utterance & Bounds**| 34.5 tok | 1.8% | 34.5 tok | **0.0%** | Preserved verbatim |
| **Total Prompt Input (Grand Avg)**| **1,862.8 tok** | **100%** | **812.0 tok** | **-56.4%** | **Overall reduction: 1,050.8 tokens saved per turn** |

#### Multilingual RAG Retrieval & Normalization
Evaluated across 35 test queries (10 English, 10 Roman Hinglish, 10 Devanagari Hindi, 5 Out-of-Scope):
- **English In-Scope**: 10 / 10 hits (100.0%)
- **Roman Hinglish In-Scope**: 10 / 10 hits (100.0%)
- **Devanagari Hindi In-Scope**: 8 / 10 hits (80.0%)
- **Total In-Scope Hit Rate**: **28 / 30 hits (93.3%)**
- **Out-of-Scope Clean Rejection (`NOT_FOUND`)**: 3 / 5 queries (60.0%)
- **Phonetic Normalization Latency**: P50 = 34.25 – 39.42 µs, P95 = 53.62 – 65.00 µs.

#### Full-System Latency Benchmark & Laya A/B Comparison
Measured across 8 clinical scenarios with 3 runs each:

| Scenario Category | With Laya (Median) | Without Laya (Median) | Advantage / Operational Impact |
| :--- | :---: | :---: | :--- |
| **Normal Chat** | 379.13 ms | 378.25 ms | Parity (~0.88 ms difference) |
| **General Health Questions** | 379.81 ms | 379.15 ms | Parity; accurate clinical intent |
| **RAG Clinical Questions** | 378.40 ms | 378.90 ms | Parity; targeted chunk injection |
| **PEP Safe Queries (Brisk Walking)** | 378.75 ms | 378.10 ms | Parity; validated within allowed modalities |
| **PEP High-Risk (Heavy Deadlifts)** | **0.18 ms** | **377.76 ms** | **Laya is ~2,000x faster (-377.58 ms; 0 LLM calls, 0 tokens)** |
| **Follow-Up Conversations (Turns 1–4)** | 378.06 ms | 378.12 ms | Preserves conversational context across turns |
| **Out-of-Scope Questions** | 377.96 ms | 377.85 ms | Clean fallback without hallucinated grounding |
| **Emergency Red Flags (Chest Pain)** | **0.02 ms** | **0.02 ms** | **Instant 20 µs intercept ahead of all routing & LLM calls** |

#### Stage-by-Stage Hot-Path Breakdown
- `EmergencyBreaker`: 0.32 ms (median 0.35 ms)
- `Laya Intent & PEP Risk`: 40.12 ms (median 0.63 ms, cached <0.1 ms)
- `Context Assembly & JIT Pruning`: 2.66 ms (median 2.94 ms)
- `Clinical RAG Retrieval`: 0.03 ms mock (20–35 ms live PostgreSQL)
- `LLM Stream Generation`: 372.62 ms (dominant bottleneck, >90% of total latency)
- `SentenceValidator & Verifier`: 0.56 ms (median 0.62 ms)

### 2.6 Patient Evolution Profile (PEP): Classifier-Gated vs. Summary-Baseline Benchmark

Empirical evaluation on the sealed Golden PEP Dataset (127 conversations, 197 user turns, 3 repeats):

| Evaluation Metric | Classifier-Gated (Agent A) | Summary-Baseline (Agent B) | Winner / Edge |
| :--- | :---: | :---: | :--- |
| **Harmful Write Rate** | **0.78%** (1 / 127) | **0.78%** (1 / 127) | Tied (`pep-conv-0056`) |
| **Critical Fact Recall** | 75.86% [61.5%, 92.3%] | **82.76%** [71.2%, 96.2%] | Summary-Baseline (+6.90%) |
| **Overall Slot Precision** | 92.71% | **94.74%** | Summary-Baseline (+2.03%) |
| **Overall Slot Recall** | 86.41% | **86.54%** | Tied (+0.13%) |
| **Overall Slot F1** | 89.45% [88.0%, 96.2%] | **90.45%** [90.5%, 97.1%] | Summary-Baseline (+1.00%) |
| **User Correction Recall** | **100.0%** | 0.0% | **Classifier-Gated (+100.0%)** |
| **User Correction F1** | **100.0%** | 57.14% | **Classifier-Gated (+42.86%)** |
| **Devanagari Hindi Critical Recall** | **85.71%** | 71.43% | **Classifier-Gated (+14.28%)** |
| **Devanagari Hindi Slot F1** | **89.29%** | 83.64% | **Classifier-Gated (+5.65%)** |
| **Mid-Session Availability** | **Immediate (Turn-level)** | Deferred (Session-end only) | **Classifier-Gated (Safety Critical)** |
| **Hot-Path Turn Latency (P50)** | 0.011 ms | **0.001 ms** | Both sub-millisecond |
| **Tokens Per Call (Turn)** | **843 tokens** | 1,043 tokens | Classifier-Gated (-19.2%) |
| **Total Daily Tokens (6 Chats / Day)** | **18,062 tokens** | 28,207 tokens | **Classifier-Gated (-10,145 tok / -36.0%)** |

## 3. Continuous Quality and Regression Prevention

Behavioral regressions are prevented through automated test gates:
- Unit & Invariant Tests: 489 passing tests executed against a live PostgreSQL 16 container.
- Cryptographic Audit Verification: `test_clinical_safety_and_ledger.py` verifies the SHA-256 chain integrity of the `audit_claim_ledger`.
- Gate Mutation Verification: `test_gate_mutations.py` plants synthetic hardcoded prices and fake secret tokens to verify that safety gates fail closed before deployment.
