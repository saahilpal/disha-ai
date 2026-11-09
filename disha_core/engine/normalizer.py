from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

ALIASES: dict[str, tuple[str, ...]] = {
    "GI_SYMPTOM_ACUTE": ("pet dard", "paet dard", "dast", "loose motions", "paet kharab", "पेट दर्द", "दस्त", "पेट खराब"),
    "GI_BLOATING": ("bloating", "gas", "pet phoolna", "paet phoolna", "pet fulna", "गैस", "अफारा", "पेट फूलना"),
    "GI_ACIDITY": ("acidity", "acid reflux", "heartburn", "khatti dakar", "seene me jalan", "sine me jalan", "chest burning", "amlapitta", "एसिडिटी", "खट्टी डकार", "सीने में जलन", "अम्लपित्त"),
    "KNEE_PAIN": ("knee pain", "knees hurt", "ghutno ka dard", "ghutne me dard", "knee stiffness", "sandhivata", "joint pain", "घुटनों का दर्द", "घुटने में दर्द", "जोड़ों का दर्द"),
    "COUGH_COLD": ("cough", "khansi", "cold", "sardi", "throat irritation", "gale me kharash", "kasa", "खांसी", "जुकाम", "सर्दी", "गले में खराश"),
    "FEVER": ("fever", "bukhar", "tap", "jwara", "बुखार", "ताप", "ज्वर"),
    "DIABETES": ("sugar", "diabetes", "blood sugar", "madhumeh", "prameha", "शुगर", "डायबिटीज", "मधुमेह"),
    "HYPERTENSION": ("bp", "blood pressure", "hypertension", "high bp", "high blood pressure", "बीपी", "हाई बीपी", "रक्तचाप", "ब्लड प्रेशर", "हाई ब्लड प्रेशर"),
    "INSOMNIA_SLEEP": ("insomnia", "neend nahi", "sleep issue", "poor sleep", "sleeplessness", "sleep hygiene", "neend", "नींद", "अनिद्रा"),
    "FRUIT_MODERATION": ("mango", "mangoes", "aam", "alphonso", "seasonal fruit", "seasonal fruits", "आम", "अल्फांसो"),
    "HYDRATION": ("hydration", "dehydration", "water intake", "paani kitna", "pani kitna", "पानी कितना", "जलयोजन"),
    "WEIGHT_MANAGEMENT": ("weight loss", "lose weight", "weight management", "weight gain", "वजन घटाना", "वज़न घटाना", "वजन कम"),
}

HINDI_CLINICAL_TRANSLITERATION: dict[str, str] = {
    "गैस": "gas bloating",
    "अफारा": "bloating gas",
    "पेट फूलना": "bloating pet phoolna",
    "पेट": "pet stomach",
    "दर्द": "dard pain",
    "दस्त": "dast loose motions",
    "पेट खराब": "paet kharab loose motions",
    "एसिडिटी": "acidity",
    "खट्टी डकार": "khatti dakar acid reflux",
    "खट्टी": "khatti",
    "डकार": "dakar acid reflux",
    "सीने में जलन": "seene me jalan heartburn acid reflux",
    "जलन": "jalan heartburn",
    "अम्लपित्त": "amlapitta acidity",
    "घुटनों का दर्द": "ghutno ka dard knee pain",
    "घुटने": "ghutne knee",
    "घुटनों": "ghutno knee",
    "जोड़ों का दर्द": "joint pain arthritis",
    "खांसी": "khansi cough",
    "जुकाम": "jukam cold",
    "सर्दी": "sardi cold",
    "गले में खराश": "throat irritation gale me kharash",
    "बुखार": "bukhar fever",
    "ताप": "tap fever",
    "ज्वर": "jwara fever",
    "शुगर": "sugar diabetes",
    "डायबिटीज": "diabetes",
    "मधुमेह": "madhumeh diabetes",
    "बीपी": "bp blood pressure hypertension",
    "हाई बीपी": "high bp blood pressure hypertension",
    "ब्लड प्रेशर": "blood pressure hypertension high bp",
    "हाई ब्लड प्रेशर": "high bp blood pressure hypertension",
    "रक्तचाप": "blood pressure hypertension",
    "नमक": "namak salt sodium",
    "फैटी लिवर": "fatty liver",
    "वॉक": "walk walking exercise brisk",
    "पीसीओडी": "pcos",
    "पुदीना चाय": "spearmint tea",
    "पुदीना": "spearmint mint",
    "बालों": "facial hair hirsutism",
    "खून की कमी": "anemia hemoglobin low iron",
    "खून": "blood hemoglobin",
    "एनीमिया": "anemia hemoglobin chai iron",
    "कोलेस्ट्रॉल": "cholesterol lipid",
    "तेल": "tel cooking oil",
    "मोटा अनाज": "millets ragi jowar bajra",
    "चावल": "rice glycemic",
    "यूरिक एसिड": "uric acid gout purine",
    "गठिया": "gout arthritis sandhivata",
    "थायराइड": "thyroid",
    "पत्तागोभी": "cabbage goitrogens",
    "फूलगोभी": "cauliflower goitrogens",
    "नारियल पानी": "coconut water potassium",
    "केला": "banana potassium",
    "नींद": "neend sleep insomnia",
    "अनिद्रा": "insomnia sleep",
    "आम": "aam mango fruit",
    "अल्फांसो": "alphonso mango",
    "अजवाइन": "ajwain",
    "जीरा": "jeera",
    "हल्दी": "haldi turmeric",
    "सौंफ": "saunf fennel",
    "अदरक": "adrak ginger",
    "मेथी": "methi fenugreek",
    "इसबगोल": "isabgol psyllium",
    "दलिया": "daliya porridge oats",
    "दूध": "milk doodh",
    "टहलना": "walk walking brisk walk",
    "कसरत": "exercise workout",
    "व्यायाम": "exercise",
    "घरेलू उपाय": "home remedy",
}

