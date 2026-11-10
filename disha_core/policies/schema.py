"""Pydantic schemas for Disha AI Behavior Policies and Situation Cards.

Enforces strict structural invariants, example counts, language categorization,
and clinical coaching parameters.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ExampleType(str, Enum):
    """Categorization of few-shot example."""

    GOOD = "good"
    BAD = "bad"


class ExampleLanguage(str, Enum):
    """Language codes for localized examples."""

    EN = "en"
    HI = "hi"
    HINGLISH = "hinglish"


class PolicyStatus(str, Enum):
    """Lifecycle status of a situation policy."""

    ACTIVE = "active"
    DRAFT = "draft"
    DEPRECATED = "deprecated"


class PolicyExample(BaseModel):
    """A concrete few-shot example demonstrating recommended or anti-pattern response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_input: str = Field(..., min_length=1, description="Sample user query or message")
    response: str = Field(..., min_length=1, description="Exemplary or cautionary response")
    type: ExampleType = Field(..., description="Whether this is a good or bad example")
    language: ExampleLanguage = Field(..., description="Language: en, hi, or hinglish")
    critique: str = Field(
        ...,
        min_length=5,
        description="Clinical/coaching rationale explaining why this is good or bad",
    )


class SituationPolicy(BaseModel):
    """A behavioral policy card governing assistant behavior in a specific clinical/coaching situation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    situation_id: str = Field(..., min_length=2, description="Unique situation identifier")
    triggers: list[str] = Field(..., min_length=1, description="Trigger keywords, phrases, or conditions")
    objective: str = Field(..., min_length=10, description="Coaching or clinical objective")
    must: list[str] = Field(..., min_length=1, description="Mandatory actions / invariants")
    must_not: list[str] = Field(..., min_length=1, description="Prohibited actions / anti-patterns")
    response_shape: str = Field(..., min_length=5, description="Structural response format")
    coach_moves: list[str] = Field(..., min_length=1, description="Recommended coaching moves / techniques")
    examples: list[PolicyExample] = Field(..., description="Few-shot examples")
    owner: str = Field(..., min_length=2, description="Team or clinician owner")
    version: str = Field(..., min_length=1, description="Semantic version string")
    status: PolicyStatus = Field(default=PolicyStatus.ACTIVE, description="Lifecycle status")

    @field_validator("examples")
    @classmethod
    def validate_example_distribution(cls, v: list[PolicyExample]) -> list[PolicyExample]:
        good_count = sum(1 for ex in v if ex.type == ExampleType.GOOD)
        bad_count = sum(1 for ex in v if ex.type == ExampleType.BAD)
        if good_count < 2:
            raise ValueError(f"Each card must contain at least 2 good examples, found {good_count}")
        if bad_count < 2:
            raise ValueError(f"Each card must contain at least 2 bad examples, found {bad_count}")
        return v

    @property
    def good_examples(self) -> list[PolicyExample]:
        return [ex for ex in self.examples if ex.type == ExampleType.GOOD]

    @property
    def bad_examples(self) -> list[PolicyExample]:
        return [ex for ex in self.examples if ex.type == ExampleType.BAD]


class PolicyPack(BaseModel):
    """Root container model for behavior policies collection."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    version: str = Field(..., description="Policy pack version")
    updated_at: str | None = Field(default=None, description="ISO timestamp of last update")
    description: str | None = Field(default=None, description="Overview of policy pack")
    policies: list[SituationPolicy] = Field(..., description="List of situation cards")

    @model_validator(mode="before")
    @classmethod
    def normalize_policies_key(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "policies" not in data and "situations" in data:
                data = dict(data)
                data["policies"] = data["situations"]
            elif "policies" not in data and isinstance(data.get("cards"), list):
                data = dict(data)
                data["policies"] = data["cards"]
        return data

    @field_validator("policies")
    @classmethod
    def validate_unique_situation_ids(cls, v: list[SituationPolicy]) -> list[SituationPolicy]:
        seen: set[str] = set()
        for p in v:
            if p.situation_id in seen:
                raise ValueError(f"Duplicate situation_id: {p.situation_id}")
            seen.add(p.situation_id)
        return v
