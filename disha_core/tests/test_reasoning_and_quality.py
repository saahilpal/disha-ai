from __future__ import annotations

import unittest
from typing import AsyncIterator

from disha_core.engine.anti_echo import (
    filter_response_sentences,
    is_pure_echo_or_filler,
    strip_echo_prefix,
)
from disha_core.engine.context_builder import (
    LengthPolicy,
    determine_length_policy,
    render_user_payload,
)
from disha_core.engine.normalizer import (
    normalize,
)
from disha_core.llm.sentence_buffer import validated_sentences
from disha_core.pipeline.validator import SentenceValidator


class AntiEchoQualityTests(unittest.TestCase):
    def test_strip_echo_prefix_hinglish_inquiry(self) -> None:
        user_input = "Pet mein dard ho raha hai"
        model_reply = "Aapne poocha ki pet mein dard ho raha hai, toh pehle thoda gunguna paani piyein."
        cleaned = strip_echo_prefix(model_reply, user_input)
        self.assertEqual(cleaned, "Pehle thoda gunguna paani piyein.")
        self.assertNotIn("Aapne poocha ki", cleaned)

    def test_strip_echo_prefix_english_inquiry(self) -> None:
        user_input = "Can I drink coffee before morning walk?"
        model_reply = "Regarding your question about drinking coffee before morning walk, yes, you can have black coffee in moderation."
        cleaned = strip_echo_prefix(model_reply, user_input)
        self.assertEqual(cleaned, "Yes, you can have black coffee in moderation.")
        self.assertNotIn("Regarding your question", cleaned)

    def test_strip_echo_prefix_hindi_devanagari(self) -> None:
        user_input = "पेट में गैस बन रही है"
        model_reply = "आपने पूछा कि पेट में गैस बन रही है, तो आप थोड़ा गुनगुना पानी पिएं।"
        cleaned = strip_echo_prefix(model_reply, user_input)
        self.assertNotIn("आपने पूछा कि", cleaned)
        self.assertIn("गुनगुना पानी पिएं", cleaned)

    def test_pure_empathy_filler_detection(self) -> None:
        filler = "I understand you have been feeling tired after work."
        self.assertTrue(is_pure_echo_or_filler(filler, "feeling tired after work"))

        hinglish_filler = "Main samajh sakti hoon ki aap kaisa mehsoos kar rahe hain."
        self.assertTrue(is_pure_echo_or_filler(hinglish_filler))

        # Direct advice should NOT be marked as filler
        advice = "Evening energy ke liye 10 minute brisk walk karein."
        self.assertFalse(is_pure_echo_or_filler(advice))

    def test_filter_response_sentences_promotes_direct_answer_to_sentence_one(self) -> None:
        user_input = "What can I do for evening fatigue?"
        raw_sentences = [
            "I understand you have been feeling tired after work.",
            "Evening energy ke liye aap 10 minute brisk walk karein aur warm water piyein.",
            "Aap ise try karein aur mujhe batayein.",
        ]
        filtered = filter_response_sentences(raw_sentences, user_input, has_history=True)
        # Sentence 1 must be the actionable advice, NOT the empathy boilerplate
        self.assertEqual(filtered[0], "Evening energy ke liye aap 10 minute brisk walk karein aur warm water piyein.")
        self.assertNotIn("I understand you have been feeling tired", filtered[0])

    def test_filter_response_sentences_suppresses_redundant_greetings_with_history(self) -> None:
        user_input = "Dedicated nutritionist plan ka kya price hai?"
        raw_sentences = [
            "Namaste! Main Disha hoon. Aapka swagat hai.",
            "Dedicated nutritionist plan ₹1,499 per month hai.",
        ]
        filtered = filter_response_sentences(raw_sentences, user_input, has_history=True)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0], "Dedicated nutritionist plan ₹1,499 per month hai.")

    def test_affirmative_answers_not_mutilated(self) -> None:
        user_input = "Kya main subah aam kha sakta hoon?"
        direct_reply = "Haan, aap morning mein 100g mango kha sakte hain."
        cleaned = strip_echo_prefix(direct_reply, user_input)
        self.assertEqual(cleaned, direct_reply)


class ResponseLengthPolicyTests(unittest.TestCase):
    def test_factual_query_length_policy(self) -> None:
        factual_queries = [
            "Dedicated plan kitne ka hai?",
            "Follow-up fees kitni hai?",
            "Aap kaun ho?",
            "What is your price?",
            "What is BMI?",
        ]
        for q in factual_queries:
            policy = determine_length_policy(q)
            self.assertEqual(policy.category, "factual", f"Failed for query: {q}")
            self.assertEqual(policy.min_sentences, 1)
            self.assertEqual(policy.max_sentences, 2)

    def test_coaching_query_length_policy(self) -> None:
        coaching_queries = [
            "Daily morning walk ki habit kaise shuru karein?",
            "Raat ko neend nahi aati, koi tips batayein.",
            "Hydration maintain karne ke liye best tarika kya hai?",
        ]
        for q in coaching_queries:
            policy = determine_length_policy(q)
            self.assertEqual(policy.category, "coaching", f"Failed for query: {q}")
            self.assertEqual(policy.min_sentences, 2)
            self.assertEqual(policy.max_sentences, 4)

    def test_complex_health_query_length_policy(self) -> None:
        complex_queries = [
            "Mujhe high bp aur diabetes dono hai, aur subah dizziness lagti hai.",
            "Severe pain and shortness of breath ho rahi hai.",
        ]
        for q in complex_queries:
            policy = determine_length_policy(q)
            self.assertIn(policy.category, {"complex", "emergency"}, f"Failed for query: {q}")
            self.assertGreaterEqual(policy.max_sentences, 2)

    def test_detailed_query_length_policy(self) -> None:
        detailed_queries = [
            "Explain in detail how shatapadi helps blood sugar control step by step.",
            "Mujhe vistar se samjhao diabetes management ka plan.",
        ]
        for q in detailed_queries:
            policy = determine_length_policy(q)
            self.assertEqual(policy.category, "detailed", f"Failed for query: {q}")
            self.assertGreaterEqual(policy.max_sentences, 6)

    def test_emergency_length_policy(self) -> None:
        policy = determine_length_policy("Chest pain", is_emergency=True)
        self.assertEqual(policy.category, "emergency")
        self.assertEqual(policy.max_sentences, 2)


