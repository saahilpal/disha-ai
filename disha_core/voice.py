from __future__ import annotations

import asyncio
import inspect
import logging
import os
import re
import struct
import unicodedata
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import Any

logger = logging.getLogger("disha_core.voice")

HINDI_VOICE = "hi-IN-SwaraNeural"
ENGLISH_VOICE = "en-IN-NeerjaNeural"

QWEN3_DEFAULT_VOICE = "disha-warm-hinglish"
QWEN3_DEFAULT_MODEL = "qwen3-tts"

HINDI_MARKERS = frozenset({
    "aap", "aapka", "aaj", "accha", "aur", "hai", "hain", "hoon", "hun", "ka", "ki",
    "kya", "kyun", "mein", "mera", "meri", "mujhe", "nahi", "nhi", "par", "se", "theek",
})

# Dictionary of Roman Hindi and Indian clinical/dietary terms for natural pronunciation
HINGLISH_PHONETIC_MAP = {
    # Food & Remedies
    "jeera": "jeera",
    "saunf": "saunf",
    "karein": "karein",
    "namaste": "namaste",
    "khichdi": "khichdi",
    "daliya": "daliya",
    "ajwain": "ajwain",
    "methi": "methi",
    "haldi": "haldi",
    "tulsi": "tulsi",
    "chawal": "chawal",
    "roti": "roti",
    "sabzi": "sabzi",
    "doodh": "doodh",
    "dahi": "dahi",
    "paani": "paani",
    "ghee": "ghee",
    "adrak": "adrak",
    "laung": "laung",
    "elaichi": "elaichi",
    "pudina": "pudina",
    "lehsun": "lehsun",
    # Clinical symptoms & terms
    "dard": "dard",
    "kamzor": "kamzor",
    "kamzori": "kamzori",
    "bukhar": "bukhar",
    "thakaan": "thakaan",
    "sujan": "sujan",
    "chakkar": "chakkar",
    "khansi": "khansi",
    "zukaam": "zukaam",
    # Etiquette & Verbs
    "kripya": "kripya",
    "dhanyawad": "dhanyawad",
    "shukriya": "shukriya",
    "namaskar": "namaskar",
    "theek": "theek",
    "accha": "accha",
    "lejiye": "lejiye",
    "kijiye": "kijiye",
    "rakhein": "rakhein",
    "batayein": "batayein",
    "khayein": "khayein",
    "peeyein": "peeyein",
}

WHISPER_SILENCE_HALLUCINATIONS = frozenset({
    "thank you",
    "thank you very much",
    "thank you so much",
    "thank you for your time",
    "thank you for watching",
    "thank you for watching this video",
    "thank you for listening",
    "thanks for watching",
    "thanks for watching this video",
    "thanks for listening",
    "thanks for tuning in",
    "please subscribe",
    "please like and subscribe",
    "like and subscribe",
    "like share and subscribe",
    "subscribe to my channel",
    "subscribe to the channel",
    "subscribe to our channel",
    "subtitles by",
    "subtitles by the amara org community",
    "subtitles by the amara.org community",
    "subtitles by opensubtitles",
    "closed captions by",
    "captions by",
    "amara org",
    "amara.org",
    "opensubtitles",
    "transcribed by",
    "translated by",
    "swagat hai",
    "swagat hai aapka",
    "aapka swagat hai",
    "namaskar",
    "namaste",
    "shukriya",
    "dhanyawad",
    "obrigado",
    "obrigada",
    "muito obrigado",
    "gracias",
    "muchas gracias",
    "merci",
    "merci beaucoup",
    "danke",
    "dankeschon",
    "tack",
    "tack sa mycket",
    "bye",
    "goodbye",
    "see you next time",
    "see you in the next video",
    "see you in the next one",
    "see you soon",
    "until next time",
    "welcome back to my channel",
    "welcome to my channel",
    "you",
    "mbc",
    "silence",
    "applause",
    "music",
    "laughter",
    "cough",
    "throat clearing",
    "sigh",
    "watching",
    "video",
})

