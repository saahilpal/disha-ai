"""Multi-Field Information Extraction Layer for Patient Disclosures.

Parses natural conversational turns across English, Hindi, and Hinglish.
Distinguishes between:
- Clinically diagnosed conditions vs transient symptoms.
- Permanent lifestyle habits vs one-off deviations.
- Captures multiple fields in a single turn.
"""

from __future__ import annotations

import re
from typing import Any

from disha_core.models.slots import (
    normalize_dietary_restrictions,
    normalize_meal_preferences,
    normalize_steps_target,
    normalize_tea_coffee_frequency,
    normalize_time,
    normalize_water_intake,
)

# Symptom words that are transient complaints rather than diagnosed diseases
TRANSIENT_SYMPTOM_WORDS = (
    "pet kharab",
    "loose motion",
    "bloating",
    "gas",
    "acidity",
    "sir dard",
    "headache",
    "fever",
    "bukhar",
    "body pain",
    "badan dard",
    "vomiting",
    "ulti",
    "weakness",
    "chakkar",
    "thakan",
    "tired",
)

# Clinical condition patterns
CONDITION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:hypertension|high\s+bp|high\s+blood\s+pressure|bp\s+ki\s+bimari)\b", re.I), "hypertension"),
    (re.compile(r"\b(?:type\s*[12]\s+diabetes|diabetes|sugar\s+ki\s+bimari|madhumeh)\b", re.I), "type2_diabetes"),
    (re.compile(r"\b(?:thyroid|hypothyroid|hyperthyroid)\b", re.I), "thyroid"),
    (re.compile(r"\b(?:pcod|pcos)\b", re.I), "pcod"),
    (re.compile(r"\b(?:heart\s+disease|cardiac|heart\s+attack|dil\s+ki\s+bimari)\b", re.I), "cardiac_history"),
    (
        re.compile(
            r"\b(?:none|no\s+conditions?|koi\s+bimari\s+nahi|kuch\s+nahi|kuch\s+ni|sab\s+theek\s+hai|koi\s+dikkat\s+nahi|koi\s+issue\s+nahi|bilkul\s+nahi|not\s+diagnosed)\b",
            re.I,
        ),
        "none",
    ),
]

# Generalized negative responses to closed questions
NEGATIVE_AFFIRMATION_PATTERN = re.compile(
    r"^\s*(?:nhi|nahi|nah|no|nope|na|nothing|none|kuch\s+nahi|kuch\s+ni|bilkul\s+nahi|not\s+really|koi\s+bhi\s+nahi|aisa\s+kuch\s+nahi|kuch\s+bhi\s+nahi|no\s+issue|all\s+good|sab\s+theek\s+hai)\b",
    re.I,
)

# Medication patterns
MEDICATION_PATTERN = re.compile(
    r"\b(?:metformin|amlodipine|atorvastatin|aspirin|insulin|atenolol|losartan|telmisartan|thyronorm|pantocid)\b",
    re.I,
)

# Work schedule patterns
WORK_SCHEDULE_PATTERNS = [
    (re.compile(r"\b(?:night\s+shifts?|raat\s+ki\s+shifts?|night\s+duty)\b", re.I), "night_shift"),
    (re.compile(r"\b(?:day\s+shifts?|morning\s+shifts?|general\s+shifts?|din\s+ki\s+shifts?)\b", re.I), "day_shift"),
    (re.compile(r"\b(?:rotational(?:\s+shifts?)?|badalti\s+rehti\s+hai|shifting)\b", re.I), "rotational"),
    (re.compile(r"\b(?:desk\s+job|sitting\s+job|it\s+job|wfh|work\s+from\s+home)\b", re.I), "sedentary_desk_job"),
]


