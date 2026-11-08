from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

ALIASES: dict[str, tuple[str, ...]] = {
    "GI_SYMPTOM_ACUTE": ("pet dard", "paet dard", "dast", "loose motions", "paet kharab"),
    "GI_BLOATING": ("bloating", "gas", "pet phoolna", "paet phoolna", "pet fulna"),
    "GI_ACIDITY": ("acidity", "acid reflux", "heartburn", "khatti dakar", "seene me jalan", "sine me jalan", "chest burning", "amlapitta"),
    "KNEE_PAIN": ("knee pain", "knees hurt", "ghutno ka dard", "ghutne me dard", "knee stiffness", "sandhivata", "joint pain"),
    "COUGH_COLD": ("cough", "khansi", "cold", "sardi", "throat irritation", "gale me kharash", "kasa"),
    "FEVER": ("fever", "bukhar", "tap", "jwara"),
    "DIABETES": ("sugar", "diabetes", "blood sugar", "madhumeh", "prameha"),
    "HYPERTENSION": ("bp", "blood pressure", "hypertension", "high bp", "high blood pressure"),
    "INSOMNIA_SLEEP": ("insomnia", "neend nahi", "sleep issue", "poor sleep", "sleeplessness"),
    "FRUIT_MODERATION": ("mango", "mangoes", "aam", "alphonso", "seasonal fruit", "seasonal fruits"),
}

# Domain & complexity detection patterns
MEAL_QUERY_RE = re.compile(
    r"\b(?:dinner|breakfast|lunch|meal|meals|khaana|khana|recipe|recipes|diet|diet\s+chart|"
    r"snack|snacks|protein|carbs|calories|food|foods|eating|dish|subzi|sabzi|roti|rice|dal|"
    r"khaun|khaa\s+sakta|fruits?|seb|banana|apple|tea|coffee|chawal)\b|"
    r"नाश्ता|खाना|भोजन|डाइट|रेसिपी|फल|सब्जी",
    re.I,
)

EXERCISE_QUERY_RE = re.compile(
    r"\b(?:gym|workout|workouts|exercise|exercises|running|walking|jogging|weights|"
    r"strength|training|cardio|pushups|squats|yoga|stretching|activity|karein\s+exercise|"
    r"brisk\s+walk|walks|deadlifts|sprints)\b|"
    r"व्यायाम|कसरत|जिम|योगा|टहलना",
    re.I,
)

DETAIL_REQUEST_RE = re.compile(
    r"\b(?:detail(?:ed)?|details|vistar\s+se|bistar\s+se|step\s+by\s+step|in\s+detail|"
    r"explain\s+in\s+detail|gehrai\s+mein|samjhao|explain\s+properly|thoroughly|"
    r"deep\s+dive|complete\s+guide|pure\s+steps|vistar\s+mein)\b|"
    r"विस्तार\s+से|विस्तारपूर्वक|पूरा\s+समझाओ",
    re.I,
)

FACTUAL_LOOKUP_RE = re.compile(
    r"\b(?:fees?|price|cost|charges?|kitne\s+ka|kitni\s+fees|subscription|paid\s+plan|"
    r"who\s+are\s+you|aap\s+kaun\s+ho|kya\s+aap\s+doctor\s+ho|what\s+is\s+your\s+name|"
    r"app\s+mein\s+plan\s+kahan\s+hai|my\s+plan\s+kahan\s+hai|timing|hours|"
    r"kya\s+hai\s+yeh|what\s+is\s+(?:bmi|bp|blood\s+pressure|hba1c))\b|"
    r"फीस|दाम|कीमत|प्लान",
    re.I,
)

COMPLEX_HEALTH_RE = re.compile(
    r"\b(?:chest\s+pain|shortness\s+of\s+breath|breathing\s+difficulty|chronic|"
    r"high\s+bp\s+aur|diabetes\s+aur|fever\s+aur|vomiting\s+and|blood\s+in|"
    r"sugar\s+300|bp\s+180|dawai\s+ke\s+side\s+effects?|reaction|infection|"
    r"multiple\s+symptoms|severe\s+pain|chhati\s+mein\s+dard)\b",
    re.I,
)


def is_meal_query(text: str) -> bool:
    """Check if the text explicitly inquires about meals, food, nutrition, or recipes."""
    return bool(MEAL_QUERY_RE.search(text))


def is_exercise_query(text: str) -> bool:
    """Check if the text explicitly inquires about workouts, exercise, gym, or physical activities."""
    return bool(EXERCISE_QUERY_RE.search(text))


def is_detail_requested(text: str) -> bool:
    """Check if the user explicitly requested a detailed or in-depth explanation."""
    return bool(DETAIL_REQUEST_RE.search(text))


def is_simple_factual(text: str) -> bool:
    """Check if the text is a simple factual or lookup query (pricing, identity, quick definitions)."""
    if FACTUAL_LOOKUP_RE.search(text):
        return True
    # Queries of 1-4 words that do not report symptoms are often quick lookups
    words = text.strip().split()
    if len(words) <= 4 and not bool(re.search(r"\b(dard|pain|fever|vomit|gas|bloat)\b", text, re.I)):
        return True
    return False


def is_complex_health_query(text: str, tags: tuple[str, ...] = (), intent: str | None = None) -> bool:
    """Check if the query addresses complex, multi-symptom, or high-concern health topics."""
    if COMPLEX_HEALTH_RE.search(text):
        return True
    if len(tags) >= 2:
        return True
    return False


@dataclass(frozen=True)
class NormalizedText:
    original: str
    normalized: str
    tags: tuple[str, ...]

    @property
    def is_meal_query(self) -> bool:
        return is_meal_query(self.normalized)

    @property
    def is_exercise_query(self) -> bool:
        return is_exercise_query(self.normalized)

    @property
    def is_detail_requested(self) -> bool:
        return is_detail_requested(self.normalized)

    @property
    def is_simple_factual(self) -> bool:
        return is_simple_factual(self.normalized)

    @property
    def is_complex_health(self) -> bool:
        return is_complex_health_query(self.normalized, self.tags)


@lru_cache(maxsize=1)
def _patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    return tuple(
        (tag, re.compile(r"(?<!\w)(?:" + "|".join(re.escape(x) for x in aliases) + r")(?!\w)", re.I))
        for tag, aliases in ALIASES.items()
    )


def normalize(text: str) -> NormalizedText:
    normalized = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    tags = tuple(tag for tag, pattern in _patterns() if pattern.search(normalized))
    return NormalizedText(text, normalized, tags)
