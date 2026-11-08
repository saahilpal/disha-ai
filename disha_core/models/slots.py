"""Canonical Slot Registry for Patient Habits, Lifestyle, and PEP Clinical Boundaries.

Covers English, Hindi (Devanagari script), and Hinglish (Romanized Hindi).
Defines slot schemas, normalizers, source authority validation, and clinical boundary guards.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("disha_core.models.slots")


class SourceAuthority(str, Enum):
    """Authority source governing slot permissions and updates."""
    PEP_DOCTOR = "PEP_DOCTOR"
    PATIENT_REPORTED = "PATIENT_REPORTED"
    CLINICIAN = "CLINICIAN"


class EpistemicStatus(str, Enum):
    """Epistemic state of an asserted memory item or fact."""
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RESOLVED = "resolved"
    CONTRADICTED = "contradicted"
    FLAGGED_REVIEW = "flagged_review"


# Devanagari to Arabic numeral translation map
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# Hindi word to numeric mappings
HINDI_NUMBER_WORDS: dict[str, float] = {
    "ek": 1.0, "एक": 1.0,
    "do": 2.0, "दो": 2.0,
    "teen": 3.0, "तीन": 3.0,
    "chaar": 4.0, "char": 4.0, "चार": 4.0,
    "paanch": 5.0, "panch": 5.0, "पांच": 5.0, "पाँच": 5.0,
    "chhah": 6.0, "che": 6.0, "chhe": 6.0, "छह": 6.0, "छः": 6.0,
    "saat": 7.0, "सात": 7.0,
    "aath": 8.0, "आठ": 8.0,
    "nau": 9.0, "नौ": 9.0,
    "das": 10.0, "दस": 10.0,
    "gyarah": 11.0, "ग्यारह": 11.0,
    "baarah": 12.0, "बारह": 12.0,
    "aadha": 0.5, "आधा": 0.5,
    "dedh": 1.5, "डेढ़": 1.5,
    "dhai": 2.5, "ढाई": 2.5,
    "hazar": 1000.0, "hazaar": 1000.0, "हजार": 1000.0, "हज़ार": 1000.0,
}


def _clean_text(text: str) -> str:
    """Normalize unicode, strip commas in numbers, and strip extra spaces."""
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(DEVANAGARI_DIGITS)
    # Remove commas between digits like 10,000 -> 10000
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    return " ".join(text.split())


def _extract_number(text: str) -> float | None:
    """Extract numeric value considering digits and Hindi number words."""
    cleaned = _clean_text(text).lower()

    # Check for direct decimal or integer
    num_match = re.search(r"(\d+(?:\.\d+)?)", cleaned)
    if num_match:
        val = float(num_match.group(1))
        if "hazar" in cleaned or "hazaar" in cleaned or "हजार" in cleaned or "k" in cleaned:
            # e.g., "10 hazar" or "10k"
            if val < 100:
                val *= 1000.0
        return val

    # Check Hindi number words
    words = cleaned.split()
    total = 0.0
    found = False
    for i, w in enumerate(words):
        if w in HINDI_NUMBER_WORDS:
            num = HINDI_NUMBER_WORDS[w]
            found = True
            if num == 1000.0:
                total = (total or 1.0) * 1000.0
            else:
                total += num
    return total if found else None


def normalize_time(val: Any, lang: str = "hinglish") -> str:
    """Normalize wake or sleep time to standard 'HH:MM' 24-hour string."""
    if isinstance(val, str) and re.match(r"^\d{2}:\d{2}$", val.strip()):
        return val.strip()

    s = _clean_text(str(val)).lower()

    is_night = any(w in s for w in ("रात", "raat", "night", "shaam", "sham", "evening", "pm", "सोना", "sota", "sote", "soti"))
    is_morning = any(w in s for w in ("सुबह", "subah", "subha", "morning", "am", "उठना", "uthta", "uthti", "uthte"))

    # Match hour and minute
    m = re.search(r"(\d{1,2})(?::(\d{2}))?", s)
    if m:
        hr = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0

        if is_night and hr < 12 and "am" not in s:
            hr += 12
        elif is_morning and hr == 12:
            hr = 0
        elif not is_morning and not is_night:
            # Default heuristics based on hour
            if "pm" in s and hr < 12:
                hr += 12
            elif "am" in s and hr == 12:
                hr = 0

        return f"{hr:02d}:{minute:02d}"

    # Fallback to word extraction
    words = s.split()
    for w in words:
        if w in HINDI_NUMBER_WORDS:
            hr = int(HINDI_NUMBER_WORDS[w])
            if is_night and hr < 12:
                hr += 12
            return f"{hr:02d}:00"

    return str(val).strip()


def normalize_water_intake(val: Any, lang: str = "hinglish") -> float:
    """Normalize water intake target to liters (float)."""
    if isinstance(val, (int, float)):
        return round(float(val), 2)

    s = _clean_text(str(val)).lower()
    num = _extract_number(s)
    if num is None:
        return 2.5  # Standard clinical baseline default

    # If expressed in glasses (गिलास, glass, glasses)
    if any(g in s for g in ("glass", "glasses", "गिलास", "gilas")):
        # Standard clinical assumption: 1 glass = 250ml = 0.25L
        return round(num * 0.25, 2)

    # If expressed in ml
    if "ml" in s or "मिली" in s:
        return round(num / 1000.0, 2)

    return round(num, 2)


def normalize_meal_preferences(val: Any, lang: str = "hinglish") -> str:
    """Normalize dietary preferences across English, Hindi, and Hinglish."""
    if not val:
        return "Vegetarian"
    s = _clean_text(str(val)).lower()

    if any(w in s for w in ("pure veg", "pure vegetarian", "shuddh shakahari")):
        return "Vegetarian"
    if any(q in s for q in ("chhod diya", "band kar diya", "quit non-veg", "stopped non-veg", "left non-veg")) and "veg" in s:
        return "Vegetarian"

    if any(w in s for w in ("jain", "जैन", "no onion", "bina pyaaz")):
        return "Jain"
    if any(w in s for w in ("satvik", "सात्विक")):
        return "Satvik"
    if any(w in s for w in ("vegan", "वीगन")):
        return "Vegan"
    if any(w in s for w in ("egg", "eggetarian", "अंडा", "anda")):
        return "Eggetarian"
    if any(w in s for w in ("non-veg", "non veg", "nonveg", "meat", "chicken", "mutton", "fish", "मांसाहारी", "mansahari")):
        return "Non-Vegetarian"
    if any(w in s for w in ("veg", "vegetarian", "शाकाहारी", "shakahari")):
        return "Vegetarian"

    return str(val).strip().title()


def normalize_dietary_restrictions(val: Any, lang: str = "hinglish") -> list[str]:
    """Normalize dietary restrictions and allergies into canonical token list."""
    if isinstance(val, (list, tuple, set)):
        items = list(val)
    elif isinstance(val, str):
        items = re.split(r"[,;।\n]+", val)
    else:
        return []

    tokens: list[str] = []
    for item in items:
        s = _clean_text(str(item)).lower()
        if not s:
            continue
        if any(w in s for w in ("pyaaz", "lehsun", "garlic", "onion", "प्याज", "लहसुन")):
            tokens.append("no_onion_garlic")
        elif any(w in s for w in ("namak", "salt", "sodium", "नमक", "सोडियम", "low salt", "low sodium")):
            tokens.append("low_sodium")
        elif any(w in s for w in ("sugar", "cheeni", "shakkar", "चीनी", "शक्कर", "meetha", "diabetic")):
            tokens.append("sugar_free")
        elif any(w in s for w in ("gluten", "ग्लूटेन", "wheat", "gehun")):
            tokens.append("gluten_free")
        elif any(w in s for w in ("lactose", "milk", "doodh", "दूध", "dairy")):
            tokens.append("lactose_intolerant")
        elif any(w in s for w in ("nut", "peanut", "moongphali", "मूंगफली")):
            tokens.append("nut_allergy")
        else:
            clean_token = re.sub(r"[^\w]+", "_", s).strip("_")
            if clean_token:
                tokens.append(clean_token)

    # Return deduplicated sorted tokens
    return sorted(list(dict.fromkeys(tokens)))


def normalize_steps_target(val: Any, lang: str = "hinglish") -> int:
    """Normalize daily step count to integer."""
    if isinstance(val, int):
        return val
    s = _clean_text(str(val)).lower()
    num = _extract_number(s)
    if num is not None:
        return int(num)
    return 8000  # Default clinical baseline step target


def normalize_tea_coffee_frequency(val: Any, lang: str = "hinglish") -> dict[str, Any]:
    """Normalize tea/coffee consumption frequency."""
    s = _clean_text(str(val)).lower()

    if any(w in s for w in ("band", "nahi", "no tea", "नहीं", "none", "zero", "zero tea")):
        return {"tea_cups_per_day": 0, "coffee_cups_per_day": 0, "frequency_label": "none"}

    num = _extract_number(s) or 2.0
    is_coffee = any(w in s for w in ("coffee", "कॉफ़ी", "कॉफी"))
    is_tea = any(w in s for w in ("tea", "chai", "चाय")) or not is_coffee

    tea_count = int(num) if is_tea else 0
    coffee_count = int(num) if is_coffee else 0

    return {
        "tea_cups_per_day": tea_count,
        "coffee_cups_per_day": coffee_count,
        "raw_text": s,
        "frequency_label": f"{int(num)} cups/day",
    }


def normalize_physical_activity_clearance(val: Any, lang: str = "hinglish") -> dict[str, Any]:
    """Normalize PEP-controlled physical activity clearance."""
    if isinstance(val, dict):
        return {
            "gym_clearance": bool(val.get("gym_clearance", False)),
            "allowed_modalities": list(val.get("allowed_modalities") or []),
            "restricted_modalities": list(val.get("restricted_modalities") or []),
            "clinician_certified": bool(val.get("clinician_certified", True)),
        }
    if isinstance(val, bool):
        return {
            "gym_clearance": val,
            "allowed_modalities": ["brisk_walking", "light_stretching"] if val else ["walking"],
            "restricted_modalities": ["heavy_weightlifting", "hiit"] if not val else [],
            "clinician_certified": True,
        }
    return {
        "gym_clearance": False,
        "allowed_modalities": ["walking"],
        "restricted_modalities": ["heavy_weightlifting", "hiit"],
        "clinician_certified": False,
    }


@dataclass(frozen=True)
class SlotDefinition:
    """Canonical metadata definition for a habit, lifestyle, or clinical boundary slot."""
    key: str
    prompt_label: str
    valid_types: tuple[type, ...]
    normalization_rules: Callable[[Any, str], Any]
    sensitive_flag: bool
    source_authority: SourceAuthority
    category: str = "lifestyle"
    description: str = ""


@dataclass(frozen=True)
class ContradictionResult:
    """Result of checking a patient's self-reported claim against PEP clinical constraints."""
    is_contradiction: bool
    slot_key: str
    reported_value: Any
    pep_restriction: str = ""
    reason: str = ""
    flagged_for_review: bool = False


