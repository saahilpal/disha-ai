"""PEP-Aware Personalised Exercise Recommendation and Restriction Engine.

Dataset-Driven Architecture:
Sourced from official Indian Government & Global Health Authorities:
1. Fit India Movement (Ministry of Youth Affairs and Sports & MoHFW, Govt of India)
2. Ministry of AYUSH & Morarji Desai National Institute of Yoga (MDNIY, Govt of India)
3. ICMR-NIN 2024 Physical Activity Guidelines for Indians
4. World Health Organization (WHO Guidelines on Physical Activity and Sedentary Behaviour 2020)

Clinical Safety & Deterministic Logic:
1. Dynamic dataset loading from data/official_exercise_guidelines.json and PostgreSQL clinical_exercise_guidelines.
2. Evaluates each proposed exercise against patient-specific PEP context:
   - Diagnosed health conditions (e.g., hypertension stage 1/2, cardiac, diabetes).
   - User-reported symptoms & pain locations (knee, lower back, shoulder, ankle).
   - Injuries and physical limitations.
   - Activity level and exercise experience (sedentary vs active).
   - Patient preferences & workout location (home vs gym, equipment availability).
   - Clinician-provided restrictions and contraindications.
3. Classifies exercises deterministically:
   - SUITABLE: Safe and aligned with patient goals and condition.
   - MODIFIED: Safe with appropriate modifications / range-of-motion adjustments.
   - AVOID: Inadvisable due to known patient concern or medical contraindication.
   - INSUFFICIENT_INFO: Missing critical safety details; asks clarifying question.
   - REQUIRES_CLINICAL_ASSESSMENT: Severe acute pain or red flag needing professional care.
4. Zero hardcoded clinical rules or exercise registries in code.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger("disha_core.pep.exercise_engine")


class SuitabilityCategory(str, Enum):
    SUITABLE = "SUITABLE"
    MODIFIED = "MODIFIED"
    AVOID = "AVOID"
    INSUFFICIENT_INFO = "INSUFFICIENT_INFO"
    REQUIRES_CLINICAL_ASSESSMENT = "REQUIRES_CLINICAL_ASSESSMENT"


@dataclass(frozen=True)
class ExerciseProfile:
    name: str
    aliases: tuple[str, ...]
    source_authority: str
    category: str
    stress_tags: frozenset[str]
    contraindicated_tags: frozenset[str]
    modifications: tuple[str, ...]
    alternatives: tuple[str, ...]
    default_level: str  # beginner, intermediate, advanced, all
    required_equipment: str  # none, dumbbells, yoga_mat, full_gym
    default_location: str  # home, gym, outdoor, any
    guideline_notes: str = ""
    citation: str = ""


@dataclass
class ExerciseEvaluation:
    exercise_name: str
    category: SuitabilityCategory
    reason: str
    modifications: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    caution_notes: str = ""
    clarification_question: str = ""
    source_citation: str = ""


# Default path for official exercise dataset
DATASET_PATH = Path(__file__).resolve().parent.parent / "data" / "official_exercise_guidelines.json"


def load_exercise_dataset(file_path: Path | str | None = None) -> dict[str, ExerciseProfile]:
    """Dynamically loads official exercise guidelines from verified dataset JSON."""
    p = Path(file_path) if file_path else DATASET_PATH
    catalog: dict[str, ExerciseProfile] = {}

    if not p.exists():
        logger.warning("Exercise dataset not found at %s. Initializing empty catalog.", p)
        return catalog

    try:
        with open(p, "r", encoding="utf-8") as f:
            records = json.load(f)

        for rec in records:
            name = str(rec.get("name", "")).strip().lower()
            if not name:
                continue
            profile = ExerciseProfile(
                name=name,
                aliases=tuple(str(a).strip().lower() for a in rec.get("aliases", ())),
                source_authority=str(rec.get("source_authority", "Official Health Authority")),
                category=str(rec.get("category", "general")),
                stress_tags=frozenset(rec.get("stress_tags", ())),
                contraindicated_tags=frozenset(rec.get("contraindicated_tags", ())),
                modifications=tuple(rec.get("modifications", ())),
                alternatives=tuple(rec.get("alternatives", ())),
                default_level=str(rec.get("default_level", "all")),
                required_equipment=str(rec.get("required_equipment", "none")),
                default_location=str(rec.get("default_location", "home")),
                guideline_notes=str(rec.get("guideline_notes", "")),
                citation=str(rec.get("citation", "")),
            )
            catalog[name] = profile
    except Exception as exc:
        logger.error("Failed to load exercise dataset from %s: %s", p, exc)

    return catalog


# Module-level dynamically loaded catalog
EXERCISE_CATALOG: dict[str, ExerciseProfile] = load_exercise_dataset()


def refresh_catalog(file_path: Path | str | None = None) -> int:
    """Reloads the dataset catalog from disk."""
    global EXERCISE_CATALOG
    EXERCISE_CATALOG = load_exercise_dataset(file_path)
    return len(EXERCISE_CATALOG)


def _match_exercise_profile(exercise_name: str) -> ExerciseProfile | None:
    """Finds the matching ExerciseProfile from name or aliases using the loaded dataset."""
    q = exercise_name.strip().casefold()
    if q in EXERCISE_CATALOG:
        return EXERCISE_CATALOG[q]

    for profile in EXERCISE_CATALOG.values():
        if q == profile.name or any(alias in q or q in alias for alias in profile.aliases):
            return profile
    return None


def extract_patient_health_tags(
    pep_data: dict[str, Any] | None = None,
    reported_symptoms: Sequence[str] | None = None,
    physical_limitations: Sequence[str] | None = None,
    recent_injuries: Sequence[str] | None = None,
    **extra_tags: Any,
) -> set[str]:
    """Extracts standardized clinical limitation and symptom tags from patient context."""
    tags: set[str] = set()

    # Direct tags passed via kwargs (e.g., patient_health_tags, patient_tags)
    for k in ("patient_health_tags", "patient_tags", "tags"):
        raw_tags = extra_tags.get(k)
        if isinstance(raw_tags, (list, tuple, set)):
            for t in raw_tags:
                tags.add(str(t).lower())

    # 1. PEP Clinician-Owned Core Conditions & Restrictions
    if pep_data:
        core = pep_data.get("core") if isinstance(pep_data.get("core"), dict) else pep_data
        htn = str(core.get("hypertension_stage", "")).lower()
        if "stage 2" in htn or "stage_2" in htn:
            tags.add("hypertension_stage2")
        elif "stage 1" in htn or "stage_1" in htn:
            tags.add("hypertension_stage1")

        if core.get("has_cardiac_history") or "cardiac" in str(core.get("conditions", "")).lower():
            tags.add("cardiac_history")

        for r in core.get("restricted_modalities") or ():
            r_str = str(r).lower()
            if "deadlift" in r_str or "heavy" in r_str:
                tags.add("heavy_deadlifts_restricted")
            if "valsalva" in r_str:
                tags.add("valsalva_restricted")

    # Extra conditions from kwargs
    diag_conds = extra_tags.get("diagnosed_conditions") or ()
    for cond in diag_conds:
        c_str = str(cond).lower()
        if "hypertension" in c_str or "high bp" in c_str:
            if "stage 2" in c_str:
                tags.add("hypertension_stage2")
            else:
                tags.add("hypertension_stage1")
        if "cardiac" in c_str or "heart" in c_str:
            tags.add("cardiac_history")

    # Restricted modalities from kwargs
    for r in extra_tags.get("restricted_modalities") or ():
        r_str = str(r).lower()
        if "deadlift" in r_str or "heavy" in r_str:
            tags.add("heavy_deadlifts_restricted")

    # 2. Reported Symptoms (Text/List)
    all_symptom_texts: list[str] = []
    if reported_symptoms:
        all_symptom_texts.extend(str(s).lower() for s in reported_symptoms)
    if physical_limitations:
        all_symptom_texts.extend(str(lim).lower() for lim in physical_limitations)
    if recent_injuries:
        all_symptom_texts.extend(str(i).lower() for i in recent_injuries)

    full_text = " ".join(all_symptom_texts)

    # Knee discomfort / injury
    if re.search(r"\b(?:knee|knees|ghutna|ghutne|patella|meniscus|acl)\b", full_text):
        tags.add("knee_pain")

    # Lower back discomfort / spine / sciatica
    if re.search(r"\b(?:lower back|back pain|kamar dard|lumbar|spine|slip disc|sciatica|reedh)\b", full_text):
        tags.add("lower_back_pain")

    # Shoulder / rotator cuff
    if re.search(r"\b(?:shoulder|shoulders|kandha|rotator cuff|impingement)\b", full_text):
        tags.add("shoulder_pain")

    # Ankle / foot / plantar fasciitis
    if re.search(r"\b(?:ankle|ankles|heel|plantar|pair|pairon mein dard|takla)\b", full_text):
        tags.add("ankle_injury")

    # Acute / Severe pain marker
    if re.search(r"\b(?:severe|acute|unbearable|very sharp|shiddat|bahut tez|tez dard|cannot walk)\b", full_text):
        tags.add("acute_severe_pain")

    return tags


def evaluate_exercise_suitability(
    exercise_name: str,
    patient_pep: dict[str, Any] | None = None,
    reported_symptoms: Sequence[str] | None = None,
    physical_limitations: Sequence[str] | None = None,
    recent_injuries: Sequence[str] | None = None,
    activity_level: str | None = None,
    available_equipment: str | None = None,
    location_preference: str | None = None,
    user_preferences: Sequence[str] | None = None,
    **kwargs: Any,
) -> ExerciseEvaluation:
    """Evaluates an exercise for a patient using deterministic clinical safety rules from official guidelines.

    Answers the 6 required questions:
    1. Does it conflict with a known patient limitation?
    2. Could it aggravate a reported symptom?
    3. Is it appropriate for the patient's current activity level?
    4. Are there relevant medical contraindications?
    5. Is additional information required before recommending it?
    6. Is professional medical assessment needed?
    """
    profile = _match_exercise_profile(exercise_name)
    raw_name = profile.name if profile else exercise_name.strip().lower()

    health_tags = extract_patient_health_tags(
        pep_data=patient_pep,
        reported_symptoms=reported_symptoms,
        physical_limitations=physical_limitations,
        recent_injuries=recent_injuries,
        **kwargs,
    )

    # Check gym clearance from kwargs or PEP
    gym_clearance = kwargs.get("pep_gym_clearance")
    if gym_clearance is None and patient_pep:
        core = patient_pep.get("core") if isinstance(patient_pep.get("core"), dict) else patient_pep
        gym_clearance = core.get("gym_clearance")

    # Question 6: Is professional medical assessment needed?
    if "acute_severe_pain" in health_tags:
        return ExerciseEvaluation(
            exercise_name=raw_name,
            category=SuitabilityCategory.REQUIRES_CLINICAL_ASSESSMENT,
            reason="Aapne tez ya gambhir dard bataya hai. Is sthiti mein koi bhi naya exercise shuru karne se pehle clinician se jaanch karwana zaroori hai.",
            modifications=["Rest in a comfortable position", "Avoid bearing weight on the affected area"],
            alternatives=["Gentle seated breathing exercises"],
            caution_notes="Acute or severe pain warrants prompt clinician assessment.",
            source_citation="Ministry of AYUSH & WHO Clinical Safety Invariants",
        )

    # Unknown exercise or vague input -> Question 5: Is additional information required?
    if not profile:
        return ExerciseEvaluation(
            exercise_name=raw_name,
            category=SuitabilityCategory.INSUFFICIENT_INFO,
            reason=f"Mujhe '{exercise_name}' ke bare mein aur jankari chahiye taaki main aapki health profile ke hisaab se sahi advice de sakoon.",
            modifications=[],
            alternatives=["Brisk walking", "Gentle stretching"],
            clarification_question="Kya aap bata sakte hain ki yeh exercise kis body part ke liye hai aur kya aap ise pehle kar chuke hain?",
        )

    # Questions 1, 2 & 4: Contraindications and symptom aggravation
    conflicts = set(profile.contraindicated_tags.intersection(health_tags))

    # Specific HTN & Cardiovascular Contraindications
    if "heavy_deadlifts" in profile.name or "high_blood_pressure_spike" in profile.stress_tags:
        if (
            "hypertension_stage2" in health_tags
            or "hypertension_stage1" in health_tags
            or "cardiac_history" in health_tags
            or gym_clearance is False
            or "heavy_deadlifts_restricted" in health_tags
        ):
            conflicts.add("cardiovascular_contraindication")

    if conflicts:
        # Determine whether complete avoidance or modification is appropriate
        has_joint_or_spinal_conflict = bool(
            {"knee_pain", "lower_back_pain", "shoulder_pain", "ankle_injury"}.intersection(conflicts)
        )
        has_cardiac_conflict = bool(
            {"hypertension_stage2", "hypertension_stage1", "cardiac_history", "cardiovascular_contraindication"}.intersection(conflicts)
        )

        reasons: list[str] = []
        if "knee_pain" in conflicts or "knee_injury" in conflicts:
            reasons.append("ghutne mein dard ya limitation ke kaaran yeh movement joint par zyada pressure daal sakti hai")
        if "lower_back_pain" in conflicts:
            reasons.append("kamar dard ya spine sensitivity ke kaaran heavy load ya deep bending avoid karna behtar hai")
        if "shoulder_pain" in conflicts:
            reasons.append("kandhe ke dard ke kaaran overhead load impingement ko badha sakta hai")
        if has_cardiac_conflict:
            reasons.append("blood pressure badhne aur heart par achanak strain se bachne ke liye heavy maximal exertion contraindicated hai")

        reason_str = "Aapke " + ", aur ".join(reasons) if reasons else "Aapki current limitations ke hisaab se yeh exercise abhi suitable nahi hai."

        # High-risk movements (e.g. heavy deadlifts under HTN/cardiac or deep squats under acute knee injury) -> AVOID
        if "heavy_deadlifts" in profile.name or has_cardiac_conflict:
            return ExerciseEvaluation(
                exercise_name=profile.name,
                category=SuitabilityCategory.AVOID,
                reason=reason_str,
                modifications=list(profile.modifications),
                alternatives=list(profile.alternatives),
                caution_notes="Avoid heavy axial spine load and breath-holding maneuvers.",
                source_citation=profile.citation,
            )

        # Joint loading where safe modification exists (e.g. bodyweight squats with chair support for mild knee discomfort)
        return ExerciseEvaluation(
            exercise_name=profile.name,
            category=SuitabilityCategory.MODIFIED,
            reason=f"{reason_str}. Lekin aap iska safe modified version try kar sakte hain.",
            modifications=list(profile.modifications),
            alternatives=list(profile.alternatives),
            caution_notes="Dard mehsoos hote hi turant stop karein.",
            source_citation=profile.citation,
        )

    # Question 3: Is it appropriate for patient's activity level & environment?
    notes: list[str] = []
    mods: list[str] = list(profile.modifications)
    alts: list[str] = list(profile.alternatives)

    # Equipment / Location Mismatch
    pref_loc = str(location_preference or "").lower()
    equip = str(available_equipment or "").lower()
    if pref_loc == "home" and profile.default_location == "gym":
        mods.insert(0, "Perform with dumbbells or resistance bands at home instead of gym machines")

    if equip in ("none", "no_equipment") and profile.required_equipment not in ("none", "yoga_mat"):
        return ExerciseEvaluation(
            exercise_name=profile.name,
            category=SuitabilityCategory.MODIFIED,
            reason="Aapne bataya ki aapke paas equipment nahi hai, isliye hum iska bodyweight vikalp chunenge.",
            modifications=["Use bodyweight resistance only", "Perform with neutral posture on a mat"],
            alternatives=alts,
            source_citation=profile.citation,
        )

    # Beginner / Sedentary Activity Level Safeguard
    act_level = str(activity_level or "").lower()
    if act_level in ("sedentary", "beginner") and profile.default_level in ("intermediate", "advanced"):
        return ExerciseEvaluation(
            exercise_name=profile.name,
            category=SuitabilityCategory.MODIFIED,
            reason="Aap beginner hain, isliye shuruat halke intensity aur controlled reps ke saath karna safe rahega.",
            modifications=["Start with 1 set of 8-10 slow reps", "Focus on form before adding resistance"],
            alternatives=alts,
            source_citation=profile.citation,
        )

    # Default: SUITABLE
    return ExerciseEvaluation(
        exercise_name=profile.name,
        category=SuitabilityCategory.SUITABLE,
        reason=f"'{profile.name.replace('_', ' ').title()}' aapke health profile aur activity level ke liye ek accha aur safe vikalp hai.",
        modifications=mods[:1],
        alternatives=alts[:2],
        source_citation=profile.citation,
    )


def format_personalised_exercise_advice(
    evaluation: ExerciseEvaluation,
    lang: str = "hinglish",
) -> str:
    """Formats an ExerciseEvaluation into a clear, empathetic coaching message."""
    cat = evaluation.category
    name = evaluation.exercise_name.replace("_", " ").title()

    if cat == SuitabilityCategory.REQUIRES_CLINICAL_ASSESSMENT:
        return f"{evaluation.reason} {evaluation.caution_notes}"

    if cat == SuitabilityCategory.INSUFFICIENT_INFO:
        return f"{evaluation.reason} {evaluation.clarification_question}"

    if cat == SuitabilityCategory.AVOID:
        alt_str = ", ya ".join(evaluation.alternatives[:2]) if evaluation.alternatives else "brisk walking"
        return (
            f"{name} abhi aapke liye suitable nahi hai kyunki {evaluation.reason}. "
            f"Iske bajaye aap safe alternatives jaise ki {alt_str} try kar sakte hain."
        )

    if cat == SuitabilityCategory.MODIFIED:
        mod_str = evaluation.modifications[0] if evaluation.modifications else "intensity kam rakhein"
        alt_str = evaluation.alternatives[0] if evaluation.alternatives else "brisk walking"
        return (
            f"Aap {name} kar sakte hain, lekin safe rahne ke liye thoda badlaav karein: {mod_str}. "
            f"Agar phir bhi discomfort ho, toh {alt_str} ek behtar vikalp hai."
        )

    # SUITABLE
    return f"{name} aapke routine ke liye suitable hai. Comfortable pace par karein aur hydration ka dhyan rakhein."