# Domain & complexity detection patterns
MEAL_QUERY_RE = re.compile(
    r"\b(?:dinner|breakfast|lunch|meal|meals|khaana|khana|recipe|recipes|diet|diet\s+chart|"
    r"snack|snacks|protein|carbs|calories|food|foods|eating|dish|subzi|sabzi|roti|rice|dal|"
    r"khaun|khaa\s+sakta|fruits?|seb|banana|apple|tea|coffee|chawal)\b|"
    r"नाश्ता|खाना|भोजन|डाइट|रेसिपी|फल|सब्जी",
    re.I,
)

PRESCRIBED_MEAL_QUERY_RE = re.compile(
    r"\b(?:prescribed|assigned|my\s+(?:diet\s+chart|meal\s+plan|food\s+plan|breakfast|lunch|dinner)|"
    r"(?:as\s+per|according\s+to)\s+my\s+(?:diet|meal)\s+plan|"
    r"what(?:'s|\s+is)\s+(?:on\s+my\s+plan|my\s+(?:breakfast|lunch|dinner))|my\s+prescription)\b|"
    r"\b(?:meri|mere)\s+(?:diet|khane|meal)\s+(?:ka\s+)?(?:chart|plan|schedule)\b|"
    r"\b(?:mere\s+liye|mujhe)\s+(?:kya\s+)?(?:prescribed|plan\s+kiya|diya\s+gaya)\b|"
    r"निर्धारित|मेरे\s+(?:डाइट|खाने)\s+(?:चार्ट|प्लान)",
    re.I,
)