# Canonical 8 Slots Specification
CANONICAL_SLOTS: list[SlotDefinition] = [
    SlotDefinition(
        key="wake_time",
        prompt_label="Morning Wake Time",
        valid_types=(str,),
        normalization_rules=normalize_time,
        sensitive_flag=False,
        source_authority=SourceAuthority.PATIENT_REPORTED,
        category="circadian",
        description="Patient daily wake time (HH:MM 24-hr format).",
    ),
    SlotDefinition(
        key="sleep_time",
        prompt_label="Night Sleep Time",
        valid_types=(str,),
        normalization_rules=normalize_time,
        sensitive_flag=False,
        source_authority=SourceAuthority.PATIENT_REPORTED,
        category="circadian",
        description="Patient daily sleep time (HH:MM 24-hr format).",
    ),
    SlotDefinition(
        key="water_intake_target",
        prompt_label="Daily Water Intake Target",
        valid_types=(float, int),
        normalization_rules=normalize_water_intake,
        sensitive_flag=False,
        source_authority=SourceAuthority.PATIENT_REPORTED,
        category="hydration",
        description="Daily hydration target in liters.",
    ),
    SlotDefinition(
        key="meal_preferences",
        prompt_label="Dietary and Meal Preferences",
        valid_types=(str,),
        normalization_rules=normalize_meal_preferences,
        sensitive_flag=False,
        source_authority=SourceAuthority.PATIENT_REPORTED,
        category="nutrition",
        description="Core diet style (Vegetarian, Non-Vegetarian, Eggetarian, Jain, Satvik, Vegan).",
    ),
    SlotDefinition(
        key="dietary_restrictions",
        prompt_label="Dietary Restrictions & Allergies",
        valid_types=(list, tuple, set),
        normalization_rules=normalize_dietary_restrictions,
        sensitive_flag=True,
        source_authority=SourceAuthority.PATIENT_REPORTED,
        category="nutrition",
        description="Specific ingredient allergies, sodium limits, or religious restrictions.",
    ),
    SlotDefinition(
        key="physical_activity_clearance",
        prompt_label="PEP Clinician Physical Activity Clearance",
        valid_types=(dict, bool),
        normalization_rules=normalize_physical_activity_clearance,
        sensitive_flag=True,
        source_authority=SourceAuthority.PEP_DOCTOR,
        category="clinical_pep",
        description="PEP-controlled clinician clearance for exercise, gym, and exertion.",
    ),
    SlotDefinition(
        key="daily_steps_target",
        prompt_label="Daily Step Count Target",
        valid_types=(int,),
        normalization_rules=normalize_steps_target,
        sensitive_flag=False,
        source_authority=SourceAuthority.PATIENT_REPORTED,
        category="activity",
        description="Daily walking step count goal.",
    ),
    SlotDefinition(
        key="tea_coffee_frequency",
        prompt_label="Tea and Coffee Consumption Frequency",
        valid_types=(dict, str, int),
        normalization_rules=normalize_tea_coffee_frequency,
        sensitive_flag=False,
        source_authority=SourceAuthority.PATIENT_REPORTED,
        category="lifestyle",
        description="Daily intake count of caffeinated beverages (tea/coffee).",
    ),
    SlotDefinition(
        key="work_schedule",
        prompt_label="Work Shift Schedule",
        valid_types=(str,),
        normalization_rules=lambda val, lang="hinglish": str(val).strip(),
        sensitive_flag=False,
        source_authority=SourceAuthority.PATIENT_REPORTED,
        category="circadian",
        description="Daily work shift schedule (day_shift, night_shift, rotational, etc.).",
    ),
]


