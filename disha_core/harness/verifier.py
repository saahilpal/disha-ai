"""Deterministic Response Verification Engine.

Enforces 6 required verification checks:
1. Claims to be doctor/human (identity violation)
2. Unsupported capabilities (channel boundaries, external delivery)
3. Ungrounded numbers and facts (pricing, prescription alteration, diagnosis)
4. False memory claims (claims about prior conversations when ungrounded)
5. Question spam (more than 1 question per turn)
6. N-gram repetitions (repetition loops, echoing)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from disha_core.pipeline.validator import (
    ACTIVITY_PATTERNS,
    CHANNEL_RE,
    CHANNEL_REPLACEMENT,
    DIAGNOSIS_RE,
    DIAGNOSIS_REPLACEMENT,
    DIETARY_MISMATCH_REPLACEMENT,
    HYPERTENSION_SODIUM_REPLACEMENT,
    IDENTITY_RE,
    IDENTITY_REPLACEMENT,
    LLM_CLINICAL_CLEARANCE_RE,
    LLM_CLINICAL_PERMISSION_REPLACEMENT,
    PEP_REPLACEMENT,
    PRESCRIPTION_RE,
    PRESCRIPTION_REPLACEMENT,
    PRICE_CONTEXT_RE,
    PRICE_RE,
    REMEDY_UNAVAILABLE,
    SODIUM_RE,
    VEG_MEAT_RE,
    _allowed_price,
    _amount,
    false_memory_replacement,
    get_team_confirmation_replacement,
)


@dataclass(frozen=True)
class VerificationViolation:
    check_name: str
    description: str
    specific_feedback: str
    replacement_text: str | None = None


@dataclass(frozen=True)
class VerificationResult:
    is_valid: bool
    violations: tuple[VerificationViolation, ...]
    sanitized_text: str


# False memory regexes (referencing past turns when no history exists)
PAST_MEMORY_RE = re.compile(
    r"\b(?:as\s+you\s+(?:mentioned|said|told\s+me)\s+(?:yesterday|earlier|before)|"
    r"jaise\s+aapne\s+(?:pehle|kal|last\s+time)\s+(?:bataya|kaha)|"
    r"kal\s+(?:jo\s+)?aapne\s+bataya\s+tha|"
    r"aapne\s+pehle\s+kaha\s+tha)\b",
    re.I,
)

# N-gram repetition regex: consecutive duplicate phrases of 2-6 words
CONSECUTIVE_REPETITION_RE = re.compile(r"((?:\b\w+\b[\s,]*){2,6}?)(?:\s*\1){2,}", re.I)


def check_doctor_or_human_claim(text: str) -> VerificationViolation | None:
    """Check 1: Claims to be doctor, clinician, physician, nurse, or human."""
    if IDENTITY_RE.search(text):
        return VerificationViolation(
            check_name="claims_to_be_doctor_or_human",
            description="Response claims to be a doctor, clinician, or human",
            specific_feedback="Never claim to be a doctor, physician, clinician, or human. Identify only as an AI health coach.",
            replacement_text=IDENTITY_REPLACEMENT,
        )
    return None


def check_unsupported_capabilities(text: str) -> VerificationViolation | None:
    """Check 2: Promises external channels (WhatsApp, SMS, calls) or external delivery."""
    if CHANNEL_RE.search(text):
        return VerificationViolation(
            check_name="unsupported_capabilities",
            description="Response promises communication via external channels (WhatsApp/SMS/call)",
            specific_feedback="Do not promise communication via external channels like WhatsApp, SMS, or phone calls. Refer to the My Plan section in the app.",
            replacement_text=CHANNEL_REPLACEMENT,
        )
    return None


def check_ungrounded_numbers_and_facts(text: str, context: dict[str, Any]) -> list[VerificationViolation]:
    """Check 3: Ungrounded pricing, prescription dosages, or medical diagnoses."""
    violations: list[VerificationViolation] = []

    # 3a. Pricing verification
    pricing_replacement = get_team_confirmation_replacement(context)
    price_violated = False
    if any(not _allowed_price(match, text, context) for match in PRICE_RE.finditer(text)):
        price_violated = True
    else:
        contextual = PRICE_CONTEXT_RE.search(text)
        if contextual:
            try:
                amount = Decimal(contextual.group(1).replace(",", ""))
            except InvalidOperation:
                amount = Decimal(-1)
            quoted = any(
                Decimal(_amount(match)[0].replace(",", "")) == amount and _allowed_price(match, text, context)
                for match in PRICE_RE.finditer(text)
            )
            if not quoted:
                price_violated = True

    if price_violated:
        violations.append(
            VerificationViolation(
                check_name="ungrounded_pricing",
                description="Response states unverified or ungrounded price or fee",
                specific_feedback="Do not quote unverified prices or subscription fees. Inform the user that pricing details must be confirmed with the team.",
                replacement_text=pricing_replacement,
            )
        )

    # 3b. Prescription alteration
    if PRESCRIPTION_RE.search(text):
        violations.append(
            VerificationViolation(
                check_name="ungrounded_prescription",
                description="Response instructs altering or stopping medication dosages",
                specific_feedback="Never prescribe medication dosages, start/stop medicines, or change doses. Advise the user to consult their prescribing doctor.",
                replacement_text=PRESCRIPTION_REPLACEMENT,
            )
        )

    # 3c. Diagnosis assertion
    if DIAGNOSIS_RE.search(text):
        violations.append(
            VerificationViolation(
                check_name="ungrounded_diagnosis",
                description="Response makes clinical medical diagnosis",
                specific_feedback="Never diagnose medical conditions. Frame observations gently and recommend consulting a physician.",
                replacement_text=DIAGNOSIS_REPLACEMENT,
            )
        )

    # 3d. LLM Clinical Clearance grant
    if LLM_CLINICAL_CLEARANCE_RE.search(text):
        violations.append(
            VerificationViolation(
                check_name="llm_clinical_clearance",
                description="Response autonomously grants clinical clearance",
                specific_feedback="Never grant medical or clinical clearance. Only human physicians can clear patients.",
                replacement_text=LLM_CLINICAL_PERMISSION_REPLACEMENT,
            )
        )

    return violations


def check_false_memory_claims(text: str, context: dict[str, Any]) -> VerificationViolation | None:
    """Check 4: Claims about past conversations when no such history/memory exists."""
    has_history = context.get("has_history", False)
    history_turns = context.get("conversation_history") or []
    patient_slots = context.get("patient_slots") or {}
    pep = context.get("pep") or {}
    habits = pep.get("habits") or {}
    if isinstance(habits, str):
        try:
            habits = json.loads(habits)
        except Exception:
            habits = {}
    habits_slots = habits.get("slots") if isinstance(habits, dict) else {}
    has_memory = bool(has_history or history_turns or patient_slots or habits_slots)
    if not has_memory:
        if PAST_MEMORY_RE.search(text):
            lang = context.get("preferred_language") or pep.get("language")
            return VerificationViolation(
                check_name="false_memory_claims",
                description="Response references past conversations when no conversation history exists",
                specific_feedback="Do not claim to remember past conversations or statements that are not in the conversation history.",
                replacement_text=false_memory_replacement(lang),
            )
    return None


def check_question_spam(text: str) -> VerificationViolation | None:
    """Check 5: Question spam - strictly <= 1 question per turn."""
    # Count question marks
    q_marks = text.count("?")
    if q_marks > 1:
        return VerificationViolation(
            check_name="question_spam",
            description=f"Response contains {q_marks} questions, violating the <=1 question limit",
            specific_feedback="Ask at most one question in your response. Remove any additional questions.",
            replacement_text=None,
        )
    return None


def check_ngram_repetitions(text: str) -> VerificationViolation | None:
    """Check 6: N-gram repetition loops and echoing."""
    if CONSECUTIVE_REPETITION_RE.search(text):
        return VerificationViolation(
            check_name="ngram_repetitions",
            description="Response contains consecutive repeating word n-grams",
            specific_feedback="Eliminate repeating phrases and repetition loops. Speak crisply and variedly.",
            replacement_text=CONSECUTIVE_REPETITION_RE.sub(r"\1", text),
        )

    # Check for 3-gram repeating 3+ times non-consecutively
    words = re.findall(r"\b\w+\b", text.lower())
    if len(words) >= 9:
        trigrams: dict[tuple[str, ...], int] = {}
        for i in range(len(words) - 2):
            tri = (words[i], words[i + 1], words[i + 2])
            trigrams[tri] = trigrams.get(tri, 0) + 1
            if trigrams[tri] >= 3:
                return VerificationViolation(
                    check_name="ngram_repetitions",
                    description=f"Trigram {' '.join(tri)} repeated {trigrams[tri]} times",
                    specific_feedback="Avoid repeating the same phrase multiple times throughout your answer.",
                    replacement_text=None,
                )

    return None


def check_pep_and_clinical_bounds(text: str, context: dict[str, Any]) -> list[VerificationViolation]:
    """Check PEP physical activity restrictions, sodium in HTN, and ungrounded remedies."""
    violations: list[VerificationViolation] = []
    pep = context.get("pep") or context

    # PEP Exercise restrictions
    has_pep = (
        "allowed_modalities" in pep
        or "restricted_modalities" in pep
        or "diagnosed_conditions" in pep
        or "hypertension_stage" in pep
        or bool(context.get("pep"))
    )
    if has_pep:
        restricted = {str(item).replace("_", " ").casefold() for item in pep.get("restricted_modalities") or ()}
        allowed = {str(item).replace("_", " ").casefold() for item in pep.get("allowed_modalities") or ()}
        diag_conditions = {str(d).casefold() for d in pep.get("diagnosed_conditions") or ()}
        htn_stage = str(pep.get("hypertension_stage", "")).casefold()
        is_cardiac = any(
            any(c in d for c in ("cardiac", "heart", "cad", "angina", "coronary", "arrhythmia", "mi"))
            for d in diag_conditions
        )
        is_htn_severe = "stage 2" in htn_stage or "crisis" in htn_stage
        if is_cardiac or is_htn_severe:
            restricted.update(
                {"heavy weightlifting", "heavy deadlifts", "hiit", "high intensity sprints", "valsalva maneuver"}
            )

        mentioned = {tag for tag, pattern in ACTIVITY_PATTERNS.items() if pattern.search(text)}
        blocked = any(tag.replace("_", " ") in restricted for tag in mentioned)
        for tag in mentioned:
            normalized_tag = tag.replace("_", " ")
            if normalized_tag in restricted:
                continue
            if tag != "gym" and allowed:
                blocked |= normalized_tag not in allowed

        if blocked:
            violations.append(
                VerificationViolation(
                    check_name="pep_restriction",
                    description="Response recommends restricted or contraindicated physical activity",
                    specific_feedback="Do not recommend restricted high-intensity or contraindicated exercises. Suggest only safe, approved activities like walking.",
                    replacement_text=PEP_REPLACEMENT,
                )
            )

    # Vegetarian diet boundary
    diet_pref = str(pep.get("dietary_preference", "")).casefold()
    if "veg" in diet_pref and "non" not in diet_pref and "egg" not in diet_pref:
        if VEG_MEAT_RE.search(text):
            violations.append(
                VerificationViolation(
                    check_name="dietary_preference_mismatch",
                    description="Response suggests non-vegetarian food to a vegetarian patient",
                    specific_feedback="The patient is vegetarian. Do not suggest non-vegetarian food or meat.",
                    replacement_text=DIETARY_MISMATCH_REPLACEMENT,
                )
            )

    # Hypertension sodium
    htn_stage = str(pep.get("hypertension_stage", "")).casefold()
    has_htn = htn_stage in {"stage 1", "stage 2"} or any(
        "hypertension" in str(condition).casefold() for condition in context.get("conditions", ())
    )
    if has_htn and SODIUM_RE.search(text):
        violations.append(
            VerificationViolation(
                check_name="hypertension_sodium",
                description="Response suggests high-sodium items to a hypertension patient",
                specific_feedback="The patient has hypertension. Do not suggest high-sodium items like pickles or papad.",
                replacement_text=HYPERTENSION_SODIUM_REPLACEMENT,
            )
        )

    # Clinical remedy assertion check
    clinical_tags = {str(t).upper() for t in (context.get("clinical_tags") or ())}
    symptom_tags = {"GI_BLOATING", "GI_ACIDITY", "GI_SYMPTOM_ACUTE", "KNEE_PAIN", "FEVER", "COUGH_COLD"}
    has_symptom = bool(clinical_tags & symptom_tags)
    if has_symptom or context.get("protocol_approved"):
        tokens = tuple(
            str(token).casefold().strip() for token in context.get("required_remedy_tokens", ()) if str(token).strip()
        )
        approved_text = str(context.get("approved_remedy_text", "")).strip()
        if not context.get("protocol_approved") or not tokens:
            violations.append(
                VerificationViolation(
                    check_name="unapproved_remedy",
                    description="Home remedy suggested without approved clinical protocol",
                    specific_feedback="Do not suggest home remedies without approved clinical grounding.",
                    replacement_text=REMEDY_UNAVAILABLE,
                )
            )
        elif not all(re.search(rf"(?<!\w){re.escape(token)}(?!\w)", text, re.I) for token in tokens):
            violations.append(
                VerificationViolation(
                    check_name="remedy_assertion_missing_token",
                    description="Approved remedy missing required clinical token",
                    specific_feedback=f"Include verified remedy tokens ({', '.join(tokens)}) in advice.",
                    replacement_text=approved_text or REMEDY_UNAVAILABLE,
                )
            )

    return violations


# ---------------------------------------------------------------------------
# Behavior Spec v1 Deterministic Verifiers (P3, P4, P6/F3, F1, F2, F4, C2)
# ---------------------------------------------------------------------------

DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
ROMAN_HINDI_COMMON_RE = re.compile(
    r"\b(aap|aapka|aapko|hai|hain|kripya|karein|karo|nahi|nhi|mein|batao|theek|kaisa|kaise|kyun|kya|hoga)\b", re.I
)

BANNED_HONORIFICS_RE = re.compile(
    r"\b(ji\s+sir|ji\s+ma'?am|ji\s+madam|sir|ma'?am|madam|sahab|sahib|shrimaan|shreemati)\b|"
    r"(?:जी\s*सर|जी\s*मैम|सर|मैम|मैडम|साहब|साहिब|श्रीमान|श्रीमती)",
    re.I,
)

C2_MEDICATION_DOSE_RE = re.compile(r"\b\d+\s*(?:mg|ml|mcg|tablets?|capsules?|goli)\b", re.I)
C2_MED_NAMES_RE = re.compile(
    r"\b(metformin|paracetamol|ibuprofen|aspirin|omeprazole|atorvastatin|amlodipine|insulin)\b", re.I
)
C2_DIAGNOSIS_RE = re.compile(
    r"\b(?:you\s+have\s+(?:diabetes|hypertension|pcos|thyroid|asthma|depression|anxiety|gerd)|"
    r"aapko\s+(?:diabetes|hypertension|pcos|thyroid|asthma|depression|anxiety|gerd)\s+hai)\b",
    re.I,
)
C2_TREATMENT_PLAN_RE = re.compile(
    r"\b(?:treatment\s+plan|start\s+taking|stop\s+taking|double\s+the\s+dose|halve\s+the\s+dose)\b", re.I
)


def split_sentences_multilingual(text: str) -> list[str]:
    """Split text into sentences handling '.', '?', '!', '।', and newlines."""
    raw = re.split(r"(?<=[.?!।\n])\s+", text.strip())
    return [s.strip() for s in raw if s.strip()]


def check_p3_language_mode(text: str, language_mode: str = "hinglish") -> VerificationViolation | None:
    """P3: Natural Hinglish in Roman script (no Devanagari); English (no Hindi/Devanagari); Hindi (mostly Devanagari)."""
    lang = (language_mode or "hinglish").lower()
    has_devanagari = bool(DEVANAGARI_RE.search(text))

    if lang in ("hinglish", "en", "english"):
        if has_devanagari:
            return VerificationViolation(
                check_name="p3_script_mismatch",
                description=f"Response contains Devanagari script while language mode is {lang}",
                specific_feedback=f"Use Roman script only for {lang}. Avoid Devanagari characters.",
            )
        if lang in ("en", "english"):
            hindi_matches = ROMAN_HINDI_COMMON_RE.findall(text)
            if len(hindi_matches) >= 2:
                return VerificationViolation(
                    check_name="p3_english_pure",
                    description="Response contains Hindi words in English language mode",
                    specific_feedback="Use clear, casual English without Hindi words in English mode.",
                )
    elif lang in ("hi", "hindi"):
        # Hindi should use Devanagari script predominantly
        chars = [c for c in text if c.isalpha()]
        deva_chars = [c for c in text if "\u0900" <= c <= "\u097f"]
        if chars and (len(deva_chars) / len(chars)) < 0.35:
            return VerificationViolation(
                check_name="p3_hindi_devanagari",
                description="Hindi response must be primarily in Devanagari script",
                specific_feedback="Write Hindi responses in Devanagari script with everyday words.",
            )
    return None


def check_p4_honorifics(text: str) -> VerificationViolation | None:
    """P4: No honorifics ('Ji sir/ma'am'), no rigid corporate templates."""
    m = BANNED_HONORIFICS_RE.search(text)
    if m:
        return VerificationViolation(
            check_name="p4_banned_honorific",
            description=f"Response contains banned honorific '{m.group(0)}'",
            specific_feedback="Do not use formal honorifics like 'sir', 'ma'am', 'ji', or rigid templates. Keep it casual and friendly.",
        )
    return None


def check_p6_f3_length(text: str) -> VerificationViolation | None:
    """P6 & F3: 1-3 sentences maximum; no lengthy paragraphs, fast WhatsApp exchange feel."""
    sentences = split_sentences_multilingual(text)
    if len(sentences) > 3:
        return VerificationViolation(
            check_name="p6_f3_sentence_count",
            description=f"Response has {len(sentences)} sentences; maximum allowed is 3",
            specific_feedback="Keep your response strictly to 1-3 sentences maximum. Be concise like a WhatsApp exchange.",
        )
    if len(text) > 450:
        return VerificationViolation(
            check_name="p6_f3_char_cap",
            description=f"Response length {len(text)} exceeds 450 characters cap",
            specific_feedback="Shorten your response. Keep it under 400 characters, fast and direct.",
        )
    return None


def check_f1_zero_echo(text: str, context: dict[str, Any]) -> VerificationViolation | None:
    """F1: Zero-echo - never repeat back facts the user gave (e.g. stated weight, age, or full echo)."""
    user_input = str(context.get("user_input") or "").strip()
    if not user_input:
        return None

    # Check for direct number + unit echoes (e.g., "62 kg", "62kg", "75 kg")
    user_numbers = re.findall(r"\b(\d+(?:\.\d+)?)\s*(kg|kilos?|kgs?|years?|saal|ghante|hours?)\b", user_input, re.I)
    for num, unit in user_numbers:
        # Exempt emergency numbers
        if num in ("112", "14416"):
            continue
        # If response repeats "aapka weight {num}" or "{num} {unit}"
        pattern = re.compile(
            rf"\b(?:aapka|apka|your)\s+(?:weight|vajan|age|umra)\s+{re.escape(num)}\b|"
            rf"\b(?:weight|vajan)\s+{re.escape(num)}\s*{re.escape(unit)}\b",
            re.I,
        )
        if pattern.search(text):
            return VerificationViolation(
                check_name="f1_zero_echo",
                description=f"Response echoed user-stated fact '{num} {unit}'",
                specific_feedback=f"Do not repeat the user's stated facts back (e.g., do not say 'aapka weight {num}{unit}'). Acknowledge naturally and move forward.",
            )

    # Check for echo clause prefixes: "aapne bataya ki...", "as you mentioned..."
    echo_prefix_re = re.compile(
        r"^(?:(?:aapne|apne)\s+(?:bataya|kaha|likha)\s+(?:tha|hai)?\s*ki\s*|"
        r"jaise\s+ki\s+aapne\s+(?:bataya|kaha)\s*[,]?\s*|"
        r"as\s+you\s+(?:mentioned|said|noted|stated)\s*(?:that)?\s*)",
        re.I,
    )
    if echo_prefix_re.search(text.strip()):
        return VerificationViolation(
            check_name="f1_zero_echo_prefix",
            description="Response opens with an echo clause repeating user input",
            specific_feedback="Never open by repeating what the user just said (e.g. 'aapne bataya ki...'). Jump straight into your natural response.",
        )
    return None


def check_f2_at_most_one_question(text: str) -> VerificationViolation | None:
    """F2: At most ONE question per response."""
    q_count = text.count("?")
    if q_count > 1:
        return VerificationViolation(
            check_name="f2_multiple_questions",
            description=f"Response contains {q_count} question marks; maximum allowed is 1",
            specific_feedback="Ask at most ONE question in your response. Remove any secondary questions.",
        )
    return None


def check_f4_selective_empathy(text: str, context: dict[str, Any]) -> VerificationViolation | None:
    """F4: Empathy only when user shares distress or physical struggle; no artificial cheerleading."""
    distress = bool(context.get("distress_expressed", False))
    if not distress:
        # If user did NOT express distress, flag excessive boilerplate empathy
        empathy_boilerplate = re.compile(
            r"\b(?:main\s+aapka\s+dard\s+samajh\s+sakti\s+hoon|"
            r"i\s+(?:deeply\s+)?understand\s+your\s+pain|"
            r"sunkar\s+bahut\s+dukh\s+hua|"
            r"it\s+must\s+be\s+so\s+hard\s+for\s+you)\b",
            re.I,
        )
        if empathy_boilerplate.search(text):
            return VerificationViolation(
                check_name="f4_unprompted_boilerplate_empathy",
                description="Boilerplate empathy used when user did not share distress",
                specific_feedback="Do not use dramatic empathy boilerplate unless the user explicitly shared distress or struggle. Move forward naturally.",
            )
    return None


def check_c2_clinical_boundary(text: str) -> list[VerificationViolation]:
    """C2: No medication doses, diagnoses, or treatment plans on chat."""
    violations: list[VerificationViolation] = []
    if C2_MEDICATION_DOSE_RE.search(text):
        violations.append(
            VerificationViolation(
                check_name="c2_medication_dose_advice",
                description="Response specifies medication dose or quantity",
                specific_feedback="Never specify medication dosages or prescription advice in chat. Direct the user to a clinical consultation.",
                replacement_text=PRESCRIPTION_REPLACEMENT,
            )
        )
    if C2_DIAGNOSIS_RE.search(text):
        violations.append(
            VerificationViolation(
                check_name="c2_diagnosis_claim",
                description="Response provides a definitive diagnosis",
                specific_feedback="Never diagnose conditions on chat. Advise consulting a doctor for clinical assessment.",
                replacement_text=DIAGNOSIS_REPLACEMENT,
            )
        )
    if C2_TREATMENT_PLAN_RE.search(text):
        violations.append(
            VerificationViolation(
                check_name="c2_treatment_plan",
                description="Response outlines a treatment plan or medication alteration",
                specific_feedback="Never outline treatment plans in chat. Withhold medical advice and recommend consulting a clinician.",
                replacement_text=PRESCRIPTION_REPLACEMENT,
            )
        )
    return violations


def verify_response(text: str, context: dict[str, Any] | None = None) -> VerificationResult:
    """Run all 6 deterministic verification checks plus clinical guardrails."""
    ctx = context or {}
    violations: list[VerificationViolation] = []
    sanitized = text

    # Check 1: Doctor or human claim
    v1 = check_doctor_or_human_claim(sanitized)
    if v1:
        violations.append(v1)
        if v1.replacement_text:
            sanitized = v1.replacement_text

    # Check 2: Unsupported capabilities
    v2 = check_unsupported_capabilities(sanitized)
    if v2:
        violations.append(v2)
        if v2.replacement_text:
            sanitized = v2.replacement_text

    # Check 3: Ungrounded numbers and facts (pricing, prescription, diagnosis)
    for v3 in check_ungrounded_numbers_and_facts(sanitized, ctx):
        violations.append(v3)
        if v3.replacement_text:
            sanitized = v3.replacement_text

    # Check 4: False memory claims
    v4 = check_false_memory_claims(sanitized, ctx)
    if v4:
        violations.append(v4)

    # Check 5: Question spam
    v5 = check_question_spam(sanitized)
    if v5:
        violations.append(v5)

    # Check 6: N-gram repetitions
    v6 = check_ngram_repetitions(sanitized)
    if v6:
        violations.append(v6)
        if v6.replacement_text:
            sanitized = v6.replacement_text

    # Clinical safety checks (PEP, sodium, diet, unapproved remedies)
    for v_clin in check_pep_and_clinical_bounds(sanitized, ctx):
        violations.append(v_clin)
        if v_clin.replacement_text:
            sanitized = v_clin.replacement_text

    # Behavior Spec v1 checks (gated by config / context flag)
    from disha_core.config import get_settings

    settings = get_settings()
    if getattr(settings, "behavior_spec_v1", True) or ctx.get("behavior_spec_v1", True):
        lang = str(ctx.get("language") or ctx.get("user_language") or "hinglish")

        # P3: Language & script mode
        v_p3 = check_p3_language_mode(sanitized, lang)
        if v_p3:
            violations.append(v_p3)

        # P4: Banned honorifics
        v_p4 = check_p4_honorifics(sanitized)
        if v_p4:
            violations.append(v_p4)

        # P6 & F3: Length (1-3 sentences, char cap)
        v_len = check_p6_f3_length(sanitized)
        if v_len:
            violations.append(v_len)

        # F1: Zero-echo
        v_echo = check_f1_zero_echo(sanitized, ctx)
        if v_echo:
            violations.append(v_echo)

        # F2: At most one question
        v_f2 = check_f2_at_most_one_question(sanitized)
        if v_f2 and v_f2 not in violations:
            violations.append(v_f2)

        # F4: Selective empathy
        v_f4 = check_f4_selective_empathy(sanitized, ctx)
        if v_f4:
            violations.append(v_f4)

        # C2: No advice on chat (meds, diagnosis, treatment)
        for v_c2 in check_c2_clinical_boundary(sanitized):
            violations.append(v_c2)
            if v_c2.replacement_text:
                sanitized = v_c2.replacement_text

    return VerificationResult(
        is_valid=len(violations) == 0,
        violations=tuple(violations),
        sanitized_text=sanitized,
    )
