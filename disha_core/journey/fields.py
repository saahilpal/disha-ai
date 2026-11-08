"""Field Registry and PEP Mapping for the 5-Stage Patient Journey.

Defines each journey field, its associated stage, data type, requirement level,
safety flags, destination table/column, and normalization/validation rules.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from disha_core.models.slots import (
    normalize_dietary_restrictions,
    normalize_meal_preferences,
    normalize_steps_target,
    normalize_tea_coffee_frequency,
    normalize_time,
    normalize_water_intake,
)


class FieldDestination(str, Enum):
    PROFILE = "patient_profiles"
    PEP_CORE = "patient_pep"
    HABIT_SLOT = "habit_current_state"
    HABIT_OBSERVATION = "habit_observations"
    HABIT_EPISODE = "habit_episodes"
    TEMPORAL_FACT = "patient_temporal_facts"


@dataclass(frozen=True)
class JourneyField:
    field_id: str
    name: str
    description: str
    stage: int  # 1 to 5
    required: bool
    safety_critical: bool
    destination: FieldDestination
    dest_column: str
    data_type: str  # "str", "int", "float", "list", "dict", "bool"
    validator: Callable[[Any, str], Any] | None = None


def _validate_str(val: Any, lang: str = "hinglish") -> str:
    if not val:
        return ""
    return str(val).strip()


def _validate_int(val: Any, lang: str = "hinglish") -> int:
    if isinstance(val, int):
        return val
    m = re.search(r"\d+", str(val))
    return int(m.group(0)) if m else 0


def _validate_float(val: Any, lang: str = "hinglish") -> float:
    if isinstance(val, (int, float)):
        return float(val)
    m = re.search(r"(\d+(?:\.\d+)?)", str(val))
    return float(m.group(1)) if m else 0.0


def _validate_list(val: Any, lang: str = "hinglish") -> list[str]:
    if isinstance(val, (list, tuple, set)):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        items = re.split(r"[,;।\n]+", val)
        return [x.strip() for x in items if x.strip()]
    return []


# Canonical 5-Stage Journey Field Registry
JOURNEY_FIELDS: dict[str, JourneyField] = {
    # -------------------------------------------------------------
    # Stage 1: Basic Patient Profile
    # -------------------------------------------------------------
    "name": JourneyField(
        field_id="name",
        name="Patient Full Name",
        description="Patient primary given/family name.",
        stage=1,
        required=True,
        safety_critical=False,
        destination=FieldDestination.PROFILE,
        dest_column="name",
        data_type="str",
        validator=_validate_str,
    ),
    "age": JourneyField(
        field_id="age",
        name="Age",
        description="Patient age in years.",
        stage=1,
        required=True,
        safety_critical=False,
        destination=FieldDestination.PROFILE,
        dest_column="age",
        data_type="int",
        validator=_validate_int,
    ),
    "gender": JourneyField(
        field_id="gender",
        name="Gender",
        description="Biological sex / gender identity.",
        stage=1,
        required=True,
        safety_critical=False,
        destination=FieldDestination.PROFILE,
        dest_column="gender",
        data_type="str",
        validator=_validate_str,
    ),
    "height_cm": JourneyField(
        field_id="height_cm",
        name="Height (cm)",
        description="Standing height in centimeters.",
        stage=1,
        required=True,
        safety_critical=False,
        destination=FieldDestination.PROFILE,
        dest_column="height_cm",
        data_type="float",
        validator=_validate_float,
    ),
    "weight_kg": JourneyField(
        field_id="weight_kg",
        name="Current Weight (kg)",
        description="Current measured body weight in kilograms.",
        stage=1,
        required=True,
        safety_critical=False,
        destination=FieldDestination.PROFILE,
        dest_column="weight_kg",
        data_type="float",
        validator=_validate_float,
    ),
    "language": JourneyField(
        field_id="language",
        name="Preferred Language",
        description="Primary conversation language (English, Hindi, Hinglish).",
        stage=1,
        required=False,
        safety_critical=False,
        destination=FieldDestination.PROFILE,
        dest_column="language",
        data_type="str",
        validator=_validate_str,
    ),

    # -------------------------------------------------------------
    # Stage 2: Health Background and Safety
    # -------------------------------------------------------------
    "diagnosed_conditions": JourneyField(
        field_id="diagnosed_conditions",
        name="Diagnosed Health Conditions",
        description="Clinician-diagnosed conditions (hypertension, diabetes, pcod, etc.).",
        stage=2,
        required=True,
        safety_critical=True,
        destination=FieldDestination.PEP_CORE,
        dest_column="diagnosed_conditions",
        data_type="list",
        validator=_validate_list,
    ),
    "medications": JourneyField(
        field_id="medications",
        name="Current Medications",
        description="Current active prescription medications.",
        stage=2,
        required=False,
        safety_critical=True,
        destination=FieldDestination.TEMPORAL_FACT,
        dest_column="current_medications",
        data_type="list",
        validator=_validate_list,
    ),
    "allergies_intolerances": JourneyField(
        field_id="allergies_intolerances",
        name="Allergies & Intolerances",
        description="Food, environmental, or pharmaceutical allergies.",
        stage=2,
        required=False,
        safety_critical=True,
        destination=FieldDestination.HABIT_SLOT,
        dest_column="dietary_restrictions",
        data_type="list",
        validator=normalize_dietary_restrictions,
    ),
    "symptoms": JourneyField(
        field_id="symptoms",
        name="Current User-Reported Symptoms",
        description="Active transient complaints (bloating, headache, knee ache).",
        stage=2,
        required=False,
        safety_critical=False,
        destination=FieldDestination.HABIT_EPISODE,
        dest_column="description",
        data_type="list",
        validator=_validate_list,
    ),
    "injuries_or_limitations": JourneyField(
        field_id="injuries_or_limitations",
        name="Physical Limitations or Past Injuries",
        description="Musculoskeletal injuries, chronic back/joint pain.",
        stage=2,
        required=False,
        safety_critical=True,
        destination=FieldDestination.TEMPORAL_FACT,
        dest_column="physical_limitations",
        data_type="list",
        validator=_validate_list,
    ),
    "exercise_clearance": JourneyField(
        field_id="exercise_clearance",
        name="Doctor Gym/Exercise Clearance",
        description="Clinician-certified gym clearance and activity permissions.",
        stage=2,
        required=False,
        safety_critical=True,
        destination=FieldDestination.PEP_CORE,
        dest_column="gym_clearance",
        data_type="bool",
    ),

    # -------------------------------------------------------------
    # Stage 3: Lifestyle and Daily Routine
    # -------------------------------------------------------------
    "work_schedule": JourneyField(
        field_id="work_schedule",
        name="Work Shift Schedule",
        description="Daily working hours, shift structure (day, night, rotational).",
        stage=3,
        required=True,
        safety_critical=False,
        destination=FieldDestination.HABIT_SLOT,
        dest_column="work_schedule",
        data_type="str",
        validator=_validate_str,
    ),
    "wake_time": JourneyField(
        field_id="wake_time",
        name="Morning Wake Time",
        description="Daily waking time in 24-hr format (HH:MM).",
        stage=3,
        required=True,
        safety_critical=False,
        destination=FieldDestination.HABIT_SLOT,
        dest_column="wake_time",
        data_type="str",
        validator=normalize_time,
    ),
    "sleep_time": JourneyField(
        field_id="sleep_time",
        name="Night Sleep Time",
        description="Daily bedtime in 24-hr format (HH:MM).",
        stage=3,
        required=True,
        safety_critical=False,
        destination=FieldDestination.HABIT_SLOT,
        dest_column="sleep_time",
        data_type="str",
        validator=normalize_time,
    ),
    "daily_movement_level": JourneyField(
        field_id="daily_movement_level",
        name="Daily Movement / Step Target",
        description="Daily activity and walking steps goal.",
        stage=3,
        required=False,
        safety_critical=False,
        destination=FieldDestination.HABIT_SLOT,
        dest_column="daily_steps_target",
        data_type="int",
        validator=normalize_steps_target,
    ),
    "exercise_habits": JourneyField(
        field_id="exercise_habits",
        name="Current Exercise Habits",
        description="Existing physical exercises, walking, yoga, or workouts.",
        stage=3,
        required=False,
        safety_critical=False,
        destination=FieldDestination.TEMPORAL_FACT,
        dest_column="exercise_habits",
        data_type="str",
        validator=_validate_str,
    ),
    "water_intake_target": JourneyField(
        field_id="water_intake_target",
        name="Daily Water Intake (Liters)",
        description="Target fluid intake in liters per day.",
        stage=3,
        required=False,
        safety_critical=False,
        destination=FieldDestination.HABIT_SLOT,
        dest_column="water_intake_target",
        data_type="float",
        validator=normalize_water_intake,
    ),
    "tea_coffee_frequency": JourneyField(
        field_id="tea_coffee_frequency",
        name="Tea / Coffee Frequency",
        description="Daily cups of tea, chai, or coffee.",
        stage=3,
        required=False,
        safety_critical=False,
        destination=FieldDestination.HABIT_SLOT,
        dest_column="tea_coffee_frequency",
        data_type="dict",
        validator=normalize_tea_coffee_frequency,
    ),

    # -------------------------------------------------------------
    # Stage 4: Goals, Diet and Personal Preferences
    # -------------------------------------------------------------
    "primary_health_goal": JourneyField(
        field_id="primary_health_goal",
        name="Primary Health Goal",
        description="Main motivation (weight loss, BP control, diabetes management, fitness).",
        stage=4,
        required=True,
        safety_critical=False,
        destination=FieldDestination.PEP_CORE,
        dest_column="primary_focus",
        data_type="str",
        validator=_validate_str,
    ),
    "secondary_health_goals": JourneyField(
        field_id="secondary_health_goals",
        name="Secondary Health Goals",
        description="Additional wellness aspirations (stamina, sleep, gut health).",
        stage=4,
        required=False,
        safety_critical=False,
        destination=FieldDestination.PEP_CORE,
        dest_column="secondary_focuses",
        data_type="list",
        validator=_validate_list,
    ),
    "dietary_preference": JourneyField(
        field_id="dietary_preference",
        name="Dietary Style",
        description="Core diet style (Vegetarian, Non-Vegetarian, Jain, Satvik, Eggetarian, Vegan).",
        stage=4,
        required=True,
        safety_critical=True,
        destination=FieldDestination.PEP_CORE,
        dest_column="dietary_preference",
        data_type="str",
        validator=normalize_meal_preferences,
    ),
    "disliked_foods": JourneyField(
        field_id="disliked_foods",
        name="Disliked Foods & Ingredients",
        description="Vegetables or foods the patient actively dislikes (karela, tinda, etc.).",
        stage=4,
        required=False,
        safety_critical=False,
        destination=FieldDestination.TEMPORAL_FACT,
        dest_column="disliked_foods",
        data_type="list",
        validator=_validate_list,
    ),
    "cultural_regional_preferences": JourneyField(
        field_id="cultural_regional_preferences",
        name="Regional Cuisine Preferences",
        description="Regional cuisine style (North Indian, South Indian, Gujarati, Bengali, etc.).",
        stage=4,
        required=False,
        safety_critical=False,
        destination=FieldDestination.TEMPORAL_FACT,
        dest_column="regional_cuisine",
        data_type="str",
        validator=_validate_str,
    ),
    "cooking_preparation_habits": JourneyField(
        field_id="cooking_preparation_habits",
        name="Meal Preparation Habits",
        description="Cooks at home, eats out, or has food prepared by family/cook.",
        stage=4,
        required=False,
        safety_critical=False,
        destination=FieldDestination.TEMPORAL_FACT,
        dest_column="meal_prep_habits",
        data_type="str",
        validator=_validate_str,
    ),

    # -------------------------------------------------------------
    # Stage 5: Validation, Missing Gaps & Personalisation Readiness
    # -------------------------------------------------------------
    "personalisation_readiness": JourneyField(
        field_id="personalisation_readiness",
        name="Coaching Personalisation Readiness",
        description="System verification that minimum essential profile is safe and actionable.",
        stage=5,
        required=True,
        safety_critical=True,
        destination=FieldDestination.PEP_CORE,
        dest_column="is_personalized",
        data_type="bool",
    ),
}


def get_stage_fields(stage: int, required_only: bool = False) -> list[JourneyField]:
    """Return all fields belonging to a specific stage."""
    fields = [f for f in JOURNEY_FIELDS.values() if f.stage == stage]
    if required_only:
        return [f for f in fields if f.required]
    return fields


def get_required_fields_by_stage() -> dict[int, list[str]]:
    """Return mapping of stage number to list of required field IDs."""
    res: dict[int, list[str]] = {s: [] for s in range(1, 6)}
    for f in JOURNEY_FIELDS.values():
        if f.required:
            res[f.stage].append(f.field_id)
    return res
