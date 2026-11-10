#!/usr/bin/env python3
"""Migrate red-flag and crisis rules into clinician-owned data table (data/red_flags.yaml).

Per DPDP Act Section 8 and Telemedicine Practice Guidelines (2020).
"""

import json
import unicodedata
from pathlib import Path

import yaml

from disha_core.pipeline.breaker import EMERGENCY_PATTERNS, EMERGENCY_SCRIPTS


def is_deva(s: str) -> bool:
    return any("DEVANAGARI" in unicodedata.name(c, "") for c in s)


hinglish_indicators = {
    "mein",
    "me",
    "dard",
    "dabaav",
    "dabav",
    "bhaari",
    "bhari",
    "dil",
    "daura",
    "pada",
    "ruk",
    "dhadkan",
    "band",
    "nahi",
    "mil",
    "rahi",
    "chaati",
    "chhati",
    "seene",
    "saans",
    "saas",
    "lene",
    "dikkat",
    "takleef",
    "taklif",
    "phool",
    "dum",
    "ghut",
    "raha",
    "hoth",
    "neele",
    "bilkul",
    "atak",
    "gale",
    "khana",
    "achanak",
    "behosh",
    "chehra",
    "tedha",
    "bol",
    "pa",
    "ek",
    "taraf",
    "kamzori",
    "latak",
    "gaya",
    "ho",
    "lakwa",
    "mar",
    "mirgi",
    "zubaan",
    "ladkhada",
    "jhatke",
    "lag",
    "khudkushi",
    "jaan",
    "dena",
    "chahta",
    "apne",
    "aap",
    "ko",
    "maar",
    "zeher",
    "kha",
    "liya",
    "apni",
    "nasein",
    "kaat",
    "faansi",
    "faasi",
    "neend",
    "ki",
    "goliyan",
    "sari",
    "keede",
    "maarne",
    "wali",
    "dawa",
    "kood",
    "bahut",
    "khoon",
    "beh",
    "tez",
    "bada",
    "accident",
    "gehri",
    "chot",
    "ulti",
    "nikal",
    "goli",
    "chaku",
    "sar",
    "toot",
}


def classify_lang(phrase: str) -> str:
    if is_deva(phrase):
        return "hi"
    words = set(phrase.casefold().split())
    if words & hinglish_indicators:
        return "hinglish"
    return "en"


severities = {
    "CARDIOVASCULAR": "CRITICAL",
    "RESPIRATORY": "CRITICAL",
    "NEUROLOGICAL": "CRITICAL",
    "CRISIS": "EMERGENCY_CRISIS",
    "TRAUMA": "CRITICAL",
}

