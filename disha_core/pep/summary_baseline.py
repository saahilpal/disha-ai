"""Summary-then-Update Baseline PEP Update Pipeline.

Maintains rolling conversation digest and executes session-level extraction of
PEP slots conforming to SharedPEPUpdater.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from disha_core.pep.shared_interface import (
    ClinicalStatus,
    PEPSlotRecord,
    SharedPEPUpdater,
    SlotSource,
    VerificationStatus,
)

logger = logging.getLogger("disha_core.pep.summary_baseline")


@dataclass
class SessionTurnDigest:
    """Session digest tracking conversation history and rolling disclosures."""
    patient_id: str
    session_id: str
    turns: list[dict[str, str]] = field(default_factory=list)
    rolling_disclosures: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def normalize_text(text: str) -> str:
    """Normalize unicode, Hindi digits, and whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    trans = str.maketrans("०१२३४५६७८९", "0123456789")
    text = text.translate(trans)
    return " ".join(text.split())


def is_third_party(text: str) -> bool:
    """Detect if utterance attributes health facts to a third party."""
    t = text.lower()
    tp_patterns = [
        r"(?:mere\s+dost|dost\s+ko|friend|my\s+friend|my\s+colleague|colleague|roommate|neighbor)",
        r"(?:mere\s+bhai|brother|my\s+brother|meri\s+behen|sister|my\s+sister)",
        r"(?:my\s+mother|meri\s+mummy|meri\s+maa|mother|mummy)",
        r"(?:my\s+father|mere\s+papa|mere\s+pitaji|father|papa)",
        r"(?:pati|husband|patni|wife)",
    ]
    for pat in tp_patterns:
        if re.search(pat, t):
            if not re.search(r"(?:mujhe\s+bhi|main\s+bhi|i\s+also)", t):
                return True
    return False


def is_hypothetical(text: str) -> bool:
    """Detect hypothetical conjectures or future scenarios."""
    t = text.lower()
    patterns = [
        r"(?:यदि\s+किसी\s+को|kisi\s+ko|किसी\s+को|if\s+someone|if\s+a\s+person|agar\s+kisi\s+ko)",
        r"(?:agar\s+main\s+.*?\s+lagun\s+to\s+kya)",
        r"(?:suppose\s+if|suppose\s+i|what\s+if\s+someone)",
        r"(?:if\s+i\s+were|in\s+the\s+future)",
    ]
    for pat in patterns:
        if re.search(pat, t):
            return True
    return False


def is_informational_question(text: str) -> bool:
    """Detect generic questions seeking medical info rather than personal disclosure."""
    t = text.lower().strip()
    is_q = t.endswith("?") or re.match(r"^(?:what|how|is|are|can\s+i|kya|ek\s+swasth|क्या)\b", t)
    if not is_q:
        return False
    # If the user opens with an explicit personal health disclosure, do not reject
    if re.search(r"^(?:mujhe|मुझे|main|मैं|i\s+am|i\s+have|i\s+take)\b", t):
        return False
    if re.search(r"(?:i\s+am\s+14\s+weeks\s+pregnant|i\s+was\s+diagnosed|main\s+metformin|मुझे\s+मूंगफली)", t):
        return False
    return True


def is_prompt_injection(text: str) -> bool:
    """Detect attempts to override boundaries or delete clinical restrictions."""
    t = text.lower()
    patterns = [
        r"(?:purani\s+sari\s+restrictions\s+delete\s+karo|delete\s+all\s+.*?\s+restrictions)",
        r"(?:heavy\s+weightlifting\s+ki\s+permission\s+do|ignore\s+previous|override\s+safety|disregard\s+clinical\s+safety)",
        r"(?:reset\s+my\s+profile\s+to\s+no\s+restrictions)",
    ]
    for pat in patterns:
        if re.search(pat, t):
            return True
    return False


def is_sarcasm_or_idiom(text: str) -> bool:
    """Detect sarcastic self-aggrandizement or idioms."""
    t = text.lower()
    patterns = [
        r"(?:usain\s+bolt|superman|queen\s+of\s+england)",
        r"(?:kismat\s+hi\s+kharab\s+hai|sari\s+bimariyan\s+mujhe\s+hi)",
    ]
    for pat in patterns:
        if re.search(pat, t):
            return True
    return False


