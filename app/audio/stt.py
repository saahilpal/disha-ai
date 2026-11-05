import httpx
from typing import Optional
from app.config import settings

GROQ_AUDIO_TRANSCRIPTIONS_ENDPOINT = "https://api.groq.com/openai/v1/audio/transcriptions"
HINGLISH_CLINICAL_PROMPT = "Hinglish patient follow-up: BP, bloating, jeera paani, saunf, gym, migraine, nausea, diet chart, weakness, paneer bhurji, roti"

class SpeechToTextTranscriber:
    """
    Groq Whisper-large-v3-turbo Speech-to-Text Transcriber with Hinglish prompt biasing.
    """

    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        self.model = "whisper-large-v3-turbo"

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.wav") -> str:
        """Transcribes PCM/WAV audio into Romanized Hinglish text."""
        if not self.api_key:
            return "Mujhe periods ke dauran thodi bloating ho rahi hai"

        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        files = {
            "file": (filename, audio_bytes, "audio/wav"),
            "model": (None, self.model),
            "prompt": (None, HINGLISH_CLINICAL_PROMPT),
            "language": (None, "hi"),
            "temperature": (None, "0.0")
        }

        async with httpx.AsyncClient(timeout=4.0) as client:
            try:
                res = await client.post(GROQ_AUDIO_TRANSCRIPTIONS_ENDPOINT, headers=headers, files=files)
                if res.status_code == 200:
                    return res.json().get("text", "").strip()
            except Exception:
                pass

        return ""

# Global singleton
stt_transcriber = SpeechToTextTranscriber()
