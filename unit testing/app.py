"""Standalone API for the FitAI speech-to-text proof of concept.

This service is deliberately separate from the FitAI backend: it holds no chat
state, calls no LLM and never touches the FitAI database or API routes. The
browser posts a recorded clip to `/api/transcribe` and receives JSON text that
the page inserts into its own textarea.
"""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from audio_utils import AudioValidationError, decode_audio, is_silent
from speech_service import ModelLoadError, SpeechService, TranscriptionError, get_service, set_service

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
RECORDINGS_DIR = BASE_DIR / "recordings"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # a long spoken message stays far below this


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Warm the model in the background so the first recording is not slowed."""
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    service = get_service()
    if service.eager_load:
        threading.Thread(target=service.warmup, name="stt-warmup", daemon=True).start()
    yield


app = FastAPI(title="FitAI STT proof of concept", docs_url="/api/docs", lifespan=lifespan)


def _service() -> SpeechService:
    return get_service()


@app.get("/api/status")
async def status() -> JSONResponse:
    service = _service()
    return JSONResponse(service.status_dict())


@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)) -> JSONResponse:
    payload = await file.read()
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The recording is larger than 25 MB.")

    try:
        decoded = await run_in_threadpool(decode_audio, payload, file.filename)
    except AudioValidationError as exc:
        # 422: the request is understood but the audio is not usable.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if is_silent(decoded.samples):
        return JSONResponse(
            {
                "text": "",
                "warning": "No speech was detected in that recording.",
                "audio": decoded.summary(),
                "model": {
                    "model_id": _service().model_id,
                    "device": _service().status.device,
                    "state": _service().status.state,
                },
            }
        )

    try:
        result = await run_in_threadpool(
            _service().transcribe, decoded.samples, decoded.sample_rate
        )
    except ModelLoadError as exc:
        # 503: the service itself is unavailable, the client may retry later.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TranscriptionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse(
        {
            "text": result.text,
            "audio": decoded.summary(),
            "model": {
                "model_id": result.model_id,
                "device": result.device,
                "load_seconds": result.load_seconds,
            },
            "warnings": result.warnings,
        }
    )


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":  # pragma: no cover - manual entry point
    import os

    import uvicorn

    uvicorn.run(
        "app:app",
        host=os.environ.get("STT_HOST", "127.0.0.1"),
        port=int(os.environ.get("STT_PORT", "8077")),
        reload=False,
    )