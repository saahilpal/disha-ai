from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from disha_core.engine.anti_echo import (
    strip_echo_prefix,
)

CHANNEL_RE = re.compile(r"\b(?:whatsapp|sms|email|telegram)\b|व्हाट्स?ऐप|व्हाट्स?एप", re.I)
AMOUNT = r"\d[\d,]*(?:\.\d+)?"
AMOUNT_END = r"(?![\d,]|\.\d)"
CURRENCY = r"(?:₹|[$€£¥₩₽]|rs\.?|rupees?|inr|usd|eur|gbp|jpy|cny|rmb|cad|aud|nzd|sgd|hkd|chf|krw|rub|aed|sar)"
INR_CURRENCIES = frozenset({"₹", "rs", "rs.", "rupee", "rupees", "inr"})
PRICE_RE = re.compile(
    rf"(?:(?P<currency_before>{CURRENCY})\s*(?P<amount_before>{AMOUNT}){AMOUNT_END}|"
    rf"(?P<amount_after>{AMOUNT}){AMOUNT_END}\s*(?P<currency_after>{CURRENCY})(?![A-Za-z]))", re.I,
)
PRICE_CONTEXT_RE = re.compile(
    rf"(?:price|cost|subscription|paid\s+plan|subscription\s+plan|pricing\s+plan|nutritionist\s+plan|plan\s+(?:ki\s+)?(?:fees?|price|cost|charges?)|kitne\s+ka|kitni\s+hai|charge|fee).{{0,45}}?\b({AMOUNT}){AMOUNT_END}", re.I,
)
FOREIGN_LANG_RE = re.compile(
    r"\b(?:obrigad[oa]|gracias|de\s+nada|por\s+favor)\b|[\uac00-\ud7af]", re.I
)
ROBOTIC_GREETING_PREFIX_RE = re.compile(
    r"^(?:namaste!?(?:\s+main\s+disha\s+hoon[^\.\!\?]*)?[\.\!\?]?\s*|"
    r"aapka\s+swagat\s+hai[^\.\!\?]*[\.\!\?]?\s*|"
    r"(?:theek\s+hai|thank\s+you)[,\.]?\s*)",
    re.I,
)
MONTHLY_RE = re.compile(r"\b(?:per\s+month|monthly|a\s+month|per\s+mahina|mahine\s+ka)\b|/\s*month", re.I)
IDENTITY_RE = re.compile(
    r"\b(?:main\s+(?:(?:ek|a|aapka|apka)\s+)?(?:doctor|nurse|physician|clinician)\s+(?:hoon|hun)|"
    r"i\s+am\s+(?:(?:a|your)\s+)?(?:doctor|nurse|physician|clinician)|"
    r"as\s+(?:a|your)\s+(?:doctor|physician|clinician)|"
    r"i['’]m\s+(?:(?:a|your)\s+)?(?:doctor|nurse|physician|clinician)|"
    r"maine\s+(?:aapko\s+)?prescribe\s+kiya|main\s+(?:aapko\s+)?prescribe\s+kar(?:ta|ti|unga|ungi)|"
    r"main\s+(?:a\s+)?(?:human|insaan)\s+(?:hoon|hun)|"
    r"i\s+am\s+(?:a\s+)?(?:human|person)|i['’]m\s+(?:a\s+)?(?:human|person))\b|"
    r"मैं\s+(?:एक\s+|आपका\s+)?(?:डॉक्टर|चिकित्सक|इंसान|मनुष्य)\s+हूँ", re.I,
)
DIAGNOSIS_RE = re.compile(
    r"\b(?:aapko\s+(?:(?:stage\s*[12]\s+)?hypertension|(?:type\s*[12]\s+)?diabetes|sugar|bp|heart\s+disease|cancer)\s+(?:hai|ho\s+gaya|lag\s+raha\s+hai)|"
    r"you\s+have\s+(?:(?:stage\s*[12]\s+)?hypertension|(?:type\s*[12]\s+)?diabetes|heart\s+disease|cancer)|"
    r"(?:i|we)\s+diagnose\s+you|diagnosed\s+with|mera\s+diagnosis)\b|"
    r"आपको\s+(?:डायबिटीज|मधुमेह|उच्च\s*रक्तचाप|बीमारी)\s+है", re.I,
)
DRUG_NAMES = r"(?:metformin|amlodipine|atorvastatin|aspirin|insulin|atenolol|losartan|telmisartan|xanax|alprazolam|diazepam|clonazepam|tramadol)"

