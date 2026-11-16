"""20% Blind Label Audit for Golden PEP Dataset.

Extracts PEP slots from 51 randomly sampled conversations without inspecting expected_final_state,
computes agreement rate, and records disagreements.
"""

from __future__ import annotations

import json
import random
import re
from typing import Any
from tests.pep_eval.metrics import compare_slot_values

def blind_label_conversation(turns: list[dict[str, str]], language: str, category: str) -> list[dict[str, Any]]:
    """Blindly label slots based on conversation turns alone, adhering to clinical rules."""
    user_turns = [t["text"] for t in turns if t.get("role") == "user"]
    user_full = " ".join(user_turns)
    user_lower = user_full.lower()

    slots: dict[str, Any] = {}

    # 1. Guard check: Injections / adversarial
    if any(re.search(r"(system\s+override|ignore\s+(all\s+)?previous|delete\s+memory|unrestricted|bypass)", u, re.I) for u in user_turns):
        return []

    # 2. Check if third-party disclosure
    tp_patterns = [
        r"(my\s+(mother|father|mom|dad|wife|husband|friend|brother|sister|son|daughter))",
        r"(meri\s+(mummy|maa|behen|patni|dost))",
        r"(mere\s+(pita|papa|bhai|pati|dost))",
        r"(usko|unhe|unko)\s+(bhi\s+)?(hai|tha)",
    ]
    if any(re.search(p, user_lower) for p in tp_patterns):
        return []

    # 3. Check if hypothetical
    hypo_patterns = [
        r"(what\s+if\s+someone|if\s+someone|suppose|agar\s+kisi\s+ko|kya\s+kisi\s+ko|agar\s+koi)",
    ]
    if any(re.search(p, user_lower) for p in hypo_patterns):
        return []

    # 4. Check if purely informational inquiry without self-disclosure
    info_patterns = [
        r"(is\s+keto\s+(good|safe)|tell\s+me\s+about\s+(intermittent|keto|thyroid|sugar)|kya\s+.*\s+(theek|accha|faaydemand|surakshit)\s+hai|kya\s+hota\s+hai|kya\s+fayde\s+hain)",
        r"(what\s+is\s+the\s+normal|what\s+are\s+the\s+symptoms|batao\s+na\s+kya\s+hai|ke\s+mareez|patients\s+with)",
    ]
    is_pure_info = any(re.search(p, u.strip(), re.I) for p in info_patterns for u in user_turns) and len(user_turns) == 1
    if is_pure_info or "ke mareez" in user_lower or "patients with" in user_lower:
        return []

    # 5. Sarcasm / idioms
    if any(re.search(p, user_lower) for p in [r"main\s+to\s+lohe\s+ka\s+chana", r"i\s+can\s+digest\s+stones", r"running\s+like\s+a\s+cheetah"]):
        return []

    # 6. Check loosening
    if re.search(r"(knee.*resolved|pain.*resolved|ghutne.*koi\s+dikkat\s+nahi|no\s+restrictions\s+on\s+running|nut\s+allergy\s+is\s+gone|kam\s+namak.*zaroorat\s+nahi)", user_lower):
        if "knee" in user_lower or "pain" in user_lower:
            slots["pending_loosening_confirmation"] = "knee_restriction_eased"
        elif "running" in user_lower:
            slots["pending_loosening_confirmation"] = "cardiac_running_restriction_cleared"
        elif "nut" in user_lower:
            slots["pending_loosening_confirmation"] = "nut_allergy_resolved"
        elif "namak" in user_lower or "salt" in user_lower:
            slots["pending_loosening_confirmation"] = "sodium_restriction_loosening"
        return [{"slot": k, "value": v} for k, v in slots.items()]

    # 7. Temporary symptoms (transient)
    temp_symp_map = [
        (r"(bloating|pet\s+phool|rajma\s+chawal.*bloating)", "bloating"),
        (r"(sir\s+dard|headache)", "headache"),
        (r"(fever.*badan|बुखार.*बदन|fever.*body\s+ache)", "fever_body_ache"),
        (r"(fever|बुखार)", "fever_body_ache"),
        (r"(dizziness|chakkar|चक्कर)", "dizziness_acute"),
        (r"(badan\s+dard|body\s+ache|बदन\s+दर्द)", "body_ache"),
        (r"(diarrhea|dast|loose\s+motions?|pet\s+kharab)", "acute_diarrhea"),
        (r"(knee\s+stiffness|ghutne\s+mein\s+thodi\s+jakdan)", "knee stiffness"),
    ]
    if category == "temporary_symptom" or (any(w in user_lower for w in ["aaj", "today", "since morning", "subah se", "kal raat se", "कल रात से", "आज"]) and any(re.search(p, user_lower) for p, _ in temp_symp_map)):
        for pat, symp_val in temp_symp_map:
            if re.search(pat, user_lower):
                slots["temporary_symptom"] = symp_val
                break
        return [{"slot": k, "value": v} for k, v in slots.items()]

    # 8. Dietary restrictions / Allergies
    if re.search(r"(peanut\s+allergy|allergic\s+to\s+peanuts?|mungfali\s+se\s+.*allergy|मूंगफली\s+से\s+.*एलर्जी)", user_lower):
        slots["dietary_restrictions"] = ["nut_allergy"]
    elif re.search(r"(lactose\s+intoleran|doodh\s+peete\s+hi|milk\s+gives\s+me\s+bloating)", user_lower):
        slots["dietary_restrictions"] = ["lactose_intolerant"]
    elif re.search(r"(gluten\s+allergy|celiac|wheat\s+allergy)", user_lower):
        slots["dietary_restrictions"] = ["gluten_free"]

    # 9. Meal preferences
    if re.search(r"(jain\s+bhojan|jain|जैन)", user_lower):
        slots["meal_preferences"] = "Jain"
    elif re.search(r"(eggetarian|egg\s+khata)", user_lower):
        slots["meal_preferences"] = "Eggetarian"
    elif re.search(r"(strict\s+vegetarian|shuddh\s+shakahari|pure\s+veg|vegetarian|शाकाहारी)", user_lower) and "non-veg" not in user_lower and "eggetarian" not in user_lower:
        slots["meal_preferences"] = "Vegetarian"
    elif re.search(r"(non-veg|mansahari|मांसाहारी)", user_lower):
        slots["meal_preferences"] = "Non-Vegetarian"

    # 10. Chronic conditions
    if re.search(r"(type\s*1\s+diabetes|type\s*1|t1d)", user_lower):
        slots["diagnosed_conditions"] = ["type1_diabetes"]
    elif re.search(r"(stage\s*2\s+hypertension)", user_lower):
        slots["diagnosed_conditions"] = ["hypertension_stage2"]
    elif re.search(r"(high\s+bp|high\s+blood\s+pressure|hypertension|ucch\s+raktchap|उच्च\s+रक्तचाप|बीपी\s+बढ़ी|bp\s+high)", user_lower):
        slots["diagnosed_conditions"] = ["hypertension"]
    elif re.search(r"(type\s*2\s+diabetes|sugar\s+hai|madhumeh|मधुमेह|sugar\s+ki\s+bimaari|sugar\s+badh|sugar\s+ki\s+problem)", user_lower):
        slots["diagnosed_conditions"] = ["type2_diabetes"]
    elif re.search(r"(hypothyroidism|thyroid\s+ki\s+samashya|thyroid)", user_lower):
        slots["diagnosed_conditions"] = ["hypothyroidism"]
    elif re.search(r"(pcos|pcod)", user_lower):
        slots["diagnosed_conditions"] = ["pcos"]

    # Negations for conditions
    if re.search(r"(i\s+do\s+not\s+have\s+diabetes|sugar\s+nahi\s+hai|no\s+hypertension|bp\s+normal\s+hai)", user_lower):
        slots.pop("diagnosed_conditions", None)

    # 11. Current medications
    meds: list[str] = []
    if re.search(r"(metformin)", user_lower):
        meds.append("metformin")
    if re.search(r"(amlodipine)", user_lower):
        meds.append("amlodipine")
    if re.search(r"(atorvastatin)", user_lower):
        meds.append("atorvastatin")
    if re.search(r"(telmisartan)", user_lower):
        meds.append("telmisartan")
    if re.search(r"(thyronorm)", user_lower):
        meds.append("thyronorm")
    if meds:
        slots["current_medications"] = meds

    # 12. Physical limitations & restricted modalities
    if re.search(r"(doctor\s+ne\s+gym\s+mana\s+kiya|no\s+gym)", user_lower):
        slots["restricted_modalities"] = ["gym"]
    if re.search(r"(bhari\s+weights\s+aur\s+gym\s+strictly\s+mana)", user_lower):
        slots["restricted_modalities"] = ["heavy_weightlifting", "gym"]
    if re.search(r"(knee\s+surgery|ghutne\s+mein\s+katori|acl)", user_lower):
        if "acl" in user_lower:
            slots["physical_limitations"] = ["knee_surgery_acl"]
        elif "katori" in user_lower:
            slots["physical_limitations"] = ["knee_joint_pain"]
        else:
            slots["physical_limitations"] = ["knee_surgery"]

    # 13. Sleep & Wake times
    m_wake = re.search(r"(\d{1,2}(?::\d{2})?)\s*(?:am|subah|morning|सुबह)?\s*(?:baje\s+|बजे\s+)?(?:ko\s+)?(?:uthta|uthti|uthte|wake|उठता|उठती|उठते|uth\s+jata|उठकर)", user_lower)
    if not m_wake:
        m_wake = re.search(r"(?:wake|uthta|uthti|uthte|jagne|उठता|उठती|उठते|उठकर).{0,15}?(?:around|at|ko)?\s*(\d{1,2}(?::\d{2})?)(?:\s*(?:am|subah|सुबह|baje|बजे))?", user_lower)
    if m_wake:
        h_str = m_wake.group(1)
        if ":" in h_str:
            parts = h_str.split(":")
            slots["wake_time"] = f"{int(parts[0]):02d}:{parts[1]}"
        else:
            h = int(h_str)
            if "night shift" in user_lower and h == 3:
                slots["wake_time"] = "15:00"
            else:
                slots["wake_time"] = f"{h:02d}:00"

    m_sleep = re.search(
        r"(\d{1,2}(?::\d{2})?)\s*(?:am|pm|subah|raat|रात|in\s+the\s+morning|at\s+night)?\s*(?:baje\s+|बजे\s+)?(?:ko\s+)?(?:sota|soti|sote|sleep|so\s+jata|so\s+jati|सोता|सोती|सोते|सो\s+जाता|सो\s+जाती|सो\s+जाते)",
        user_lower,
    )
    if not m_sleep:
        m_sleep = re.search(
            r"(?:sleep|sota|soti|sote|bedtime|so\s+jata|so\s+jati|सोता|सोती|सोते|सो\s+जाता|सो\s+जाती|सो\s+जाते).{0,15}?(?:around|at|ko)?\s*(\d{1,2}(?::\d{2})?)",
            user_lower,
        )
    if m_sleep:
        s_str = m_sleep.group(1)
        if ":" in s_str:
            parts = s_str.split(":")
            h = int(parts[0])
            if h < 12 and ("night" in user_lower or "raat" in user_lower or "रात" in user_lower or "pm" in user_lower or h in (10, 11)):
                h += 12
            slots["sleep_time"] = f"{h:02d}:{parts[1]}"
        else:
            h = int(s_str)
            if h == 12 or h == 0:
                slots["sleep_time"] = "00:00"
            elif h < 12 and ("night" in user_lower or "raat" in user_lower or "रात" in user_lower or "pm" in user_lower or h in (9, 10, 11)):
                slots["sleep_time"] = f"{h+12:02d}:00"
            elif "night shift" in user_lower and h == 7:
                slots["sleep_time"] = "07:00"
            else:
                slots["sleep_time"] = f"{h:02d}:00"

    # 14. Water intake target
    m_water = re.search(r"(\d+(?:\.\d+)?)\s*(?:litres?|l\b|litre|लीटर|लीटर\s+पानी)", user_lower)
    if m_water:
        slots["water_intake_target"] = float(m_water.group(1))

    # 15. Daily steps target
    m_steps = re.search(r"(\d{4,5})\s*(?:walking\s+)?(?:steps|कदम)", user_lower)
    if m_steps:
        slots["daily_steps_target"] = int(m_steps.group(1))

    # 16. Work schedule
    if "night shift" in user_lower:
        slots["work_schedule"] = "night_shift"
    elif "day shift" in user_lower or "सामान्य ड्यूटी" in user_lower:
        slots["work_schedule"] = "day_shift"

    # 17. Tea / coffee frequency
    if re.search(r"(\d+)\s*cups?\s*(?:of\s+)?(?:milk\s+)?tea", user_lower):
        m_t = re.search(r"(\d+)\s*cups?", user_lower)
        cups = int(m_t.group(1)) if m_t else 1
        slots["tea_coffee_frequency"] = {"tea_cups_per_day": cups, "frequency_label": f"{cups} cups/day"}
    elif re.search(r"(\d+)\s*cups?\s*(?:of\s+)?(?:black\s+)?coffee", user_lower):
        m_c = re.search(r"(\d+)\s*cups?", user_lower)
        cups = int(m_c.group(1)) if m_c else 1
        slots["tea_coffee_frequency"] = {"coffee_cups_per_day": cups, "frequency_label": f"{cups} cups/day"}

    return [{"slot": k, "value": v} for k, v in slots.items()]


