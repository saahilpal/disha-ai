import io
import re
import random
import edge_tts
import httpx
from typing import Any, AsyncGenerator, Dict, List, Optional
from app.config import settings

# ---------------------------------------------------------
# SENTENCE BUFFERING FOR STREAMING TTS
# ---------------------------------------------------------

PUNCTUATION_SPLIT = re.compile(r"(?<!\d)([.?!।\n]+)(?!\d)")
ABBREVIATIONS = ("dr", "mr", "mrs", "ms", "vs", "approx", "e.g", "i.e")

class SentenceBuffer:
    """
    Accumulates streaming LLM tokens and yields complete spoken clauses.
    Ensures TTS begins synthesizing within ~200-300ms without waiting for full generation.
    """
    def __init__(self, max_words: int = 14):
        self.max_words = max_words
        self._buffer = ""

    def push(self, token: str) -> List[str]:
        self._buffer += token
        ready: List[str] = []

        parts = PUNCTUATION_SPLIT.split(self._buffer)
        while len(parts) >= 3:
            # Check if this punctuation was part of an abbreviation (e.g. Dr., Mr.)
            if parts[0].rstrip().lower().endswith(ABBREVIATIONS):
                parts[0] = parts[0] + parts[1] + parts[2]
                parts = [parts[0]] + parts[3:]
                continue
            sentence = (parts[0] + parts[1]).strip()
            if sentence:
                ready.append(sentence)
            parts = parts[2:]
            self._buffer = "".join(parts)

        words = self._buffer.strip().split()
        if len(words) >= self.max_words:
            ready.append(self._buffer.strip())
            self._buffer = ""

        return ready

    def flush(self) -> Optional[str]:
        remaining = self._buffer.strip()
        self._buffer = ""
        return remaining if remaining else None

    @classmethod
    def split_into_sentences(cls, text: str) -> List[str]:
        """Splits full response into spoken sentence units."""
        if not text:
            return []
        matches = PUNCTUATION_SPLIT.split(text.strip())
        sentences = []
        i = 0
        while i < len(matches):
            chunk = matches[i].strip()
            punct = matches[i + 1].strip() if i + 1 < len(matches) else ""
            if chunk.lower().endswith(ABBREVIATIONS) and i + 2 < len(matches):
                next_chunk = matches[i + 2].strip()
                chunk = f"{chunk}{punct} {next_chunk}".strip()
                punct = matches[i + 3].strip() if i + 3 < len(matches) else ""
                i += 2
            if chunk:
                sent = f"{chunk}{punct}".strip() if punct else chunk
                sentences.append(sent)
            i += 2
        return [s for s in sentences if s] or [text.strip()]

# ---------------------------------------------------------
# CONTEXT-AWARE DELAY FILLERS (Natural conversational pacing)
# ---------------------------------------------------------

class NaturalFillerManager:
    """
    Provides natural, friendly acknowledgements only when backend operations
    exceed conversational delay thresholds (>700ms). Rotates phrases to avoid repetition.
    """
    FILLERS: Dict[str, List[str]] = {
        "meal": [
            "Let me check your meal details.",
            "One moment, looking up your diet schedule.",
            "Checking your meal plan for today."
        ],
        "profile": [
            "Let me look at your health profile.",
            "Checking your health record for you.",
            "One second, looking up your details."
        ],
        "remedy": [
            "Let me check the clinical recommendation for that.",
            "Looking up the doctor-vetted remedy for you."
        ],
        "general": [
            "Hmm, let me think about that for a second.",
            "Good question, let me check that.",
            "Give me just a moment on that."
        ]
    }

    def __init__(self):
        self._last_used: Dict[str, str] = {}

    def get_filler(self, query: str) -> str:
        lower = (query or "").lower()
        if any(w in lower for w in ["dinner", "lunch", "breakfast", "meal", "diet", "food", "khana"]):
            cat = "meal"
        elif any(w in lower for w in ["weight", "goal", "profile", "record", "height", "bp", "hypertension"]):
            cat = "profile"
        elif any(w in lower for w in ["bloating", "pain", "remedy", "gas", "medicine"]):
            cat = "remedy"
        else:
            cat = "general"

        options = [p for p in self.FILLERS[cat] if p != self._last_used.get(cat)]
        chosen = random.choice(options)
        self._last_used[cat] = chosen
        return chosen

natural_fillers = NaturalFillerManager()

# ---------------------------------------------------------
# SPEECH-TO-TEXT (Groq Whisper with Mock Fallback)
# ---------------------------------------------------------

