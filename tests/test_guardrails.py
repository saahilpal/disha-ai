import pytest
from app.guardrails import emergency_breaker, sanitizer, EgressGate

def test_emergency_cardiovascular_english():
    res = emergency_breaker.evaluate("I have severe chest pain and left arm numbness")
    assert res.is_emergency is True
    assert res.category == "cardiovascular"
    assert "112" in res.triage_message
    assert res.latency_ms < 1.0  # Must be sub-millisecond

def test_emergency_cardiovascular_hinglish():
    res = emergency_breaker.evaluate("Workout karte waqt seene mein tez dard aur baaye haath mein dard ho raha hai")
    assert res.is_emergency is True
    assert res.category == "cardiovascular"
    assert "112" in res.triage_message

def test_emergency_colloquial_chhati_and_ulta_haath():
    res = emergency_breaker.evaluate("Chhati mein bojh lag raha hai aur ulta haath sunn pad gaya hai")
    assert res.is_emergency is True
    assert res.category == "cardiovascular"
    assert "112" in res.triage_message

def test_emergency_respiratory():
    res = emergency_breaker.evaluate("Achanak saans lene mein takleef ho rahi hai aur dam ghut raha hai")
    assert res.is_emergency is True
    assert res.category == "respiratory"

def test_emergency_neurological():
    res = emergency_breaker.evaluate("Achanak chehra tedha ho gaya aur bolne mein dikkat ho rahi hai")
    assert res.is_emergency is True
    assert res.category == "neurological"

def test_emergency_psychiatric():
    res = emergency_breaker.evaluate("Mujhe marne ka mann ho raha hai aur bahut akelapan lag raha hai")
    assert res.is_emergency is True
    assert res.category == "psychiatric"

def test_non_emergency_routine_exercise():
    res = emergency_breaker.evaluate("Aaj maine 8000 steps walk kiya aur thoda thakan lag rahi hai")
    assert res.is_emergency is False
    assert res.triage_message is None

def test_sanitizer_persona_violation():
    text, modified, reason = sanitizer.sanitize("Haan main ek real insaan aur doctor hoon clinic mein.")
    assert modified is True
    assert reason == "INTERCEPTED_PERSONA_VIOLATION"
    assert "AI health coach" in text
    assert "insaan" not in text.lower()

def test_sanitizer_channel_violation():
    text, modified, reason = sanitizer.sanitize("Main aapko PDF WhatsApp par bhej deti hoon.")
    assert modified is True
    assert reason == "INTERCEPTED_CHANNEL_VIOLATION"
    assert "My Plan" in text
    assert "whatsapp" not in text.lower()

def test_sanitizer_hallucinated_price():
    text, modified, reason = sanitizer.sanitize("Iska monthly subscription ₹999 ka hai.")
    assert modified is True
    assert reason == "INTERCEPTED_PRICE_HALLUCINATION"
    assert "₹999" not in text
    assert "₹1,499" in text

def test_sanitizer_valid_price_allowed():
    clean_input = "Disha voice calls free hain, aur dietitian plan ₹1499 ka hai."
    text, modified, reason = sanitizer.sanitize(clean_input)
    assert modified is False
    assert "1499" in text

def test_sanitizer_mandatory_remedy_enforced():
    text, modified, reason = sanitizer.sanitize(
        raw_text="Aap aaram karein aur hydration ka dhyan rakhein.",
        required_remedy_tokens=["jeera", "saunf"],
    )
    assert modified is True
    assert reason == "ENFORCED_MANDATORY_REMEDY"
    assert "jeera" in text.lower()
    assert "saunf" in text.lower()

def test_egress_gate_scrubs_keys_and_phi():
    leak_sample = "Call me on +919876543210. Groq key: dummy_token_scrubbed. ABHA: 12-3456-7890-1234."
    scrubbed = EgressGate.scrub(leak_sample)
    assert "+919876543210" not in scrubbed
    assert "your_groq_api_key_here" not in scrubbed
    assert "12-3456-7890-1234" not in scrubbed
    assert "[REDACTED_KEY]" in scrubbed
    assert "[REDACTED_PHONE]" in scrubbed
    assert "[REDACTED_ABHA_ID]" in scrubbed