PRESCRIPTION_RE = re.compile(
    rf"\b(?:(?:dose|dosing|khurak)\s*(?:double|badha|kam|increase|decrease|change|badal)|"
    rf"(?:\d+\s*mg\s+(?:of\s+)?{DRUG_NAMES})|"
    rf"(?:{DRUG_NAMES}.{{0,35}}?\b(?:dose|double|\d+\s*mg|mg|lijiye|badal|start|stop|increase|decrease|prescribe))|"
    rf"(?:(?:stop|change|alter|increase|decrease|start|prescribe|take|discontinue)\s+(?:your\s+)?(?:{DRUG_NAMES}|medication|medicine|dose|prescription|tablets?|pills?))|"
    rf"(?:i\s+)?prescribe\s+(?:you\s+)?(?:{DRUG_NAMES}|medication|medicine|tablets?)|"
    rf"(?:dawai?|goli|medicine|dawa)\s*(?:badal|change|band|stop|double|badha|prescribe)|"
    rf"(?:band\s+kar\s+(?:do|dein|dijiye)\s+(?:apni\s+)?(?:dawai|dawa|goli|medicine|{DRUG_NAMES}))|"
    rf"(?:{DRUG_NAMES}\s+(?:band|stop|change)))\b|"
    rf"दवा\s*(?:बंद|बदल|डबल)",
    re.I,
)
SODIUM_RE = re.compile(
    r"\b(?:papad|achaa?r|pickles?|namkeen|extra\s+salt|zyada\s+namak|chips|sev|high\s+sodium)\b|"
    r"पापड़|अचार|नमकीन", re.I,
)
RECIPE_RE = re.compile(
    r"\b(?:recipe|ingredients|cook|prepare|make|banao|banaye|khaane\s+mein|meal\s+suggestion)\b|"
    r"\b(?:breakfast|lunch|dinner)\s+(?:mein|for)\b|\b(?:breakfast|lunch|dinner)\s*[:=-]", re.I,
)
ACTIVITY_PATTERNS = {
    "brisk_walking": re.compile(r"\b(?:brisk\s+walking|brisk\s+walk|walking)\b", re.I),
    "yoga": re.compile(r"\byoga\b", re.I),
    "light_strength": re.compile(r"\b(?:light\s+(?:strength|weights?)|bodyweight)\b|(?<!heavy\s)(?<!power\s)\b(?:weight\s+lifting|weight\s+training)\b", re.I),
    "heavy_weightlifting": re.compile(r"\b(?:heavy\s+(?:weight\s*lifting|weights?|lifting)|power\s*lifting)\b", re.I),
    "heavy_deadlifts": re.compile(r"\b(?:heavy\s+)?deadlifts?\b", re.I),
    "high_intensity_sprints": re.compile(r"\b(?:high\s+intensity|sprints?|sprinting)\b", re.I),
    "hiit": re.compile(r"\b(?:hiit|high\s*intensity\s*(?:interval\s+training|training|workout|exercise)?)\b", re.I),
    "valsalva_maneuver": re.compile(r"\bvalsalva\b", re.I),
    "running": re.compile(r"\b(?:running|run|jogging|jog)\b", re.I),
    "cycling": re.compile(r"\b(?:cycling|cycle|bicycling)\b", re.I),
    "swimming": re.compile(r"\b(?:swimming|swim)\b", re.I),
    "gym": re.compile(r"\bgym\b", re.I),
}
PRESCRIPTIVE_WORKOUT_RE = re.compile(
    r"\b(?:(?:aaj|daily|roj|kripya|please)\s+(?:workout|exercise|training)|"
    r"(?:karein|kijiye|start|shuru|badhaiye)\s+(?:workout|exercise|training)|"
    r"(?:workout|exercise|training)\s+(?:karein|kijiye|start|shuru|badhaiye))\b",
    re.I,
)
NEGATED_OR_TIMING_RE = re.compile(
    r"\b(?:mat\s+(?:karein|kijiye)|na\s+karein|theek\s+nahi|avoid|mana|turant\s+nahi|"
    r"se\s+pehle|ke\s+baad|timing|samay|digestion)\b",
    re.I,
)
MARKDOWN_RE = re.compile(r"[*_#~`\[\]{}<>]|\u200b")

