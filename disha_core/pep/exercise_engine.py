"""PEP-Aware Personalised Exercise Recommendation and Restriction Engine.

Clinical Logic:
1. Evaluates each proposed exercise against patient-specific PEP context:
   - Diagnosed health conditions (e.g., hypertension stage 1/2, cardiac, diabetes).
   - User-reported symptoms & pain locations (e.g., knee pain, lower back discomfort, shoulder impingement).
   - Injuries and physical limitations.
   - Activity level and exercise experience (sedentary vs active).
   - Patient preferences & workout location (home vs gym, equipment availability).
   - Clinician-provided restrictions and contraindications.
2. Classifies exercises deterministically:
   - SUITABLE: Safe and aligned with patient goals and condition.
   - MODIFIED: Safe with appropriate modifications / range-of-motion adjustments.
   - AVOID: Inadvisable due to known patient concern or medical contraindication.
   - INSUFFICIENT_INFO: Missing critical safety details; asks clarifying question.
   - REQUIRES_CLINICAL_ASSESSMENT: Severe acute pain or red flag needing professional care.
3. Provides personalized, safe alternatives and simple explanations for any avoided exercise.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
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
    stress_tags: frozenset[str]
    contraindicated_tags: frozenset[str]
    modifications: tuple[str, ...]
    alternatives: tuple[str, ...]
    default_level: str  # beginner, intermediate, advanced, all
    required_equipment: str  # none, dumbbells, resistance_bands, full_gym
    default_location: str  # home, gym, outdoor, any


@dataclass
class ExerciseEvaluation:
    exercise_name: str
    category: SuitabilityCategory
    reason: str
    modifications: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    caution_notes: str = ""
    clarification_question: str = ""


# Comprehensive Clinical Exercise Registry
EXERCISE_CATALOG: dict[str, ExerciseProfile] = {
    "squats": ExerciseProfile(
        name="squats",
        aliases=("squat", "deep squats", "air squats", "bodyweight squats"),
        stress_tags=frozenset({"knee_joint_loading", "patellar_shear", "quadriceps", "axial_spine"}),
        contraindicated_tags=frozenset({"knee_pain", "knee_injury", "patellar_tendonitis", "severe_arthritis_knee"}),
        modifications=(
            "Chair-supported shallow squats (limit knee bend to 45 degrees)",
            "Wall slide with exercise ball supporting the lumbar spine",
            "Keep knees tracking behind toes and avoid deep flexion",
        ),
        alternatives=(
            "Glute bridges (floor-based movement, removes knee shear force)",
            "Seated straight-leg raises to build quadriceps without joint loading",
            "Gentle flat-surface walking",
        ),
        default_level="beginner",
        required_equipment="none",
        default_location="home",
    ),
    "heavy_deadlifts": ExerciseProfile(
        name="heavy_deadlifts",
        aliases=("deadlift", "deadlifts", "heavy deadlift", "barbell deadlift", "max deadlift"),
        stress_tags=frozenset({"high_lumbar_shear", "valsalva_maneuver", "high_blood_pressure_spike", "axial_spine_compression"}),
        contraindicated_tags=frozenset({
            "hypertension_stage2",
            "hypertension_stage1",
            "cardiac_history",
            "aneurysm",
            "lower_back_pain",
            "slip_disc",
            "lumbar_herniation",
            "sciatica",
        }),
        modifications=(
            "Bodyweight hip hinge practice with neutral lumbar spine",
            "Light dumbbell Romanian deadlift with continuous rhythmic breathing (strictly no breath-holding)",
        ),
        alternatives=(
            "Bird-dog exercise on a soft mat (strengthens posterior chain with zero axial spine loading)",
            "Glute bridges on mat for posterior glute/hamstring engagement",
            "Brisk walking with active core bracing",
        ),
        default_level="intermediate",
        required_equipment="full_gym",
        default_location="gym",
    ),
    "jumping_jacks": ExerciseProfile(
        name="jumping_jacks",
        aliases=("jumping jack", "star jumps", "burpees", "box jumps", "jump rope"),
        stress_tags=frozenset({"high_impact_landing", "knee_impact", "cardiovascular_spike", "ankle_impact"}),
        contraindicated_tags=frozenset({"knee_pain", "knee_injury", "ankle_injury", "hypertension_stage2", "cardiac_history", "plantar_fasciitis"}),
        modifications=(
            "Low-impact step-jacks (step one foot out to the side without jumping)",
            "Rhythmic arm raises while walking in place",
        ),
        alternatives=(
            "Brisk walking with synchronized arm pumping",
            "Low-impact steady marching in place",
            "Stationary cycling at a comfortable cadence",
        ),
        default_level="beginner",
        required_equipment="none",
        default_location="home",
    ),
    "running": ExerciseProfile(
        name="running",
        aliases=("jogging", "run", "jog", "treadmill running", "sprints", "sprinting"),
        stress_tags=frozenset({"repetitive_knee_strike", "high_impact", "cardiovascular_exertion", "shin_splints"}),
        contraindicated_tags=frozenset({"knee_pain", "ankle_injury", "acute_shin_splints", "plantar_fasciitis", "cardiac_history"}),
        modifications=(
            "Brisk walking intervals (walk fast 2 mins, gentle walk 1 min)",
            "Walk on level grass or soft track rather than hard pavement",
        ),
        alternatives=(
            "Brisk outdoor walking or treadmill incline walking at low speed",
            "Stationary cycling with smooth pedal stroke",
            "Gentle swimming or shallow-water walking",
        ),
        default_level="intermediate",
        required_equipment="none",
        default_location="outdoor",
    ),
    "overhead_press": ExerciseProfile(
        name="overhead_press",
        aliases=("shoulder press", "military press", "dumbbell shoulder press"),
        stress_tags=frozenset({"shoulder_impingement", "hypertension_valsalva", "lumbar_extension"}),
        contraindicated_tags=frozenset({"shoulder_pain", "rotator_cuff_injury", "hypertension_stage2", "shoulder_impingement"}),
        modifications=(
            "Seated neutral-grip dumbbell press with light resistance",
            "Limit movement range below 90 degrees shoulder abduction",
        ),
        alternatives=(
            "Resistance band pull-aparts for scapular stability",
            "Incline chest press with light dumbbells",
            "Gentle wall-crawls and shoulder pendulum mobility exercises",
        ),
        default_level="intermediate",
        required_equipment="dumbbells",
        default_location="home",
    ),
    "crunches": ExerciseProfile(
        name="crunches",
        aliases=("sit-ups", "situps", "crunch", "ab crunches"),
        stress_tags=frozenset({"lumbar_flexion", "cervical_strain", "intra_abdominal_pressure"}),
        contraindicated_tags=frozenset({"lower_back_pain", "slip_disc", "lumbar_herniation", "cervical_pain", "diastasis_recti"}),
        modifications=(
            "Pelvic tilts on a flat mat with knees bent",
            "Deadbug exercise focusing on transverse abdominis engagement",
        ),
        alternatives=(
            "Bird-dog on all fours (safe isometric core stabilization)",
            "Forearm plank from knees with neutral spine",
            "Standing isometric ab bracing during daily walks",
        ),
        default_level="beginner",
        required_equipment="none",
        default_location="home",
    ),
    "brisk_walking": ExerciseProfile(
        name="brisk_walking",
        aliases=("walking", "walk", "tehalna", "morning walk", "evening walk", "brisk walk"),
        stress_tags=frozenset({"low_impact", "aerobic", "joint_friendly"}),
        contraindicated_tags=frozenset({"acute_severe_gout_foot", "acute_chest_pain"}),
        modifications=(
            "Short 10-minute bouts after meals to assist glucose management",
            "Wear supportive footwear with cushioned insoles",
        ),
        alternatives=(
            "Seated arm ergometer or gentle seated marching",
            "Gentle stretching and mobility flow",
        ),
        default_level="all",
        required_equipment="none",
        default_location="outdoor",
    ),
    "gentle_yoga": ExerciseProfile(
        name="gentle_yoga",
        aliases=("yoga", "pranayama", "stretching", "asanas", "cat-cow"),
        stress_tags=frozenset({"mobility", "low_intensity", "joint_decompression"}),
        contraindicated_tags=frozenset({"severe_joint_instability"}),
        modifications=(
            "Use yoga blocks and wall support for balance",
            "Avoid deep twists or inversions if blood pressure is elevated",
        ),
        alternatives=(
            "Chair yoga and seated spinal mobility",
            "Guided diaphragmatic breathing and relaxation",
        ),
        default_level="all",
        required_equipment="none",
        default_location="home",
    ),
}


def _match_exercise_profile(exercise_name: str) -> ExerciseProfile | None:
    """Finds the matching ExerciseProfile from name or aliases."""
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
) -> set[str]:
    """Extracts standardized clinical limitation and symptom tags from patient context."""
    tags: set[str] = set()

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
) -> ExerciseEvaluation:
    """Evaluates an exercise for a patient using deterministic clinical safety rules.

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
    )

    # Question 6: Is professional medical assessment needed?
    if "acute_severe_pain" in health_tags:
        return ExerciseEvaluation(
            exercise_name=raw_name,
            category=SuitabilityCategory.REQUIRES_CLINICAL_ASSESSMENT,
            reason="Aapne tez ya gambhir dard bataya hai. Is sthiti mein koi bhi naya exercise shuru karne se pehle clinician se jaanch karwana zaroori hai.",
            modifications=["Rest in a comfortable position", "Avoid bearing weight on the affected area"],
            alternatives=["Gentle seated breathing exercises"],
            caution_notes="Acute or severe pain warrants prompt clinician assessment.",
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
        if "hypertension_stage2" in health_tags or "hypertension_stage1" in health_tags or "cardiac_history" in health_tags:
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
            )

        # Joint loading where safe modification exists (e.g. bodyweight squats with chair support for mild knee discomfort)
        return ExerciseEvaluation(
            exercise_name=profile.name,
            category=SuitabilityCategory.MODIFIED,
            reason=f"{reason_str}. Lekin aap iska safe modified version try kar sakte hain.",
            modifications=list(profile.modifications),
            alternatives=list(profile.alternatives),
            caution_notes="Dard mehsoos hote hi turant stop karein.",
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

    if equip in ("none", "no_equipment") and profile.required_equipment != "none":
        return ExerciseEvaluation(
            exercise_name=profile.name,
            category=SuitabilityCategory.MODIFIED,
            reason="Aapne bataya ki aapke paas equipment nahi hai, isliye hum iska bodyweight vikalp chunenge.",
            modifications=["Use bodyweight resistance only", "Perform with neutral posture on a mat"],
            alternatives=alts,
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
        )

    # Default: SUITABLE
    return ExerciseEvaluation(
        exercise_name=profile.name,
        category=SuitabilityCategory.SUITABLE,
        reason=f"'{profile.name.replace('_', ' ').title()}' aapke health profile aur activity level ke liye ek accha aur safe vikalp hai.",
        modifications=mods[:1],
        alternatives=alts[:2],
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
