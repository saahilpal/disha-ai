import os
import time
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db.connection import get_connection
from app.api.routes_rules import router as rules_router
from app.api.routes_patients import router as patients_router
from app.api.routes_simulation import router as simulation_router
from app.api.routes_ws import router as ws_router

app = FastAPI(
    title="Disha AI — Clinical Voice AI Hub",
    description="Deterministic Hinglish Voice Follow-Up Engine with Sub-Second Turn Latency and Clinical Safety Guardrails.",
    version="1.0.0"
)

# Enable CORS for local simulation and multi-client access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static web directory
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Register API Routers
app.include_router(rules_router)
app.include_router(patients_router)
app.include_router(simulation_router)
app.include_router(ws_router)

# Health & Readiness Check
@app.get("/health")
def health_check():
    """System health check verifying database and engine readiness."""
    db_ok = False
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        db_ok = bool(cursor.fetchone())
        conn.close()
    except Exception as e:
        db_ok = False

    return {
        "status": "healthy" if db_ok else "degraded",
        "database_connected": db_ok,
        "database_path": settings.DATABASE_PATH,
        "llm_provider": "Groq" if settings.GROQ_API_KEY else "Offline Mock Engine",
        "llm_model": settings.GROQ_DEFAULT_MODEL,
        "tts_voice": settings.TTS_VOICE,
        "turn_latency_target_ms": 1200,
        "timestamp": time.time()
    }

# Serve Main Clinical Studio UI
@app.get("/")
def serve_index():
    """Serves the interactive Clinical Studio and Voice Simulator web interface."""
    index_file = STATIC_DIR / "index.html"
    return FileResponse(str(index_file))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
