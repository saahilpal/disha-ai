# Disha AI Release-Candidate Engineering Roster

**Order:** FINAL RELEASE-CANDIDATE ORDER: PROVE IT WORKS, FIX IT, MAKE IT SHOW-READY

**Protocol:** Autonomous sub-agents with verified conversation IDs, owned file globs, step budgets, and shared board logging.

**Lead:** `/root` — briefs, reviews, merges, and verdicts

**Updated:** 2026-11-09 15:17 UTC
**Strict Invariants:** Truth rule (prior claims unverified until re-proven), zero pricing claims without verified facts, zero gym clearance claims, 100% green gates.

---

## Active Strike Team & Sub-Agents

| ID | Role | Handle / Subagent Conversation ID | Owned File Globs | Brief / Mission | Step Budget | Status |
|---|---|---|---|---|---|---|
| **01** | Lead / Coordinator | `/root` | `agent/*`, `docs/contracts.md` | Overall architecture, briefs, reviews, merges, gate verdicts | Unlimited | Active |
| **02** | Claims Auditor | `4ef77ed8-717f-4081-acad-6e09f34af557` | `audit/reports/claims_ledger.md` | Exhaustive requirements audit across Order v4, UI order, v5 | 40 | Running |
| **03** | Test-Integrity Auditor | `f83a6e14-55a5-4c75-b93a-f21b600f59e3` | `audit/reports/test_integrity.md`, `tests/*` | Diff tests since baseline, detect flakiness, gate mutation tests | 50 | Running |
| **04** | Clean-Clone Builder | `62412595-70ad-4dae-8ea6-f259c5cefd4d` | `audit/reports/clean_clone_audit.md` | Clone repo to temp dir, execute 60s quickstart on fresh DB | 40 | Running |
| **05** | Wiring Auditor | `14b6577c-3034-4af6-b6b9-a7fb1461baaa` | `audit/reports/wiring_audit.md` | Real chat & voice turn traces; prove components on live path | 50 | Running |
| **06** | Clinical Scenario Tester | `39a74ac5-5fff-4787-9e30-f3c32efb14b4` | `audit/reports/acceptance_clinical_scenarios.md` | 8 known failure scenarios x 3 phrasings x 15 runs; 200+ red flags | 60 | Running |
| **07** | Journey & Memory Tester | `8c0ba4b3-ff29-49cd-be2b-c48d656a8117` | `audit/reports/acceptance_journey_memory.md` | Onboarding in chat & voice, cross-session proof, habit updates | 50 | Running |
| **08** | RAG Tester | `e3f4a19d-fc0e-4979-bbc9-7929c7667e34` | `audit/reports/acceptance_rag.md` | Recall@k, MRR, groundedness, chunk id tracing, embedding audit | 45 | Running |
| **09** | Voice & Latency Tester | `a517d8e7-0a57-4de2-9302-fe4e1f1b76b9` | `audit/reports/acceptance_voice_latency.md` | 50-turn latency (p50/p95), barge-in stop time, interruption safety | 50 | Running |
| **10** | UI Visual QA Auditor | `4ae864fd-d81f-491d-a515-f8ee8b0b23fd` | `audit/reports/acceptance_ui_visual_qa.md` | 8 viewports light/dark inspection, overlap detector, axe, Lighthouse | 50 | Running |
| **11** | Resilience Tester | `719574f1-4a87-4f4b-9883-ba14214bcd80` | `audit/reports/acceptance_resilience.md` | Stack restart, DB kill/restore, tunnel recovery, idempotent replay | 45 | Running |
| **12** | Security Auditor | `aec271b1-3e43-48a5-8e4d-1e64e073c3e6` | `audit/reports/acceptance_security.md` | Gitleaks history, hardcode-check, patient isolation, key rotation | 40 | Running |
| **13** | Demo Producer & Doc Steward | `7a9f10e4-de87-4daa-9fef-8edf80b25230` | `docs/demo/*`, `Makefile`, `README.md` | `make demo`, `SCRIPT.md`, `DESIGN_MAP.md`, `ACCEPTANCE.md` | 50 | Running |
| **14** | Skeptic Gatekeeper | `d98735a3-0c6b-4842-a8a8-c20912fe97ec` | `audit/reports/skeptic_final_audit.md` | Independent verification, attacks every verdict, Go/No-Go gate | 45 | Running |

---

## Operating Directives

1. Every agent posts findings to `agent/board/board.jsonl` using `./scripts/board post`.
2. All reports must contain real execution commands, timings, and raw tool outputs.
3. No claims are accepted without reproducible evidence.
