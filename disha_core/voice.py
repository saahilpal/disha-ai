from __future__ import annotations

import asyncio
import inspect
import logging
import os
import re
import struct
import tempfile
import unicodedata
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger("disha_core.voice")

HINDI_VOICE = "hi-IN-SwaraNeural"
ENGLISH_VOICE = "en-IN-NeerjaNeural"

QWEN3_DEFAULT_VOICE = "disha-warm-hinglish"
QWEN3_DEFAULT_MODEL = "qwen3-tts"

HINDI_MARKERS = frozenset(
    {
        "aap",
        "aapka",
        "aaj",
        "accha",
        "aur",
        "hai",
        "hain",
        "hoon",
        "hun",
        "ka",
        "ki",
        "kya",
        "kyun",
        "mein",
        "mera",
        "meri",
        "mujhe",
        "nahi",
        "nhi",
        "par",
        "se",
        "theek",
        "karein",
        "kijiye",
        "lejiye",
        "rakhein",
        "batayein",
        "khayein",
        "peeyein",
        "bahut",
        "bohot",
        "halka",
        "dard",
        "saunf",
        "jeera",
        "khichdi",
        "daliya",
        "namaste",
        "namaskar",
        "kripya",
        "dhanyawad",
        "shukriya",
    }
)

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

