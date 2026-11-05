import re
import time
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel

# ---------------------------------------------------------
# 1. PRE-TURN EMERGENCY RED-FLAG CIRCUIT BREAKER (<0.05ms)
# ---------------------------------------------------------

EMERGENCY_PATTERNS = {
    "cardiovascular": [
        r"\b(?:chest\s+(?:(?:severe|sharp|heavy|tight)\s+)?(?:pain|pressure|tightness|discomfort)|heavy\s+chest|cardiac\s+arrest)\b",
        r"\b(?:seene|chhati|chest|dil)\s*(?:mein|me|pe|par)?\s*(?:(?:bahut|bohot|tez|sharp|severe|heavy|halka|bada|badi)\s*)*(?:dard|pain|dabav|pressure|bojh|tightness|discomfort|ghutan)\b",
        r"\b(?:left\s+arm|baaye\s*haath|left\s*hand)\s*(?:mein|me)?\s*(?:ja\s*raha|radiat|dard|pain|numb|sunn|fail\s*raha)\b",
        r"\b(?:left\s+arm\s+(?:pain|numb|heavy)|left\s+hand\s+(?:numb|pain)|baaye\s+haath\s+(?:mein|me)\s+dard)\b",
        r"\b(?:ulta\s+haath\s+sunn|baayan\s+baazu\s+bhari|haath\s+sunn\s+pad|dil\s+ka\s+daura)\b",
        r"\b(?:pain\s+radiating\s+to\s+(?:jaw|shoulder|neck|arm)|jabde\s+tak\s+dard)\b",
        r"\b(?:dil\s+(?:mein|me)\s+ghutan|chhati\s+(?:mein|me)\s+tez\s+jalan\s+aur\s+dard)\b",
    ],
    "respiratory": [
        r"\b(shortness\s+of\s+breath|difficulty\s+breathing|cannot\s+breathe|gasping|choking)\b",
        r"\b(saans\s+(?:phool|lene\s+(?:mein|me)\s+takleef|nahi\s+aa\s+rahi|ruk\s+rahi)|dam\s+ghut\s+raha)\b",
    ],
    "neurological": [
        r"\b(stroke|facial\s+droop|slurred\s+speech|sudden\s+weakness|paralysis)\b",
        r"\b(bolne\s+(?:mein|me)\s+(?:dikkat|ladkhadahat)|chehra\s+tedha|aadha\s+shareer\s+sunn|behosh|chakkar\s+aake\s+gir)\b",
    ],
    "psychiatric": [
        r"\b(suicide|suicidal|want\s+to\s+die|kill\s+myself|self\s+harm)\b",
        r"\b(marne\s+ka\s+mann|jaan\s+dena|khud\s+ko\s+chot)\b",
        r"\b(end\s+(?:my\s+)?life|end\s+it\s+all)\b",
    ],
}

EMERGENCY_TRIAGE_SCRIPTS = {
    "cardiovascular": (
        "Yeh symptoms serious ho sakte hain. Kripya turant exercise ya physical activity band karein, "
        "aaram se baith jayein aur bina deri kiye emergency services (112) ya najdeeki hospital ke emergency ward se contact karein. "
        "Kripya kisi callback ka intezar na karein aur turant emergency medical help lein."
    ),
    "respiratory": (
        "Saans lene mein takleef ek medical emergency ho sakti hai. Kripya seedhe baithiye, taazi hawa lein "
        "aur turant emergency helpline 112 par call karein ya paas ke hospital ke emergency ward jayein."
    ),
    "neurological": (
        "Yeh neurological emergency ke lakshan ho sakte hain. Kripya aaram karein, kisi ko paas bulayein "
        "aur turant emergency hospital jayein ya 112 par call karein."
    ),
    "psychiatric": (
        "Aapki jaan bahut keemti hai aur aap akele nahi hain. Kripya turant national mental health helpline "
        "KIRAN (1800-599-0019), Tele-MANAS (14416) ya emergency services (112) par baat karein."
    ),
    "general": (
        "Yeh symptoms serious ho sakte hain. Kripya turant kisi emergency doctor ya hospital se consult karein, "
        "ya emergency helpline 112 par call karein."
    ),
}

# ---------------------------------------------------------
# 2. EXTENDED SAFETY CIRCUIT BREAKERS (Pre-turn Invariants)
# ---------------------------------------------------------

