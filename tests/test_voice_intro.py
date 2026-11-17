import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
import disha_core.main as app_main
from disha_core.voice import VoiceSession, get_intro_greeting


def test_get_intro_greeting_all_languages():
    for lang, expected_substr in [
        ("hinglish", "AI health coach"),
        ("en", "AI health coach"),
        ("hi", "एआई हेल्थ कोच"),
    ]:
        text, audio_bytes = get_intro_greeting(lang)
        assert expected_substr in text, f"Expected '{expected_substr}' in '{text}'"
        assert audio_bytes is not None, f"Audio bytes missing for language {lang}"
        assert len(audio_bytes) < 100 * 1024, f"Audio file exceeded 100 KB: {len(audio_bytes)} bytes"


def test_websocket_start_call_emits_intro_and_onboarding():
    app = app_main.create_app()

    with (
        patch.object(app_main, "_authenticated_patient", return_value="pt_test_intro"),
        patch.object(VoiceSession, "speak", AsyncMock()),
    ):
        client = TestClient(app)
        with client.websocket_connect("/voice?token=valid_tok") as ws:
            ws.send_json({"type": "start_call", "language": "hinglish"})
            # 1. First frame: intro json
            frame1 = ws.receive_json()
            assert frame1["type"] == "intro"
            assert "AI health coach" in frame1["text"]
            assert frame1["language"] == "hinglish"

            # 2. Second frame: binary audio bytes
            audio_frame = ws.receive_bytes()
            assert len(audio_frame) > 0
            assert len(audio_frame) < 100 * 1024

            # 3. Subsequent frames: ready_to_listen (or question if db present)
            next_frame = ws.receive_json()
            assert next_frame["type"] in ("question", "ready_to_listen")
