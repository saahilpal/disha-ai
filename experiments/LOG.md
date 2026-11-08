# DISHA AI — EXPERIMENT LOG

## Experiment EXP-001: Local Ollama (`qwen2.5:7b`) Integration & Fallback
- **Hypothesis**: Routing simple turns and local fallback to Ollama `qwen2.5:7b` eliminates external API rate limits and network latency spikes while maintaining clinical coaching quality.
- **Change**: Added `OLLAMA_ENABLED: "true"` and `OLLAMA_URL: "http://host.docker.internal:11434"` to backend service in `docker-compose.yml`. Configured fallback order in `disha_core/llm/client.py`.
- **Metrics**: 0 API timeouts under concurrent load; p50 local inference response ~850ms.
- **Decision**: KEEP.

## Experiment EXP-002: Dynamic Sentence Buffer Length Policy
- **Hypothesis**: Dynamic length budgeting (1-2 sentences for simple QA, 3-4 for complex symptoms) eliminates conversational rambling without truncation errors.
- **Change**: Added `LengthPolicy` across 5 categories in `disha_core/engine/context_builder.py` and enforce in `sentence_buffer.py`.
- **Metrics**: Average response tokens dropped by 38%; conciseness score rose from 68% to 94%.
- **Decision**: KEEP.

