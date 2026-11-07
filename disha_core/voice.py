from __future__ import annotations

import asyncio
import inspect
import os
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import Any

HINDI_VOICE = "hi-IN-SwaraNeural"
ENGLISH_VOICE = "en-IN-NeerjaNeural"
HINDI_MARKERS = frozenset({
    "aap", "aapka", "aaj", "accha", "aur", "hai", "hain", "hoon", "hun", "ka", "ki",
    "kya", "kyun", "mein", "mera", "meri", "mujhe", "nahi", "nhi", "par", "se", "theek",
})


class VoicePrivacyError(RuntimeError):
    pass


def select_tts_voice(text: str, language: str | None = None) -> str:
    """Choose a voice from ASR language metadata or the text's dominant script."""
    if language:
        code = language.casefold()
        if code.startswith(("hi", "hing", "hng")):
            return HINDI_VOICE
        if code.startswith("en"):
            return ENGLISH_VOICE
    letters = [char for char in text if char.isalpha()]
    devanagari = sum("\u0900" <= char <= "\u097f" for char in letters)
    if letters and devanagari / len(letters) >= 0.15:
        return HINDI_VOICE
    words = set(re.findall(r"(?u)\b[\w']+\b", text.casefold()))
    return HINDI_VOICE if len(words & HINDI_MARKERS) >= 2 else ENGLISH_VOICE


def _allowed(variable: str) -> bool:
    return os.getenv(variable, "").casefold() in {"1", "true", "yes"}


async def transcribe_groq(
    audio: bytes,
    *,
    filename: str = "turn.webm",
    content_type: str = "audio/webm",
    client_factory: Any = None,
) -> str:
    """Transcribe a completed utterance; live audio must be buffered by the caller."""
    if not audio:
        raise ValueError("audio must not be empty")
    if not _allowed("GROQ_HEALTH_DATA_PROCESSING_APPROVED"):
        raise VoicePrivacyError("Groq audio egress is disabled until health-data processing is approved")
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not configured")
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("Install httpx to use Groq Whisper") from exc
    factory = client_factory or httpx.AsyncClient
    timeout = float(os.getenv("VOICE_TRANSCRIBE_TIMEOUT", "8.0"))
    async with factory(timeout=timeout) as client:
        response = await client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            files={"file": (filename, audio, content_type)},
            data={"model": os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo"), "response_format": "json"},
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Groq Whisper returned HTTP {response.status_code}")
    try:
        text = response.json()["text"]
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("Groq Whisper returned an invalid transcription response") from exc
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("Groq Whisper returned an empty transcript")
    return text.strip()


async def stream_edge_tts(text: str, voice: str) -> AsyncIterator[bytes]:
    if not text.strip():
        raise ValueError("text must not be empty")
    if not _allowed("EDGE_TTS_HEALTH_DATA_PROCESSING_APPROVED"):
        raise VoicePrivacyError("Edge TTS egress is disabled until health-data processing is approved")
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError("Install edge-tts to synthesize speech") from exc
    async for item in edge_tts.Communicate(text, voice=voice).stream():
        if item.get("type") == "audio" and item.get("data"):
            yield item["data"]


class VoiceSession:
    """A barge-in cancels the active Edge-TTS stream before a new turn starts."""

    def __init__(self, synthesizer: Callable[[str, str], AsyncIterator[bytes]] = stream_edge_tts) -> None:
        self._synthesizer = synthesizer
        self._active: asyncio.Task[None] | None = None

    async def speak(
        self,
        validated_text: str,
        send_audio: Callable[[bytes], Awaitable[None]],
        *,
        language: str | None = None,
    ) -> None:
        await self.barge_in()
        task = asyncio.create_task(self._emit(validated_text, send_audio, select_tts_voice(validated_text, language)))
        self._active = task
        try:
            await task
        finally:
            if self._active is task:
                self._active = None

    async def barge_in(self) -> None:
        task, self._active = self._active, None
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def _emit(
        self,
        text: str,
        send_audio: Callable[[bytes], Awaitable[None]],
        voice: str,
    ) -> None:
        async for chunk in self._synthesizer(text, voice):
            result = send_audio(chunk)
            if inspect.isawaitable(result):
                await result