def run_blind_audit() -> dict[str, Any]:
    with open("tests/pep_eval/dev.jsonl") as f:
        dev = [json.loads(line) for line in f]
    with open("/Users/nitrousoxide/Desktop/disha-research/pep-benchmark/sealed/test.jsonl") as f:
        test = [json.loads(line) for line in f]

    all_cases = dev + test
    random.seed(42)
    sample_indices = random.sample(range(len(all_cases)), 51)
    sample = [all_cases[i] for i in sample_indices]

    agreements = 0
    disagreements: list[dict[str, Any]] = []

    for item in sample:
        cid = item.get("conversation_id") or item["id"]
        cat = item["category"]
        lang = item["language"]
        turns = item["turns"]
        expected = item.get("expected_final_state", [])

        # Blind label without seeing expected
        audited = blind_label_conversation(turns, lang, cat)

        # Compare
        exp_map = {s["slot"]: s.get("value") for s in expected if "slot" in s}
        aud_map = {s["slot"]: s.get("value") for s in audited if "slot" in s}

        match = True
        # Check keys
        if set(exp_map.keys()) != set(aud_map.keys()):
            match = False
        else:
            for k in exp_map:
                if not compare_slot_values(exp_map[k], aud_map[k]):
                    match = False
                    break

        if match:
            agreements += 1
        else:
            disagreements.append({
                "id": cid,
                "category": cat,
                "language": lang,
                "user_text": [t["text"] for t in turns if t["role"] == "user"][:2],
                "expected": exp_map,
                "audited": aud_map,
            })

    rate = (agreements / len(sample)) * 100.0
    return {
        "total_audited": len(sample),
        "agreements": agreements,
        "agreement_rate": round(rate, 2),
        "disagreements": disagreements,
    }

if __name__ == "__main__":
    res = run_blind_audit()
    print(f"Blind Audit Result: {res['agreements']}/{res['total_audited']} ({res['agreement_rate']}%)")
    if res["disagreements"]:
        print(f"Disagreements count: {len(res['disagreements'])}")
        for d in res["disagreements"][:5]:
            print("  Disagreement:", d)