class StreamingSentenceBufferQualityTests(unittest.IsolatedAsyncioTestCase):
    async def test_factual_query_streaming_enforces_max_length(self) -> None:
        async def mock_stream() -> AsyncIterator[str]:
            # Emits 4 sentences
            yield "Follow-up check-in kal subah karenge. "
            yield "Aap daily walk 20 minute rakhein. "
            yield "Aap My Plan tab mein check karein. "
            yield "Mujhe batayein agar koi sawaal ho."

        policy = LengthPolicy(category="factual", min_sentences=1, max_sentences=2)
        context = {
            "length_policy": policy,
            "user_input": "Next check-in kab hai?",
        }
        validator = SentenceValidator()
        emitted = [s async for s in validated_sentences(mock_stream(), validator, context)]
        # Must enforce max_sentences <= 2
        self.assertLessEqual(len(emitted), 2)
        self.assertIn("Follow-up check-in", emitted[0])

    async def test_anti_echo_in_stream_skips_filler_and_answers_immediately(self) -> None:
        async def mock_stream() -> AsyncIterator[str]:
            yield "I understand you have been feeling tired after work. "
            yield "Evening energy ke liye 10 minute brisk walk karein. "
            yield "Hydration ka dhyan rakhein."

        policy = LengthPolicy(category="coaching", min_sentences=2, max_sentences=4)
        context = {
            "length_policy": policy,
            "user_input": "I feel tired in the evening, what to do?",
        }
        validator = SentenceValidator()
        emitted = [s async for s in validated_sentences(mock_stream(), validator, context)]
        # First emitted sentence must be the direct answer!
        self.assertEqual(emitted[0], "Evening energy ke liye 10 minute brisk walk karein.")
        self.assertNotIn("I understand", emitted[0])

    async def test_safety_disclaimer_preserved_at_boundary(self) -> None:
        async def mock_stream() -> AsyncIterator[str]:
            yield "Thoda gunguna paani piyein. "
            yield "10 minute aaram karein. "
            yield "Agar dard badhta hai toh turant apne doctor ya clinic se consult karein."

        # Policy limits to 2 sentences
        policy = LengthPolicy(category="coaching", min_sentences=1, max_sentences=2)
        context = {
            "length_policy": policy,
            "user_input": "Pet mein thoda dard hai",
        }
        validator = SentenceValidator()
        emitted = [s async for s in validated_sentences(mock_stream(), validator, context)]
        # The safety disclaimer mentioning doctor/clinic must be preserved!
        combined = " ".join(emitted)
        self.assertTrue(any("doctor" in s or "clinic" in s for s in emitted), f"Safety disclaimer missing in: {combined}")


class ContextRelevanceTests(unittest.TestCase):
    def test_user_query_domain_detection(self) -> None:
        sleep_query = "Raat ko acchi neend aane ke liye kya karein?"
        norm_sleep = normalize(sleep_query)
        self.assertFalse(norm_sleep.is_meal_query)
        self.assertFalse(norm_sleep.is_exercise_query)

        food_query = "Lunch mein kya khana chahiye?"
        norm_food = normalize(food_query)
        self.assertTrue(norm_food.is_meal_query)
        self.assertFalse(norm_food.is_exercise_query)

        gym_query = "Gym mein heavy deadlifts kar sakta hoon?"
        norm_gym = normalize(gym_query)
        self.assertFalse(norm_gym.is_meal_query)
        self.assertTrue(norm_gym.is_exercise_query)

    def test_render_payload_includes_discipline_tags(self) -> None:
        user_input = "Pani kitna peena chahiye?"
        context = {
            "patient_id": "test_patient",
            "pep": {
                "gym_clearance": True,
                "allowed_modalities": ["walking"],
                "restricted_modalities": [],
            },
        }
        payload = render_user_payload(user_input, context)
        # Should include response discipline XML
        self.assertIn('<RESPONSE_DISCIPLINE answer_first="true"', payload)
        self.assertIn('prompted_for_meals="false"', payload)
        self.assertIn('prompted_for_exercise="false"', payload)
        self.assertIn('<RESPONSE_TARGET category="', payload)


if __name__ == "__main__":
    unittest.main()
