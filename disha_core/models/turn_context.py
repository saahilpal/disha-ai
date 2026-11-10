"""Unified per-turn context schema for Disha AI pipeline.

Enforces strict sectioned reads/writes, stage provenance, timing telemetry,
and PHI-safe trace generation across chat and voice pipelines.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class TranscriptSection(BaseModel):
    """Audio transcription inputs and interim stream state."""

    model_config = ConfigDict(extra="forbid")

    interim: str = Field(default="", description="Interim streaming transcript")
    final: str = Field(default="", description="Final finalized transcript")
    is_interim: bool = Field(default=False, description="Whether current turn is interim")
    audio_duration_ms: float = Field(default=0.0, ge=0.0, description="Duration of processed audio")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="ASR confidence score")


class LanguageSection(BaseModel):
    """Language detection, script identification, and boundary checks."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(default="hinglish", description="Language code: en, hi, or hinglish")
    script: str = Field(default="Latn", description="Script: Latn or Deva")
    is_supported: bool = Field(default=True, description="Whether language is within approved tier")
    deflected: bool = Field(default=False, description="Whether deflection was required")


class SafetySection(BaseModel):
    """Clinical emergency breaker and early PEP risk gate outputs."""

    model_config = ConfigDict(extra="forbid")

    breaker_triggered: bool = Field(default=False, description="Emergency red-flag breaker fired")
    category: str | None = Field(default=None, description="Emergency category if triggered")
    response: str | None = Field(default=None, description="Emergency triage instructions")
    pep_risk: int = Field(default=0, ge=0, le=3, description="Laya System-1 PEP risk score (0-3)")
    pep_restricted: bool = Field(default=False, description="Whether contraindicated exercise blocked")


class StageIntentSection(BaseModel):
    """Laya intent routing and Onboarding Stage Engine cursor state."""

    model_config = ConfigDict(extra="forbid")

    intent: str = Field(default="general_coaching", description="Classified intent")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Classifier confidence")
    stage_id: str | None = Field(default=None, description="Current journey stage (S0-S9)")
    slot_id: str | None = Field(default=None, description="Active question slot being addressed")
    scheduled_question: str | None = Field(default=None, description="Scheduled deterministic question")
    is_off_topic: bool = Field(default=False, description="User asked off-topic question during onboarding")
    skip_retrieval: bool = Field(default=False, description="Intent permits skipping RAG lookup")


class PatientBriefSection(BaseModel):
    """Patient snapshot loaded from profile and clinician PEP store."""

    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(default="", description="Unique patient identifier")
    day_ist: str = Field(default="monday", description="Current day of week in Asia/Kolkata")
    meal_type: Literal["breakfast", "lunch", "dinner"] | None = Field(
        default=None, description="Relevant meal window if applicable"
    )
    diet_status: str = Field(default="FOUND", description="Status of diet lookup: FOUND or NOT_FOUND")
    profile_summary: dict[str, Any] = Field(default_factory=dict, description="Safe profile summary")


class MemoryBriefSection(BaseModel):
    """Short-term conversational turns and long-term memory brief."""

    model_config = ConfigDict(extra="forbid")

    history_turns: list[dict[str, str]] = Field(default_factory=list, description="Recent conversation turns")
    disclosed_slots: dict[str, Any] = Field(default_factory=dict, description="Slots extracted this turn")
    contradictions: list[str] = Field(default_factory=list, description="Contradictions flagged")
    has_history: bool = Field(default=False, description="Whether previous context was loaded")


class RetrievalSection(BaseModel):
    """Evidence chunks retrieved from pgvector / RAG corpus."""

    model_config = ConfigDict(extra="forbid")

    evidence_ids: list[str] = Field(default_factory=list, description="IDs of retrieved chunks")
    chunk_count: int = Field(default=0, ge=0, description="Total chunks retrieved")
    tags: list[str] = Field(default_factory=list, description="Clinical/dietary tags used for query")
    skipped: bool = Field(default=False, description="Whether RAG retrieval was skipped by intent router")
    latency_ms: float = Field(default=0.0, ge=0.0, description="Retrieval latency in milliseconds")


class RulesSection(BaseModel):
    """Clinical guardrails and business rules fired during turn."""

    model_config = ConfigDict(extra="forbid")

    rules_fired: list[str] = Field(
        default_factory=list,
        description="List of rule identifiers triggered, e.g. anti_echo, fruit_moderation, zero_pricing",
    )


class DraftSection(BaseModel):
    """Raw generation from LLM provider before sentence validation."""

    model_config = ConfigDict(extra="forbid")

    raw_text: str = Field(default="", description="Raw unvalidated model output")
    model: str = Field(default="", description="LLM model identifier used")
    prompt_tokens: int = Field(default=0, ge=0, description="Input tokens")
    completion_tokens: int = Field(default=0, ge=0, description="Generated tokens")
    latency_ms: float = Field(default=0.0, ge=0.0, description="LLM generation latency in ms")