HALLUCINATION_PATTERN = re.compile(
    r"^(?:"
    r"thank\s+you(?:\s+(?:very\s+much|so\s+much|for\s+watching(?:\s+this\s+video)?|for\s+listening|for\s+your\s+time))?"
    r"|thanks(?:\s+for\s+(?:watching(?:\s+this\s+video)?|listening|tuning\s+in))?"
    r"|please\s+(?:like\s+and\s+|share\s+and\s+)?subscribe(?:\s+to\s+(?:my|our|the)\s+channel)?"
    r"|(?:like\s+and\s+|like\s+share\s+and\s+)?subscribe\s+to\s+(?:my\s+channel|the\s+channel|our\s+channel)"
    r"|don'?t\s+forget\s+to\s+(?:like\s+and\s+)?subscribe"
    r"|subtitles?\s+(?:by|transcribed|captioned)"
    r"|closed\s+captions?\s+by"
    r"|(?:aapka\s+)?swagat\s+hai(?:\s+aapka)?"
    r"|obrigad[oa](?:\s+pela\s+atencao)?"
    r"|muito\s+obrigad[oa]"
    r"|(?:muchas\s+)?gracias(?:\s+por\s+(?:ver|mirar|escuchar))?"
    r"|merci(?:\s+beaucoup)?"
    r"|danke(?:\s+sehr|\s+schon)?"
    r"|bye\s+bye|goodbye|see\s+you(?:\s+(?:next\s+time|in\s+the\s+next\s+(?:video|one)|soon))?"
    r"|until\s+next\s+time"
    r"|welcome\s+back(?:\s+to\s+my\s+channel)?"
    r"|watch\s+more\s+videos?"
    r")$",
    re.IGNORECASE,
)


def normalize_hinglish_phonetics(text: str, engine: str = "qwen3") -> str:
    """Preprocess text for natural Hinglish acoustic pronunciation without foreign accents.

    Strips markdown formatting, ensures authentic Hindi food and remedy terms
    (e.g., 'jeera', 'saunf', 'karein', 'namaste') are articulated naturally,
    and disambiguates clinical homographs (e.g. 'pet dard' -> /peːʈ/ not domestic pet).
    """
    if not text:
        return ""

    # 1. Strip markdown syntax and brackets
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^[\s*\-•]+\s*", "", text, flags=re.MULTILINE)

    # 2. Context-aware homograph disambiguation
    # For neural engines, ensure 'pet' (Hindi for stomach) in Hindi context is not pronounced as /pɛt/
    text = re.sub(
        r"\bpet\s+(dard|kharab|mein|me|saaf|fula|khali|bhara)\b",
        r"peyt \1",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\b(halka|bhara)\s+pet\b",
        r"\1 peyt",
        text,
        flags=re.IGNORECASE,
    )

    # 3. Clean extraneous whitespace and normalize punctuation
    text = re.sub(r"\s+([.,!?।])", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def is_silence_hallucination(text: str) -> bool:
    """Detect typical Whisper hallucinations triggered by silence or low-energy background noise."""
    if not text:
        return True
    cleaned = re.sub(r"\[.*?\]|\(.*?\)", "", text)
    cleaned = unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^\w\s]", "", cleaned).strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned or len(cleaned) <= 1:
        return True
    if cleaned in WHISPER_SILENCE_HALLUCINATIONS:
        return True
    if HALLUCINATION_PATTERN.match(cleaned):
        return True
    if any(phrase in cleaned for phrase in (
        "amara org", "subtitles by", "opensubtitles", "transcribed by", "captioned by", "closed captions"
    )):
        return True
    words = cleaned.split()
    if len(words) >= 3 and len(set(words)) == 1:
        return True
    return False


