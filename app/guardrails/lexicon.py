"""
Emergency Red-Flag Lexicon and Triage Responses.
Includes standard medical terminology and colloquial Hinglish regional idioms.
"""

# Categorized Emergency Patterns (English + Hinglish + Colloquial Variants)
EMERGENCY_PATTERNS = {
    "cardiovascular": [
        # Standard chest pain & discomfort (with optional intensifiers: bahut, tez, severe)
        r"\b(chest\s+(?:(?:severe|sharp|heavy|tight)\s+)?(?:pain|pressure|tightness|discomfort)|heavy\s+chest|cardiac\s+arrest)\b",
        r"\b((?:seene|chhati)\s+(?:mein|pe)\s+(?:(?:bahut|tez|badi|halka)\s+)?(?:dard|dabav|bojh|jalan|ghutan)|dil\s+ka\s+daura)\b",
        # Left arm/hand numbness & pain (including colloquial 'ulta haath')
        r"\b(left\s+arm\s+(pain|numb|heavy)|left\s+hand\s+(numb|pain)|baaye\s+haath\s+mein\s+dard)\b",
        r"\b(ulta\s+haath\s+sunn|baayan\s+baazu\s+bhari|haath\s+sunn\s+pad)\b",
        # Radiation to jaw/shoulder
        r"\b(pain\s+radiating\s+to\s+(jaw|shoulder|neck)|jabde\s+tak\s+dard)\b",
        r"\b(dil\s+mein\s+ghutan|chhati\s+mein\s+tez\s+jalan\s+aur\s+dard)\b"
    ],
    "respiratory": [
        r"\b(shortness\s+of\s+breath|difficulty\s+breathing|cannot\s+breathe|gasping|choking)\b",
        r"\b(saans\s+(phool|lene\s+mein\s+takleef|nahi\s+aa\s+rahi|ruk\s+rahi)|dam\s+ghut\s+raha)\b",
        r"\b(blue\s+lips|honth\s+neele)\b"
    ],
    "neurological": [
        r"\b(stroke|facial\s+droop|slurred\s+speech|sudden\s+weakness|paralysis)\b",
        r"\b(bolne\s+mein\s+(dikkat|ladkhadahat)|chehra\s+tedha|aadha\s+shareer\s+sunn)\b",
        r"\b(fainted|loss\s+of\s+consciousness|unconscious|behosh|chakkar\s+aake\s+gir)\b"
    ],
    "obstetric": [
        r"\b(heavy\s+vaginal\s+bleeding|bahut\s+zyada\s+bleeding|severe\s+pelvic\s+pain)\b"
    ],
    "psychiatric": [
        r"\b(suicide|suicidal|want\s+to\s+die|kill\s+myself|self\s+harm)\b",
        r"\b(marne\s+ka\s+mann|jaan\s+dena|khud\s+ko\s+chot)\b"
    ]
}

# Standardized, clinician-scripted emergency triage responses (Hinglish audio scripts)
EMERGENCY_TRIAGE_SCRIPTS = {
    "cardiovascular": (
        "Yeh symptoms serious ho sakte hain. Kripya turant exercise ya physical activity band karein, "
        "aaram se baith jayein aur bina deri kiye emergency ambulance (112) ya najdeeki hospital se consult karein. "
        "Humari care team ko alert bhej diya gaya hai, lekin kripya callback ka intezar na karein aur turant emergency help lein."
    ),
    "respiratory": (
        "Saans lene mein takleef ek medical emergency ho sakti hai. Kripya seedhe baithiye, taazi hawa lein "
        "aur turant emergency helpline 112 par call karein ya paas ke hospital ke emergency ward jayein. "
        "Hum aapki care team ko alert kar rahe hain."
    ),
    "neurological": (
        "Yeh neurological emergency ke lakshan ho sakte hain. Kripya kisi ko paas bulayein, aaram karein "
        "aur turant emergency hospital consult karein ya 112 par call karein. Hum aapke emergency contact ko inform kar rahe hain."
    ),
    "psychiatric": (
        "Aapki jaan bahut keemti hai aur aap akele nahi hain. Kripya turant national mental health helpline "
        "KIRAN (1800-599-0019) ya Tele-MANAS (14416) par baat karein. Hum aapki care team ko inform kar rahe hain."
    ),
    "general": (
        "Yeh symptoms serious ho sakte hain. Kripya turant kisi emergency doctor ya najdeeki hospital se consult karein, "
        "ya emergency helpline 112 par call karein."
    )
}