class ValidatorSection(BaseModel):
    """Clinical sentence validator outputs and boundary enforcements."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(default="validated", description="Validator status, e.g. validated, rewritten, deflected")
    is_rewritten: bool = Field(default=False, description="Whether safety rewrite occurred")
    replacement_reason: str | None = Field(default=None, description="Reason for rewrite if applicable")
    validated_sentences: list[str] = Field(default_factory=list, description="Final approved sentences")
    violations: list[str] = Field(default_factory=list, description="Flagged rule violations")


class SpokenSection(BaseModel):
    """TTS speech synthesis streaming outputs."""

    model_config = ConfigDict(extra="forbid")

    spoken_text: str = Field(default="", description="Concatenated spoken output")
    sentence_count: int = Field(default=0, ge=0, description="Number of TTS audio chunks dispatched")
    audio_bytes_len: int = Field(default=0, ge=0, description="Total audio byte payload")
    tts_latency_ms: float = Field(default=0.0, ge=0.0, description="TTS synthesis latency")


class PlaybackSection(BaseModel):
    """Client-side audio playback lifecycle and interruption tracking."""

    model_config = ConfigDict(extra="forbid")

    completed: bool = Field(default=False, description="Whether playback finished completely")
    interrupted: bool = Field(default=False, description="Whether user barged in during playback")
    interrupted_at_ms: float | None = Field(default=None, description="Millisecond offset when barged in")


class TurnContext(BaseModel):
    """Unified, strongly-typed pipeline context and per-turn trace.

    Each pipeline component strictly reads from upstream sections and writes
    only to its assigned downstream section.
    """

    model_config = ConfigDict(extra="forbid")

    turn_id: str = Field(default_factory=lambda: f"turn_{uuid4().hex[:12]}")
    session_id: str = Field(default_factory=lambda: f"sess_{uuid4().hex[:12]}")
    patient_id: str = Field(default="")
    channel: Literal["chat", "voice"] = Field(default="chat")
    created_at_ts: float = Field(default_factory=time.time)

    # Pipeline stages
    transcript: TranscriptSection = Field(default_factory=TranscriptSection)
    language: LanguageSection = Field(default_factory=LanguageSection)
    safety: SafetySection = Field(default_factory=SafetySection)
    stage_intent: StageIntentSection = Field(default_factory=StageIntentSection)
    patient_brief: PatientBriefSection = Field(default_factory=PatientBriefSection)
    memory_brief: MemoryBriefSection = Field(default_factory=MemoryBriefSection)
    retrieval: RetrievalSection = Field(default_factory=RetrievalSection)
    rules: RulesSection = Field(default_factory=RulesSection)
    draft: DraftSection = Field(default_factory=DraftSection)
    validator: ValidatorSection = Field(default_factory=ValidatorSection)
    spoken: SpokenSection = Field(default_factory=SpokenSection)
    playback: PlaybackSection = Field(default_factory=PlaybackSection)

    # Telemetry
    stage_latencies_ms: dict[str, float] = Field(default_factory=dict)

    def record_stage_latency(self, stage_name: str, duration_ms: float) -> None:
        """Record stage execution duration."""
        self.stage_latencies_ms[stage_name] = round(duration_ms, 2)

    def to_phi_safe_dict(self) -> dict[str, Any]:
        """Produce a telemetry trace dict safe for logging and public dashboards.

        Redacts all raw user utterances, names, and explicit clinical text.
        Retains rule IDs, token counts, latencies, and stage transitions.
        """
        raw_text = self.transcript.final or self.transcript.interim
        text_sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()[:12] if raw_text else "empty"

        return {
            "turn_id": self.turn_id,
            "session_id": self.session_id,
            "patient_hash": hashlib.sha256(self.patient_id.encode("utf-8")).hexdigest()[:12]
            if self.patient_id
            else "anon",
            "channel": self.channel,
            "utterance_length": len(raw_text),
            "utterance_sha256_prefix": text_sha,
            "language": self.language.code,
            "script": self.language.script,
            "safety": {
                "breaker_triggered": self.safety.breaker_triggered,
                "category": self.safety.category,
                "pep_risk": self.safety.pep_risk,
                "pep_restricted": self.safety.pep_restricted,
            },
            "stage_intent": {
                "intent": self.stage_intent.intent,
                "stage_id": self.stage_intent.stage_id,
                "slot_id": self.stage_intent.slot_id,
                "is_off_topic": self.stage_intent.is_off_topic,
                "skip_retrieval": self.stage_intent.skip_retrieval,
            },
            "retrieval": {
                "chunk_count": self.retrieval.chunk_count,
                "evidence_ids": self.retrieval.evidence_ids,
                "skipped": self.retrieval.skipped,
                "latency_ms": self.retrieval.latency_ms,
            },
            "rules_fired": self.rules.rules_fired,
            "tokens": {
                "prompt": self.draft.prompt_tokens,
                "completion": self.draft.completion_tokens,
                "model": self.draft.model,
            },
            "validator": {
                "status": self.validator.status,
                "is_rewritten": self.validator.is_rewritten,
                "replacement_reason": self.validator.replacement_reason,
                "sentence_count": len(self.validator.validated_sentences),
                "violations": self.validator.violations,
            },
            "timing_ms": self.stage_latencies_ms,
        }
