# 02. Runtime Components and Ports

```mermaid
flowchart TD
    Browser["Browser SPA"]

    subgraph Inbound["FastAPI routes"]
        Chat["POST /chat"]
        SSE["POST /chat/stream"]
        Voice["/voice and /ws/conversation"]
        Auth["/auth/register, /auth/onboarding, /auth/login"]
        Profile["Patient profile routes"]
    end

    subgraph SharedTurn["Shared turn logic"]
        Breaker["Pattern emergency check"]
        Router["Intent and language routing"]
        Context["Patient/context builder"]
        Retriever["Approved PostgreSQL retriever"]
        Exercise["Selected exercise-risk checks"]
        LLM["Configured LLM adapter"]
        Validator["Sentence validation"]
    end

    subgraph Data["PostgreSQL"]
        Profiles["patient_profiles"]
        PEP["patient_pep"]
        Plans["patient_diet_schedules"]
        Knowledge["clinical_knowledge_base\nclinical_guideline_chunks view"]
        Memory["memory_items / patient_temporal_facts"]
        Journal["patient_turn_journal"]
        Journey["Journey and habit tables"]
    end

    subgraph Adapters["Optional external/local adapters"]
        ProviderChoice["Configured provider selection"]
        Ollama["Optional Ollama"]
        Groq["Optional Groq"]
        Gemini["Optional Gemini"]
        STT["Groq Whisper or local STT"]
        TTS["Qwen3-TTS or Edge-TTS"]
    end

    Browser --> Chat
    Browser --> SSE
    Browser --> Voice
    Browser --> Auth
    Browser --> Profile
    Chat --> Breaker
    SSE --> Breaker
    Voice --> STT
    STT --> Breaker
    Breaker --> Router
    Router --> Context
    Auth --> Profiles
    Profile --> Profiles
    Profile --> PEP
    Context --> PEP
    Context --> Plans
    Context --> Memory
    Context --> Journal
    Context --> Journey
    Context --> Retriever
    Retriever --> Knowledge
    Context --> Exercise
    Exercise --> LLM
    Retriever --> LLM
    LLM --> ProviderChoice
    ProviderChoice -.-> Ollama
    ProviderChoice -.-> Groq
    ProviderChoice -.-> Gemini
    LLM --> Validator
    Validator --> TTS
    TTS --> Voice
```

The diagram is a component map, not a promise that every adapter is enabled. Provider choice and fallback remain owned by `disha_core.llm.client.DualProviderClient` and its environment settings. The chat and voice interfaces return metadata such as validation/retrieval status; knowledge chunk IDs do not prove claim-level entailment.

## Route notes

- `/chat` returns JSON and `/chat/stream` returns sentence SSE events.
- `/voice` and `/ws/conversation` are authenticated WebSockets; the implementation accepts whole audio clips, JSON text, or interrupt messages.
- Registration is exposed at both `/auth/register` and `/auth/onboarding`; login is `/auth/login`.
- Normal patient routes resolve identity from bearer credentials. Do not treat a patient identifier in a request payload as authentication.
- A pattern emergency response can be returned before normal chat authentication; it is not an emergency dispatch integration.