def extract_patient_disclosures(
    text: str,
    lang: str = "hinglish",
    pending_field: str | None = None,
) -> dict[str, Any]:
    """Parse a user utterance and return a mapping of extracted journey fields.

    If pending_field is provided, contextually interprets direct affirmations
    and negative responses (e.g. 'nhi', 'nahi', 'no', 'haan') towards that field.
    """
    if not text:
        return {}

    extracted: dict[str, Any] = {}
    lower = text.strip().lower()

    # Contextual resolution for negative affirmations when answering pending questions
    is_negative = bool(NEGATIVE_AFFIRMATION_PATTERN.search(lower))
    if pending_field and is_negative:
        if pending_field in ("diagnosed_conditions", "health_conditions"):
            extracted["diagnosed_conditions"] = ["none"]
            return extracted
        if pending_field == "medications":
            extracted["medications"] = ["none"]
            return extracted
        if pending_field in ("allergies_intolerances", "dietary_restrictions"):
            extracted["allergies_intolerances"] = ["none"]
            return extracted
        if pending_field == "injuries_or_limitations":
            extracted["injuries_or_limitations"] = ["none"]
            return extracted
        if pending_field == "disliked_foods":
            extracted["disliked_foods"] = ["none"]
            return extracted

    # 1. Transient symptoms vs Diagnosed conditions
    # Check transient symptoms first
    found_symptoms: list[str] = []
    for sym in TRANSIENT_SYMPTOM_WORDS:
        if sym in lower:
            found_symptoms.append(sym)
    if found_symptoms:
        # User reported transient symptom, NOT a diagnosis
        extracted["symptoms"] = found_symptoms

    # Check diagnosed conditions
    # Only if phrased as diagnosed or longstanding, or answering conditions question
    found_conditions: list[str] = []
    for pattern, canonical in CONDITION_PATTERNS:
        if pattern.search(lower):
            found_conditions.append(canonical)
    if found_conditions:
        # Check if user explicitly stated "no conditions"
        if "none" in found_conditions:
            extracted["diagnosed_conditions"] = ["none"]
        else:
            extracted["diagnosed_conditions"] = [c for c in found_conditions if c != "none"]
    elif pending_field in ("diagnosed_conditions", "health_conditions") and is_negative:
        extracted["diagnosed_conditions"] = ["none"]

    # 2. Medications
    meds = MEDICATION_PATTERN.findall(lower)
    if meds:
        extracted["medications"] = list(dict.fromkeys(meds))

    # 3. Work Schedule
    for pat, label in WORK_SCHEDULE_PATTERNS:
        if pat.search(lower):
            extracted["work_schedule"] = label
            break

    # 4. Sleep & Wake timings
    # Prefer pre-verb time expressions: "7:30 baje uthta hoon", "11:30 baje sota hoon"
    wake_match = re.search(
        r"(\d{1,2}(?::\d{2})?\s*(?:am|pm|subah|morning)?)\s*(?:baje\s+)?(?:ko\s+)?(?:uthta|uthti|wake)",
        lower,
    )
    if not wake_match:
        wake_match = re.search(
            r"(?:wake|uthta|uthti|wake\s+up|jagne).{0,15}?(?:around|at|ko)?\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm|subah|morning)?)(?:\s*baje)?",
            lower,
        )
    if wake_match:
        norm_wake = normalize_time(wake_match.group(1), lang)
        if norm_wake:
            extracted["wake_time"] = norm_wake

    sleep_match = re.search(
        r"(\d{1,2}(?::\d{2})?\s*(?:am|pm|subah|raat|in\s+the\s+morning|at\s+night)?)\s*(?:baje\s+)?(?:ko\s+)?(?:sota|soti|sleep)",
        lower,
    )
    if not sleep_match:
        sleep_match = re.search(
            r"(?:sleep|sota|soti|bedtime|so\s+jata|so\s+jati).{0,15}?(?:around|at|ko)?\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm|subah|raat|in\s+the\s+morning|at\s+night)?)(?:\s*baje)?",
            lower,
        )
    if sleep_match:
        raw_sleep = sleep_match.group(1)
        # Contextual morning/night cues
        if (
            ("morning" in lower or "subah" in lower)
            and "am" not in raw_sleep
            and "pm" not in raw_sleep
            and "raat" not in raw_sleep
        ):
            raw_sleep = f"{raw_sleep} am"
        elif (
            ("night" in lower or "raat" in lower or "shaam" in lower)
            and "am" not in raw_sleep
            and "pm" not in raw_sleep
        ):
            raw_sleep = f"{raw_sleep} pm"
        norm_sleep = normalize_time(raw_sleep, lang)
        if norm_sleep:
            extracted["sleep_time"] = norm_sleep

    # 5. Water Intake
    water_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:liter|litre|l\b|liters|litres|glass|gilas|glasses)\s*(?:water|paani|pani)?", lower
    )
    if not water_match:
        water_match = re.search(r"(?:water|paani|pani).{0,15}?(\d+(?:\.\d+)?)\s*(?:liter|litre|l\b|glass)", lower)
    if water_match:
        extracted["water_intake_target"] = normalize_water_intake(water_match.group(0), lang)

    # 6. Tea / Coffee
    if any(w in lower for w in ("chai", "tea", "coffee")):
        tc = normalize_tea_coffee_frequency(text, lang)
        if tc:
            extracted["tea_coffee_frequency"] = tc

    # 7. Dietary Preference
    if any(w in lower for w in ("veg", "vegetarian", "non-veg", "jain", "satvik", "vegan", "shakahari", "mansahari")):
        diet_norm = normalize_meal_preferences(text, lang)
        if diet_norm:
            extracted["dietary_preference"] = diet_norm

    # 8. Allergies / Restrictions
    if any(
        w in lower
        for w in ("allergy", "allergic", "lactose", "gluten", "pyaaz", "lehsun", "onion", "garlic", "nuts", "peanuts")
    ):
        restrs = normalize_dietary_restrictions(text, lang)
        if restrs:
            extracted["allergies_intolerances"] = restrs

    # 9. Disliked Foods
    dislike_match = re.search(
        r"(?:karela|tinda|baingan|lauki|tori|palak|milk|doodh).{0,35}?(?:pasand\s+nahi|dislike|hate|nahi\s+khata|nahi\s+khati)",
        lower,
    )
    if not dislike_match:
        dislike_match = re.search(
            r"(?:pasand\s+nahi|dislike|hate|nahi\s+khata|nahi\s+khati).{0,35}?(karela|tinda|baingan|lauki|tori|palak|milk|doodh)",
            lower,
        )
    if dislike_match:
        food_item = "karela" if "karela" in lower else ("tinda" if "tinda" in lower else "baingan")
        extracted["disliked_foods"] = [food_item]

    # 10. Goals
    if any(w in lower for w in ("weight loss", "vajan kam", "wazan kam", "fat loss", "weight loose")):
        extracted["primary_health_goal"] = "weight_loss"
    elif any(w in lower for w in ("bp control", "blood pressure control", "bp kam")):
        extracted["primary_health_goal"] = "blood_pressure_management"
    elif any(w in lower for w in ("stamina", "fitness", "muscle", "active rehna")):
        extracted["primary_health_goal"] = "general_fitness"

    # 11. Steps / Movement
    steps_match = re.search(r"(\d+[\d,]*)\s*(?:steps|kadam)", lower)
    if steps_match:
        extracted["daily_movement_level"] = normalize_steps_target(steps_match.group(1), lang)

    # 12. Basic Profile (Height, Weight, Age, Name)
    wt_matches = list(re.finditer(r"(\d+(?:\.\d+)?)\s*(?:kg|kilos?|kilograms?)", lower))
    if wt_matches:
        # In corrections or multi-weight statements, the latter number represents the current/updated weight
        extracted["weight_kg"] = float(wt_matches[-1].group(1))

    ht_matches = list(re.finditer(r"(\d{2,3})\s*(?:cm|centimeters?)", lower))
    if ht_matches:
        extracted["height_cm"] = float(ht_matches[-1].group(1))

    age_match = (
        re.search(r"\b(\d{1,2})\s*(?:years?(?:\s+old)?|yrs?(?:\s+old)?|yo\b|saal(?:\s+ka|\s+ki)?|varsh|sal)\b", lower)
        or re.search(
            r"\b(?:i\s+am|i\'m|\bim\b|am|my\s+age(?:\s+is)?|age(?:\s+is)?|umer(?:\s+hai|\s+is)?|umar(?:\s+hai|\s+is)?|meri\s+(?:umar|age)(?:\s+hai|\s+bhi)?)\s*(?:is|hai|:|-)?\s*(\d{1,2})\b",
            lower,
        )
        or re.search(r"\b(?:around|turning|about)\s*(\d{1,2})\b", lower)
        or (re.match(r"^\s*(?:age\s*)?(\d{1,2})\s*$", lower.strip()))
    )
    if age_match:
        val = int(age_match.group(1))
        if 10 <= val <= 110:
            extracted["age"] = val

    name_match = re.search(r"(?:mera\s+naam|my\s+name\s+is|i\s+am)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)", text, re.I)
    if name_match:
        cand_name = name_match.group(1).strip()
        if cand_name.lower() not in ("disha", "patient", "user", "fine", "good"):
            extracted["name"] = cand_name

    return extracted