CHANNEL_REPLACEMENT = "Aap apna plan sirf app ke 'My Plan' tab mein dekh sakte hain."
IDENTITY_REPLACEMENT = "Main Disha hoon, aapki AI health coach."
MEAL_NOT_FOUND_REPLACEMENT = "Is meal ka prescribed plan abhi available nahi hai; app ke My Plan tab mein check karein."
PRICING_REPLACEMENT = "Follow-up consultations ₹0 hain; dedicated nutritionist plan ₹1,499 per month hai."
PEP_REPLACEMENT = "Main aapke exercise permissions ke andar safe activity chunne mein madad kar sakti hoon."
REMEDY_UNAVAILABLE = "Is symptom ke liye verified advice mere paas available nahi hai; apne clinician se poochhein."
DIAGNOSIS_REPLACEMENT = "Main ek AI coach hoon aur koi medical diagnosis nahi de sakti; kripya diagnosis ke liye clinician se consult karein."
PRESCRIPTION_REPLACEMENT = "Main dawaiyon ki dose ya prescription badalne ke liye authorized nahi hoon; kripya apne prescribing clinician se salah lein."
HYPERTENSION_SODIUM_REPLACEMENT = "Hypertension mein high-sodium khana jaise papad, achaar, aur namkeen avoid karein; low-salt diet lein."

# Clinical Permission Guard: LLM-written clinical permissions = 0
LLM_CLINICAL_CLEARANCE_RE = re.compile(
    r"\b(?:i\s+(?:hereby\s+)?(?:clear|approve|authorize|grant)\s+(?:you\s+)?(?:for\s+|permission\s+for\s+)?(?:gym|heavy\s+(?:weights?|lifting)|deadlifts?|exercise|workouts?|exertion)|"
    r"you\s+(?:are|have\s+been)\s+(?:cleared|approved|authorized)\s+(?:for|to\s+go\s+to)\s+(?:the\s+)?gym|"
    r"i\s+(?:am\s+)?(?:clearing|approving)\s+you|"
    r"i\s+(?:can|will)\s+(?:clear|allow)\s+you\s+(?:for|to\s+do)\s+(?:gym|deadlifts|heavy)|"
    r"(?:i\s+(?:clear|cure)|your\s+(?:hypertension|high\s+bp|blood\s+pressure|diabetes|disease)\s+(?:is|has\s+been)(?:\s+\w+)?\s+(?:cleared|cured|healed|treated|theek))|"
    r"(?:high\s+blood\s+pressure|hypertension|bp)\s+(?:is\s+)?(?:cured|cleared)|"
    r"(?:main|maine)\s+(?:aapko\s+)?(?:gym|heavy\s+(?:exercise|workout|weights?)|deadlifts?)\s+(?:ki\s+)?(?:clearance|permission|manzoori)\s+(?:deta|deti|di\s+hai|de\s+raha|de\s+rahi)\s*(?:hoon|hain)?|"
    r"(?:main|maine)\s+(?:aapka\s+)?(?:hypertension|bp|sugar)\s+(?:theek|cure|clear)\s+kar\s+diya|"
    r"(?:main|maine)\s+aapki\s+(?:doctor\s+)?restrictions\s+(?:hata|remove)\s+(?:deta|deti|di\s+hai|di\s+hain|kar\s+raha|kar\s+rahi|kar\s+di)\s*(?:hoon|hain)?|"
    r"(?:doctor\s+)?restrictions\s+(?:hata\s+di|hata\s+diya|hat\s+gayi)\s*(?:hain|gayi\s+hain)?|"
    r"(?:ab\s+)?restrictions\s+ki\s+zaroorat\s+nahi|"
    r"aap\s+gym\s+ja\s+sakte\s+hain\s+(?:maine\s+clear\s+kar\s+diya|permission\s+hai)|"
    r"aapko\s+medical\s+clearance\s+mil\s+gayi\s+hai)\b|"
    r"मैं\s+(?:आपको\s+)?(?:जिम|व्यायाम)\s+की\s+(?:अनुमति|क्लीयरेंस)\s+देता\s+हूँ|"
    r"मैंने\s+आपकी\s+पाबंदियां\s+हटा\s+दी\s+हैं|"
    r"पाबंदियां\s+हटा\s+दी\s+गई\s+हैं",
    re.I,
)

