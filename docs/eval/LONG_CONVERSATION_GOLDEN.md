# Long-Conversation Golden Evaluation

## Purpose

The original golden suite was strong at deterministic safety, prompt integrity, and isolated response checks, but it did not adequately test whether Disha could sustain a relationship across turns. `tests/golden/d_rules_long_conversation.yaml` adds eight multi-turn journeys with explicit user types and channel sequences.

Covered journeys:

- returning user with chat-to-voice continuation;
- natural goal and barrier discovery;
- refusal/autonomy-sensitive user;
- user correction and stale-profile prevention;
- topic shift and later thread resumption;
- terse replies and natural settling;
- English/Hinglish switching across chat and voice;
- anxious symptom conversation with uncertainty and red-flag safety.

## Current evaluation

| Check | Result |
|---|---:|
| Long-conversation corpus cases | 8/8 |
| Existing golden cases | 70/70 |
| Combined deterministic runner | 78/78 |
| System prompt estimate | 594 tokens / 600 limit |

The runner now treats retired style rules consistently with the pytest suite and validates long-conversation fixture contracts: at least four turns, matching channel metadata, non-empty turns, and no repeated exact assistant question.

## What still needs fixing for a true quality gate

The current result is a deterministic corpus/contract score, not a live model quality score. The next evaluation should execute each journey through the production `ResponseHarness` with a pinned model/provider and grade each turn for:

1. reference resolution and use of prior disclosures;
2. repeated-question rate and discovery-field accuracy;
3. correction/refusal compliance;
4. topic-shift recovery;
5. cross-channel continuity;
6. clinical uncertainty and red-flag handling;
7. natural closure versus unnecessary follow-up questions.

Until that provider-backed grader exists, do not describe 78/78 as 100% conversational quality. Treat it as a clean deterministic gate and manually review the eight transcript journeys before changing the active model or prompt.
