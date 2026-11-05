"""FastAPI app. Run with:  uvicorn cartlog.api:app --reload  (from the backend/ folder)."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .memory import Memory
from .orchestrator import Orchestrator
from .schemas import SearchResponse, TextSearchRequest
from .service import SearchService

MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # MCP servers start once and stay up, so no search pays process start-up cost.
    async with Orchestrator() as orchestrator:
        app.state.service = SearchService(orchestrator, Memory())
        yield


app = FastAPI(title="CartLog AI", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
async def health():
    return {"ok": True, "llm": settings.llm_enabled, "agents": list(app.state.service.orchestrator.sessions)}


@app.post("/api/search", response_model=SearchResponse)
async def search(req: TextSearchRequest):
    return await app.state.service.search_text(req.text, req.session_id)


@app.post("/api/search/image", response_model=SearchResponse)
async def search_image(image: UploadFile = File(...), note: str | None = Form(None), session_id: str | None = Form(None)):
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(415, "Upload a JPEG, PNG or WebP image.")
    data = await image.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image is larger than 8 MB.")
    try:
        return await app.state.service.search_image(data, image.content_type, note, session_id)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/history/{session_id}")
async def history(session_id: str):
    return app.state.service.memory.history(session_id)