LLM_CLINICAL_PERMISSION_REPLACEMENT = (
    "Main ek AI coach hoon aur medical clearance ya doctor restrictions badalne ke liye authorized nahi hoon; "
    "kripya clearance ke liye apne prescribing clinician se consult karein."
)


@dataclass(frozen=True)
class ValidationResult:
    text: str
    status: str
    reasons: tuple[str, ...]


def _amount(match: re.Match[str]) -> tuple[str, str | None]:
    amount = match.group("amount_before") or match.group("amount_after")
    currency = match.group("currency_before") or match.group("currency_after")
    return amount, currency


def _allowed_price(match: re.Match[str], text: str) -> bool:
    raw, currency = _amount(match)
    try:
        value = Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return False
    if not currency or currency.casefold() not in INR_CURRENCIES:
        return False
    if value == 0:
        return True
    return value == 1499 and bool(MONTHLY_RE.search(text))


def _strip_markdown(text: str) -> str:
    text = re.sub(r"(?m)^\s*[-+•]\s+", "", text)
    return MARKDOWN_RE.sub("", text)


REPETITION_RE = re.compile(r"((?:\b\w+\b[\s,]*){2,6}?)(?:\s*\1){2,}", re.I)
VEG_MEAT_RE = re.compile(r"\b(?:grilled\s+)?(?:chicken|mutton|fish|meat|poultry|seafood|prawns|beef|pork)\b", re.I)