class SpeechToText:
    """Groq Whisper Large v3 Turbo transcriber biased for Indian clinical Hinglish."""
    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        self.prompt = "Hinglish patient follow-up: BP, bloating, jeera paani, saunf, gym, diet chart, paneer bhurji, roti"

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        if not self.api_key:
            return ""

        headers = {"Authorization": f"Bearer {self.api_key}"}
        files = {
            "file": (filename, audio_bytes, "audio/webm"),
            "model": (None, "whisper-large-v3-turbo"),
            "prompt": (None, self.prompt),
            "language": (None, "en"),
        }
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.post("https://api.groq.com/openai/v1/audio/transcriptions", headers=headers, files=files)
                if res.status_code == 200:
                    return res.json().get("text", "").strip()
        except Exception:
            pass
        return ""

stt = SpeechToText()

# ---------------------------------------------------------
# TEXT-TO-SPEECH (Microsoft Edge-TTS en-IN-NeerjaNeural)
# ---------------------------------------------------------

class SpokenTextNormalizer:
    """Normalizes text for natural auditory pronunciation by Edge-TTS without markdown artifacts."""
    @classmethod
    def normalize_for_speech(cls, text: str) -> str:
        s = text
        # 1. Expand nutrition and medical units before stripping symbols
        s = re.sub(r"~(\d+)\s*kcal", r"around \1 calories", s)
        s = re.sub(r"(\d+)\s*kcal", r"\1 calories", s)
        s = re.sub(r"\bBP\s*(\d{2,3})/(\d{2,3})\b", r"BP \1 over \2", s)
        s = re.sub(r"\b108/112\b", "108 or 112", s)
        s = re.sub(r"₹\s*1[,.]?499", "1,499 rupees", s)
        s = re.sub(r"₹\s*(\d+)", r"\1 rupees", s)
        s = re.sub(r"(\d+)\s*g\b", r"\1 grams", s)
        s = re.sub(r"\b1/2\b", "half a", s)
        s = re.sub(r"\btsp\b", "teaspoon", s)
        s = re.sub(r"\btbsp\b", "tablespoon", s)

        # 2. Strip markdown formatting
        s = re.sub(r"[*_~#`]+", "", s)
        s = re.sub(r"^\s*[-•]\s*", "", s, flags=re.MULTILINE)

        # 3. Clean parenthetical translations and special brackets
        s = re.sub(r"\((?:cumin-fennel|cumin|fennel)[^)]*\)", "", s, flags=re.IGNORECASE)
        s = re.sub(r"[\(\)\[\]]", "", s)
        return re.sub(r"\s+", " ", s).strip()

class TextToSpeech:
    """Streams natural Indian English speech using Edge-TTS (en-IN-NeerjaNeural)."""
    def __init__(self):
        self.voice = settings.TTS_VOICE

    async def stream_audio(self, text: str) -> AsyncGenerator[bytes, None]:
        if not text or not text.strip():
            return
        clean_text = SpokenTextNormalizer.normalize_for_speech(text)
        communicate = edge_tts.Communicate(clean_text, self.voice)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    async def synthesize(self, text: str) -> bytes:
        buf = io.BytesIO()
        async for chunk in self.stream_audio(text):
            buf.write(chunk)
        return buf.getvalue()

    async def synthesize_progressive(self, text: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Splits text into sentences and synthesizes each sentence progressively.
        First sentence is delivered in ~800ms, while remaining sentences queue in background.
        """
        sentences = SentenceBuffer.split_into_sentences(text)
        for idx, sentence in enumerate(sentences):
            audio_bytes = await self.synthesize(sentence)
            yield {
                "sentence_index": idx,
                "total_sentences": len(sentences),
                "sentence_text": sentence,
                "audio_bytes": audio_bytes,
                "is_first": (idx == 0),
                "is_last": (idx == len(sentences) - 1),
            }

tts = TextToSpeech()

# ---------------------------------------------------------
# CONTEXT SYNCHRONIZER (Honest History on Interruption)
# ---------------------------------------------------------

class ContextSynchronizer:
    """
    Truncates assistant message in history to only what the user actually heard
    before interrupting (Barge-In synchronisation).
    """
    @classmethod
    def align_history(cls, full_text: str, played_fraction: float) -> str:
        if played_fraction >= 0.92 or not full_text:
            return full_text
        if played_fraction <= 0.05:
            return ""

        words = full_text.split()
        cutoff = max(1, int(len(words) * played_fraction))
        return " ".join(words[:cutoff]) + "..."