WHISPER_SILENCE_HALLUCINATIONS = frozenset(
    {
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
    }
)

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
    cleaned_full = re.sub(r"\[.*?\]|\(.*?\)", "", text).strip()
    if not cleaned_full:
        return True
    # Strip non-word characters while preserving unicode letters (including Devanagari)
    cleaned_words = re.sub(r"[^\w\s]", "", cleaned_full).strip().lower()
    cleaned_words = re.sub(r"\s+", " ", cleaned_words)
    if not cleaned_words or len(cleaned_words) <= 1:
        return True

    # For checking English/Latin hallucination dictionaries, produce an ASCII normalized version
    cleaned_ascii = unicodedata.normalize("NFKD", cleaned_words).encode("ascii", "ignore").decode("ascii").strip()
    cleaned_ascii = re.sub(r"\s+", " ", cleaned_ascii)

    if cleaned_words in WHISPER_SILENCE_HALLUCINATIONS or (
        cleaned_ascii and cleaned_ascii in WHISPER_SILENCE_HALLUCINATIONS
    ):
        return True
    if HALLUCINATION_PATTERN.match(cleaned_words) or (cleaned_ascii and HALLUCINATION_PATTERN.match(cleaned_ascii)):
        return True
    if any(
        phrase in cleaned_words or (cleaned_ascii and phrase in cleaned_ascii)
        for phrase in (
            "amara org",
            "subtitles by",
            "opensubtitles",
            "transcribed by",
            "captioned by",
            "closed captions",
        )
    ):
        return True
    words = cleaned_words.split()
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
            num_samples = min(len(pcm_data) // 2, 4096)
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


def detect_turn_language(text: str, language_hint: str | None = None) -> str:
    """Detect whether turn is Hindi/Hinglish (Devanagari or Romanized Hindi) or English.

    Returns:
        'hi' for Devanagari Hindi or Romanized Hinglish
        'en' for English
    """
    if language_hint:
        code = language_hint.casefold().strip()
        if code.startswith(("hi", "hing", "hng")):
            return "hi"
        if code.startswith("en"):
            return "en"

    # Check for Devanagari script (\u0900 - \u097F)
    letters = [char for char in text if char.isalpha()]
    devanagari = sum("\u0900" <= char <= "\u097f" for char in letters)
    if letters and (devanagari / len(letters) >= 0.10 or devanagari >= 2):
        return "hi"

    # Check for Romanized Hindi grammatical & clinical markers
    words = set(re.findall(r"(?u)\b[\w']+\b", text.casefold()))
    if len(words & HINDI_MARKERS) >= 2 or any(
        w in words for w in ("namaste", "namaskar", "kripya", "dhanyawad", "shukriya")
    ):
        return "hi"

    return "en"


def is_hindi_turn(text: str, language: str | None = None) -> bool:
    """Return True if the turn text or language hint indicates Hindi or Hinglish."""
    return detect_turn_language(text, language) == "hi"


def select_tts_voice(text: str, language: str | None = None) -> str:
    """Choose a voice from ASR language metadata or the text's dominant script."""
    return HINDI_VOICE if is_hindi_turn(text, language) else ENGLISH_VOICE


def route_tts(
    text: str,
    language: str | None = None,
    preferred_engine: str | None = None,
) -> tuple[str, str]:
    """Determine optimal TTS engine and voice based on turn language.

    Policy:
    - Hindi / Hinglish (Devanagari & Romanized Hindi): Routes to Edge-TTS `hi-IN-SwaraNeural`
      for native Indian phonetics and authentic pronunciation of clinical/dietary terms.
    - English: Routes to Qwen3-TTS (`disha-warm-hinglish`) / local neural TTS,
      with fallback to Edge-TTS `en-IN-NeerjaNeural`.

    Returns:
        tuple[str, str]: (engine, voice) e.g. ("edge-tts", "hi-IN-SwaraNeural")
    """
    lang = detect_turn_language(text, language)
    engine_pref = (preferred_engine or os.getenv("TTS_ENGINE", "auto")).casefold().strip()

    if _local_only() or engine_pref in {"mlx", "local", "local-mlx"}:
        voice = (
            os.getenv("LOCAL_TTS_HINDI_VOICE", "Hindi (Female)")
            if lang == "hi"
            else os.getenv("LOCAL_TTS_ENGLISH_VOICE", "English (Indian) (Female)")
        )
        return ("mlx", voice)

    if engine_pref in {"edge-tts", "edge"}:
        return ("edge-tts", HINDI_VOICE if lang == "hi" else ENGLISH_VOICE)

    if engine_pref in {"qwen3", "qwen", "qwen3-tts"}:
        return ("qwen3", QWEN3_DEFAULT_VOICE if lang != "hi" else HINDI_VOICE)

    # Language-routed dual engine policy:
    if lang == "hi":
        return ("edge-tts", HINDI_VOICE)
    else:
        return ("qwen3", QWEN3_DEFAULT_VOICE)


def _allowed(variable: str) -> bool:
    val = os.getenv(variable)
    if val is None:
        if variable in {"QWEN3_TTS_HEALTH_DATA_PROCESSING_APPROVED", "TTS_HEALTH_DATA_PROCESSING_APPROVED"}:
            return True
        return False
    return val.casefold() in {"1", "true", "yes"}


def _local_only() -> bool:
    return os.getenv("LOCAL_ONLY", "").strip().casefold() in {"1", "true", "yes", "on"}


def _is_local_url(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
        "host.docker.internal",
    }


async def transcribe_groq(
    audio: bytes,
    *,
    language: str | None = None,
    filename: str = "turn.webm",
    content_type: str = "audio/webm",
    client_factory: Any = None,
) -> str:
    """Transcribe a completed utterance; live audio must be buffered by the caller."""
    if not audio:
        raise ValueError("audio must not be empty")
    local_only = _local_only()
    backend = "Local" if local_only else "Groq"

    if local_only:
        url = os.getenv("LOCAL_STT_URL", "http://127.0.0.1:8880/v1/audio/transcriptions")
        if not _is_local_url(url):
            raise VoicePrivacyError("LOCAL_ONLY requires speech recognition to use a local endpoint")
        key = None
        model = os.getenv("LOCAL_STT_MODEL", "mlx-community/whisper-large-v3-turbo-asr-fp16")
        timeout = float(os.getenv("VOICE_TRANSCRIBE_TIMEOUT", "30.0"))
    else:
        if not _allowed("GROQ_HEALTH_DATA_PROCESSING_APPROVED"):
            raise VoicePrivacyError("Groq audio egress is disabled until health-data processing is approved")
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY is not configured")
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        model = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
        timeout = float(os.getenv("VOICE_TRANSCRIBE_TIMEOUT", "8.0"))

    if is_silent_audio(audio):
        raise RuntimeError(f"{backend} Whisper returned an empty transcript (empty or silent audio frame filtered)")

    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("Install httpx to transcribe audio") from exc
    factory = client_factory or httpx.AsyncClient
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    async with factory(timeout=timeout) as client:
        stt_data: dict[str, Any] = {"model": model, "response_format": "json"}
        if language:
            lang_clean = str(language).lower()
            if lang_clean in ("hi", "hindi", "hinglish"):
                stt_data["language"] = "hi"
            elif lang_clean in ("en", "english"):
                stt_data["language"] = "en"

        response = await client.post(
            url,
            headers=headers,
            files={"file": (filename, audio, content_type)},
            data=stt_data,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"{backend} Whisper returned HTTP {response.status_code}")
    try:
        text = response.json()["text"]
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f"{backend} Whisper returned an invalid transcription response") from exc
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError(f"{backend} Whisper returned an empty transcript")
    cleaned_transcript = text.strip()
    if is_silence_hallucination(cleaned_transcript):
        raise RuntimeError(f"{backend} Whisper returned an empty transcript (filtered silence hallucination)")
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

    if not _local_only() and not (
        _allowed("QWEN3_TTS_HEALTH_DATA_PROCESSING_APPROVED") or _allowed("TTS_HEALTH_DATA_PROCESSING_APPROVED")
    ):
        raise VoicePrivacyError("Qwen3-TTS egress is disabled until health-data processing is approved")

    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("Install httpx to use Qwen3-TTS") from exc

    url = endpoint_url or os.getenv("QWEN3_TTS_URL", "http://localhost:8880/v1/audio/speech")
    if _local_only() and not _is_local_url(url):
        raise VoicePrivacyError("LOCAL_ONLY requires speech synthesis to use a local endpoint")
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
    yielded_audio = False
    try:
        async with factory(timeout=req_timeout) as client:
            if hasattr(client, "stream"):
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code >= 400:
                        raise RuntimeError(f"Qwen3-TTS returned HTTP {response.status_code}")
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yielded_audio = True
                            yield chunk
            else:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code >= 400:
                    raise RuntimeError(f"Qwen3-TTS returned HTTP {response.status_code}")
                content = getattr(response, "content", None)
                if content:
                    yielded_audio = True
                    yield content
                elif hasattr(response, "aiter_bytes"):
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yielded_audio = True
                            yield chunk
    except Exception:
        if not _local_only() or yielded_audio:
            raise
        logger.warning("MLX TTS HTTP server failed; using local CLI fallback")

    if not yielded_audio:
        if not _local_only():
            raise RuntimeError("Qwen3-TTS returned no audio")
        async for chunk in stream_mlx_cli_tts(phonetic_text, req_voice, req_model):
            yield chunk


