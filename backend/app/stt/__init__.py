"""Speech-to-text API endpoints backed by Granite Speech 5.0 TurboCTC.

These routes live under `/api/v1/stt` and reuse the same model service and
audio utilities that powered the original `unit testing/speech to text` proof of
concept. They are part of the main backend so `run-all.sh` starts a single
process for chat, data persistence and dictation.
"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentUser
from app.core.errors import (
    AppError,
    PayloadTooLargeError,
    ServiceUnavailableError,
    UnsupportedMediaTypeError,
    ValidationError,
)
from app.core.logging import get_logger
from app.stt.audio_utils import AudioValidationError, UnsupportedAudioError, decode_audio, is_silent
from app.stt.speech_service import ModelLoadError, SpeechService, TranscriptionError, get_service

router = APIRouter(prefix="/stt", tags=["speech-to-text"])
logger = get_logger(__name__)

# A long spoken message stays far below this.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _service() -> SpeechService:
    return get_service()


@router.get("/status")
def stt_status() -> dict[str, object]:
    """Return whether the model is loaded and which device it is using."""
    return _service().status_dict()


@router.post("/transcribe")
async def transcribe(
    user: CurrentUser,
    file: UploadFile = File(...),
) -> dict[str, object]:
    """Upload an audio clip and receive the recognised text.

    The caller must supply a valid FitAI access token; the user id is derived
    from it and never from the request body.
    """
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise PayloadTooLargeError("Audio clip is too large.")

    try:
        decoded = decode_audio(data, filename=file.filename)
    except UnsupportedAudioError as exc:
        logger.info("stt_audio_format_unsupported", user_id=user.id, error=str(exc))
        raise UnsupportedMediaTypeError(str(exc)) from exc
    except AudioValidationError as exc:
        logger.info("stt_audio_validation_failed", user_id=user.id, error=str(exc))
        raise ValidationError(str(exc)) from exc

    if is_silent(decoded.samples):
        return {
            "text": "",
            "warning": "The recording appears silent.",
            "audio": decoded.summary(),
        }

    try:
        result = await run_in_threadpool(
            _service().transcribe, decoded.samples, decoded.sample_rate
        )
    except ModelLoadError as exc:
        logger.error("stt_model_load_failed", user_id=user.id, error=str(exc))
        raise ServiceUnavailableError(str(exc)) from exc
    except TranscriptionError as exc:
        logger.error("stt_inference_failed", user_id=user.id, error=str(exc))
        raise AppError(str(exc)) from exc

    return {
        "text": result.text,
        "warning": result.warnings[0] if result.warnings else None,
        "audio": {"duration_s": result.duration_s},
        "model_id": result.model_id,
        "device": result.device,
    }