class SentenceValidator:
    def validate_sentence(self, sentence: str, context: dict[str, Any] | None = None) -> ValidationResult:
        context = context or {}
        text = sentence.strip()
        reasons: list[str] = []
        plain = _strip_markdown(text)
        if plain != text:
            text = plain
            reasons.append("markdown")

        squashed = REPETITION_RE.sub(r"\1", text)
        if squashed != text:
            text = squashed
            reasons.append("repetition_squashed")

        if FOREIGN_LANG_RE.search(text):
            text = FOREIGN_LANG_RE.sub("", text).strip()
            reasons.append("foreign_language")

        if context.get("has_history") and ROBOTIC_GREETING_PREFIX_RE.match(text):
            stripped = ROBOTIC_GREETING_PREFIX_RE.sub("", text).strip()
            if stripped:
                text = stripped
                reasons.append("robotic_greeting_suppressed")

        # Anti-Echo: strip parroting intro clauses from opening sentence
        user_input = context.get("user_input")
        if user_input:
            stripped_echo = strip_echo_prefix(text, user_input)
            if stripped_echo != text and stripped_echo:
                text = stripped_echo
                reasons.append("echo_stripped")

        diet_pref = str((context.get("pep") or context).get("dietary_preference", "")).casefold()
        if "veg" in diet_pref and "non" not in diet_pref and "egg" not in diet_pref:
            if VEG_MEAT_RE.search(text):
                text = VEG_MEAT_RE.sub("paneer ya tofu", text)
                reasons.append("vegetarian_guardrail")

        if CHANNEL_RE.search(text):
            text = CHANNEL_REPLACEMENT
            reasons.append("channel_boundary")
        if IDENTITY_RE.search(text):
            text = IDENTITY_REPLACEMENT
            reasons.append("identity")
        if DIAGNOSIS_RE.search(text):
            text = DIAGNOSIS_REPLACEMENT
            reasons.append("diagnosis_boundary")
        if PRESCRIPTION_RE.search(text):
            text = PRESCRIPTION_REPLACEMENT
            reasons.append("prescription_boundary")
        if LLM_CLINICAL_CLEARANCE_RE.search(text):
            text = LLM_CLINICAL_PERMISSION_REPLACEMENT
            reasons.append("llm_clinical_permission_grant_blocked")

        ctx = context or {}
        pep_ctx = ctx.get("pep") or ctx
        htn_stage = str(pep_ctx.get("hypertension_stage", "")).casefold()
        has_htn = htn_stage in {"stage 1", "stage 2"} or any("hypertension" in str(c).casefold() for c in ctx.get("conditions", ()))
        if has_htn and SODIUM_RE.search(text):
            text = HYPERTENSION_SODIUM_REPLACEMENT
            reasons.append("hypertension_sodium")

        if any(not _allowed_price(match, text) for match in PRICE_RE.finditer(text)):
            text = PRICING_REPLACEMENT
            reasons.append("price")
        else:
            contextual = PRICE_CONTEXT_RE.search(text)
            if contextual:
                try:
                    amount = Decimal(contextual.group(1).replace(",", ""))
                except InvalidOperation:
                    amount = Decimal(-1)
                quoted = any(
                    Decimal(_amount(match)[0].replace(",", "")) == amount
                    and _allowed_price(match, text)
                    for match in PRICE_RE.finditer(text)
                )
                if amount != 0 and not quoted:
                    text = PRICING_REPLACEMENT
                    reasons.append("price")

        raw_intent = context.get("intent", "")
        intent = str(getattr(raw_intent, "value", raw_intent)).upper()
        if context.get("diet_status") == "NOT_FOUND" and (
            intent in {"MEAL_QUERY", "RECIPE"} or RECIPE_RE.search(text)
        ):
            text = MEAL_NOT_FOUND_REPLACEMENT
            reasons.append("meal_not_found")

        pep = context.get("pep") or context
        has_pep = (
            "allowed_modalities" in pep
            or "restricted_modalities" in pep
            or "gym_clearance" in pep
            or "diagnosed_conditions" in pep
            or "hypertension_stage" in pep
            or bool(context.get("pep"))
        )
        if has_pep:
            restricted = {str(item).replace("_", " ").casefold() for item in pep.get("restricted_modalities") or ()}
            allowed = {str(item).replace("_", " ").casefold() for item in pep.get("allowed_modalities") or ()}
            gym_clearance = bool(pep.get("gym_clearance", False))

            diag_conditions = {str(d).casefold() for d in pep.get("diagnosed_conditions") or ()}
            htn_stage = str(pep.get("hypertension_stage", "")).casefold()
            is_cardiac = any(any(c in d for c in ("cardiac", "heart", "cad", "angina", "coronary", "arrhythmia", "mi")) for d in diag_conditions)
            is_htn_severe = "stage 2" in htn_stage or "crisis" in htn_stage
            if is_cardiac or is_htn_severe:
                restricted.update({
                    "heavy weightlifting", "heavy deadlifts", "hiit", "high intensity sprints", "valsalva maneuver"
                })

            mentioned = {tag for tag, pattern in ACTIVITY_PATTERNS.items() if pattern.search(text)}
            blocked = any(tag.replace("_", " ") in restricted for tag in mentioned)
            for tag in mentioned:
                normalized_tag = tag.replace("_", " ")
                if normalized_tag in restricted:
                    continue
                if tag == "gym":
                    blocked |= not gym_clearance
                else:
                    blocked |= normalized_tag not in allowed
            if (
                PRESCRIPTIVE_WORKOUT_RE.search(text)
                and not NEGATED_OR_TIMING_RE.search(text)
                and not mentioned
                and bool(allowed or restricted or not gym_clearance)
            ):
                blocked = True
            if blocked:
                text = PEP_REPLACEMENT
                reasons.append("pep_restriction")

        return ValidationResult(text, "rewritten" if reasons else "accepted", tuple(reasons))

    def validate_turn(self, text: str, context: dict[str, Any] | None = None) -> ValidationResult:
        context = context or {}
        user_input = context.get("user_input")
        if user_input:
            text = strip_echo_prefix(text, user_input)

        result = self.validate_sentence(text, context)
        value, reasons = result.text, list(result.reasons)
        clinical_tags = context.get("clinical_tags") or ()
        if not clinical_tags:
            return result

        tokens = tuple(str(token).casefold().strip() for token in context.get("required_remedy_tokens", ()) if str(token).strip())
        approved_text = str(context.get("approved_remedy_text", "")).strip()
        if not context.get("protocol_approved") or not tokens:
            return ValidationResult(REMEDY_UNAVAILABLE, "rewritten", tuple(reasons + ["remedy_not_configured"]))
        if tokens and any(re.search(rf"(?<!\w){re.escape(token)}(?!\w)", value, re.I) for token in tokens):
            return result
        if approved_text:
            return ValidationResult(approved_text, "rewritten", tuple(reasons + ["remedy_assertion"]))
        return ValidationResult(REMEDY_UNAVAILABLE, "rewritten", tuple(reasons + ["remedy_not_configured"]))

    @staticmethod
    def sanitize_for_tts(text: str) -> str:
        text = _strip_markdown(text)
        text = "".join(
            char for char in text
            if unicodedata.category(char) not in {"So", "Sk"}
            and char not in {"\u200d", "\ufe0e", "\ufe0f", "\u20e3"}
        )
        text = re.sub(r"\s+([.,!?।])", r"\1", text)
        return re.sub(r"\s+", " ", text).strip()