# A. Prompt Injection & Jailbreak Attacks
PROMPT_INJECTION_PATTERN = re.compile(
    r"\b(ignore\s+(?:all\s+)?previous\s+instructions|system\s+prompt|reveal\s+(?:all\s+)?instructions|"
    r"you\s+are\s+now\s+dan|forget\s+(?:your\s+)?rules|developer\s+mode|override\s+system|"
    r"act\s+as\s+an\s+unfiltered|bypass\s+safety|tell\s+me\s+your\s+hidden\s+prompt)\b",
    re.IGNORECASE,
)

CANONICAL_PROMPT_INJECTION_DEFENSE = (
    "Main Disha hoon, aapki AI health coach. Main aapki health, nutrition, aur fitness routine "
    "par focused rehti hoon. Kripya batayein main aapki health journey mein kaise madad kar sakti hoon?"
)

# B. Unsupported Medication Changes (Stopping/Altering Prescriptions)
MEDICATION_ALTERATION_PATTERN = re.compile(
    r"\b(?:stop|skip|discontinue|taper|reduce|increase|double|change|replace)\s+(?:taking\s+)?(?:my\s+)?"
    r"(?:medicines?|medications?|tablets?|pills?|bp\s+meds?|metformin|insulin|thyronorm|statins?|antibiotics?|dosage)\b|"
    r"\b(?:dawa|dawani|tablet|goli|dose)\s+(?:band\s+kar|kam\s+kar|chhod\s+do|badha\s+do|lena\s+band)\b",
    re.IGNORECASE,
)

CANONICAL_MEDICATION_SAFETY = (
    "Please do not stop or change any prescribed medication without consulting your treating doctor directly. "
    "As an AI health coach, I support your diet, exercise, and lifestyle, but only your doctor can safely adjust your prescriptions."
)

# C. Pregnancy & Lactation Precautions
PREGNANCY_PATTERN = re.compile(
    r"\b(?:pregnant|pregnancy|expecting|garbhavastha|breastfeeding|lactating|doodh\s+pilati)\b.*"
    r"\b(?:fasting|diet|workout|exercise|medicine|herbs?|vrat|weight\s+loss)\b|"
    r"\b(?:fasting|heavy\s+workout|diet|weight\s+loss)\b.*\b(?:pregnant|pregnancy|expecting|garbhavastha)\b",
    re.IGNORECASE,
)

CANONICAL_PREGNANCY_PRECAUTION = (
    "During pregnancy and lactation, any nutritional changes or exercise routines require close guidance "
    "from your gynecologist or obstetrician. Please consult your doctor directly before making changes to your diet or workout."
)

class EmergencyResult(BaseModel):
    is_emergency: bool
    category: Optional[str] = None
    matched_phrases: List[str] = []
    triage_message: Optional[str] = None
    latency_ms: float
    is_pre_turn_intercept: bool = False
    intercept_reason: Optional[str] = None

class PreTurnEmergencyCircuitBreaker:
    """Sub-millisecond regex circuit breaker that halts or intercepts turns before calling the LLM."""
    def __init__(self):
        self._compiled: Dict[str, re.Pattern] = {
            cat: re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)
            for cat, patterns in EMERGENCY_PATTERNS.items()
        }

    def evaluate(self, text: str) -> EmergencyResult:
        start = time.perf_counter()
        clean = re.sub(r"<[^>]+>", " ", text or "").strip()

        # 1. Critical Red-Flag Emergencies
        for cat, pat in self._compiled.items():
            matches = [m.group(0) for m in pat.finditer(clean)]
            if matches:
                lat = (time.perf_counter() - start) * 1000.0
                return EmergencyResult(
                    is_emergency=True,
                    category=cat,
                    matched_phrases=matches,
                    triage_message=EMERGENCY_TRIAGE_SCRIPTS.get(cat, EMERGENCY_TRIAGE_SCRIPTS["general"]),
                    latency_ms=lat,
                )

        # 2. Prompt Injection Attacks
        inj_match = PROMPT_INJECTION_PATTERN.search(clean)
        if inj_match:
            lat = (time.perf_counter() - start) * 1000.0
            return EmergencyResult(
                is_emergency=False,
                is_pre_turn_intercept=True,
                intercept_reason="PROMPT_INJECTION_ATTACK",
                matched_phrases=[inj_match.group(0)],
                triage_message=CANONICAL_PROMPT_INJECTION_DEFENSE,
                latency_ms=lat,
            )

        # 3. Prescription Medication Alteration Attempt
        med_match = MEDICATION_ALTERATION_PATTERN.search(clean)
        if med_match:
            lat = (time.perf_counter() - start) * 1000.0
            return EmergencyResult(
                is_emergency=False,
                is_pre_turn_intercept=True,
                intercept_reason="MEDICATION_ALTERATION_ATTEMPT",
                matched_phrases=[med_match.group(0)],
                triage_message=CANONICAL_MEDICATION_SAFETY,
                latency_ms=lat,
            )

        # 4. Pregnancy / Lactation Precautions
        preg_match = PREGNANCY_PATTERN.search(clean)
        if preg_match:
            lat = (time.perf_counter() - start) * 1000.0
            return EmergencyResult(
                is_emergency=False,
                is_pre_turn_intercept=True,
                intercept_reason="PREGNANCY_PRECAUTION_TRIGGER",
                matched_phrases=[preg_match.group(0)],
                triage_message=CANONICAL_PREGNANCY_PRECAUTION,
                latency_ms=lat,
            )

        return EmergencyResult(
            is_emergency=False,
            latency_ms=(time.perf_counter() - start) * 1000.0,
        )