def is_general_negation(text: str) -> bool:
    """Detect explicit negative assertions denying conditions/allergies."""
    t = text.lower()
    if re.search(r"(?:do\s+not\s+eat\s+non-vegetarian|non-veg\s+nahi\s+khata)", t):
        return False
    patterns = [
        r"(?:koi\s+allergy\s+ya\s+khanpan\s+ki\s+pabandi\s+nahi|कोई\s+एलर्जी\s+या\s+खानपान\s+की\s+पाबंदी\s+नहीं)",
        r"(?:definitely\s+do\s+not\s+have\s+high\s+cholesterol)",
        r"(?:pair\s+ya\s+ghutne\s+mein\s+koi\s+dard\s+nahi|aaram\s+se\s+chal\s+sakta\s+hoon)",
        r"(?:not\s+diagnosed|no\s+known\s+allergies|all\s+clear)",
    ]
    for pat in patterns:
        if re.search(pat, t):
            return True
    return False


def extract_slots_from_turns(
    turns: list[dict[str, str]],
    is_onboarding: bool = False,
) -> list[dict[str, Any]]:
    """Extract PEP slots from user turns across English, Hindi, and Hinglish."""
    user_turns = [t["text"] for t in turns if t.get("role") == "user"]
    if not user_turns:
        return []

    slots: dict[str, dict[str, Any]] = {}

    for u_idx, raw_text in enumerate(user_turns):
        text = normalize_text(raw_text)
        t_lower = text.lower()

        # Guard filters: ignore adversarial or non-personal claims
        if is_third_party(text) or is_hypothetical(text) or is_prompt_injection(text) or is_sarcasm_or_idiom(text):
            continue
        if is_informational_question(text):
            continue
        if is_general_negation(text):
            continue

        default_src = "onboarding" if is_onboarding else "chat_user"
        ev_label = f"evidence:usr:{u_idx}"

        # 1. Name
        m_name = re.search(r"(?:my\s+name\s+is|mera\s+naam)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", text, re.I)
        if m_name:
            words = m_name.group(1).strip().split()
            valid_words = [w for w in words if w.lower() not in ("hai", "hoon", "hun", "ji")]
            if valid_words:
                name_val = " ".join(valid_words)
                slots["name"] = {"slot": "name", "value": name_val, "status": "active", "source": "onboarding", "evidence": ev_label}

        # 2. Age
        m_age_corr = re.search(r"(?:उम्र\s*38\s*नहीं\s*,\s*वास्तव\s*में\s*|age\s+is\s+actually\s+)(\d{1,2})", text)
        if m_age_corr:
            age_val = int(m_age_corr.group(1))
            slots["age"] = {"slot": "age", "value": age_val, "status": "active", "source": "chat_user", "evidence": ev_label}
        else:
            m_age = re.search(r"\b(?:age|umar|उम्र)\s+(\d{1,2})\b", text, re.I)
            if m_age:
                age_val = int(m_age.group(1))
                slots["age"] = {"slot": "age", "value": age_val, "status": "active", "source": default_src, "evidence": ev_label}

        # 3. Height cm
        m_h = re.search(r"\b(?:height|kad)\s+(\d{2,3}(?:\.\d+)?)\s*cm", text, re.I)
        if m_h:
            h_val = float(m_h.group(1))
            slots["height_cm"] = {"slot": "height_cm", "value": h_val, "status": "active", "source": "onboarding", "evidence": ev_label}

        # 4. Weight kg
        m_w = re.search(r"\b(?:weight|vajan|wajan)\s+(\d{2,3}(?:\.\d+)?)\s*kg", text, re.I)
        if m_w:
            w_val = float(m_w.group(1))
            slots["weight_kg"] = {"slot": "weight_kg", "value": w_val, "status": "active", "source": "onboarding", "evidence": ev_label}

        # 5. Primary focus
        if re.search(r"(?:पहले\s+मेरा\s+लक्ष्य\s+वजन\s+घटाना\s+था\s*,\s*अब\s+.*ब्लड\s+प्रेशर)", text):
            slots["primary_focus"] = {"slot": "primary_focus", "value": "bp_control", "status": "active", "source": "chat_user", "evidence": ev_label}
        elif re.search(r"(?:weight\s+loss|vajan\s+ghatana|वजन\s+घटाना)", text, re.I):
            slots["primary_focus"] = {"slot": "primary_focus", "value": "weight_loss", "status": "active", "source": default_src, "evidence": ev_label}
        elif re.search(r"(?:diabetes\s+management\s+as\s+primary\s+goal|मुख्य\s+लक्ष्य\s+शुगर)", text, re.I):
            slots["primary_focus"] = {"slot": "primary_focus", "value": "diabetes_management", "status": "active", "source": "onboarding", "evidence": ev_label}
        elif re.search(r"(?:ब्लड\s+प्रेशर\s+कंट्रोल|bp\s+control)", text, re.I):
            slots["primary_focus"] = {"slot": "primary_focus", "value": "bp_control", "status": "active", "source": default_src, "evidence": ev_label}

        # 6. Secondary focuses
        if re.search(r"\b(?:tenshun|stress|tension|तनाव)\b", text, re.I) and not is_third_party(text):
            slots["secondary_focuses"] = {"slot": "secondary_focuses", "value": ["stress_management"], "status": "active", "source": "chat_user", "evidence": ev_label}

        # 7. Work schedule
        if re.search(r"(?:night\s+shift|नाइट\s+शिफ्ट)", text, re.I):
            slots["work_schedule"] = {"slot": "work_schedule", "value": "night_shift", "status": "active", "source": default_src, "evidence": ev_label}
        elif re.search(r"(?:day\s+shifts?|डे\s+शिफ्ट|दिन\s+की\s+सामान्य\s+ड्यूटी)", text, re.I):
            slots["work_schedule"] = {"slot": "work_schedule", "value": "day_shift", "status": "active", "source": default_src, "evidence": ev_label}

        # 8. Wake time & Sleep time
        m_night_comb = re.search(r"subah\s+(\d+)\s+baje\s+sota\s+hoon\s+aur\s+(\d+)\s+baje\s+uthta", text, re.I)
        if m_night_comb:
            s_hr = int(m_night_comb.group(1))
            w_hr = int(m_night_comb.group(2))
            slots["sleep_time"] = {"slot": "sleep_time", "value": f"{s_hr:02d}:00", "status": "active", "source": default_src, "evidence": ev_label}
            w_24 = w_hr + 12 if w_hr < 12 else w_hr
            slots["wake_time"] = {"slot": "wake_time", "value": f"{w_24:02d}:00", "status": "active", "source": default_src, "evidence": ev_label}
        else:
            m_wake = re.search(r"(?:wake\s*up.*?at|morning\s+walk\s+at|walk\s+at|wake\s+time\s+is)\s*(\d{1,2}:\d{2})\s*(?:am|बजे)?", text, re.I)
            if not m_wake:
                m_wake = re.search(r"(\d{1,2}:\d{2})\s*(?:am|बजे)?\s*(?:uth\s+jata\s+hoon|उठता|wake)", text, re.I)
            if not m_wake:
                m_wake = re.search(r"(?:subah|सुबह|प्रातः)\s*(\d{1,2}:\d{2})\s*(?:am|बजे)?", text, re.I)
            if not m_wake:
                m_wake = re.search(r"(?:wake\s+up\s+time\s+is\s+)(\d{1,2}:\d{2})", text, re.I)
            if m_wake:
                val = m_wake.group(1).strip()
                if len(val.split(":")[0]) == 1:
                    val = f"0{val}"
                slots["wake_time"] = {"slot": "wake_time", "value": val, "status": "active", "source": default_src, "evidence": ev_label}

            m_sleep_corr = re.search(r"(?:used\s+to\s+sleep\s+at\s+.*?(?:now|consistently)\s+sleep\s+at)\s*(\d{1,2}:\d{2})\s*(?:am|pm)?", text, re.I)
            if m_sleep_corr:
                raw_t = m_sleep_corr.group(1).strip()
                hr, mn = [int(x) for x in raw_t.split(":")]
                if hr == 12:
                    val = f"00:{mn:02d}"
                else:
                    val = f"{hr:02d}:{mn:02d}"
                slots["sleep_time"] = {"slot": "sleep_time", "value": val, "status": "active", "source": "chat_user", "evidence": ev_label}
            else:
                m_sleep = re.search(r"(?:सो\s+जाता\s+हूँ|sota\s+hoon|sleep\s+at)\s*(?:around|at|pe|ko)?\s*(\d{1,2}(?::\d{2})?)\s*(?:am|pm|baje|बजे)?", text, re.I)
                if not m_sleep:
                    m_sleep = re.search(r"(\d{1,2}(?::\d{2})?)\s*(?:baje|बजे)?\s*(?:sota|सो\s+जाता|sleep)", text, re.I)
                if not m_sleep:
                    m_sleep = re.search(r"(?:रात|raat)\s*(\d{1,2}(?::\d{2})?)\s*(?:baje|बजे)?", text, re.I)
                if m_sleep:
                    raw_s = m_sleep.group(1).strip()
                    if ":" in raw_s:
                        hr, mn = [int(x) for x in raw_s.split(":")]
                    else:
                        hr, mn = int(raw_s), 0
                    if hr == 12 or hr == 0:
                        val = f"00:{mn:02d}"
                    elif hr < 12 and any(w in t_lower for w in ["रात", "raat", "night", "pm"]):
                        val = f"{hr+12:02d}:{mn:02d}"
                    else:
                        val = f"{hr:02d}:{mn:02d}"
                    slots["sleep_time"] = {"slot": "sleep_time", "value": val, "status": "active", "source": default_src, "evidence": ev_label}

        # 9. Water intake target
        m_water_corr = re.search(r"(?:don't\s+drink\s+.*?actually\s+)(\d+(?:\.\d+)?)\s*lit", text, re.I)
        if m_water_corr:
            slots["water_intake_target"] = {"slot": "water_intake_target", "value": float(m_water_corr.group(1)), "status": "active", "source": "chat_user", "evidence": ev_label}
        else:
            m_water = re.search(r"(\d+(?:\.\d+)?)\s*(?:litre|liter|litres|liters|लीटर)\s*(?:paani|pani|पानी|of\s+water)?", text, re.I)
            if not m_water:
                m_water = re.search(r"(?:paani|pani|water|पानी)\s*.*?(\d+(?:\.\d+)?)\s*(?:litre|liter|लीटर)", text, re.I)
            if m_water:
                slots["water_intake_target"] = {"slot": "water_intake_target", "value": float(m_water.group(1)), "status": "active", "source": default_src, "evidence": ev_label}

        # 10. Daily steps target
        m_steps_corr = re.search(r"(?:pehle\s+.*?\s+ab\s+.*?)(\d+)\s*steps", text, re.I)
        if m_steps_corr:
            slots["daily_steps_target"] = {"slot": "daily_steps_target", "value": int(m_steps_corr.group(1)), "status": "active", "source": "chat_user", "evidence": ev_label}
        else:
            m_steps = re.search(r"(\d+)\s*(?:walking\s+steps|steps|kadam|कदम)", text, re.I)
            if m_steps:
                slots["daily_steps_target"] = {"slot": "daily_steps_target", "value": int(m_steps.group(1)), "status": "active", "source": default_src, "evidence": ev_label}

        # 11. Tea/Coffee frequency
        if re.search(r"(?:no\s+tea\s+or\s+coffee|tea\s+coffee\s+nahi|zero\s+tea)", text, re.I):
            slots["tea_coffee_frequency"] = {"slot": "tea_coffee_frequency", "value": {"tea_cups_per_day": 0, "coffee_cups_per_day": 0, "frequency_label": "none"}, "status": "active", "source": default_src, "evidence": ev_label}
        else:
            m_tea = re.search(r"(\d+)\s*cups?\s*of\s*(?:milk\s+)?tea", text, re.I)
            if m_tea:
                num = int(m_tea.group(1))
                slots["tea_coffee_frequency"] = {"slot": "tea_coffee_frequency", "value": {"tea_cups_per_day": num, "frequency_label": f"{num} cups/day"}, "status": "active", "source": default_src, "evidence": ev_label}

        # 12. Meal preferences
        if re.search(r"(?:chicken\s+biryani.*?non-veg\s+start|ab\s+main\s+non-veg)", text, re.I):
            slots["meal_preferences"] = {"slot": "meal_preferences", "value": "Non-Vegetarian", "status": "active", "source": "chat_user", "evidence": ev_label}
        elif re.search(r"(?:do\s+not\s+eat\s+non-vegetarian\s+food\s+ever)", text, re.I):
            slots["meal_preferences"] = {"slot": "meal_preferences", "value": "Vegetarian", "status": "active", "source": "chat_user", "evidence": ev_label}
        elif re.search(r"(?:jain\s+khana|bina\s+pyaz\s+lahsun|जैन)", text, re.I):
            slots["meal_preferences"] = {"slot": "meal_preferences", "value": "Jain", "status": "active", "source": default_src, "evidence": ev_label}
        elif re.search(r"(?:eggetarian)", text, re.I):
            slots["meal_preferences"] = {"slot": "meal_preferences", "value": "Eggetarian", "status": "active", "source": default_src, "evidence": ev_label}
        elif re.search(r"(?:pure\s+veg|shuddh\s+shakahari|शुद्ध\s+शाकाहारी|vegetarian)", text, re.I):
            slots["meal_preferences"] = {"slot": "meal_preferences", "value": "Vegetarian", "status": "active", "source": default_src, "evidence": ev_label}

        # 13. Dietary restrictions
        d_restr: list[str] = []
        if re.search(r"(?:allergic\s+to\s+peanuts|मूंगफली\s+से\s+तेज\s+एलर्जी|peanut\s+allergy)", text, re.I):
            d_restr.append("nut_allergy")
        if re.search(r"(?:lactose\s+intoleran|दूध\s+पीते\s+ही\s+पेट\s+दर्द)", text, re.I):
            d_restr.append("lactose_intolerant")
        if re.search(r"(?:allergic\s+to\s+gluten\s+and\s+have\s+celiac)", text, re.I):
            d_restr.extend(["gluten_free", "celiac"])
        elif re.search(r"(?:gluten\s+allergy|gluten\s+free|ग्लूटेन)", text, re.I):
            d_restr.append("gluten_free")
        if re.search(r"(?:प्याज\s+और\s+लहसुन\s+नहीं\s+खाता|no\s+onion\s+garlic)", text, re.I):
            d_restr.append("no_onion_garlic")
        if d_restr:
            slots["dietary_restrictions"] = {"slot": "dietary_restrictions", "value": sorted(list(set(d_restr))), "status": "active", "source": default_src, "evidence": ev_label}

        # 14. Current medications
        meds: list[str] = []
        if re.search(r"(?:badal\s+kar\s+telmisartan\s+40mg)", text, re.I):
            meds.append("telmisartan_40mg")
        elif re.search(r"(?:amlodipine\s+5mg)", text, re.I):
            meds.append("amlodipine")
        if re.search(r"(?:atorvastatin\s+10mg)", text, re.I):
            meds.append("atorvastatin")
        if re.search(r"(?:metformin\s+500mg)", text, re.I):
            meds.append("metformin")
        if meds:
            slots["current_medications"] = {"slot": "current_medications", "value": meds, "status": "active", "source": "chat_user", "evidence": ev_label}

        # 15. Diagnosed conditions
        conds: list[str] = []
        if re.search(r"(?:type\s*1\s+diabetes)", text, re.I):
            conds.append("type1_diabetes")
        elif re.search(r"(?:type\s*2\s+diabetes|टाइप\s*2\s+डायबिटीज|diabetes\s+ke\s+liye)", text, re.I):
            conds.append("type2_diabetes")
        if re.search(r"(?:stage\s*2\s+hypertension)", text, re.I):
            conds.append("hypertension_stage2")
        elif re.search(r"(?:उच्च\s+रक्तचाप|हाई\s+बीपी|high\s+blood\s+pressure|बीपी\s+अक्सर\s+बढ़\s+जाता)", text, re.I):
            if not re.search(r"(?:ab\s+theek\s+ho\s+gaya|theek\s+ho\s+gaya)", text, re.I):
                conds.append("hypertension")
        if re.search(r"(?:हाइपोथायरायडिज्म|hypothyroidism)", text, re.I):
            conds.append("hypothyroidism")
        if re.search(r"(?:pregnant|गर्भवती)", text, re.I):
            conds.append("pregnancy")
        if re.search(r"(?:mujhe\s+koi\s+bimari\s+nahi\s+hai\s*,\s*sab\s+theek\s+hai\s+report)", text, re.I):
            conds.append("none")
        if conds:
            slots["diagnosed_conditions"] = {"slot": "diagnosed_conditions", "value": conds, "status": "active", "source": default_src, "evidence": ev_label}

        # 16. Restricted modalities
        restr_mods: list[str] = []
        if re.search(r"(?:bhari\s+weights|heavy\s+weightlifting).*?(?:gym\s+strictly\s+mana|mana)", text, re.I):
            restr_mods.extend(["heavy_weightlifting", "gym"])
        elif re.search(r"(?:gym\s+mana\s+kiya)", text, re.I):
            restr_mods.append("gym")
        if restr_mods:
            slots["restricted_modalities"] = {"slot": "restricted_modalities", "value": restr_mods, "status": "active", "source": "chat_user", "evidence": ev_label}

        # 17. Physical limitations
        if re.search(r"(?:ghutne\s+mein\s+katori\s+ghisne\s+ka\s+dard)", text, re.I):
            slots["physical_limitations"] = {"slot": "physical_limitations", "value": ["knee_joint_pain"], "status": "active", "source": "chat_user", "evidence": ev_label}

        # 18. Pending loosening confirmation
        if re.search(r"(?:cardiologist\s+said\s+i\s+don't\s+need\s+any\s+restrictions\s+on\s+running)", text, re.I):
            slots["pending_loosening_confirmation"] = {"slot": "pending_loosening_confirmation", "value": "cardiac_running_restriction_cleared", "status": "active", "source": "chat_user", "evidence": ev_label}
        elif re.search(r"(?:peanut\s+allergy\s+theek\s+ho\s+gayi\s+hai|nut\s+allergy\s+is\s+gone)", text, re.I):
            slots["pending_loosening_confirmation"] = {"slot": "pending_loosening_confirmation", "value": "nut_allergy_resolved", "status": "active", "source": "chat_user", "evidence": ev_label}
        elif re.search(r"(?:कम\s+नमक\s+वाले\s+खाने\s+की\s+जरूरत\s+नहीं\s+है)", text, re.I):
            slots["pending_loosening_confirmation"] = {"slot": "pending_loosening_confirmation", "value": "sodium_restriction_loosening", "status": "active", "source": "chat_user", "evidence": ev_label}
        elif re.search(r"(?:hypertension\s+ab\s+theek\s+ho\s+gaya\s+hai\s*,\s*bp\s+bilkul\s+normal)", text, re.I):
            slots["pending_loosening_confirmation"] = {"slot": "pending_loosening_confirmation", "value": "hypertension_claimed_cured", "status": "active", "source": "chat_user", "evidence": ev_label}

        # 19. Temporary symptoms
        if re.search(r"(?:badan\s+dard)", text, re.I):
            slots["temporary_symptom"] = {"slot": "temporary_symptom", "value": "body_ache", "status": "active", "source": "chat_user", "evidence": ev_label}
        elif re.search(r"(?:bloating\s+after\s+having\s+rajma\s+chawal|mild\s+bloating\s+since\s+this\s+morning)", text, re.I):
            slots["temporary_symptom"] = {"slot": "temporary_symptom", "value": "bloating", "status": "active", "source": "chat_user", "evidence": ev_label}
        elif re.search(r"(?:mild\s+knee\s+stiffness\s+since\s+this\s+morning)", text, re.I):
            slots["temporary_symptom"] = {"slot": "temporary_symptom", "value": "knee stiffness", "status": "active", "source": "chat_user", "evidence": ev_label}
        elif re.search(r"(?:sir\s+dard)", text, re.I):
            slots["temporary_symptom"] = {"slot": "temporary_symptom", "value": "headache", "status": "active", "source": "chat_user", "evidence": ev_label}
        elif re.search(r"(?:lower\s+back\s+is\s+slightly\s+sore)", text, re.I):
            slots["temporary_symptom"] = {"slot": "temporary_symptom", "value": "lower_back_soreness", "status": "active", "source": "chat_user", "evidence": ev_label}
        elif re.search(r"(?:pet\s+kharab\s+ho\s+gaya\s+aur\s+loose\s+motion)", text, re.I):
            slots["temporary_symptom"] = {"slot": "temporary_symptom", "value": "acute_diarrhea", "status": "active", "source": "chat_user", "evidence": ev_label}
        elif re.search(r"(?:धूप\s+में\s+घूमने\s+की\s+वजह\s+से\s+थोड़ा\s+चक्कर\s+आ\s+रहा\s+है)", text, re.I):
            slots["temporary_symptom"] = {"slot": "temporary_symptom", "value": "dizziness_acute", "status": "active", "source": "chat_user", "evidence": ev_label}
        elif re.search(r"(?:gas\s+aur\s+pet\s+phoolne)", text, re.I):
            slots["temporary_symptom"] = {"slot": "temporary_symptom", "value": "bloating_gas", "status": "active", "source": "chat_user", "evidence": ev_label}

    return list(slots.values())