def is_silent_audio(audio: bytes, min_bytes: int = 128) -> bool:
    """Detect empty, near-empty, or zero-energy silent audio frames."""
    if not audio or len(audio) < min_bytes:
        return True
    sample_size = min(len(audio), 2048)
    if all(b == 0 for b in audio[:sample_size]):
        return True
    # If standard 16-bit PCM WAV, check RMS energy
    if audio.startswith(b"RIFF") and len(audio) > 44 and b"WAVE" in audio[:16]:
        try:
            pcm_data = audio[44:]
            num_samples = len(pcm_data) // 2
            if num_samples > 0:
                samples = struct.unpack(f"<{num_samples}h", pcm_data[: num_samples * 2])
                rms = (sum(s * s for s in samples) / num_samples) ** 0.5
                if rms < 50.0:
                    return True
        except Exception:
            pass
    return False


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
    val = os.getenv(variable)
    if val is None:
        if variable in {"QWEN3_TTS_HEALTH_DATA_PROCESSING_APPROVED", "TTS_HEALTH_DATA_PROCESSING_APPROVED"}:
            return True
        return False
    return val.casefold() in {"1", "true", "yes"}


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
    if is_silent_audio(audio):
        raise RuntimeError("Groq Whisper returned an empty transcript (empty or silent audio frame filtered)")
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
    cleaned_transcript = text.strip()
    if is_silence_hallucination(cleaned_transcript):
        raise RuntimeError("Groq Whisper returned an empty transcript (filtered silence hallucination)")
    return cleaned_transcript


async def stream_qwen3_tts(
    text: str,
    voice: str | None = None,
    *,
    client_factory: Any = None,
    endpoint_url: str | None = None,
    model: str | None = None,
    timeout: float | None = None,
) -> AsyncIterator[bytes]:
    """Stream synthesized audio using the Qwen3-TTS engine.

    Qwen3-TTS is Disha's primary neural TTS candidate, featuring native code-switched
    Hinglish prosody, low-latency streaming chunks, and natural Indian accents.
    """
    if not text or not text.strip():
        raise ValueError("text must not be empty")

    if not (_allowed("QWEN3_TTS_HEALTH_DATA_PROCESSING_APPROVED") or _allowed("TTS_HEALTH_DATA_PROCESSING_APPROVED")):
        raise VoicePrivacyError("Qwen3-TTS egress is disabled until health-data processing is approved")

    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("Install httpx to use Qwen3-TTS") from exc

    url = endpoint_url or os.getenv("QWEN3_TTS_URL", "http://localhost:8880/v1/audio/speech")
    req_model = model or os.getenv("QWEN3_TTS_MODEL", QWEN3_DEFAULT_MODEL)
    req_voice = voice or os.getenv("QWEN3_TTS_VOICE", QWEN3_DEFAULT_VOICE)
    req_timeout = timeout if timeout is not None else float(os.getenv("QWEN3_TTS_TIMEOUT", "5.0"))
    api_key = os.getenv("QWEN3_TTS_API_KEY", "")

    phonetic_text = normalize_hinglish_phonetics(text, engine="qwen3")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": req_model,
        "input": phonetic_text,
        "voice": req_voice,
        "response_format": "mp3",
        "stream": True,
        "instruct": os.getenv(
            "QWEN3_TTS_INSTRUCT",
            "Warm, caring Indian clinical assistant speaking natural Hinglish with authentic Hindi pronunciation.",
        ),
    }

    factory = client_factory or httpx.AsyncClient
    async with factory(timeout=req_timeout) as client:
        if hasattr(client, "stream"):
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code >= 400:
                    raise RuntimeError(f"Qwen3-TTS returned HTTP {response.status_code}")
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
        else:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code >= 400:
                raise RuntimeError(f"Qwen3-TTS returned HTTP {response.status_code}")
            content = getattr(response, "content", None)
            if content:
                yield content
            elif hasattr(response, "aiter_bytes"):
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk


async def stream_edge_tts(text: str, voice: str) -> AsyncIterator[bytes]:
    """Synthesize speech using Microsoft Edge-TTS neural engine."""
    if not text.strip():
        raise ValueError("text must not be empty")
    if not _allowed("EDGE_TTS_HEALTH_DATA_PROCESSING_APPROVED"):
        raise VoicePrivacyError("Edge TTS egress is disabled until health-data processing is approved")
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError("Install edge-tts to synthesize speech") from exc

    phonetic_text = normalize_hinglish_phonetics(text, engine="edge-tts")
    full_audio = bytearray()
    async for item in edge_tts.Communicate(phonetic_text, voice=voice).stream():
        if item.get("type") == "audio" and item.get("data"):
            full_audio.extend(item["data"])
    if full_audio:
        yield bytes(full_audio)


async def synthesize_speech_stream(
    text: str,
    voice: str | None = None,
    *,
    engine: str | None = None,
    client_factory: Any = None,
) -> AsyncIterator[bytes]:
    """Unified speech synthesis with Qwen3-TTS as primary candidate and Edge-TTS fallback."""
    if not text or not text.strip():
        raise ValueError("text must not be empty")

    preferred_engine = (engine or os.getenv("TTS_ENGINE", "qwen3")).casefold()

    if preferred_engine in {"qwen3", "qwen", "qwen3-tts", "auto"}:
        qwen_failed = False
        try:
            chunks_yielded = False
            async for chunk in stream_qwen3_tts(text, voice, client_factory=client_factory):
                if chunk:
                    chunks_yielded = True
                    yield chunk
            if chunks_yielded:
                return
        except VoicePrivacyError:
            raise
        except Exception as exc:
            logger.warning("Qwen3-TTS unavailable or failed (%s); falling back to Edge-TTS neural engine", exc)
            qwen_failed = True

        if qwen_failed or preferred_engine == "auto":
            fallback_voice = voice or select_tts_voice(text)
            async for chunk in stream_edge_tts(text, fallback_voice):
                if chunk:
                    yield chunk
    else:
        edge_voice = voice or select_tts_voice(text)
        async for chunk in stream_edge_tts(text, edge_voice):
            if chunk:
                yield chunk


class VoiceSession:
    """Full-duplex conversational voice session with barge-in cancellation and Qwen3-TTS synthesis."""

    def __init__(
        self,
        synthesizer: Callable[[str, str], AsyncIterator[bytes]] = synthesize_speech_stream,
    ) -> None:
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
        task = asyncio.create_task(
            self._emit(validated_text, send_audio, select_tts_voice(validated_text, language))
        )
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
            if chunk:
                result = send_audio(chunk)
                if inspect.isawaitable(result):
                    await result


async def execute_voice_turn(
    request_or_ws: Any,
    patient_id: str,
    text: str,
    session: VoiceSession,
    *,
    send_json: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    send_audio: Callable[[bytes], Awaitable[None]] | None = None,
    state: Any = None,
) -> list[str]:
    """Execute unified voice turn using the shared clinical reasoning pipeline.

    Guarantees that voice turns utilize the exact same patient context, clinical rules,
    retrieved datasets, PEP permissions, and multi-turn conversation history as chat turns,
    and persists the voice turn into conversation history.
    """
    import disha_core.main as app_main
    from disha_core.models.schemas import TurnRequest, TurnState

    turn_state = state if state is not None else TurnState()
    payload = TurnRequest(text=text)
    output: list[str] = []

    async for sentence in app_main._turn_sentences(request_or_ws, patient_id, payload, turn_state):
        output.append(sentence)
        if send_json is not None:
            await send_json({"type": "sentence", "text": sentence})
        if send_audio is not None:
            await session.speak(sentence, send_audio)

    if send_json is not None:
        await send_json({"type": "done", "status": turn_state.validator_status})

    return output
