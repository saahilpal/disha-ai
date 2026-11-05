import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "Disha AI Health Coach")
    ENV: str = os.getenv("ENV", "development")
    PORT: int = int(os.getenv("PORT", "8000"))
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "disha.db"))
    
    # Gemini Configuration
    @property
    def GEMINI_API_KEY(self) -> str:
        load_dotenv(BASE_DIR / ".env", override=True)
        return os.getenv("GEMINI_API_KEY", "")

    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
    GEMINI_EXTRACTION_MODEL: str = os.getenv("GEMINI_EXTRACTION_MODEL", "gemini-flash-lite-latest")
    
    # Optional Provider: Groq
    @property
    def GROQ_API_KEY(self) -> str:
        load_dotenv(BASE_DIR / ".env", override=True)
        return os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
    
    # Rate Limiting & Usage Protection
    RATE_LIMIT_RPM: int = int(os.getenv("RATE_LIMIT_RPM", "15"))
    MAX_CONCURRENT_PER_USER: int = int(os.getenv("MAX_CONCURRENT_PER_USER", "1"))
    DAILY_REQUEST_BUDGET: int = int(os.getenv("DAILY_REQUEST_BUDGET", "1400"))
    MAX_INPUT_TOKENS: int = int(os.getenv("MAX_INPUT_TOKENS", "2000"))
    MAX_OUTPUT_TOKENS: int = int(os.getenv("MAX_OUTPUT_TOKENS", "800"))
    
    # Audio Settings
    TTS_VOICE: str = os.getenv("TTS_VOICE", "en-IN-NeerjaNeural")

settings = Settings()
