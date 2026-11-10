# Disha AI — Documentation Map (`docs/README.md`)

This directory contains the canonical documentation for the Disha AI conversational health coach architecture.

---

## 1. Specifications & Policies (`docs/spec/`)
- [`docs/spec/BEHAVIOR_SPEC.md`](file:///Users/nitrousoxide/Code/disha%20ai/docs/spec/BEHAVIOR_SPEC.md): Owner-provided final Behavior Spec v1 with IDs (P1-P6, F1-F5, C1-C4, M1-M3).
- [`docs/spec/ENFORCEMENT_MATRIX.md`](file:///Users/nitrousoxide/Code/disha%20ai/docs/spec/ENFORCEMENT_MATRIX.md): Complete audit matrix mapping every rule ID to code layer, test, and verification status.
- [`docs/spec/IMPLEMENTATION_NOTES.md`](file:///Users/nitrousoxide/Code/disha%20ai/docs/spec/IMPLEMENTATION_NOTES.md): Decided defaults D2 through D5, risk analysis, and configuration parameters.
- [`docs/spec/PROMPT_DIFF.md`](file:///Users/nitrousoxide/Code/disha%20ai/docs/spec/PROMPT_DIFF.md): Side-by-side diff comparing legacy prompt to the ≤600-token Spec v1 rendered prompt.

---

## 2. Core Architecture & Operation (`docs/`)
- [`docs/HOW_IT_WORKS.md`](file:///Users/nitrousoxide/Code/disha%20ai/docs/HOW_IT_WORKS.md): Plain-language tour of the running system, ports, chat/voice paths, persistence, and safety.
- [`docs/theory/HOW_DISHA_THINKS.md`](file:///Users/nitrousoxide/Code/disha%20ai/docs/theory/HOW_DISHA_THINKS.md): Theoretical cognitive model: decision pipeline, layered guardrails, and History Triangle.
- [`docs/LEARNINGS.md`](file:///Users/nitrousoxide/Code/disha%20ai/docs/LEARNINGS.md): Consolidated engineering learnings from real incidents, bug fixes, and safety audits.
- [`docs/DELETIONS.md`](file:///Users/nitrousoxide/Code/disha%20ai/docs/DELETIONS.md): Ledger of intentionally deleted dead files, deprecated mocks, and removed legacy assets.
- [`docs/contracts.md`](file:///Users/nitrousoxide/Code/disha%20ai/docs/contracts.md): Core component interface contracts and data models (`TurnContext`, `SentenceValidator`).

---

## 3. Living Mermaid Diagrams (`docs/architecture/`)
- [`docs/architecture/01_system_context.md`](file:///Users/nitrousoxide/Code/disha%20ai/docs/architecture/01_system_context.md): System boundary and external integrations context diagram.
- [`docs/architecture/02_runtime_components.md`](file:///Users/nitrousoxide/Code/disha%20ai/docs/architecture/02_runtime_components.md): Internal runtime component wiring and data flows.
- [`docs/architecture/03_voice_turn_sequence.md`](file:///Users/nitrousoxide/Code/disha%20ai/docs/architecture/03_voice_turn_sequence.md): Voice streaming sequence from VAD and ASR through LLM and TTS.
- [`docs/architecture/04_rag_ingestion_and_retrieval.md`](file:///Users/nitrousoxide/Code/disha%20ai/docs/architecture/04_rag_ingestion_and_retrieval.md): RAG pipeline, pgvector embedding index, and hybrid retrieval.
- [`docs/architecture/05_memory_and_stage_engine.md`](file:///Users/nitrousoxide/Code/disha%20ai/docs/architecture/05_memory_and_stage_engine.md): PEP memory lifecycle and stage candidate generation.
- [`docs/architecture/06_deployment_topology.md`](file:///Users/nitrousoxide/Code/disha%20ai/docs/architecture/06_deployment_topology.md): Container deployment topology, NGINX proxy, and Cloudflare tunnel.
- [`docs/architecture/07_agent_collaboration.md`](file:///Users/nitrousoxide/Code/disha%20ai/docs/architecture/07_agent_collaboration.md): Multi-agent execution ledger and orchestration state.

---

## 4. Interview & Narrative Artifacts (`docs/interview/`)
- [`docs/interview/STORY.md`](file:///Users/nitrousoxide/Code/disha%20ai/docs/interview/STORY.md): One-page narrative of the project origin, problem statement, and architectural turnaround.
- [`docs/interview/QA.md`](file:///Users/nitrousoxide/Code/disha%20ai/docs/interview/QA.md): 20 honest, evidence-backed engineering questions and answers across system design and safety.
- [`docs/interview/GLOSSARY.md`](file:///Users/nitrousoxide/Code/disha%20ai/docs/interview/GLOSSARY.md): Definitions of key concepts (PEP, History Triangle, Zero-Echo, Barge-in, Breaker).
- [`docs/interview/RCA/`](file:///Users/nitrousoxide/Code/disha%20ai/docs/interview/RCA/): Root cause analyses for refresh loss, greeting lectures, and voice continuity bugs.

---

## 5. Engineering Records & Changes (`docs/changes/`)
- [`docs/changes/WHY.md`](file:///Users/nitrousoxide/Code/disha%20ai/docs/changes/WHY.md): Architectural justification ledger for non-trivial codebase modifications.
- [`docs/OWNERS.yaml`](file:///Users/nitrousoxide/Code/disha%20ai/docs/OWNERS.yaml): Code-to-documentation mapping rules verified by `scripts/docs-drift`.

