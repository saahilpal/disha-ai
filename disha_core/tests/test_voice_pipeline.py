"""Automated test suite for Disha AI voice pipeline and Qwen3-TTS synthesis engine."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import httpx

import disha_core.main as app_main
from disha_core.models.schemas import TurnRequest, TurnState
from disha_core.pipeline.validator import SentenceValidator
from disha_core.voice import (
    ENGLISH_VOICE,
    HINDI_VOICE,
    QWEN3_DEFAULT_MODEL,
    QWEN3_DEFAULT_VOICE,
    VoicePrivacyError,
    VoiceSession,
    detect_turn_language,
    execute_voice_turn,
    is_hindi_turn,
    is_silence_hallucination,
    is_silent_audio,
    normalize_hinglish_phonetics,
    route_tts,
    select_tts_voice,
    stream_qwen3_tts,
    synthesize_speech_stream,
    transcribe_groq,
)


class MockStreamResponse:
    """Mock for httpx streaming HTTP response."""

    def __init__(self, chunks: list[bytes], status_code: int = 200) -> None:
        self.chunks = chunks
        self.status_code = status_code

    async def aiter_bytes(self):
        for chunk in self.chunks:
            yield chunk

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class MockQwenClient:
    """Mock httpx.AsyncClient for Qwen3-TTS tests."""

    def __init__(
        self,
        chunks: list[bytes] | None = None,
        status_code: int = 200,
        should_fail: bool = False,
    ) -> None:
        self.chunks = chunks or [b"\xff\xfb\x90\x44audio1", b"\xff\xfb\x90\x44audio2"]
        self.status_code = status_code
        self.should_fail = should_fail
        self.last_request: dict | None = None

    def stream(self, method: str, url: str, **kwargs):
        if self.should_fail:
            raise httpx.ConnectError("Failed to connect to Qwen3-TTS endpoint")
        self.last_request = {"method": method, "url": url, **kwargs}
        return MockStreamResponse(self.chunks, self.status_code)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class VoicePipelineTests(IsolatedAsyncioTestCase):
    """Unit and integration tests for the unified Voice & Qwen3-TTS pipeline."""

    async def test_qwen3_tts_audio_generation(self) -> None:
        """Verify Qwen3-TTS client formats request correctly and streams audio chunks."""
        client = MockQwenClient(chunks=[b"chunk_a", b"chunk_b"])

        chunks = []
        async for chunk in stream_qwen3_tts(
            "Warm jeera water lein.",
            client_factory=lambda **_: client,
            endpoint_url="http://test-qwen-tts:8880/v1/audio/speech",
        ):
            chunks.append(chunk)

        self.assertEqual(chunks, [b"chunk_a", b"chunk_b"])
        self.assertIsNotNone(client.last_request)
        self.assertEqual(client.last_request["url"], "http://test-qwen-tts:8880/v1/audio/speech")
        payload = client.last_request["json"]
        self.assertEqual(payload["model"], QWEN3_DEFAULT_MODEL)
        self.assertEqual(payload["voice"], QWEN3_DEFAULT_VOICE)
        self.assertTrue(payload["stream"])
        self.assertIn("jeera", payload["input"])

    async def test_qwen3_tts_privacy_check(self) -> None:
        """Verify Qwen3-TTS fails closed if health data egress is not approved."""
        with patch.dict("os.environ", {
            "QWEN3_TTS_HEALTH_DATA_PROCESSING_APPROVED": "false",
            "TTS_HEALTH_DATA_PROCESSING_APPROVED": "false",
        }):
            with self.assertRaises(VoicePrivacyError):
                async for _ in stream_qwen3_tts("Jeera water lein."):
                    pass

    async def test_qwen3_tts_fallback_to_edge_tts(self) -> None:
        """Verify graceful fallback to Edge-TTS when Qwen3-TTS service is unreachable."""
        failing_client = MockQwenClient(should_fail=True)

        async def fake_edge_tts(text: str, voice: str):
            yield b"edge_audio_chunk"

        with patch("disha_core.voice.stream_edge_tts", side_effect=fake_edge_tts):
            chunks = []
            async for chunk in synthesize_speech_stream(
                "Aap aaram karein.",
                client_factory=lambda **_: failing_client,
            ):
                chunks.append(chunk)

            self.assertEqual(chunks, [b"edge_audio_chunk"])

    def test_hinglish_phonetic_normalization(self) -> None:
        """Verify Hinglish phonetic normalizer handles Indian remedy words and clinical homographs."""
        raw_text = "Namaste! Aap **jeera** aur saunf water lein aur pet dard mein aaram karein."
        normalized = normalize_hinglish_phonetics(raw_text)

        # Markdown asterisks stripped
        self.assertNotIn("**", normalized)
        # Indian English / Roman Hindi remedy terms preserved
        self.assertIn("jeera", normalized)
        self.assertIn("saunf", normalized)
        self.assertIn("karein", normalized)
        self.assertIn("Namaste", normalized)
        # Clinical homograph 'pet' (stomach) converted to avoid English /pɛt/ mispronunciation
        self.assertIn("peyt dard", normalized)

    def test_voice_selection_rules(self) -> None:
        """Verify select_tts_voice chooses Hindi or English voice accurately."""
        self.assertEqual(select_tts_voice("Hello doctor, I have an appointment", "en-IN"), ENGLISH_VOICE)
        self.assertEqual(select_tts_voice("Aap kaise hain? Mujhe saunf water lena hai"), HINDI_VOICE)
        self.assertEqual(select_tts_voice("नमस्ते डॉक्टर साहब"), HINDI_VOICE)

    async def test_voice_turn_context_sharing_with_chat(self) -> None:
        """Verify voice turns share and persist conversation history across chat and voice mediums."""
        history_storage: dict[str, list[dict[str, str]]] = {
            "patient-42": [
                {"role": "user", "content": "Mujhe gas aur pet dard hai."},
                {"role": "assistant", "content": "Aap halka khana lein aur thoda paani peeyein."},
            ]
        }

        # Setup mock app state
        received_messages: list[dict[str, str]] = []

        class MockLLM:
            def stream(self, prompt: str, messages: list[dict[str, str]] | None = None):
                if messages:
                    received_messages.extend(messages)

                async def token_gen():
                    yield "Aap warm jeera water lejiye. Yeh pet ke liye accha hai."

                return token_gen()

        class MockTx:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class MockConnection:
            def transaction(self):
                return MockTx()

            async def fetchrow(self, *args, **kwargs):
                return {"activity_permissions": "all"}

            async def fetchval(self, *args, **kwargs):
                return None

            async def fetch(self, *args, **kwargs):
                return []

        class MockPool:
            async def fetchrow(self, *args, **kwargs):
                return {"activity_permissions": "all"}

            async def fetchval(self, *args, **kwargs):
                return None

            async def fetch(self, *args, **kwargs):
                return []

            def acquire(self):
                class AcquireCtx:
                    async def __aenter__(self):
                        return MockConnection()

                    async def __aexit__(self, *args):
                        pass

                return AcquireCtx()

        mock_state = SimpleNamespace(
            router=SimpleNamespace(route=lambda text: (SimpleNamespace(triggered=False), None)),
            today_ist=lambda: "monday",
            pool=MockPool(),
            validator=SentenceValidator(),
            llm=MockLLM(),
            conversation_history=history_storage,
            sync_history=False,
            ledger=None,
        )
        mock_ws = SimpleNamespace(app=SimpleNamespace(state=mock_state))

        # 1. Voice Turn
        voice_audio_received = []

        async def mock_send_audio(chunk: bytes):
            voice_audio_received.append(chunk)

        async def fake_tts_synthesizer(text: str, voice: str):
            yield b"voice_output_audio"

        session = VoiceSession(synthesizer=fake_tts_synthesizer)

        sentences = await execute_voice_turn(
            mock_ws,
            "patient-42",
            "Kya main daliya kha sakta hoon?",
            session,
            send_audio=mock_send_audio,
        )

        self.assertTrue(len(sentences) > 0)
        self.assertEqual(len(voice_audio_received), len(sentences))

        # Check that the voice turn received the previous chat turns in messages!
        self.assertEqual(len(received_messages), 2)
        self.assertEqual(received_messages[0]["content"], "Mujhe gas aur pet dard hai.")

        # Check that the voice turn was appended to patient-42's conversation history!
        patient_hist = history_storage["patient-42"]
        self.assertEqual(len(patient_hist), 4)
        self.assertEqual(patient_hist[2]["role"], "user")
        self.assertEqual(patient_hist[2]["content"], "Kya main daliya kha sakta hoon?")
        self.assertEqual(patient_hist[3]["role"], "assistant")
        self.assertIn("jeera", patient_hist[3]["content"])

        # 2. Subsequent Chat Turn verifies history contains the voice turn
        received_messages.clear()
        chat_state = TurnState()
        chat_turn = TurnRequest(text="Aur saunf water?")

        chat_sentences = [
            s async for s in app_main._turn_sentences(mock_ws, "patient-42", chat_turn, chat_state)
        ]
        self.assertTrue(len(chat_sentences) > 0)

        # The chat turn now saw 4 previous turns (2 chat + 2 voice)!
        self.assertEqual(len(received_messages), 4)
        self.assertEqual(received_messages[2]["content"], "Kya main daliya kha sakta hoon?")

    async def test_barge_in_cancellation_handling(self) -> None:
        """Verify barge-in promptly cancels the active speech synthesis task without leaks."""
        started_event = asyncio.Event()
        cancelled_event = asyncio.Event()

        async def long_stream(text: str, voice: str):
            started_event.set()
            try:
                while True:
                    yield b"infinite_audio_chunk"
                    await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                cancelled_event.set()
                raise

        session = VoiceSession(synthesizer=long_stream)

        async def mock_send(b):
            pass

        speak_task = asyncio.create_task(session.speak("Long utterance", mock_send))
        await started_event.wait()

        # Trigger barge-in
        await session.barge_in()
        try:
            await speak_task
        except asyncio.CancelledError:
            pass

        self.assertTrue(cancelled_event.is_set())
        self.assertIsNone(session._active)

    def test_whisper_silence_and_hallucination_filtering(self) -> None:
        """Verify whisper silence, YouTube outros, and credit hallucinations are rejected."""
        # Hallucinations that must be filtered out
        hallucinations = [
            "Thank you for watching",
            "Thank you for watching this video",
            "Thanks for watching!",
            "Please like and subscribe to my channel",
            "Subtitles by the Amara.org community",
            "Subtitles by OpenSubtitles",
            "Transcribed by https://otter.ai",
            "Obrigado pela atencao",
            "Muchas gracias por ver",
            "Merci beaucoup",
            "See you in the next video",
            "Welcome back to my channel",
            "[music]",
            "(applause)",
            "...",
            "",
            "   ",
        ]
        for phrase in hallucinations:
            self.assertTrue(
                is_silence_hallucination(phrase),
                f"Expected '{phrase}' to be detected as hallucination",
            )

        # Valid clinical queries that must NOT be filtered
        valid_queries = [
            "Mujhe pet mein jalan aur dard ho raha hai",
            "Kya main saunf water le sakta hoon?",
            "BP 140/90 hai, kya dawai loon?",
            "Khichdi khane ke baad vomiting jaisa lag raha hai",
            "112 par call kab karni chahiye?",
        ]
        for query in valid_queries:
            self.assertFalse(
                is_silence_hallucination(query),
                f"Valid query '{query}' was incorrectly flagged as hallucination",
            )

    def test_silent_audio_detection(self) -> None:
        """Verify empty and zero-energy silent audio frames are flagged for dropping."""
        # Empty and sub-threshold bytes
        self.assertTrue(is_silent_audio(b""))
        self.assertTrue(is_silent_audio(b"short"))
        # 1024 zero bytes (silence)
        self.assertTrue(is_silent_audio(b"\x00" * 1024))
        # Simulated PCM silence WAV (44-byte header + 1000 zero samples)
        wav_header = b"RIFF" + (1044).to_bytes(4, "little") + b"WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data" + (1000).to_bytes(4, "little")
        silent_wav = wav_header + b"\x00" * 1000
        self.assertTrue(is_silent_audio(silent_wav))

        # Audio with non-zero bytes
        active_audio = b"\x1a\x45\xdf\xa3" + bytes(range(256))
        self.assertFalse(is_silent_audio(active_audio))

    async def test_transcribe_groq_drops_silent_audio(self) -> None:
        """Verify transcribe_groq rejects silent audio without attempting network egress."""
        with patch.dict("os.environ", {
            "GROQ_HEALTH_DATA_PROCESSING_APPROVED": "true",
            "GROQ_API_KEY": "gsk-mock-key-for-test",
        }):
            with self.assertRaises(RuntimeError) as ctx:
                await transcribe_groq(b"\x00" * 512)
            self.assertIn("silent audio frame", str(ctx.exception))

    def test_websocket_voice_silence_frame_handling(self) -> None:
        """Verify WebSocket /voice drops silent audio frames cleanly with silence message."""
        from fastapi.testclient import TestClient
        app = app_main.create_app()

        with patch.dict("os.environ", {
            "GROQ_HEALTH_DATA_PROCESSING_APPROVED": "true",
            "GROQ_API_KEY": "gsk-mock-key-for-test",
        }), patch.object(app_main, "_authenticated_patient", return_value="pt_voice_test"):
            client = TestClient(app)
            with client.websocket_connect("/voice?token=valid_tok") as ws:
                # Send empty/silent audio bytes (all zeros)
                ws.send_bytes(b"\x00" * 512)
                resp = ws.receive_json()
                self.assertEqual(resp, {"type": "silence", "message": "Silence detected"})

    def test_websocket_voice_text_turn_and_context_persistence(self) -> None:
        """Verify WebSocket voice turns are processed and persisted in shared conversation history."""
        from fastapi.testclient import TestClient
        app = app_main.create_app()

        async def mock_turn_gen(ws, patient_id, payload, state):
            state.validator_status = "validated"
            yield "Aap halki khichdi lein."

        with patch.object(app_main, "_authenticated_patient", return_value="pt_voice_shared"), \
             patch.object(app_main, "_turn_sentences", mock_turn_gen), \
             patch.object(VoiceSession, "speak", AsyncMock()):
            client = TestClient(app)
            with client.websocket_connect("/voice?token=valid_tok") as ws:
                ws.send_json({"type": "text", "text": "Mujhe pet dard hai."})
                # Expect transcript
                frame1 = ws.receive_json()
                self.assertEqual(frame1["type"], "transcript")
                # Expect sentence
                frame2 = ws.receive_json()
                self.assertEqual(frame2["type"], "sentence")
                self.assertEqual(frame2["text"], "Aap halki khichdi lein.")
                # Expect done
                frame3 = ws.receive_json()
                self.assertEqual(frame3["type"], "done")
                self.assertEqual(frame3["status"], "validated")

    def test_detect_turn_language_devanagari_and_hinglish(self) -> None:
        """Verify detect_turn_language correctly categorizes Devanagari, Hinglish, and English."""
        # Pure Devanagari
        self.assertEqual(detect_turn_language("नमस्ते! मैं दिशा हूँ"), "hi")
        self.assertEqual(detect_turn_language("बीपी 140/90 है, क्या दवा लूँ?"), "hi")

        # Romanized Hinglish with Hindi markers
        self.assertEqual(detect_turn_language("Aap warm jeera water lein aur pet dard mein aaram karein"), "hi")
        self.assertEqual(detect_turn_language("Mujhe gas aur pet dard ho raha hai"), "hi")
        self.assertEqual(detect_turn_language("Namaste doctor, kya main walk kar sakti hoon?"), "hi")
        self.assertTrue(is_hindi_turn("Aapka blood pressure kaisa hai?"))

        # English turns
        self.assertEqual(detect_turn_language("Hello doctor, I would like to schedule an appointment"), "en")
        self.assertEqual(detect_turn_language("Please consult your treating physician before altering your medication"), "en")
        self.assertFalse(is_hindi_turn("Should I take Metformin before or after meals?"))

        # Explicit language hints
        self.assertEqual(detect_turn_language("Some mixed turn", language_hint="hi-IN"), "hi")
        self.assertEqual(detect_turn_language("Some mixed turn", language_hint="en-US"), "en")

    def test_route_tts_dual_engine_policy(self) -> None:
        """Verify route_tts implements the language-routed dual engine policy."""
        # Hindi & Hinglish route to Edge-TTS hi-IN-SwaraNeural
        eng_hi, voice_hi = route_tts("Aap warm jeera water lejiye")
        self.assertEqual(eng_hi, "edge-tts")
        self.assertEqual(voice_hi, HINDI_VOICE)

        eng_dev, voice_dev = route_tts("नमस्ते डॉक्टर साहब")
        self.assertEqual(eng_dev, "edge-tts")
        self.assertEqual(voice_dev, HINDI_VOICE)

        # English routes to Qwen3-TTS
        eng_en, voice_en = route_tts("Please follow your doctor's instructions carefully")
        self.assertEqual(eng_en, "qwen3")
        self.assertEqual(voice_en, QWEN3_DEFAULT_VOICE)

        # Forced engine override
        eng_forced, voice_forced = route_tts("Aap kaise hain?", preferred_engine="qwen3")
        self.assertEqual(eng_forced, "qwen3")

        eng_forced_edge, voice_forced_edge = route_tts("Hello doctor", preferred_engine="edge-tts")
        self.assertEqual(eng_forced_edge, "edge-tts")
        self.assertEqual(voice_forced_edge, ENGLISH_VOICE)

    async def test_synthesize_speech_stream_routes_hindi_to_edge_tts(self) -> None:
        """Verify synthesize_speech_stream delegates Hindi directly to Edge-TTS under dual engine policy."""
        called_edge = False
        called_qwen = False

        async def fake_edge(text: str, voice: str):
            nonlocal called_edge
            called_edge = True
            yield b"edge_swara_bytes"

        async def fake_qwen(text: str, voice: str, **kwargs):
            nonlocal called_qwen
            called_qwen = True
            yield b"qwen_bytes"

        with patch("disha_core.voice.stream_edge_tts", side_effect=fake_edge), \
             patch("disha_core.voice.stream_qwen3_tts", side_effect=fake_qwen):
            # 1. Hindi turn should route directly to Edge-TTS
            chunks = []
            async for chunk in synthesize_speech_stream("Aap warm jeera water lein."):
                chunks.append(chunk)

            self.assertTrue(called_edge)
            self.assertFalse(called_qwen)
            self.assertEqual(chunks, [b"edge_swara_bytes"])

            # 2. English turn should route to Qwen3-TTS
            called_edge = False
            called_qwen = False
            chunks_en = []
            async for chunk in synthesize_speech_stream("Please drink water and rest."):
                chunks_en.append(chunk)

            self.assertTrue(called_qwen)
            self.assertEqual(chunks_en, [b"qwen_bytes"])

    async def test_barge_in_latency_under_50ms(self) -> None:
        """Verify barge_in cancellation executes well within 50ms stop latency."""
        import time

        started_event = asyncio.Event()

        async def infinite_synthesizer(text: str, voice: str):
            started_event.set()
            while True:
                yield b"audio_chunk"
                await asyncio.sleep(0.01)

        session = VoiceSession(synthesizer=infinite_synthesizer)

        async def mock_sink(b: bytes) -> None:
            pass

        speak_task = asyncio.create_task(session.speak("Utterance for barge-in test", mock_sink))
        await started_event.wait()

        # Measure barge-in stop latency
        t0 = time.perf_counter()
        await session.barge_in()
        try:
            await speak_task
        except asyncio.CancelledError:
            pass
        t_stop_ms = (time.perf_counter() - t0) * 1000.0

        self.assertLess(t_stop_ms, 50.0, f"Barge-in took {t_stop_ms:.2f}ms, exceeding 50ms budget")
        self.assertIsNone(session._active)

    def test_websocket_barge_in_and_interruption_event(self) -> None:
        """Verify WebSocket barge-in event cancels speech generation and sends interrupted frame."""
        from fastapi.testclient import TestClient
        app = app_main.create_app()

        async def mock_slow_turn_gen(ws, patient_id, payload, state):
            state.validator_status = "validated"
            yield "Sentence one."
            await asyncio.sleep(1.0)
            yield "Sentence two."

        with patch.object(app_main, "_authenticated_patient", return_value="pt_barge_test"), \
             patch.object(app_main, "_turn_sentences", mock_slow_turn_gen), \
             patch.object(VoiceSession, "speak", AsyncMock()):
            client = TestClient(app)
            with client.websocket_connect("/voice?token=valid_tok") as ws:
                # 1. Start a turn
                ws.send_json({"type": "text", "text": "Mujhe pet dard hai."})
                frame1 = ws.receive_json()
                self.assertEqual(frame1["type"], "transcript")
                frame2 = ws.receive_json()
                self.assertEqual(frame2["type"], "sentence")

                # 2. Trigger barge-in
                ws.send_json({"type": "barge_in"})
                interrupt_frame = ws.receive_json()
                self.assertEqual(interrupt_frame["type"], "interrupted")
