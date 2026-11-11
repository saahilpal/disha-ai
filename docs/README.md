# Disha AI — Documentation Map

This directory contains the canonical documentation for the Disha AI conversational health coach architecture.

---

## Start here

- [`HOW_IT_WORKS.md`](HOW_IT_WORKS.md): runtime flow, ports, persistence, and safety boundaries.
- [`DEPLOYMENT.md`](DEPLOYMENT.md): local Compose, local-only models, tunnel operation, and limitations.
- [`ARCHITECTURE.md`](ARCHITECTURE.md): system architecture and component boundaries.
- [`SECURITY.md`](SECURITY.md): security, secrets, and data-handling notes.

## Specifications & policies

- [`spec/BEHAVIOR_SPEC.md`](spec/BEHAVIOR_SPEC.md): owner-provided Behavior Spec v1.
- [`spec/ENFORCEMENT_MATRIX.md`](spec/ENFORCEMENT_MATRIX.md): rule-to-code and rule-to-test mapping.
- [`spec/IMPLEMENTATION_NOTES.md`](spec/IMPLEMENTATION_NOTES.md): decided defaults and configuration.
- [`spec/PROMPT_DIFF.md`](spec/PROMPT_DIFF.md): rendered prompt comparison.

---

## Core architecture & operation

- [`MEMORY_AND_PEP.md`](MEMORY_AND_PEP.md): patient memory and personalization.
- [`VOICE_PIPELINE.md`](VOICE_PIPELINE.md): streaming voice path and known limitations.
- [`contracts.md`](contracts.md): core interfaces and data contracts.
- [`LEARNINGS.md`](LEARNINGS.md): consolidated engineering learnings.
- [`theory/HOW_DISHA_THINKS.md`](theory/HOW_DISHA_THINKS.md): decision pipeline and guardrails.

---

## Architecture diagrams

The living Mermaid diagrams are in [`architecture/`](architecture/): system context, runtime components, voice turns, retrieval, memory, deployment, and agent collaboration. Run `python3 scripts/diagram-check` after changing one.

---

## Engineering records

- [`changes/WHY.md`](changes/WHY.md): architectural decision ledger.
- [`adr/`](adr/): numbered architectural decision records.
- [`OWNERS.yaml`](OWNERS.yaml): code-to-documentation ownership rules.

Other design, research, evaluation, demo, and map documents remain available in their folders. Prefer the guides above for current operational truth; historical reports describe the state at the time they were written.

