# DISHA AI — ENGINEERING TASK TRACKER

| Task ID | Task Description | Owner | Status | Dependencies | Test Evidence / Metrics |
|---------|------------------|-------|--------|--------------|--------------------------|
| W0-01 | Baseline Inventory & Secret Scrub | Boss / Agent F | DONE | None | `audit/disha-fit/evidence/blog_raw.html` key scrubbed, 0 secrets in repo |
| W0-02 | Invariant Testing & Unit Test Suite | Agent H | DONE | W0-01 | 113/113 passing across 6 suites in 27.76s |
| W0-03 | Local Ollama (`qwen2.5:7b`) Failover | Agent G | DONE | W0-01 | `docker-compose.yml` configured, `host.docker.internal:11434` responsive |
| W1-01 | Dynamic Length Policy & Anti-Echo Filter | Agent A | DONE | W0-02 | `disha_core/engine/anti_echo.py`, 17/17 tests passing in `test_reasoning_and_quality.py` |
| W1-02 | Laya Clinical Intent Classifier v2 & Routing | Agent B | DONE | W0-02 | `2026-11-08.v2` schema, non-clinical DB bypass, early PEP triage |
| W1-03 | Hybrid Database Retrieval & PEP Persistence | Agent C | DONE | W0-02 | PostgreSQL `patient_turn_journal`, `patient_temporal_facts`, 7/7 tests passing |
| W1-04 | Qwen3-TTS & Speech Pipeline Real-Time | Agent D | DONE | W0-02 | `stream_qwen3_tts`, Hinglish phonetic normalizer, 12/12 tests passing |
| W1-05 | 25-Scenario Golden Dataset & Benchmark Runner | Agent E / Boss | DONE | W0-02 | `golden_dataset.json` (25 clinical scenarios), `run_eval.py` (12 dimensions) |
| W2-01 | Backend Security Limiting & Zero-PHI Scrubbing | Agent F | DONE | W0-02 | 20 auth/min, 60 chat/min, 2MB body limit, 23/23 tests passing |
| W2-02 | Responsive UI/UX Centering & Dose Theme | Agent I | DONE | W0-02 | Hallmark sloplint `0 FAIL, 0 REFLEX, 0 WARN`, Playwright 8/8 passing |
| W2-03 | Validator Sentence Deduplication & False Positives | Boss | DONE | W1-01 | Deduplication in `sentence_buffer.py`, specific workout regex in `validator.py` |
| W3-01 | Golden Benchmark Execution & Baseline Scoring | Boss / Agent H | DONE | W2-03 | 25/25 passed (100.0%), avg latency 4.05s, 0 hallucinations |
| W3-02 | Engineering Learnings Update & Final Release Sign-off | Boss | DONE | W3-01 | Documentation ledger `docs/ENGINEERING_LEARNINGS.md` [ENTRY-019] |