regex_definitions = {
    "CARDIOVASCULAR": [
        {
            "name": "spaced chest pain",
            "pattern": r"(?<!\w)c\s*h\s*h\s*a\s*t\s*i.{0,12}(?:d\s*a\s*r\s*d|d\s*a\s*b\s*a\s*v)(?!\w)",
        },
        {
            "name": "cardio regex",
            "pattern": r"\b(?:chhati|chaati|seene|chest|chst|dil|myocardial|angina|heart)\b.{0,35}?\b(?:dard|drd|daba+v|pressure|pain|attack|crushing|crushng|tightness|daura|infarction|pectoris|arrest|stopped)\b|\bcrush(?:ing|ng)\s+ch[e]?st\s+pain\b|\bleft\s+(?:hand|arm)\s+pain\b|\b(?:no|lost)\s+pulse\b|\bpulseless\b|(?:छाती|सीने|दिल|धड़कन).{0,35}?(?:दर्द|दबाव|दौरा|बंद|रुक)",
        },
    ],
    "RESPIRATORY": [
        {
            "name": "spaced breathing distress",
            "pattern": r"(?<!\w)s\s*a\s*a\s*n\s*s.{0,16}(?:n\s*a\s*h\s*i|r\s*u\s*k)(?!\w)",
        },
        {
            "name": "respiratory regex",
            "pattern": r"\b(?:saans|saas|sans|breath(?:e|ing)?|dum|respiratory)\b.{0,35}?\b(?:nahi|ni|takleef|taklif|dikkat|ruk|choking|choke|gasping|cannot|can't|cant|phool|ghut|distress|failure|atak)\b|\basthma\s+attack\b|\bsuffocating\b|\b(?:throat\s+is\s+closing|throat\s+closing|anaphylaxis|stridor|lips\s+turning\s+blue)\b|\b(?:oxygen|spo2)\b.{0,25}?\b(?:drop|gir|fall|low|kam)\b|सांस.{0,25}?(?:नहीं|रुक|फूल|दिक्कत|तकलीफ|बंद|अटक)|ऑक्सीजन.{0,20}?गिर",
        },
    ],
    "NEUROLOGICAL": [
        {
            "name": "neuro regex",
            "pattern": r"\b(?:chehra|chhra|face)\b.{0,30}?\b(?:tedha|droop|droping|latak)\b|\bslurred\s+(?:speech|spch)\b|\bparalyz(?:ed|is)\b|\bbol\s+nahi\s+pa\b|\bbehosh\b|\bunconscious\b|\bstroke\b|\blakwa\b|\bmirgi\b|\b(?:seizure|convuls(?:ing|ion)|epilep|status\s+epilepticus)\b|\bthunderclap(?:\s+headache)?\b|\bworst\s+headache\b|\bunresponsive\b|\bpassed\s+out\b|चेहरा.{0,20}?टेढ़ा|लकवा|बेहोश|अचेत|मिर्गी|जीवन\s+का\s+सबसे\s+(?:भयंकर|तेज|खराब)\s+सिरदर्द",
        }
    ],
    "CRISIS": [
        {
            "name": "crisis regex",
            "pattern": r"\bsuicide\b|\bkill\s+myself\b|\bend\s+my\s+life\b|\bself\s+harm\b|\bwant\s+to\s+die\b|\bkhudkushi\b|\bjaan\s+(?:dena|lena)\b|\bzeher\b|\bpoison\b|\bfaansi\b|\bfaasi\b|\b(?:overdose|sleeping\s+pills?|pesticide|rat\s+poison|cut(?:ting)?\s+(?:my\s+)?wrists?|hang(?:ing)?\s+myself)\b|\bneend\s+ki\s+.*goli|\b(?:tezaab|acid)\b.{0,20}?\b(?:pi|drank|pee)\b|आत्महत्या|खुदकुशी|ज़हर|फांसी|नींद\s+की.*गोली",
        }
    ],
    "TRAUMA": [
        {
            "name": "trauma regex",
            "pattern": r"\b(?:khoon|blood|internal|abdominal|acute|arterial|massive)\b.{0,30}?\b(?:ulti|vomit|beh|nikal|heavy|arterial|bleeding|hemorrhage|haemorrhage|loss)\b|\b(?:hypovolemic|septic|cardiogenic)\s+shock\b|\b(?:in\s+shock|patient\s+is\s+in\s+shock)\b|\bextensive\s+burns?\b|\bsevere\s+burns?\b|\bhead\s+injury\b|\bgoli\s+lag\b|\bchaku\s+lag\b|\b(?:bleeding\s+uncontrollably|stabbed|stab\s+wound|gunshot(?:\s+wound)?|coughing\s+(?:up\s+)?blood|hemoptysis|hematemesis)\b|\b(?:chaku|goli)\b.{0,25}?(?:lag|mar|lagi|mara)\b|खून\s+(?:की\s+उल्टी|बह|निकल)|चाकू|गोली",
        }
    ],
}

