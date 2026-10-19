"""API tests for the backend speech-to-text endpoint.

The real Granite model is never loaded here. A fake ``SpeechService`` is swapped
in for each test so the suite stays fast, deterministic and offline.
"""

from __future__ import annotations

import uuid

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.stt import audio_utils
from app.stt.speech_service import (
    ModelLoadError,
    SpeechService,
    TranscriptionError,
    get_service,
    set_service,
)


def _make_service(transcriber=None) -> SpeechService:
    """Build a SpeechService whose load/transcribe steps are fully controlled."""

    def _loader():
        return (object(), object())

    service = SpeechService(
        model_id="fake-model",
        device="cpu",
        loader=_loader,
        transcriber=transcriber,
    )
    service.load()  # populates _processor/_model and sets status to ready
    service._device = "cpu"
    return service


@pytest.fixture(autouse=True)
def _reset_stt_service(monkeypatch) -> None:
    """Give every test a fresh fake service and clean up afterwards."""
    set_service(None)
    yield
    set_service(None)


def _valid_wav() -> bytes:
    samples = np.random.uniform(-0.1, 0.1, size=8_000).astype(np.float32)
    return audio_utils.wav_bytes(samples)


def test_status_reports_idle_when_not_loaded(client: TestClient) -> None:
    response = client.get("/api/v1/stt/status")
    assert response.status_code == 200
    body = response.json()
    assert body["model_id"] == "ibm-granite/granite-speech-5.0-470m-turboctc"
    assert body["state"] == "idle"
    assert body["device"] == "not loaded"


def test_transcribe_requires_auth(anon_client: TestClient) -> None:
    response = anon_client.post(
        "/api/v1/stt/transcribe", files={"file": ("x.wav", _valid_wav(), "audio/wav")}
    )
    assert response.status_code == 401


def test_transcribe_returns_text_for_valid_audio(client: TestClient, monkeypatch) -> None:
    def _transcriber(_processor, _model, samples, sample_rate):
        return "hello from granite"

    service = _make_service(_transcriber)
    set_service(service)

    response = client.post(
        "/api/v1/stt/transcribe", files={"file": ("voice.wav", _valid_wav(), "audio/wav")}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "hello from granite"
    assert "duration_s" in body["audio"]
    assert body["device"] == "cpu"


def test_transcribe_returns_empty_warning_for_silent_audio(client: TestClient) -> None:
    samples = np.zeros(8_000, dtype=np.float32)
    silent_wav = audio_utils.wav_bytes(samples)

    service = _make_service()
    set_service(service)

    response = client.post(
        "/api/v1/stt/transcribe", files={"file": ("silent.wav", silent_wav, "audio/wav")}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == ""
    assert body["warning"] == "The recording appears silent."


def test_transcribe_rejects_too_short_audio(client: TestClient) -> None:
    samples = np.random.uniform(-0.1, 0.1, size=800).astype(np.float32)
    short_wav = audio_utils.wav_bytes(samples)

    response = client.post(
        "/api/v1/stt/transcribe", files={"file": ("short.wav", short_wav, "audio/wav")}
    )
    assert response.status_code == 422


def test_transcribe_rejects_unsupported_format(client: TestClient) -> None:
    bad_bytes = b"this is not audio"
    response = client.post(
        "/api/v1/stt/transcribe", files={"file": ("bad.txt", bad_bytes, "text/plain")}
    )
    assert response.status_code == 415


def test_transcribe_returns_503_when_model_will_not_load(client: TestClient) -> None:
    def _broken(_processor, _model, _samples, _sample_rate):
        raise ModelLoadError("GPU not available")

    service = _make_service(_broken)
    set_service(service)

    response = client.post(
        "/api/v1/stt/transcribe", files={"file": ("voice.wav", _valid_wav(), "audio/wav")}
    )
    body = response.text
    assert response.status_code == 503, f"unexpected status {response.status_code}: {body!r}"
    assert "GPU not available" in body


def test_transcribe_returns_500_on_inference_failure(client: TestClient) -> None:
    def _broken(_processor, _model, _samples, _sample_rate):
        raise TranscriptionError("inference exploded")

    service = _make_service(_broken)
    set_service(service)

    response = client.post(
        "/api/v1/stt/transcribe", files={"file": ("voice.wav", _valid_wav(), "audio/wav")}
    )
    body = response.text
    assert response.status_code == 500, f"unexpected status {response.status_code}: {body!r}"
    assert "inference exploded" in body


def test_transcribe_rejects_oversized_upload(client: TestClient) -> None:
    huge = b"\x00" * (25 * 1024 * 1024 + 1)
    response = client.post(
        "/api/v1/stt/transcribe", files={"file": ("huge.wav", huge, "audio/wav")}
    )
    assert response.status_code == 413


def test_user_id_is_derived_from_token_not_request_body(client: TestClient) -> None:
    """The endpoint must never trust a user id supplied by the caller."""

    def _transcriber(_processor, _model, _samples, _sample_rate):
        return "ok"

    set_service(_make_service(_transcriber))
    response = client.post(
        "/api/v1/stt/transcribe",
        files={"file": ("voice.wav", _valid_wav(), "audio/wav")},
        data={"user_id": str(uuid.uuid4())},
    )
    assert response.status_code == 200
    assert response.json()["text"] == "ok"


# Expose the real singleton for tests that intentionally want to inspect it.
def _real_service() -> SpeechService:
    return get_service()
