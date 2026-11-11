"""Response Harness Structured Planner.

Produces concise, structured plans (<=80 tokens JSON) containing:
- goal: Turn coaching objective
- coach_moves: Ordered coaching actions
    - question: Supplied PEP candidate when available; otherwise the LLM writes it
- things_to_avoid: Safety, regulatory, and style constraints
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StructuredPlan(BaseModel):
    """Structured turn plan enforced to <= 80 tokens JSON."""

    model_config = ConfigDict(extra="forbid")

    goal: str = Field(description="Primary turn objective")
    coach_moves: list[str] = Field(description="1-3 concise coach actions")
    question: str | None = Field(default=None, description="Supplied fallback question opportunity")
    question_required: bool = Field(default=True, description="Whether F6 requires one closing question")
    things_to_avoid: list[str] = Field(default_factory=list, description="Specific safety/domain boundaries")

    def to_json(self) -> str:
        """Serialize plan to compact JSON string under 80 tokens."""
        data = {
            "goal": self.goal,
            "coach_moves": self.coach_moves,
            "question": self.question,
            "question_required": self.question_required,
            "things_to_avoid": self.things_to_avoid,
        }
        compact = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        # 80 tokens roughly corresponds to ~320 characters
        if len(compact) > 320:
            data["things_to_avoid"] = data["things_to_avoid"][:3]
            data["coach_moves"] = data["coach_moves"][:2]
            compact = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        return compact

    @classmethod
    def from_json(cls, json_str: str) -> StructuredPlan:
        data = json.loads(json_str)
        return cls(
            goal=str(data.get("goal", "")),
            coach_moves=[str(m) for m in data.get("coach_moves", [])],
            question=str(data["question"]) if data.get("question") else None,
            question_required=bool(data.get("question_required", True)),
            things_to_avoid=[str(t) for t in data.get("things_to_avoid", [])],
        )


def build_structured_plan(
    user_input: str,
    context: dict[str, Any] | None = None,
    intent: str | None = None,
) -> StructuredPlan:
    """Deterministically construct a structured turn plan adhering to <=80 token budget."""
    ctx = context or {}
    intent_str = str(intent or ctx.get("intent", "general_coaching")).lower()
    text = user_input.strip()
    lower = text.lower()

    # Detect emotional struggles, setbacks, or frustration
    is_struggle = any(
        w in lower
        for w in (
            "stress",
            "pareshan",
            "nahi ho raha",
            "chhoot gaya",
            "miss ho gaya",
            "frustrated",
            "upset",
            "weight nahi kam ho raha",
            "cheat",
            "regret",
            "give up",
            "demotivated",
            "thak gaya",
            "thak gayi",
            "gussa",
            "tension",
            "mushkil",
            "difficult",
            "tired",
            "guilt",
            "sad",
            "low feel",
        )
    )

    # Detect simple acknowledgment ("okay", "theek hai", "ji")
    is_ack = lower in (
        "ok",
        "okay",
        "theek hai",
        "thik hai",
        "thik h",
        "theek h",
        "ji",
        "haan",
        "han",
        "got it",
        "samajh gaya",
        "samajh gayi",
        "achha",
        "thanks",
        "thank you",
        "dhanyawad",
        "shukriya",
    )

    # Detect direct demand ("jo hai de do", "kuch bhi bata do")
    is_direct_demand = any(
        phrase in lower
        for phrase in (
            "jo hai de do",
            "jo hai dedo",
            "kuch bhi de do",
            "kuch bhi dedo",
            "kuch bhi bata do",
            "kuch bhi batao",
            "give whatever",
            "just tell me",
            "direct batao",
            "jo marzi",
        )
    )

    # Detect repeated inquiry by checking history
    history = ctx.get("conversation_history") or []
    is_repeated_query = False
    if len(history) >= 2:
        last_user_turn = ""
        for h in reversed(history):
            if isinstance(h, dict) and h.get("role") == "user":
                last_user_turn = str(h.get("content", "")).lower()
                break
        if last_user_turn and (
            (lower in last_user_turn or last_user_turn in lower)
            or ("breakfast" in lower and "breakfast" in last_user_turn)
            or ("lunch" in lower and "lunch" in last_user_turn)
            or ("dinner" in lower and "dinner" in last_user_turn)
            or ("exercise" in lower and "exercise" in last_user_turn)
        ):
            is_repeated_query = True

    # 1. Goal
    if is_struggle:
        goal = "Acknowledge struggle with deep empathy without guilt or blame"
    elif is_ack:
        goal = "Warmly acknowledge and offer gentle next step without repeating advice"
    elif is_direct_demand:
        goal = "Provide immediate practical guidance without asking preference questions"
    elif is_repeated_query:
        goal = "Provide fresh alternatives and variety without repeating previous suggestions"
    elif "meal" in intent_str:
        goal = "Address dietary query with verified schedule or grounding"
    elif "exercise" in intent_str:
        goal = "Provide exercise guidance adhering strictly to PEP safety"
    elif "symptom" in intent_str:
        goal = "Acknowledge symptom empathetically without medical diagnosis"
    elif intent_str in {"greeting", "app_meta", "factual"}:
        goal = "Respond directly and warmly to user query"
    else:
        goal = "Provide clear, supportive everyday health coaching"

    # 2. Coach moves
    coach_moves = []
    if is_struggle:
        coach_moves.append("Validate feelings with genuine empathy and care")
        coach_moves.append("Offer one gentle, achievable next step")
    elif is_ack:
        coach_moves.append("Acknowledge warmly and briefly")
        coach_moves.append("Stay available for next step")
    elif is_direct_demand:
        coach_moves.append("Give a concrete, practical suggestion immediately")
    elif is_repeated_query:
        coach_moves.append("Offer fresh variety/alternatives instead of repeating past advice")
    else:
        coach_moves.append("Answer directly in first sentence")
        if ctx.get("has_history"):
            coach_moves.append("Continue thread naturally without re-greeting")
        else:
            coach_moves.append("Adopt warm, empathetic tone")

    # 3. Question: use the existing PEP candidate only as the fallback opportunity;
    # the LLM writes a contextual question when the user's turn provides a hook.
    question: str | None = None
    scheduled_q = ctx.get("scheduled_question")
    if scheduled_q and not ctx.get("is_incomplete_thought"):
        question = str(scheduled_q)

    # 4. Things to avoid
    things_to_avoid = [
        "claims to be doctor/human",
        "unverified pricing",
        "multiple questions",
        "generic quotes",
        "questionnaire tone",
        "end with exactly one meaningful question unless this is an emergency or closing",
    ]
    if is_struggle:
        things_to_avoid.append("judgment or guilt")
        things_to_avoid.append("cheerful toxic positivity")
    if is_repeated_query:
        things_to_avoid.append("repeating same recommendations")
    if is_direct_demand:
        things_to_avoid.append("asking more preference questions")

    pep = ctx.get("pep") or ctx
    diet_pref = str(pep.get("dietary_preference", "")).casefold()
    if "veg" in diet_pref and "non" not in diet_pref and "egg" not in diet_pref:
        things_to_avoid.append("non-veg food")

    restricted = pep.get("restricted_modalities") or ()
    if restricted:
        things_to_avoid.append("restricted exercise")

    if not ctx.get("protocol_approved") and ctx.get("clinical_tags"):
        things_to_avoid.append("unapproved remedies")

    return StructuredPlan(
        goal=goal,
        coach_moves=coach_moves,
        question=question,
        things_to_avoid=things_to_avoid,
    )