negations = {
    "CARDIOVASCULAR": [
        r"(?:do\s+not|don't|no)\s+(?:have|feel)\s+(?:any\s+)?(?:chest\s+pain|chest\s+pressure|heart\s+attack)",
        r"chhati\s+m(?:ein)?\s+koi\s+d(?:a)?rd\s+n(?:a)?hi",
        r"seene\s+m(?:ein|e)?\s+bilkul\s+dard\s+nahi",
        r"dil\s+ka\s+daura\s+nahi\s+pada",
        r"(?:छाती|सीने)\s+में\s+(?:कोई\s+)?दर्द\s+नहीं",
    ],
    "RESPIRATORY": [
        r"(?:do\s+not|don't|no)\s+(?:have|feel)\s+(?:any\s+)?(?:difficulty\s+breathing|shortness\s+of\s+breath)",
        r"not\s+having\s+any\s+breathing\s+trouble",
        r"saans\s+lene\s+m(?:ein)?\s+koi\s+dikkat\s+n(?:a)?hi",
        r"saans\s+phool\s+nahi\s+rahi",
        r"सांस\s+लेने\s+में\s+(?:कोई\s+)?(?:तकलीफ|दिक्कत)\s+नहीं",
    ],
    "NEUROLOGICAL": [
        r"does\s+not\s+have\s+(?:face\s+drooping|weakness)",
        r"patient\s+is\s+not\s+unconscious",
        r"chehra\s+tedha\s+nahi\s+hua",
        r"behosh\s+nahi\s+hua",
        r"चेहरा\s+टेढ़ा\s+नहीं\s+हुआ",
        r"बेहोश\s+नहीं\s+है",
    ],
    "CRISIS": [
        r"no\s+thoughts\s+of\s+suicide",
        r"suicide\s+ke\s+khayal\s+bilkul\s+n(?:a)?hi",
        r"आत्महत्या\s+का\s+कोई\s+विचार\s+नहीं",
    ],
    "TRAUMA": [r"no\s+active\s+bleeding", r"khoon\s+n(?:a)?hi\s+beh\s+r(?:a)?h(?:a)?", r"कोई\s+खून\s+नहीं\s+बह\s+रहा"],
}

exceptions = [
    {
        "id": "EXC_BLACKOUT_CURTAIN",
        "phrase": "blackout",
        "pattern": r"\bblackout\s+(?:curtains?|shades?|blinds?|drapes?|window)\b",
        "category": "NEUROLOGICAL",
        "description": "Benign home decor context",
    },
    {
        "id": "EXC_CHEST_PAINTING",
        "phrase": "chest",
        "pattern": r"\bchest\s+paint(?:ing|ings)?\b",
        "category": "CARDIOVASCULAR",
        "description": "Artistic painting or hobby",
    },
    {
        "id": "EXC_HEART_PILLOW",
        "phrase": "heart",
        "pattern": r"\bheart-?shaped\s+pillow\b",
        "category": "CARDIOVASCULAR",
        "description": "Heart shaped object or pillow",
    },
]


def main() -> None:
    categories_data = {}
    for cat, phrases in EMERGENCY_PATTERNS.items():
        terms_by_lang = {"en": [], "hinglish": [], "hi": []}
        for p in phrases:
            lang = classify_lang(p)
            terms_by_lang[lang].append(p)
        categories_data[cat] = {
            "severity": severities[cat],
            "protocol_text": EMERGENCY_SCRIPTS[cat],
            "languages": ["en", "hi", "hinglish"],
            "scripts": ["Latn", "Deva"],
            "terms": terms_by_lang,
            "regex_patterns": regex_definitions.get(cat, []),
            "negation_patterns": negations.get(cat, []),
        }

    root = {
        "version": "1.0.0",
        "metadata": {
            "table_name": "clinician_emergency_red_flags",
            "owner": "Chief Medical Officer / Clinical Safety Committee",
            "last_reviewed": "2026-11-09",
            "description": "Clinician-owned emergency red flag and crisis lexicon, negation rules, and response protocols per DPDP Act Section 8 and Telemedicine Practice Guidelines",
            "compliance": [
                "DPDP Act 2023 Section 8 (Security Safeguards & Emergency Interception)",
                "Telemedicine Practice Guidelines 2020 (Mandatory Acute Triage Protocol)",
                "Mental Healthcare Act 2017 (Tele-MANAS Crisis Escalation 14416)",
            ],
            "default_protocol_text": "Yeh emergency ho sakti hai. Abhi 112 par call karein ya kisi paas ke vyakti se call karne ko kahein.",
        },
        "exceptions": exceptions,
        "categories": categories_data,
    }

    out_yaml = Path("data/red_flags.yaml")
    out_yaml.parent.mkdir(parents=True, exist_ok=True)
    with open(out_yaml, "w", encoding="utf-8") as f:
        yaml.dump(root, f, allow_unicode=True, sort_keys=False, indent=2)

    out_json = Path("data/red_flags.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(root, f, ensure_ascii=False, indent=2)

    print(f"Generated {out_yaml} and {out_json}")


if __name__ == "__main__":
    main()
