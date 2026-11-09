# 03. Voice Turn Sequence

```mermaid
sequenceDiagram
    actor User
    participant Browser
    participant WS as FastAPI WebSocket
    participant STT as Groq or local STT
    participant Turn as Shared turn pipeline
    participant DB as PostgreSQL
    participant LLM as Configured LLM adapter
    participant Gate as Sentence validator
    participant TTS as Configured TTS adapter

    User->>Browser: Records a complete utterance
    Browser->>WS: Authenticate, send binary audio clip
    WS->>STT: Transcribe completed clip
    STT-->>WS: Transcript
    WS->>Turn: execute_voice_turn(transcript)
    Turn->>DB: Load context and approved knowledge as needed
    DB-->>Turn: User context / retrieved rows
    Turn->>LLM: Stream prompt and recent messages
    LLM-->>Gate: Incremental response text
    Gate->>Gate: Buffer and validate sentence output
    Gate-->>TTS: Validated sentence
    TTS-->>WS: Audio chunks
    WS-->>Browser: Transcript, sentence/status events, binary audio
    Browser-->>User: Play response

    opt Interrupt or a new turn while processing
        Browser->>WS: Interrupt message or new turn
        WS->>Turn: Cancel active task and stop synthesis
        WS-->>Browser: interrupted event
    end
```

Audio transcription operates on a completed WebSocket message, not interim microphone frames. In normal mode Groq STT requires the explicit processing flag and key; `LOCAL_ONLY` requires a local STT endpoint. Output synthesis uses configured Qwen3-TTS/Edge-TTS paths with independent egress checks. See [Voice Pipeline](../VOICE_PIPELINE.md) for message contract and provider limits.
