# 05. Onboarding and Conversation Context

```mermaid
flowchart TD
    Turn["Chat or voice turn"]
    Auth["Resolve patient identity"]
    Context["Load current context"]
    PEP["patient_pep"]
    Facts["Active patient_temporal_facts"]
    Slots["Active memory_items"]
    History["Latest journal messages"]
    Meal["Optional active approved meal schedule"]
    Extract["Journey disclosure extraction"]
    Store["Mapped profile / PEP / memory / journey writes"]
    Prompt["Shared turn prompt"]
    Response["Validated response"]
    Journal["Append completed user/assistant messages"]
    Cache["Process-local history cache"]

    Turn --> Auth
    Auth --> Context
    Context --> PEP
    Context --> Facts
    Context --> Slots
    Context --> History
    Context --> Meal
    Turn --> Extract
    Extract --> Store
    Context --> Prompt
    Prompt --> Response
    Response --> Journal
    Response --> Cache
    Journal -.->|"rehydrate recent messages"| History
```

## Account and journey data

- Registration at `/auth/register` or `/auth/onboarding` writes account/profile fields, a hash of the bearer token, and selected PEP fields. The service stores supplied conditions/goals as user-provided data; it does not establish clinician verification.
- The request model accepts some safety-related values that registration does not currently copy to PEP safety columns. For implementation details see [Memory and PEP](../MEMORY_AND_PEP.md).
- During turns, `disha_core.journey` extracts disclosures and maps them to configured profile, PEP, memory, temporal-fact, or habit/episode destinations and tracks journey questions/state. These are application-level mappings, not proof of a clinician-only write gate.

## Short-term context behavior

- The context builder reads up to sixteen most recent messages from `patient_turn_journal`.
- The prompt path uses chronological history messages (up to sixteen messages / eight user/assistant pairs) and injects `<CONVERSATION_STATE>` to handle references like "that", "same", "why", and "okay".
- Older relevant exchanges outside the recent window are retrieved via conversation history RAG into `<RELEVANT_PAST_CONVERSATION>`.
- All turns (normal generation, emergency/safety deflections, and provider errors) commit to `patient_turn_journal` and update in-memory cache.
- Active pending onboarding questions are deferred (`status = 'skipped'`, `skip_reason = 'deferred: topic_shift'`) when the user switches topics.
- The `/chat/history` endpoint provides full client hydration on page reload, preserving continuous conversation.

The memory and journey schema is broader than the context loaded into a single prompt. Table existence does not imply that every value is used, current, clinically reviewed, or proven.
