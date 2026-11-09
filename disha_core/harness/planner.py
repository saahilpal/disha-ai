"""Response Harness Structured Planner.

Produces concise, structured plans (<=80 tokens JSON) containing:
- goal: Turn coaching objective
- coach_moves: Ordered coaching actions
- question: At most 1 question (<=1 question rule)
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
    question: str | None = Field(default=None, description="At most 1 targeted follow-up question")
    things_to_avoid: list[str] = Field(default_factory=list, description="Specific safety/domain boundaries")

    def to_json(self) -> str:
        """Serialize plan to compact JSON string under 80 tokens."""
        data = {
            "goal": self.goal,
            "coach_moves": self.coach_moves,
            "question": self.question,
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

    # 1. Goal
    if "meal" in intent_str:
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
    coach_moves = ["Answer directly in first sentence"]
    if ctx.get("has_history"):
        coach_moves.append("Continue thread naturally without re-greeting")
    else:
        coach_moves.append("Adopt warm, empathetic tone")

    # 3. Question (<= 1 question strictly enforced)
    question: str | None = None
    scheduled_q = ctx.get("scheduled_question")
    if scheduled_q and not ctx.get("is_incomplete_thought"):
        question = str(scheduled_q)
    elif ctx.get("is_incomplete_thought"):
        question = "Aap aaram se batayein ki kaisa feel ho raha hai?"
    elif intent_str in {"greeting", "general_coaching"} and not ctx.get("has_history"):
        question = "Main aapki health routine mein kaise madad kar sakti hoon?"
    elif intent_str in {"factual", "app_meta"} or "price" in text.lower():
        question = None

    # 4. Things to avoid
    things_to_avoid = [
        "claims to be doctor/human",
        "unverified pricing",
        "multiple questions",
    ]

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
