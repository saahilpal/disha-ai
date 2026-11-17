"""Generate pre-rendered static intro audio assets for Disha AI Voice Consultation.
Each file is under 100 KB and contains the exact introductory greeting per language:
- Hinglish: 'Hi, main Disha, aapki AI health coach hoon.' (hi-IN-SwaraNeural)
- English: 'Hi, I\'m Disha, your AI health coach.' (en-IN-NeerjaExpressiveNeural)
- Hindi: 'हाय, मैं दिशा, आपकी एआई हेल्थ कोच हूँ।' (hi-IN-SwaraNeural)
Zero banned greetings ('namaste', 'namaskar') permitted.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import edge_tts

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "disha_core" / "data" / "intro_audio"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

INTRO_TEXTS = {
    "hinglish": ("Hi, main Disha, aapki AI health coach hoon.", "hi-IN-SwaraNeural"),
    "en": ("Hi, I'm Disha, your AI health coach.", "en-IN-NeerjaExpressiveNeural"),
    "hi": ("हाय, मैं दिशा, आपकी एआई हेल्थ कोच हूँ।", "hi-IN-SwaraNeural"),
}


async def generate_all() -> None:
    for lang, (text, voice) in INTRO_TEXTS.items():
        out_file = OUTPUT_DIR / f"intro_{lang}.mp3"
        print(f"Generating {out_file.name} with voice {voice}...")
        communicate = edge_tts.Communicate(text, voice, rate="+12%")
        await communicate.save(str(out_file))
        size_kb = out_file.stat().st_size / 1024
        print(f"  -> {out_file.name}: {size_kb:.1f} KB (must be < 100 KB)")
        assert size_kb < 100.0, f"File {out_file.name} exceeded 100 KB"
        # Banned greeting check
        lower = text.lower()
        assert "namaste" not in lower and "namaskar" not in lower, "Banned greeting detected"


if __name__ == "__main__":
    asyncio.run(generate_all())
