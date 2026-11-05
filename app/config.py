import os
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    APP_NAME: str = "Disha Clinical Voice AI"
    APP_ENV: str = os.getenv("APP_ENV", "development")
    PORT: int = int(os.getenv("PORT", "8000"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Database
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "disha_clinical.db"))
    
    # External APIs (Zero-cost free tiers)
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_DEFAULT_MODEL: str = os.getenv("GROQ_DEFAULT_MODEL", "llama-3.3-70b-versatile")
    GROQ_FALLBACK_MODEL: str = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")
    
    # Audio
    TTS_VOICE: str = os.getenv("TTS_VOICE", "hi-IN-SwaraNeural")
    TTS_SECONDARY_VOICE: str = os.getenv("TTS_SECONDARY_VOICE", "en-IN-NeerjaNeural")
    
    # Care Ops Webhook
    CARE_OPS_WEBHOOK_URL: str = os.getenv("CARE_OPS_WEBHOOK_URL", "")
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

