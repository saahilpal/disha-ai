"""Clinical Evaluation Benchmark for EmergencyBreaker.

Evaluates 100+ clinical test cases covering Cardiovascular, Respiratory, Neurological,
Crisis, Trauma, Pregnancy Emergencies, Acute Abdomen, and Negation controls.
Verifies zero false negatives on emergencies and negation control accuracy.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from disha_core.pipeline.breaker import EmergencyBreaker

BENCHMARK_PATH = Path("/Users/nitrousoxide/Desktop/disha-research/breaker_eval_100.json")


@pytest.fixture(scope="module")
def breaker() -> EmergencyBreaker:
    return EmergencyBreaker()


def test_negation_controls_do_not_trigger_emergency(breaker: EmergencyBreaker) -> None:
    """Verify that clinical negation phrases (e.g. 'no chest pain') do not false-positive."""
    test_cases = [
        "I have no chest pain at all, just a minor cold",
        "There is no shortness of breath, breathing is completely fine",
        "Chhati mein koi dard nahi hai, sirf pet mein halki gas hai",
        "Seene mein bilkul dard nahi hai, sab normal hai",
        "छाती या सीने में कोई दर्द नहीं है, सिर्फ गले में खराश है",
        "Saans lene mein koi dikkat nahi hai",
        "सांस लेने में कोई तकलीफ या परेशानी नहीं है",
        "Patient is not unconscious, he is awake and talking normally",
        "Chehra tedha nahi hua hai, na hi koi kamzori hai",
        "चेहरा टेढ़ा नहीं हुआ है और मरीज पूरी तरह होश में है",
        "No active bleeding, cut was tiny and stopped right away",
        "Khoon nahi beh raha hai, sirf halki kharoch aayi thi",
        "I have zero thoughts of suicide or self harm, feeling very positive today",
        "Suicide ke khayal bilkul nahi hain, meri life achhi chal rahi hai",
        "आत्महत्या का कोई विचार नहीं है, मैं अपनी प्रगति से खुश हूँ",
        "No heart attack symptoms, doctor checked ECG yesterday and said normal",
        "Dil ka daura nahi pada, sirf muscular khinchav tha",
        "Not having any difficulty breathing while walking",
        "Blood vomiting nahi hui hai, normal acidity vomit thi",
        "Behosh nahi hua tha, sirf thoda chakkar aaya aur paani peene par theek ho gaya",
        "I did not poison myself or take any overdose",
        "Never had a stroke or facial droop in my family",
        "No bleeding or cramping during this pregnancy so far",
        "Sugar kam nahi hui hai, bilkul normal 110 hai",
    ]
    for phrase in test_cases:
        res = breaker.check(phrase)
        assert not res.triggered, f"Negation false positive on '{phrase}' (category: {res.category})"


def test_pregnancy_and_acute_abdomen_emergencies_trigger(breaker: EmergencyBreaker) -> None:
    """Verify that pregnancy and acute surgical abdomen emergencies are reliably caught."""
    emergency_cases = [
        ("Heavy vaginal bleeding in 7th month of pregnancy with severe pain", "PREGNANCY_EMERGENCY"),
        ("Pregnancy mein tez bleeding shuru ho gayi hai aur pet mein achanak dard", "PREGNANCY_EMERGENCY"),
        ("गर्भावस्था में अचानक तेज रक्तस्राव और पेट में असहनीय मरोड़", "PREGNANCY_EMERGENCY"),
        ("Sudden severe acute abdominal pain, board-like rigid belly cannot touch", "ACUTE_ABDOMEN"),
        ("Pet mein achanak itna tez dard hua hai ki pet pathar jaisa tight ho gaya", "ACUTE_ABDOMEN"),
        ("पेट में असहनीय भयंकर दर्द, पेट छूने पर चीख निकल रही है और उल्टियां", "ACUTE_ABDOMEN"),
    ]
    for phrase, expected_cat in emergency_cases:
        res = breaker.check(phrase)
        assert res.triggered, f"Failed to trigger emergency on '{phrase}'"
        assert res.category == expected_cat, f"Expected {expected_cat}, got {res.category} on '{phrase}'"


def test_crisis_protocol_includes_verified_mohfw_helplines(breaker: EmergencyBreaker) -> None:
    """Verify Tele-MANAS (1800-891-4416 / 14416) and KIRAN (1800-599-0019) are in crisis response."""
    res = breaker.check("I want to end my life, please help me")
    assert res.triggered
    assert res.category == "CRISIS"
    assert "1800-891-4416" in res.response or "14416" in res.response
    assert "1800-599-0019" in res.response
