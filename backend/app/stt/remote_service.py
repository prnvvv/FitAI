"""Speech-to-text through an external OpenAI-compatible transcription endpoint.

The local Granite model needs far more than 512 MB, so the memory-constrained STT
service forwards the (validated) audio to a provider instead. No endpoint is
defaulted: ``STT_REMOTE_URL``, ``STT_REMOTE_API_KEY`` and ``STT_REMOTE_MODEL`` must
be set, and a missing value fails with a clear configuration error rather than
silently falling back to anything else.

Expected provider contract (the de-facto ``/audio/transcriptions`` shape):
``POST multipart/form-data`` with ``file`` and ``model`` fields and a bearer token,
answering ``{"text": "..."}``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.stt.speech_service import ModelLoadError, TranscriptionError, TranscriptionResult


class UnsupportedAudioFormatError(ValueError):
    """The upload does not look like a supported audio container."""


# Leading-byte signatures of the containers browsers and phones produce.
_SIGNATURES: tuple[tuple[int, bytes, str], ...] = (
    (0, b"RIFF", "wav"),
    (0, b"OggS", "ogg"),
    (0, b"\x1a\x45\xdf\xa3", "webm"),
    (0, b"fLaC", "flac"),
    (0, b"ID3", "mp3"),
    (4, b"ftyp", "mp4"),
)


def sniff_audio_format(data: bytes) -> str:
    """Return the container name from magic bytes, or raise ``UnsupportedAudioFormatError``."""
    for offset, magic, name in _SIGNATURES:
        if data[offset : offset + len(magic)] == magic:
            return name
    if len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:  # MPEG frame sync
        return "mp3"
    raise UnsupportedAudioFormatError("Unsupported audio format.")


@dataclass
class RemoteStatus:
    requests: int = 0
    last_error: str | None = None


class RemoteTranscriber:
    """Bounded, shared-client wrapper around the configured transcription endpoint."""

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_s: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        # An explicit "" means "unset" (do not fall back to the environment).
        self._url = settings.stt_remote_url if url is None else url
        self._key = settings.stt_remote_api_key if api_key is None else api_key
        self._model = settings.stt_remote_model if model is None else model
        self._timeout = timeout_s or settings.stt_remote_timeout_s
        self._client = client
        self.status = RemoteStatus()

    @property
    def configured(self) -> bool:
        return bool(self._url and self._key and self._model)

    def status_dict(self) -> dict[str, object]:
        return {
            "state": "ready" if self.configured else "unconfigured",
            "provider": "remote",
            "model_id": self._model,
            "device": "remote",
            "requests": self.status.requests,
            "error": None if self.configured else "Remote STT is not configured.",
        }

    def transcribe(self, data: bytes, filename: str, content_type: str) -> TranscriptionResult:
        if not self.configured:
            raise ModelLoadError(
                "Speech-to-text is not configured. Set STT_REMOTE_URL, "
                "STT_REMOTE_API_KEY and STT_REMOTE_MODEL."
            )
        if self._client is None:
            self._client = httpx.Client(timeout=httpx.Timeout(self._timeout, connect=10.0))
        started = time.perf_counter()
        self.status.requests += 1
        try:
            response = self._client.post(
                str(self._url),
                headers={"Authorization": f"Bearer {self._key}"},
                data={"model": str(self._model), "response_format": "json"},
                files={"file": (filename or "audio", data, content_type or "audio/webm")},
            )
            response.raise_for_status()
            text = str(response.json().get("text", "")).strip()
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            # The provider's body is never logged or returned: it may echo secrets.
            self.status.last_error = type(exc).__name__
            raise TranscriptionError(
                f"The transcription provider request failed ({type(exc).__name__})."
            ) from exc
        return TranscriptionResult(
            text=text,
            duration_s=round(time.perf_counter() - started, 3),
            model_id=str(self._model),
            device="remote",
        )


_transcriber: RemoteTranscriber | None = None


def get_remote_transcriber() -> RemoteTranscriber:
    """Return the process-wide transcriber (one HTTP client)."""
    global _transcriber
    if _transcriber is None:
        _transcriber = RemoteTranscriber()
    return _transcriber


def set_remote_transcriber(transcriber: RemoteTranscriber | None) -> None:
    """Replace the shared transcriber (tests)."""
    global _transcriber
    _transcriber = transcriber