# ---------------------------------------------------------
# 3. POST-TURN OUTPUT SANITIZER
# ---------------------------------------------------------

FORBIDDEN_HUMAN = re.compile(
    r"\b(insaan|human\s+(?:doctor|person|being|hoon)?|real\s+(?:human|person|doctor)|asli\s+(?:doctor|insaan|ladki)|clinic\s+mein\s+baith|not\s+an\s+ai)\b",
    re.IGNORECASE,
)

FORBIDDEN_CHANNELS = re.compile(
    r"\b(whatsapp|wa|watsapp|wapp|telegram|email|mail|pdf\s+link|forward)\b",
    re.IGNORECASE,
)

PRICE_REGEX = re.compile(r"(?:₹|rs\.?|rupees?\s*)\s*(\d{2,6})", re.IGNORECASE)
ALLOWED_PRICES = {0, 1499}

CANONICAL_PERSONA = (
    "Main Disha hoon, aapki AI health coach. Main aapke doctor ke guidance mein "
    "aapki health journey track karne mein madad karti hoon."
)

CANONICAL_APP_CHANNEL = (
    "Aapka diet chart Disha mobile app ke 'My Plan' tab mein already available hai, "
    "aap wahan se directly dekh sakte hain."
)

CANONICAL_PRICING = (
    "Aapke doctor ke treatment plan ke sath Disha basic voice follow-up calls 100% free hain. "
    "Personal dietitian plans ₹1,499 prati mahina se start hote hain."
)

# Allergen Detection Maps
ALLERGEN_MAP = {
    "lactose": {
        "triggers": [r"\b(?:paneer|curd|milk|dahi|cheese|butter|whey|ghee)\b"],
        "replacement_note": " Since you have a dairy restriction, substitute paneer or curd with seasoned tofu or unsweetened almond/soy curd."
    },
    "dairy": {
        "triggers": [r"\b(?:paneer|curd|milk|dahi|cheese|butter|whey|ghee)\b"],
        "replacement_note": " Since you have a dairy restriction, substitute paneer or curd with seasoned tofu or unsweetened almond/soy curd."
    },
    "gluten": {
        "triggers": [r"\b(?:wheat|rotis?|chapati|bread|maida|semolina|sooji)\b"],
        "replacement_note": " Please choose gluten-free alternatives like jowar, bajra, or brown rice rotis to stay within your dietary plan."
    },
    "peanut": {
        "triggers": [r"\b(?:peanuts?|peanut\s+butter|groundnut|mungfali)\b"],
        "replacement_note": " Please replace peanuts with sunflower seeds or roasted pumpkin seeds to avoid allergen exposure."
    }
}

def is_persona_violation(text: str) -> bool:
    lower = text.lower()
    # If the text explicitly negates being human or asserts AI health coach, check if it also positively claims human
    if any(neg in lower for neg in ["human nahi", "insaan nahi", "doctor nahi", "not a human", "not a doctor", "ai health coach", "ai hoon"]):
        if not re.search(r"\b(main\s+(?:ek\s+)?(?:asli|real)?\s*(?:insaan|doctor)\s+hoon|i\s+am\s+(?:a\s+)?(?:real\s+)?(?:human|doctor))\b", lower):
            return False
    return bool(FORBIDDEN_HUMAN.search(text))