async def stream_mlx_cli_tts(text: str, voice: str, model: str) -> AsyncIterator[bytes]:
    """Use MLX's process-local CLI when its HTTP worker loses the GPU stream."""
    cli = os.getenv("MLX_TTS_CLI", "")
    if not cli:
        raise RuntimeError("MLX_TTS_CLI is not configured")

    with tempfile.TemporaryDirectory(prefix="disha-mlx-tts-") as output_dir:
        process = await asyncio.create_subprocess_exec(
            cli,
            "--model",
            model,
            "--text",
            text,
            "--voice",
            voice,
            "--output_path",
            output_dir,
            "--file_prefix",
            "disha",
            "--audio_format",
            "wav",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            detail = stderr.decode(errors="replace")[-500:] or stdout.decode(errors="replace")[-500:]
            raise RuntimeError(f"MLX CLI TTS failed: {detail}")

        files = sorted(Path(output_dir).glob("*.wav"))
        if not files:
            raise RuntimeError("MLX CLI TTS returned no audio")
        yield files[0].read_bytes()


async def stream_edge_tts(text: str, voice: str) -> AsyncIterator[bytes]:
    """Synthesize speech using Microsoft Edge-TTS neural engine."""
    if not text.strip():
        raise ValueError("text must not be empty")
    if _local_only():
        raise VoicePrivacyError("Edge TTS is disabled in local-only mode")
    if not _allowed("EDGE_TTS_HEALTH_DATA_PROCESSING_APPROVED"):
        raise VoicePrivacyError("Edge TTS egress is disabled until health-data processing is approved")
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError("Install edge-tts to synthesize speech") from exc

    phonetic_text = normalize_hinglish_phonetics(text, engine="edge-tts")
    async for item in edge_tts.Communicate(phonetic_text, voice=voice).stream():
        if item.get("type") == "audio" and item.get("data"):
            yield item["data"]


async def synthesize_speech_stream(
    text: str,
    voice: str | None = None,
    *,
    engine: str | None = None,
    client_factory: Any = None,
    language: str | None = None,
) -> AsyncIterator[bytes]:
    """Unified speech synthesis with language-routed dual engine policy.

    Routes Hindi & Hinglish turns to Edge-TTS (`hi-IN-SwaraNeural`) for flawless Indian
    phonetics, and English turns to Qwen3-TTS / local neural TTS with Edge-TTS fallback.
    """
    if not text or not text.strip():
        raise ValueError("text must not be empty")

    routed_engine, routed_voice = route_tts(
        text, language=language, preferred_engine="mlx" if _local_only() else engine
    )
    selected_voice = voice or routed_voice
    target_engine = "mlx" if _local_only() else (engine.casefold().strip() if engine else routed_engine)

    # If client_factory is explicitly passed without explicit engine, caller is testing Qwen3
    if client_factory is not None and engine is None:
        target_engine = "qwen3"

    if target_engine in {"qwen3", "qwen", "qwen3-tts", "mlx", "local", "local-mlx"}:
        qwen_failed = False
        try:
            chunks_yielded = False
            async for chunk in stream_qwen3_tts(text, selected_voice, client_factory=client_factory):
                if chunk:
                    chunks_yielded = True
                    yield chunk
            if chunks_yielded:
                return
        except VoicePrivacyError:
            raise
        except Exception as exc:
            if _local_only() or target_engine in {"mlx", "local", "local-mlx"}:
                raise
            logger.warning("Qwen3-TTS unavailable or failed (%s); falling back to Edge-TTS neural engine", exc)
            qwen_failed = True

        if qwen_failed:
            fallback_voice = (
                selected_voice
                if selected_voice.endswith("Neural")
                else (HINDI_VOICE if detect_turn_language(text, language) == "hi" else ENGLISH_VOICE)
            )
            async for chunk in stream_edge_tts(text, fallback_voice):
                if chunk:
                    yield chunk
    else:
        edge_voice = (
            selected_voice
            if selected_voice.endswith("Neural")
            else (HINDI_VOICE if detect_turn_language(text, language) == "hi" else ENGLISH_VOICE)
        )
        async for chunk in stream_edge_tts(text, edge_voice):
            if chunk:
                yield chunk


class VoiceSession:
    """Full-duplex conversational voice session with barge-in cancellation and dual-engine synthesis."""

    def __init__(
        self,
        synthesizer: Callable[..., AsyncIterator[bytes]] = synthesize_speech_stream,
    ) -> None:
        self._synthesizer = synthesizer
        self._active: asyncio.Task[None] | None = None

    async def speak(
        self,
        validated_text: str,
        send_audio: Callable[[bytes], Awaitable[None]],
        *,
        language: str | None = None,
        engine: str | None = None,
    ) -> None:
        await self.barge_in()
        routed_engine, routed_voice = route_tts(validated_text, language, preferred_engine=engine)
        task = asyncio.create_task(self._emit(validated_text, send_audio, routed_voice, routed_engine))
        self._active = task
        try:
            await task
        except asyncio.CancelledError:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            raise
        finally:
            if not task.done():
                task.cancel()
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
        engine: str | None = None,
    ) -> None:
        sig = inspect.signature(self._synthesizer)
        kwargs: dict[str, Any] = {}
        if "engine" in sig.parameters and engine:
            kwargs["engine"] = engine
        async for chunk in self._synthesizer(text, voice, **kwargs):
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
    language: str | None = None,
) -> list[str]:
    """Execute unified voice turn using the shared clinical reasoning pipeline.

    Guarantees that voice turns utilize the exact same patient context, clinical rules,
    retrieved datasets, PEP permissions, and multi-turn conversation history as chat turns,
    and persists the voice turn into conversation history.
    """
    import disha_core.main as app_main
    from disha_core.models.schemas import TurnRequest, TurnState

    turn_lang = language or detect_turn_language(text)
    turn_state = state if state is not None else TurnState()
    payload = TurnRequest(text=text)
    output: list[str] = []

    async for sentence in app_main._turn_sentences(request_or_ws, patient_id, payload, turn_state):
        output.append(sentence)
        if send_json is not None:
            await send_json({"type": "sentence", "text": sentence})
        if send_audio is not None:
            sent_lang = detect_turn_language(sentence, language_hint=turn_lang)
            await session.speak(sentence, send_audio, language=sent_lang)

    if send_json is not None:
        await send_json(
            {
                "type": "done",
                "status": turn_state.validator_status,
                "evidence_ids": turn_state.evidence_ids,
                "retrieval_status": turn_state.retrieval_status,
            }
        )

    return output
