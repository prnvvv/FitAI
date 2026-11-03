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
from app.core.config import settings
from app.core.errors import (
    AppError,
    PayloadTooLargeError,
    ServiceUnavailableError,
    UnsupportedMediaTypeError,
    ValidationError,
)
from app.core.logging import get_logger
from app.stt.audio_utils import AudioValidationError, UnsupportedAudioError, decode_audio, is_silent
from app.stt.remote_service import (
    UnsupportedAudioFormatError,
    get_remote_transcriber,
    sniff_audio_format,
)
from app.stt.speech_service import ModelLoadError, SpeechService, TranscriptionError, get_service

router = APIRouter(prefix="/stt", tags=["speech-to-text"])
logger = get_logger(__name__)

# A long spoken message stays far below this.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _service() -> SpeechService:
    return get_service()


def _is_remote() -> bool:
    return settings.stt_provider.strip().lower() == "remote"


@router.get("/status")
def stt_status(_user: CurrentUser) -> dict[str, object]:
    """Return whether the model is loaded and which provider/device it is using.

    Requires a valid access token like every other STT route (the web app already
    sends one), so a public STT service does not advertise its configuration.
    """
    if _is_remote():
        return get_remote_transcriber().status_dict()
    return _service().status_dict()


async def _read_limited(file: UploadFile, limit: int) -> bytes:
    """Read at most ``limit`` bytes; refuse anything larger without buffering it all."""
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise PayloadTooLargeError("Audio clip is too large.")
    return data


async def _transcribe_remote(user: CurrentUser, file: UploadFile) -> dict[str, object]:
    """Validate cheaply, then forward the original bytes to the configured provider.

    No local decode: decoding a long compressed clip to float32 PCM can take
    hundreds of MB, which a 512 MB instance cannot afford.
    """
    data = await _read_limited(file, settings.stt_max_upload_mb * 1024 * 1024)
    if not data:
        raise ValidationError("The audio clip is empty.")
    try:
        container = sniff_audio_format(data)
    except UnsupportedAudioFormatError as exc:
        logger.info("stt_audio_format_unsupported", user_id=user.id)
        raise UnsupportedMediaTypeError(str(exc)) from exc

    transcriber = get_remote_transcriber()
    try:
        result = await run_in_threadpool(
            transcriber.transcribe,
            data,
            file.filename or f"audio.{container}",
            file.content_type or "",
        )
    except ModelLoadError as exc:
        logger.error("stt_remote_not_configured", user_id=user.id)
        raise ServiceUnavailableError(str(exc)) from exc
    except TranscriptionError as exc:
        logger.error("stt_remote_failed", user_id=user.id, error=str(exc))
        raise AppError(str(exc)) from exc
    finally:
        del data
    return {
        "text": result.text,
        "warning": None,
        "audio": {"duration_s": None},
        "model_id": result.model_id,
        "device": result.device,
    }


@router.post("/transcribe")
async def transcribe(
    user: CurrentUser,
    file: UploadFile = File(...),
) -> dict[str, object]:
    """Upload an audio clip and receive the recognised text.

    The caller must supply a valid FitAI access token; the user id is derived
    from it and never from the request body.
    """
    if _is_remote():
        return await _transcribe_remote(user, file)

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
