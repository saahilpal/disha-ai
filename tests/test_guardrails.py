import time
import pytest
from app.guardrails.pre_turn_emergency import emergency_circuit_breaker
from app.guardrails.post_turn_sanitizer import post_turn_sanitizer
from app.guardrails.egress_gate import EgressGate

def test_emergency_standard_chest_pain():
    utterance = "Workout karte waqt seene mein dard aur left hand mein numbness ho rahi hai."
    res = emergency_circuit_breaker.evaluate(utterance)
    assert res.is_emergency is True
    assert res.category == "cardiovascular"
    assert "112" in res.triage_message

def test_emergency_colloquial_hinglish_ulta_haath():
    # North Indian colloquial idiom for left arm: 'ulta haath'
    utterance = "Chhati mein bojh lag raha hai aur ulta haath sunn ho gaya hai."
    res = emergency_circuit_breaker.evaluate(utterance)
    assert res.is_emergency is True
    assert res.category == "cardiovascular"
    assert "112" in res.triage_message

def test_emergency_respiratory_dyspnea():
    utterance = "Achanak saans lene mein bahut takleef ho rahi hai aur dam ghut raha hai."
    res = emergency_circuit_breaker.evaluate(utterance)
    assert res.is_emergency is True
    assert res.category == "respiratory"

def test_emergency_sub_millisecond_latency():
    utterance = "Haan Disha, workout karte waqt seene mein dard ho raha tha."
    start = time.perf_counter()
    iterations = 1000
    for _ in range(iterations):
        emergency_circuit_breaker.evaluate(utterance)
    avg_latency_ms = ((time.perf_counter() - start) / iterations) * 1000.0
    # Must be <0.5ms (usually <0.02ms)
    assert avg_latency_ms < 0.5, f"Emergency check too slow: {avg_latency_ms:.4f} ms"

def test_post_turn_sanitizer_whatsapp_interception():
    raw_llm = "Main aapko WhatsApp par diet chart bhej deti hoon abhi."
    res = post_turn_sanitizer.sanitize(raw_llm)
    assert res.is_modified is True
    assert "whatsapp" not in res.sanitized_text.lower()
    assert "disha mobile app" in res.sanitized_text.lower()

def test_post_turn_sanitizer_persona_interception():
    raw_llm = "Main ek real human doctor hoon jo Disha team se baat kar rahi hoon."
    res = post_turn_sanitizer.sanitize(raw_llm)
    assert res.is_modified is True
    assert "ai health coach" in res.sanitized_text.lower()
    assert "human" not in res.sanitized_text.lower()

def test_post_turn_sanitizer_price_interception():
    raw_llm = "Aapka subscription ₹999 ka hoga monthly."
    res = post_turn_sanitizer.sanitize(raw_llm)
    assert res.is_modified is True
    assert "1499" in res.sanitized_text or "free" in res.sanitized_text
    assert "999" not in res.sanitized_text

def test_post_turn_sanitizer_mandatory_remedy_enforcement():
    # If LLM gave generic empathy and omitted jeera/saunf
    raw_llm = "Aap aaram kijiye aur pani pijiye."
    res = post_turn_sanitizer.sanitize(raw_llm, required_remedy_tokens=["jeera", "saunf"])
    assert res.is_modified is True
    assert "jeera" in res.sanitized_text
    assert "saunf" in res.sanitized_text

def test_egress_gate_sanitizes_credentials_and_abha():
    sensitive_log = "Patient ABHA: 12-3456-7890-1234, Mobile: +919876543210, Key: dummy_token_scrubbed"
    clean = EgressGate.sanitize(sensitive_log)
    assert "[REDACTED_ABHA_ID]" in clean
    assert "[REDACTED_INDIAN_PHONE]" in clean
    assert "[REDACTED_GROQ_KEY]" in clean
    assert "12-3456-7890-1234" not in clean

