"""HTTP contract of the standalone transcription service and its page."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from audio_utils import TARGET_SAMPLE_RATE, wav_bytes
from conftest import FakeModel, FakeProcessor
from speech_service import SpeechService, set_service

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


def test_status_reports_a_ready_service(client):
    response = client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "ready"
    assert body["sample_rate"] == TARGET_SAMPLE_RATE


def test_transcribe_returns_structured_json(client, wav_upload):
    response = client.post("/api/transcribe", files={"file": ("clip.wav", wav_upload, "audio/wav")})

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "hello from granite"
    assert body["audio"]["duration_s"] == pytest.approx(1.0, abs=0.01)
    assert body["audio"]["sample_rate"] == TARGET_SAMPLE_RATE
    assert body["audio"]["source_format"] == "wav"
    assert body["model"]["model_id"] == "test/model"
    assert body["warnings"] == []


def test_transcribe_returns_empty_text_for_silence(client):
    silence = wav_bytes(np.zeros(TARGET_SAMPLE_RATE, dtype=np.float32))

    response = client.post("/api/transcribe", files={"file": ("clip.wav", silence, "audio/wav")})

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == ""
    assert "No speech" in body["warning"]


def test_transcribe_rejects_an_empty_upload(client):
    response = client.post("/api/transcribe", files={"file": ("clip.wav", b"", "audio/wav")})

    assert response.status_code == 422
    assert "empty" in response.json()["detail"].lower()


def test_transcribe_rejects_an_unsupported_format(client):
    response = client.post("/api/transcribe", files={"file": ("clip.aiff", b"\x00\x01\x02\x03", "audio/aiff")})

    assert response.status_code == 422
    assert "Unsupported audio format" in response.json()["detail"]


def test_transcribe_requires_a_file(client):
    assert client.post("/api/transcribe").status_code == 422


def test_transcribe_returns_503_when_the_model_failed_to_load(speech_sample):
    service = SpeechService(
        model_id="test/model",
        device="cpu",
        loader=lambda: (_ for _ in ()).throw(RuntimeError("checkpoint download failed")),
        transcriber=lambda *_: "",
    )
    set_service(service)
    try:
        from fastapi.testclient import TestClient

        import app as app_module

        with TestClient(app_module.app) as test_client:
            upload = wav_bytes(speech_sample)
            response = test_client.post("/api/transcribe", files={"file": ("clip.wav", upload, "audio/wav")})
            assert response.status_code == 503
            assert "checkpoint download failed" in response.json()["detail"]
    finally:
        set_service(None)


def test_status_reports_a_load_failure(wav_upload):
    service = SpeechService(
        model_id="test/model",
        device="cpu",
        loader=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        transcriber=lambda *_: "",
    )
    service.warmup()
    set_service(service)
    try:
        from fastapi.testclient import TestClient

        import app as app_module

        with TestClient(app_module.app) as test_client:
            body = test_client.get("/api/status").json()
            assert body["state"] == "error"
            assert "boom" in body["error"]
    finally:
        set_service(None)


def test_serves_the_experiment_page(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "Speech-to-text proof of concept" in response.text


def test_page_exposes_the_recording_controls():
    """Static contract for the manual microphone flow."""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    for control in ('id="message-input"', 'id="mic-button"', 'id="stop-button"', 'id="clear-button"'):
        assert control in html, f"missing {control}"
    assert 'id="recording-indicator"' in html
    assert 'id="transcribing-indicator"' in html
    assert 'id="error-message"' in html


def test_frontend_hides_indicators_that_carry_the_hidden_attribute():
    """`.indicator { display: flex }` would otherwise defeat [hidden]."""
    styles = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")

    assert re.search(r"\[hidden\]\s*\{[^}]*display:\s*none\s*!important", styles)


def test_frontend_requests_the_microphone_posts_and_inserts_the_text():
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "getUserMedia" in script
    assert "new MediaRecorder" in script
    assert "fetch('/api/transcribe'" in script
    # The recognised text is written into the textarea, not appended to a log.
    assert re.search(r"els\.input\.value = .*payload\.text", script)
    # Stopping a recording never sends anything to a chat backend.
    assert "/api/chat" not in script
    assert "openai" not in script.lower() and "groq" not in script.lower()


def test_frontend_surfaces_errors_for_denied_microphone_access():
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "NotAllowedError" in script
    assert "Microphone permission was denied" in script