class SlotRegistry:
    """Registry managing canonical slots, trilingual extraction, and clinical boundary checks."""

    def __init__(self, slots: list[SlotDefinition] | None = None) -> None:
        self._slots: dict[str, SlotDefinition] = {}
        for s in (slots or CANONICAL_SLOTS):
            self.register(s)

    def register(self, slot: SlotDefinition) -> None:
        """Register a slot definition."""
        self._slots[slot.key] = slot

    def get(self, key: str) -> SlotDefinition | None:
        """Retrieve a slot definition by key."""
        return self._slots.get(key)

    def list_all(self) -> list[SlotDefinition]:
        """List all registered slot definitions."""
        return list(self._slots.values())

    def normalize(self, key: str, raw_value: Any, lang: str = "hinglish") -> Any:
        """Normalize a slot value using its registered normalization rules."""
        slot = self._slots.get(key)
        if not slot:
            return raw_value
        return slot.normalization_rules(raw_value, lang)

    def validate_authority(self, key: str, claimed_authority: SourceAuthority | str) -> tuple[bool, str]:
        """Validate if the claiming authority has permission to write this slot.

        Invariant: LLM and patient self-report CANNOT modify PEP_DOCTOR slots.
        """
        slot = self._slots.get(key)
        if not slot:
            return False, f"Unknown slot '{key}'"

        authority_str = str(getattr(claimed_authority, "value", claimed_authority))
        slot_auth_str = str(slot.source_authority.value)

        if slot.source_authority == SourceAuthority.PEP_DOCTOR:
            if authority_str != SourceAuthority.PEP_DOCTOR.value:
                return False, (
                    f"Permission Denied: Slot '{key}' is governed by {slot_auth_str}. "
                    f"Claimed authority '{authority_str}' cannot grant or modify clinical permissions."
                )

        return True, "Authorized"

    def check_pep_contradiction(
        self,
        slot_key: str,
        reported_value: Any,
        pep_data: dict[str, Any] | None,
    ) -> ContradictionResult:
        """Check if a patient's self-reported claim contradicts official PEP restrictions.

        If a contradiction is detected, it is flagged for clinician review and NEVER silently applied.
        """
        if not pep_data:
            return ContradictionResult(is_contradiction=False, slot_key=slot_key, reported_value=reported_value)

        # 1. Contradiction check for gym and heavy lifting clearance
        if slot_key == "physical_activity_clearance":
            gym_clearance = bool(pep_data.get("gym_clearance", False))
            restricted = [str(r).casefold() for r in (pep_data.get("restricted_modalities") or ())]

            # Check if patient claims gym clearance or restricted exercises
            val_str = str(reported_value).lower()
            claims_gym = "gym" in val_str or "weight" in val_str or "lifting" in val_str or "deadlift" in val_str

            if not gym_clearance and claims_gym:
                return ContradictionResult(
                    is_contradiction=True,
                    slot_key=slot_key,
                    reported_value=reported_value,
                    pep_restriction="gym_clearance = False",
                    reason="Patient self-reported gym/heavy lifting clearance, but official PEP clearance is False.",
                    flagged_for_review=True,
                )

            for restr in restricted:
                if restr in val_str:
                    return ContradictionResult(
                        is_contradiction=True,
                        slot_key=slot_key,
                        reported_value=reported_value,
                        pep_restriction=f"restricted_modality: {restr}",
                        reason=f"Patient claimed permission for '{restr}', which is restricted by doctor PEP.",
                        flagged_for_review=True,
                    )

        # 2. Contradiction check for dietary preferences / sodium in hypertension
        if slot_key == "dietary_restrictions":
            htn_stage = str(pep_data.get("hypertension_stage", "")).casefold()
            val_str = str(reported_value).lower()
            if ("stage 2" in htn_stage or "crisis" in htn_stage) and any(w in val_str for w in ("high salt", "extra salt", "namkeen")):
                return ContradictionResult(
                    is_contradiction=True,
                    slot_key=slot_key,
                    reported_value=reported_value,
                    pep_restriction=f"hypertension_stage: {htn_stage}",
                    reason="Patient reports high sodium diet, contradicting clinical hypertension stage 2 protocol.",
                    flagged_for_review=True,
                )

        return ContradictionResult(is_contradiction=False, slot_key=slot_key, reported_value=reported_value)

    def extract_slots_from_text(self, text: str, lang: str = "hinglish") -> dict[str, Any]:
        """Extract habits and preferences from patient speech across English, Hindi, and Hinglish."""
        if not text:
            return {}

        extracted: dict[str, Any] = {}
        s = _clean_text(text).lower()

        # 1. Wake time
        wake_patterns = [
            r"(?:wake\s*up|waking\s*up|uthta|uthti|uthte|उठता|उठती|उठते|wake\s*time)\s*(?:at|pe|around|ko|बजे)?\s*([0-9०-९a-zA-Z:\s]+?(?:am|बजे|subah|morning|सुबह))",
            r"(?:सुबह|subah|subha)\s*([0-9०-९:\s]+?(?:am|बजे)?)\s*(?:उठता|uthta|wake)",
            r"([0-9०-९]{1,2}(?::[0-9०-९]{2})?\s*(?:am|pm)?)\s*(?:baje\s+uthta|बजे\s+उठना)",
        ]
        for pat in wake_patterns:
            m = re.search(pat, s)
            if m:
                extracted["wake_time"] = self.normalize("wake_time", m.group(1), lang)
                break

        # 2. Sleep time
        sleep_patterns = [
            r"(?:sleep|sleeping|sota|soti|sote|सोता|सोती|सोते|sleep\s*time)\s*(?:at|pe|around|ko|बजे)?\s*([0-9०-९a-zA-Z:\s]+?(?:pm|बजे|raat|night|रात))",
            r"(?:रात|raat)\s*([0-9०-९:\s]+?(?:pm|बजे)?)\s*(?:सोता|sota|sleep)",
            r"([0-9०-९]{1,2}(?::[0-9०-९]{2})?\s*(?:am|pm)?)\s*(?:baje\s+sota|बजे\s+सोना)",
        ]
        for pat in sleep_patterns:
            m = re.search(pat, s)
            if m:
                extracted["sleep_time"] = self.normalize("sleep_time", m.group(1), lang)
                break

        # 3. Water intake target
        water_patterns = [
            r"([0-9०-९\.]+|ek|do|teen|chaar|paanch|aadha|dedh|dhai|एक|दो|तीन|चार|पांच|आधा|डेढ़|ढाई)\s*(?:liters?|litres?|लीटर|l|glasses?|गिलास)\s*(?:of\s+)?(?:water|pani|paani|पानी)?",
            r"(?:पानी|pani|paani|water)\s*(?:roz|daily)?\s*([0-9०-९\.]+|ek|do|teen|chaar|paanch)\s*(?:liters?|litres?|लीटर|glasses?|गिलास)",
        ]
        for pat in water_patterns:
            m = re.search(pat, s)
            if m:
                extracted["water_intake_target"] = self.normalize("water_intake_target", m.group(0), lang)
                break

        # 4. Meal preferences
        if any(w in s for w in ("vegetarian", "shakahari", "शाकाहारी", "pure veg", "veg hoon")):
            extracted["meal_preferences"] = "Vegetarian"
        elif any(w in s for w in ("non-veg", "non veg", "mansahari", "मांसाहारी", "meat khata", "chicken khata")):
            extracted["meal_preferences"] = "Non-Vegetarian"
        elif any(w in s for w in ("eggetarian", "anda khata", "अंडा")):
            extracted["meal_preferences"] = "Eggetarian"
        elif any(w in s for w in ("jain", "जैन", "no onion garlic")):
            extracted["meal_preferences"] = "Jain"
        elif any(w in s for w in ("satvik", "सात्विक")):
            extracted["meal_preferences"] = "Satvik"
        elif any(w in s for w in ("vegan", "वीगन")):
            extracted["meal_preferences"] = "Vegan"

        # 5. Dietary restrictions
        restr_found: list[str] = []
        if any(w in s for w in ("bina pyaaz", "no onion", "bina lahsun", "no garlic", "बिना प्याज", "बिना लहसुन")):
            restr_found.append("no_onion_garlic")
        if any(w in s for w in ("kam namak", "low salt", "namak kam", "low sodium", "कम नमक")):
            restr_found.append("low_sodium")
        if any(w in s for w in ("cheeni band", "sugar free", "no sugar", "चीनी बंद", "शुगर फ्री")):
            restr_found.append("sugar_free")
        if any(w in s for w in ("gluten free", "gluten", "ग्लूटेन फ्री")):
            restr_found.append("gluten_free")
        if any(w in s for w in ("lactose", "doodh hazam nahi", "दूध से एलर्जी")):
            restr_found.append("lactose_intolerant")
        if restr_found:
            extracted["dietary_restrictions"] = restr_found

        # 6. Daily steps target
        steps_patterns = [
            r"([0-9०-९,]+|das\s+hazar|दस\s+हजार|[0-9]+k)\s*(?:steps|kadam|कदम)",
        ]
        for pat in steps_patterns:
            m = re.search(pat, s)
            if m:
                extracted["daily_steps_target"] = self.normalize("daily_steps_target", m.group(1), lang)
                break

        # 7. Tea/Coffee frequency
        tea_patterns = [
            r"([0-9०-९]+|ek|do|teen|chaar|एक|दो|तीन|चार)\s*(?:cups?|बार|baar)?\s*(?:of\s+)?(?:chai|tea|coffee|चाय|कॉफ़ी|कॉफी)",
            r"(?:chai|tea|coffee|चाय|कॉफ़ी)\s*(?:din\s+mein\s+)?([0-9०-९]+|ek|do|teen|chaar|एक|दो|तीन|चार)\s*(?:cup|baar|बार)",
        ]
        for pat in tea_patterns:
            m = re.search(pat, s)
            if m:
                extracted["tea_coffee_frequency"] = self.normalize("tea_coffee_frequency", m.group(0), lang)
                break

        # 8. Physical activity clearance claims (Detected to evaluate contradictions)
        if any(w in s for w in (
            "doctor said gym", "doctor cleared", "doctor ne bola gym", "doctor ne bola heavy",
            "gym ki permission", "cardiologist said", "physician cleared", "doctor cleared me",
        )):
            # Note: extracted as a candidate claim, NOT directly applied to PEP!
            extracted["patient_claimed_clearance"] = s

        return extracted


# Global Singleton Instance
DEFAULT_SLOT_REGISTRY = SlotRegistry()