EXERCISE_QUERY_RE = re.compile(
    r"\b(?:gym|workout|workouts|exercise|exercises|run|walk|running|walking|jogging|steps|weights|"
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

RECOMMENDATION_REQUEST_RE = re.compile(
    r"\b(?:what\s+should\s+i|what\s+can\s+i|how\s+(?:can|do)\s+i|"
    r"should\s+i|can\s+i\s+(?:do|start|try|perform|exercise|work\s*out)|"
    r"what\s+(?:exercise|workout|routine)\s+(?:should|would)\s+i|"
    r"what\s+(?:exercise|workout|routine)\s+is\s+(?:right|good)\s+for\s+me|"
    r"tips?\s+for|advice\s+(?:for|on)|suggest(?:ions?)?|"
    r"recommend(?:ations?)?|guide\s+me|give\s+me\s+(?:a\s+)?(?:plan|routine|advice)|"
    r"kya\s+(?:karu|karoon|karna\s+chahiye)|kaise\s+(?:karu|karoon|sudharu)|"
    r"salah\s+do|sujhav|mujhe\s+(?:plan|routine|advice)\s+do)\b|"
    r"क्या\s+करूँ|क्या\s+करूं|क्या\s+करना\s+चाहिए|कैसे\s+करूँ|कैसे\s+करूं|सलाह\s+दो|सुझाव",
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

UNSUPPORTED_LANGUAGE_REPLACEMENT = (
    "Main abhi sirf English, Hindi aur Hinglish samajh sakti hoon. "
    "Kripya mujhse in bhashao mein baat karein. "
    "(Currently, I only support English, Hindi, and Hinglish. Please ask your health question in one of these languages.)"
)

UNSUPPORTED_SCRIPTS_RE = re.compile(
    r"[\u0980-\u09FF"  # Bengali
    r"\u0A00-\u0A7F"  # Gurmukhi
    r"\u0A80-\u0AFF"  # Gujarati
    r"\u0B00-\u0B7F"  # Oriya
    r"\u0B80-\u0BFF"  # Tamil
    r"\u0C00-\u0C7F"  # Telugu
    r"\u0C80-\u0CFF"  # Kannada
    r"\u0D00-\u0D7F"  # Malayalam
    r"\u0600-\u06FF"  # Arabic / Persian / Urdu
    r"\u4E00-\u9FFF"  # CJK
    r"\u3040-\u30FF"  # Hiragana / Katakana
    r"\uAC00-\uD7AF"  # Hangul
    r"\u0E00-\u0E7F"  # Thai
    r"]"
)

FOREIGN_LATIN_LANG_RE = re.compile(
    r"\b(?:"
    r"bonjour|bonsoir|merci(?:\s+beaucoup)?|s'il\s+vous\s+pla[îi]t|sil\s+vous\s+plait|je\s+(?:dors|bois|mange|suis|peux|voudrais|veux)|d'eau|par\s+jour|régime|regime\s+alimentaire|"
    r"guten\s+(?:tag|morgen|abend)|ich\s+(?:wache|trinke|esse|brauche|schlafe|kann)|diätplan|diaetplan|gesundheit|bitte\s+(?:sehr)?|schmerzen|morgens|"
    r"buenos\s+d[íi]as|buenas\s+tardes|necesito\s+un\s+plan|como\s+est[áa]s|por\s+favor|"
    r"bom\s+dia|boa\s+tarde|obrigad[oa]\s+pela|saúde|preciso\s+de\s+um\s+plano"
    r")\b",
    re.I,
)


def is_unsupported_language(text: str) -> bool:
    """Detect if utterance is in a non-supported language (e.g. Tamil, Bengali, French, German)."""
    if not text or not isinstance(text, str):
        return False
    clean = text.strip()
    if not clean:
        return False
    if UNSUPPORTED_SCRIPTS_RE.search(clean):
        return True
    if FOREIGN_LATIN_LANG_RE.search(clean):
        return True
    return False



def is_meal_query(text: str) -> bool:
    """Check if the text explicitly inquires about meals, food, nutrition, or recipes."""
    return bool(MEAL_QUERY_RE.search(text))


def is_prescribed_meal_query(text: str) -> bool:
    """Return whether the user explicitly asks for their assigned meal plan."""
    return bool(PRESCRIBED_MEAL_QUERY_RE.search(text))


def is_recommendation_request(text: str) -> bool:
    """Return whether the user asks for advice that must be grounded in approved knowledge."""
    return bool(RECOMMENDATION_REQUEST_RE.search(text))


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
    def is_recommendation_request(self) -> bool:
        return is_recommendation_request(self.normalized)

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

    # If text contains Devanagari characters, augment normalized query with transliterated tokens for GIN full-text & trigram indexes
    if re.search(r"[\u0900-\u097F]", text):
        extra_terms: list[str] = []
        for hindi_word, latin_equiv in HINDI_CLINICAL_TRANSLITERATION.items():
            if hindi_word in text:
                extra_terms.extend(latin_equiv.split())
        if extra_terms:
            seen_tokens: set[str] = set()
            unique_extra = [t for t in extra_terms if not (t in seen_tokens or seen_tokens.add(t))]
            normalized = f"{normalized} {' '.join(unique_extra)}"
            if not tags:
                tags = tuple(tag for tag, pattern in _patterns() if pattern.search(normalized))

    return NormalizedText(text, normalized, tags)
