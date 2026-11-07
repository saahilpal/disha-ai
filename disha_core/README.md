# Disha AI Core

This folder contains the deterministic safety and retrieval core plus a local Docker Compose deployment. Compose publishes only NGINX on `127.0.0.1:8080`; PostgreSQL and FastAPI stay on a private Docker network.

## Run locally

Export runtime variables in the shell, then run Compose with an empty interpolation file so Docker Compose does not read the repository `.env`:

```sh
export POSTGRES_PASSWORD='a-long-url-safe-random-password'
docker compose --env-file /dev/null -f compose.yaml up --build -d
```

API keys are passed through from the shell environment. They are not required for startup; if provider configuration, health-data authorization, or the explicit Groq usage-charge flag is missing, ordinary model generation returns a fixed unavailable response. Emergency handling and database readiness remain local.

The `/voice` WebSocket expects an initial JSON message `{"type":"auth","token":"..."}`, then one complete audio clip per binary frame. A new frame cancels the active response for barge-in. Groq Whisper and Edge TTS require separate `GROQ_HEALTH_DATA_PROCESSING_APPROVED` and `EDGE_TTS_HEALTH_DATA_PROCESSING_APPROVED` flags; both default off. Whisper is a cloud file-transcription call, not local streaming STT.

PostgreSQL executes `db/schema.sql` only when it initializes an empty volume. Schema changes need a reviewed migration; do not remove `postgres_data` to apply them.

## Patient access

`/chat` and `/chat/stream` require a bearer token whose SHA-256 digest is in `patient_access_tokens`. The API resolves the patient from that digest; request bodies cannot choose a patient ID. Tokens are not seeded. An operator can issue one with `python -m disha_core.admin PATIENT_ID`; the one-time token is printed to stdout and expires after 30 days by default.

## Safety and data limits

The emergency matcher ships with the small reviewed-in-repo example lexicon only; the 1,200-pattern clinician-approved corpus is not present, so this is not a production-ready emergency detector. The reviewed 1,500-turn golden corpus is also not present. `python -m disha_core.tests.runner CORPUS --sha256 PINNED_SHA256` refuses to claim the evaluation gate without it.

No ICMR-NIN/MoHFW advice, dosage, or home remedy is seeded. Only approved clinician-reviewed database rows can be retrieved. No HealthCareMagic, MedDialog, ChatDoctor, MedMCQA, IndicCorp, or Samanantar data is used or bundled.

The LLM, transcription, and Edge TTS services are external egress. Health-data and billable-usage flags default off. Google’s unpaid Gemini service must not receive sensitive or personal health information. Groq currently publishes usage prices and account-specific quotas; code cannot guarantee a free quota or a $0 bill. Set provider flags only after the deployment has an approved data-processing basis, cost controls, and service terms; a zero-cost demo configuration is not a clinical deployment approval.

The audit queue is in-memory. A process crash can lose queued records, and queue overflow is reported as a dropped event; it is not a durable compliance ledger.

This local Compose deployment has no public TLS certificate, patient identity provider, admin token-provisioning flow, clinician authoring UI, or loaded Laya ONNX artifact. Do not expose it publicly until those production integrations and the clinical corpora are supplied and reviewed.
