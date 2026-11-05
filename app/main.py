from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.db import init_db
from app.api import router as api_router

STATIC_DIR = Path(__file__).resolve().parent / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure database schema and default clinical fixtures are initialized on startup
    init_db()
    yield

app = FastAPI(
    title="Disha AI — Health Coach",
    description="Real-time voice and text health follow-up engine with clinical safety guardrails.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static web directory
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(api_router)

@app.get("/")
def root(request: Request):
    """
    Serves the interactive Health Coach UI to web browsers,
    or returns service status JSON to automated API test clients.
    """
    accept = request.headers.get("accept", "")
    index_file = STATIC_DIR / "index.html"
    if "text/html" in accept and index_file.exists():
        return FileResponse(str(index_file))

    return {
        "service": "Disha AI Health Coach Backend",
        "status": "online",
        "docs_url": "/docs",
        "app_url": "/",
    }

@app.get("/app")
@app.get("/demo")
def serve_app():
    """Explicit endpoint to serve the Health Coach web application."""
    index_file = STATIC_DIR / "index.html"
    return FileResponse(str(index_file))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
