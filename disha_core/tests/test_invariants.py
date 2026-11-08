from __future__ import annotations

import asyncio
import hashlib
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from disha_core import main as app_main
from disha_core.compliance.ledger import AuditLedger, AuditRecord, current_hash
from disha_core.engine.context_builder import (
    PEP_SQL,
    add_approved_remedy_constraints,
    build_patient_context,
    diet_slot_xml,
    render_user_payload,
)
from disha_core.engine.normalizer import normalize
from disha_core.llm.client import (
    ConsecutiveFailureCircuitBreaker,
    DualProviderClient,
    GeminiProvider,
    GroqProvider,
    LLMSettings,
    ProviderError,
)
from disha_core.llm.sentence_buffer import SentenceBuffer, validated_sentences
from disha_core.pipeline.breaker import EmergencyBreaker
from disha_core.pipeline.router import Intent, IntentRouter
from disha_core.pipeline.validator import PRICING_REPLACEMENT, REMEDY_UNAVAILABLE, SentenceValidator
from disha_core.tests.runner import evaluate_corpus, turn_sha256, wilson_upper_bound
from disha_core.voice import (
    ENGLISH_VOICE,
    HINDI_VOICE,
    VoicePrivacyError,
    VoiceSession,
    select_tts_voice,
    transcribe_groq,
)


class ExplodingClassifier:
    def classify(self, text: str) -> Intent:
        raise AssertionError("classifier must not run on an emergency turn")


class InvariantTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = SentenceValidator()

    def test_pre_turn_breaker_intercepts_chest_pain_and_bypasses_classifier(self) -> None:
        router = IntentRouter(ExplodingClassifier())
        result, intent = router.route("Chhati mein dabaav aur dard lag raha hai.")
        self.assertTrue(result.triggered)
        self.assertEqual(result.category, "CARDIOVASCULAR")
        self.assertIn("112", result.response or "")
        self.assertIsNone(intent)

    def test_breaker_handles_spaced_hinglish(self) -> None:
        result = EmergencyBreaker().check("c h h a t i mein d a r d ho raha hai")
        self.assertTrue(result.triggered)

    def test_breaker_respects_word_boundaries(self) -> None:
        self.assertFalse(EmergencyBreaker().check("I like chest painting.").triggered)

    def test_invalid_currency_and_price_context_are_rewritten(self) -> None:
        for text in (
            "Plan ₹500 ka hai.", "The subscription costs ₹500.",
            "Yeh subscription kitne ka hai? 500 chalega?",
            "Dedicated plan is ₹1,499.99/month.",
        ):
            result = self.validator.validate_sentence(text)
            self.assertIn("price", result.reasons)
            self.assertIn("₹1,499", result.text)

    def test_allowed_prices_pass(self) -> None:
        result = self.validator.validate_sentence("Follow-up ₹0 hai aur plan ₹1,499 per month hai.")
        self.assertEqual(result.status, "accepted")

    def test_non_inr_zero_price_is_rewritten_to_catalog_pricing(self) -> None:
        result = self.validator.validate_sentence("Follow-up is $0.")
        self.assertEqual(result.text, PRICING_REPLACEMENT)
        self.assertIn("price", result.reasons)

    def test_foreign_currency_symbol_is_rewritten_without_pricing_keywords(self) -> None:
        result = self.validator.validate_sentence("Plan €1,499/month.")
        self.assertEqual(result.text, PRICING_REPLACEMENT)
        self.assertIn("price", result.reasons)

    def test_unqualified_dedicated_plan_amount_is_rewritten(self) -> None:
        result = self.validator.validate_sentence("Dedicated nutritionist plan is 1500 per month.")
        self.assertEqual(result.text, PRICING_REPLACEMENT)
        self.assertIn("price", result.reasons)

    def test_channel_promise_is_rewritten(self) -> None:
        result = self.validator.validate_sentence("Main WhatsApp par chart bhejungi.")
        self.assertIn("channel_boundary", result.reasons)
        self.assertIn("My Plan", result.text)
        hindi_result = self.validator.validate_sentence("Main व्हाट्सएप par chart bhejungi.")
        self.assertIn("channel_boundary", hindi_result.reasons)

    def test_first_person_clinical_claim_is_rewritten(self) -> None:
        for claim in ("Haan, main doctor hoon.", "I'm a doctor.", "मैं डॉक्टर हूँ।"):
            result = self.validator.validate_sentence(claim)
            self.assertIn("identity", result.reasons)
            self.assertIn("AI health coach", result.text)

    def test_missing_meal_slot_blocks_recipe(self) -> None:
        result = self.validator.validate_sentence(
            "Aap dal aur roti ki recipe bana sakte hain.", {"diet_status": "NOT_FOUND"}
        )
        self.assertIn("meal_not_found", result.reasons)
        self.assertNotIn("recipe", result.text.casefold())

    def test_gym_clearance_is_not_contradicted(self) -> None:
        context = {
            "gym_clearance": True,
            "allowed_modalities": ["gym", "light_strength"],
            "restricted_modalities": ["heavy_deadlifts"],
        }
        result = self.validator.validate_sentence("Gym mein light strength training kar sakte hain.", context)
        self.assertEqual(result.status, "accepted")

    def test_restricted_modality_is_blocked(self) -> None:
        result = self.validator.validate_sentence(
            "Aaj heavy deadlifts kijiye.", {"restricted_modalities": ["heavy_deadlifts"]}
        )
        self.assertIn("pep_restriction", result.reasons)

    def test_activity_missing_from_patient_permissions_is_blocked(self) -> None:
        result = self.validator.validate_sentence(
            "Aaj running karein.", {"allowed_modalities": ["yoga"], "restricted_modalities": []}
        )
        self.assertIn("pep_restriction", result.reasons)

    def test_draft_remedy_is_not_asserted_as_clinical_advice(self) -> None:
        result = self.validator.validate_turn(
            "Aap rest karein.", {"clinical_tags": ["GI_BLOATING"], "protocol_approved": False}
        )
        self.assertIn("remedy_not_configured", result.reasons)
        self.assertIn("verified advice", result.text)

    def test_approved_remedy_requires_configured_source_text(self) -> None:
        result = self.validator.validate_turn(
            "Aap rest karein.", {
                "clinical_tags": ["GI_BLOATING"], "protocol_approved": True,
                "required_remedy_tokens": ["jeera"],
                "approved_remedy_text": "Verified plan ke mutabik warm jeera water lein.",
            }
        )
        self.assertIn("remedy_assertion", result.reasons)
        self.assertIn("jeera", result.text)

    def test_mango_is_normalized_but_not_promoted_to_approved_advice(self) -> None:
        self.assertIn("FRUIT_MODERATION", normalize("Weight loss mein aam khana mana hai?").tags)

    def test_only_matching_clinical_chunk_supplies_remedy_constraints(self) -> None:
        context = {}
        chunks = [
            {"condition_tag": "GENERAL", "guideline_content": "Rest.", "required_remedy_tokens": ["rest"]},
            {
                "condition_tag": "GI_BLOATING",
                "guideline_content": "Approved source: warm jeera water.",
                "required_remedy_tokens": ["jeera"],
            },
        ]
        add_approved_remedy_constraints(context, chunks)
        self.assertTrue(context["protocol_approved"])
        self.assertEqual(context["required_remedy_tokens"], ("jeera",))

    def test_tts_sanitizer_preserves_emergency_number(self) -> None:
        self.assertEqual(SentenceValidator.sanitize_for_tts("**Call 112 now.**"), "Call 112 now.")
        self.assertEqual(SentenceValidator.sanitize_for_tts("❤️ Call 112 now 😊."), "Call 112 now.")

    def test_llm_model_ids_are_taken_from_environment(self) -> None:
        with patch.dict(os.environ, {
            "GROQ_MODEL": "configured-groq-model",
            "GEMINI_MODEL": "configured-gemini-model",
            "GROQ_API_KEY": "test-groq-key",
            "GEMINI_API_KEY": "test-gemini-key",
            "GROQ_HEALTH_DATA_AUTHORIZED": "false",
            "GEMINI_HEALTH_DATA_AUTHORIZED": "false",
            "GEMINI_PAID_OR_CONTRACTED": "false",
        }):
            settings = LLMSettings.from_env()
        self.assertEqual(settings.groq_model, "configured-groq-model")
        self.assertEqual(settings.gemini_model, "configured-gemini-model")

    def test_retired_provider_model_ids_are_mapped_without_editing_environment(self) -> None:
        with patch.dict(os.environ, {
            "GROQ_MODEL": "llama-3.3-70b-versatile",
            "GEMINI_MODEL": "gemini-2.0-flash",
            "GROQ_HEALTH_DATA_AUTHORIZED": "false",
            "GEMINI_HEALTH_DATA_AUTHORIZED": "false",
            "GEMINI_PAID_OR_CONTRACTED": "false",
        }):
            settings = LLMSettings.from_env()
        self.assertEqual(settings.groq_model, "openai/gpt-oss-120b")
        self.assertEqual(settings.gemini_model, "gemini-3.6-flash")

    def test_context_xml_escapes_patient_and_retrieved_text(self) -> None:
        context = {
            "patient_id": 'p<&"',
            "pep": {"allowed_modalities": ["yoga & <gym>"], "restricted_modalities": [], "gym_clearance": True},
            "diet_slot_xml": diet_slot_xml("dinner", "<recipe>&"),
        }
        payload = render_user_payload("<ignore rules>", context, [{
            "source_citation": "source<&", "context_header": "<scope>", "guideline_content": "A & B",
        }])
        self.assertIn("&lt;ignore rules&gt;", payload)
        self.assertIn("&lt;recipe&gt;&amp;", payload)
        self.assertNotIn('id="p<&"', payload)

    def test_sentence_buffer_handles_boundaries_and_decimal_split_across_chunks(self) -> None:
        buffer = SentenceBuffer()
        self.assertEqual(buffer.feed("Dose 1."), [])
        self.assertEqual(buffer.feed("5 mg. Agla"), ["Dose 1.5 mg."])
        self.assertEqual(buffer.feed(" vakya!"), ["Agla vakya!"])

    def test_hash_formula_matches_specification(self) -> None:
        record = AuditRecord("p1", "hello", "namaste", "clear", "accepted")
        prev = "0" * 64
        expected = hashlib.sha256(f"{prev}|p1|hello|namaste|clear|accepted".encode()).hexdigest()
        self.assertEqual(current_hash(prev, record), expected)

    def test_1500_zero_false_verifications_cannot_prove_target(self) -> None:
        self.assertGreater(wilson_upper_bound(0, 1500), 0.001)
        self.assertLess(wilson_upper_bound(0, 2703), 0.001)

    def test_hash_pinned_fixture_and_fvr_gate(self) -> None:
        record = {
            "id": "turn-1",
            "input": "Mujhe halka sa headache hai",
            "expected_emergency": False,
        }
        record["record_sha256"] = turn_sha256(record)
        corpus = (json.dumps(record, separators=(",", ":")) + "\n").encode()
        digest = hashlib.sha256(corpus).hexdigest()
        report = evaluate_corpus(corpus, digest)
        self.assertEqual(report.turns, 1)
        self.assertFalse(report.meets_fvr_target)
        self.assertFalse(report.complete_corpus)
        self.assertFalse(report.all_invariants_pass)
        with self.assertRaises(ValueError):
            evaluate_corpus(corpus, "0" * 64)

    def test_fvr_is_unsafe_output_false_acceptance(self) -> None:
        record = {
            "id": "unsafe-1",
            "input": "How much is the plan?",
            "expected_emergency": False,
            "output": "Plan ₹500 ka hai.",
            "must_reject": True,
        }
        record["record_sha256"] = turn_sha256(record)
        corpus = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        report = evaluate_corpus(corpus, hashlib.sha256(corpus).hexdigest())
        self.assertEqual(report.unsafe_output_trials, 1)
        self.assertEqual(report.false_verifications, 0)
        self.assertFalse(report.complete_corpus)

    def test_fvr_increments_when_expected_unsafe_output_is_accepted(self) -> None:
        record = {
            "id": "unsafe-accepted-1",
            "input": "Tell me the price",
            "expected_emergency": False,
            "output": "Namaste, aap kaise hain?",
            "must_reject": True,
        }
        record["record_sha256"] = turn_sha256(record)
        corpus = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        report = evaluate_corpus(corpus, hashlib.sha256(corpus).hexdigest())
        self.assertEqual(report.false_verifications, 1)
        self.assertEqual(report.unsafe_output_trials, 1)
        self.assertAlmostEqual(report.fvr_upper_95_one_sided, 1.0)

    def test_per_turn_digest_detects_tampering_even_if_corpus_hash_is_updated(self) -> None:
        record = {
            "id": "turn-1",
            "input": "A safe question",
            "expected_emergency": False,
        }
        record["record_sha256"] = turn_sha256(record)
        record["input"] = "tampered input"
        corpus = (json.dumps(record, separators=(",", ":")) + "\n").encode()
        with self.assertRaisesRegex(ValueError, "turn-1 SHA-256 mismatch"):
            evaluate_corpus(corpus, hashlib.sha256(corpus).hexdigest())


class AsyncPipelineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        from disha_core.compliance.ledger import _resolve_wal_path
        p = _resolve_wal_path("audit_wal.db")
        if p and p.is_file():
            p.unlink()

    def tearDown(self) -> None:
        from disha_core.compliance.ledger import _resolve_wal_path
        p = _resolve_wal_path("audit_wal.db")
        if p and p.is_file():
            p.unlink()

    async def test_audit_overflow_warns_without_phi_and_does_not_block_chat(self) -> None:
        ledger = AuditLedger(object(), max_queue_size=1)
        ledger.queue.put_nowait(AuditRecord("queued", "", "", "clear", "accepted"))

        async def discard(_record):
            return None

        app = app_main.create_app()
        chat = next((route.endpoint for route in app.routes if getattr(route, "path", None) == "/chat"), None)
        if chat is None:
            for r in app.routes:
                if hasattr(r, "original_router"):
                    for sr in r.original_router.routes:
                        if getattr(sr, "path", None) == "/chat":
                            chat = sr.endpoint
                            break
                if chat is not None:
                    break
        assert chat is not None, "Could not find /chat endpoint in app routes"
        state = SimpleNamespace(
            router=SimpleNamespace(
                breaker=SimpleNamespace(check=lambda _text: SimpleNamespace(triggered=False))
            ),
            ledger=ledger,
        )
        request = SimpleNamespace(app=SimpleNamespace(state=state))
        payload = app_main.TurnRequest(text="PRIVATE_INPUT_SENTINEL")

        async def sentences(*_args):
            yield "PRIVATE_OUTPUT_SENTINEL"

        with patch.object(ledger, "_persist", discard):
            try:
                with (
                    patch.object(app_main, "_authenticated_patient", return_value="PRIVATE_PATIENT_SENTINEL"),
                    patch.object(app_main, "_turn_sentences", sentences),
                    self.assertLogs("disha_core.main", level="WARNING") as captured,
                ):
                    response = await asyncio.wait_for(chat(payload, request, "Bearer token"), timeout=1)
                    self.assertEqual(response["response"], "PRIVATE_OUTPUT_SENTINEL")
                    self.assertEqual(ledger.dropped_count, 1)
                warning = " ".join(record.getMessage() for record in captured.records)
                self.assertRegex(warning.casefold(), r"audit.*(overflow|drop|lost|not recorded|full)")
                for private_value in (payload.text, response["response"], "PRIVATE_PATIENT_SENTINEL"):
                    self.assertNotIn(private_value, warning)
            finally:
                await ledger.close()

    async def test_turn_retrieval_uses_acquired_connection_not_pool(self) -> None:
        class Transaction:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

        class Connection:
            def __init__(self):
                self.transaction_calls = 0
                self.fetchval_calls = []
                self.fetch_calls = []

            def transaction(self):
                self.transaction_calls += 1
                return Transaction()

            async def fetchval(self, query, *args):
                self.fetchval_calls.append((query, args))

            async def fetch(self, query, *args):
                self.fetch_calls.append((query, args))
                return []

        class Pool:
            def __init__(self):
                self.connection = Connection()
                self.acquire_calls = 0

            def acquire(self):
                pool = self

                class Acquire:
                    async def __aenter__(self):
                        pool.acquire_calls += 1
                        return pool.connection

                    async def __aexit__(self, *_):
                        return None

                return Acquire()

        async def unused_sentences(*_args):
            if False:
                yield ""

        pool = Pool()
        state = SimpleNamespace(
            router=SimpleNamespace(route=lambda _text: (SimpleNamespace(triggered=False), None)),
            today_ist=lambda: "monday",
            pool=pool,
            validator=SentenceValidator(),
            llm=SimpleNamespace(stream=lambda _prompt: None),
        )
        request = SimpleNamespace(app=SimpleNamespace(state=state))

        async def patient_context(*_args):
            return {}

        with (
            patch.object(app_main, "build_patient_context", patient_context),
            patch.object(app_main, "render_user_payload", return_value="prompt"),
            patch.object(app_main, "validated_sentences", unused_sentences),
        ):
            output = [
                sentence
                async for sentence in app_main._turn_sentences(
                    request, "patient-1", app_main.TurnRequest(text="hello"), app_main.TurnState()
                )
            ]

        self.assertEqual(output, [])
        self.assertEqual(pool.acquire_calls, 1)
        self.assertEqual(pool.connection.transaction_calls, 1)
        self.assertGreaterEqual(len(pool.connection.fetchval_calls), 1)
        self.assertGreaterEqual(len(pool.connection.fetch_calls), 1)

    def test_voice_selection_uses_language_or_dominant_script(self) -> None:
        self.assertEqual(select_tts_voice("Hello, how are you?", "en-IN"), ENGLISH_VOICE)
        self.assertEqual(select_tts_voice("Hello, aap kaise hain?"), HINDI_VOICE)
        self.assertEqual(select_tts_voice("आप कैसे हैं?"), HINDI_VOICE)

    async def test_voice_barge_in_cancels_active_audio_stream(self) -> None:
        started = asyncio.Event()
        voices: list[str] = []
        sent: list[bytes] = []

        async def synthesizer(text: str, voice: str):
            voices.append(voice)
            yield b"first chunk"
            started.set()
            await asyncio.Event().wait()

        async def send_audio(chunk: bytes) -> None:
            sent.append(chunk)

        session = VoiceSession(synthesizer)
        speaking = asyncio.create_task(session.speak("Aap kaise hain?", send_audio))
        await asyncio.wait_for(started.wait(), timeout=1)
        await session.barge_in()
        with self.assertRaises(asyncio.CancelledError):
            await speaking
        self.assertEqual(sent, [b"first chunk"])
        self.assertEqual(voices, [HINDI_VOICE])

    async def test_groq_transcription_fails_closed_before_network_without_approval(self) -> None:
        with patch.dict(os.environ, {"GROQ_HEALTH_DATA_PROCESSING_APPROVED": "false"}):
            with self.assertRaises(VoicePrivacyError):
                await transcribe_groq(b"audio bytes")

    async def test_patient_context_uses_parameters_and_marks_missing_meal(self) -> None:
        calls = []

        class Connection:
            async def fetchrow(self, query, *args):
                calls.append((query, args))
                if query == PEP_SQL:
                    return {"hypertension_stage": "stage_1", "gym_clearance": True,
                            "allowed_modalities": ["yoga"], "restricted_modalities": []}
                return None

        context = await build_patient_context(Connection(), "patient-1", "Monday", "dinner")
        self.assertEqual(calls[1][1], ("patient-1", "monday", "dinner"))
        self.assertEqual(context["diet_status"], "NOT_FOUND")
        self.assertEqual(context["diet_slot_xml"], '<DIET_SLOT status="NOT_FOUND"/>')

    async def test_patient_context_pep_permissions_reach_sentence_validator(self) -> None:
        class Connection:
            async def fetchrow(self, query, *_args):
                if query == PEP_SQL:
                    return {
                        "gym_clearance": True,
                        "allowed_modalities": ["yoga"],
                        "restricted_modalities": ["heavy_deadlifts"],
                    }
                return None

        context = await build_patient_context(Connection(), "patient-1", "Monday", "dinner")
        pep = context.get("pep") or context
        self.assertTrue(pep["gym_clearance"])
        self.assertEqual(pep["restricted_modalities"], ["heavy_deadlifts"])
        result = SentenceValidator().validate_sentence("Aaj heavy deadlifts kijiye.", context)
        self.assertIn("pep_restriction", result.reasons)

    async def test_provider_fails_over_before_first_token(self) -> None:
        class Fail:
            async def stream(self, prompt: str):
                raise ProviderError("rate limited", retryable=True)
                yield "unreachable"

        class Good:
            async def stream(self, prompt: str):
                yield "Namaste."

        client = DualProviderClient(LLMSettings(None, None, None, None))
        client.providers = (Fail(), Good())
        self.assertEqual([piece async for piece in client.stream("hello")], ["Namaste."])

    async def test_primary_circuit_opens_after_two_consecutive_failures(self) -> None:
        class Fail:
            calls = 0

            async def stream(self, prompt: str):
                self.calls += 1
                raise ProviderError("rate limited", retryable=True)
                yield "unreachable"

        class Good:
            async def stream(self, prompt: str):
                yield "Namaste."

        primary = Fail()
        client = DualProviderClient(LLMSettings(None, None, None, None))
        client.providers = (primary, Good())
        for _ in range(3):
            self.assertEqual([piece async for piece in client.stream("hello")], ["Namaste."])
        self.assertEqual(primary.calls, 2)

    async def test_health_data_providers_fail_closed_without_authorization(self) -> None:
        with self.assertRaises(ProviderError):
            await anext(GroqProvider(LLMSettings("key", "model", None, None)).stream("health data"))
        with self.assertRaises(ProviderError):
            await anext(GeminiProvider(LLMSettings(None, None, "key", "model")).stream("health data"))

    async def test_circuit_breaker_requires_two_failures_then_opens(self) -> None:
        circuit = ConsecutiveFailureCircuitBreaker(threshold=2, cooldown=60)
        self.assertTrue(await circuit.allow_primary())
        await circuit.record_failure()
        self.assertTrue(await circuit.allow_primary())
        await circuit.record_failure()
        self.assertFalse(await circuit.allow_primary())
        await circuit.record_success()
        self.assertTrue(await circuit.allow_primary())

    async def test_validated_sentence_stream_rewrites_before_egress(self) -> None:
        async def chunks():
            yield "Main aapko WhatsApp par bhejungi. Agla sentence."

        output = [sentence async for sentence in validated_sentences(chunks(), SentenceValidator())]
        self.assertIn("My Plan", output[0])
        self.assertEqual(output[1], "Agla sentence.")

    async def test_approved_remedy_gate_runs_before_first_sentence_egress(self) -> None:
        approved_text = "Verified plan ke mutabik warm jeera water lein."

        class Chunks:
            def __init__(self):
                self.pieces = ["Aap rest karein. Saunf water lein."]
                self.started = False
                self.closed = False

            def __aiter__(self):
                self.started = True
                return self

            async def __anext__(self):
                if not self.pieces:
                    raise StopAsyncIteration
                return self.pieces.pop(0)

            async def aclose(self):
                self.closed = True

        source = Chunks()
        output = validated_sentences(source, SentenceValidator(), {
            "clinical_tags": ["GI_BLOATING"],
            "protocol_approved": True,
            "required_remedy_tokens": ["jeera"],
            "approved_remedy_text": approved_text,
        })
        try:
            self.assertEqual(await anext(output), approved_text)
            with self.assertRaises(StopAsyncIteration):
                await anext(output)
            self.assertTrue(source.closed)
            self.assertFalse(source.started)
        finally:
            await output.aclose()

    async def test_unapproved_remedy_rewrite_closes_stream_before_later_sentences(self) -> None:
        class Chunks:
            def __init__(self):
                self.pieces = ["Aap rest karein. Saunf water lein."]
                self.started = False
                self.closed = False

            def __aiter__(self):
                self.started = True
                return self

            async def __anext__(self):
                if not self.pieces:
                    raise StopAsyncIteration
                return self.pieces.pop(0)

            async def aclose(self):
                self.closed = True

        source = Chunks()
        output = validated_sentences(source, SentenceValidator(), {"clinical_tags": ["GI_BLOATING"]})
        try:
            self.assertEqual(await anext(output), REMEDY_UNAVAILABLE)
            with self.assertRaises(StopAsyncIteration):
                await anext(output)
            self.assertTrue(source.closed)
            self.assertFalse(source.started)
        finally:
            await output.aclose()

    async def test_onnx_and_router_async_classify(self) -> None:
        from disha_core.pipeline.router import OnnxIntentClassifier, RuleIntentClassifier
        rule_classifier = RuleIntentClassifier()
        intent = await rule_classifier.async_classify("What should I eat for dinner?")
        self.assertEqual(intent, Intent.MEAL_QUERY)

        router = IntentRouter(rule_classifier)
        intent = await router.async_classify("What should I eat for dinner?")
        self.assertEqual(intent, Intent.MEAL_QUERY)

        breaker_res, intent = await router.async_route("What should I eat for dinner?")
        self.assertFalse(breaker_res.triggered)
        self.assertEqual(intent, Intent.MEAL_QUERY)

        # Test OnnxIntentClassifier async_classify uses asyncio.to_thread
        mock_onnx = object.__new__(OnnxIntentClassifier)
        mock_onnx._session = SimpleNamespace(run=lambda _out, _inp: [["MEAL_QUERY"]])
        mock_onnx._encode = lambda text: {"input": text}
        mock_onnx._decode = lambda values: Intent.MEAL_QUERY
        onnx_intent = await mock_onnx.async_classify("khana kya hai")
        self.assertEqual(onnx_intent, Intent.MEAL_QUERY)

    async def test_ledger_wal_durability_and_replay(self) -> None:
        import tempfile
        from contextlib import suppress
        with tempfile.TemporaryDirectory() as tmpdir:
            wal_file = os.path.join(tmpdir, "test_wal.db")
            record1 = AuditRecord("pt-1", "user1", "llm1", "clear", "accepted")
            record2 = AuditRecord("pt-2", "user2", "llm2", "clear", "accepted")

            # Create ledger and enqueue records
            ledger = AuditLedger(object(), max_queue_size=10, wal_path=wal_file)
            ledger.enqueue(record1)
            ledger.enqueue(record2)
            # Verify records are in SQLite WAL
            ledger.flush_to_wal()
            if ledger._worker and not ledger._worker.done():
                ledger._worker.cancel()
                with suppress(asyncio.CancelledError):
                    await ledger._worker

            # Now create a second ledger pointing to the same WAL file
            # It should recover and replay the uncommitted records from SQLite on startup
            ledger2 = AuditLedger(object(), max_queue_size=10, wal_path=wal_file)
            self.assertEqual(ledger2.queue.qsize(), 2)
            recovered = [ledger2.queue.get_nowait(), ledger2.queue.get_nowait()]
            self.assertEqual({r.patient_id for r in recovered}, {"pt-1", "pt-2"})
            if ledger2._worker and not ledger2._worker.done():
                ledger2._worker.cancel()
                with suppress(asyncio.CancelledError):
                    await ledger2._worker

    async def test_sigterm_and_shutdown_flushes_pending_wal(self) -> None:
        import sqlite3
        import tempfile
        from contextlib import suppress
        with tempfile.TemporaryDirectory() as tmpdir:
            wal_file = os.path.join(tmpdir, "shutdown_wal.db")
            record = AuditRecord("pt-shutdown", "u", "l", "clear", "accepted")
            ledger = AuditLedger(object(), max_queue_size=10, wal_path=wal_file)
            # Put directly into in-memory queue without writing to WAL
            ledger.queue.put_nowait(record)
            # Simulate graceful shutdown / SIGTERM flush
            ledger.flush_to_wal()
            with sqlite3.connect(wal_file) as conn:
                count = conn.execute("SELECT COUNT(*) FROM wal_audit_records WHERE patient_id = 'pt-shutdown'").fetchone()[0]
                self.assertEqual(count, 1)
            if ledger._worker and not ledger._worker.done():
                ledger._worker.cancel()
                with suppress(asyncio.CancelledError):
                    await ledger._worker


    def test_websocket_barge_in_and_interruption_frames(self) -> None:
        from fastapi.testclient import TestClient
        app = app_main.create_app()

        async def slow_turn(*args):
            yield "sentence 1"
            await asyncio.sleep(1)
            yield "sentence 2"

        async def fake_speak(*args, **kwargs):
            await asyncio.sleep(1)

        with patch.object(app_main, "_authenticated_patient", return_value="pt_test_01"), \
             patch.object(app_main, "_turn_sentences", slow_turn), \
             patch.object(VoiceSession, "speak", fake_speak):
            client = TestClient(app)
            with client.websocket_connect("/voice?token=valid") as ws:
                # 1. Test explicit interrupt frame
                ws.send_json({"type": "interrupt"})
                self.assertEqual(ws.receive_json(), {"type": "interrupted"})

                # 2. Test explicit barge_in frame
                ws.send_json({"type": "barge_in"})
                self.assertEqual(ws.receive_json(), {"type": "interrupted"})

                # 3. Test new turn while active sends interrupted
                ws.send_json({"type": "text", "text": "turn 1"})
                _ = ws.receive_json()  # transcript
                _ = ws.receive_json()  # sentence
                # New turn arrives while turn 1 is active
                ws.send_json({"type": "text", "text": "turn 2"})
                interrupted_frame = ws.receive_json()
                self.assertEqual(interrupted_frame, {"type": "interrupted"})


    async def test_configurable_pool_limits(self) -> None:
        created_kwargs = {}

        async def fake_create_pool(*args, **kwargs):
            created_kwargs.update(kwargs)
            return SimpleNamespace(close=lambda: asyncio.sleep(0))

        env = {
            "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
            "DB_POOL_MIN": "5",
            "DB_POOL_MAX": "42",
            "DB_POOL_TIMEOUT": "7.5",
        }
        with patch.dict(os.environ, env), patch("asyncpg.create_pool", side_effect=fake_create_pool):
            app = app_main.create_app()
            async with app.router.lifespan_context(app):
                self.assertEqual(created_kwargs.get("min_size"), 5)
                self.assertEqual(created_kwargs.get("max_size"), 42)
                self.assertEqual(created_kwargs.get("timeout"), 7.5)


if __name__ == "__main__":
    unittest.main()