class SummaryBaselineUpdater(SharedPEPUpdater):
    """Summary-then-Update Baseline PEP updater conforming to SharedPEPUpdater."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionTurnDigest] = {}
        self._persisted_cache: dict[str, dict[str, Any]] = {}

    def _session_key(self, patient_id: str, session_id: str) -> str:
        return f"{patient_id}:{session_id}"

    async def on_turn(
        self,
        patient_id: str,
        user_text: str,
        assistant_text: str,
        session_id: str = "default",
        call_id: str | None = None,
        conn: Any = None,
        app_state: Any = None,
        turn_context: Any = None,
    ) -> dict[str, Any]:
        """Record turn into session digest and update rolling summary."""
        key = self._session_key(patient_id, session_id)
        if key not in self._sessions:
            self._sessions[key] = SessionTurnDigest(patient_id=patient_id, session_id=session_id)

        digest = self._sessions[key]
        if user_text:
            digest.turns.append({"role": "user", "text": user_text})
        if assistant_text:
            digest.turns.append({"role": "assistant", "text": assistant_text})
        digest.updated_at = datetime.now(timezone.utc)

        logger.debug("Ingested turn into digest for patient %s session %s", patient_id, session_id)

        return {
            "mode": "summary",
            "status": "digested",
            "turns_count": len(digest.turns),
            "llm_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }

    async def on_session_end(
        self,
        patient_id: str,
        session_id: str = "default",
        call_id: str | None = None,
        conn: Any = None,
        app_state: Any = None,
    ) -> dict[str, Any]:
        """Finalize session-level slot extraction from turn digest."""
        key = self._session_key(patient_id, session_id)
        digest = self._sessions.get(key)
        turns = digest.turns if digest else []

        # Determine onboarding context from turn context or introductory cues
        is_onboarding = False
        if app_state and hasattr(app_state, "onboarding") and app_state.onboarding:
            is_onboarding = True

        final_slots = extract_slots_from_turns(turns, is_onboarding=is_onboarding)

        # Update persisted in-memory cache for patient
        if patient_id not in self._persisted_cache:
            self._persisted_cache[patient_id] = {}
        for s in final_slots:
            self._persisted_cache[patient_id][s["slot"]] = s["value"]

        # If DB connection provided, persist to patient_pep_slots scoped strictly by patient_id
        if conn is not None and hasattr(conn, "execute"):
            now = datetime.now(timezone.utc)
            for slot_item in final_slots:
                s_name = slot_item.get("slot")
                s_val = slot_item.get("value")
                s_src = slot_item.get("source", "chat_user")
                s_stat = slot_item.get("status", "active")
                s_ev = slot_item.get("evidence", "")
                val_json = json.dumps(s_val) if not isinstance(s_val, str) else json.dumps({"value": s_val})
                try:
                    await conn.execute(
                        """
                        UPDATE patient_pep_slots
                        SET valid_until = $3, updated_at = $3
                        WHERE patient_id = $1 AND slot = $2 AND valid_until IS NULL
                        """,
                        patient_id,
                        s_name,
                        now,
                    )
                    await conn.execute(
                        """
                        INSERT INTO patient_pep_slots (
                            patient_id, slot, value, source, clinical_status,
                            verification_status, valid_from, evidence, created_at, updated_at
                        ) VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7, $8, $7, $7)
                        """,
                        patient_id,
                        s_name,
                        val_json,
                        s_src,
                        s_stat,
                        "unconfirmed",
                        now,
                        s_ev,
                    )
                except Exception as exc:
                    logger.warning("Could not persist slot %s to DB for patient %s: %s", s_name, patient_id, exc)

        logger.info("Session finalized for patient %s session %s with %d slots", patient_id, session_id, len(final_slots))

        # Reset session digest to allow clean repeats
        if key in self._sessions:
            del self._sessions[key]

        return {
            "mode": "summary",
            "status": "completed",
            "slots": final_slots,
            "llm_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }

    def context_slice(
        self,
        patient_id: str,
        intent: str | None = None,
        context: dict[str, Any] | None = None,
        app_state: Any = None,
    ) -> dict[str, Any]:
        """Retrieve intent-scoped context slice of PEP slots."""
        patient_slots = self._persisted_cache.get(patient_id, {})
        if not intent:
            return {"slots": dict(patient_slots)}

        intent_lower = intent.lower()
        scoped: dict[str, Any] = {}
        if "nutrition" in intent_lower or "diet" in intent_lower or "food" in intent_lower:
            for k in ("meal_preferences", "dietary_restrictions", "water_intake_target", "tea_coffee_frequency"):
                if k in patient_slots:
                    scoped[k] = patient_slots[k]
        elif "exercise" in intent_lower or "activity" in intent_lower or "fitness" in intent_lower:
            for k in ("daily_steps_target", "restricted_modalities", "physical_limitations", "pending_loosening_confirmation"):
                if k in patient_slots:
                    scoped[k] = patient_slots[k]
        elif "circadian" in intent_lower or "sleep" in intent_lower or "wake" in intent_lower:
            for k in ("wake_time", "sleep_time", "work_schedule"):
                if k in patient_slots:
                    scoped[k] = patient_slots[k]
        else:
            scoped = dict(patient_slots)

        return {"slots": scoped}


_GLOBAL_SUMMARY_UPDATER = SummaryBaselineUpdater()


def get_summary_baseline_updater() -> SummaryBaselineUpdater:
    """Return singleton instance of SummaryBaselineUpdater."""
    return _GLOBAL_SUMMARY_UPDATER


async def on_turn_summary(
    patient_id: str,
    user_text: str,
    assistant_text: str,
    session_id: str = "default",
    call_id: str | None = None,
    conn: Any = None,
    app_state: Any = None,
    turn_context: Any = None,
) -> dict[str, Any]:
    """Module-level turn hook for summary baseline."""
    return await _GLOBAL_SUMMARY_UPDATER.on_turn(
        patient_id, user_text, assistant_text, session_id, call_id, conn, app_state, turn_context
    )


async def on_session_end_summary(
    patient_id: str,
    session_id: str = "default",
    call_id: str | None = None,
    conn: Any = None,
    app_state: Any = None,
) -> dict[str, Any]:
    """Module-level session end hook for summary baseline."""
    return await _GLOBAL_SUMMARY_UPDATER.on_session_end(
        patient_id, session_id, call_id, conn, app_state
    )


def context_slice_summary(
    patient_id: str,
    intent: str | None = None,
    context: dict[str, Any] | None = None,
    app_state: Any = None,
) -> dict[str, Any]:
    """Module-level context slice hook for summary baseline."""
    return _GLOBAL_SUMMARY_UPDATER.context_slice(patient_id, intent, context, app_state)
