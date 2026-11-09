"""Versioned question schemas for Laya System 1 decision engine.

Schema Version: 2026-11-08.v2
Design Conformance: Aligned with LLD Section 2.3 & Disha Clinical Protocol.
Supported Intents: meal_query, symptom_complaint, general_coaching, exercise_query, emergency_escalation, app_meta.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "2026-11-08.v2"
LEGACY_SCHEMA_VERSION = "2026-11-07.v1"

ALL_INTENTS: tuple[str, ...] = (
    "meal_query",
    "symptom_complaint",
    "general_coaching",
    "exercise_query",
    "emergency_escalation",
    "app_meta",
    "greeting",
)

CLINICAL_QUESTIONS: dict[str, dict[str, Any]] = {
    "intent": {
        "type": "choice",
        "instructions": "What is the primary category of the patient statement?",
        "criteria": {
            "meal_query": "food, eating, meals, what to eat, dinner, lunch, breakfast, recipes, diet plan, calories, prescribed food",
            "symptom_complaint": "illness, stomach ache, pain, gas, bloating, fever, acidity, nausea, vomiting, discomfort",
            "general_coaching": "wellness, greeting, walking, steps, daily exercise, sleep, water intake, routine check-in, habit tracking",
            "emergency_escalation": "urgent life-threatening emergency, chest pain, heart attack, severe difficulty breathing, stroke, collapse, heavy bleeding",
        },
    },
    "emergency_triage": {
        "type": "noul",
        "instructions": "Does this message report an acute life-threatening medical emergency?",
    },
    "pep_risk": {
        "type": "score",
        "instructions": "Evaluate the cardiovascular strain and physical exertion intensity of the physical activity mentioned.",
        "criteria": [
            "low risk: brisk walking, gentle stretching, restorative yoga, breathing exercises",
            "moderate risk: light jogging, bodyweight squats, low-impact aerobics, resistance band work",
            "high risk: heavy deadlifts, max-effort weightlifting, competitive CrossFit, high-intensity sprinting",
        ],
    },
}