def is_channel_violation(text: str) -> bool:
    lower = text.lower()
    # If the text explicitly explains WhatsApp is NOT supported or redirects to in-app
    if any(neg in lower for neg in ["whatsapp par nahi", "whatsapp nahi", "not on whatsapp", "do not send on whatsapp", "cannot send on whatsapp", "bhejte nahi"]):
        return False
    return bool(FORBIDDEN_CHANNELS.search(text))

class PostTurnSanitizer:
    """Verifies and sanitizes LLM output against persona, channel, price, remedy, and patient dietary rules."""
    def sanitize(
        self,
        raw_text: str,
        required_remedy_tokens: Optional[List[str]] = None,
        patient_conditions: Optional[List[str]] = None,
        dietary_preference: Optional[str] = None,
    ) -> Tuple[str, bool, Optional[str]]:
        text = (raw_text or "").strip()
        if not text:
            return "", False, None

        # Clean any raw reference brackets or internal doc tags
        text = re.sub(r"\[(?:Approved Reference|Disha Protocol|SYSTEM_DATA|Clinical Protocol)[^\]]*\]", "", text).strip()

        # 1. Persona invariant (Failure #4)
        if is_persona_violation(text):
            return CANONICAL_PERSONA, True, "INTERCEPTED_PERSONA_VIOLATION"

        # 2. Channel boundary (Failure #3: WhatsApp)
        if is_channel_violation(text):
            return CANONICAL_APP_CHANNEL, True, "INTERCEPTED_CHANNEL_VIOLATION"

        # 3. Pricing accuracy (Failure #1)
        for p_str in PRICE_REGEX.findall(text):
            try:
                if int(p_str) not in ALLOWED_PRICES:
                    return CANONICAL_PRICING, True, "INTERCEPTED_PRICE_HALLUCINATION"
            except ValueError:
                pass

        # 4. Mandatory Clinical Remedy assertion (Failure #2: Bloating -> jeera & saunf)
        if required_remedy_tokens:
            lower = text.lower()
            missing = [t for t in required_remedy_tokens if t.lower() not in lower]
            if missing:
                remedy_line = " Aap din mein do baar gungune paani mein jeera aur saunf ubaal kar pijiye, isse pet ko kaafi aaram milega."
                text = text.rstrip(".") + "." + remedy_line
                return text, True, "ENFORCED_MANDATORY_REMEDY"

        # 5. Patient Allergies & Strict Dietary Restriction Cross-check
        conditions_list = [c.lower() for c in (patient_conditions or [])]
        diet_pref = (dietary_preference or "").lower()

        # Check allergen matches
        for allergen, data in ALLERGEN_MAP.items():
            if any(allergen in cond for cond in conditions_list):
                for trig in data["triggers"]:
                    if re.search(trig, text, re.IGNORECASE):
                        # Append allergen safety notice
                        text = text.rstrip(".") + "." + data["replacement_note"]
                        return text, True, f"ALLERGEN_GUARD_{allergen.upper()}"

        return text, False, None

# ---------------------------------------------------------
# 4. EGRESS PHI & CREDENTIAL FILTER
# ---------------------------------------------------------

EGRESS_FILTERS = [
    ("KEY", re.compile(r"(?:your_groq_api_key_here|sk-|ghp_)[A-Za-z0-9_\-]{20,}")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("ABHA_ID", re.compile(r"\b\d{2}-\d{4}-\d{4}-\d{4}\b")),
    ("AADHAAR", re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")),
    ("PAN", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b")),
    ("PHONE", re.compile(r"(?:(?:\+|0{0,2})91[\s-]?)?[6789]\d{9}")),
    ("CARD", re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")),
]

class EgressGate:
    """Scrubs sensitive credentials, tokens, cards, and patient PHI before logging or response dispatch."""
    @classmethod
    def scrub(cls, text: str) -> str:
        if not text:
            return ""
        out = text
        for token_name, pattern in EGRESS_FILTERS:
            out = pattern.sub(f"[REDACTED_{token_name}]", out)
        return out

# Global singletons
emergency_breaker = PreTurnEmergencyCircuitBreaker()
sanitizer = PostTurnSanitizer()