def evaluate_patient_claims(
    user_utterance: str,
    pep_data: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Strict Clinical Boundary Guard: Evaluate patient claims against PEP restrictions.

    Invariant:
    - LLM-written clinical permissions = 0.
    - Patient can self-report habits, but CANNOT grant themselves medical clearance
      or modify doctor-set PEP restrictions.
    - Any contradictory claim is flagged for clinician review, NEVER silently overwritten.
    """
    from disha_core.models.slots import DEFAULT_SLOT_REGISTRY, SourceAuthority

    contradictions: list[dict[str, Any]] = []
    if not user_utterance or not pep_data:
        return contradictions

    extracted = DEFAULT_SLOT_REGISTRY.extract_slots_from_text(user_utterance)

    # 1. Check patient claim to grant themselves medical or gym clearance
    if "patient_claimed_clearance" in extracted or re.search(
        r"\b(?:(?:doctor|cardiologist|physician|clinician)\s+(?:said|told|cleared|allowed)|doctor\s+ne\s+bola|clearance\s+mil\s+gayi)\b",
        user_utterance,
        re.I,
    ):
        gym_clearance = bool(pep_data.get("gym_clearance", False))
        restricted = [str(r).casefold() for r in (pep_data.get("restricted_modalities") or ())]
        user_lower = user_utterance.lower()

        claims_gym_or_heavy = any(
            w in user_lower for w in ("gym", "heavy", "deadlift", "weightlifting", "lifting", "hiit")
        )
        if not gym_clearance and claims_gym_or_heavy:
            contradictions.append({
                "slot_key": "physical_activity_clearance",
                "claimed_value": user_utterance,
                "source_authority": "PATIENT_REPORTED",
                "required_authority": SourceAuthority.PEP_DOCTOR.value,
                "pep_restriction": "gym_clearance = False",
                "reason": "Patient claimed doctor clearance for gym/heavy exertion, but official PEP gym_clearance is False.",
                "flagged_for_review": True,
                "action": "FLAG_CLINICIAN_REVIEW_MAINTAIN_RESTRICTION",
            })

        for restr in restricted:
            if restr.replace("_", " ") in user_lower or restr in user_lower:
                contradictions.append({
                    "slot_key": "physical_activity_clearance",
                    "claimed_value": user_utterance,
                    "source_authority": "PATIENT_REPORTED",
                    "required_authority": SourceAuthority.PEP_DOCTOR.value,
                    "pep_restriction": f"restricted_modality: {restr}",
                    "reason": f"Patient claimed permission for '{restr}', which is restricted by doctor PEP.",
                    "flagged_for_review": True,
                    "action": "FLAG_CLINICIAN_REVIEW_MAINTAIN_RESTRICTION",
                })

    # 2. Check each extracted slot for PEP contradiction
    for slot_key, slot_val in extracted.items():
        if slot_key == "patient_claimed_clearance":
            continue
        res = DEFAULT_SLOT_REGISTRY.check_pep_contradiction(slot_key, slot_val, pep_data)
        if res.is_contradiction:
            contradictions.append({
                "slot_key": slot_key,
                "claimed_value": slot_val,
                "source_authority": "PATIENT_REPORTED",
                "required_authority": SourceAuthority.PEP_DOCTOR.value if slot_key == "physical_activity_clearance" else "CLINICIAN",
                "pep_restriction": res.pep_restriction,
                "reason": res.reason,
                "flagged_for_review": res.flagged_for_review,
                "action": "FLAG_CLINICIAN_REVIEW_MAINTAIN_RESTRICTION",
            })

    return contradictions
