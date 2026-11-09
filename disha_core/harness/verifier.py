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
    """Check 4: Claims about past conversations when no such history exists."""
    has_history = context.get("has_history", False)
    history_turns = context.get("conversation_history") or []
    if not has_history and not history_turns:
        if PAST_MEMORY_RE.search(text):
            return VerificationViolation(
                check_name="false_memory_claims",
                description="Response references past conversations when no conversation history exists",
                specific_feedback="Do not claim to remember past conversations or statements that are not in the conversation history.",
                replacement_text=None,
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
    clinical_tags = context.get("clinical_tags") or ()
    if clinical_tags:
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

    return VerificationResult(
        is_valid=len(violations) == 0,
        violations=tuple(violations),
        sanitized_text=sanitized,
    )
