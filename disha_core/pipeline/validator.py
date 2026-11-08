from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from disha_core.engine.anti_echo import (
    is_clinical_safety_statement,
    is_pure_echo_or_filler,
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
    r"\b(?:aapko\s+(?:(?:type\s*[12]\s+)?diabetes|hypertension|sugar|bp|heart\s+disease|cancer)\s+(?:hai|ho\s+gaya|lag\s+raha\s+hai)|"
    r"you\s+have\s+(?:(?:type\s*[12]\s+)?diabetes|hypertension|heart\s+disease|cancer)|"
    r"(?:i|we)\s+diagnose\s+you|diagnosed\s+with|mera\s+diagnosis)\b|"
    r"आपको\s+(?:डायबिटीज|मधुमेह|उच्च\s*रक्तचाप|बीमारी)\s+है", re.I,
)
PRESCRIPTION_RE = re.compile(
    r"\b(?:(?:dose|dosing|khurak)\s*(?:double|badha|kam|increase|decrease|change|badal)|"
    r"(?:\d+\s*mg\s+(?:of\s+)?(?:metformin|amlodipine|atorvastatin|aspirin|insulin|atenolol|losartan|telmisartan|xanax|alprazolam|diazepam|clonazepam|tramadol)|"
    r"(?:metformin|amlodipine|atorvastatin|aspirin|insulin|atenolol|losartan|telmisartan|xanax|alprazolam|diazepam|clonazepam|tramadol).{0,35}?\b(?:dose|double|\d+\s*mg|mg|lijiye|badal|start|stop|increase|decrease|prescribe))|"
    r"(?:i\s+)?prescribe\s+(?:you\s+)?(?:xanax|alprazolam|diazepam|clonazepam|tramadol|medication|medicine|tablets?)|"
    r"(?:dawai?|goli|medicine|dawa)\s*(?:badal|change|band|stop|double|badha|prescribe)|"
    r"(?:stop|change|alter|increase|decrease)\s+(?:your\s+)?(?:medication|dose|prescription|tablets?))\b|"
    r"दवा\s*(?:बंद|बदल|डबल)", re.I,
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
