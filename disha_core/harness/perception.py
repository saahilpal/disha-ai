"""Behavior Spec v1 — Structured Turn Perception and Move Selection.

The LLM produces a TurnPerception JSON once per turn. The harness then
deterministically selects the move (no LLM move selection).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TriangleStatus(BaseModel):
    """History Triangle tracking per concern (C1)."""

    model_config = ConfigDict(extra="forbid")

    duration: Literal["unknown", "asked", "answered", "declined"] = "unknown"
    past_attempts: Literal["unknown", "asked", "answered", "declined"] = "unknown"
    severity: Literal["unknown", "asked", "answered", "declined"] = "unknown"

    def next_unanswered(self) -> str | None:
        """Return the next axis to ask about, or None if all are answered/declined."""
        for axis in ("duration", "past_attempts", "severity"):
            if getattr(self, axis) == "unknown":
                return axis
        return None

    def all_complete(self) -> bool:
        """True if every axis is answered or declined."""
        return all(getattr(self, ax) in ("answered", "declined") for ax in ("duration", "past_attempts", "severity"))


class TurnPerception(BaseModel):
    """Structured perception of a single user turn, filled by a single LLM call."""

    model_config = ConfigDict(extra="forbid")

    detected_language: Literal["en", "hi", "hinglish"] = "hinglish"
    detected_script: Literal["latin", "devanagari", "mixed"] = "latin"
    user_act: Literal[
        "answer",
        "refusal",
        "question",
        "disclosure",
        "greeting",
        "correction",
        "other",
    ] = "other"
    answer_quality: Literal["complete", "vague", "incomplete", "na"] = "na"
    missing_info: str | None = None
    current_concern: str | None = None
    triangle_status: TriangleStatus = Field(default_factory=TriangleStatus)
    distress_expressed: bool = False
    medication_inquiry: bool = False
    style_features: list[str] = Field(default_factory=list)

    # Chosen move is set by deterministic code, NOT the LLM
    chosen_move: Literal[
        "emergency",
        "withhold_and_pivot",
        "clarify",
        "triangle_question",
        "intake_slot",
        "clinical_insight",
        "pivot",
        "natural_reply",
    ] = "natural_reply"


# JSON schema instruction appended to the system prompt for the perception call
PERCEPTION_SCHEMA_INSTRUCTION = """Before replying, output a JSON block wrapped in <PLAN>...</PLAN> tags with exactly these fields:
{"detected_language":"en|hi|hinglish","detected_script":"latin|devanagari|mixed","user_act":"answer|refusal|question|disclosure|greeting|correction|other","answer_quality":"complete|vague|incomplete|na","missing_info":null or string,"current_concern":null or string,"triangle_status":{"duration":"unknown|asked|answered|declined","past_attempts":"unknown|asked|answered|declined","severity":"unknown|asked|answered|declined"},"distress_expressed":true|false,"medication_inquiry":true|false,"style_features":[]}
Then write your reply as plain text after the </PLAN> tag."""


def select_move(
    perception: TurnPerception,
    known_slots: set[str] | None = None,
    candidate_slots: list[str] | None = None,
) -> str:
    """Deterministic move selection based on perception state (Section 5.3).

    Precedence:
    1. medication_inquiry → withhold_and_pivot
    2. vague/incomplete answer → clarify
    3. next unanswered Triangle axis → triangle_question
    4. essential intake slot not yet known → intake_slot
    5. triangle complete → clinical_insight
    6. greeting/chit-chat → natural_reply
    7. default → pivot
    """
    # C2+C4: medication or treatment inquiry
    if perception.medication_inquiry:
        return "withhold_and_pivot"

    # M2: clarify vague/incomplete
    if perception.answer_quality in ("vague", "incomplete"):
        return "clarify"

    # C1: next unanswered triangle axis
    next_axis = perception.triangle_status.next_unanswered()
    if next_axis and perception.current_concern:
        return "triangle_question"

    # Intake slot (never a second question, never ask what's known)
    _known = known_slots or set()
    _candidates = candidate_slots or []
    for slot in _candidates:
        if slot not in _known:
            return "intake_slot"

    # Clinical insight only after triangle is complete
    if perception.current_concern and perception.triangle_status.all_complete():
        return "clinical_insight"

    # Greeting / chit-chat → natural reply steering toward concern
    if perception.user_act in ("greeting", "other") and not perception.current_concern:
        return "natural_reply"

    # Default: pivot to expert call
    return "pivot"
